"""Deep technical understanding helpers for Jarvis.

Three independent capabilities, each usable on its own:
  - parse_error: turns a raw error message/traceback (Python or JS/Node, or a generic
    "Error: ..." line) into a structured explanation — error type, likely causes, and
    concrete next steps — instead of Jarvis just reading the raw text back.
  - analyze_python_file: AST-based structural analysis of a single Python file (functions,
    classes, long-function/complexity/docstring flags) — cheap, no external linter needed.
  - trace_dependencies: builds an import graph across a Python project directory and answers
    "what does X import" / "what imports X", for tracing multi-file dependencies.
"""

from __future__ import annotations

import ast
import logging
import os
import re
from pathlib import Path

log = logging.getLogger("jarvis.tech_understanding")

MAX_RESULT_CHARS = 4000
MAX_FILES_WALKED = 800

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}

# --- error message parsing ---------------------------------------------------------------

_PY_FRAME_RE = re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>\S+)')
_PY_EXC_RE = re.compile(r"^(?P<type>[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Warning))"
                         r"(?:: (?P<msg>.*))?$", re.M)
_JS_FRAME_RE = re.compile(r"at\s+(?P<func>\S+)?\s*\(?(?P<file>[^\s()]+):(?P<line>\d+):(?P<col>\d+)\)?")
_JS_EXC_RE = re.compile(r"^(?P<type>[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))"
                         r"(?:: (?P<msg>.*))?$", re.M)
_HTTP_STATUS_RE = re.compile(r"\b(4\d{2}|5\d{2})\b")

_PY_EXPLANATIONS: dict[str, tuple[str, str]] = {
    "KeyError": (
        "code indexed a dict with a key that isn't present.",
        "check the key actually exists (dict.get with a default, or `in` before indexing).",
    ),
    "AttributeError": (
        "code called a method/attribute an object doesn't have — often None where a real "
        "object was expected, or a typo'd name.",
        "print/inspect the object's actual type just before the failing line.",
    ),
    "TypeError": (
        "an operation got a value of the wrong type (wrong argument count, None where a "
        "callable/number was expected, mixing types in an operator).",
        "check the exact types of everything on the failing line.",
    ),
    "ImportError": (
        "a name couldn't be imported from a module that was otherwise found.",
        "confirm the name exists in that module/version and there's no circular import.",
    ),
    "ModuleNotFoundError": (
        "a module isn't installed, or isn't on sys.path.",
        "pip install the package, or check you're in the right virtualenv.",
    ),
    "FileNotFoundError": (
        "code tried to open/read a path that doesn't exist from the process's working directory.",
        "print the resolved absolute path and confirm the working directory assumption.",
    ),
    "IndexError": (
        "a sequence was indexed past its length (often an off-by-one, or an empty list).",
        "check the collection's length before indexing, or use a safe default.",
    ),
    "ZeroDivisionError": (
        "a division or modulo by zero.",
        "guard the denominator, or check why it's zero at that point.",
    ),
    "RecursionError": (
        "a function recursed past Python's stack limit — usually a missing/broken base case.",
        "verify the recursive call always makes progress toward the base case.",
    ),
    "PermissionError": (
        "the OS denied access to a file/resource for the current user.",
        "check file permissions/ownership, or whether another process has it locked.",
    ),
    "ConnectionError": (
        "a network connection failed (refused, reset, or unreachable).",
        "confirm the target host/port is up and reachable from this machine.",
    ),
    "TimeoutError": (
        "an operation didn't complete within its allotted time.",
        "check network/service health, or whether the timeout itself is too short.",
    ),
    "JSONDecodeError": (
        "text that was expected to be valid JSON wasn't.",
        "log the raw text before parsing — it's often an HTML error page or empty body.",
    ),
    "ValueError": (
        "a value had the right type but an inappropriate value (bad format, out of range).",
        "check the exact value that reached the failing call.",
    ),
    "NameError": (
        "code referenced a name that was never defined/imported in that scope.",
        "check for a typo, a missing import, or a variable used before assignment.",
    ),
}

_JS_EXPLANATIONS: dict[str, tuple[str, str]] = {
    "TypeError": (
        "an operation was performed on a value of the wrong type (often undefined/null).",
        "check whether the value is undefined/null right before the failing line.",
    ),
    "ReferenceError": (
        "code referenced a variable that isn't defined in scope.",
        "check for a typo or a missing declaration/import.",
    ),
    "SyntaxError": (
        "the parser hit invalid JS/TS syntax.",
        "check the exact line/column reported for a stray character or mismatched bracket.",
    ),
    "RangeError": (
        "a value was outside its allowed range (e.g. array length, recursion depth).",
        "check the value feeding the failing call.",
    ),
}

