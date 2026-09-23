"""Composable, side-effect-safe skills for the autonomy layer.

A skill is a NAMED, ORDERED sequence of tool calls that already exist (built-in tools, MCP tools, dynamic
tools) with fixed parameters. It gains no new power: every step is executed through jarvis.py's normal
`_execute_tool`, so the catastrophic confirmation gate, the audit log and every per-tool guard apply
exactly as if the model had called the tools one by one. A skill can only name a tool that exists RIGHT
NOW (checked when it is created and again on every run), so a tool that is later removed, or a made-up
name, cannot be smuggled in; it cannot call itself (no recursion) or the skill-management tool.

Under the full-permission model the model may create skills directly, and a sequence the user has run
the same way `JARVIS_AUTONOMY_PATTERN_MIN` (default 3) times is turned into a skill automatically
(shell/python steps are never mined). Everything is logged in autonomy_decisions and action_audit.
Dashboard: list / enable / disable / revoke.

Self-contained like the other jarvis_*.py modules: own tables (IF NOT EXISTS), no import of jarvis.py
(it uses the core module's DB helpers and the callbacks jarvis.py configured: `known_tools() -> [name]`
and `run_tool(name, input) -> str`).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta

import jarvis_autonomy as core

log = logging.getLogger("jarvis.autonomy_skills")

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,39}$")
MAX_STEPS = 12
MAX_MINED_STEPS = 6
FORBIDDEN_TOOLS = frozenset({"autonomy_skill"})           # no recursion / self-management from inside a skill
# Never turned into a skill automatically: shell/python, anything that types or clicks (may carry a password or
# PIN), sends messages, writes files, calls arbitrary HTTP (auth headers), or changes Jarvis itself.
NEVER_MINED = frozenset({
    "run_shell", "run_python", "system_action", "set_plan", "type_text", "click_at", "drag_and_drop", "scroll_screen",
    "read_clipboard", "http_request", "write_file", "set_llm_provider", "enroll_face",
    "delete_face", "face_privacy", "restart_jarvis", "change_jarvis_code", "delegate_to_claude_code",
    "delegate_research", "save_skill", "remember_fact", "create_tool", "manage_dynamic_tool",
})
MAX_MINED_INPUT_CHARS = 1500
MAX_SKILLS_PER_DAY = 10
_FAILED_RE = re.compile(r"^(tool failed|mcp tool|unknown mcp|error|failed|dynamic tool .* failed)", re.I)

_DDL = [
    "CREATE TABLE IF NOT EXISTS autonomy_skills ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, description TEXT NOT NULL, "
    "steps_json TEXT NOT NULL, sig TEXT, is_enabled INTEGER NOT NULL DEFAULT 1, source TEXT NOT NULL DEFAULT 'model', "
    "use_count INTEGER NOT NULL DEFAULT 0, last_used_at TEXT, last_result TEXT, created_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS autonomy_patterns ("
    "sig TEXT PRIMARY KEY, count INTEGER NOT NULL DEFAULT 0, steps_json TEXT NOT NULL, last_seen TEXT NOT NULL)",
]
_ready: set[str] = set()


def _init() -> None:
    key = str(core._db_path())
    if key in _ready:
        return
    with core._db_lock:
        conn = core._raw_connect()
        try:
            for ddl in _DDL:
                conn.execute(ddl)
            conn.commit()
        finally:
            conn.close()
    _ready.add(key)


def _q(sql: str, params: tuple = ()) -> list[dict]:
    _init()
    return core._rows(sql, params)


def _x(sql: str, params: tuple = ()) -> int:
    _init()
    return core._exec_rc(sql, params)


def _known() -> set[str]:
    return {str(n) for n in (core._call("known_tools", default=[]) or [])}


def validate_steps(steps: object) -> tuple[list[dict], str | None]:
    """(clean steps, None) or ([], reason). Every tool must exist now and not be forbidden."""
    if not isinstance(steps, list) or not steps:
        return [], "A skill needs a non-empty list of steps: [{tool, input}]."
    if len(steps) > MAX_STEPS:
        return [], f"A skill may have at most {MAX_STEPS} steps."
    known = _known()
    clean: list[dict] = []
    for i, s in enumerate(steps, 1):
        if not isinstance(s, dict) or not str(s.get("tool") or "").strip():
            return [], f"Step {i} needs a 'tool' name."
        tool = str(s["tool"]).strip()
        if tool in FORBIDDEN_TOOLS:
            return [], f"Step {i}: {tool!r} cannot be used inside a skill."
        if tool not in known:
            return [], f"Step {i}: there is no tool named {tool!r}; a skill can only call tools that already exist."
        inp = s.get("input") or {}
        if not isinstance(inp, dict):
            return [], f"Step {i}: 'input' must be an object."
        try:
            json.dumps(inp)
        except (TypeError, ValueError):
            return [], f"Step {i}: 'input' must be JSON-serialisable."
        clean.append({"tool": tool, "input": inp})
    return clean, None


def _sig(steps: list[dict]) -> str:
    return hashlib.sha1(json.dumps(steps, sort_keys=True).encode()).hexdigest()


def create_skill(name: str, description: str, steps: object, source: str = "model") -> str:
    if core.hard_disabled():
        return "Autonomy is hard-disabled (JARVIS_AUTONOMY_DISABLED)."
    name = (name or "").strip()
    if not NAME_RE.match(name):
        return "Skill name must be lowercase letters, digits and underscores, 3-40 chars, starting with a letter."
    if not (description or "").strip():
        return "A description is required."
    clean, err = validate_steps(steps)
    if err:
        core._log_decision(f"skill {name} rejected", None, "skill", "", err, category="skill", outcome="failed")
        return f"Skill not created: {err}"
    day = core._today_start()
    with core._db_lock:  # budget check + insert as one step (two threads cannot both slip under the limit)
        if _q("SELECT COUNT(*) n FROM autonomy_skills WHERE created_at>=?", (day,))[0]["n"] >= MAX_SKILLS_PER_DAY:
            return f"Daily limit of {MAX_SKILLS_PER_DAY} new skills reached."
        if _q("SELECT 1 FROM autonomy_skills WHERE name=?", (name,)):
            return f"A skill named {name!r} already exists; revoke it first to replace it."
        _x("INSERT INTO autonomy_skills (name, description, steps_json, sig, source, created_at) VALUES (?,?,?,?,?,?)",
           (name, core._clean(description, 300), json.dumps(clean), _sig(clean), source, core._iso()))
    core._log_decision(f"skill {name} created ({source})", None, "skill", f"{len(clean)} step(s): "
                       + ", ".join(s["tool"] for s in clean), "skill registered", category="skill",
                       payload={"steps": clean}, outcome="ok")
    core._publish()
    return f"Skill {name!r} created with {len(clean)} step(s)."


def _substitute(value: object, params: dict) -> object:
    if isinstance(value, str):
        for k, v in params.items():
            value = value.replace("{" + str(k) + "}", str(v))
        return value
    if isinstance(value, dict):
        return {k: _substitute(v, params) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, params) for v in value]
    return value


def run_skill(name: str, params: dict | None = None) -> str:
    """Runs the stored sequence through the normal tool path, one step at a time; stops at the first failure."""
    if core.hard_disabled():
        return "Autonomy is hard-disabled (JARVIS_AUTONOMY_DISABLED)."
    rows = _q("SELECT * FROM autonomy_skills WHERE name=?", ((name or "").strip(),))
    if not rows:
        return f"No skill named {name!r}."
    row = rows[0]
    if not row["is_enabled"]:
        return f"Skill {name!r} is disabled."
    try:
        stored = json.loads(row["steps_json"])
    except json.JSONDecodeError:
        return f"Skill {name!r} is corrupt."
    steps, err = validate_steps(stored)  # re-checked on EVERY run against the tools that exist now
    if err:
        core._log_decision(f"skill {name} refused", None, "skill", "", err, category="skill", outcome="failed")
        return f"Skill {name!r} can no longer run: {err}"
    if core.dry_run():
        return "(dry run) would run: " + ", ".join(s["tool"] for s in steps)
    params = params if isinstance(params, dict) else {}
    results: list[str] = []
    ok = True
    failed_step: dict | None = None
    for i, s in enumerate(steps, 1):
        res = core._call("run_tool", s["tool"], _substitute(s["input"], params), default=None)
        text = str(res if res is not None else "no tool runner available")
        results.append(f"{i}. {s['tool']}: {text[:200]}")
        if res is None or _FAILED_RE.match(text.strip()):
            ok = False
            failed_step = {"step": i, "tool": s["tool"], "error": text[:200]}
            break
    summary = "\n".join(results)
    _x("UPDATE autonomy_skills SET use_count=use_count+1, last_used_at=?, last_result=? WHERE id=?",
       (core._iso(), summary[:600], row["id"]))
    core._log_decision(f"skill {name}", None, "act", summary[:500],
                       "skill run" if ok else f"skill stopped at step {failed_step['step']} ({failed_step['tool']})",
                       category="skill", payload={"steps": [s["tool"] for s in steps], "params": params,
                                                  "failed_step": failed_step},
                       result=summary[:600], outcome="ok" if ok else "failed")
    if not ok:  # exactly one notification per failed run
        core._call("notify", f"Skill {name} stopped at step {failed_step['step']} ({failed_step['tool']}): "
                             f"{failed_step['error'][:100]}", False)
    core._audit("skill_run", {"skill": name, "ok": ok, "steps": len(results)}, summary[:300])
    return ("Ran skill " if ok else "Skill stopped early: ") + f"{name}.\n{summary}"


def list_skills() -> list[dict]:
    return _q("SELECT id, name, description, steps_json, is_enabled, source, use_count, last_used_at, created_at "
              "FROM autonomy_skills ORDER BY id")


def set_enabled(name: str, on: bool) -> str:
    n = _x("UPDATE autonomy_skills SET is_enabled=? WHERE name=?", (1 if on else 0, name))
    core._publish()
    return f"Skill {name} {'enabled' if on else 'disabled'}." if n else f"No skill named {name!r}."


def revoke(name: str) -> str:
    n = _x("DELETE FROM autonomy_skills WHERE name=?", (name,))
    core._publish()
    return f"Skill {name} deleted." if n else f"No skill named {name!r}."


# ----------------------------------------------------------------------------- pattern mining
def note_turn(transcript: str) -> str | None:
    """After a command: if it ran a short sequence of tools (>= 2) and that exact sequence (tools AND
    inputs) has now been seen JARVIS_AUTONOMY_PATTERN_MIN times, register it as a skill. Returns the
    new skill's name, or None."""
    if not core.enabled():
        return None
    rows = list(reversed(core._recent_tool_rows(transcript, 12)))  # chronological
    known = _known()
    steps: list[dict] = []
    for r in rows:
        tool = str(r["tool_name"] or "")
        if not tool or tool in FORBIDDEN_TOOLS or tool in NEVER_MINED or tool not in known or tool.startswith("autonomy"):
            return None
        try:
            inp = json.loads(r["tool_input"] or "{}")
        except json.JSONDecodeError:
            return None
        if not isinstance(inp, dict) or len(json.dumps(inp)) > MAX_MINED_INPUT_CHARS:
            return None
        steps.append({"tool": tool, "input": inp})
    if not (2 <= len(steps) <= MAX_MINED_STEPS):
        return None
    _x("DELETE FROM autonomy_patterns WHERE last_seen<?", (core._iso(datetime.now() - timedelta(days=60)),))
    sig = _sig(steps)
    _x("INSERT INTO autonomy_patterns (sig, count, steps_json, last_seen) VALUES (?, 1, ?, ?) "
       "ON CONFLICT(sig) DO UPDATE SET count=count+1, last_seen=excluded.last_seen",
       (sig, json.dumps(steps), core._iso()))
    count = _q("SELECT count FROM autonomy_patterns WHERE sig=?", (sig,))[0]["count"]
    if count < core._env_int("JARVIS_AUTONOMY_PATTERN_MIN", 3) or _q("SELECT 1 FROM autonomy_skills WHERE sig=?", (sig,)):
        return None
    name = f"auto_{sig[:8]}"
    desc = "Repeated sequence: " + " -> ".join(s["tool"] for s in steps)
    msg = create_skill(name, desc, steps, source="pattern")
    return name if msg.startswith("Skill") and "created" in msg else None


# ------------------------------------------------------------------------------------- tool API
def handle_tool(inp: dict, source: str | None = None) -> str:
    action = str(inp.get("action") or "list").lower()
    name = str(inp.get("name") or "").strip()
    if action == "create":
        return create_skill(name, str(inp.get("description") or ""), inp.get("steps"))
    if action == "run":
        return run_skill(name, inp.get("params"))
    if action == "enable":
        return set_enabled(name, True)
    if action == "disable":
        return set_enabled(name, False)
    if action == "revoke":
        return revoke(name)
    rows = list_skills()
    return "\n".join(f"{r['name']} ({'on' if r['is_enabled'] else 'off'}, used {r['use_count']}x, {r['source']}): "
                     f"{r['description'][:80]}" for r in rows) or "No skills yet."
