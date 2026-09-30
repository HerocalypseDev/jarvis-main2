"""Voice macros (2026-09-27, feature batch A4): a trigger phrase runs a fixed list of existing tool
calls with no LLM call ("start work mode" -> open VS Code, focus mode on, ...).

Stored in `macros` (jarvis_memory.db): name, trigger phrases, steps [{"tool", "input"}], enabled.
Matching is deterministic: the spoken/typed command, lower-cased, punctuation and a leading
"jarvis"/"please" stripped, must equal a trigger phrase exactly. (Fuzzy matching was removed in the
2026-09-27 audit: "unlock the screen" scored 0.94 against a "lock the screen" macro. Add more
phrases for variants instead.) Each step runs through jarvis's normal `_execute_tool`, so every step is
audited and the catastrophic confirmation gate still applies: a step that gets staged stops the macro.

Steps may only name tools that already exist; macros can't call the macro tool itself (no loops)
and add no new privileges.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Callable

# Phrases that must keep reaching Jarvis's own handling: "stop talking" silences speech, safe mode is a
# safety switch. A macro can't take them over.
RESERVED = {"stop", "stop talking", "be quiet", "shut up", "quiet", "safe mode on", "safe mode off",
            "turn on safe mode", "turn off safe mode", "yes", "no", "cancel"}
MAX_STEPS = 12
FORBIDDEN_STEP_TOOLS = {"macros"}
_LEAD_RE = re.compile(r"^(?:(?:hey|ok|okay)\s+)?(?:jarvis\s+)?(?:please\s+)?")


def normalize(text: str) -> str:
    t = re.sub(r"[^\w\s]", " ", (text or "").lower().replace("'", "").replace("\u2019", ""))
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
    reserved = [p for p in phrases if normalize(str(p)) in RESERVED]
    if reserved:
        return f"{reserved[0]!r} is one of Jarvis's own commands, so a macro can't use it."
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


# Jarvis4U Pro routine packs (pro/macros/*.json) may only use these low-risk tools. Never shell/python,
# typing, web requests, email, delegation, closing windows or switching a safety feature (Safe Mode) off.
PACK_ALLOWED_TOOLS = {
    "open_app", "open_url", "play_media", "play_ambient_sound", "focus_mode", "create_reminder", "weather",
    "briefing", "daily_plan", "system_status", "system_action", "arrange_windows", "restore_window_layout",
}


# Tools whose result a Pro routine reads back to you (the rest just act, so "Done" is enough).
SPEAK_RESULT_TOOLS = {"briefing", "daily_plan", "weather", "system_status"}


def _pack_step_problem(st: dict) -> str | None:
    tool = str(st.get("tool"))
    if tool not in PACK_ALLOWED_TOOLS:
        return f"tool {tool!r} is not allowed in Pro routines"
    if tool in ("open_url", "play_media"):
        url = str((st.get("input") or {}).get("url") or "").strip().lower()
        if not url.startswith(("https://", "http://")):
            return f"{tool} may only open a web link"   # never a file path / shell: target
    return None


_CONTRACTIONS = {"whats": "what's", "whos": "who's", "im": "i'm", "its": "it's", "dont": "don't", "thats": "that's",
                 "hows": "how's", "wheres": "where's", "lets": "let's", "ill": "i'll", "youre": "you're",
                 "isnt": "isn't", "cant": "can't", "wont": "won't"}


def _phrase_variants(phrase: str) -> set[str]:
    """The phrase as written, normalised, and normalised with apostrophes put back ("whats" -> "what's"):
    matching drops apostrophes, but Jarvis's own intent patterns are written with them."""
    n = normalize(phrase)
    return {phrase.strip().lower(), n, " ".join(_CONTRACTIONS.get(w, w) for w in n.split())}


def pack_macros(specs: list[dict], known_tools: set[str], disabled=(),
                is_core_phrase: Callable[[str], bool] | None = None, log: Callable[[str], None] | None = None) -> list[dict]:
    """Validated, read-only macros from an installed Pro pack. A spec that fails the normal checks, uses a
    tool outside PACK_ALLOWED_TOOLS, opens a non-web target, or claims a phrase one of Jarvis's own commands
    answers (`is_core_phrase`, e.g. "what's urgent", "pause") is skipped whole and logged."""
    out, seen = [], set()
    off = {str(n).strip().lower() for n in disabled}
    for spec in specs or []:
        if not isinstance(spec, dict):
            continue
        name = str(spec.get("name") or "").strip()[:60]
        phrases, steps = spec.get("phrases"), spec.get("steps")
        err = validate(name, phrases, steps, known_tools)
        if not err:
            err = next((e for e in (_pack_step_problem(st) for st in steps) if e), None)
        if not err and is_core_phrase:
            core = [p for p in phrases if any(is_core_phrase(v) for v in _phrase_variants(str(p)))]
            if core:
                err = f"phrase {core[0]!r} belongs to one of Jarvis's own commands"
        if err:
            if log:
                log(f"Pro routine {name or '?'!r} skipped: {err}")
            continue
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append({"id": None, "name": name, "pack": True, "enabled": name.lower() not in off,
                    "phrases": sorted({normalize(str(p)) for p in phrases if normalize(str(p))}),
                    "steps": [{"tool": st["tool"], "input": dict(st.get("input") or {})} for st in steps]})
    return out


