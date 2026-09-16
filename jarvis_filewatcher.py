"""Filesystem watcher for Jarvis.

Polls a small set of folders (Downloads by default) for new/changed files and flags
anything large (default >100MB). Deliberately polling rather than an OS-level watch API
(no new dependency — reuses the same stdlib-only approach as jarvis_proactive.py) since
the folders being watched are small enough that an os.walk every few seconds is cheap.

Self-contained: owns its own sqlite table (known_files) so restarts don't re-announce
every file already seen, and has no import-time dependency back on jarvis.py. jarvis.py
wires this in by calling start_watching() with a notifier callback.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger("jarvis.filewatcher")

DEFAULT_POLL_INTERVAL_S = 15
DEFAULT_LARGE_FILE_MB = 100  # 104857600 bytes — only events >= this size get announced
MAX_FILES_PER_SCAN = 20_000  # safety cap so a huge folder can't hang a poll tick

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".cache", "$RECYCLE.BIN", "System Volume Information"}


def _db_path() -> Path:
    override = (os.environ.get("JARVIS_MEMORY_DB_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent / "jarvis_memory.db"


_db_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.execute(
        "CREATE TABLE IF NOT EXISTS watched_files ("
        "path TEXT PRIMARY KEY, "
        "size INTEGER NOT NULL, "
        "mtime REAL NOT NULL, "
        "first_seen_at TEXT NOT NULL, "
        "last_seen_at TEXT NOT NULL)"
    )
    return conn


def _default_watch_paths() -> list[str]:
    return [str(Path.home() / "Downloads")]


class FileWatcher:
    """One instance owns the polling loop, the set of watched folders, a rolling event
    log (in-memory, for get_recent_events), and the large-file threshold. jarvis.py holds
    a single module-level instance (see `watcher` below); tests/other callers can make
    their own."""

    def __init__(
        self,
        paths: list[str] | None = None,
        poll_interval: int = DEFAULT_POLL_INTERVAL_S,
        large_file_mb: int = DEFAULT_LARGE_FILE_MB,
        notifier=None,
    ) -> None:
        self.paths: list[str] = list(paths) if paths else _default_watch_paths()
        self.poll_interval = poll_interval
        self.large_file_bytes = large_file_mb * 1024 * 1024
        self.notifier = notifier  # callable(text: str, urgent: bool) -> None
        self._events: list[dict] = []
        self._events_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # --- folder management ---------------------------------------------------------
    def add_path(self, path: str) -> str:
        p = str(Path(path).expanduser().resolve())
        if not os.path.isdir(p):
            return f"{path!r} is not a folder that exists."
        if p in self.paths:
            return f"Already watching {p}."
        self.paths.append(p)
        return f"Now watching {p}."

    def remove_path(self, path: str) -> str:
        p = str(Path(path).expanduser().resolve())
        if p not in self.paths:
            return f"Not currently watching {p}."
        self.paths.remove(p)
        return f"Stopped watching {p}."

    def list_paths(self) -> list[str]:
        return list(self.paths)

    # --- event log -------------------------------------------------------------------
    def _record_event(self, kind: str, path: str, size: int) -> dict:
        event = {
            "kind": kind,  # "new" or "changed"
            "path": path,
            "size": size,
            "large": size >= self.large_file_bytes,
            "at": datetime.now().isoformat(timespec="seconds"),
        }
        with self._events_lock:
            self._events.append(event)
            del self._events[:-200]  # keep the last 200 in memory
        return event

    def recent_events(self, limit: int = 20) -> list[dict]:
        with self._events_lock:
            return list(self._events[-limit:])

    # --- scan / poll -------------------------------------------------------------------
    def _iter_files(self, root: str):
        count = 0
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
            for name in filenames:
                p = Path(dirpath) / name
                try:
                    st = p.stat()
                except OSError:
                    continue
                yield str(p), st.st_size, st.st_mtime
                count += 1
                if count >= MAX_FILES_PER_SCAN:
                    return

    def poll_once(self) -> list[dict]:
        """Runs one scan across all watched folders, persists what changed, and returns the
        new events (also appended to the in-memory recent-events log)."""
        now = datetime.now().isoformat(timespec="seconds")
        new_events: list[dict] = []
        with _db_lock:
            conn = _connect()
            try:
                for root in list(self.paths):
                    if not os.path.isdir(root):
                        continue
                    for path, size, mtime in self._iter_files(root):
                        row = conn.execute(
                            "SELECT size, mtime FROM watched_files WHERE path = ?", (path,)
                        ).fetchone()
                        if row is None:
                            conn.execute(
                                "INSERT INTO watched_files (path, size, mtime, first_seen_at, last_seen_at) "
                                "VALUES (?,?,?,?,?)",
                                (path, size, mtime, now, now),
                            )
                            new_events.append(self._record_event("new", path, size))
                        else:
                            old_size, old_mtime = row
                            if size != old_size or mtime != old_mtime:
                                conn.execute(
                                    "UPDATE watched_files SET size = ?, mtime = ?, last_seen_at = ? "
                                    "WHERE path = ?",
                                    (size, mtime, now, path),
                                )
                                new_events.append(self._record_event("changed", path, size))
                            else:
                                conn.execute(
                                    "UPDATE watched_files SET last_seen_at = ? WHERE path = ?", (now, path)
                                )
                conn.commit()
            except sqlite3.Error as e:
                log.warning("watched_files write failed: %s", e)
            finally:
                conn.close()

        for event in new_events:
            self._announce(event)
        return new_events

    def _announce(self, event: dict) -> None:
        size_mb = event["size"] / (1024 * 1024)
        verb = "New file" if event["kind"] == "new" else "File changed"
        if not event["large"]:
            # Still recorded in the event log (see recent_events), just not announced —
            # only files at/above large_file_bytes are worth interrupting for.
            log.info("File event (below announce threshold, not announced): %s %s (%.1f MB)",
                      event["kind"], event["path"], size_mb)
            return
        text = f"{verb} in a watched folder: {event['path']} ({size_mb:.0f} MB) — that's a large one."
        log.info("Large file event: %s", text)
        if self.notifier:
            try:
                self.notifier(text, event["large"])
            except Exception as e:
                log.warning("File watcher notifier failed: %s", e)

    # --- background loop -------------------------------------------------------------
    def _loop(self) -> None:
        # First pass after a restart only baselines known_files silently (no backlog of
        # "new file" alerts for everything already sitting in Downloads from before).
        try:
            self._baseline()
        except Exception as e:
            log.warning("File watcher baseline failed: %s", e)
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception as e:
                log.warning("File watcher poll failed: %s", e)
            self._stop.wait(self.poll_interval)

    def _baseline(self) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with _db_lock:
            conn = _connect()
            try:
                already_known = conn.execute("SELECT COUNT(*) FROM watched_files").fetchone()[0]
                if already_known:
                    return  # not first run ever — let poll_once report real changes normally
                for root in list(self.paths):
                    if not os.path.isdir(root):
                        continue
                    for path, size, mtime in self._iter_files(root):
                        conn.execute(
                            "INSERT OR IGNORE INTO watched_files "
                            "(path, size, mtime, first_seen_at, last_seen_at) VALUES (?,?,?,?,?)",
                            (path, size, mtime, now, now),
                        )
                conn.commit()
            except sqlite3.Error as e:
                log.warning("watched_files baseline write failed: %s", e)
            finally:
                conn.close()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="file-watcher")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


# Module-level singleton — jarvis.py imports `watcher` and calls start()/stop() on it, and
# the agent-tool functions below all operate on this same instance so tool calls and the
# background loop see consistent state.
watcher = FileWatcher()


def start_watching(notifier=None) -> None:
    if notifier is not None:
        watcher.notifier = notifier
    watcher.start()


def stop_watching() -> None:
    watcher.stop()


# --- agent-tool entry points (thin wrappers returning strings, matching the other
# jarvis_*.py modules' convention) --------------------------------------------------
def list_watched_folders() -> str:
    paths = watcher.list_paths()
    if not paths:
        return "Not watching any folders."
    return "Watching: " + ", ".join(paths)


def add_watched_folder(path: str) -> str:
    return watcher.add_path(path)


def remove_watched_folder(path: str) -> str:
    return watcher.remove_path(path)


def get_recent_file_events(limit: int = 20) -> str:
    events = watcher.recent_events(limit)
    if not events:
        return "No file events recorded yet."
    lines = []
    for e in events:
        size_mb = e["size"] / (1024 * 1024)
        flag = " [LARGE]" if e["large"] else ""
        lines.append(f"{e['at']} — {e['kind']}: {e['path']} ({size_mb:.1f} MB){flag}")
    return "\n".join(lines)
