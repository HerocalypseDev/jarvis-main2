""""What did I miss?" inbox (2026-10-03, owner: "it should not say out autonomous messages or reminders unless it is
something very important").

Jarvis now speaks on its own only for the owner's own reminders and truly urgent things (a security alert, a meeting in
a few minutes, a job they asked for finishing or failing). Everything else that used to be read out unprompted (a
scheduled skill's report, health tips, network joins, autonomy notes, the doctor's findings...) lands here instead: it
shows on the dashboard Home card and is read out when the owner asks "what did I miss?".

Pure module (never imports jarvis.py): jarvis.py hands it the DB connect function and lock.
"""
from __future__ import annotations

import re
import time
from datetime import datetime

from jarvis_untrusted import mask_secrets

MAX_ROWS = 300
KEEP_DAYS = 7
SPEAK_MAX_ITEMS = 6

_KIND_RULES = (
    ("network", re.compile(r"\b(?:network|joined|left the network|device)\b", re.I)),
    ("health", re.compile(r"\b(?:cpu|disk|battery|memory usage|sign-in|signed in|heads up:)\b", re.I)),
    ("mail", re.compile(r"\b(?:emails?|e-mails?|inbox|gmail|mail from)\b", re.I)),
    ("calendar", re.compile(r"\b(?:meeting|calendar|event)\b", re.I)),
    ("task", re.compile(r"\b(?:job|task|plan|done:|finished|failed)\b", re.I)),
)


def kind_of(text: str) -> str:
    for kind, rx in _KIND_RULES:
        if rx.search(text or ""):
            return kind
    return "update"


def _ensure(conn) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS missed_items (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, "
                 "text TEXT NOT NULL, kind TEXT, source TEXT, seen_at REAL)")


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def add(connect, lock, text: str, source: str = "", now: float | None = None) -> int | None:
    """Store one message. The same unseen message again (a repeating check) only moves to the top."""
    text = mask_secrets(" ".join(str(text or "").split()))[0][:1200]  # never keep a key/token, even in a notice
    if not text:
        return None
    now = time.time() if now is None else now
    with lock:
        conn = connect()
        try:
            _ensure(conn)
            key = _norm(text)
            for rid, old in conn.execute("SELECT id, text FROM missed_items WHERE seen_at IS NULL AND ts >= ?",
                                         (now - KEEP_DAYS * 86400,)).fetchall():
                if _norm(old) == key:
                    conn.execute("UPDATE missed_items SET ts=? WHERE id=?", (now, rid))
                    conn.commit()
                    return rid
            cur = conn.execute("INSERT INTO missed_items (ts, text, kind, source) VALUES (?, ?, ?, ?)",
                               (now, text, kind_of(text), source[:40]))
            conn.execute("DELETE FROM missed_items WHERE ts < ?", (now - KEEP_DAYS * 86400,))
            conn.execute("DELETE FROM missed_items WHERE id NOT IN (SELECT id FROM missed_items ORDER BY id DESC LIMIT ?)",
                         (MAX_ROWS,))
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def unseen(connect, lock, limit: int = 50) -> list[dict]:
    """The NEWEST `limit` unread items, oldest first (audit 2026-10-04: the oldest `limit` were taken, so with more
    unread than that "what did I miss" read items from the middle and the newest ones were never reached)."""
    return _rows(connect, lock, "SELECT * FROM (SELECT id, ts, text, kind, source FROM missed_items WHERE seen_at IS NULL "
                                "ORDER BY ts DESC, id DESC LIMIT ?) ORDER BY ts, id", (limit,))


def recent(connect, lock, limit: int = 20) -> list[dict]:
    return _rows(connect, lock, "SELECT id, ts, text, kind, source, seen_at FROM missed_items ORDER BY ts DESC LIMIT ?",
                 (limit,))


def _rows(connect, lock, sql: str, args: tuple) -> list[dict]:
    with lock:
        conn = connect()
        try:
            _ensure(conn)
            cur = conn.execute(sql, args)
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
        finally:
            conn.close()


def mark_seen(connect, lock, ids: list[int] | None = None, now: float | None = None) -> int:
    """ids None = everything unseen."""
    now = time.time() if now is None else now
    with lock:
        conn = connect()
        try:
            _ensure(conn)
            if ids is None:
                cur = conn.execute("UPDATE missed_items SET seen_at=? WHERE seen_at IS NULL", (now,))
            elif ids:
                marks = ",".join("?" * len(ids))
                cur = conn.execute(f"UPDATE missed_items SET seen_at=? WHERE seen_at IS NULL AND id IN ({marks})",
                                   (now, *ids))
            else:
                return 0
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()


def _when(ts: float, now: float) -> str:
    d = datetime.fromtimestamp(ts)
    if datetime.fromtimestamp(now).date() == d.date():
        return d.strftime("%I:%M %p").lstrip("0")
    return d.strftime("%a %I:%M %p").replace(" 0", " ")


def spoken_summary(items: list[dict], now: float | None = None) -> str:
    """What "what did I miss?" says: oldest first, at most SPEAK_MAX_ITEMS, the rest counted."""
    now = time.time() if now is None else now
    if not items:
        return "Nothing new. You haven't missed anything since you last asked."
    shown = items[-SPEAK_MAX_ITEMS:]
    head = "One thing came in" if len(items) == 1 else f"{len(items)} things came in"
    lines = [f"At {_when(i['ts'], now)}: {_short(i['text'])}" for i in shown]
    more = len(items) - len(shown)
    tail = f" Ask again for the {more} older one{'s' if more != 1 else ''}." if more > 0 else ""
    return f"{head} while you weren't asking. " + " ".join(lines) + tail


def _short(text: str, limit: int = 220) -> str:
    t = " ".join(str(text or "").split())
    if len(t) <= limit:
        return t if t.endswith((".", "!", "?")) else t + "."
    cut = t[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[: end + 1] if end > 60 else cut.rsplit(" ", 1)[0] + "...")


def spoken_ids(items: list[dict]) -> list[int]:
    """The ids spoken_summary actually reads out (the newest SPEAK_MAX_ITEMS): only those are marked read."""
    return [i["id"] for i in items[-SPEAK_MAX_ITEMS:]]


def count_line(n: int) -> str:
    """For the volatile prompt: lets "anything new?" be answered without guessing."""
    if n <= 0:
        return ""
    return (f" There {'is' if n == 1 else 'are'} {n} unread item{'s' if n != 1 else ''} in the user's 'what did I miss' "
            "list (things Jarvis noticed but didn't say out loud); mention it only if the user asks what's new.")
