"""Memory consolidation for the autonomy layer: HOT -> WARM -> COLD and derived rules.

  HOT   = recent turns (memory_turns) and today's facts, untouched.
  WARM  = per-session conversation_summaries written by jarvis_autonomy.
  COLD  = weekly digests: once summaries are older than COLD_AFTER_DAYS, all the summaries of one
          ISO week are merged into a single digest by one model call and the originals are deleted.
  Rules = what the autonomy policy engine has *learned* (e.g. "reminders from email are always
          approved") written into memory_facts under keys starting "rule:", so the normal fact
          recall and the system prompt see them. Deterministic, no model call.

Self-contained (own state table, own _db_path/_db_lock/_connect, no import of jarvis.py). Runs at
most once per RUN_EVERY_H hours, called from jarvis_autonomy's tick through the `consolidate`
callback, and only while autonomy is enabled.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

log = logging.getLogger("jarvis.memory_consolidation")

COLD_AFTER_DAYS = 30
RUN_EVERY_H = 24
MIN_GROUP = 2

_db_lock = threading.Lock()


def _db_path() -> Path:
    override = (os.environ.get("JARVIS_MEMORY_DB_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent / "jarvis_memory.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS consolidation_state (key TEXT PRIMARY KEY, value TEXT)")
    return conn


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _state(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM consolidation_state WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def abstract_rules(conn: sqlite3.Connection, now: datetime) -> int:
    """Learned policies -> memory_facts 'rule:' rows (superseding any earlier text for the same key)."""
    try:
        # only what was really learned: 3 approvals in a row / 2 dismissals in a row (a fresh learned row starts
        # as auto_act after ONE approval and must not be written into memory as "repeatedly approved")
        policies = conn.execute("SELECT category, verdict, approved_streak, dismissed_streak FROM autonomy_policies "
                                "WHERE source='learned' AND ((verdict='auto_act' AND approved_streak>=3) "
                                "OR (verdict='ignore' AND dismissed_streak>=2))").fetchall()
        conn.execute("SELECT 1 FROM memory_facts LIMIT 1")
    except sqlite3.OperationalError:
        return 0
    written = 0
    for p in policies:
        key = f"rule:autonomy:{p['category']}"
        text = (f"The user has repeatedly approved '{p['category']}' suggestions, so Jarvis handles them itself."
                if p["verdict"] == "auto_act" else
                f"The user has repeatedly dismissed '{p['category']}' suggestions, so Jarvis no longer offers them.")
        current = conn.execute("SELECT id, content FROM memory_facts WHERE key=? AND superseded_at IS NULL",
                               (key,)).fetchone()
        if current and current["content"] == text:
            continue
        cur = conn.execute("INSERT INTO memory_facts (category, key, content, created_at) VALUES ('rule', ?, ?, ?)",
                           (key, text, _iso(now)))
        if current:
            conn.execute("UPDATE memory_facts SET superseded_at=?, superseded_by=? WHERE id=?",
                         (_iso(now), cur.lastrowid, current["id"]))
        written += 1
    # a rule that no longer qualifies (reverted, expired, deleted) must not linger in memory as if still true
    live = {f"rule:autonomy:{p['category']}" for p in policies}
    for row in conn.execute("SELECT id, key FROM memory_facts WHERE key LIKE 'rule:autonomy:%' "
                            "AND superseded_at IS NULL").fetchall():
        if row["key"] not in live:
            conn.execute("UPDATE memory_facts SET superseded_at=? WHERE id=?", (_iso(now), row["id"]))
            written += 1
    return written


def compress_old_summaries(conn: sqlite3.Connection, now: datetime, claude: Callable | None) -> int:
    """WARM -> COLD. Returns how many weekly digests were produced."""
    if claude is None:
        return 0
    try:
        rows = conn.execute("SELECT id, summary_text, end_time_iso, created_at, tags_json FROM conversation_summaries "
                            "WHERE created_at<? ORDER BY id", (_iso(now - timedelta(days=COLD_AFTER_DAYS)),)).fetchall()
    except sqlite3.OperationalError:
        return 0
    weeks: dict[str, list[sqlite3.Row]] = {}
    for r in rows:
        try:
            tags = json.loads(r["tags_json"] or "{}")
        except json.JSONDecodeError:
            tags = {}
        if tags.get("compressed"):
            continue
        try:
            d = datetime.fromisoformat(r["end_time_iso"] or r["created_at"])
        except ValueError:
            continue
        iso = d.isocalendar()
        weeks.setdefault(f"{iso[0]}-W{iso[1]:02d}", []).append(r)
    made = 0
    for week, group in weeks.items():
        if len(group) < MIN_GROUP:
            continue
        joined = "\n".join(f"- {g['summary_text']}" for g in group)[:6000]
        text = claude("You compress notes. Output plain text only.",
                      f"Merge these session summaries from {week} into ONE summary of at most 4 sentences, "
                      f"keeping people, decisions and deadlines:\n{joined}", 400)
        if not text or not text.strip():
            continue
        conn.execute("INSERT INTO conversation_summaries (session_id, summary_text, start_time_iso, end_time_iso, "
                     "tags_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                     (f"digest-{week}", text.strip()[:1500], group[0]["created_at"], group[-1]["end_time_iso"],
                      json.dumps({"compressed": True, "week": week, "sources": len(group)}), _iso(now)))
        conn.execute(f"DELETE FROM conversation_summaries WHERE id IN ({','.join('?' * len(group))})",
                     tuple(g["id"] for g in group))
        conn.commit()
        made += 1
    return made


def consolidate(now: datetime | None = None, claude: Callable | None = None, force: bool = False) -> dict:
    """Runs both passes if RUN_EVERY_H hours have passed (or force). Returns what it did."""
    now = now or datetime.now()
    with _db_lock:
        conn = _connect()
        try:
            last = _state(conn, "last_run")
            if not force and last and now - datetime.fromisoformat(last) < timedelta(hours=RUN_EVERY_H):
                return {"skipped": "ran recently"}
            out = {"rules": abstract_rules(conn, now)}
            conn.commit()  # release SQLite's write lock before any (slow) model call below
            out["digests"] = compress_old_summaries(conn, now, claude)
            conn.execute("INSERT INTO consolidation_state (key, value) VALUES ('last_run', ?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (_iso(now),))
            conn.commit()
            return out
        finally:
            conn.close()
