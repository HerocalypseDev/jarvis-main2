"""Full-autonomy layer for Jarvis: durable commitments/projects, a clocked decision tick, a policy
engine that learns from Approve/Dismiss, proactive suggestions, and multi-day campaigns.

OFF BY DEFAULT. Turn on with the `autonomy` tool ("turn on autonomy"), the dashboard Autonomy tab,
or JARVIS_AUTONOMY_ENABLED=1. Turn off instantly with the same switches, or set
JARVIS_AUTONOMY_DISABLED=1 (hard kill: overrides everything, nothing here runs).

Self-contained like the other jarvis_*.py modules: owns its tables in jarvis_memory.db, has its own
_db_path()/_db_lock/_connect(), never imports jarvis.py. jarvis.py hands it callbacks via
configure(), calls tick(now) from the existing scheduler loop (no second thread loop; the tick's
slow work runs on a short-lived worker thread), and calls after_turn()/process_inbound_message_
for_events() from the command/mail handlers. Every decision and every executed action is written
to autonomy_decisions AND action_audit (through the audit callback).

Safety model (the catastrophic confirmation gate in jarvis.py is untouched and still applies to
anything an approved action asks the agent to do):
  * Default verdict for anything is ASK (a dashboard card + a spoken suggestion). Auto-acting needs
    an explicit auto_act policy; the only built-in one is a harmless nudge about an approaching
    deadline. Learned rules may only auto-act on reminders/notifications; email / file / background
    task actions auto-run only under a rule the user wrote themselves.
  * Content that arrived from someone else (email, Telegram, Discord) can never auto-act through a
    category-wide rule, only through a rule naming that sender or keyword, since anyone can write
    "please add this to my calendar" in an email.
  * Suppressed while the user is talking/typing, in Focus/Sleep Mode, and for a cooldown after a
    similar suggestion was dismissed. Daily budgets cap autonomous acts, suggestions and concurrent
    background tasks. A global dry-run mode logs what would have happened and does nothing.

Configuration (env; the DB `autonomy_settings` table overrides where noted):
  JARVIS_AUTONOMY_ENABLED            default 0   (DB 'enabled' overrides)
  JARVIS_AUTONOMY_DISABLED           hard off
  JARVIS_AUTONOMY_TICK_S             45 (effective floor = the scheduler's own tick, 60s)
  JARVIS_AUTONOMY_CLASSIFIER_MIN     15   minutes between model "is there a need?" checks
  JARVIS_AUTONOMY_MAX_ACTS_PER_DAY   10
  JARVIS_AUTONOMY_MAX_SUGGESTIONS_PER_DAY 8
  JARVIS_AUTONOMY_MAX_BG_TASKS       2
  JARVIS_AUTONOMY_AUTO_MIN_CONF      0.85
  JARVIS_AUTONOMY_DISMISS_COOLDOWN_MIN 180
  JARVIS_AUTONOMY_SUMMARY_IDLE_MIN   20
  JARVIS_AUTONOMY_PLANNER_HOURS      4
  JARVIS_AUTONOMY_EXTRACT_ALWAYS     0    1 = extract from every command, not just ones with cues
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("jarvis.autonomy")

# --------------------------------------------------------------------------------------- prompts
COMMITMENT_EXTRACTION_PROMPT = """You are analyzing a conversation between a user and their personal AI assistant (Jarvis).
Your job is to extract any commitments, planned events, implied tasks, or goals that imply future action.
Return a JSON array. Each element must have this exact schema:
{
"type": "task" | "event" | "promise" | "goal",
"description": "short clear description of what needs to happen",
"who_is_responsible": "user" | "other" | "system",
"deadline_iso": "ISO8601 datetime or null",
"related_project": "project name or null",
"confidence": 0.0–1.0,
"source_quote": "exact snippet from the conversation that implies this"
}
Rules:

Only include items with confidence >= 0.6.
Be conservative: if something is vague or speculative, omit it.
Prefer precise deadlines when present; otherwise leave deadline_iso null.
For events, type should usually be "event"; for to-dos, "task"; for verbal commitments, "promise"; for longer-term aims, "goal".
Conversation turns:
{conversation_turns_text}
Recent tool actions (if any):
{recent_tool_actions_text}
Output ONLY the JSON array, no extra text."""

EMAIL_EVENT_EXTRACTION_PROMPT = """You are analyzing an email (or message) to detect meetings, appointments, and tasks.
Return a JSON object with this exact schema:
{
"meetings": [
{
"title": "meeting title or null",
"start_iso": "ISO8601 or null",
"end_iso": "ISO8601 or null",
"location": "location or null",
"participants": ["name/email", ...],
"confidence": 0.0–1.0,
"source_quote": "snippet that indicates this meeting"
}
],
"tasks": [
{
"description": "task description",
"deadline_iso": "ISO8601 or null",
"confidence": 0.0–1.0,
"source_quote": "snippet that indicates this task"
}
]
}
Rules:

Only include items with confidence >= 0.6.
Be conservative: if something is vague, omit it.
Infer times/dates from relative expressions (“tomorrow at 2pm”, “next Friday”) using the current time: {current_time_iso}.
Email subject:
{email_subject}
Email body:
{email_body}
Output ONLY the JSON object, no extra text."""

SESSION_SUMMARIZATION_PROMPT = """Summarize this conversation session for long-term memory.
Produce a JSON object with this schema:
{
"summary_text": "2–5 sentence summary of what was discussed and decided",
"tags": {
"people": ["name1", "name2"],
"projects": ["project1", "project2"],
"topics": ["topic1", "topic2"],
"deadlines": ["ISO8601 or description"]
}
}
Conversation turns:
{conversation_turns_text}
Output ONLY the JSON object, no extra text."""

AUTONOMY_TICK_CLASSIFIER_PROMPT = """You are the decision engine for a fully autonomous personal AI assistant (Jarvis).
Given the current context and memory, decide if there is a high-value latent need or approaching deadline that justifies action or a suggestion.
Return a JSON object with this exact schema:
{
"has_need": true | false,
"type": "deadline" | "conflict" | "missing_info" | "opportunity" | null,
"description": "short description of the need or null",
"confidence": 0.0–1.0,
"suggested_action": "act" | "suggest" | "monitor",
"action_payload": {
"action_type": "calendar" | "reminder" | "email" | "file_op" | "background_task" | "notification" | null,
"details": { ... action-specific details ... }
}
}
Rules:

