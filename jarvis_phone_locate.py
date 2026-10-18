"""Phone locator (2026-10-17, owner request): where are my phones?

The owner's Android phones run the "Jarvis Locator" app (source in phone_locator/). Each one sends its GPS position
every few minutes, and when Jarvis asks, through an ntfy topic. Everything on that topic is sealed with AES-256-GCM
under a key only Jarvis and the paired phones hold, so the relay (ntfy.sh by default) sees random text, and a stranger
who guesses the topic can neither read a position, nor fake one, nor make the phones answer.

Pairing: Jarvis makes a random topic + key once (kept in .env as JARVIS_PHONE_LOCATOR_TOPIC / _KEY, both write-only on
the Settings page) and shows a setup code on the dashboard Phones page: "JLOC1." + base64url(JSON {s, t, k}).

Message format (both directions): base64url(nonce[12] + ciphertext + tag[16]), associated data b"jloc1|" + topic.
  phone -> Jarvis: {"type": "loc"|"nofix", "id", "phone", "lat", "lon", "acc", "fix_ts", "sent_ts", "battery", ...}
  Jarvis -> phone: {"type": "ask", "ts", "nonce", "phone"?}   (phones ignore asks older than 10 minutes)

Pure module: never imports jarvis.py; the DB connection, network calls and the clock are passed in so tests use fakes.
"""

from __future__ import annotations

import base64
import json
import logging
import math
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from typing import Callable

log = logging.getLogger("jarvis.phone_locate")

PREFIX = "JLOC1."
ENV_TOPIC = "JARVIS_PHONE_LOCATOR_TOPIC"
ENV_KEY = "JARVIS_PHONE_LOCATOR_KEY"
ENV_SERVER = "JARVIS_PHONE_LOCATOR_SERVER"
DEFAULT_SERVER = "https://ntfy.sh"
MAX_DEVICES = 10
HISTORY_DAYS = 7
HISTORY_MAX_ROWS = 5000
FUTURE_SLACK_MS = 10 * 60 * 1000
_TOPIC_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_ID_RE = re.compile(r"^[a-z0-9]{8,32}$")


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    s = s.strip()
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# --- pairing ---------------------------------------------------------------------------------
def new_pairing() -> dict:
    return {"topic": "jloc_" + secrets.token_urlsafe(24).replace("-", "a").replace("_", "b"),
            "key": _b64e(secrets.token_bytes(32))}


def setup_code(server: str, topic: str, key: str) -> str:
    body = json.dumps({"s": server.rstrip("/"), "t": topic, "k": key}, separators=(",", ":")).encode()
    return PREFIX + _b64e(body)


def parse_setup_code(code: str) -> dict | None:
    c = re.sub(r"\s+", "", code or "")
    if PREFIX not in c:
        return None
    try:
        o = json.loads(_b64d(c.split(PREFIX, 1)[1]))
        key = _b64d(o["k"])
        if not str(o["s"]).startswith("https://") or not _TOPIC_RE.match(o["t"]) or len(key) != 32:
            return None
        return {"server": o["s"], "topic": o["t"], "key": o["k"]}
    except Exception:
        return None


def valid_config(server: str, topic: str, key: str) -> bool:
    try:
        return (server.startswith("https://") or server.startswith("http://127.0.0.1")) and bool(
            _TOPIC_RE.match(topic or "")) and len(_b64d(key or "")) == 32
    except Exception:
        return False


# --- sealing ---------------------------------------------------------------------------------
def _aad(topic: str) -> bytes:
    return ("jloc1|" + topic).encode()


def seal(key: str, topic: str, obj: dict) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = secrets.token_bytes(12)
    ct = AESGCM(_b64d(key)).encrypt(nonce, json.dumps(obj, separators=(",", ":")).encode(), _aad(topic))
    return _b64e(nonce + ct)


