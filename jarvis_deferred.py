"""Deferred Jarvis work (2026-09-27, executive autonomy): "in 30 minutes, change the code for X" is a job
Jarvis RUNS at that time, not a reminder it reads out.

`autonomy_deferred_jobs` (jarvis_memory.db): due_at, kind (execute_jarvis | notify_user), instruction (a
clean imperative for Jarvis), source_quote, origin (user = scheduled by a direct request through the
schedule_jarvis_task tool; conversation = extracted by autonomy from the user's own words), status
(pending | running | done | failed | cancelled), result, attempts.

jarvis.py's scheduler tick calls `claim_due()` (atomic pending->running, so a job never runs twice) and
runs each claimed execute_jarvis job through the normal agent loop on a worker thread: every tool call
audited, the catastrophic confirmation gate intact (a shutdown/format/wipe still STAGES). A failed run is
retried up to MAX_ATTEMPTS times, RETRY_MIN apart, then reported.

Only the user's own requests create jobs: never mail, messages, web pages or files (enforced by the
callers: the tool refuses unattended/autonomous sources, extraction only accepts quotes from the user's
own words).
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta

KINDS = ("execute_jarvis", "notify_user")
MAX_ATTEMPTS = 3
RETRY_MIN = 5
DEDUPE_WINDOW_MIN = 20
STALE_RUNNING_MIN = 90  # a job left 'running' by a crash/restart this long is retried
# Only an explicit "Jarvis": "You should call mom" is a reminder FOR the user (audit 2026-09-27).
_RESTART_RE = re.compile(r"\b(?:restart|reboot|relaunch|reload)\s+(?:yourself|jarvis|itself)\b|\brestart_jarvis\b"
                         r"|\bupdate (?:time|yourself|and restart)\b|\b(?:pull|update) and restart\b", re.I)
_REMIND_JARVIS_RE = re.compile(r"^\s*(?:please\s+)?(?:remind\s+)?jarvis\s*,?\s+"
                               r"(?:to|should|needs? to|will|must|has to)\s+(.+)$", re.I)


def ensure(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS autonomy_deferred_jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                 "due_at TEXT NOT NULL, kind TEXT NOT NULL, instruction TEXT NOT NULL, source_quote TEXT, "
                 "origin TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', result TEXT, created_at TEXT NOT NULL, "
                 "started_at TEXT, finished_at TEXT, attempts INTEGER NOT NULL DEFAULT 0)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deferred_due ON autonomy_deferred_jobs(status, due_at)")


class Store:
    def __init__(self, connect, lock):
        self.connect, self.lock = connect, lock

    def q(self, sql: str, args: tuple = (), write: bool = False):
        with self.lock:
            conn = self.connect()
            try:
                ensure(conn)
                conn.row_factory = sqlite3.Row
                cur = conn.execute(sql, args)
                if write:
                    conn.commit()
                    return cur.rowcount if not sql.lstrip().upper().startswith("INSERT") else cur.lastrowid
                return [dict(r) for r in cur.fetchall()]
            finally:
                conn.close()


def as_jarvis_instruction(text: str) -> str | None:
    """'remind Jarvis to change the code' -> 'change the code'; None if it isn't work for Jarvis."""
    m = _REMIND_JARVIS_RE.match(text or "")
    if not m:
        return None
    body = m.group(1).strip().rstrip(".")
    return body[:1].upper() + body[1:] if body else None


# "In 10 minutes run the internet test again" was saved as a reminder ("Run the internet speed test") that was only
# read out at 21:34 (debug report 2026-10-02): the model picked create_reminder over schedule_jarvis_task. A reminder
# whose text is a job Jarvis can do itself, from a request that never asked to be reminded, becomes a job instead.
_ASKED_FOR_REMINDER_RE = re.compile(r"\b(?:remind|reminder|alarm|nudge me|ping me|tell me to|let me know to|"
                                    r"don'?t let me forget)\b", re.I)
_JARVIS_WORK_RE = re.compile(r"^\s*(?:please\s+)?(?:to\s+)?(?:re-?)?(?:run|perform|repeat|redo|check|test|measure|"
                             r"search|look\s+up|find|scan|summari[sz]e|research|download|refresh)\b", re.I)
