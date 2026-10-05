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

Instant or AI (2026-10-03, owner: "every macro/skill I make should run instantly, no AI call - unless it needs the AI"):
`classify` reads what the routine is for and its steps, and decides by itself. Fixed tool calls (open an app, volume,
weather, a git pull) run instantly with no model call; anything that needs thinking (summarise, decide, "tell me if",
write or reply) is saved with mode 'ai': saying its phrase sends its instructions to the AI, so it still works. Nobody is
asked. Every step is checked against its tool's real parameters when the routine is made, so a step that could never
work (the "update time" macro that called a tool without its required action) is refused up front, and a step that
fails at run time is reported, never "Done".
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
            "turn on safe mode", "turn off safe mode", "yes", "no", "cancel",
            # built-in "update and restart" (2026-10-03): it checks the pull worked before restarting
            "update time", "time to update", "update yourself", "update jarvis", "update and restart",
            "pull and restart", "git pull and restart", "its update time"}
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
    cols = {r[1] for r in conn.execute("PRAGMA table_info(macros)")}
    if "mode" not in cols:  # 2026-10-03: instant (fixed steps, no AI) or ai (instructions go to the AI)
        conn.execute("ALTER TABLE macros ADD COLUMN mode TEXT NOT NULL DEFAULT 'instant'")
    if "instructions" not in cols:
        conn.execute("ALTER TABLE macros ADD COLUMN instructions TEXT")
    if "start_line" not in cols:  # 2026-10-05: what an AI routine says the moment it starts
        conn.execute("ALTER TABLE macros ADD COLUMN start_line TEXT")


# What makes a routine need the AI: words asking it to think, judge, write or pick, rather than do a fixed thing.
_NEEDS_AI_RE = re.compile(
    r"\b(?:summari[sz]e|summary|explain|decide|decision|whether|compare|analy[sz]e|recommend|suggest|advise|"
    r"draft|write (?:a|an|the|me|up|back)|reply to|respond to|answer (?:it|them|the)|translate|figure out|find out|"
    r"work out|pick (?:the|a|one)|choose|the best|most important|important ones?|interesting|relevant|"
    r"tell me (?:if|whether|what|which|why|how|when|about)|let me know (?:if|whether|what)|check (?:if|whether)|"
    r"if (?:it|there|i|my|the|any)\b|unless|depending on|sort out|clean up my|organi[sz]e my|plan my|review|"
    r"read (?:me )?(?:my|the) (?:emails?|mail|messages?|news))",
    re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"\{[a-z_]+\}|<[A-Za-z _-]{2,30}>|\$\{")


def classify(description: str, instructions: str, steps, check_step=None, known_tools: set[str] | None = None
             ) -> tuple[str, str]:
    """('instant', why) when fixed tool calls can do the whole job with no thinking, else ('ai', why)."""
    text = f"{description or ''} {instructions or ''}"
    if not isinstance(steps, list) or not steps:
        return "ai", "it has no fixed steps, so the AI carries it out"
    hit = _NEEDS_AI_RE.search(text)
    if hit:
        return "ai", f"it needs thinking ('{hit.group(0)}')"
    for i, s in enumerate(steps, 1):
        tool = str((s or {}).get("tool") or "")
        inp = (s or {}).get("input") or {}
        if tool in FORBIDDEN_STEP_TOOLS or (known_tools is not None and tool not in known_tools):
            return "ai", f"step {i} ({tool or 'no tool'}) isn't a tool it can call directly"
        if not isinstance(inp, dict) or _PLACEHOLDER_RE.search(json.dumps(inp)):
            return "ai", f"step {i} ({tool}) has a value that has to be worked out each time"
        if check_step:
            err = check_step(tool, inp)
            if err:
                return "ai", f"step {i} ({tool}) can't run as written: {err}"
    return "instant", "every step is a fixed action"


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
        r["mode"] = r.get("mode") or "instant"
        r["instructions"] = r.get("instructions") or ""
        out.append(r)
    return out


