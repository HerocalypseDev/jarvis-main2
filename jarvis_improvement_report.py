"""Weekly "how could Jarvis work better for you" report (2026-09-27, feature batch D5). Read-only and
deterministic (plain SQL over tables Jarvis already keeps, no model call). It only suggests: nothing
here edits Jarvis's code, settings, macros or agents.

Looks at the last `days` (7) of: tool failures (action_audit), commands typed/spoken the same way 3+
times (dashboard_sessions: macro candidates), announcement kinds that keep getting cut off
(notification_stats), background agents that are failing, and slow voice turns (in-memory latency).
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter
from datetime import datetime, timedelta

_FAIL_RE = re.compile(r"^(tool failed|couldn't|could not|failed|error|unrecognized tool)", re.I)


def _exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def build(connect, lock, days: int = 7, latency_rows: list[dict] | None = None) -> dict:
    since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    out: dict = {"days": days, "failing_tools": [], "repeated_commands": [], "ignored_announcements": [],
                 "failing_agents": [], "slow_turns": 0}
    with lock:
        conn = connect()
        try:
            if _exists(conn, "action_audit"):
                fails = Counter()
                totals = Counter()
                for tool, result in conn.execute("SELECT tool_name, result FROM action_audit WHERE timestamp >= ?", (since,)):
                    totals[tool] += 1
                    if _FAIL_RE.match((result or "").strip()):
                        fails[tool] += 1
                out["failing_tools"] = [{"tool": t, "failed": n, "of": totals[t]} for t, n in fails.most_common(5) if n >= 2]
            if _exists(conn, "dashboard_sessions"):
                cols = {r[1] for r in conn.execute("PRAGMA table_info(dashboard_sessions)")}
                tcol = "started_at" if "started_at" in cols else "created_at" if "created_at" in cols else None
                if tcol and "transcript" in cols:
                    norm = Counter()
                    for (t,) in conn.execute(f"SELECT transcript FROM dashboard_sessions WHERE {tcol} >= ?", (since,)):
                        key = re.sub(r"[^\w\s']", "", (t or "").lower()).strip()
                        if 2 <= len(key.split()) <= 10:
                            norm[key] += 1
                    out["repeated_commands"] = [{"command": c, "times": n} for c, n in norm.most_common(5) if n >= 3]
            if _exists(conn, "notification_stats"):
                out["ignored_announcements"] = [
                    {"kind": k, "dismissed": d, "acted": a}
                    for k, d, a in conn.execute("SELECT kind, dismissed, acted FROM notification_stats "
                                                "WHERE dismissed >= 3 AND dismissed > acted ORDER BY dismissed DESC")]
            if _exists(conn, "agents"):
                out["failing_agents"] = [r[0] for r in conn.execute("SELECT name FROM agents WHERE last_ok = 0 AND enabled = 1")]
        finally:
            conn.close()
    out["slow_turns"] = sum(1 for r in (latency_rows or []) if (r.get("e2e_ms") or 0) > 6000)
    return out


def suggestions(r: dict) -> list[str]:
    s = []
    for f in r["failing_tools"]:
        s.append(f"{f['tool']} failed {f['failed']} of {f['of']} times this week; check its setup (self check can help).")
    for c in r["repeated_commands"]:
        s.append(f"You said \"{c['command']}\" {c['times']} times; a voice macro would run it instantly with no AI call.")
    for a in r["ignored_announcements"]:
        s.append(f"You cut off {a['kind']} announcements {a['dismissed']} times; they'll move to the digest, or turn them off.")
    for name in r["failing_agents"]:
        s.append(f"The background agent {name} is failing; open the Toolbox to see why.")
    if r["slow_turns"]:
        s.append(f"{r['slow_turns']} recent voice replies took over 6 seconds; the Voice tab shows where the time went.")
    return s


def format_report(r: dict) -> str:
    items = suggestions(r)
    if not items:
        return f"Nothing to improve from the last {r['days']} days: no repeated failures, repeated commands or ignored announcements."
    return f"Suggestions from the last {r['days']} days (nothing was changed):\n" + "\n".join(f"- {x}" for x in items)