_WORK_VERB_RE = re.compile(r"\b(?:re-?)?(?:run|perform|repeat|redo|check|test|measure|search|look\s+up|find|scan|"
                           r"summari[sz]e|research|download|refresh)\b", re.I)


def as_work_for_jarvis(reminder_text: str, request: str) -> str | None:
    """The job instruction when a reminder is really work for Jarvis, else None. Only when the user's own request
    asked Jarvis to DO it (a work verb, no "remind me"), and the reminder starts with that kind of verb. A job that
    turns out to be something only the user can do still reminds them (see the instruction's last sentence)."""
    text = re.sub(r"\s+", " ", reminder_text or "").strip().rstrip(".")
    if not text or not request or _ASKED_FOR_REMINDER_RE.search(request):
        return None
    if not _JARVIS_WORK_RE.match(text) or not _WORK_VERB_RE.search(request):
        return None
    text = re.sub(r"^\s*(?:please\s+)?(?:to\s+)?", "", text)
    text = re.sub(r"\s+as (?:requested|asked)$", "", text, flags=re.I)
    body = text[:1].upper() + text[1:]
    return (f"{body}. Then tell the user the result. (If this turns out to be something only the user can do, "
            f"just remind them: \"Reminder: {body}.\")")


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (t or "").lower())).strip()


def _tokens(t: str) -> set[str]:
    return {w for w in _norm(t).split() if len(w) > 2}