def validate(name: str, phrases, steps, known_tools: set[str], check_step=None, mode: str = "instant") -> str | None:
    if not str(name or "").strip():
        return "A macro needs a name."
    if not isinstance(phrases, list) or not [p for p in phrases if normalize(str(p))]:
        return "A macro needs at least one trigger phrase."
    if any(len(normalize(str(p)).split()) < 2 for p in phrases):
        return "Trigger phrases need at least two words (one word would fire by accident)."
    reserved = [p for p in phrases if normalize(str(p)) in RESERVED]
    if reserved:
        return f"{reserved[0]!r} is one of Jarvis's own commands, so a macro can't use it."
    if mode == "ai":
        return None  # its instructions go to the AI when the phrase is said; steps are only a hint
    if not isinstance(steps, list) or not steps or len(steps) > MAX_STEPS:
        return f"A macro needs 1 to {MAX_STEPS} steps."
    for i, s in enumerate(steps, 1):
        tool = str((s or {}).get("tool") or "")
        if tool in FORBIDDEN_STEP_TOOLS or tool not in known_tools:
            return f"Step tool {tool!r} isn't an existing tool a macro may use."
        if not isinstance(s.get("input") or {}, dict):
            return f"Step {tool!r} input must be an object."
        if check_step:
            err = check_step(tool, s.get("input") or {})
            if err:
                return f"Step {i} ({tool}) wouldn't work: {err}"
    return None


def save(connect, lock, name: str, phrases: list, steps: list, known_tools: set[str], enabled: bool = True,
         instructions: str = "", description: str = "", check_step=None, start_line: str = "") -> str:
    instructions = str(instructions or "").strip()[:2000]
    start_line = re.sub(r"[\x00-\x1f\x7f]+", " ", str(start_line or "")).strip()[:140]
    # The stored name is cut to 60 characters: compare and store that same form, or re-saving a long-named macro
    # found its own phrases "already taken" by itself (audit 2026-10-04).
    name = str(name or "").strip()[:60]
    steps = steps if isinstance(steps, list) else []
    if instructions or description:
        mode, why = classify(description, instructions, steps, check_step, known_tools)
    else:  # only steps given (Toolbox form, accepted suggestion): they must all work as they are
        mode, why = "instant", ""
    if mode == "ai" and not (instructions or description):
        return "Say what the routine should do (instructions), so the AI can carry it out."
    err = validate(name, phrases, steps, known_tools, check_step, mode)
    if err:
        return err
    clean_steps = [{"tool": s["tool"], "input": s.get("input") or {}} for s in steps if isinstance(s, dict) and s.get("tool")]
    clean_phrases = sorted({normalize(str(p)) for p in phrases if normalize(str(p))})
    taken = {p: m["name"] for m in list_macros(connect, lock) if m["name"] != name.strip() for p in m["phrases"]}
    clash = [p for p in clean_phrases if p in taken]
    if clash:
        return f"The phrase {clash[0]!r} already triggers the macro {taken[clash[0]]!r}."
    _q(connect, lock, "INSERT INTO macros (name, phrases, steps, enabled, created_at, mode, instructions, start_line) "
                      "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET phrases=excluded.phrases, "
                      "steps=excluded.steps, mode=excluded.mode, instructions=excluded.instructions, "
                      "start_line=COALESCE(NULLIF(excluded.start_line, ''), start_line)",  # keeps on/off
       (name.strip()[:60], json.dumps(clean_phrases), json.dumps(clean_steps), int(bool(enabled)),
        datetime.now().isoformat(timespec="seconds"), mode, instructions or str(description or "").strip()[:2000],
        start_line), write=True)
    if mode == "ai":
        return (f"Saved {name.strip()!r}: say {clean_phrases[0]!r} and I'll do it with the AI each time ({why}).")
    return f"Saved macro {name.strip()!r}: say {clean_phrases[0]!r} to run its {len(clean_steps)} step(s) instantly, no AI call."


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
    if t in RESERVED:  # Jarvis's own command (an older macro may still claim the phrase: it no longer wins)
        return None
    for m in list(list_macros(connect, lock)) + list(extra or []):
        if m["enabled"] and any(normalize(p) == t for p in m["phrases"]):
            return m
    return None


_EXIT_RE = re.compile(r"^\s*exit_code=(-?\d+)")
_QUIET_RESULTS = {"done", "done.", "ok", "ok.", "opened.", ""}


def _step_failed(result: str, failed=None) -> bool:
    r = (result or "").strip()
    m = _EXIT_RE.match(r)
    if m:
        return m.group(1) != "0"  # a shell command that exited with an error
    return r.lower().startswith(("tool failed", "unrecognized tool")) or bool(failed and failed(r))


