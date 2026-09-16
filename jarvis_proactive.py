"""Proactive problem detection for Jarvis.

Scans a file or project directory for concrete, regex/AST-detectable patterns that
commonly precede real bugs, security issues, or performance problems — deliberately
*not* a full static analyzer or linter replacement, just cheap, high-signal checks
that are worth surfacing unprompted. Findings are persisted and de-duplicated so a
repeat scan reports what's new/still-present rather than repeating the same list.

Explicitly out of scope (per product decision): continuous screen monitoring. This
module only ever runs on-demand (a tool call) or as a one-shot scan triggered by
another action (e.g. after a coding task finishes) — never a background poll of the
screen or filesystem.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

log = logging.getLogger("jarvis.proactive")

MAX_RESULT_CHARS = 4000
MAX_FILES_SCANNED = 400
MAX_FILE_BYTES = 1_500_000

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".next", ".cache", "target", ".pytest_cache", ".mypy_cache", "vendor",
}
_SOURCE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb", ".php",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".sh", ".ps1",
}

# (category, severity, compiled pattern, message)
_PATTERNS: tuple[tuple[str, str, "re.Pattern[str]", str], ...] = (
    (
        "bug_risk", "medium",
        re.compile(r"^\s*except\s*:\s*$", re.M),
        "bare `except:` swallows every exception, including Ctrl+C/SystemExit — narrow it.",
    ),
    (
        "bug_risk", "low",
        re.compile(r"except\s+Exception\s*(as\s+\w+)?\s*:\s*\n\s*pass\b"),
        "exception caught and silently discarded — errors here vanish with no trace.",
    ),
    (
        "bug_risk", "low",
        re.compile(r"<<<<<<<\s|=======\s*$|>>>>>>>\s", re.M),
        "unresolved merge-conflict marker left in the file.",
    ),
    (
        "bug_risk", "low",
        re.compile(r"\b(TODO|FIXME|HACK|XXX)\b"),
        "TODO/FIXME/HACK marker present.",
    ),
    (
        "security", "high",
        re.compile(
            r"(?i)(api[_-]?key|secret|password|passwd|token|access[_-]?key)\s*[:=]\s*"
            r"['\"][A-Za-z0-9_\-/+=]{12,}['\"]"
        ),
        "possible hardcoded credential/secret literal.",
    ),
    (
        "security", "high",
        re.compile(r"-----BEGIN (RSA|EC|OPENSSH|PRIVATE) KEY-----"),
        "an embedded private key.",
    ),
    (
        "security", "medium",
        re.compile(r"\beval\s*\(|\bexec\s*\("),
        "eval()/exec() on dynamic input is a common injection vector.",
    ),
    (
        "security", "medium",
        re.compile(r"subprocess\.\w+\([^)]*shell\s*=\s*True"),
        "subprocess call with shell=True — risky if any part of the command is user input.",
    ),
    (
        "security", "medium",
        re.compile(r"pickle\.loads?\("),
        "pickle deserialization of untrusted data can execute arbitrary code.",
    ),
    (
        "security", "medium",
        re.compile(r"(?i)\b(execute|cursor\.execute)\s*\(\s*f?[\"'].*%s.*[\"']\s*%|"
                    r"execute\s*\(\s*[\"'][^\"']*\"\s*\+"),
        "SQL built via string formatting/concatenation — use parameterized queries.",
    ),
    (
        "performance", "low",
        re.compile(r"time\.sleep\([^)]*\)\s*\n(?:[^\n]*\n){0,3}?\s*(for|while)\b"),
        "sleep() near a loop — check it isn't polling tightly inside the loop body.",
    ),
    (
        "performance", "medium",
        re.compile(r"for\s+\w+\s+in\s+.+:\s*\n(?:.*\n){0,15}?\s*for\s+\w+\s+in\s+.+:"),
        "nested loops found close together — worth a second look for O(n^2) behavior on large inputs.",
    ),
)


def _db_path() -> Path:
    override = (os.environ.get("JARVIS_MEMORY_DB_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent / "jarvis_memory.db"


_db_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.execute(
        "CREATE TABLE IF NOT EXISTS proactive_findings ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "path TEXT NOT NULL, "
        "category TEXT NOT NULL, "
        "severity TEXT NOT NULL, "
        "message TEXT NOT NULL, "
        "line_number INTEGER, "
        "fingerprint TEXT NOT NULL UNIQUE, "
        "first_seen_at TEXT NOT NULL, "
        "last_seen_at TEXT NOT NULL, "
        "resolved_at TEXT)"
    )
    return conn


def _iter_source_files(root: Path):
    if root.is_file():
        if root.suffix.lower() in _SOURCE_EXTS:
            yield root
        return
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() not in _SOURCE_EXTS:
                continue
            try:
                if p.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield p
            count += 1
            if count >= MAX_FILES_SCANNED:
                return


def _scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        log.debug("could not read %s: %s", path, e)
        return []
    findings: list[dict] = []
    for category, severity, pattern, message in _PATTERNS:
        for m in pattern.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            findings.append(
                {
                    "path": str(path),
                    "category": category,
                    "severity": severity,
                    "message": message,
                    "line_number": line_no,
                }
            )
    return findings


def scan_path(root_path: str) -> dict:
    """Scans a file or directory tree, persists/de-dupes findings against previous scans,
    and returns {new, still_present, resolved, total_files_scanned}."""
    root = Path(root_path).expanduser().resolve()
    if not root.exists():
        return {"error": f"{root_path!r} does not exist."}

    all_findings: list[dict] = []
    files_scanned = 0
    for f in _iter_source_files(root):
        all_findings.extend(_scan_file(f))
        files_scanned += 1

    now = datetime.now().isoformat(timespec="seconds")
    seen_fingerprints: set[str] = set()
    new_findings: list[dict] = []
    still_present: list[dict] = []

    with _db_lock:
        conn = _connect()
        try:
            for f in all_findings:
                fp = f"{f['path']}|{f['category']}|{f['message']}|{f['line_number']}"
                seen_fingerprints.add(fp)
                existing = conn.execute(
                    "SELECT id, resolved_at FROM proactive_findings WHERE fingerprint = ?",
                    (fp,),
                ).fetchone()
                if existing is None:
                    conn.execute(
                        "INSERT INTO proactive_findings "
                        "(path, category, severity, message, line_number, fingerprint, "
                        "first_seen_at, last_seen_at, resolved_at) VALUES (?,?,?,?,?,?,?,?,NULL)",
                        (f["path"], f["category"], f["severity"], f["message"],
                         f["line_number"], fp, now, now),
                    )
                    new_findings.append(f)
                else:
                    conn.execute(
                        "UPDATE proactive_findings SET last_seen_at = ?, resolved_at = NULL "
                        "WHERE id = ?",
                        (now, existing[0]),
                    )
                    if existing[1]:  # was previously marked resolved, now back
                        new_findings.append(f)
                    else:
                        still_present.append(f)

            # Anything under this root that was seen before but not this time is resolved.
            resolved: list[dict] = []
            prior_rows = conn.execute(
                "SELECT id, path, category, message, line_number, fingerprint "
                "FROM proactive_findings WHERE resolved_at IS NULL AND path LIKE ?",
                (str(root) + "%",),
            ).fetchall()
            for row_id, path, category, message, line_number, fp in prior_rows:
                if fp not in seen_fingerprints:
                    conn.execute(
                        "UPDATE proactive_findings SET resolved_at = ? WHERE id = ?", (now, row_id)
                    )
                    resolved.append(
                        {"path": path, "category": category, "message": message, "line_number": line_number}
                    )
            conn.commit()
        except sqlite3.Error as e:
            log.warning("proactive_findings write failed: %s", e)
            resolved = []
        finally:
            conn.close()

    return {
        "new": new_findings,
        "still_present": still_present,
        "resolved": resolved,
        "total_files_scanned": files_scanned,
    }


def _fmt_findings(findings: list[dict], limit: int = 15) -> list[str]:
    lines = []
    for f in findings[:limit]:
        rel = f["path"]
        lines.append(f"[{f['category']}/{f['severity']}] {rel}:{f['line_number']} — {f['message']}")
    if len(findings) > limit:
        lines.append(f"... and {len(findings) - limit} more")
    return lines


def check_project_health(root_path: str) -> str:
    """Tool entry point: scans `root_path` and returns a human-readable report of new,
    still-open, and resolved findings."""
    result = scan_path(root_path)
    if "error" in result:
        return result["error"]

    if not result["new"] and not result["still_present"] and not result["resolved"]:
        return f"Scanned {result['total_files_scanned']} file(s) under {root_path} — nothing flagged."

    lines = [f"Scanned {result['total_files_scanned']} file(s) under {root_path}."]
    if result["new"]:
        lines.append(f"\nNew findings ({len(result['new'])}):")
        lines.extend(_fmt_findings(result["new"]))
    if result["still_present"]:
        lines.append(f"\nStill present ({len(result['still_present'])}):")
        lines.extend(_fmt_findings(result["still_present"], limit=8))
    if result["resolved"]:
        lines.append(f"\nResolved since last scan ({len(result['resolved'])}):")
        lines.extend(_fmt_findings(result["resolved"], limit=8))

    report = "\n".join(lines)
    return report[:MAX_RESULT_CHARS]