Set has_need = false if nothing clearly important stands out.
Use high confidence only for clear, time-sensitive, or high-impact items.
Prefer "monitor" when something might matter later but does not require immediate action.
Do not invent facts; use only the provided context and memory.
Current context:
{context_summary}
Recent memory (facts, summaries, projects, commitments):
{memory_context}
Output ONLY the JSON object, no extra text."""

# ------------------------------------------------------------------------------------- constants
COMMITMENT_TYPES = ("task", "event", "promise", "goal")
RESPONSIBLE = ("user", "other", "system")
ACTION_TYPES = ("calendar", "reminder", "email", "file_op", "background_task", "notification")
VERDICTS = ("auto_act", "ask_once", "always_ask", "ignore")
LEARNABLE_AUTO = ("reminder", "notification")  # the only action types a *learned* rule may auto-run
INBOUND_SOURCES = ("email", "telegram", "discord", "message")  # content written by someone else
MIN_EXTRACT_CONFIDENCE = 0.6
LEARN_APPROVALS = 3   # consecutive approvals before a learned rule may auto-act
LEARN_DISMISSALS = 2  # consecutive dismissals before a learned rule goes to "ignore"
SUGGESTION_TTL_H = 48

# Words that make a command worth an extraction call at all (a cheap gate on the extra model
# call every command would otherwise cost). Deliberately broad: a miss only costs one item.
_CUE_RE = re.compile(
    r"\b(remind|need to|have to|has to|got to|gotta|must|should|going to|gonna|plan|planning|"
    r"schedule|meeting|appointment|deadline|due|by (?:mon|tue|wed|thu|fri|sat|sun|tomorrow|tonight|"
    r"next|the end)|tomorrow|tonight|next (?:week|month|monday|tuesday|wednesday|thursday|friday|"
    r"saturday|sunday)|this (?:week|weekend|friday|monday)|later today|promise|promised|remember to|"
    r"don't forget|goal|aim to|want to|trying to|call|email|submit|finish|book|pay|renew|"
    r"birthday|exam|interview|flight|trip)\b",
    re.I,
)

# Re-entrant: _connect() may lazily run init_autonomy_tables() while a caller already holds it.
_db_lock = threading.RLock()
_initialized_paths: set[str] = set()
_cb: dict[str, Callable] = {}
_tick_lock = threading.Lock()
_tick_running = threading.Event()
_last_tick_start: datetime | None = None
_last_classifier: datetime | None = None
_last_context_hash: str = ""
_started = False


# ---------------------------------------------------------------------------------------- config
def _env_int(name: str, default: int) -> int:
    try:
        return int((os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float((os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default


def _truthy(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def _now() -> datetime:
    return datetime.now()


def _iso(dt: datetime | None = None) -> str:
    return (dt or _now()).isoformat(timespec="seconds")


def _db_path() -> Path:
    override = (os.environ.get("JARVIS_MEMORY_DB_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent / "jarvis_memory.db"


_SCHEMA = [
    "CREATE TABLE IF NOT EXISTS commitments ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL, description TEXT NOT NULL, "
    "who_is_responsible TEXT NOT NULL DEFAULT 'user', deadline_iso TEXT, related_project_id INTEGER, "
    "source_type TEXT, source_quote TEXT, confidence REAL, status TEXT NOT NULL DEFAULT 'open', "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, metadata_json TEXT)",
    # Named autonomy_projects (not `projects`): jarvis.py already owns a differently-shaped
    # `projects` table (name PRIMARY KEY), and CREATE TABLE IF NOT EXISTS would silently keep it.
    "CREATE TABLE IF NOT EXISTS autonomy_projects ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, goal TEXT, "
    "status TEXT NOT NULL DEFAULT 'active', deadline_iso TEXT, risk_level TEXT DEFAULT 'low', "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, metadata_json TEXT)",
    "CREATE TABLE IF NOT EXISTS autonomy_project_actions ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, action_type TEXT NOT NULL, "
    "description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'planned', scheduled_for_iso TEXT, "
    "completed_at TEXT, result_summary TEXT, task_ref INTEGER, created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS conversation_summaries ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, summary_text TEXT NOT NULL, "
    "start_time_iso TEXT, end_time_iso TEXT, tags_json TEXT, created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS autonomy_decisions ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, tick_time_iso TEXT NOT NULL, context_summary TEXT, "
    "detected_need_json TEXT, decision TEXT NOT NULL, action_taken TEXT, policy_reason TEXT, "
    "created_at TEXT NOT NULL)",
    # Granular rules. match_kind: category | sender | keyword. Streak columns drive the teach loop.
    "CREATE TABLE IF NOT EXISTS autonomy_policies ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, match_kind TEXT NOT NULL DEFAULT 'category', "
    "match_value TEXT NOT NULL DEFAULT '', verdict TEXT NOT NULL, min_confidence REAL, "
    "source TEXT NOT NULL DEFAULT 'user', approved_streak INTEGER NOT NULL DEFAULT 0, "
    "dismissed_streak INTEGER NOT NULL DEFAULT 0, last_feedback_at TEXT, "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS autonomy_settings (key TEXT PRIMARY KEY, value TEXT)",
    # The card the user sees: evidence + one concrete action + confidence + Approve/Dismiss.
    "CREATE TABLE IF NOT EXISTS autonomy_suggestions ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, category TEXT NOT NULL, "
    "sender TEXT, title TEXT NOT NULL, evidence TEXT, action_type TEXT, action_json TEXT, "
    "confidence REAL, status TEXT NOT NULL DEFAULT 'pending', commitment_id INTEGER, "
    "announced_at TEXT, decided_at TEXT, result TEXT)",
]


def init_autonomy_tables() -> None:
    """Idempotent. Creates every table this module owns and seeds the single built-in policy."""
    with _db_lock:
        conn = _raw_connect()
        try:
            for ddl in _SCHEMA:
                conn.execute(ddl)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_commit_status ON commitments(status, deadline_iso)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sugg_status ON autonomy_suggestions(status)")
            seeded = conn.execute(
                "SELECT 1 FROM autonomy_policies WHERE category='deadline:notification' AND source='default'"
            ).fetchone()
            if not seeded:
                now = _iso()
                conn.execute(
                    "INSERT INTO autonomy_policies (category, match_kind, match_value, verdict, min_confidence, "
                    "source, created_at, updated_at) VALUES ('deadline:notification','category','','auto_act',0,"
                    "'default',?,?)",
                    (now, now),
                )
            conn.commit()
        finally:
            conn.close()
    _initialized_paths.add(str(_db_path()))


def _raw_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def _connect() -> sqlite3.Connection:
    if str(_db_path()) not in _initialized_paths:
        init_autonomy_tables()
    return _raw_connect()


def _rows(sql: str, params: tuple = ()) -> list[dict]:
    with _db_lock:
        conn = _connect()
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        except sqlite3.OperationalError as e:  # e.g. memory_turns not created yet
            log.debug("query failed (%s): %s", sql[:40], e)
            return []
        finally:
            conn.close()


def _exec(sql: str, params: tuple = ()) -> int:
    with _db_lock:
        conn = _connect()
        try:
            cur = conn.execute(sql, params)
            conn.commit()
            return int(cur.lastrowid or 0)
        finally:
            conn.close()


def get_setting(key: str, default: str | None = None) -> str | None:
    rows = _rows("SELECT value FROM autonomy_settings WHERE key=?", (key,))
    return rows[0]["value"] if rows else default


def set_setting(key: str, value: str) -> None:
    _exec("INSERT INTO autonomy_settings (key, value) VALUES (?, ?) "
          "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


def hard_disabled() -> bool:
    return _truthy(os.environ.get("JARVIS_AUTONOMY_DISABLED"))


def enabled() -> bool:
    if hard_disabled():
        return False
    stored = get_setting("enabled")
    if stored is not None:
        return _truthy(stored)
    return _truthy(os.environ.get("JARVIS_AUTONOMY_ENABLED"))


def set_enabled(on: bool) -> str:
    if on and hard_disabled():
        return "Autonomy is hard-disabled by JARVIS_AUTONOMY_DISABLED; unset it to turn autonomy on."
    set_setting("enabled", "1" if on else "0")
    log.info("Autonomy %s.", "ENABLED" if on else "disabled")
    _publish()
    return "Autonomy is on." if on else "Autonomy is off. Nothing autonomous will run."


def dry_run() -> bool:
    return _truthy(get_setting("dry_run", os.environ.get("JARVIS_AUTONOMY_DRY_RUN", "0")))


def set_dry_run(on: bool) -> str:
    set_setting("dry_run", "1" if on else "0")
    _publish()
    return "Dry-run on: autonomy will log what it would do and change nothing." if on else "Dry-run off."


# ------------------------------------------------------------------------------------- callbacks
def configure(callbacks: dict[str, Callable]) -> None:
    """jarvis.py passes: claude(system,user,max_tokens)->str|None; notify(text,urgent=False);
    user_busy()->bool; quiet()->bool; audit(tool,input,transcript,result); create_reminder(text,
    due_iso)->str; run_agent(instruction)->str; queue_task(description,instructions,priority,
    deadline)->str; plan_queue()->str; running_background_count()->int; semantic_recall(query)->str;
    calendar_events(hours)->str; file_events()->str; workspace()->str; system_status()->str;
    publish(event dict). Every one is optional; a missing one degrades that feature only."""
    _cb.update({k: v for k, v in callbacks.items() if v is not None})


def _call(name: str, *args: Any, default: Any = None, **kwargs: Any) -> Any:
    fn = _cb.get(name)
    if fn is None:
        return default
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        log.warning("callback %s failed: %s", name, e)
        return default


def _publish() -> None:
    _call("publish", {"type": "autonomy_update", "data": {"enabled": enabled()}})


def _audit(kind: str, payload: dict, result: str) -> None:
    _call("audit", f"autonomy_{kind}", payload, "(autonomy)", result)


def _fill(template: str, **values: str) -> str:
    """Placeholder substitution by plain replace: the prompts contain literal JSON braces, so
    str.format would choke."""
    out = template
    for k, v in values.items():
        out = out.replace("{" + k + "}", v)
    return out


def _parse_json(text: str | None) -> Any:
    if not text:
        return None
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (s.find("["), s.find("{")) if i != -1]
    if not starts:
        return None
    i = min(starts)
    j = s.rfind("]" if s[i] == "[" else "}")
    if j <= i:
        return None
    try:
        return json.loads(s[i : j + 1])
    except json.JSONDecodeError:
        return None


def _ask_model(prompt: str, max_tokens: int = 900) -> Any:
    raw = _call("claude", "You output only valid JSON as instructed.", prompt, max_tokens, default=None)
    return _parse_json(raw)


def _norm_dt(value: Any) -> str | None:
    if not value or str(value).lower() in ("null", "none"):
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.isoformat(timespec="seconds")


def _norm_text(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", (s or "").lower()).strip()


# ------------------------------------------------------------------------------- projects/commitments
def get_or_create_project(name: str, goal: str = "", risk_level: str = "low") -> int | None:
    name = (name or "").strip()
    if not name or name.lower() in ("null", "none"):
        return None
    rows = _rows("SELECT id FROM autonomy_projects WHERE lower(name)=lower(?) AND status!='archived'", (name,))
    if rows:
        return rows[0]["id"]
    now = _iso()
    return _exec(
        "INSERT INTO autonomy_projects (name, goal, status, risk_level, created_at, updated_at, metadata_json) "
        "VALUES (?, ?, 'active', ?, ?, ?, '{}')", (name, goal, risk_level, now, now))


def _find_duplicate(description: str, deadline: str | None) -> int | None:
    key = _norm_text(description)
    for r in _rows("SELECT id, description, deadline_iso FROM commitments WHERE status='open'"):
        if _norm_text(r["description"]) == key and (r["deadline_iso"] or "")[:10] == (deadline or "")[:10]:
            return r["id"]
    return None


def add_commitment(c: dict, source_type: str, sender: str = "") -> int | None:
    """Validates and stores one extracted item; returns its id, or None if it was invalid, below
    the confidence floor, or a duplicate of an open commitment."""
    ctype = str(c.get("type") or "task").lower()
    desc = str(c.get("description") or "").strip()
    try:
        conf = float(c.get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    if ctype not in COMMITMENT_TYPES or not desc or conf < MIN_EXTRACT_CONFIDENCE:
        return None
    who = str(c.get("who_is_responsible") or "user").lower()
    who = who if who in RESPONSIBLE else "user"
    deadline = _norm_dt(c.get("deadline_iso"))
    if _find_duplicate(desc, deadline):
        return None
    pid = get_or_create_project(str(c.get("related_project") or ""))
    meta = {k: c[k] for k in ("end_iso", "location", "participants") if c.get(k)}
    if sender:
        meta["sender"] = sender
    now = _iso()
    return _exec(
        "INSERT INTO commitments (type, description, who_is_responsible, deadline_iso, related_project_id, "
        "source_type, source_quote, confidence, status, created_at, updated_at, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)",
        (ctype, desc[:500], who, deadline, pid, source_type, str(c.get("source_quote") or "")[:400],
         conf, now, now, json.dumps(meta)))


def _commitment(cid: int) -> dict | None:
    rows = _rows("SELECT * FROM commitments WHERE id=?", (cid,))
    return rows[0] if rows else None


def _meta(row: dict) -> dict:
    try:
        return json.loads(row.get("metadata_json") or "{}") or {}
    except json.JSONDecodeError:
        return {}


def _set_commitment_meta(cid: int, **updates: Any) -> None:
    row = _commitment(cid)
    if not row:
        return
    meta = _meta(row)
    meta.update(updates)
    _exec("UPDATE commitments SET metadata_json=?, updated_at=? WHERE id=?", (json.dumps(meta), _iso(), cid))


def set_commitment_status(cid: int, status: str) -> str:
    if status not in ("open", "completed", "cancelled", "expired"):
        return "Status must be open, completed, cancelled or expired."
    if not _commitment(cid):
        return f"No commitment #{cid}."
    _exec("UPDATE commitments SET status=?, updated_at=? WHERE id=?", (status, _iso(), cid))
    _publish()
    return f"Commitment #{cid} marked {status}."


# --------------------------------------------------------------------------------- policy engine
def list_policies() -> list[dict]:
    return _rows("SELECT * FROM autonomy_policies ORDER BY id")


def set_policy(category: str, verdict: str, match_kind: str = "category", match_value: str = "",
               min_confidence: float | None = None, source: str = "user") -> str:
    category = (category or "").strip()
    if verdict not in VERDICTS:
        return f"Verdict must be one of {', '.join(VERDICTS)}."
    if match_kind not in ("category", "sender", "keyword"):
        return "match_kind must be category, sender or keyword."
    if match_kind != "category" and not (match_value or "").strip():
        return f"A {match_kind} rule needs a match_value."
    if not category and match_kind == "category":
        return "A category rule needs a category."
    mv = (match_value or "").strip().lower() if match_kind != "category" else ""
    now = _iso()
    existing = _rows("SELECT id FROM autonomy_policies WHERE category=? AND match_kind=? AND match_value=?",
                     (category, match_kind, mv))
    if existing:
        _exec("UPDATE autonomy_policies SET verdict=?, min_confidence=?, source=?, updated_at=? WHERE id=?",
              (verdict, min_confidence, source, now, existing[0]["id"]))
    else:
        _exec("INSERT INTO autonomy_policies (category, match_kind, match_value, verdict, min_confidence, "
              "source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (category, match_kind, mv, verdict, min_confidence, source, now, now))
    _publish()
    return f"Rule saved: {match_kind} {mv or category!r} -> {verdict}."


def delete_policy(pid: int) -> str:
    _exec("DELETE FROM autonomy_policies WHERE id=?", (pid,))
    _publish()
    return f"Rule #{pid} removed."


def evaluate_policy(category: str, sender: str, text: str, confidence: float,
                    action_type: str | None, source_type: str) -> tuple[str, str]:
    """(category, sender, keywords, confidence) -> ('auto_act'|'ask'|'ignore', reason). Most
    specific match wins: sender > keyword > category; newest rule breaks ties. No match -> ask."""
    sender_l, text_l = (sender or "").lower(), (text or "").lower()
    rules = _rows("SELECT * FROM autonomy_policies WHERE category=? OR match_kind IN ('sender','keyword') "
                  "ORDER BY id DESC", (category,))
    specificity = {"sender": 3, "keyword": 2, "category": 1}
    matched: list[dict] = []
    for r in rules:
        kind, mv = r["match_kind"], r["match_value"]
        if kind == "category" and r["category"] == category:
            matched.append(r)
        elif kind == "sender" and mv and mv in sender_l and (not r["category"] or r["category"] == category):
            matched.append(r)
        elif kind == "keyword" and mv and mv in text_l and (not r["category"] or r["category"] == category):
            matched.append(r)
    if not matched:
        return "ask", "no rule; default is to ask"
    matched.sort(key=lambda r: (specificity[r["match_kind"]], r["id"]), reverse=True)
    rule = matched[0]
    verdict = rule["verdict"]
    if verdict == "ignore":
        return "ignore", f"rule #{rule['id']} ({rule['match_kind']}) says ignore"
    if verdict in ("always_ask", "ask_once"):
        return "ask", f"rule #{rule['id']} says {verdict}"
    # auto_act: apply the hard guards on top of the rule.
    floor = rule["min_confidence"] if rule["min_confidence"] is not None else _env_float(
        "JARVIS_AUTONOMY_AUTO_MIN_CONF", 0.85)
    if confidence < floor:
        return "ask", f"rule #{rule['id']} auto-acts only at confidence >= {floor:.2f} (got {confidence:.2f})"
    if source_type in INBOUND_SOURCES and rule["match_kind"] == "category":
        return "ask", "content from another person never auto-acts through a category-wide rule"
    if rule["source"] == "learned" and action_type not in LEARNABLE_AUTO:
        return "ask", f"learned rules may not auto-run {action_type} actions"
    return "auto_act", f"rule #{rule['id']} ({rule['match_kind']}, {rule['source']}) says auto_act"


def record_feedback(category: str, sender: str, action_type: str | None, approved: bool) -> None:
    """The teach loop. Approve/Dismiss updates the category's counters; enough approvals of a
    harmless action type promote it to auto_act, enough dismissals demote it to ignore. Rules the
    user wrote themselves are never changed here, only counted."""
    rows = _rows("SELECT * FROM autonomy_policies WHERE category=? AND match_kind='category'", (category,))
    now = _iso()
    if not rows:
        _exec("INSERT INTO autonomy_policies (category, match_kind, match_value, verdict, source, created_at, "
              "updated_at) VALUES (?, 'category', '', 'always_ask', 'learned', ?, ?)", (category, now, now))
        rows = _rows("SELECT * FROM autonomy_policies WHERE category=? AND match_kind='category'", (category,))
    r = rows[0]
    a = r["approved_streak"] + 1 if approved else 0
    d = 0 if approved else r["dismissed_streak"] + 1
    verdict = r["verdict"]
    if r["source"] == "learned":
        if approved and a >= LEARN_APPROVALS and action_type in LEARNABLE_AUTO:
            verdict = "auto_act"
        elif not approved and d >= LEARN_DISMISSALS:
            verdict = "ignore"
        elif not approved and verdict == "auto_act":
            verdict = "always_ask"  # one dismissal takes a learned auto rule back to asking
    elif r["verdict"] == "ask_once" and approved and action_type in LEARNABLE_AUTO:
        verdict = "auto_act"
    _exec("UPDATE autonomy_policies SET approved_streak=?, dismissed_streak=?, verdict=?, last_feedback_at=?, "
          "updated_at=? WHERE id=?", (a, d, verdict, now, now, r["id"]))
    if verdict != r["verdict"]:
        log.info("Autonomy learned: category %s %s -> %s", category, r["verdict"], verdict)


def _recently_dismissed(category: str) -> bool:
    cutoff = _iso(_now() - timedelta(minutes=_env_int("JARVIS_AUTONOMY_DISMISS_COOLDOWN_MIN", 180)))
    return bool(_rows("SELECT 1 FROM autonomy_suggestions WHERE category=? AND status='dismissed' "
                      "AND decided_at>=? LIMIT 1", (category, cutoff)))


# ------------------------------------------------------------------------------- gates & budgets
def gate_reason() -> str | None:
    """Why autonomy must stay quiet right now (None = clear): the existing Focus/Sleep gates and
    the user being mid-sentence or mid-keystroke."""
    if _call("quiet", default=False):
        return "focus or sleep mode"
    if _call("user_busy", default=False):
        return "user is active"
    return None


def _today_start() -> str:
    return _now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")


def budgets() -> dict:
    day = _today_start()
    acts = _rows("SELECT COUNT(*) n FROM autonomy_decisions WHERE decision='act' AND created_at>=?", (day,))
    sugg = _rows("SELECT COUNT(*) n FROM autonomy_suggestions WHERE created_at>=?", (day,))
    return {
        "acts_today": acts[0]["n"], "max_acts": _env_int("JARVIS_AUTONOMY_MAX_ACTS_PER_DAY", 10),
        "suggestions_today": sugg[0]["n"], "max_suggestions": _env_int("JARVIS_AUTONOMY_MAX_SUGGESTIONS_PER_DAY", 8),
        "max_bg_tasks": _env_int("JARVIS_AUTONOMY_MAX_BG_TASKS", 2),
    }


def _log_decision(context: str, need: Any, decision: str, action: str = "", reason: str = "") -> None:
    _exec("INSERT INTO autonomy_decisions (tick_time_iso, context_summary, detected_need_json, decision, "
          "action_taken, policy_reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
          (_iso(), (context or "")[:600], json.dumps(need)[:1500] if need is not None else None,
           decision, action[:600], reason[:300], _iso()))
    _audit("decision", {"decision": decision, "action": action[:200], "reason": reason[:200]},
           (context or "")[:300])


# ---------------------------------------------------------------------------- actions & suggestions
def _action_for_commitment(c: dict) -> tuple[str | None, dict]:
    """The one concrete action a stored commitment implies, or (None, {}) if it is tracking-only."""
    if c["who_is_responsible"] != "user" and c["type"] != "event":
        return None, {}
    dl = c.get("deadline_iso")
    if c["type"] == "event" and dl:
        meta = _meta(c)
        return "calendar", {"title": c["description"], "start_iso": dl, "end_iso": meta.get("end_iso"),
                            "location": meta.get("location"), "participants": meta.get("participants")}
    if c["type"] in ("task", "promise") and dl:
        try:
            when = datetime.fromisoformat(dl) - timedelta(hours=1)
        except ValueError:
            return None, {}
        if when < _now() + timedelta(minutes=2):
            when = _now() + timedelta(minutes=2)
        return "reminder", {"text": c["description"], "due_iso": when.isoformat(timespec="seconds")}
    return None, {}


def _title(action_type: str, details: dict, fallback: str) -> str:
    if action_type == "calendar":
        return f"Add to calendar: {details.get('title') or fallback} ({(details.get('start_iso') or '')[:16]})"
    if action_type == "reminder":
        return f"Remind you: {details.get('text') or fallback} ({(details.get('due_iso') or '')[:16]})"
    if action_type == "background_task":
        return f"Work on it in the background: {details.get('description') or fallback}"
    return f"{action_type}: {details.get('description') or details.get('text') or fallback}"[:160]


def create_suggestion(category: str, sender: str, title: str, evidence: str, action_type: str | None,
                      details: dict, confidence: float, commitment_id: int | None = None) -> int | None:
    b = budgets()
    if b["suggestions_today"] >= b["max_suggestions"]:
        _log_decision(title, None, "silent", "", "daily suggestion budget reached")
        return None
    if _recently_dismissed(category):
        _log_decision(title, None, "silent", "", f"{category} dismissed recently")
        return None
    dup = _rows("SELECT id FROM autonomy_suggestions WHERE status='pending' AND title=?", (title,))
    if dup:
        return dup[0]["id"]
    sid = _exec("INSERT INTO autonomy_suggestions (created_at, category, sender, title, evidence, action_type, "
                "action_json, confidence, status, commitment_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                (_iso(), category, sender or "", title[:300], (evidence or "")[:500], action_type,
                 json.dumps(details), confidence, commitment_id))
    _log_decision(title, {"category": category, "confidence": confidence}, "suggest", title, "asked (policy)")
    _publish()
    return sid


def _run_action(action_type: str | None, details: dict, commitment_id: int | None = None) -> tuple[bool, str]:
    """Performs one approved/auto action through existing Jarvis paths only. Dry-run does nothing."""
    if dry_run():
        return True, f"(dry run) would {action_type}: {json.dumps(details)[:200]}"
    if action_type == "reminder":
        res = _call("create_reminder", str(details.get("text") or ""), str(details.get("due_iso") or ""),
                    default=None)
        return (res is not None and "couldn't" not in str(res).lower()), str(res)
    if action_type == "notification":
        _call("notify", str(details.get("text") or details.get("description") or ""), False)
        return True, "notification delivered"
    if action_type == "background_task":
        if (_call("running_background_count", default=0) or 0) >= budgets()["max_bg_tasks"]:
            return False, "too many background tasks already running; try again later"
        desc = str(details.get("description") or details.get("title") or "autonomy task")
        res = _call("queue_task", desc, str(details.get("instructions") or desc),
                    str(details.get("priority") or "normal"), details.get("deadline_iso"), default=None)
        if commitment_id:
            _set_commitment_meta(commitment_id, accepted=True, queued=True)
        return res is not None, str(res)
    if action_type in ("calendar", "email", "file_op"):
        # Handed to the normal agent loop, so its tools, audit and the catastrophic gate all apply.
        if action_type == "calendar":
            instr = ("Create a calendar event with the Google Calendar tools: "
                     f"{json.dumps(details)}. Do not send emails or invite anyone. Reply in one short sentence.")
        elif action_type == "email":
            instr = (f"Do exactly this email task and nothing more: {json.dumps(details)}. "
                     "Reply in one short sentence.")
        else:
            instr = (f"Do exactly this file task and nothing more: {json.dumps(details)}. "
                     "Reply in one short sentence.")
        res = _call("run_agent", instr, default=None)
        return res is not None, str(res or "no agent available")
    return False, f"unknown action type {action_type!r}"


def _finish_suggestion(sid: int, status: str, result: str) -> None:
    _exec("UPDATE autonomy_suggestions SET status=?, decided_at=?, result=? WHERE id=?",
          (status, _iso(), result[:500], sid))
    _publish()


def approve_suggestion(sid: int, background: bool = True) -> str:
    rows = _rows("SELECT * FROM autonomy_suggestions WHERE id=?", (sid,))
    if not rows:
        return f"No suggestion #{sid}."
    s = rows[0]
    if s["status"] != "pending":
        return f"Suggestion #{sid} is already {s['status']}."
    try:
        details = json.loads(s["action_json"] or "{}")
    except json.JSONDecodeError:
        details = {}
    _exec("UPDATE autonomy_suggestions SET status='running', decided_at=? WHERE id=?", (_iso(), sid))
    record_feedback(s["category"], s["sender"] or "", s["action_type"], True)

    def _work() -> None:
        ok, res = _run_action(s["action_type"], details, s["commitment_id"])
        _finish_suggestion(sid, "executed" if ok else "failed", res)
        _log_decision(s["title"], None, "act", f"approved #{sid}: {res}"[:500], "user approved")
        _audit("action", {"suggestion": sid, "type": s["action_type"], "ok": ok}, res)
        if not ok:
            _call("notify", f"That approved suggestion failed: {res[:160]}", False)

    if background:
        threading.Thread(target=_work, daemon=True, name="autonomy-approve").start()
        return f"Approved suggestion #{sid}; working on it."
    _work()
    return f"Approved suggestion #{sid}."


def dismiss_suggestion(sid: int, never: bool = False) -> str:
    rows = _rows("SELECT * FROM autonomy_suggestions WHERE id=?", (sid,))
    if not rows:
        return f"No suggestion #{sid}."
    s = rows[0]
    if s["status"] != "pending":
        return f"Suggestion #{sid} is already {s['status']}."
    _finish_suggestion(sid, "dismissed", "never for this category" if never else "dismissed")
    record_feedback(s["category"], s["sender"] or "", s["action_type"], False)
    if never:
        set_policy(s["category"], "ignore", source="user")
    _log_decision(s["title"], None, "dismiss", "", "user dismissed" + (" (never)" if never else ""))
    return f"Dismissed suggestion #{sid}" + (f"; I won't suggest {s['category']} again." if never else ".")


def list_suggestions(status: str = "pending", limit: int = 30) -> list[dict]:
    return _rows("SELECT * FROM autonomy_suggestions WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit))


def _route(category: str, sender: str, title: str, evidence: str, action_type: str | None, details: dict,
           confidence: float, source_type: str, commitment_id: int | None, model_says: str = "suggest",
           gated_ok: bool = True) -> str:
    """One item -> policy -> act | suggest | silent, logged. Returns the decision."""
    text = f"{title} {evidence}"
    if not action_type:
        _log_decision(title, {"category": category}, "silent", "", "tracking only, no action implied")
        return "silent"
    verdict, reason = evaluate_policy(category, sender, text, confidence, action_type, source_type)
    if verdict == "ignore":
        _log_decision(title, {"category": category}, "silent", "", reason)
        return "silent"
    if verdict == "auto_act" and model_says != "suggest" and _recently_dismissed(category):
        verdict, reason = "ask", "similar item dismissed recently"
    if verdict == "auto_act" and model_says != "suggest":
        b = budgets()
        if b["acts_today"] >= b["max_acts"]:
            _log_decision(title, None, "silent", "", "daily autonomous-action budget reached")
            return "silent"
        if not gated_ok:
            return "deferred"  # user busy/asleep: try again on a later tick, no decision logged
        ok, res = _run_action(action_type, details, commitment_id)
        _log_decision(title, {"category": category, "confidence": confidence}, "act", res, reason)
        _audit("action", {"category": category, "type": action_type, "ok": ok}, res)
        return "act"
    create_suggestion(category, sender, _title(action_type, details, title), evidence, action_type, details,
                      confidence, commitment_id)
    return "suggest"


# -------------------------------------------------------------------------------------- extraction
def _recent_tool_actions(transcript: str, limit: int = 8) -> str:
    rows = _rows("SELECT tool_name, tool_input, result FROM action_audit WHERE transcript=? "
                 "ORDER BY id DESC LIMIT ?", (transcript, limit))
    return "\n".join(f"- {r['tool_name']}({r['tool_input'][:120]}) -> {r['result'][:120]}" for r in rows) or "(none)"


def test_commitment_extraction(turns_text: str, tool_actions_text: str = "(none)") -> list[dict]:
    """Manual hook: runs the extraction prompt and returns the parsed, validated items without
    storing anything."""
    parsed = _ask_model(_fill(COMMITMENT_EXTRACTION_PROMPT, conversation_turns_text=turns_text,
                              recent_tool_actions_text=tool_actions_text), 900)
    return [c for c in (parsed if isinstance(parsed, list) else [])
            if isinstance(c, dict) and float(c.get("confidence") or 0) >= MIN_EXTRACT_CONFIDENCE]


def extract_commitments_and_projects(turns_text: str, tool_actions_text: str = "(none)",
                                     source_type: str = "conversation", sender: str = "",
                                     gated_ok: bool = True) -> list[int]:
    """conversation text -> commitments (+ projects) -> policy routing. Returns new commitment ids."""
    if not enabled() or not (turns_text or "").strip():
        return []
    parsed = _ask_model(_fill(COMMITMENT_EXTRACTION_PROMPT, conversation_turns_text=turns_text[:6000],
                              recent_tool_actions_text=tool_actions_text[:1500]), 900)
    if not isinstance(parsed, list):
        return []
    return _ingest([c for c in parsed if isinstance(c, dict)], source_type, sender, gated_ok)


def _ingest(items: list[dict], source_type: str, sender: str, gated_ok: bool = True) -> list[int]:
    created: list[int] = []
    for item in items:
        cid = add_commitment(item, source_type, sender)
        if not cid:
            continue
        created.append(cid)
        c = _commitment(cid)
        if not c:
            continue
        action_type, details = _action_for_commitment(c)
        category = f"{source_type}:{action_type or 'track'}"
        _route(category, sender, c["description"], c["source_quote"] or "", action_type, details,
               float(c["confidence"] or 0), source_type, cid, gated_ok=gated_ok)
    if created:
        _publish()
    return created


def after_turn(transcript: str, reply: str, source: str = "text") -> None:
    """Called by jarvis.py after every command. Cheap unless the exchange contains a cue that
    something is planned; then one model call on a worker thread (never delays the reply)."""
    if not enabled() or source == "autonomy" or len((transcript or "").strip()) < 12:
        return
    if not _truthy(os.environ.get("JARVIS_AUTONOMY_EXTRACT_ALWAYS")) and not _CUE_RE.search(transcript or ""):
        return
    turns = f"User: {transcript}\nJarvis: {(reply or '')[:600]}"

    def _work() -> None:
        try:
            extract_commitments_and_projects(turns, _recent_tool_actions(transcript), "conversation",
                                             gated_ok=gate_reason() is None)
        except Exception as e:
            log.warning("Autonomy extraction failed: %s", e)

    threading.Thread(target=_work, daemon=True, name="autonomy-extract").start()


def process_inbound_message_for_events(subject: str, body: str, sender: str = "", source: str = "email") -> list[int]:
    """Mail / Telegram / Discord hook. Meetings become event commitments, tasks become task
    commitments; both go through the policy engine, and since someone else wrote the text nothing
    auto-acts unless a rule names that sender or keyword. Returns new commitment ids."""
    if not enabled() or not ((subject or "").strip() or (body or "").strip()):
        return []
    source = source if source in INBOUND_SOURCES else "message"
    parsed = _ask_model(_fill(EMAIL_EVENT_EXTRACTION_PROMPT, current_time_iso=_iso(),
                              email_subject=(subject or "")[:300], email_body=(body or "")[:5000]), 900)
    if not isinstance(parsed, dict):
        return []
    items: list[dict] = []
    for m in parsed.get("meetings") or []:
        if isinstance(m, dict) and (m.get("title") or m.get("start_iso")):
            items.append({"type": "event", "description": m.get("title") or f"Meeting from {sender or 'message'}",
                          "who_is_responsible": "user", "deadline_iso": m.get("start_iso"),
                          "end_iso": m.get("end_iso"), "location": m.get("location"),
                          "participants": m.get("participants"), "confidence": m.get("confidence"),
                          "source_quote": m.get("source_quote")})
    for t in parsed.get("tasks") or []:
        if isinstance(t, dict) and t.get("description"):
            items.append({"type": "task", "description": t["description"], "who_is_responsible": "user",
                          "deadline_iso": t.get("deadline_iso"), "confidence": t.get("confidence"),
                          "source_quote": t.get("source_quote")})
    return _ingest(items, source, sender or "")


# ------------------------------------------------------------------------------------ memory reads
def memory_context(query: str = "", max_chars: int = 1800) -> str:
    """Compact retrieval for the tick (projects + commitments + summaries + semantic recall)."""
    lines: list[str] = []
    for p in _rows("SELECT name, goal, deadline_iso FROM autonomy_projects WHERE status='active' LIMIT 8"):
        lines.append(f"Project: {p['name']}" + (f" - {p['goal']}" if p["goal"] else "")
                     + (f" (due {p['deadline_iso'][:10]})" if p["deadline_iso"] else ""))
    for c in _rows("SELECT id, type, description, deadline_iso, who_is_responsible FROM commitments "
                   "WHERE status='open' ORDER BY COALESCE(deadline_iso,'9999') LIMIT 12"):
        lines.append(f"Open {c['type']} #{c['id']} ({c['who_is_responsible']}): {c['description']}"
                     + (f" - due {c['deadline_iso'][:16]}" if c["deadline_iso"] else ""))
    for s in _rows("SELECT summary_text, end_time_iso FROM conversation_summaries ORDER BY id DESC LIMIT 3"):
        lines.append(f"Earlier ({(s['end_time_iso'] or '')[:10]}): {s['summary_text'][:240]}")
    if query:
        recalled = _call("semantic_recall", query, default="")
        if recalled and "no " not in str(recalled)[:12].lower():
            lines.append("Related memory: " + str(recalled)[:500])
    return "\n".join(lines)[:max_chars]


def agent_context_line(max_chars: int = 700) -> str:
    """One short block for run_agent_loop's volatile system block: what is open and upcoming."""
    if not enabled():
        return ""
    soon = _iso(_now() + timedelta(days=3))
    rows = _rows("SELECT id, description, deadline_iso FROM commitments WHERE status='open' AND "
                 "(deadline_iso IS NULL OR deadline_iso<=?) ORDER BY COALESCE(deadline_iso,'9999') LIMIT 6", (soon,))
    projects = _rows("SELECT name FROM autonomy_projects WHERE status='active' LIMIT 5")
    if not rows and not projects:
        return ""
    parts = []
    if projects:
        parts.append("Active projects: " + ", ".join(p["name"] for p in projects) + ".")
    if rows:
        parts.append("Open commitments: " + "; ".join(
            f"#{r['id']} {r['description'][:70]}" + (f" (due {r['deadline_iso'][:16]})" if r["deadline_iso"] else "")
            for r in rows) + ".")
    return ("\nAutonomy memory (things the user has committed to; mention only if relevant): "
            + " ".join(parts))[:max_chars]