_HTTP_EXPLANATIONS: dict[str, str] = {
    "400": "Bad Request — the request itself was malformed (bad params/body).",
    "401": "Unauthorized — missing or invalid credentials.",
    "403": "Forbidden — authenticated but not permitted to do this.",
    "404": "Not Found — the URL/resource doesn't exist (or a routing mismatch).",
    "408": "Request Timeout.",
    "409": "Conflict — the request clashes with the resource's current state.",
    "422": "Unprocessable Entity — request was well-formed but semantically invalid.",
    "429": "Too Many Requests — rate limited.",
    "500": "Internal Server Error — the server itself failed; check server-side logs.",
    "502": "Bad Gateway — an upstream server returned an invalid response.",
    "503": "Service Unavailable — the server is overloaded or down for maintenance.",
    "504": "Gateway Timeout — an upstream server didn't respond in time.",
}


def parse_error(error_text: str) -> dict:
    """Classifies a raw error message/traceback and returns a structured explanation.
    Handles Python tracebacks, JS/Node stack traces, and bare HTTP status codes; falls
    back to a generic 'unrecognized format' result rather than raising."""
    text = (error_text or "").strip()
    if not text:
        return {"language": None, "error_type": None, "message": "", "frames": [],
                "likely_cause": None, "suggested_fix": None}

    frames = [m.groupdict() for m in _PY_FRAME_RE.finditer(text)]
    if frames or "Traceback (most recent call last)" in text:
        exc_matches = list(_PY_EXC_RE.finditer(text))
        exc = exc_matches[-1] if exc_matches else None
        etype = exc.group("type") if exc else None
        emsg = (exc.group("msg") or "") if exc else ""
        cause, fix = _PY_EXPLANATIONS.get(etype, (None, None))
        return {
            "language": "python",
            "error_type": etype,
            "message": emsg,
            "frames": frames[-5:],
            "likely_cause": cause,
            "suggested_fix": fix,
        }

    js_frames = [m.groupdict() for m in _JS_FRAME_RE.finditer(text)]
    if js_frames:
        exc_matches = list(_JS_EXC_RE.finditer(text))
        exc = exc_matches[0] if exc_matches else None
        etype = exc.group("type") if exc else None
        emsg = (exc.group("msg") or "") if exc else ""
        cause, fix = _JS_EXPLANATIONS.get(etype, (None, None))
        return {
            "language": "javascript",
            "error_type": etype,
            "message": emsg,
            "frames": js_frames[:5],
            "likely_cause": cause,
            "suggested_fix": fix,
        }

    http_match = _HTTP_STATUS_RE.search(text)
    if http_match and ("http" in text.lower() or "status" in text.lower() or "request" in text.lower()):
        code = http_match.group(1)
        return {
            "language": "http",
            "error_type": f"HTTP {code}",
            "message": text[:300],
            "frames": [],
            "likely_cause": _HTTP_EXPLANATIONS.get(code),
            "suggested_fix": None,
        }

    return {
        "language": "unknown",
        "error_type": None,
        "message": text[:300],
        "frames": [],
        "likely_cause": "unrecognized error format — no structured explanation available.",
        "suggested_fix": "share more context (surrounding log lines, the command that produced it).",
    }


def format_error_report(parsed: dict) -> str:
    if not parsed.get("error_type") and parsed.get("language") == "unknown":
        return "Couldn't recognize a structured error in that text — " + (parsed.get("likely_cause") or "")
    lines = []
    lang = parsed.get("language") or "unknown"
    etype = parsed.get("error_type") or "unspecified error"
    lines.append(f"{etype} ({lang})")
    if parsed.get("message"):
        lines.append(f"Message: {parsed['message']}")
    if parsed.get("likely_cause"):
        lines.append(f"Likely cause: {parsed['likely_cause']}")
    if parsed.get("suggested_fix"):
        lines.append(f"Suggested fix: {parsed['suggested_fix']}")
    frames = parsed.get("frames") or []
    if frames:
        last = frames[-1]
        loc = f"{last.get('file')}:{last.get('line')}"
        if last.get("func"):
            loc += f" in {last['func']}"
        lines.append(f"Failure point: {loc}")
    return "\n".join(lines)[:MAX_RESULT_CHARS]


# --- python code structure analysis ------------------------------------------------------

LONG_FUNCTION_LINES = 50
HIGH_COMPLEXITY_BRANCHES = 10


