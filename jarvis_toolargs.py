"""Generic tool-argument checking and repair (2026-09-30).

Models regularly call a tool with the right idea but the wrong parameter name (found live: quick_search got
{"name_query": "weird"} because the neighbouring find_files tool uses that name, so Everything was never asked).
Instead of patching one tool at a time, every call is checked against the tool's own schema first:

  * an unknown parameter that clearly stands for a missing one is renamed (name_query -> query);
  * simple type slips are fixed ("5" -> 5, "true" -> True, a lone string for a list parameter);
  * a wrong-case enum value is fixed;
  * anything that cannot be repaired comes back as an error that says what is missing and what the tool takes,
    so the model can correct itself on the next round instead of guessing.

Pure functions, no imports from jarvis.py. Every repair is remembered (recent()) so the tool descriptions
that keep confusing models can be found and fixed.
"""

from __future__ import annotations

import difflib
import re
import threading
import time
from collections import deque

_recent: deque = deque(maxlen=60)
_lock = threading.Lock()


def _tokens(name: str) -> set[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(name))
    return {t for t in re.split(r"[^a-zA-Z0-9]+", spaced.lower()) if t}


def _types(prop: dict) -> set[str]:
    t = (prop or {}).get("type")
    if isinstance(t, list):
        return {str(x) for x in t}
    return {str(t)} if t else set()


def _compatible(value, prop: dict) -> bool:
    """True when `value` can stand for this parameter without changing its meaning."""
    types = _types(prop) - {"null"}
    if not types:
        return True
    if "string" in types and isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return True
    if "integer" in types and (isinstance(value, int) and not isinstance(value, bool)
                               or isinstance(value, str) and re.fullmatch(r"\s*-?\d+\s*", value)):
        return True
    if "number" in types and (isinstance(value, (int, float)) and not isinstance(value, bool)
                              or isinstance(value, str) and re.fullmatch(r"\s*-?\d+(\.\d+)?\s*", value)):
        return True
    if "boolean" in types and (isinstance(value, bool) or str(value).strip().lower() in _TRUE | _FALSE):
        return True
    if "array" in types and isinstance(value, (list, str)):
        return True
    if "object" in types and isinstance(value, dict):
        return True
    return False


_TRUE = {"true", "yes", "on", "1"}
_FALSE = {"false", "no", "off", "0"}


def _name_score(unknown: str, wanted: str) -> float:
    a, b = _tokens(unknown), _tokens(wanted)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if b <= a or a <= b:  # name_query ~ query, path ~ path_prefix
        return 0.9
    if len(a) == 1 and len(b) == 1:  # extension ~ ext, directory ~ dir: one word starts with the other
        x, y = next(iter(a)), next(iter(b))
        if min(len(x), len(y)) >= 3 and (x.startswith(y) or y.startswith(x)):
            return 0.85
    return difflib.SequenceMatcher(None, unknown.lower(), wanted.lower()).ratio()


def _coerce(value, prop: dict):
    """(new_value, changed). Only fixes slips that cannot change what was meant."""
    types = _types(prop) - {"null"}
    if not types or (isinstance(value, bool) and "boolean" in types):
        return value, False
    if "string" in types:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value), True
        return value, False
    if "integer" in types and isinstance(value, str) and re.fullmatch(r"\s*-?\d+\s*", value):
        return int(value), True
    if "integer" in types and isinstance(value, float) and value.is_integer():
        return int(value), True
    if "number" in types and isinstance(value, str) and re.fullmatch(r"\s*-?\d+(\.\d+)?\s*", value):
        return float(value), True
    if "boolean" in types and isinstance(value, (str, int)) and not isinstance(value, bool):
        s = str(value).strip().lower()
        if s in _TRUE:
            return True, True
        if s in _FALSE:
            return False, True
    if "array" in types and isinstance(value, str) and "string" not in types:
        return [value], True
    return value, False


