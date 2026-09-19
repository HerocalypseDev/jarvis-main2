"""Roblox Game Dev Companion: watches Roblox Studio and reviews Lua/Luau scripts.

Everything is local and read-only. Monitoring only reads the Studio process's CPU/memory via
psutil; script review is a static pattern scan of .lua/.luau files under a folder the user names
(e.g. a Rojo project). It never edits scripts, it only suggests. Findings are keyword/regex
heuristics, not a Luau type checker, so treat them as hints.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path

log = logging.getLogger("jarvis")

STUDIO_PROCESS = "robloxstudiobeta.exe"
CPU_LIMIT = 85.0
MEM_LIMIT_MB = 6000
SUSTAINED_CHECKS = 3
CHECK_INTERVAL_S = 60
MAX_FILES = 200
MAX_FILE_BYTES = 500_000

_lock = threading.Lock()
_state: dict = {"active": False, "project": None, "high": 0, "last": 0.0, "reviewed": {}}

# (regex, suggestion). Applied per line; comments are stripped first.
_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?<![\w.:])wait\s*\("), "wait() is deprecated and throttled; use task.wait()."),
    (re.compile(r"(?<![\w.:])spawn\s*\("), "spawn() is deprecated; use task.spawn() or task.defer()."),
    (re.compile(r"(?<![\w.:])delay\s*\("), "delay() is deprecated; use task.delay()."),
    (re.compile(r":connect\s*\("), "lowercase :connect is deprecated; use :Connect()."),
    (re.compile(r"\bgame\.Workspace\b"), "use the global `workspace` instead of game.Workspace."),
    (re.compile(r"Instance\.new\([^)]*,\s*[\w.]+\s*\)"),
     "Instance.new(class, parent) is slow; set properties first and parent last."),
    (re.compile(r"while\s+true\s+do"), "while true do loops: make sure they yield (task.wait) and consider events instead of polling."),
    (re.compile(r"\.Heartbeat:Connect|RenderStepped:Connect"),
     "per-frame connection: keep the handler light, cache lookups outside it, disconnect when unused."),
    (re.compile(r"GetChildren\(\)|GetDescendants\(\)"),
     "GetChildren/GetDescendants allocate a table; avoid in hot paths, cache the result or use events."),
    (re.compile(r"FindFirstChild\([^)]*\)\s*\.\s*\w+"),
     "FindFirstChild result used without a nil check; guard it or use WaitForChild."),
    (re.compile(r"\bTouched:Connect"),
     "Touched fires very often; add a debounce and filter by the hit part early."),
]
_LOOP_HEAD = re.compile(r"^\s*(for\b.*\bdo|while\b.*\bdo|repeat\b)")
_CONCAT_IN_LOOP = re.compile(r"\w+\s*=\s*\w+\s*\.\.")


def _strip_comment(line: str) -> str:
    return line.split("--", 1)[0] if "--" in line else line


def review_source(text: str, name: str = "script") -> list[str]:
    """Findings for one script's text, as 'name:line: suggestion'."""
    out: list[str] = []
    loop_depth = 0
    for i, raw in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw)
        if _LOOP_HEAD.match(line):
            loop_depth += 1
        elif re.match(r"^\s*until\b", line) or (loop_depth and re.match(r"^\s*end\b", line)):
            loop_depth = max(0, loop_depth - 1)
        for pat, tip in _RULES:
            if pat.search(line):
                out.append(f"{name}:{i}: {tip}")
        if loop_depth and _CONCAT_IN_LOOP.search(line):
            out.append(f"{name}:{i}: string concatenation in a loop; collect pieces in a table and table.concat.")
    return out


def review_folder(folder: str, limit: int = 15) -> str:
    root = Path(folder).expanduser()
    if not root.is_dir():
        return f"{folder} is not a folder."
    files = [
        p for p in root.rglob("*")
        if p.suffix.lower() in (".lua", ".luau") and not any(s in p.parts for s in (".git", "Packages", "node_modules"))
    ][:MAX_FILES]
    findings: list[str] = []
    for p in files:
        try:
            if p.stat().st_size > MAX_FILE_BYTES:
                continue
            findings += review_source(p.read_text(encoding="utf-8", errors="replace"), str(p.relative_to(root)))
        except OSError:
            continue
    if not files:
        return f"No .lua or .luau files under {folder}."
    if not findings:
        return f"Reviewed {len(files)} scripts; nothing suspicious found."
    shown = "\n".join(findings[:limit])
    more = f"\n...and {len(findings) - limit} more." if len(findings) > limit else ""
    return f"Reviewed {len(files)} scripts, {len(findings)} suggestions:\n{shown}{more}"


def studio_stats() -> dict | None:
    """CPU/memory of running Roblox Studio processes, or None if it isn't running."""
    try:
        import psutil

        procs = [p for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == STUDIO_PROCESS]
        if not procs:
            return None
        cpu = sum(p.cpu_percent(interval=0.2) for p in procs) / (psutil.cpu_count() or 1)
        mem = sum(p.memory_info().rss for p in procs) / 1_048_576
        return {"cpu_percent": round(cpu, 1), "memory_mb": round(mem)}
    except Exception as e:
        log.debug("Studio stats failed: %s", e)
        return None


def performance_flag(stats: dict | None) -> str | None:
    if not stats:
        return None
    if stats["cpu_percent"] >= CPU_LIMIT:
        return f"Roblox Studio is using {stats['cpu_percent']}% CPU."
    if stats["memory_mb"] >= MEM_LIMIT_MB:
        return f"Roblox Studio is using {stats['memory_mb']} MB of memory."
    return None


def start(project: str | None = None) -> str:
    with _lock:
        _state.update(active=True, project=project or _state.get("project"), high=0, last=0.0)
    where = f" and reviewing scripts in {_state['project']}" if _state["project"] else ""
    return f"Roblox companion on: watching Studio's CPU and memory{where}."


def stop() -> str:
    with _lock:
        _state.update(active=False, high=0)
    return "Roblox companion off."


def status() -> str:
    stats = studio_stats()
    head = "Roblox companion is " + ("on" if _state["active"] else "off")
    if not stats:
        return head + "; Roblox Studio isn't running."
    return f"{head}; Studio at {stats['cpu_percent']}% CPU, {stats['memory_mb']} MB."


def tick(notify) -> None:
    """Scheduler hook. Flags sustained load (3 checks in a row) and, once per changed script
    set, adds the top Lua suggestions. Non-urgent, so Focus/Sleep Mode still queue it."""
    if not _state["active"] or time.time() - _state["last"] < CHECK_INTERVAL_S:
        return
    _state["last"] = time.time()
    flag = performance_flag(studio_stats())
    _state["high"] = _state["high"] + 1 if flag else 0
    if flag and _state["high"] == SUSTAINED_CHECKS:
        msg = flag + " It's been high for a few minutes."
        proj = _state.get("project")
        if proj:
            msg += " " + review_folder(proj, limit=3).split("\n", 1)[-1].replace("\n", " ")
        notify(msg)
