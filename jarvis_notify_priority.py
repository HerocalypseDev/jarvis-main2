"""Smart notification priority (2026-09-27, feature batch C6). Counts in SQLite, simple rules, no ML.

Every non-urgent proactive message has a kind (reminder, deadline, autonomy, network, file, battery,
meeting, agent, skill, other; inferred from the text when the caller doesn't say). For each kind we
count how often the user **dismissed** it (cut the speech off with push-to-talk or "stop") vs **acted**
on it (talked to Jarvis within ACT_WINDOW_S afterwards without cutting it off). A kind with at least
MIN_SAMPLES and an act rate below LOW_SCORE goes into a digest that is read out once every
JARVIS_NOTIFY_DIGEST_MIN (60) minutes as one combined message, instead of interrupting each time.
Urgent messages, reminders and anything the user asked for are never batched.
"""

from __future__ import annotations

import re
import sqlite3
import time
from datetime import datetime

MIN_SAMPLES = 5
LOW_SCORE = 0.35
ACT_WINDOW_S = 120
NEVER_BATCH = {"reminder", "battery", "meeting"}
_KIND_RULES = [
    ("network", r"^new device on your network|joined the network"),
    ("deadline", r"^heads up:"),
    ("autonomy", r"^suggestion \d+|autonomy"),
    ("battery", r"^battery|power's back"),
    ("meeting", r"meeting notes"),
    ("agent", r"^background agent"),
    ("file", r"in a watched folder|new file"),
    ("health", r"\bcpu\b|disk (space|is)|running low on"),
]
_last = {"kind": None, "at": 0.0, "resolved": True}


def infer_kind(text: str) -> str:
    low = (text or "").strip().lower()
    for kind, rx in _KIND_RULES:
        if re.search(rx, low):
            return kind
    return "other"


def ensure(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS notification_stats (kind TEXT PRIMARY KEY, delivered INTEGER NOT NULL "
                 "DEFAULT 0, acted INTEGER NOT NULL DEFAULT 0, dismissed INTEGER NOT NULL DEFAULT 0, updated_at TEXT)")


def _bump(connect, lock, kind: str, col: str) -> None:
    with lock:
        conn = connect()
        try:
            ensure(conn)
            conn.execute(f"INSERT INTO notification_stats (kind, {col}, updated_at) VALUES (?, 1, ?) ON CONFLICT(kind) "
                         f"DO UPDATE SET {col}={col}+1, updated_at=excluded.updated_at",
                         (kind, datetime.now().isoformat(timespec="seconds")))
            conn.commit()
        finally:
            conn.close()


def stats(connect, lock) -> dict[str, dict]:
    with lock:
        conn = connect()
        try:
            ensure(conn)
            return {r[0]: {"delivered": r[1], "acted": r[2], "dismissed": r[3]}
                    for r in conn.execute("SELECT kind, delivered, acted, dismissed FROM notification_stats")}
        finally:
            conn.close()


def score(s: dict | None) -> float | None:
    """Act rate with a +1/+2 prior; None until there are MIN_SAMPLES decided outcomes."""
    if not s or s["acted"] + s["dismissed"] < MIN_SAMPLES:
        return None
    return (s["acted"] + 1) / (s["acted"] + s["dismissed"] + 2)


def should_batch(connect, lock, kind: str) -> bool:
    if kind in NEVER_BATCH:
        return False
    sc = score(stats(connect, lock).get(kind))
    return sc is not None and sc < LOW_SCORE


def delivered(connect, lock, kind: str, now: float | None = None) -> None:
    """A notification of `kind` just started playing."""
    _bump(connect, lock, kind, "delivered")
    _last.update(kind=kind, at=time.monotonic() if now is None else now, resolved=False)


def on_interrupt(connect, lock, now: float | None = None) -> None:
    """Speech was cut off: counts as a dismissal if a notification was the last thing started."""
    now = time.monotonic() if now is None else now
    if not _last["resolved"] and now - _last["at"] < ACT_WINDOW_S:
        _last["resolved"] = True
        _bump(connect, lock, _last["kind"], "dismissed")


def on_user_command(connect, lock, now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    if not _last["resolved"] and now - _last["at"] < ACT_WINDOW_S:
        _last["resolved"] = True
        _bump(connect, lock, _last["kind"], "acted")


def digest_text(items: list[dict]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]["text"]
    return f"{len(items)} updates since earlier: " + " ".join(f"{i}. {x['text']}" for i, x in enumerate(items, 1))