def open_sealed(key: str, topic: str, text: str) -> dict | None:
    """The decrypted JSON object, or None for anything not sealed with this key (or changed on the way)."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        raw = _b64d(text)
        if len(raw) < 12 + 16:
            return None
        obj = json.loads(AESGCM(_b64d(key)).decrypt(raw[:12], raw[12:], _aad(topic)))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


# --- validating a phone's report -------------------------------------------------------------
def _clean_name(s) -> str:
    s = re.sub(r"[\x00-\x1f\x7f<>]", "", str(s or "")).strip()
    return s[:40] or "Phone"


def _num(v, lo: float, hi: float) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or f < lo or f > hi:
        return None
    return f


def parse_report(obj: dict, now_ms: int) -> dict | None:
    """Keeps only known fields with sane values. Returns None for anything that isn't a phone report."""
    kind = obj.get("type")
    if kind not in ("loc", "nofix"):
        return None
    dev_id = str(obj.get("id") or "")
    if not _ID_RE.match(dev_id):
        return None
    sent = _num(obj.get("sent_ts"), 0, now_ms + FUTURE_SLACK_MS)
    if sent is None:
        return None
    rep = {"kind": kind, "id": dev_id, "name": _clean_name(obj.get("phone")), "sent_ts": int(sent),
           "reason": re.sub(r"[^a-z,_]", "", str(obj.get("reason") or ""))[:40],
           "battery": None, "charging": None}
    bat = _num(obj.get("battery"), 0, 100)
    rep["battery"] = int(bat) if bat is not None else None
    if isinstance(obj.get("charging"), bool):
        rep["charging"] = obj["charging"]
    if kind == "loc":
        lat, lon = _num(obj.get("lat"), -90, 90), _num(obj.get("lon"), -180, 180)
        if lat is None or lon is None:
            return None
        fix = _num(obj.get("fix_ts"), 0, now_ms + FUTURE_SLACK_MS)
        rep.update({"lat": lat, "lon": lon, "acc": _num(obj.get("acc"), 0, 100000),
                    "speed": _num(obj.get("speed"), 0, 400),
                    "provider": re.sub(r"[^a-z_]", "", str(obj.get("provider") or ""))[:16],
                    "fix_ts": int(fix) if fix is not None else int(sent)})
    else:
        rep["problem"] = re.sub(r"[^a-z_]", "", str(obj.get("problem") or ""))[:24] or "no_fix"
    return rep


PROBLEM_TEXT = {"location_off": "its location setting is off", "no_permission": "the app lost location permission",
                "no_fix": "it couldn't get a GPS fix (indoors or no sky view?)"}


