"""Intelligent task queuing for Jarvis.

A task is something the user wants done "at some point during free time" rather than at
an exact time (that's what create_reminder in jarvis.py is already for). This module
holds a priority queue of such tasks, plans them into free slots around supplied busy
intervals (typically the user's calendar, fetched by the agent loop via the
mcp_googlecalendar_* tools and handed to plan_task_queue — this module has no calendar
API access of its own, on purpose: jarvis.py already has a live Calendar MCP integration,
duplicating auth/API code here would just be a second thing to keep in sync), and runs
them when their slot arrives.

Self-contained: owns its own sqlite tables (task_queue) in jarvis_memory.db, like the
other jarvis_*.py modules. jarvis.py wires tick() into its existing scheduler loop
(SCHEDULER_TICK_S) so no second background thread is needed, and supplies a run_callback
for actually executing a task's instructions (identical shape to how it already runs
scheduled skills) plus a notify_callback for delivering plain reminders.

Backoff: when a task actually takes longer than its estimate, every task still queued
behind it for that day is re-planned starting after the overrun, and that task's own
future estimate (matched by a normalized description) is inflated by BACKOFF_FACTOR so
the next time something like it is queued, the plan is less likely to be optimistic.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("jarvis.task_scheduler")

DEFAULT_DAY_START = "09:00"
DEFAULT_DAY_END = "21:00"
DEFAULT_ESTIMATE_MINUTES = 30
BACKOFF_FACTOR = 1.5
MIN_ESTIMATE_MINUTES = 5
MAX_ESTIMATE_MINUTES = 240
PRIORITY_LEVELS = ("low", "normal", "high")


def _db_path() -> Path:
    override = (os.environ.get("JARVIS_MEMORY_DB_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent / "jarvis_memory.db"


_db_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.execute(
        "CREATE TABLE IF NOT EXISTS task_queue ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "description TEXT NOT NULL, "
        "instructions TEXT, "
        "priority TEXT NOT NULL DEFAULT 'normal', "
        "estimate_minutes INTEGER NOT NULL, "
        "earliest_start TEXT, "
        "deadline TEXT, "
        "scheduled_start TEXT, "
        "scheduled_end TEXT, "
        "status TEXT NOT NULL DEFAULT 'pending', "  # pending -> scheduled -> running -> done/failed/cancelled
        "actual_minutes REAL, "
        "created_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS task_estimate_history ("
        "normalized_description TEXT PRIMARY KEY, "
        "estimate_minutes INTEGER NOT NULL)"
    )
    return conn


def _normalize(description: str) -> str:
    return " ".join(description.strip().lower().split())


# --- queueing --------------------------------------------------------------------------
def queue_task(
    description: str,
    estimate_minutes: int | None = None,
    priority: str = "normal",
    instructions: str | None = None,
    earliest_start: str | None = None,
    deadline: str | None = None,
) -> str:
    """Adds a task to the queue as 'pending' (not yet given a slot — call plan_task_queue
    to assign times). earliest_start/deadline are optional ISO datetimes constraining when
    it may run; instructions, if given, are what actually gets run (via run_callback in
    tick()) instead of just a spoken reminder."""
    description = (description or "").strip()
    if not description:
        return "No task description given."
    priority = priority if priority in PRIORITY_LEVELS else "normal"

    with _db_lock:
        conn = _connect()
        try:
            if estimate_minutes is None:
                row = conn.execute(
                    "SELECT estimate_minutes FROM task_estimate_history WHERE normalized_description = ?",
                    (_normalize(description),),
                ).fetchone()
                estimate_minutes = row[0] if row else DEFAULT_ESTIMATE_MINUTES
            estimate_minutes = max(MIN_ESTIMATE_MINUTES, min(int(estimate_minutes), MAX_ESTIMATE_MINUTES))

            now = datetime.now().isoformat(timespec="seconds")
            cur = conn.execute(
                "INSERT INTO task_queue (description, instructions, priority, estimate_minutes, "
                "earliest_start, deadline, status, created_at) VALUES (?,?,?,?,?,?,'pending',?)",
                (description, instructions, priority, estimate_minutes, earliest_start, deadline, now),
            )
            conn.commit()
            task_id = cur.lastrowid
        finally:
            conn.close()
    return f"Queued task #{task_id}: {description!r} (~{estimate_minutes} min, {priority} priority)."


def cancel_task(task_id: int) -> str:
    with _db_lock:
        conn = _connect()
        try:
            cur = conn.execute(
                "UPDATE task_queue SET status = 'cancelled' WHERE id = ? AND status IN ('pending','scheduled')",
                (task_id,),
            )
            conn.commit()
        finally:
            conn.close()
    return f"Cancelled task #{task_id}." if cur.rowcount else f"No pending/scheduled task #{task_id}."


def list_task_queue(include_done: bool = False) -> str:
    with _db_lock:
        conn = _connect()
        try:
            query = "SELECT id, description, priority, estimate_minutes, scheduled_start, scheduled_end, status FROM task_queue"
            if not include_done:
                query += " WHERE status NOT IN ('done','cancelled','failed')"
            query += " ORDER BY COALESCE(scheduled_start, created_at)"
            rows = conn.execute(query).fetchall()
        finally:
            conn.close()
    if not rows:
        return "Task queue is empty."
    lines = []
    for tid, desc, pri, est, start, end, status in rows:
        when = f"{start} to {end}" if start else "unscheduled"
        lines.append(f"#{tid} [{status}/{pri}] {desc} (~{est} min) — {when}")
    return "\n".join(lines)


# --- planning: fit pending tasks into free slots around busy_intervals -----------------
def _parse_busy_intervals(busy_intervals: list[dict] | None) -> list[tuple[datetime, datetime]]:
    parsed = []
    for b in busy_intervals or []:
        try:
            start = datetime.fromisoformat(b["start"])
            end = datetime.fromisoformat(b["end"])
            if end > start:
                parsed.append((start, end))
        except (KeyError, ValueError, TypeError):
            log.warning("Skipping malformed busy interval: %r", b)
    return sorted(parsed)


def _free_slots(
    day_start: datetime, day_end: datetime, busy: list[tuple[datetime, datetime]]
) -> list[tuple[datetime, datetime]]:
    slots = []
    cursor = day_start
    for b_start, b_end in busy:
        if b_start > cursor:
            slots.append((cursor, min(b_start, day_end)))
        cursor = max(cursor, b_end)
        if cursor >= day_end:
            break
    if cursor < day_end:
        slots.append((cursor, day_end))
    return [(s, e) for s, e in slots if e > s]


def plan_task_queue(
    busy_intervals: list[dict] | None = None,
    day_start: str = DEFAULT_DAY_START,
    day_end: str = DEFAULT_DAY_END,
    days_ahead: int = 3,
) -> str:
    """Assigns scheduled_start/scheduled_end to every 'pending' task, greedily by priority
    then earliest-created, fitting each into the first free slot (today through
    days_ahead-1 more days) it fits in without violating earliest_start/deadline. Existing
    'scheduled'/'running' tasks count as busy time too, so replanning doesn't double-book."""
    busy = _parse_busy_intervals(busy_intervals)
    now = datetime.now()

    with _db_lock:
        conn = _connect()
        try:
            already_scheduled = conn.execute(
                "SELECT scheduled_start, scheduled_end FROM task_queue "
                "WHERE status IN ('scheduled','running') AND scheduled_start IS NOT NULL"
            ).fetchall()
            for s, e in already_scheduled:
                busy.append((datetime.fromisoformat(s), datetime.fromisoformat(e)))
            busy.sort()

            pending = conn.execute(
                "SELECT id, estimate_minutes, priority, earliest_start, deadline FROM task_queue "
                "WHERE status = 'pending' ORDER BY "
                "CASE priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END, created_at"
            ).fetchall()

            scheduled_count = 0
            for task_id, est, priority, earliest_start, deadline in pending:
                earliest = datetime.fromisoformat(earliest_start) if earliest_start else now
                earliest = max(earliest, now)
                dl = datetime.fromisoformat(deadline) if deadline else None
                placed = False
                for day_offset in range(days_ahead):
                    day = (now + timedelta(days=day_offset)).date()
                    d_start = datetime.combine(day, datetime.strptime(day_start, "%H:%M").time())
                    d_end = datetime.combine(day, datetime.strptime(day_end, "%H:%M").time())
                    d_start = max(d_start, earliest)
                    if d_start >= d_end:
                        continue
                    day_busy = [(s, e) for s, e in busy if s.date() == day or e.date() == day]
                    for slot_start, slot_end in _free_slots(d_start, d_end, day_busy):
                        candidate_end = slot_start + timedelta(minutes=est)
                        if candidate_end > slot_end:
                            continue
                        if dl and candidate_end > dl:
                            continue
                        conn.execute(
                            "UPDATE task_queue SET status = 'scheduled', scheduled_start = ?, "
                            "scheduled_end = ? WHERE id = ?",
                            (slot_start.isoformat(timespec="seconds"),
                             candidate_end.isoformat(timespec="seconds"), task_id),
                        )
                        busy.append((slot_start, candidate_end))
                        busy.sort()
                        scheduled_count += 1
                        placed = True
                        break
                    if placed:
                        break
            conn.commit()
        finally:
            conn.close()
    return f"Planned {scheduled_count} task(s) into free slots." if scheduled_count else \
        "No pending tasks could be fit into the given free time."