def _similar(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.6


def schedule(store: Store, instruction: str, due_at: datetime, source_quote: str = "", origin: str = "user",
             kind: str = "execute_jarvis", now: datetime | None = None) -> tuple[int | None, str]:
    """-> (job id or None, message). A near-identical pending job due within DEDUPE_WINDOW_MIN is reused, so
    one request (seen by both the live tool call and autonomy's extraction) never becomes two runs."""
    instruction = re.sub(r"\s+", " ", (instruction or "")).strip()[:2000]
    if not instruction:
        return None, "Nothing to schedule: say what Jarvis should do."
    if kind not in KINDS:
        return None, f"kind must be one of {', '.join(KINDS)}."
    now = now or datetime.now()
    if due_at < now - timedelta(minutes=1):
        return None, "That time has already passed."
    lo = (due_at - timedelta(minutes=DEDUPE_WINDOW_MIN)).isoformat(timespec="seconds")
    hi = (due_at + timedelta(minutes=DEDUPE_WINDOW_MIN)).isoformat(timespec="seconds")
    for j in store.q("SELECT id, instruction FROM autonomy_deferred_jobs WHERE status IN ('pending','running') "
                     "AND kind=? AND due_at BETWEEN ? AND ?", (kind, lo, hi)):
        if _similar(j["instruction"], instruction):
            return j["id"], f"Already scheduled as job #{j['id']}."
    jid = store.q("INSERT INTO autonomy_deferred_jobs (due_at, kind, instruction, source_quote, origin, created_at) "
                  "VALUES (?, ?, ?, ?, ?, ?)", (due_at.isoformat(timespec="seconds"), kind, instruction,
                                                (source_quote or "")[:500], origin, now.isoformat(timespec="seconds")),
                  write=True)
    return jid, f"Scheduled job #{jid} for {due_at.strftime('%A %H:%M')}: {instruction[:120]}"


def claim_due(store: Store, now: datetime | None = None, limit: int = 1,
              still_running: set | None = None) -> list[dict]:
    """Due jobs, each atomically moved pending -> running (a second caller gets nothing). A job left 'running'
    STALE_RUNNING_MIN by a crash is retried, but never one this process is still running (`still_running`)."""
    now = now or datetime.now()
    stale = (now - timedelta(minutes=STALE_RUNNING_MIN)).isoformat(timespec="seconds")
    for j in store.q("SELECT id, instruction, attempts FROM autonomy_deferred_jobs WHERE status='running' "
                     "AND started_at < ?", (stale,)):
        if j["id"] in (still_running or set()):
            continue
        # Audit 2026-10-04: "git pull then restart yourself" is cut off by its own restart (Jarvis exits ~8 s later,
        # often before the job is marked done), and a stale job was retried with no attempt limit: Jarvis restarted
        # itself every 90 minutes, for ever. A job that asked for the restart is finished by it; any other stale job
        # is retried only while it has attempts left.
        if _RESTART_RE.search(j["instruction"] or ""):
            status, result = "done", "Jarvis restarted during this job (the job asked for a restart), so it isn't run again."
        elif (j["attempts"] or 0) >= MAX_ATTEMPTS:
            status, result = "failed", f"Cut off {j['attempts']} times (Jarvis stopped or restarted mid-job); not run again."
        else:
            status, result = "pending", None
        if status == "pending":
            store.q("UPDATE autonomy_deferred_jobs SET status='pending' WHERE id=? AND status='running'",
                    (j["id"],), write=True)
        else:
            store.q("UPDATE autonomy_deferred_jobs SET status=?, result=?, finished_at=? WHERE id=? AND status='running'",
                    (status, result, now.isoformat(timespec="seconds"), j["id"]), write=True)
    claimed = []
    for j in store.q("SELECT * FROM autonomy_deferred_jobs WHERE status='pending' AND due_at <= ? ORDER BY due_at "
                     "LIMIT ?", (now.isoformat(timespec="seconds"), limit)):
        if store.q("UPDATE autonomy_deferred_jobs SET status='running', started_at=?, attempts=attempts+1 WHERE id=? "
                   "AND status='pending'", (now.isoformat(timespec="seconds"), j["id"]), write=True):
            j["attempts"] += 1
            claimed.append(j)
    return claimed


def finish(store: Store, jid: int, ok: bool, result: str, attempts: int, now: datetime | None = None) -> str:
    """-> final status. A failure before MAX_ATTEMPTS goes back to pending, RETRY_MIN later."""
    now = now or datetime.now()
    if ok:
        status, due = "done", None
    elif attempts < MAX_ATTEMPTS:
        status, due = "pending", (now + timedelta(minutes=RETRY_MIN)).isoformat(timespec="seconds")
    else:
        status, due = "failed", None
    if due:
        store.q("UPDATE autonomy_deferred_jobs SET status=?, result=?, due_at=? WHERE id=?",
                (status, (result or "")[:2000], due, jid), write=True)
    else:
        store.q("UPDATE autonomy_deferred_jobs SET status=?, result=?, finished_at=? WHERE id=?",
                (status, (result or "")[:2000], now.isoformat(timespec="seconds"), jid), write=True)
    return status


def release(store: Store, jid: int) -> None:
    """Back to pending without counting an attempt (e.g. it was claimed while the user was mid-command)."""
    store.q("UPDATE autonomy_deferred_jobs SET status='pending', attempts=MAX(0, attempts-1) WHERE id=? AND "
            "status='running'", (jid,), write=True)


def cancel(store: Store, jid: int) -> bool:
    return bool(store.q("UPDATE autonomy_deferred_jobs SET status='cancelled', finished_at=? WHERE id=? AND "
                        "status='pending'", (datetime.now().isoformat(timespec="seconds"), int(jid)), write=True))


def list_jobs(store: Store, include_finished: bool = False, limit: int = 30) -> list[dict]:
    where = "" if include_finished else "WHERE status IN ('pending','running')"
    return store.q(f"SELECT * FROM autonomy_deferred_jobs {where} ORDER BY due_at DESC LIMIT ?", (limit,))


def next_pending(store: Store) -> dict | None:
    rows = store.q("SELECT * FROM autonomy_deferred_jobs WHERE status='pending' ORDER BY due_at LIMIT 1")
    return rows[0] if rows else None


def prune(store: Store, keep_days: int = 60) -> None:
    cut = (datetime.now() - timedelta(days=keep_days)).isoformat(timespec="seconds")
    store.q("DELETE FROM autonomy_deferred_jobs WHERE status IN ('done','failed','cancelled') AND created_at < ?",
            (cut,), write=True)