# --- storage ---------------------------------------------------------------------------------
class Store:
    def __init__(self, connect: Callable[[], sqlite3.Connection]):
        self._connect = connect
        self._lock = threading.Lock()

    def _conn(self) -> sqlite3.Connection:
        c = self._connect()
        # cheap IF NOT EXISTS on every connection: the DB path can change (tests use a fresh one each)
        c.executescript(
            "CREATE TABLE IF NOT EXISTS phone_devices (id TEXT PRIMARY KEY, name TEXT, lat REAL, lon REAL, "
            "acc REAL, speed REAL, provider TEXT, fix_ts INTEGER, sent_ts INTEGER, recv_ts INTEGER, "
            "battery INTEGER, charging INTEGER, reason TEXT, problem TEXT, problem_ts INTEGER, place TEXT, "
            "quiet_told INTEGER DEFAULT 0);"
            "CREATE TABLE IF NOT EXISTS phone_fixes (id INTEGER PRIMARY KEY AUTOINCREMENT, device TEXT, "
            "lat REAL, lon REAL, acc REAL, fix_ts INTEGER);"
            "CREATE INDEX IF NOT EXISTS phone_fixes_dev ON phone_fixes(device, fix_ts);"
            "CREATE TABLE IF NOT EXISTS phone_places (k TEXT PRIMARY KEY, place TEXT, ts INTEGER);")
        return c

    def record(self, rep: dict, now_ms: int) -> str:
        """Saves a report. Returns 'new', 'updated', 'stale' (older than what we have: a replay) or 'full'."""
        with self._lock:
            c = self._conn()
            try:
                row = c.execute("SELECT sent_ts, fix_ts FROM phone_devices WHERE id=?", (rep["id"],)).fetchone()
                if row is None:
                    n = c.execute("SELECT COUNT(*) FROM phone_devices").fetchone()[0]
                    if n >= MAX_DEVICES:
                        return "full"
                    c.execute("INSERT INTO phone_devices (id, name) VALUES (?, ?)", (rep["id"], rep["name"]))
                    status = "new"
                elif row[0] is not None and rep["sent_ts"] <= row[0]:
                    return "stale"
                else:
                    status = "updated"
                c.execute("UPDATE phone_devices SET name=?, sent_ts=?, recv_ts=?, battery=?, charging=?, reason=?, "
                          "quiet_told=0 WHERE id=?",
                          (rep["name"], rep["sent_ts"], now_ms, rep["battery"],
                           None if rep["charging"] is None else int(rep["charging"]), rep["reason"], rep["id"]))
                # A phone with no fresh fix sends its last known position with its real (older) time: it counts as
                # a check-in, but the pin never moves back to a position older than the one already shown.
                newer_fix = row is None or row[1] is None or rep.get("fix_ts", 0) >= row[1]
                if rep["kind"] == "loc" and newer_fix:
                    c.execute("UPDATE phone_devices SET lat=?, lon=?, acc=?, speed=?, provider=?, fix_ts=?, "
                              "problem=NULL, place=NULL WHERE id=?",
                              (rep["lat"], rep["lon"], rep["acc"], rep["speed"], rep["provider"], rep["fix_ts"],
                               rep["id"]))
                    c.execute("INSERT INTO phone_fixes (device, lat, lon, acc, fix_ts) VALUES (?, ?, ?, ?, ?)",
                              (rep["id"], rep["lat"], rep["lon"], rep["acc"], rep["fix_ts"]))
                    c.execute("DELETE FROM phone_fixes WHERE fix_ts < ?", (now_ms - HISTORY_DAYS * 86400000,))
                    c.execute("DELETE FROM phone_fixes WHERE id NOT IN (SELECT id FROM phone_fixes "
                              "ORDER BY id DESC LIMIT ?)", (HISTORY_MAX_ROWS,))
                elif rep["kind"] == "loc":
                    c.execute("UPDATE phone_devices SET problem='no_fix', problem_ts=? WHERE id=?", (now_ms, rep["id"]))
                else:
                    c.execute("UPDATE phone_devices SET problem=?, problem_ts=? WHERE id=?",
                              (rep["problem"], now_ms, rep["id"]))
                c.commit()
                return status
            finally:
                c.close()

    def devices(self) -> list[dict]:
        with self._lock:
            c = self._conn()
            try:
                cur = c.execute("SELECT * FROM phone_devices ORDER BY name COLLATE NOCASE")
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, r)) for r in cur.fetchall()]
            finally:
                c.close()

    def trail(self, device: str, since_ms: int, limit: int = 300) -> list[list[float]]:
        with self._lock:
            c = self._conn()
            try:
                rows = c.execute("SELECT lat, lon, acc, fix_ts FROM phone_fixes WHERE device=? AND fix_ts>=? "
                                 "ORDER BY fix_ts DESC LIMIT ?", (device, since_ms, limit)).fetchall()
                return [list(r) for r in reversed(rows)]
            finally:
                c.close()

    def set_place(self, device: str, place: str) -> None:
        with self._lock:
            c = self._conn()
            try:
                c.execute("UPDATE phone_devices SET place=? WHERE id=?", (place, device))
                c.commit()
            finally:
                c.close()

    def cached_place(self, k: str, max_age_ms: int, now_ms: int) -> str | None:
        with self._lock:
            c = self._conn()
            try:
                r = c.execute("SELECT place, ts FROM phone_places WHERE k=?", (k,)).fetchone()
                return r[0] if r and now_ms - r[1] < max_age_ms else None
            finally:
                c.close()

    def cache_place(self, k: str, place: str, now_ms: int) -> None:
        with self._lock:
            c = self._conn()
            try:
                c.execute("INSERT OR REPLACE INTO phone_places (k, place, ts) VALUES (?, ?, ?)", (k, place, now_ms))
                c.execute("DELETE FROM phone_places WHERE k NOT IN (SELECT k FROM phone_places ORDER BY ts DESC "
                          "LIMIT 2000)")
                c.commit()
            finally:
                c.close()

    def mark_quiet_told(self, device: str) -> None:
        with self._lock:
            c = self._conn()
            try:
                c.execute("UPDATE phone_devices SET quiet_told=1 WHERE id=?", (device,))
                c.commit()
            finally:
                c.close()

    def forget(self, device: str) -> bool:
        with self._lock:
            c = self._conn()
            try:
                n = c.execute("DELETE FROM phone_devices WHERE id=?", (device,)).rowcount
                c.execute("DELETE FROM phone_fixes WHERE device=?", (device,))
                c.commit()
                return n > 0
            finally:
                c.close()


# --- place names (OpenStreetMap Nominatim, free, 1 request a second at most) ------------------
_geo_lock = threading.Lock()
_geo_last = [0.0]


