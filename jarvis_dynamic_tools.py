"""Runtime tool creation for Jarvis: the model writes a small Python function, this module checks it,
tests it, stores it, and offers it as a new tool (named dyn_<name>) for the rest of the process and
every later run.

The design choice that matters: a dynamic tool is a *pure computation*, not a new way to touch the
machine. So instead of trying to allow "safe" subprocess/network/file use (which no AST filter can
guarantee), the scanner simply refuses anything that could reach outside the function's own inputs:
  * imports limited to a stdlib allow-list of pure modules (json, re, math, datetime, ...),
  * no eval/exec/compile/open/__import__/getattr/setattr/globals/... and no attribute that starts
    with an underscore (which closes the usual ().__class__.__mro__ escape route),
  * exactly one public entry function, only imports/assignments/helper defs at top level.
Tools run in a separate `python -I` process (10s timeout, output capped, restricted builtins and a
restricted __import__), so a bug or infinite loop cannot hang or crash Jarvis. If a task needs the
network, files or the shell, the model should use the existing tools; it cannot smuggle them in here.

Self-contained like the other jarvis_*.py modules: own tables in jarvis_memory.db (dynamic_tools,
dynamic_tool_events), own _db_path()/_db_lock/_connect(), no import of jarvis.py. jarvis.py calls
init_dynamic_tools() at startup, appends schemas() to the tool list, and routes dyn_* calls to run().

Limits and controls: JARVIS_DYNAMIC_TOOLS_PER_DAY (default 3) creations per day (deletions do not
refund the budget), JARVIS_DYNAMIC_TOOLS_DRY_RUN=1 (validate and test but never register),
JARVIS_DYNAMIC_TOOLS_DISABLED=1 (no dynamic tools at all: none created, none advertised, none run).
Each stored tool is re-hashed and re-scanned every time it is loaded, so an edited database row is
rejected instead of run.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

log = logging.getLogger("jarvis.dynamic_tools")

TOOL_PREFIX = "dyn_"
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,39}$")
MAX_CODE_CHARS = 8000
RUN_TIMEOUT_S = 10
MAX_OUTPUT_CHARS = 20000

ALLOWED_IMPORTS = frozenset({
    "json", "re", "math", "cmath", "statistics", "datetime", "time", "random", "collections", "itertools",
    "functools", "string", "textwrap", "hashlib", "base64", "decimal", "fractions", "uuid", "typing",
    "operator", "bisect", "heapq", "calendar", "unicodedata", "difflib", "html", "urllib.parse", "enum",
    "dataclasses", "numbers", "zlib", "colorsys",
})
BLOCKED_NAMES = frozenset({
    "eval", "exec", "compile", "open", "__import__", "input", "breakpoint", "globals", "locals", "vars",
    "getattr", "setattr", "delattr", "dir", "help", "exit", "quit", "memoryview", "type", "super",
    "classmethod", "staticmethod", "property", "object", "bytearray",
})
BLOCKED_ATTRS = frozenset({"format_map", "gi_frame", "f_globals", "f_locals", "tb_frame", "co_code"})
_SCHEMA_TYPES = {"str": "string", "int": "integer", "float": "number", "bool": "boolean",
                 "list": "array", "dict": "object"}

_db_lock = threading.Lock()
_registry: dict[str, dict] = {}
_registry_lock = threading.Lock()


def _db_path() -> Path:
    override = (os.environ.get("JARVIS_MEMORY_DB_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent / "jarvis_memory.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS dynamic_tools ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, description TEXT NOT NULL, "
        "code_hash TEXT NOT NULL, code_text TEXT NOT NULL, schema_json TEXT NOT NULL, "
        "created_at TEXT NOT NULL, last_used_at TEXT, is_enabled INTEGER NOT NULL DEFAULT 1)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS dynamic_tool_events ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, event TEXT NOT NULL, name TEXT, detail TEXT)"
    )
    return conn


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def disabled() -> bool:
    return (os.environ.get("JARVIS_DYNAMIC_TOOLS_DISABLED") or "").strip().lower() in ("1", "true", "yes")


def _dry_run_env() -> bool:
    return (os.environ.get("JARVIS_DYNAMIC_TOOLS_DRY_RUN") or "").strip().lower() in ("1", "true", "yes")


def _per_day() -> int:
    try:
        return int((os.environ.get("JARVIS_DYNAMIC_TOOLS_PER_DAY") or "3").strip())
    except ValueError:
        return 3


def _event(event: str, name: str, detail: str = "") -> None:
    with _db_lock:
        conn = _connect()
        try:
            conn.execute("INSERT INTO dynamic_tool_events (ts, event, name, detail) VALUES (?, ?, ?, ?)",
                         (_now(), event, name, detail[:500]))
            conn.commit()
        finally:
            conn.close()


def created_today() -> int:
    day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
    with _db_lock:
        conn = _connect()
        try:
            return conn.execute("SELECT COUNT(*) FROM dynamic_tool_events WHERE event='created' AND ts>=?",
                                (day,)).fetchone()[0]
        finally:
            conn.close()


# ------------------------------------------------------------------------------------- the scanner
def scan_code(code: str, name: str) -> tuple[ast.Module | None, str | None]:
    """(tree, None) if the code is acceptable, else (None, reason)."""
    if not code or not code.strip():
        return None, "No code given."
    if len(code) > MAX_CODE_CHARS:
        return None, f"Code is over {MAX_CODE_CHARS} characters; keep a dynamic tool small."
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return None, f"Syntax error: {e.msg} (line {e.lineno})."
    entry = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(entry) != 1:
        return None, f"The code must define exactly one top-level function named {name!r}."
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.Assign, ast.AnnAssign)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue  # a docstring
        return None, f"Top level may only hold imports, assignments and function definitions (line {node.lineno})."
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name not in ALLOWED_IMPORTS:
                    return None, f"Import of {a.name!r} is not allowed (pure-computation modules only)."
        elif isinstance(node, ast.ImportFrom):
            if node.level or (node.module or "") not in ALLOWED_IMPORTS or any(a.name == "*" for a in node.names):
                return None, f"Import from {node.module!r} is not allowed."
        elif isinstance(node, ast.Name):
            if node.id in BLOCKED_NAMES or node.id.startswith("__"):
                return None, f"Use of {node.id!r} is not allowed."
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("_") or node.attr in BLOCKED_ATTRS:
                return None, f"Access to attribute {node.attr!r} is not allowed."
        elif isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.AsyncFor, ast.AsyncWith, ast.Global,
                               ast.Nonlocal, ast.ClassDef)):
            return None, f"{type(node).__name__} is not allowed."
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and "__" in node.value:
            # blocks "{0.__class__}".format(...) style attribute access through format strings
            return None, "Strings containing '__' are not allowed."
    return tree, None


def derive_schema(tree: ast.Module, name: str, description: str) -> dict:
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    props: dict[str, dict] = {}
    required: list[str] = []
    args = fn.args
    positional = args.posonlyargs + args.args
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    for a, d in list(zip(positional, defaults)) + list(zip(args.kwonlyargs, args.kw_defaults)):
        ann = a.annotation.id if isinstance(a.annotation, ast.Name) else "str"
        props[a.arg] = {"type": _SCHEMA_TYPES.get(ann, "string")}
        if d is None:
            required.append(a.arg)
    return {"name": TOOL_PREFIX + name, "description": description[:600],
            "input_schema": {"type": "object", "properties": props, "required": required}}


# ---------------------------------------------------------------------------------------- the runner
_RUNNER = r'''
import sys, json, builtins
req = json.loads(sys.stdin.read())
ALLOWED = set(req["allowed"])
_real_import = builtins.__import__
def _imp(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name not in ALLOWED:
        raise ImportError("import not allowed: " + name)
    return _real_import(name, globals, locals, fromlist, level)
SAFE = "abs all any bool bytes chr dict divmod enumerate filter float format frozenset hash int isinstance issubclass iter len list map max min next ord pow print range repr reversed round set slice sorted str sum tuple zip Exception ValueError TypeError KeyError IndexError ZeroDivisionError StopIteration ArithmeticError RuntimeError AttributeError OverflowError".split()
b = {k: getattr(builtins, k) for k in SAFE}
b["__import__"] = _imp
g = {"__builtins__": b, "__name__": "dynamic_tool"}
exec(compile(req["code"], "<dynamic_tool>", "exec"), g)
out = g[req["name"]](**req["args"])
sys.stdout.write("\x00RESULT" + json.dumps(out, default=str))
'''


def _run_sandboxed(code: str, name: str, args: dict) -> tuple[bool, str]:
    payload = json.dumps({"code": code, "name": name, "args": args or {}, "allowed": sorted(ALLOWED_IMPORTS)})
    try:
        proc = subprocess.run([sys.executable, "-I", "-c", _RUNNER], input=payload, capture_output=True,
                              text=True, timeout=RUN_TIMEOUT_S,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return False, f"Timed out after {RUN_TIMEOUT_S}s."
    except Exception as e:
        return False, f"Could not run: {e}"
    if proc.returncode != 0:
        lines = (proc.stderr or "").strip().splitlines()
        return False, (lines[-1] if lines else "failed")[:300]
    out = proc.stdout or ""
    if "\x00RESULT" not in out:
        return False, "Tool produced no result."
    return True, out.split("\x00RESULT", 1)[1][:MAX_OUTPUT_CHARS]


def _run_tests(code: str, name: str, tests: list | None) -> str | None:
    """None if all pass; otherwise the first failure."""
    for i, t in enumerate(tests or [], 1):
        if not isinstance(t, dict):
            return f"Test {i} must be an object with 'args' and 'expect'."
        ok, out = _run_sandboxed(code, name, t.get("args") or {})
        if not ok:
            return f"Test {i} errored: {out}"
        if "expect" in t:
            try:
                got = json.loads(out)
            except json.JSONDecodeError:
                return f"Test {i} returned non-JSON output."
            if got != t["expect"]:
                return f"Test {i} expected {t['expect']!r} but got {got!r}."
    return None


# ---------------------------------------------------------------------------------------- registry
def init_dynamic_tools() -> int:
    """Creates tables and loads every enabled stored tool, re-verifying its hash and re-scanning it.
    Returns how many are live."""
    with _db_lock:
        conn = _connect()
        try:
            rows = [dict(r) for r in conn.execute("SELECT * FROM dynamic_tools").fetchall()]
        finally:
            conn.close()
    live: dict[str, dict] = {}
    if not disabled():
        for r in rows:
            if not r["is_enabled"]:
                continue
            if hashlib.sha256(r["code_text"].encode()).hexdigest() != r["code_hash"]:
                log.warning("Dynamic tool %s failed its integrity check; not loading.", r["name"])
                _event("rejected_on_load", r["name"], "hash mismatch")
                continue
            _, reason = scan_code(r["code_text"], r["name"])
            if reason:
                log.warning("Dynamic tool %s no longer passes the scanner (%s); not loading.", r["name"], reason)
                _event("rejected_on_load", r["name"], reason)
                continue
            live[r["name"]] = r
    with _registry_lock:
        _registry.clear()
        _registry.update(live)
    return len(live)


def schemas() -> list[dict]:
    """Tool definitions for the model, sorted so the tool prefix (and its prompt cache) is stable."""
    if disabled():
        return []
    with _registry_lock:
        return [json.loads(r["schema_json"]) for _, r in sorted(_registry.items())]


def is_dynamic(tool_name: str) -> bool:
    return tool_name.startswith(TOOL_PREFIX) and tool_name[len(TOOL_PREFIX):] in _registry


def run(tool_name: str, inp: dict) -> str:
    name = tool_name[len(TOOL_PREFIX):] if tool_name.startswith(TOOL_PREFIX) else tool_name
    with _registry_lock:
        row = _registry.get(name)
    if disabled() or row is None:
        return f"Dynamic tool {name!r} is not available."
    ok, out = _run_sandboxed(row["code_text"], name, inp or {})
    with _db_lock:
        conn = _connect()
        try:
            conn.execute("UPDATE dynamic_tools SET last_used_at=? WHERE name=?", (_now(), name))
            conn.commit()
        finally:
            conn.close()
    return out if ok else f"Dynamic tool {name} failed: {out}"


def create_tool(code_string: str, name: str, description: str, tests: list | None = None,
                dry_run: bool = False, reserved_names: set[str] | None = None) -> str:
    """Validate -> test -> (unless dry-run) persist and register. Never raises."""
    name = (name or "").strip()
    if disabled():
        return "Dynamic tool creation is disabled (JARVIS_DYNAMIC_TOOLS_DISABLED)."
    if not NAME_RE.match(name):
        return "Tool name must be lowercase letters, digits and underscores, 3-40 chars, starting with a letter."
    if (TOOL_PREFIX + name) in (reserved_names or set()) or name in (reserved_names or set()):
        return f"{name!r} collides with an existing tool."
    if not (description or "").strip():
        return "A description is required so the model knows when to use the tool."
    tree, reason = scan_code(code_string, name)
    if reason:
        _event("rejected", name, reason)
        return f"Rejected by the safety scan: {reason}"
    failure = _run_tests(code_string, name, tests)
    if failure:
        _event("test_failed", name, failure)
        return f"Tests failed, tool not created: {failure}"
    if dry_run or _dry_run_env():
        _event("dry_run", name, "passed")
        return f"Dry run: {name} passes the safety scan and {len(tests or [])} test(s). Nothing was registered."
    with _registry_lock:
        exists = name in _registry
    if created_today() >= _per_day() and not exists:
        return f"Daily limit of {_per_day()} new dynamic tools reached; try again tomorrow."
    schema = derive_schema(tree, name, description)
    code_hash = hashlib.sha256(code_string.encode()).hexdigest()
    with _db_lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO dynamic_tools (name, description, code_hash, code_text, schema_json, created_at, is_enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, 1) ON CONFLICT(name) DO UPDATE SET description=excluded.description, "
                "code_hash=excluded.code_hash, code_text=excluded.code_text, schema_json=excluded.schema_json, "
                "is_enabled=1",
                (name, description.strip(), code_hash, code_string, json.dumps(schema), _now()))
            conn.commit()
        finally:
            conn.close()
    _event("created", name, f"hash {code_hash[:12]}")
    init_dynamic_tools()
    return f"Created tool {TOOL_PREFIX}{name} ({len(tests or [])} test(s) passed). It is available now and after restarts."


def list_tools() -> list[dict]:
    with _db_lock:
        conn = _connect()
        try:
            rows = conn.execute("SELECT id, name, description, code_hash, created_at, last_used_at, is_enabled "
                                "FROM dynamic_tools ORDER BY id").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_code(name: str) -> str | None:
    with _db_lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT code_text FROM dynamic_tools WHERE name=?", (name,)).fetchone()
            return row["code_text"] if row else None
        finally:
            conn.close()


def set_enabled(name: str, on: bool) -> str:
    with _db_lock:
        conn = _connect()
        try:
            n = conn.execute("UPDATE dynamic_tools SET is_enabled=? WHERE name=?", (1 if on else 0, name)).rowcount
            conn.commit()
        finally:
            conn.close()
    if not n:
        return f"No dynamic tool named {name!r}."
    _event("enabled" if on else "disabled", name)
    init_dynamic_tools()
    return f"Tool {name} {'enabled' if on else 'disabled'}."


def revoke(name: str) -> str:
    with _db_lock:
        conn = _connect()
        try:
            n = conn.execute("DELETE FROM dynamic_tools WHERE name=?", (name,)).rowcount
            conn.commit()
        finally:
            conn.close()
    if not n:
        return f"No dynamic tool named {name!r}."
    _event("revoked", name)
    init_dynamic_tools()
    return f"Tool {name} revoked and deleted."


def handle_manage(inp: dict) -> str:
    action = str(inp.get("action") or "list").lower()
    name = str(inp.get("name") or "").strip()
    if action == "list":
        rows = list_tools()
        return "\n".join(f"{r['name']} ({'on' if r['is_enabled'] else 'off'}): {r['description'][:80]}" for r in rows) \
            or "No dynamic tools yet."
    if action == "enable":
        return set_enabled(name, True)
    if action == "disable":
        return set_enabled(name, False)
    if action == "revoke":
        return revoke(name)
    return f"Unknown action {action!r}."


def test_dynamic_tool_creation() -> dict:
    """Manual hook: exercises the scanner and sandbox with a good tool and several hostile ones,
    without storing anything. Returns {case: result}."""
    good = "def add_numbers(a: int, b: int) -> int:\n    return a + b\n"
    cases = {
        "good": scan_code(good, "add_numbers")[1] is None
                and _run_tests(good, "add_numbers", [{"args": {"a": 2, "b": 3}, "expect": 5}]) is None,
        "eval": scan_code("def f(x):\n    return eval(x)\n", "f")[1] is not None,
        "os_import": scan_code("import os\ndef f():\n    return os.getcwd()\n", "f")[1] is not None,
        "subprocess": scan_code("import subprocess\ndef f():\n    return 1\n", "f")[1] is not None,
        "dunder_escape": scan_code("def f():\n    return ().__class__.__mro__\n", "f")[1] is not None,
        "open": scan_code("def f():\n    return open('x').read()\n", "f")[1] is not None,
        "top_level_call": scan_code("print(1)\ndef f():\n    return 1\n", "f")[1] is not None,
    }
    return cases
