"""Telling the owner what they should know (2026-10-18, owner: "my Windows Update and MCP tool were failing in the
caretaker but it didn't send me a Telegram message, a phone call, or tell me while I was talking to it").

Before this, every proactive line went through the quiet gate: anything not urgent waited in the "what did I miss"
inbox, and phone pushes were off unless JARVIS_PHONE_PROACTIVE_NOTIFICATIONS was on. So a caretaker issue Jarvis gave
up on, a tool server that stayed down, or an email warning about a bad update was only ever written to the inbox.

One rule now decides the channel by how much it matters:
- urgent    -> said out loud now, a Telegram message, and a phone call when the owner is away from the PC;
- important -> a Telegram message right away, and said at the start of the next thing the owner says to Jarvis;
- minor     -> the "what did I miss" inbox, and mentioned at the start of the next thing the owner says.

The same problem (same key) is told once per COOLDOWN_H unless it gets worse. This module is pure: jarvis.py hands it
the database and does the sending; it never imports jarvis.py.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta

from jarvis_untrusted import mask_secrets, neutralize_injection

LEVELS = ("minor", "important", "urgent")
COOLDOWN_H = 24
MAX_TEXT = 300
HEADS_UP_MAX = 3
HEADS_UP_MAX_AGE_H = 24


def enabled() -> bool:
    return _on("JARVIS_ALERTS", True)


def telegram_on() -> bool:
    return _on("JARVIS_ALERT_TELEGRAM", True)


def heads_up_on() -> bool:
    return _on("JARVIS_ALERT_HEADS_UP", True)


def _on(key: str, default: bool) -> bool:
    v = (os.environ.get(key) or "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")


def rank(level: str) -> int:
    return LEVELS.index(level) if level in LEVELS else 0


def norm_level(level) -> str:
    level = str(level or "").strip().lower()
    return level if level in LEVELS else "minor"


def clean(text: str) -> str:
    """One line, no control characters, secrets masked, injection-like text defused (alerts can carry email text)."""
    t = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text or ""))
    t = re.sub(r"\s+", " ", t).strip()
    t = neutralize_injection(t)[0]
    t = mask_secrets(t)[0]
    return t[:MAX_TEXT].rstrip()


def channels(level: str) -> dict:
    """Which ways a message of this level goes out (before the owner's switches)."""
    level = norm_level(level)
    return {"speak": level == "urgent", "telegram": level in ("urgent", "important"), "call": level == "urgent",
            "inbox": level != "urgent", "heads_up": level != "urgent"}


# --- caretaker issues ---------------------------------------------------------------------------------------------

# Problems that stop something the owner relies on: these reach the phone, not only the inbox.
_IMPORTANT_CATEGORIES = {"update", "disk_health", "self_mcp", "self_skill", "self_job", "self_agent", "network"}


def caretaker_level(issue: dict, gave_up: bool = False) -> str:
    sev = str(issue.get("severity") or "")
    if sev == "critical":
        return "urgent"
    if gave_up or str(issue.get("category") or "") in _IMPORTANT_CATEGORIES:
        return "important"
    return "minor"


def caretaker_text(issue: dict, gave_up_reason: str = "") -> str:
    title = str(issue.get("title") or "A problem on your PC").strip().rstrip(".")
    ev = issue.get("evidence") or {}
    if gave_up_reason:
        return f"I couldn't fix this on my own: {title}. {gave_up_reason}".strip()
    advice = str(ev.get("advice") or "").strip()
    return f"{title}." + (f" {advice}" if advice else " I'm working on it and will tell you if I can't fix it.")


# --- the owner_alerts table: once per problem -----------------------------------------------------------------------

def ensure(conn) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS owner_alerts (key TEXT PRIMARY KEY, level TEXT NOT NULL, text TEXT, "
                 "source TEXT, first_at TEXT NOT NULL, last_at TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 1)")


class Store:
    def __init__(self, connect, lock):
        self.connect, self.lock = connect, lock

    def claim(self, key: str, level: str, text: str, source: str = "", now: datetime | None = None,
              cooldown_h: float = COOLDOWN_H) -> bool:
        """True = tell the owner now (new, worse than last time, or the cooldown passed); records it either way."""
        now = now or datetime.now()
        stamp = now.isoformat(timespec="seconds")
        with self.lock:
            conn = self.connect()
            try:
                ensure(conn)
                row = conn.execute("SELECT level, last_at FROM owner_alerts WHERE key=?", (key,)).fetchone()
                if row is not None:
                    try:
                        recent = now - datetime.fromisoformat(row[1]) < timedelta(hours=cooldown_h)
                    except (TypeError, ValueError):
                        recent = False
                    if recent and rank(level) <= rank(row[0]):
                        return False
                    conn.execute("UPDATE owner_alerts SET level=?, text=?, source=?, last_at=?, count=count+1 "
                                 "WHERE key=?", (level, text, source, stamp, key))
                else:
                    conn.execute("INSERT INTO owner_alerts (key, level, text, source, first_at, last_at) "
                                 "VALUES (?,?,?,?,?,?)", (key, level, text, source, stamp, stamp))
                conn.commit()
                return True
            finally:
                conn.close()

    def forget(self, key: str) -> None:
        """The problem went away: a later recurrence is news again."""
        with self.lock:
            conn = self.connect()
            try:
                ensure(conn)
                conn.execute("DELETE FROM owner_alerts WHERE key=?", (key,))
                conn.commit()
            finally:
                conn.close()

    def recent(self, limit: int = 20) -> list[dict]:
        with self.lock:
            conn = self.connect()
            try:
                ensure(conn)
                rows = conn.execute("SELECT key, level, text, source, first_at, last_at, count FROM owner_alerts "
                                    "ORDER BY last_at DESC LIMIT ?", (limit,)).fetchall()
            finally:
                conn.close()
        return [dict(zip(("key", "level", "text", "source", "first_at", "last_at", "count"), r)) for r in rows]


# --- heads-up: said at the start of the next thing the owner says -----------------------------------------------------

def fresh_heads_up(items: list, now: datetime | None = None) -> list[dict]:
    """Drop old and repeated items; newest last."""
    now = now or datetime.now()
    out, seen = [], set()
    for i in items or []:
        if not isinstance(i, dict) or not str(i.get("text") or "").strip():
            continue
        try:
            if now - datetime.fromisoformat(str(i.get("at"))) > timedelta(hours=HEADS_UP_MAX_AGE_H):
                continue
        except (TypeError, ValueError):
            continue
        k = re.sub(r"[^a-z0-9]+", " ", str(i["text"]).lower()).strip()
        if k in seen:
            continue
        seen.add(k)
        out.append(i)
    return out


def heads_up_line(items: list) -> str:
    """One spoken line for what came in since the owner last talked to Jarvis (most important first, at most 3)."""
    items = sorted(items or [], key=lambda i: -rank(norm_level(i.get("level"))))
    if not items:
        return ""
    texts = [str(i["text"]).strip().rstrip(".") for i in items[:HEADS_UP_MAX]]
    more = len(items) - len(texts)
    tail = f" And {more} more in what you missed." if more > 0 else ""
    if len(texts) == 1:
        return f"Before I answer, something you should know: {texts[0]}.{tail}"
    return f"Before I answer, {len(texts)} things you should know. " + " ".join(
        f"{n}: {t}." for n, t in enumerate(texts, 1)) + tail