def analyze_python_file(path: str) -> dict:
    """AST-based structural analysis of a single Python file: functions/classes found,
    a rough branch-count complexity per function, and flags for long functions and
    missing docstrings on public (non-underscore) functions/classes."""
    p = Path(path).expanduser()
    try:
        source = p.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return {"error": f"couldn't read {path}: {e}"}
    try:
        tree = ast.parse(source, filename=str(p))
    except SyntaxError as e:
        return {"error": f"syntax error parsing {path}: {e}"}

    functions: list[dict] = []
    classes: list[dict] = []
    flags: list[str] = []

    class _BranchCounter(ast.NodeVisitor):
        def __init__(self):
            self.count = 0

        def visit_If(self, node):
            self.count += 1
            self.generic_visit(node)

        def visit_For(self, node):
            self.count += 1
            self.generic_visit(node)

        def visit_While(self, node):
            self.count += 1
            self.generic_visit(node)

        def visit_Try(self, node):
            self.count += len(node.handlers)
            self.generic_visit(node)

        def visit_BoolOp(self, node):
            self.count += len(node.values) - 1
            self.generic_visit(node)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end_line = getattr(node, "end_lineno", node.lineno)
            n_lines = end_line - node.lineno + 1
            counter = _BranchCounter()
            counter.visit(node)
            has_doc = ast.get_docstring(node) is not None
            entry = {
                "name": node.name,
                "line": node.lineno,
                "lines": n_lines,
                "branch_count": counter.count,
                "has_docstring": has_doc,
            }
            functions.append(entry)
            if n_lines > LONG_FUNCTION_LINES:
                flags.append(f"{node.name} (line {node.lineno}) is {n_lines} lines — consider splitting.")
            if counter.count > HIGH_COMPLEXITY_BRANCHES:
                flags.append(
                    f"{node.name} (line {node.lineno}) has ~{counter.count} branch points — "
                    "high complexity, harder to test/reason about."
                )
            if not has_doc and not node.name.startswith("_"):
                flags.append(f"{node.name} (line {node.lineno}) is public but has no docstring.")
        elif isinstance(node, ast.ClassDef):
            has_doc = ast.get_docstring(node) is not None
            classes.append({"name": node.name, "line": node.lineno, "has_docstring": has_doc})
            if not has_doc and not node.name.startswith("_"):
                flags.append(f"class {node.name} (line {node.lineno}) is public but has no docstring.")

    return {
        "path": str(p),
        "total_lines": len(source.splitlines()),
        "functions": functions,
        "classes": classes,
        "flags": flags,
    }


def format_analysis_report(analysis: dict) -> str:
    if "error" in analysis:
        return analysis["error"]
    lines = [
        f"{analysis['path']}: {analysis['total_lines']} lines, "
        f"{len(analysis['functions'])} function(s), {len(analysis['classes'])} class(es)."
    ]
    if analysis["flags"]:
        lines.append("Flags:")
        lines.extend(f"  - {f}" for f in analysis["flags"][:20])
    else:
        lines.append("No structural flags.")
    return "\n".join(lines)[:MAX_RESULT_CHARS]


# --- dependency tracing --------------------------------------------------------------

def _module_name_for(file_path: Path, root: Path) -> str:
    try:
        rel = file_path.relative_to(root)
    except ValueError:
        rel = file_path
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imports_of(file_path: Path) -> list[str]:
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(file_path))
    except (OSError, SyntaxError):
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def build_import_graph(root_path: str) -> dict[str, list[str]]:
    """Maps each Python module under `root_path` to the list of modules it imports."""
    root = Path(root_path).expanduser().resolve()
    graph: dict[str, list[str]] = {}
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            fp = Path(dirpath) / name
            mod = _module_name_for(fp, root)
            graph[mod] = _imports_of(fp)
            count += 1
            if count >= MAX_FILES_WALKED:
                return graph
    return graph


def trace_dependencies(root_path: str, target: str = "") -> str:
    """Tool entry point: builds the import graph for a Python project and, if `target`
    is given, reports both what it imports and what imports it (reverse lookup)."""
    root = Path(root_path).expanduser()
    if not root.is_dir():
        return f"{root_path!r} is not a directory."
    graph = build_import_graph(str(root))
    if not graph:
        return f"No Python files found under {root_path}."

    if not target:
        lines = [f"{len(graph)} Python module(s) found under {root_path}."]
        top = sorted(graph.items(), key=lambda kv: len(kv[1]), reverse=True)[:10]
        lines.append("Modules with the most imports:")
        lines.extend(f"  - {mod}: {len(imps)} import(s)" for mod, imps in top)
        return "\n".join(lines)[:MAX_RESULT_CHARS]

    target_norm = target.strip()
    matches = [m for m in graph if m == target_norm or m.endswith("." + target_norm) or target_norm in m]
    if not matches:
        return f"No module matching {target!r} found under {root_path}."

    lines = []
    for mod in matches[:5]:
        imports = graph.get(mod, [])
        lines.append(f"{mod} imports: {', '.join(imports) if imports else '(nothing local-looking)'}")
        importers = [
            other for other, imps in graph.items()
            if other != mod and any(i == mod or i.startswith(mod + ".") for i in imps)
        ]
        lines.append(f"{mod} is imported by: {', '.join(importers) if importers else '(nothing else in this tree)'}")
    return "\n".join(lines)[:MAX_RESULT_CHARS]
