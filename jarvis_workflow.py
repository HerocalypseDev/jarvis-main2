"""Workflow integration for Jarvis.

Tracks which development workspace(s) the user is actually working in, detects
git branch/status for them, notices when the user switches between projects,
and suggests relevant tools/actions based on what it can see about the current
workspace (stack, uncommitted changes, etc). Designed to be called opportunistically
from jarvis.py — e.g. whenever a repo path is touched by another tool — plus exposed
as its own `get_workflow_status` tool for on-demand use.

Self-contained: owns its own SQLite tables (in the same jarvis_memory.db file jarvis.py
already uses) and its own connection/lock, so it has no import-time dependency on
jarvis.py and can't create a circular import.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

log = logging.getLogger("jarvis.workflow")

MAX_RESULT_CHARS = 4000
GIT_TIMEOUT_S = 8

# Files whose presence identifies a project's stack. Checked in order; first match wins
# per marker file, but every match found is reported (a repo can be more than one thing).
_STACK_MARKERS: tuple[tuple[str, str], ...] = (
    ("package.json", "Node.js/JavaScript"),
    ("pyproject.toml", "Python (pyproject)"),
    ("requirements.txt", "Python (pip)"),
    ("Cargo.toml", "Rust"),
    ("go.mod", "Go"),
    ("pom.xml", "Java (Maven)"),
    ("build.gradle", "Java/Kotlin (Gradle)"),
    ("Gemfile", "Ruby"),
    ("composer.json", "PHP"),
    ("CMakeLists.txt", "C/C++ (CMake)"),
    (".csproj", "C#/.NET"),
)

_db_lock = threading.Lock()


def _db_path() -> Path:
    override = (os.environ.get("JARVIS_MEMORY_DB_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent / "jarvis_memory.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.execute(
        "CREATE TABLE IF NOT EXISTS workflow_sessions ("
        "path TEXT PRIMARY KEY, "
        "project_name TEXT NOT NULL, "
        "stack TEXT, "
        "git_branch TEXT, "
        "first_seen_at TEXT NOT NULL, "
        "last_active_at TEXT NOT NULL, "
        "touch_count INTEGER NOT NULL DEFAULT 1)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS workflow_switches ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "from_path TEXT, "
        "to_path TEXT NOT NULL, "
        "timestamp TEXT NOT NULL)"
    )
    return conn


_last_active_path: str | None = None


def _run_git(path: str, args: list[str]) -> str | None:
    """Runs a git subcommand in `path`; returns stripped stdout, or None on any failure
    (not a git repo, git not installed, timeout, etc.) — callers treat None as 'unknown'."""
    try:
        popen_kw: dict = {}
        if os.name == "nt":
            popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.run(
            ["git", "-C", path, *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
            **popen_kw,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        log.debug("git %s in %s failed: %s", args, path, e)
        return None


def git_info(path: str) -> dict:
    """Best-effort git snapshot for `path`: branch, uncommitted file count, ahead/behind
    the upstream, and the last commit's subject line. Any field is None if it couldn't be
    determined (not a repo, no commits yet, no upstream configured, etc)."""
    info: dict = {
        "is_repo": False,
        "branch": None,
        "uncommitted_files": None,
        "ahead": None,
        "behind": None,
        "last_commit": None,
    }
    branch = _run_git(path, ["rev-parse", "--abbrev-ref", "HEAD"])
    if branch is None:
        return info
    info["is_repo"] = True
    info["branch"] = branch
    status = _run_git(path, ["status", "--porcelain"])
    if status is not None:
        info["uncommitted_files"] = len([l for l in status.splitlines() if l.strip()])
    counts = _run_git(path, ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"])
    if counts:
        parts = counts.split()
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            info["ahead"], info["behind"] = int(parts[0]), int(parts[1])
    last_commit = _run_git(path, ["log", "-1", "--pretty=%s"])
    if last_commit:
        info["last_commit"] = last_commit
    return info


def detect_stack(path: str) -> list[str]:
    """Lightweight project-type detection from marker files in the top level of `path`."""
    found: list[str] = []
    try:
        entries = {p.name for p in Path(path).iterdir()}
    except OSError:
        return found
    for marker, label in _STACK_MARKERS:
        if marker.startswith("."):
            if any(name.endswith(marker) for name in entries):
                found.append(label)
        elif marker in entries:
            found.append(label)
    return found


def suggest_tools(git: dict, stack: list[str]) -> list[str]:
    """Turns a git/stack snapshot into short, actionable suggestions — not commands run
    automatically, just hints surfaced to the user/model."""
    suggestions: list[str] = []
    if git.get("is_repo"):
        uncommitted = git.get("uncommitted_files") or 0
        if uncommitted > 0:
            suggestions.append(
                f"{uncommitted} uncommitted file(s) on branch {git.get('branch')} — "
                "consider committing or stashing before switching context."
            )
        if (git.get("behind") or 0) > 0:
            suggestions.append(
                f"branch is {git['behind']} commit(s) behind its upstream — consider pulling."
            )
        if (git.get("ahead") or 0) > 5:
            suggestions.append(
                f"branch is {git['ahead']} commit(s) ahead of its upstream — consider pushing."
            )
    else:
        suggestions.append("not a git repository — version control isn't tracking this folder.")
    if "Python (pip)" in stack or "Python (pyproject)" in stack:
        suggestions.append("Python project — tests can likely be run with pytest.")
    if "Node.js/JavaScript" in stack:
        suggestions.append("Node project — check package.json's \"scripts\" for test/build commands.")
    return suggestions


def touch_workspace(path: str) -> dict:
    """Called whenever a directory is actively worked in (e.g. a coding task targets it).
    Records/updates the workflow_sessions row, detects a context switch if this differs
    from the last-touched workspace, and returns a fresh snapshot (git info, stack,
    suggestions, whether this was a switch)."""
    global _last_active_path
    resolved = str(Path(path).expanduser().resolve()) if path.strip() else ""
    if not resolved or not Path(resolved).is_dir():
        return {"error": f"{path!r} is not a directory."}

    git = git_info(resolved)
    stack = detect_stack(resolved)
    now = datetime.now().isoformat(timespec="seconds")
    is_switch = _last_active_path is not None and _last_active_path != resolved

    with _db_lock:
        conn = _connect()
        try:
            project_name = Path(resolved).name
            row = conn.execute(
                "SELECT touch_count FROM workflow_sessions WHERE path = ?", (resolved,)
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO workflow_sessions "
                    "(path, project_name, stack, git_branch, first_seen_at, last_active_at, touch_count) "
                    "VALUES (?, ?, ?, ?, ?, ?, 1)",
                    (resolved, project_name, ", ".join(stack), git.get("branch"), now, now),
                )
            else:
                conn.execute(
                    "UPDATE workflow_sessions SET stack = ?, git_branch = ?, last_active_at = ?, "
                    "touch_count = touch_count + 1 WHERE path = ?",
                    (", ".join(stack), git.get("branch"), now, resolved),
                )
            if is_switch:
                conn.execute(
                    "INSERT INTO workflow_switches (from_path, to_path, timestamp) VALUES (?, ?, ?)",
                    (_last_active_path, resolved, now),
                )
            conn.commit()
        except sqlite3.Error as e:
            log.warning("workflow_sessions write failed: %s", e)
        finally:
            conn.close()

    _last_active_path = resolved
    return {
        "path": resolved,
        "project_name": Path(resolved).name,
        "stack": stack,
        "git": git,
        "suggestions": suggest_tools(git, stack),
        "context_switch": is_switch,
    }


def recent_switches(limit: int = 5) -> list[tuple]:
    with _db_lock:
        conn = _connect()
        try:
            return conn.execute(
                "SELECT from_path, to_path, timestamp FROM workflow_switches "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            conn.close()


def get_workflow_status(path: str = "") -> str:
    """Tool entry point: full human-readable workflow report for `path` (or the last
    actively-touched workspace if `path` is omitted)."""
    target = path.strip() or _last_active_path
    if not target:
        return "No active workspace tracked yet — pass a project path."
    snap = touch_workspace(target)
    if "error" in snap:
        return snap["error"]

    lines = [f"Workspace: {snap['project_name']} ({snap['path']})"]
    if snap["stack"]:
        lines.append(f"Stack: {', '.join(snap['stack'])}")
    git = snap["git"]
    if git.get("is_repo"):
        branch_line = f"Git branch: {git['branch']}"
        if git.get("uncommitted_files") is not None:
            branch_line += f", {git['uncommitted_files']} uncommitted file(s)"
        lines.append(branch_line)
        if git.get("last_commit"):
            lines.append(f"Last commit: {git['last_commit']}")
    else:
        lines.append("Not a git repository.")
    if snap["context_switch"]:
        lines.append("(context switch detected from the previous workspace)")
    if snap["suggestions"]:
        lines.append("Suggestions: " + " | ".join(snap["suggestions"]))

    switches = recent_switches(3)
    if switches:
        recent = "; ".join(
            f"{Path(f).name if f else '?'} -> {Path(t).name}" for f, t, _ts in switches
        )
        lines.append(f"Recent context switches: {recent}")

    report = "\n".join(lines)
    return report[:MAX_RESULT_CHARS]


def get_context_summary() -> str:
    """Short one-paragraph summary for injection into Jarvis's system prompt — cheap,
    read-only, no git calls (uses whatever was last recorded by touch_workspace)."""
    if not _last_active_path:
        return ""
    with _db_lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT project_name, git_branch, stack FROM workflow_sessions WHERE path = ?",
                (_last_active_path,),
            ).fetchone()
        finally:
            conn.close()
    if not row:
        return ""
    name, branch, stack = row
    parts = [f"Current dev workspace: {name}"]
    if branch:
        parts.append(f"(branch {branch})")
    if stack:
        parts.append(f"[{stack}]")
    return "\n\nWorkflow context: " + " ".join(parts)