def short_result(tool: str, result: str) -> str:
    """One short spoken line for a step's result ('' when there's nothing worth saying)."""
    r = " ".join(str(result or "").split())
    if _EXIT_RE.match(r) or r.lower() in _QUIET_RESULTS:
        return ""  # shell output isn't speech; success is said by the overall "Done"
    r = re.sub(r"\s*\[verified:[^\]]*\]", "", r)
    if len(r) <= 160:
        return r
    cut = re.search(r"^(.{40,200}?[.!?])\s", r)
    return cut.group(1) if cut else r[:157].rstrip() + "..."


def run(connect, lock, macro: dict, execute: Callable[[str, dict], str],
        staged: Callable[[str], bool] | None = None, failed: Callable[[str], bool] | None = None) -> str:
    """Runs the steps in order; stops at a step whose result is a staged confirmation or a failure.
    Says a short line per step that told something, 'Done.' when none did, and which step failed when one did."""
    done, stopped, spoken, lines = [], False, [], []
    for i, s in enumerate(macro["steps"], 1):
        result = execute(s["tool"], dict(s.get("input") or {})) or ""
        if s["tool"] in SPEAK_RESULT_TOOLS and result.strip():
            spoken.append(result.strip())
        if staged and staged(result):
            done.append(f"step {i} ({s['tool']}) needs your confirmation: {result}")
            stopped = True
        elif _step_failed(result, failed):
            done.append(f"step {i} ({s['tool']}) failed: {short_result(s['tool'], result) or result[:160]}")
            stopped = True
        else:
            done.append(f"{s['tool']}: {result[:160]}")
            line = short_result(s["tool"], result)
            if line:
                lines.append(line)
        if stopped:
            break
    if macro.get("id") is not None:  # pack macros aren't stored in the table
        _q(connect, lock, "UPDATE macros SET last_run=?, runs=runs+1 WHERE id=?",
           (datetime.now().isoformat(timespec="seconds"), macro["id"]), write=True)
    if stopped:
        return f"{macro['name']} stopped at " + done[-1] + (". Before that: " + "; ".join(lines) if lines else "")
    if macro.get("pack") and spoken:
        # Pro routines exist to tell you something (briefing, plan, weather): say those results.
        return "\n\n".join(spoken)
    return " ".join(lines) if lines else "Done."


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
        if any(t in SPEAK_RESULT_TOOLS for t, _ in stable):
            continue  # asked for the ANSWER (weather, status...): a user macro only says "Done", which would be a downgrade
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
                safe_tools: set[str] | None = None, already_fast=None, check_step=None, failed=None) -> str:
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
        return save(connect, lock, pick["name"], [pick["phrase"]], pick["steps"], known_tools, check_step=check_step)
    if action == "list":
        ms = list_macros(connect, lock)
        return "\n".join(f"- {m['name']}{'' if m['enabled'] else ' (off)'}: say " +
                         " / ".join(repr(p) for p in m["phrases"]) + " -> " +
                         ("(with the AI) " + m["instructions"][:120] if m["mode"] == "ai" else
                          ", ".join(s["tool"] for s in m["steps"]) + " (instant)") for m in ms) or "No macros yet."
    if action in ("create", "delete", "enable", "disable") and not attended:
        return "Macros can only be changed from the PC (voice, typed or dashboard), not from here."
    if action == "create":
        phrases = inp.get("phrases") or ([inp["phrase"]] if inp.get("phrase") else [])
        return save(connect, lock, str(inp.get("name") or ""), phrases, inp.get("steps") or [],
                    known_tools, instructions=str(inp.get("instructions") or ""),
                    description=str(inp.get("description") or ""), check_step=check_step,
                    start_line=str(inp.get("start_line") or ""))
    if action == "delete":
        return "Deleted." if delete(connect, lock, str(inp.get("name") or "")) else "No macro by that name."
    if action in ("enable", "disable"):
        return "Done." if set_enabled(connect, lock, str(inp.get("name") or ""), action == "enable") else \
            "No macro by that name."
    if action == "run" and execute:
        m = next((m for m in list_macros(connect, lock) if m["name"] == str(inp.get("name") or "").strip()), None)
        if m and m["mode"] == "ai":
            return f"{m['name']} runs with the AI: say {m['phrases'][0]!r} to run it."
        return run(connect, lock, m, execute, staged, failed) if m else "No macro by that name."
    return "Unknown macro action."