# ---------------------------------------------------------------------------- tick building blocks
def _turns_since(last_id: int, limit: int = 60) -> list[dict]:
    return _rows("SELECT id, role, content, timestamp FROM memory_turns WHERE id>? ORDER BY id LIMIT ?",
                 (last_id, limit))


def _maybe_summarize(now: datetime) -> bool:
    """After N idle minutes, one SESSION_SUMMARIZATION_PROMPT call over the turns not yet summarized."""
    last_id = int(get_setting("summarized_through_turn_id", "0") or 0)
    turns = _turns_since(last_id)
    if not turns:
        return False
    try:
        last_ts = datetime.fromisoformat(turns[-1]["timestamp"])
    except ValueError:
        last_ts = now - timedelta(days=1)
    idle_min = _env_int("JARVIS_AUTONOMY_SUMMARY_IDLE_MIN", 20)
    if (now - last_ts) < timedelta(minutes=idle_min):
        return False
    if len(turns) < 4 and (now - last_ts) < timedelta(hours=6):
        return False
    attempted = get_setting("summary_attempt_at")
    if attempted and (now - datetime.fromisoformat(attempted)) < timedelta(minutes=30):
        return False
    set_setting("summary_attempt_at", _iso(now))
    text = "\n".join(f"{'User' if t['role'] == 'user' else 'Jarvis'}: {str(t['content'])[:400]}" for t in turns)
    parsed = _ask_model(_fill(SESSION_SUMMARIZATION_PROMPT, conversation_turns_text=text[:7000]), 700)
    if not isinstance(parsed, dict) or not str(parsed.get("summary_text") or "").strip():
        return False
    _exec("INSERT INTO conversation_summaries (session_id, summary_text, start_time_iso, end_time_iso, tags_json, "
          "created_at) VALUES (?, ?, ?, ?, ?, ?)",
          (f"turns-{turns[0]['id']}-{turns[-1]['id']}", str(parsed["summary_text"])[:1500],
           turns[0]["timestamp"], turns[-1]["timestamp"], json.dumps(parsed.get("tags") or {}), _iso(now)))
    set_setting("summarized_through_turn_id", str(turns[-1]["id"]))
    _log_decision(f"summarized {len(turns)} turns", None, "act", "conversation summary stored", "session idle")
    return True


