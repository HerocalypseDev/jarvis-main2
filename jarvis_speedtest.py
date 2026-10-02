"""Internet speed test with no browser (2026-10-02, owner request: "what's my network speed").

Measures against Cloudflare's public speed-test server (speed.cloudflare.com, the same one its web test uses):
  ping    median of a few tiny requests on one already-open connection (so TLS setup isn't counted), and jitter
  download  STREAMS parallel downloads for about DOWN_SECONDS; the first second (TCP ramp-up) is left out
  upload    STREAMS parallel uploads for about UP_SECONDS; bytes count only once the server has answered
Standard library only, no key, nothing installed. It honours an HTTPS proxy from the environment.

Data use: a fast line can move a lot of data in a few seconds, so downloads stop at JARVIS_SPEEDTEST_MAX_MB
(default 40) and uploads at half that. The spoken result says how much was used (mobile data costs money).
Results go in `speed_tests` (jarvis_memory.db) so the next test can say whether it got faster or slower.
One test at a time (a second request while one runs is told so, it would halve both results).
"""
from __future__ import annotations

import http.client
import os
import re
import sqlite3
import ssl
import statistics
import threading
import time
import urllib.parse
from datetime import datetime
from typing import Callable

HOST = "speed.cloudflare.com"
STREAMS = 4
DOWN_SECONDS = 8.0
UP_SECONDS = 6.0
UP_GRACE_SECONDS = 9.0  # an upload already under way may finish this long after UP_SECONDS (slow uplinks)
PING_COUNT = 8
SOCKET_TIMEOUT_S = 15.0
BLOCK = 64 * 1024
KEEP_ROWS = 500

_running = threading.Lock()


def max_mb() -> int:
    try:
        v = int(float((os.environ.get("JARVIS_SPEEDTEST_MAX_MB") or "40").strip()))
    except ValueError:
        v = 40
    return max(10, min(500, v))


def _proxy() -> tuple[str, int, dict] | None:
    """(host, port, tunnel headers) of an HTTPS proxy from the environment, unless HOST is excluded by no_proxy."""
    raw = (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or "").strip()
    if not raw:
        return None
    no = (os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or "").lower()
    if any(p.strip() and HOST.endswith(p.strip().lstrip("*").lstrip(".")) for p in no.split(",")):
        return None
    u = urllib.parse.urlsplit(raw if "://" in raw else "http://" + raw)
    headers = {}
    if u.username:
        import base64
        cred = f"{urllib.parse.unquote(u.username)}:{urllib.parse.unquote(u.password or '')}"
        headers["Proxy-Authorization"] = "Basic " + base64.b64encode(cred.encode()).decode()
    return u.hostname or "", u.port or 8080, headers


def _connect() -> http.client.HTTPSConnection:
    ctx = ssl.create_default_context()
    proxy = _proxy()
    if proxy:
        conn = http.client.HTTPSConnection(proxy[0], proxy[1], timeout=SOCKET_TIMEOUT_S, context=ctx)
        conn.set_tunnel(HOST, 443, headers=proxy[2])
        return conn
    return http.client.HTTPSConnection(HOST, 443, timeout=SOCKET_TIMEOUT_S, context=ctx)


def _ping(factory: Callable, count: int = PING_COUNT) -> tuple[float, float, str]:
    """(median ms, jitter ms, server location code). Raises when the server can't be reached."""
    conn = factory()
    try:
        colo = ""
        samples = []
        for i in range(count + 1):
            t = time.perf_counter()
            conn.request("GET", "/__down?bytes=0", headers={"Cache-Control": "no-store"})
            resp = conn.getresponse()
            resp.read()
            dt = (time.perf_counter() - t) * 1000.0
            if resp.status != 200:
                raise OSError(f"the speed test server answered {resp.status}")
            colo = colo or (resp.getheader("cf-meta-colo") or resp.getheader("colo") or "")
            server = 0.0
            m = re.search(r"cfSpeedWorker;dur=([\d.]+)", resp.getheader("Server-Timing") or "")
            if m:
                server = float(m.group(1))  # time the server itself spent; not the network's fault
            if i:  # the first request also opens the connection: not a ping
                samples.append(max(0.1, dt - server))
        jitter = statistics.mean(abs(a - b) for a, b in zip(samples, samples[1:])) if len(samples) > 1 else 0.0
        return statistics.median(samples), jitter, colo
    finally:
        conn.close()


