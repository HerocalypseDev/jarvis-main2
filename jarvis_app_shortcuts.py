"""App-specific shortcuts (2026-09-27, feature batch B3): commands that only apply while a given app
is in front ("format document" in VS Code, "new incognito tab" in Opera).

`app_shortcuts` table: app (process name like "code.exe", or a window-title regex prefixed "title:"),
label (the phrase), kind + value:
  keys   value = a key combination sent to that app, e.g. "shift+alt+f"
  say    value = a phrase run as a normal Jarvis command (full pipeline, confirmation gate intact)
  macro  value = a voice macro's name
The foreground app is tracked by `ForegroundTracker` (one GetForegroundWindow call every 1.5 s; the
Jarvis dashboard tab and popups are skipped, so the "current app" is the one the user was really in).
A spoken command that matches a label for that app is handled before intent routing; the Alt+K palette
lists that app's shortcuts first. No per-app listeners, nothing always-on beyond the tracker.
"""

from __future__ import annotations

import difflib
import re
import sqlite3
import sys
import threading
import time

MATCH_RATIO = 0.88
KINDS = ("keys", "say", "macro")
_KEYS_RE = re.compile(r"^[a-z0-9+\- ,]{1,60}$", re.I)
_SKIP_TITLE_RE = re.compile(r"jarvis", re.I)


def ensure(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS app_shortcuts (id INTEGER PRIMARY KEY AUTOINCREMENT, app TEXT NOT NULL, "
                 "label TEXT NOT NULL, kind TEXT NOT NULL, value TEXT NOT NULL, UNIQUE(app, label))")


def _db(connect, lock, sql: str, args: tuple = (), write: bool = False):
    with lock:
        conn = connect()
        try:
            ensure(conn)
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql, args)
            if write:
                conn.commit()
                return cur.rowcount
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()


def _norm(t: str) -> str:
    t = re.sub(r"[^\w\s]", " ", (t or "").lower())
    return re.sub(r"^(?:jarvis\s+)?(?:please\s+)?", "", re.sub(r"\s+", " ", t).strip())


def app_matches(rule_app: str, fg: dict) -> bool:
    rule = (rule_app or "").strip()
    if rule.lower().startswith("title:"):
        try:
            return bool(re.search(rule[6:], fg.get("title") or "", re.I))
        except re.error:
            return False
    return rule.lower() == (fg.get("app") or "").lower()


def save(connect, lock, app: str, label: str, kind: str, value: str) -> str:
    app, label, kind, value = (app or "").strip(), _norm(label), (kind or "").strip().lower(), (value or "").strip()
    if not app or not label or not value:
        return "A shortcut needs an app, a phrase and what it does."
    if kind not in KINDS:
        return f"kind must be one of {', '.join(KINDS)}."
    if kind == "keys" and not _KEYS_RE.match(value):
        return "keys must look like 'ctrl+shift+p' (letters, digits, + and -)."
    if app.lower().startswith("title:"):
        try:
            re.compile(app[6:])
        except re.error:
            return "That title pattern isn't a valid regular expression."
    _db(connect, lock, "INSERT INTO app_shortcuts (app, label, kind, value) VALUES (?, ?, ?, ?) "
                       "ON CONFLICT(app, label) DO UPDATE SET kind=excluded.kind, value=excluded.value",
        (app[:120], label[:80], kind, value[:300]), write=True)
    return f"Saved: in {app}, \"{label}\" {kind} {value}."


def delete(connect, lock, sid: int) -> bool:
    return bool(_db(connect, lock, "DELETE FROM app_shortcuts WHERE id=?", (int(sid),), write=True))


def all_shortcuts(connect, lock) -> list[dict]:
    return _db(connect, lock, "SELECT * FROM app_shortcuts ORDER BY app, label")


def for_app(connect, lock, fg: dict) -> list[dict]:
    return [s for s in all_shortcuts(connect, lock) if app_matches(s["app"], fg)]


def match(connect, lock, transcript: str, fg: dict) -> dict | None:
    t = _norm(transcript)
    if not t or len(t.split()) > 8:
        return None
    best, score = None, 0.0
    for s in for_app(connect, lock, fg):
        r = 1.0 if s["label"] == t else difflib.SequenceMatcher(None, s["label"], t).ratio()
        if r > score:
            best, score = s, r
    return best if score >= MATCH_RATIO else None


class ForegroundTracker:
    """Remembers the last real app window the user was in (skips Jarvis's own windows/tabs)."""

    def __init__(self, probe, interval_s: float = 1.5):
        self.probe, self.interval_s = probe, interval_s
        self.last: dict = {"app": "", "title": "", "hwnd": 0}
        self._thread: threading.Thread | None = None

    def update(self) -> None:
        fg = self.probe() or {}
        if fg.get("title") and not _SKIP_TITLE_RE.search(fg["title"]):
            self.last = {"app": fg.get("app", ""), "title": fg.get("title", ""), "hwnd": fg.get("hwnd", 0)}

    def start(self) -> None:
        if sys.platform != "win32" or self._thread:
            return

        def loop():
            while True:
                try:
                    self.update()
                except Exception:
                    pass
                time.sleep(self.interval_s)

        self._thread = threading.Thread(target=loop, daemon=True, name="foreground-tracker")
        self._thread.start()