def _expire_old(now: datetime) -> None:
    cutoff = _iso(now - timedelta(hours=SUGGESTION_TTL_H))
    _exec("UPDATE autonomy_suggestions SET status='expired', decided_at=? WHERE status='pending' AND created_at<?",
          (_iso(now), cutoff))
    _exec("UPDATE commitments SET status='expired', updated_at=? WHERE status='open' AND deadline_iso IS NOT NULL "
          "AND deadline_iso<?", (_iso(now), _iso(now - timedelta(days=2))))


def _deadline_scan(now: datetime, gated_ok: bool) -> int:
    """Deterministic (no model): a nudge as an open commitment's deadline nears. Buckets are
    remembered per commitment so each fires once. If the user is busy/asleep the bucket stays
    unmarked and it is retried on a later tick."""
    fired = 0
    horizon = _iso(now + timedelta(hours=24))
    floor = _iso(now - timedelta(days=1))
    for c in _rows("SELECT * FROM commitments WHERE status='open' AND deadline_iso IS NOT NULL AND "
                   "deadline_iso<=? AND deadline_iso>=? AND who_is_responsible!='other'", (horizon, floor)):
        try:
            due = datetime.fromisoformat(c["deadline_iso"])
        except ValueError:
            continue
        left = due - now
        bucket = "overdue" if left.total_seconds() < 0 else ("2h" if left <= timedelta(hours=2) else "24h")
        meta = _meta(c)
        if bucket in (meta.get("notified") or []):
            continue
        when = "is overdue" if bucket == "overdue" else f"is due {due.strftime('%A %H:%M')}"
        text = f"Heads up: {c['description']} {when}."
        decision = _route("deadline:notification", "", c["description"], c["source_quote"] or "", "notification",
                          {"text": text}, 1.0, "deadline", c["id"], model_says="act", gated_ok=gated_ok)
        if decision in ("act", "suggest", "silent"):
            _set_commitment_meta(c["id"], notified=(meta.get("notified") or []) + [bucket])
            fired += decision == "act"
    return fired