def _empty(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def describe(schema: dict, limit: int = 8) -> str:
    """'query (string), ext (string), path_prefix (string)' - what the tool takes, for error messages."""
    props = (schema or {}).get("properties") or {}
    req = set((schema or {}).get("required") or [])
    parts = []
    for name, p in list(props.items())[:limit]:
        t = "/".join(sorted(_types(p) - {"null"})) or "any"
        parts.append(f"{name} ({t}{', required' if name in req else ''})")
    more = f", +{len(props) - limit} more" if len(props) > limit else ""
    return ", ".join(parts) + more


def check(tool: str, schema: dict | None, args: dict | None) -> tuple[dict, list[str], str | None]:
    """(arguments to use, notes about what was repaired, error text or None)."""
    args = dict(args or {})
    props = (schema or {}).get("properties") or {}
    if not props:
        return args, [], None
    required = [r for r in ((schema or {}).get("required") or []) if r in props]
    notes: list[str] = []

    unknown = [k for k in args if k not in props and not str(k).startswith("_")]
    missing = [p for p in props if p not in args or _empty(args[p])]

    # 1. rename unknown parameters that clearly mean a missing one
    for u in list(unknown):
        cands = [(m, _name_score(u, m)) for m in missing if _compatible(args[u], props[m])]
        cands = sorted((c for c in cands if c[1] >= 0.75), key=lambda c: -c[1])
        if cands and (len(cands) == 1 or cands[0][1] > cands[1][1]):
            target = cands[0][0]
            args[target] = args.pop(u)
            unknown.remove(u)
            missing.remove(target)
            notes.append(f"{u} -> {target}")
    # 2. one stray parameter and exactly one missing required one: the same thing under another name
    miss_req = [m for m in missing if m in required]
    if len(unknown) == 1 and len(miss_req) == 1 and _compatible(args[unknown[0]], props[miss_req[0]]):
        u, target = unknown[0], miss_req[0]
        args[target] = args.pop(u)
        unknown.clear()
        missing.remove(target)
        notes.append(f"{u} -> {target}")

    # 3. simple type slips and enum case
    for name, prop in props.items():
        if name not in args or _empty(args[name]):
            continue
        new, changed = _coerce(args[name], prop)
        if changed:
            args[name] = new
            notes.append(f"{name}: fixed type")
        enum = prop.get("enum")
        if enum and isinstance(args[name], str) and args[name] not in enum:
            match = next((e for e in enum if isinstance(e, str) and e.lower() == args[name].strip().lower()), None)
            if match is not None:
                args[name] = match
                notes.append(f"{name}: fixed case")
            else:
                return args, notes, (
                    f"Invalid value {args[name]!r} for '{name}' of {tool}. Valid values: "
                    f"{', '.join(str(e) for e in enum)}. Call {tool} again with one of them.")

    still_missing = [r for r in required if r not in args or _empty(args[r])]
    if still_missing:
        got = ", ".join(k for k in args if not str(k).startswith("_")) or "nothing"
        return args, notes, (
            f"{tool} needs {', '.join(repr(m) for m in still_missing)} but got: {got}. "
            f"It takes: {describe(schema)}. Call {tool} again with the right parameter names.")
    if unknown:
        notes.append("ignored unknown: " + ", ".join(unknown))
    if notes:
        with _lock:
            _recent.append({"ts": time.time(), "tool": tool, "notes": list(notes)})
    return args, notes, None


def recent(limit: int = 20) -> list[dict]:
    with _lock:
        return list(_recent)[-limit:]


def summary(limit: int = 5) -> str:
    """One line for the doctor/self-check: which tools needed argument repairs lately."""
    with _lock:
        rows = list(_recent)
    if not rows:
        return "no argument repairs needed lately"
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["tool"]] = counts.get(r["tool"], 0) + 1
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:limit]
    return "argument repairs: " + ", ".join(f"{t} x{n}" for t, n in top)