def nominatim_reverse(lat: float, lon: float, timeout: float = 8.0) -> str | None:
    with _geo_lock:
        wait = 1.1 - (time.time() - _geo_last[0])
        if wait > 0:
            time.sleep(wait)
        _geo_last[0] = time.time()
    q = urllib.parse.urlencode({"lat": f"{lat:.5f}", "lon": f"{lon:.5f}", "format": "jsonv2", "zoom": 17,
                                "addressdetails": 1})
    req = urllib.request.Request("https://nominatim.openstreetmap.org/reverse?" + q,
                                 headers={"User-Agent": "Jarvis-phone-locator/1.0 (personal use)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read(200000))
    return short_place(data)


def short_place(data: dict) -> str | None:
    """'Allen Avenue, Ikeja' from a Nominatim answer: street (or landmark) + area + town, no postcode/country."""
    if not isinstance(data, dict):
        return None
    a = data.get("address") or {}
    first = data.get("name") or a.get("road") or a.get("pedestrian") or a.get("amenity")
    area = a.get("suburb") or a.get("neighbourhood") or a.get("quarter") or a.get("village")
    town = a.get("city") or a.get("town") or a.get("county") or a.get("state")
    parts = []
    for p in (first, area, town):
        p = re.sub(r"[\x00-\x1f<>]", "", str(p or "")).strip()
        if p and p not in parts:
            parts.append(p[:60])
    return ", ".join(parts) or None


def place_key(lat: float, lon: float) -> str:
    return f"{lat:.4f},{lon:.4f}"  # ~11 m: close enough to reuse a name


# --- describing --------------------------------------------------------------------------------
def ago(ms: int | None, now_ms: int) -> str:
    if not ms:
        return "never"
    s = max(0, (now_ms - ms) / 1000)
    if s < 90:
        return "just now"
    if s < 3600:
        return f"{round(s / 60)} minutes ago"
    if s < 86400:
        h = round(s / 3600)
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = round(s / 86400)
    return f"{d} day{'s' if d != 1 else ''} ago"


def checkin_text(dev: dict, now_ms: int) -> str:
    """The dashboard card's second line: when the phone last talked to Jarvis, and what it said if it had no fix.
    Kept apart from the position's age: a phone indoors can check in every 10 minutes with no new position."""
    rec = dev.get("recv_ts")
    if not rec:
        return "no check-in yet"
    text = f"checked in {ago(rec, now_ms)}"
    if dev.get("problem") and (dev.get("problem_ts") or 0) >= (dev.get("fix_ts") or 0):
        text += f", but {PROBLEM_TEXT.get(dev['problem'], 'it had no GPS fix')}"
    return text


def describe(dev: dict, now_ms: int) -> str:
    name = dev.get("name") or "Phone"
    if dev.get("lat") is None:
        line = f"{name}: no position yet"
    else:
        where = dev.get("place") or f"{dev['lat']:.5f}, {dev['lon']:.5f}"
        acc = dev.get("acc")
        within = f" (within about {int(round(acc))} m)" if acc else ""
        line = f"{name}: near {where}{within}, {ago(dev.get('fix_ts'), now_ms)}"
    if dev.get("problem") and (dev.get("problem_ts") or 0) >= (dev.get("fix_ts") or 0):
        line += f"; last check-in {ago(dev.get('problem_ts'), now_ms)} said {PROBLEM_TEXT.get(dev['problem'], 'no GPS fix')}"
    elif dev.get("recv_ts") and dev.get("fix_ts") and dev["recv_ts"] - dev["fix_ts"] > 30 * 60000:
        line += f"; last check-in {ago(dev['recv_ts'], now_ms)}"
    if dev.get("battery") is not None:
        line += f", battery {dev['battery']}%" + (" and charging" if dev.get("charging") else "")
    return line + "."


def match_device(devices: list[dict], words: str) -> list[dict]:
    """Devices whose name shares a word with the request ('my samsung' -> Samsung). Empty = no name given."""
    w = set(re.findall(r"[a-z0-9]{3,}", (words or "").lower())) - {"phone", "phones", "where", "show", "the", "and",
                                                                      "all", "both", "map", "visually", "with"}
    if not w:
        return []
    return [d for d in devices if w & set(re.findall(r"[a-z0-9]{3,}", (d.get("name") or "").lower()))]


def map_url(lat: float, lon: float) -> str:
    return f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=17/{lat:.6f}/{lon:.6f}"


# --- the relay connection ----------------------------------------------------------------------
class Locator:
    """Listens on the topic (a daemon thread) and publishes asks. `config()` returns (server, topic, key) or None,
    re-read on each reconnect so pairing from the dashboard takes effect without a restart."""

    def __init__(self, store: Store, config: Callable[[], tuple | None],
                 on_report: Callable[[dict, str], None] | None = None,
                 opener: Callable = urllib.request.urlopen, now_ms: Callable[[], int] | None = None):
        self.store = store
        self.config = config
        self.on_report = on_report
        self._open = opener
        self._now = now_ms or (lambda: int(time.time() * 1000))
        self._since = "10m"
        self._changed = threading.Condition()
        self._thread: threading.Thread | None = None
        self.connected = False
        self.last_error = ""

    # incoming ----------------------------------------------------------------------------------
    def handle_text(self, text: str) -> str | None:
        cfg = self.config()
        if not cfg:
            return None
        obj = open_sealed(cfg[2], cfg[1], text or "")
        if obj is None:
            return None  # not ours: ignore quietly (a stranger posting to the topic)
        now = self._now()
        rep = parse_report(obj, now)
        if rep is None:
            return None  # our own "ask", or a report with bad fields
        status = self.store.record(rep, now)
        if status in ("new", "updated"):
            with self._changed:
                self._changed.notify_all()
            if self.on_report:
                try:
                    self.on_report(rep, status)
                except Exception as e:
                    log.debug("phone report hook failed: %s", e)
        return status

    def _listen_once(self) -> None:
        cfg = self.config()
        if not cfg:
            raise RuntimeError("not paired")
        server, topic, _key = cfg
        url = f"{server}/{topic}/json?since={urllib.parse.quote(self._since)}"
        with self._open(urllib.request.Request(url), timeout=100) as resp:
            self.connected = True
            self.last_error = ""
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("event") != "message":
                    continue
                if ev.get("id"):
                    self._since = str(ev["id"])
                self.handle_text(str(ev.get("message") or ""))
                if self.config() != cfg:
                    return  # re-paired: reconnect on the new topic

    def _loop(self) -> None:
        backoff = 5
        while True:
            if not self.config():
                self.connected = False
                time.sleep(15)
                continue
            try:
                self._listen_once()
                backoff = 5
            except Exception as e:
                self.last_error = type(e).__name__
                log.debug("phone locator relay: %s (reconnecting)", e)
            self.connected = False
            time.sleep(backoff)
            backoff = min(backoff * 2, 120)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="phone-locator", daemon=True)
        self._thread.start()

    # outgoing ----------------------------------------------------------------------------------
    def ask(self, device_id: str | None = None) -> bool:
        cfg = self.config()
        if not cfg:
            return False
        server, topic, key = cfg
        msg = {"v": 1, "type": "ask", "ts": self._now(), "nonce": secrets.token_hex(8)}
        if device_id:
            msg["phone"] = device_id
        body = seal(key, topic, msg).encode()
        req = urllib.request.Request(f"{server}/{topic}", data=body, method="POST",
                                     headers={"Content-Type": "text/plain"})
        try:
            with self._open(req, timeout=15) as resp:
                resp.read()
            return True
        except Exception as e:
            self.last_error = type(e).__name__
            log.info("phone locator: ask not sent (%s)", type(e).__name__)
            return False

    def wait_for(self, device_ids: list[str], after_ms: int, timeout_s: float) -> set[str]:
        """Waits until every listed phone reported after `after_ms` (or the time is up). Returns the ones that did."""
        deadline = time.time() + timeout_s
        while True:
            fresh = {d["id"] for d in self.store.devices() if (d.get("recv_ts") or 0) >= after_ms}
            if set(device_ids) <= fresh or time.time() >= deadline:
                return fresh & set(device_ids)
            with self._changed:
                self._changed.wait(min(1.0, max(0.05, deadline - time.time())))


def env_config(env=os.environ) -> tuple | None:
    server = (env.get(ENV_SERVER) or DEFAULT_SERVER).strip().rstrip("/")
    topic = (env.get(ENV_TOPIC) or "").strip()
    key = (env.get(ENV_KEY) or "").strip()
    return (server, topic, key) if valid_config(server, topic, key) else None
