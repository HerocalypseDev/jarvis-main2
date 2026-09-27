"""Voice macros (2026-09-27, feature batch A4): a trigger phrase runs a fixed list of existing tool
calls with no LLM call ("start work mode" -> open VS Code, focus mode on, ...).

Stored in `macros` (jarvis_memory.db): name, trigger phrases, steps [{"tool", "input"}], enabled.
Matching is deterministic: the spoken/typed command, lower-cased, punctuation and a leading
"jarvis"/"please" stripped, must equal a trigger phrase (or be >= MATCH_RATIO similar to it, for
small transcription slips). Each step runs through jarvis's normal `_execute_tool`, so every step is
audited and the catastrophic confirmation gate still applies: a step that gets staged stops the macro.

Steps may only name tools that already exist; macros can't call the macro tool itself (no loops)
and add no new privileges.
"""

from __future__ import annotations

import difflib
import json
import re
import sqlite3
from datetime import datetime
from typing import Callable

MATCH_RATIO = 0.9
MAX_STEPS = 12
FORBIDDEN_STEP_TOOLS = {"macros"}
_LEAD_RE = re.compile(r"^(?:(?:hey|ok|okay)\s+)?(?:jarvis\s+)?(?:please\s+)?")


def normalize(text: str) -> str:
    t = re.sub(r"[^\w\s']", " ", (text or "").lower())
    t = re.sub(r"\s+", " ", t).strip()
    t = _LEAD_RE.sub("", t)
    return re.sub(r"\s+please$", "", t).strip()


def ensure(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS macros (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, "
                 "phrases TEXT NOT NULL, steps TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, "
                 "created_at TEXT NOT NULL, last_run TEXT, runs INTEGER NOT NULL DEFAULT 0)")


def _q(connect, lock, sql: str, args: tuple = (), write: bool = False):
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


def list_macros(connect, lock) -> list[dict]:
    out = []
    for r in _q(connect, lock, "SELECT * FROM macros ORDER BY name"):
        r["phrases"], r["steps"], r["enabled"] = json.loads(r["phrases"]), json.loads(r["steps"]), bool(r["enabled"])
        out.append(r)
    return out


def validate(name: str, phrases, steps, known_tools: set[str]) -> str | None:
    if not str(name or "").strip():
        return "A macro needs a name."
    if not isinstance(phrases, list) or not [p for p in phrases if normalize(str(p))]:
        return "A macro needs at least one trigger phrase."
    if any(len(normalize(str(p)).split()) < 2 for p in phrases):
        return "Trigger phrases need at least two words (one word would fire by accident)."
    if not isinstance(steps, list) or not steps or len(steps) > MAX_STEPS:
        return f"A macro needs 1 to {MAX_STEPS} steps."
    for s in steps:
        tool = str((s or {}).get("tool") or "")
        if tool in FORBIDDEN_STEP_TOOLS or tool not in known_tools:
            return f"Step tool {tool!r} isn't an existing tool a macro may use."
        if not isinstance(s.get("input") or {}, dict):
            return f"Step {tool!r} input must be an object."
    return None


def save(connect, lock, name: str, phrases: list, steps: list, known_tools: set[str], enabled: bool = True) -> str:
    err = validate(name, phrases, steps, known_tools)
    if err:
        return err
    clean_steps = [{"tool": s["tool"], "input": s.get("input") or {}} for s in steps]
    clean_phrases = sorted({normalize(str(p)) for p in phrases if normalize(str(p))})
    taken = {p: m["name"] for m in list_macros(connect, lock) if m["name"] != name.strip() for p in m["phrases"]}
    clash = [p for p in clean_phrases if p in taken]
    if clash:
        return f"The phrase {clash[0]!r} already triggers the macro {taken[clash[0]]!r}."
    _q(connect, lock, "INSERT INTO macros (name, phrases, steps, enabled, created_at) VALUES (?, ?, ?, ?, ?) "
                      "ON CONFLICT(name) DO UPDATE SET phrases=excluded.phrases, steps=excluded.steps, enabled=excluded.enabled",
       (name.strip()[:60], json.dumps(clean_phrases), json.dumps(clean_steps), int(bool(enabled)),
        datetime.now().isoformat(timespec="seconds")), write=True)
    return f"Saved macro {name.strip()!r}: say {clean_phrases[0]!r} to run its {len(clean_steps)} step(s)."


def delete(connect, lock, name: str) -> bool:
    return bool(_q(connect, lock, "DELETE FROM macros WHERE name=?", (str(name or "").strip(),), write=True))


def set_enabled(connect, lock, name: str, on: bool) -> bool:
    return bool(_q(connect, lock, "UPDATE macros SET enabled=? WHERE name=?", (int(on), str(name or "").strip()), write=True))


def match(connect, lock, transcript: str) -> dict | None:
    t = normalize(transcript)
    if not t or len(t.split()) > 12:
        return None
    best, score = None, 0.0
    for m in list_macros(connect, lock):
        if not m["enabled"]:
            continue
        for p in m["phrases"]:
            r = 1.0 if p == t else difflib.SequenceMatcher(None, p, t).ratio()
            if r > score:
                best, score = m, r
    return best if score >= MATCH_RATIO else None


def run(connect, lock, macro: dict, execute: Callable[[str, dict], str],
        staged: Callable[[str], bool] | None = None) -> str:
    """Runs the steps in order; stops at a step whose result is a staged confirmation or a failure."""
    done, stopped = [], False
    for i, s in enumerate(macro["steps"], 1):
        result = execute(s["tool"], dict(s.get("input") or {})) or ""
        if staged and staged(result):
            done.append(f"step {i} ({s['tool']}) needs your confirmation: {result}")
            stopped = True
        elif result.lower().startswith(("tool failed", "unrecognized tool")):
            done.append(f"step {i} ({s['tool']}) failed: {result}")
            stopped = True
        else:
            done.append(f"{s['tool']}: {result[:160]}")
        if stopped:
            break
    _q(connect, lock, "UPDATE macros SET last_run=?, runs=runs+1 WHERE id=?",
       (datetime.now().isoformat(timespec="seconds"), macro["id"]), write=True)
    if stopped:
        return f"Macro {macro['name']} stopped. " + "; ".join(done)
    return f"Done: {macro['name']}."


def handle_tool(connect, lock, inp: dict, known_tools: set[str], attended: bool,
                execute: Callable[[str, dict], str] | None = None, staged=None) -> str:
    action = str(inp.get("action") or "list").lower()
    if action == "list":
        ms = list_macros(connect, lock)
        return "\n".join(f"- {m['name']}{'' if m['enabled'] else ' (off)'}: say " +
                         " / ".join(repr(p) for p in m["phrases"]) + " -> " +
                         ", ".join(s["tool"] for s in m["steps"]) for m in ms) or "No macros yet."
    if action in ("create", "delete", "enable", "disable") and not attended:
        return "Macros can only be changed from the PC (voice, typed or dashboard), not from here."
    if action == "create":
        return save(connect, lock, str(inp.get("name") or ""), inp.get("phrases") or [], inp.get("steps") or [],
                    known_tools)
    if action == "delete":
        return "Deleted." if delete(connect, lock, str(inp.get("name") or "")) else "No macro by that name."
    if action in ("enable", "disable"):
        return "Done." if set_enabled(connect, lock, str(inp.get("name") or ""), action == "enable") else \
            "No macro by that name."
    if action == "run" and execute:
        m = next((m for m in list_macros(connect, lock) if m["name"] == str(inp.get("name") or "").strip()), None)
        return run(connect, lock, m, execute, staged) if m else "No macro by that name."
    return "Unknown macro action."