def _announce_pending(now: datetime) -> None:
    """Speak at most one not-yet-announced suggestion per tick, only when the gates are clear."""
    rows = _rows("SELECT * FROM autonomy_suggestions WHERE status='pending' AND announced_at IS NULL "
                 "ORDER BY id LIMIT 1")
    if not rows:
        return
    s = rows[0]
    text = (f"Suggestion {s['id']}: {s['title']}. Confidence {int(float(s['confidence'] or 0) * 100)} percent. "
            "Say approve or dismiss suggestion " + str(s["id"]) + ", or use the dashboard.")
    _call("notify", text, False)
    _exec("UPDATE autonomy_suggestions SET announced_at=? WHERE id=?", (_iso(now), s["id"]))


def _context_summary(now: datetime) -> str:
    parts = [f"Now: {now.strftime('%A %Y-%m-%d %H:%M')}"]
    for label, name, arg in (("Calendar (next 48h)", "calendar_events", 48), ("Workspace", "workspace", None),
                             ("File events", "file_events", None), ("System", "system_status", None)):
        val = _call(name, arg, default="") if arg is not None else _call(name, default="")
        if val:
            parts.append(f"{label}: {str(val)[:500]}")
    turns = _rows("SELECT role, content FROM memory_turns ORDER BY id DESC LIMIT 6")[::-1]
    if turns:
        parts.append("Recent turns: " + " | ".join(f"{t['role']}: {str(t['content'])[:120]}" for t in turns))
    pending = _rows("SELECT COUNT(*) n FROM autonomy_suggestions WHERE status='pending'")[0]["n"]
    parts.append(f"Pending suggestions awaiting the user: {pending}")
    return "\n".join(parts)