# --- execution (called from jarvis.py's existing scheduler tick) -----------------------
def _inflate_estimate(conn: sqlite3.Connection, description: str, prior_estimate: int) -> None:
    new_estimate = min(int(prior_estimate * BACKOFF_FACTOR), MAX_ESTIMATE_MINUTES)
    conn.execute(
        "INSERT INTO task_estimate_history (normalized_description, estimate_minutes) VALUES (?,?) "
        "ON CONFLICT(normalized_description) DO UPDATE SET estimate_minutes = excluded.estimate_minutes",
        (_normalize(description), new_estimate),
    )


def _push_back_remaining(conn: sqlite3.Connection, after: datetime, overrun: timedelta) -> None:
    # >= (not >): plan_task_queue packs tasks back-to-back, so the very next task's
    # scheduled_start typically equals this task's original scheduled_end exactly — a
    # strict > would miss pushing back precisely the task most likely to be affected.
    rows = conn.execute(
        "SELECT id, scheduled_start, scheduled_end FROM task_queue "
        "WHERE status = 'scheduled' AND scheduled_start >= ?",
        (after.isoformat(timespec="seconds"),),
    ).fetchall()
    for task_id, start, end in rows:
        new_start = datetime.fromisoformat(start) + overrun
        new_end = datetime.fromisoformat(end) + overrun
        conn.execute(
            "UPDATE task_queue SET scheduled_start = ?, scheduled_end = ? WHERE id = ?",
            (new_start.isoformat(timespec="seconds"), new_end.isoformat(timespec="seconds"), task_id),
        )