class _Meter:
    """Bytes moved across all streams, with timestamps, shared by the worker threads."""

    def __init__(self, cap: int):
        self.cap = cap
        self.total = 0
        self.samples: list[tuple[float, int]] = []
        self.lock = threading.Lock()
        self.errors: list[str] = []
        self.reserved = 0

    def reserve(self, n: int) -> bool:
        """Claims n bytes of the cap before an upload starts, so parallel streams can't overshoot it together."""
        with self.lock:
            if self.reserved + n > self.cap:
                return False
            self.reserved += n
            return True

    def add(self, n: int) -> None:
        with self.lock:
            self.total += n
            self.samples.append((time.perf_counter(), self.total))

    def full(self) -> bool:
        return self.total >= self.cap


def _rate(start: float, end: float, samples: list[tuple[float, int]], skip: float) -> float:
    """Megabits per second over [start + skip, end], or the whole run when that leaves too little."""
    if not samples or end <= start:
        return 0.0
    total = samples[-1][1]
    t0, b0 = start, 0
    if end - start > skip * 2:
        for t, b in samples:
            if t >= start + skip:
                break
            t0, b0 = t, b
    span = end - t0
    return ((total - b0) * 8 / 1e6) / span if span > 0 else 0.0


def _download(factory: Callable, seconds: float, cap: int, streams: int = STREAMS) -> tuple[float, int]:
    meter = _Meter(cap)
    start = time.perf_counter()
    end_at = start + seconds

    def worker() -> None:
        size = 1_000_000
        conn = None
        try:
            conn = factory()
            while time.perf_counter() < end_at and not meter.full():
                conn.request("GET", f"/__down?bytes={size}", headers={"Cache-Control": "no-store"})
                resp = conn.getresponse()
                if resp.status != 200:
                    raise OSError(f"download answered {resp.status}")
                while True:
                    chunk = resp.read(BLOCK)
                    if not chunk:
                        break
                    meter.add(len(chunk))
                    if time.perf_counter() >= end_at or meter.full():
                        return  # stop mid-file; the connection is closed below
                size = min(size * 2, 25_000_000)
        except Exception as e:
            meter.errors.append(str(e) or type(e).__name__)
        finally:
            if conn is not None:
                conn.close()

    threads = [threading.Thread(target=worker, name=f"speedtest-down-{i}", daemon=True) for i in range(streams)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(seconds + SOCKET_TIMEOUT_S)
    end = meter.samples[-1][0] if meter.samples else time.perf_counter()
    if not meter.total and meter.errors:
        raise OSError(meter.errors[0])
    return _rate(start, end, list(meter.samples), 1.0), meter.total


def _upload(factory: Callable, seconds: float, cap: int, streams: int = STREAMS) -> tuple[float, int]:
    meter = _Meter(cap)
    payload = os.urandom(4_000_000)  # random, so nothing on the way can compress it
    start = time.perf_counter()
    stop_new = start + seconds
    hard_end = stop_new + UP_GRACE_SECONDS

    def worker() -> None:
        size = 128_000
        conn = None
        try:
            conn = factory()
            while time.perf_counter() < stop_new and meter.reserve(size):
                conn.putrequest("POST", "/__up")
                conn.putheader("Content-Type", "application/octet-stream")
                conn.putheader("Content-Length", str(size))
                conn.endheaders()
                for i in range(0, size, BLOCK):
                    if time.perf_counter() >= hard_end:
                        return  # far too slow to finish: the unfinished part is not counted
                    conn.send(payload[i:i + BLOCK] if i + BLOCK <= size else payload[i:size])
                resp = conn.getresponse()
                resp.read()
                if resp.status != 200:
                    raise OSError(f"upload answered {resp.status}")
                meter.add(size)  # counted once the server has it all
                size = min(size * 2, len(payload))
        except Exception as e:
            meter.errors.append(str(e) or type(e).__name__)
        finally:
            if conn is not None:
                conn.close()

    threads = [threading.Thread(target=worker, name=f"speedtest-up-{i}", daemon=True) for i in range(streams)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(seconds + UP_GRACE_SECONDS + SOCKET_TIMEOUT_S)
    if not meter.total:
        if meter.errors:
            raise OSError(meter.errors[0])
        return 0.0, 0
    end = meter.samples[-1][0]
    return _rate(start, end, list(meter.samples), 0.0), meter.total


def run(factory: Callable | None = None, down_s: float = DOWN_SECONDS, up_s: float = UP_SECONDS,
        cap_mb: int | None = None) -> dict:
    """One full test. Never raises: {"ok": False, "error": ...} when something failed."""
    factory = factory or _connect
    cap = (cap_mb or max_mb()) * 1_000_000
    if not _running.acquire(blocking=False):
        return {"ok": False, "error": "busy"}
    t0 = time.perf_counter()
    try:
        try:
            ping, jitter, colo = _ping(factory)
        except Exception as e:
            return {"ok": False, "error": f"couldn't reach the speed test server ({str(e)[:120] or type(e).__name__})"}
        result = {"ok": True, "ping_ms": round(ping, 1), "jitter_ms": round(jitter, 1), "server": colo}
        try:
            down, down_bytes = _download(factory, down_s, cap)
        except Exception as e:
            return {"ok": False, "error": f"the download test failed ({str(e)[:120]})", **result}
        try:
            up, up_bytes = _upload(factory, up_s, cap // 2)
        except Exception as e:
            up, up_bytes = None, 0
            result["upload_error"] = str(e)[:120]
        result.update({
            "download_mbps": round(down, 2), "upload_mbps": None if up is None else round(up, 2),
            "data_mb": round((down_bytes + up_bytes) / 1e6, 1), "seconds": round(time.perf_counter() - t0, 1),
        })
        return result
    finally:
        _running.release()


# --- units --------------------------------------------------------------------------------------------------------
# Measured in megabits per second (what internet plans are sold in); "in megabytes" (what a download window shows,
# 8 times smaller) and the others are converted for the answer. JARVIS_SPEEDTEST_UNIT sets the default.
UNITS = {  # name: (factor from Mbps, spoken name, short name)
    "megabits": (1.0, "megabits per second", "Mbps"),
    "megabytes": (1 / 8, "megabytes per second", "MB/s"),
    "kilobits": (1000.0, "kilobits per second", "kbps"),
    "kilobytes": (125.0, "kilobytes per second", "KB/s"),
    "gigabits": (0.001, "gigabits per second", "Gbps"),
}
_UNIT_WORDS = [  # checked in order: "megabytes" must win over "megabits", "mb/s" over "mb"
    ("kilobytes", r"kilo ?bytes?|\bkb/s\b|\bkbytes?\b"),
    ("kilobits", r"kilo ?bits?|\bkbps\b|\bkb\b|\bkbits?\b"),
    ("gigabits", r"giga ?bits?|\bgbps\b|\bgb\b"),
    ("megabytes", r"mega ?bytes?|\bmb/s\b|\bmbytes?\b|\bmbs\b|\bmb\b|\bbytes?\b"),
    ("megabits", r"mega ?bits?|\bmbps\b|\bmbits?\b|\bbits?\b"),
]


def parse_unit(text: str) -> str | None:
    """The unit asked for in "...in megabytes", or None when none was named."""
    low = (text or "").lower()
    m = re.search(r"\b(?:in|as|using|with)\s+(.+)$", low)
    if not m:
        return None
    for name, pattern in _UNIT_WORDS:
        if re.search(pattern, m.group(1)):
            return name
    return None


def normalize_unit(unit: str | None) -> str:
    u = (unit or os.environ.get("JARVIS_SPEEDTEST_UNIT") or "megabits").strip().lower()
    if u in UNITS:
        return u
    return parse_unit("in " + u) or "megabits"


# --- wording ------------------------------------------------------------------------------------------------------
def _num(v: float) -> str:
    if v < 1:
        return f"{v:.2f}"
    return f"{v:.1f}" if v < 10 else f"{v:.0f}"


def _in(mbps: float, unit: str) -> float:
    return float(mbps) * UNITS[unit][0]


def verdict(down: float) -> str:
    if down < 1:
        return "That's very slow: even web pages will drag."
    if down < 5:
        return "That's slow: fine for messages and voice calls, but video will struggle."
    if down < 15:
        return "That's okay: fine for HD video and video calls."
    if down < 50:
        return "That's good: fine for HD video, calls and downloads."
    if down < 200:
        return "That's fast."
    return "That's very fast."


def _when(ts: float, now: float) -> str:
    days = (datetime.fromtimestamp(now).date() - datetime.fromtimestamp(ts).date()).days
    if days <= 0:
        return "earlier today"
    if days == 1:
        return "yesterday"
    return f"{days} days ago"


def describe(r: dict, previous: dict | None = None, now: float | None = None, unit: str | None = None) -> str:
    if not r.get("ok"):
        if r.get("error") == "busy":
            return "A speed test is already running; give it a few seconds."
        return f"I couldn't test your internet speed: {r.get('error') or 'unknown error'}. Are you online?"
    unit = normalize_unit(unit)
    down = float(r.get("download_mbps") or 0)
    parts = [f"Download {_num(_in(down, unit))} {UNITS[unit][1]}"
             # the plan is sold in megabits: say that too, so the 8-times-smaller number isn't a shock
             + (f" ({_num(down)} megabits)" if unit == "megabytes" else "")]
    if r.get("upload_mbps") is not None:
        parts.append(f"upload {_num(_in(float(r['upload_mbps']), unit))}")
    parts.append(f"ping {r['ping_ms']:.0f} milliseconds")
    text = ", ".join(parts) + ". " + verdict(down)
    if r.get("upload_mbps") is None:
        text += " The upload part didn't work this time."
    if previous and previous.get("download_mbps"):
        before = float(previous["download_mbps"])
        if before > 0:
            change = (down - before) / before
            when = _when(float(previous["ts"]), now or time.time())
            if change >= 0.2:
                text += f" Faster than {when} ({_num(_in(before, unit))} down)."
            elif change <= -0.2:
                text += f" Slower than {when} ({_num(_in(before, unit))} down)."
            else:
                text += f" About the same as {when}."
    text += f" Used about {r.get('data_mb', 0):.0f} MB of data."
    return text


# --- history ------------------------------------------------------------------------------------------------------
def _ensure(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS speed_tests (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, "
                 "download_mbps REAL, upload_mbps REAL, ping_ms REAL, jitter_ms REAL, server TEXT, data_mb REAL)")


def save(connect: Callable[[], sqlite3.Connection], lock, r: dict, now: float | None = None) -> None:
    if not r.get("ok"):
        return
    with lock:
        conn = connect()
        try:
            _ensure(conn)
            conn.execute("INSERT INTO speed_tests (ts, download_mbps, upload_mbps, ping_ms, jitter_ms, server, data_mb) "
                         "VALUES (?,?,?,?,?,?,?)", (now or time.time(), r.get("download_mbps"), r.get("upload_mbps"),
                                                     r.get("ping_ms"), r.get("jitter_ms"), r.get("server") or "",
                                                     r.get("data_mb")))
            conn.execute("DELETE FROM speed_tests WHERE id NOT IN (SELECT id FROM speed_tests ORDER BY ts DESC LIMIT ?)",
                         (KEEP_ROWS,))
            conn.commit()
        finally:
            conn.close()


def history(connect: Callable[[], sqlite3.Connection], lock, n: int = 10) -> list[dict]:
    with lock:
        conn = connect()
        try:
            _ensure(conn)
            rows = conn.execute("SELECT ts, download_mbps, upload_mbps, ping_ms, jitter_ms, server, data_mb "
                                "FROM speed_tests ORDER BY ts DESC LIMIT ?", (max(1, int(n)),)).fetchall()
        finally:
            conn.close()
    keys = ("ts", "download_mbps", "upload_mbps", "ping_ms", "jitter_ms", "server", "data_mb")
    return [dict(zip(keys, r)) for r in rows]


def measure_and_describe(connect, lock, runner: Callable[[], dict] | None = None, unit: str | None = None) -> str:
    previous = (history(connect, lock, 1) or [None])[0]
    r = (runner or run)()
    try:
        save(connect, lock, r)
    except Exception:
        pass  # a locked database never hides the result
    return describe(r, previous, unit=unit)


def handle_tool(connect, lock, inp: dict, runner: Callable[[], dict] | None = None) -> str:
    action = str((inp or {}).get("action") or "run").lower()
    unit = normalize_unit((inp or {}).get("unit"))
    short = UNITS[unit][2]
    if action == "run":
        return measure_and_describe(connect, lock, runner, unit)
    rows = history(connect, lock, 10 if action == "history" else 1)
    if not rows:
        return "No speed test has been run yet. Ask me to test your internet speed."
    now = time.time()
    if action == "last":
        r = rows[0]
        up = f", upload {_num(_in(r['upload_mbps'], unit))}" if r.get("upload_mbps") is not None else ""
        return (f"Last test ({_when(r['ts'], now)}, {datetime.fromtimestamp(r['ts']).strftime('%H:%M')}): download "
                f"{_num(_in(r['download_mbps'] or 0, unit))} {UNITS[unit][1]}{up}, ping {r['ping_ms'] or 0:.0f} ms.")
    lines = [f"{datetime.fromtimestamp(r['ts']).strftime('%Y-%m-%d %H:%M')}: "
             f"down {_num(_in(r['download_mbps'] or 0, unit))}, "
             f"up {_num(_in(r['upload_mbps'], unit)) if r.get('upload_mbps') is not None else '-'} {short}, "
             f"ping {r['ping_ms'] or 0:.0f} ms" for r in rows]
    return "Recent speed tests (newest first):\n" + "\n".join(lines)