def _classifier_step(now: datetime, force: bool = False) -> dict | None:
    """The model check: 'is there a latent need right now?' Rate-limited and skipped when the
    context is unchanged, because it is the only per-tick step that costs money."""
    global _last_classifier, _last_context_hash
    interval = timedelta(minutes=_env_int("JARVIS_AUTONOMY_CLASSIFIER_MIN", 15))
    if not force and _last_classifier and now - _last_classifier < interval:
        return None
    memory = memory_context()
    calendar = _call("calendar_events", 48, default="")
    if not force and not memory and not calendar:
        return None  # nothing to reason about yet
    context = _context_summary(now)
    digest = hashlib.sha1((context.split("Now:", 1)[-1][20:] + memory).encode("utf-8", "ignore")).hexdigest()
    if not force and digest == _last_context_hash:
        return None
    _last_classifier, _last_context_hash = now, digest
    parsed = _ask_model(_fill(AUTONOMY_TICK_CLASSIFIER_PROMPT, context_summary=context[:3000],
                              memory_context=(memory or "(none yet)")[:2500]), 700)
    if not isinstance(parsed, dict):
        return None
    if not parsed.get("has_need"):
        _log_decision(context, parsed, "silent", "", "classifier: no need")
        return parsed
    try:
        conf = float(parsed.get("confidence") or 0)
    except (TypeError, ValueError):
        conf = 0.0
    payload = parsed.get("action_payload") if isinstance(parsed.get("action_payload"), dict) else {}
    action_type = payload.get("action_type") if payload.get("action_type") in ACTION_TYPES else None
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    desc = str(parsed.get("description") or "").strip()
    if conf < MIN_EXTRACT_CONFIDENCE or parsed.get("suggested_action") == "monitor" or not desc:
        _log_decision(context, parsed, "silent", "", "monitor / below confidence floor")
        return parsed
    if action_type is None:
        action_type, details = "notification", {"text": desc}
    _route(f"tick:{parsed.get('type') or 'need'}:{action_type}", "", desc, desc, action_type, details, conf,
           "tick", None, model_says=str(parsed.get("suggested_action") or "suggest"))
    return parsed