def tick(now: datetime, run_callback, notify_callback) -> None:
    """Call once per scheduler tick (jarvis.py's existing SCHEDULER_TICK_S loop). Starts any
    'scheduled' task whose slot has arrived (marks it 'running', executes instructions via
    run_callback if given else just notifies), and finishes any 'running' task whose slot
    has passed — if it ran over, pushes every later 'scheduled' task back by the overrun and
    inflates that task's future estimate (backoff) so tomorrow's plan is less optimistic."""
    with _db_lock:
        conn = _connect()
        try:
            due = conn.execute(
                "SELECT id, description, instructions FROM task_queue "
                "WHERE status = 'scheduled' AND scheduled_start <= ?",
                (now.isoformat(timespec="seconds"),),
            ).fetchall()
            for task_id, description, instructions in due:
                conn.execute(
                    "UPDATE task_queue SET status = 'running' WHERE id = ?", (task_id,)
                )
                conn.commit()
                log.info("Starting queued task #%s: %r", task_id, description)
                try:
                    if run_callback and instructions:
                        run_callback(description, instructions)
                    elif notify_callback:
                        notify_callback(f"Time for queued task: {description}")
                except Exception as e:
                    log.warning("Queued task #%s failed: %s", task_id, e)
                    conn.execute(
                        "UPDATE task_queue SET status = 'failed' WHERE id = ?", (task_id,)
                    )
                    conn.commit()
                    continue

                started_row = conn.execute(
                    "SELECT scheduled_start, scheduled_end, estimate_minutes FROM task_queue WHERE id = ?",
                    (task_id,),
                ).fetchone()
                finished_at = datetime.now()
                if started_row:
                    sched_end = datetime.fromisoformat(started_row[1])
                    estimate = started_row[2]
                    actual_minutes = (finished_at - datetime.fromisoformat(started_row[0])).total_seconds() / 60
                    conn.execute(
                        "UPDATE task_queue SET status = 'done', actual_minutes = ? WHERE id = ?",
                        (actual_minutes, task_id),
                    )
                    if finished_at > sched_end:
                        overrun = finished_at - sched_end
                        log.info("Task #%s ran over by %s — pushing later tasks back.", task_id, overrun)
                        _push_back_remaining(conn, sched_end, overrun)
                        _inflate_estimate(conn, description, estimate)
                conn.commit()
        finally:
            conn.close()
