"""Background agents (2026-09-27, feature batch C1): small standing jobs ("every morning at 8 check
X", "when mail from the landlord arrives, remind me", "when a PDF lands in Downloads, tell me") that
run fixed tool steps. No process per agent: the 60 s scheduler tick calls `due()` and jarvis.py runs
each due agent's steps on a worker thread, through `_execute_tool` (audited, catastrophic gate intact).

`agents` table: name, enabled, trigger_type + trigger_config, steps [{tool, input}], max_runs_per_day,
run bookkeeping. Triggers:
  interval    {"every_min": 30}
  daily       {"at": "08:00", "days": "mon,tue,wed,thu,fri"}  (days optional)
  mail_match  {"query": "from:landlord@example.com"}  Gmail search, checked every MAIL_CHECK_MIN;
              each new message fires once. {subject} / {sender} in step inputs are filled in
              (sanitised third-party text).
  file_event  {"ext": "pdf", "name_contains": "invoice"}  fed by the file watcher.
  manual      runs only when asked.
Budget: max_runs_per_day (default 24). A failing run notifies once until a run succeeds again.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Callable

TRIGGERS = ("interval", "daily", "mail_match", "file_event", "manual")
MAIL_CHECK_MIN = 10
MAX_STEPS = 10
_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_PLACEHOLDER_RE = re.compile(r"\{(subject|sender|path|snippet)\}")
# The only tools whose inputs may carry trigger text written by someone else (a mail subject, a
# downloaded file's name). Anything that runs code, types, sends, fetches or writes is excluded, so a
# crafted subject can never become a shell command, a typed keystroke or an outgoing message.
FILL_TOOLS = {"create_reminder", "quick_search", "find_files", "clipboard_history", "memory_search",
              "semantic_recall", "recall_facts", "weather"}


def ensure(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS agents (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, "
                 "enabled INTEGER NOT NULL DEFAULT 1, trigger_type TEXT NOT NULL, trigger_config TEXT NOT NULL, "
                 "steps TEXT NOT NULL, max_runs_per_day INTEGER NOT NULL DEFAULT 24, created_at TEXT NOT NULL, "
                 "last_run TEXT, last_check TEXT, runs_day TEXT, runs_today INTEGER NOT NULL DEFAULT 0, "
                 "last_result TEXT, last_ok INTEGER, fail_notified INTEGER NOT NULL DEFAULT 0, "
                 "seen TEXT NOT NULL DEFAULT '[]', pending TEXT NOT NULL DEFAULT '[]')")


class Store:
    def __init__(self, connect, lock):
        self.connect, self.lock = connect, lock

    def q(self, sql: str, args: tuple = (), write: bool = False):
        with self.lock:
            conn = self.connect()
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

    def all(self) -> list[dict]:
        out = []
        for r in self.q("SELECT * FROM agents ORDER BY name"):
            for k in ("trigger_config", "steps", "seen", "pending"):
                r[k] = json.loads(r[k] or ("{}" if k == "trigger_config" else "[]"))
            r["enabled"] = bool(r["enabled"])
            out.append(r)
        return out

    def get(self, name: str) -> dict | None:
        return next((a for a in self.all() if a["name"] == (name or "").strip()), None)

    def set(self, aid: int, **cols) -> None:
        cols = {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in cols.items()}
        self.q(f"UPDATE agents SET {', '.join(f'{k}=?' for k in cols)} WHERE id=?", (*cols.values(), aid), write=True)


def validate(trigger_type: str, config: dict, steps, known_tools: set[str], forbidden: set[str]) -> str | None:
    if trigger_type not in TRIGGERS:
        return f"trigger_type must be one of {', '.join(TRIGGERS)}."
    if not isinstance(config, dict):
        return "trigger_config must be an object."
    if trigger_type == "interval":
        try:
            if float(config.get("every_min") or 0) < 5:
                return "An interval agent runs at most every 5 minutes (every_min >= 5)."
        except (TypeError, ValueError):
            return "every_min must be a number."
    if trigger_type == "daily":
        if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", str(config.get("at") or "")):
            return "A daily agent needs at = HH:MM."
        days = [d.strip()[:3].lower() for d in str(config.get("days") or "").split(",") if d.strip()]
        if any(d not in _DAYS for d in days):
            return "days must be like mon,tue,wed."
    if trigger_type == "mail_match" and not str(config.get("query") or "").strip():
        return "A mail agent needs a Gmail search query, e.g. from:someone@example.com."
    if not isinstance(steps, list) or not steps or len(steps) > MAX_STEPS:
        return f"An agent needs 1 to {MAX_STEPS} steps."
    for s in steps:
        tool = str((s or {}).get("tool") or "")
        if tool in forbidden or tool not in known_tools:
            return f"Step tool {tool!r} isn't an existing tool an agent may use."
        if not isinstance(s.get("input") or {}, dict):
            return f"Step {tool!r} input must be an object."
        if tool not in FILL_TOOLS and _PLACEHOLDER_RE.search(json.dumps(s.get("input") or {})):
            return (f"Step {tool!r} can't use {{subject}}/{{sender}}/{{path}}: that text comes from other people "
                    f"(mail, downloaded file names). Placeholders only work in: {', '.join(sorted(FILL_TOOLS))}.")
    return None


def create(store: Store, name: str, trigger_type: str, config: dict, steps: list, known_tools: set[str],
           forbidden: set[str], max_runs_per_day: int = 24, enabled: bool = True) -> str:
    """Saves (or updates) an agent. `enabled` only applies to a NEW agent: re-saving one keeps its on/off
    state, so a setup recipe run twice can neither switch a live agent off nor a stopped one on."""
    name = (name or "").strip()[:60]
    if not name:
        return "An agent needs a name."
    err = validate(trigger_type, config or {}, steps, known_tools, forbidden)
    if err:
        return err
    try:
        cap = max(1, min(int(max_runs_per_day or 24), 288))
    except (TypeError, ValueError):
        cap = 24
    existed = store.get(name)
    store.q("INSERT INTO agents (name, trigger_type, trigger_config, steps, max_runs_per_day, created_at, enabled) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET trigger_type=excluded.trigger_type, "
            "trigger_config=excluded.trigger_config, steps=excluded.steps, max_runs_per_day=excluded.max_runs_per_day",
            (name, trigger_type, json.dumps(config or {}),
             json.dumps([{"tool": s["tool"], "input": s.get("input") or {}} for s in steps]), cap,
             datetime.now().isoformat(timespec="seconds"), int(bool(enabled))), write=True)
    if existed:
        state = f"; an agent with that name already existed and stays {'on' if existed['enabled'] else 'off'}"
    else:
        state = "" if enabled else "; it is OFF until you switch it on"
    return f"Agent {name!r} saved ({trigger_type}, {len(steps)} step(s), at most {cap} runs a day{state})."


def _runs_today(a: dict, now: datetime) -> int:
    return a["runs_today"] if a.get("runs_day") == now.date().isoformat() else 0


def budget_left(a: dict, now: datetime) -> bool:
    return _runs_today(a, now) < a["max_runs_per_day"]


def due(a: dict, now: datetime) -> bool:
    """Time-based and queued-event triggers. mail_match is checked separately (needs a Gmail call)."""
    if not a["enabled"] or a["trigger_type"] == "manual" or not budget_left(a, now):
        return False
    cfg, last = a["trigger_config"], a.get("last_run")
    last_dt = datetime.fromisoformat(last) if last else None
    if a["trigger_type"] == "interval":
        return last_dt is None or now - last_dt >= timedelta(minutes=float(cfg.get("every_min") or 60))
    if a["trigger_type"] == "daily":
        days = [d.strip()[:3].lower() for d in str(cfg.get("days") or "").split(",") if d.strip()]
        if days and _DAYS[now.weekday()] not in days:
            return False
        h, m = (int(x) for x in cfg["at"].split(":"))
        slot = now.replace(hour=h, minute=m, second=0, microsecond=0)
        # due once the slot has passed today (within 6 h, so a PC switched on at 3 pm skips an 8 am job)
        return slot <= now < slot + timedelta(hours=6) and (last_dt is None or last_dt < slot)
    return bool(a.get("pending"))  # file_event / mail_match: events queued since the last run


def file_event_matches(a: dict, event: dict) -> bool:
    if not a["enabled"] or a["trigger_type"] != "file_event" or event.get("kind") != "new":
        return False
    cfg, path = a["trigger_config"], str(event.get("path") or "")
    exts = [e.strip().lower().lstrip(".") for e in str(cfg.get("ext") or "").replace(";", ",").split(",") if e.strip()]
    if exts and not any(path.lower().endswith("." + e) for e in exts):
        return False
    name = path.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return not cfg.get("name_contains") or str(cfg["name_contains"]).lower() in name


def fill(value, fields: dict):
    """{subject}/{sender}/{path} placeholders in string step inputs."""
    if isinstance(value, str):
        return _PLACEHOLDER_RE.sub(lambda m: str(fields.get(m.group(1), "")), value)
    if isinstance(value, dict):
        return {k: fill(v, fields) for k, v in value.items()}
    if isinstance(value, list):
        return [fill(v, fields) for v in value]
    return value


def run(store: Store, a: dict, execute: Callable[[str, dict], str], staged: Callable[[str], bool],
        notify: Callable[[str], None], now: datetime | None = None, fields: dict | None = None) -> str:
    now = now or datetime.now()
    out, ok = [], True
    for i, s in enumerate(a["steps"], 1):
        inp = dict(s.get("input") or {})
        # Third-party text only ever reaches tools that just record or look things up (audit 2026-09-27).
        result = execute(s["tool"], fill(inp, fields or {}) if s["tool"] in FILL_TOOLS else inp) or ""
        if staged(result):
            out.append(f"step {i} ({s['tool']}) is waiting for your confirmation")
            break
        if result.lower().startswith(("tool failed", "unrecognized tool", "couldn't", "could not", "error")):
            out.append(f"step {i} ({s['tool']}) failed: {result[:200]}")
            ok = False
            break
        out.append(f"{s['tool']}: {result[:200]}")
    summary = "; ".join(out)
    runs = _runs_today(a, now) + 1
    store.set(a["id"], last_run=now.isoformat(timespec="seconds"), runs_day=now.date().isoformat(), runs_today=runs,
              last_result=summary[:1000], last_ok=int(ok), fail_notified=0 if ok else 1)
    if not ok and not a.get("fail_notified"):
        notify(f"Background agent {a['name']} failed: {summary[:200]}. I'll stay quiet about it until it works again.")
    if runs >= a["max_runs_per_day"]:
        notify(f"Background agent {a['name']} reached its limit of {a['max_runs_per_day']} runs today.")
    return summary