# ---------------------------------------------------------------------------- Phase 5: horizons
def add_project_action(project: str, description: str, scheduled_for: str = "", action_type: str = "background_task") -> str:
    pid = get_or_create_project(project)
    if pid is None:
        return "Give the project a name."
    if action_type not in ("background_task", "reminder", "notification"):
        return "Campaign actions may be background_task, reminder or notification."
    _exec("INSERT INTO autonomy_project_actions (project_id, action_type, description, status, scheduled_for_iso, "
          "created_at) VALUES (?, ?, ?, 'planned', ?, ?)",
          (pid, action_type, description.strip()[:400], _norm_dt(scheduled_for) or _iso(), _iso()))
    _publish()
    return f"Added a planned step to project {project!r}. It runs only after you approve the campaign."


def approve_campaign(project: str, approved: bool = True) -> str:
    rows = _rows("SELECT * FROM autonomy_projects WHERE lower(name)=lower(?)", (project.strip(),))
    if not rows:
        return f"No project named {project!r}."
    meta = _meta(rows[0])
    meta["campaign_approved"] = bool(approved)
    _exec("UPDATE autonomy_projects SET metadata_json=?, updated_at=? WHERE id=?",
          (json.dumps(meta), _iso(), rows[0]["id"]))
    _publish()
    return f"Campaign for {rows[0]['name']} {'approved' if approved else 'paused'}."


def _campaign_step(now: datetime, gated_ok: bool) -> int:
    """Drives approved projects' planned steps across days via the existing task queue, and
    reconciles queued steps against task_queue's status. High-risk projects simulate first."""
    ran = 0
    for a in _rows("SELECT a.*, p.name pname, p.risk_level, p.metadata_json pmeta FROM autonomy_project_actions a "
                   "JOIN autonomy_projects p ON p.id=a.project_id WHERE a.status='queued' AND a.task_ref IS NOT NULL"):
        t = _rows("SELECT status FROM task_queue WHERE id=?", (a["task_ref"],))
        if t and t[0]["status"] in ("done", "failed", "cancelled"):
            _exec("UPDATE autonomy_project_actions SET status=?, completed_at=?, result_summary=? WHERE id=?",
                  ("completed" if t[0]["status"] == "done" else "failed", _iso(now), f"task {t[0]['status']}", a["id"]))
    if not gated_ok:
        return 0
    for a in _rows("SELECT a.*, p.name pname, p.risk_level, p.metadata_json pmeta FROM autonomy_project_actions a "
                   "JOIN autonomy_projects p ON p.id=a.project_id WHERE a.status='planned' AND p.status='active' "
                   "AND a.scheduled_for_iso<=? ORDER BY a.scheduled_for_iso LIMIT 3", (_iso(now),)):
        try:
            pmeta = json.loads(a["pmeta"] or "{}")
        except json.JSONDecodeError:
            pmeta = {}
        if not pmeta.get("campaign_approved"):
            continue
        b = budgets()
        if b["acts_today"] >= b["max_acts"]:
            break
        simulate = dry_run() or (a["risk_level"] == "high" and not pmeta.get("live"))
        if simulate:
            _exec("UPDATE autonomy_project_actions SET status='simulated', completed_at=?, result_summary=? WHERE id=?",
                  (_iso(now), "(simulated) would run: " + a["description"][:200], a["id"]))
            _log_decision(f"campaign {a['pname']}", None, "act", f"(simulated) {a['description']}"[:300],
                          "dry run / high-risk project")
            continue
        if a["action_type"] == "background_task":
            if (_call("running_background_count", default=0) or 0) >= b["max_bg_tasks"]:
                break
            ref = _call("queue_task", f"[{a['pname']}] {a['description']}", a["description"], "normal", None, default=None)
            m = re.search(r"#(\d+)", str(ref or ""))
            _exec("UPDATE autonomy_project_actions SET status='queued', task_ref=? WHERE id=?",
                  (int(m.group(1)) if m else None, a["id"]))
            if not m:  # queued but no id to follow: consider it handed off
                _exec("UPDATE autonomy_project_actions SET status='completed', completed_at=? WHERE id=?", (_iso(now), a["id"]))
            _log_decision(f"campaign {a['pname']}", None, "act", f"queued: {a['description']}"[:300], "campaign approved")
            _audit("campaign_step", {"project": a["pname"], "action": a["description"][:120]}, str(ref))
        else:
            ok, res = _run_action(a["action_type"], {"text": a["description"], "description": a["description"],
                                                     "due_iso": _iso(now + timedelta(minutes=1))})
            _exec("UPDATE autonomy_project_actions SET status=?, completed_at=?, result_summary=? WHERE id=?",
                  ("completed" if ok else "failed", _iso(now), res[:300], a["id"]))
            _log_decision(f"campaign {a['pname']}", None, "act", res[:300], "campaign approved")
        ran += 1
    return ran


def _planner_step(now: datetime, gated_ok: bool) -> str | None:
    """Every few hours: accepted, deadline-bearing user tasks that have no queued task yet go into
    the existing priority queue, then the queue is re-planned into free slots."""
    hours = _env_int("JARVIS_AUTONOMY_PLANNER_HOURS", 4)
    last = get_setting("last_planner_at")
    if last and now - datetime.fromisoformat(last) < timedelta(hours=hours):
        return None
    set_setting("last_planner_at", _iso(now))
    horizon = _iso(now + timedelta(days=7))
    queued = 0
    for c in _rows("SELECT * FROM commitments WHERE status='open' AND type IN ('task','promise') AND "
                   "who_is_responsible='user' AND deadline_iso IS NOT NULL AND deadline_iso<=?", (horizon,)):
        meta = _meta(c)
        if not meta.get("accepted") or meta.get("queued") or dry_run():
            continue
        ref = _call("queue_task", c["description"], None, "high" if c["deadline_iso"] < _iso(now + timedelta(days=1)) else "normal",
                    c["deadline_iso"], default=None)
        if ref is not None:
            _set_commitment_meta(c["id"], queued=True)
            queued += 1
    if queued:
        _call("plan_queue", default=None)
    if not queued:
        return None
    summary = f"planner: queued {queued} accepted task(s) and re-planned the day"
    _log_decision("daily planner", None, "act", summary, "scheduled planner")
    return summary