def match(connect, lock, transcript: str, extra: list[dict] | None = None) -> dict | None:
    """The user's own macros first; then `extra` (Pro pack macros), so a user's phrase always wins."""
    t = normalize(transcript)
    if not t or len(t.split()) > 12:
        return None
    for m in list(list_macros(connect, lock)) + list(extra or []):
        if m["enabled"] and any(normalize(p) == t for p in m["phrases"]):
            return m
    return None


def run(connect, lock, macro: dict, execute: Callable[[str, dict], str],
        staged: Callable[[str], bool] | None = None) -> str:
    """Runs the steps in order; stops at a step whose result is a staged confirmation or a failure."""
    done, stopped, spoken = [], False, []
    for i, s in enumerate(macro["steps"], 1):
        result = execute(s["tool"], dict(s.get("input") or {})) or ""
        if s["tool"] in SPEAK_RESULT_TOOLS and result.strip():
            spoken.append(result.strip())
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
    if macro.get("id") is not None:  # pack macros aren't stored in the table
        _q(connect, lock, "UPDATE macros SET last_run=?, runs=runs+1 WHERE id=?",
           (datetime.now().isoformat(timespec="seconds"), macro["id"]), write=True)
    if stopped:
        return f"Macro {macro['name']} stopped. " + "; ".join(done)
    if macro.get("pack") and spoken:
        # Pro routines exist to tell you something (briefing, plan, weather): say those results.
        return "\n\n".join(spoken)
    return f"Done: {macro['name']}."


# --- suggestions from habits (2026-09-30) ---------------------------------------------------------------
# A command the owner keeps saying, that Jarvis answers with the same tool call(s) every time, is a macro waiting
# to happen: as a macro it runs with no model call (faster, and no quota). Suggestions only ever use low-risk
# tools (the Pro-routine allowlist plus the read-only tools), come from the audit table, and are never created
# without the owner saying so.
_FAILED_START = ("tool failed", "refused", "couldn't", "could not", "error", "unknown", "not available", "mcp tool")


def suggest(connect, lock, safe_tools: set[str], known_tools: set[str], already_fast=None,
            min_count: int = 3, days: int = 30, limit: int = 5, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now()
    since = (now - timedelta(days=days)).isoformat(timespec="seconds")
    try:
        sessions = _q(connect, lock, "SELECT transcript FROM dashboard_sessions WHERE started_at >= ?", (since,))
        audit = _q(connect, lock, "SELECT transcript, tool_name, tool_input, result FROM action_audit "
                                  "WHERE timestamp >= ? ORDER BY id", (since,))
    except Exception:
        return []
    said: dict[str, int] = {}
    for r in sessions:
        t = normalize(str(r.get("transcript") or ""))
        if 2 <= len(t.split()) <= 12:
            said[t] = said.get(t, 0) + 1
    taken = {normalize(p) for m in list_macros(connect, lock) for p in m["phrases"]}
    by_say: dict[str, list[tuple[str, str]]] = {}
    for r in audit:
        if str(r.get("result") or "").lower().startswith(_FAILED_START):
            continue
        by_say.setdefault(normalize(str(r.get("transcript") or "")), []).append(
            (str(r.get("tool_name") or ""), str(r.get("tool_input") or "{}")))
    out = []
    for phrase, n in sorted(said.items(), key=lambda kv: -kv[1]):
        if n < min_count or phrase in RESERVED or phrase in taken or (already_fast and already_fast(phrase)):
            continue
        calls = by_say.get(phrase, [])
        counts: dict[tuple[str, str], int] = {}
        for c in calls:
            counts[c] = counts.get(c, 0) + 1
        # the calls made almost every time (>= 80% of the runs), in the order first seen
        stable = [c for c in dict.fromkeys(calls) if counts[c] >= max(min_count, 0.8 * n)]
        if not stable or len(stable) > 4:
            continue
        if any(t not in safe_tools or t not in known_tools or t in FORBIDDEN_STEP_TOOLS for t, _ in stable):
            continue
        try:
            steps = [{"tool": t, "input": json.loads(i)} for t, i in stable]
        except ValueError:
            continue
        if any(st["tool"] in ("open_url", "play_media") and not str(st["input"].get("url", "")).lower().startswith(
                ("http://", "https://")) for st in steps):
            continue
        out.append({"phrase": phrase, "count": n, "steps": steps,
                    "name": re.sub(r"[^a-z0-9]+", "_", phrase)[:40].strip("_")})
        if len(out) >= limit:
            break
    return out


def handle_tool(connect, lock, inp: dict, known_tools: set[str], attended: bool,
                execute: Callable[[str, dict], str] | None = None, staged=None,
                safe_tools: set[str] | None = None, already_fast=None) -> str:
    action = str(inp.get("action") or "list").lower()
    if action in ("suggest", "accept"):
        sugg = suggest(connect, lock, safe_tools or set(), known_tools, already_fast)
        if action == "suggest":
            if not sugg:
                return "No habits worth a macro yet: I look for a command you said 3+ times that always did the same thing."
            return "\n".join(f"- You said {s['phrase']!r} {s['count']} times; it always ran " +
                             ", ".join(st["tool"] for st in s["steps"]) + f". To keep it: macros accept phrase={s['phrase']!r}"
                             for s in sugg)
        if not attended:
            return "Macros can only be changed from the PC (voice, typed or dashboard), not from here."
        want = normalize(str(inp.get("phrase") or ""))
        pick = next((s for s in sugg if s["phrase"] == want), None)
        if not pick:
            return "That isn't one of the current suggestions (ask for 'suggest' to see them)."
        return save(connect, lock, pick["name"], [pick["phrase"]], pick["steps"], known_tools)
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