# --------------------------------------------------------------------------------------- the tick
def tick(now: datetime | None = None) -> None:
    """Called from jarvis.py's scheduler loop every SCHEDULER_TICK_S. Cheap when disabled; when
    enabled the work runs on a worker thread so a slow model call never stalls the scheduler."""
    global _last_tick_start
    if not _started or not enabled():
        return
    now = now or _now()
    if _last_tick_start and (now - _last_tick_start).total_seconds() < _env_int("JARVIS_AUTONOMY_TICK_S", 45):
        return
    if _tick_running.is_set():
        return
    _last_tick_start = now
    threading.Thread(target=run_autonomy_tick_once, kwargs={"now": now}, daemon=True, name="autonomy-tick").start()


def run_autonomy_tick_once(callbacks: dict | None = None, now: datetime | None = None,
                           force_classifier: bool = False) -> dict:
    """One full pass (also the manual test hook). Returns what happened."""
    if callbacks:
        configure(callbacks)
    if not enabled():
        return {"skipped": "autonomy disabled"}
    if not _tick_lock.acquire(blocking=False):
        return {"skipped": "tick already running"}
    _tick_running.set()
    now = now or _now()
    out: dict[str, Any] = {}
    try:
        gate = gate_reason()
        out["gate"] = gate
        for name, fn in (
            ("expired", lambda: _expire_old(now)),
            ("deadline_acts", lambda: _deadline_scan(now, gate is None)),
            ("campaign_steps", lambda: _campaign_step(now, gate is None)),
            ("planner", lambda: _planner_step(now, gate is None)),
        ):
            try:
                out[name] = fn()
            except Exception as e:
                log.warning("Autonomy step %s failed: %s", name, e)
        if gate is None:
            for name, fn in (("summarized", lambda: _maybe_summarize(now)),
                             ("consolidated", lambda: _call("consolidate", now)),
                             ("announced", lambda: _announce_pending(now)),
                             ("classifier", lambda: _classifier_step(now, force_classifier))):
                try:
                    out[name] = fn()
                except Exception as e:
                    log.warning("Autonomy step %s failed: %s", name, e)
    finally:
        _tick_running.clear()
        _tick_lock.release()
    return out


def start_autonomy_tick(callbacks: dict[str, Callable]) -> None:
    """Wire callbacks and arm the tick. jarvis.py's scheduler loop then calls tick(now). No
    thread is started here on purpose: the existing SCHEDULER_TICK_S loop is the clock."""
    global _started
    init_autonomy_tables()
    configure(callbacks)
    _started = True
    log.info("Autonomy armed (%s). Off by default; `autonomy` tool or dashboard toggles it.",
             "ON" if enabled() else "off")


def stop_autonomy_tick() -> None:
    global _started
    _started = False
    _cb.clear()


# ------------------------------------------------------------------------------- status & tool API
def status() -> dict:
    return {
        "enabled": enabled(), "hard_disabled": hard_disabled(), "dry_run": dry_run(), "budgets": budgets(),
        "pending_suggestions": list_suggestions("pending"),
        "commitments": _rows("SELECT * FROM commitments WHERE status='open' ORDER BY COALESCE(deadline_iso,'9999') LIMIT 40"),
        "projects": _rows("SELECT * FROM autonomy_projects WHERE status!='archived' ORDER BY id DESC LIMIT 20"),
        "project_actions": _rows("SELECT * FROM autonomy_project_actions ORDER BY id DESC LIMIT 40"),
        "policies": list_policies(),
        "decisions": _rows("SELECT * FROM autonomy_decisions ORDER BY id DESC LIMIT 40"),
        "summaries": _rows("SELECT id, summary_text, end_time_iso FROM conversation_summaries ORDER BY id DESC LIMIT 5"),
    }


def _brief() -> str:
    s = status()
    b = s["budgets"]
    return (f"Autonomy is {'on' if s['enabled'] else 'off'}{' (dry run)' if s['dry_run'] else ''}. "
            f"{len(s['pending_suggestions'])} suggestion(s) waiting, {len(s['commitments'])} open commitment(s), "
            f"{len(s['projects'])} project(s). Today: {b['acts_today']}/{b['max_acts']} autonomous actions, "
            f"{b['suggestions_today']}/{b['max_suggestions']} suggestions.")


def handle_tool(inp: dict, source: str | None) -> str:
    """The model-facing `autonomy` tool. Turning things ON or loosening rules is refused from the
    phone and from unattended runs (only voice/text/dashboard); turning things OFF works anywhere."""
    action = str(inp.get("action") or "status").lower()
    attended = source in ("voice", "text", "dashboard")
    loosening = ("enable", "dry_run_off", "set_policy", "approve_campaign", "add_action", "approve")
    if action in loosening and not attended:
        return "That changes what Jarvis may do on its own, so it is only accepted from the PC (voice, typed or dashboard), not the phone."
    if action == "status":
        return _brief()
    if action == "enable":
        return set_enabled(True)
    if action == "disable":
        return set_enabled(False)
    if action == "dry_run_on":
        return set_dry_run(True)
    if action == "dry_run_off":
        return set_dry_run(False)
    if action == "list_suggestions":
        rows = list_suggestions("pending")
        return "\n".join(f"#{r['id']} [{int(float(r['confidence'] or 0) * 100)}%] {r['title']}" for r in rows) or "No suggestions waiting."
    if action == "approve":
        return approve_suggestion(int(inp.get("id") or 0))
    if action in ("dismiss", "never"):
        return dismiss_suggestion(int(inp.get("id") or 0), never=action == "never")
    if action == "list_commitments":
        rows = _rows("SELECT id, type, description, deadline_iso FROM commitments WHERE status='open' "
                     "ORDER BY COALESCE(deadline_iso,'9999') LIMIT 20")
        return "\n".join(f"#{r['id']} {r['type']}: {r['description']}" + (f" (due {r['deadline_iso'][:16]})" if r["deadline_iso"] else "")
                         for r in rows) or "No open commitments."
    if action in ("complete_commitment", "cancel_commitment"):
        return set_commitment_status(int(inp.get("id") or 0), "completed" if action == "complete_commitment" else "cancelled")
    if action == "accept_commitment":
        cid = int(inp.get("id") or 0)
        if not _commitment(cid):
            return f"No commitment #{cid}."
        _set_commitment_meta(cid, accepted=True)
        return f"Commitment #{cid} accepted; the planner will schedule it."
    if action == "add_project":
        pid = get_or_create_project(str(inp.get("project") or ""), str(inp.get("goal") or ""),
                                    str(inp.get("risk_level") or "low"))
        return f"Project ready (#{pid})." if pid else "Give the project a name."
    if action == "add_action":
        return add_project_action(str(inp.get("project") or ""), str(inp.get("description") or ""),
                                  str(inp.get("scheduled_for") or ""), str(inp.get("action_type") or "background_task"))
    if action == "approve_campaign":
        return approve_campaign(str(inp.get("project") or ""), inp.get("approved", True) is not False)
    if action == "set_policy":
        return set_policy(str(inp.get("category") or ""), str(inp.get("verdict") or ""),
                          str(inp.get("match_kind") or "category"), str(inp.get("match_value") or ""),
                          inp.get("min_confidence"))
    if action == "list_policies":
        return "\n".join(f"#{p['id']} {p['match_kind']} {p['match_value'] or p['category']} -> {p['verdict']} ({p['source']})"
                         for p in list_policies()) or "No rules."
    if action == "run_tick":
        return json.dumps(run_autonomy_tick_once(force_classifier=True), default=str)[:600]
    return f"Unknown autonomy action {action!r}."
