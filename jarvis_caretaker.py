"""Caretaker (2026-10-16): Jarvis looks after the laptop and after itself, and fixes what it can
on its own.

The loop is: NOTICE a problem (cheap checks, no model call) -> work out the CAUSE -> FIX it with a
ready-made recipe ("playbook") or, for a problem nobody wrote a fix for, ask the model for a plan
made only of allowed actions -> CHECK the fix worked -> LEARN (a model fix that works twice becomes
a playbook).

Autonomy without nagging comes from making actions *undoable*, not from dropping the safety checks:
- caches / temp files are deleted outright (they rebuild themselves),
- the user's own files are moved to a holding folder for HOLDING_DAYS and only then really removed
  ("undo the cleanup" puts them back),
- settings are snapshotted before a change.
Anything undoable (GREEN/YELLOW) runs on its own and is reported afterwards; the irreversible tier
(RED: shutdown/format/wipe/force-close/uninstall) still goes through jarvis.py's existing
catastrophic confirmation gate, unchanged.

This module is PURE: it never imports jarvis.py and never touches the OS itself. jarvis.py hands it
a DB-connect callable (like jarvis_selfaware) and the OS-specific probing/fixing lives in jarvis.py
as thin adapters, so every decision here is testable on any platform.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# --- tunables (jarvis.py overrides from env where it wires them in) -----------------------------
DISK_WARN_PERCENT = 85.0        # a drive at/above this is worth a finding
DISK_HIGH_PERCENT = 90.0        # at/above this it is urgent: free space now (Recycle Bin, not holding)
DISK_FREE_TARGET = 0.15         # stop a cleanup once this fraction of the drive is free again
HOLDING_DAYS = 7                # how long the user's own files sit in the holding folder before real deletion
RECYCLE_OLDER_DAYS = 30         # only purge Recycle Bin items at least this old
KEEP_UNUSED_MONTHS = 6          # a big file not opened in this long is a cleanup *suggestion*, never auto-moved
PROCESS_CPU_PERCENT = 35.0      # a process sustained at/above this for PROCESS_SUSTAINED_MIN is a hog
PROCESS_SUSTAINED_MIN = 10
CRASH_COUNT_TODAY = 3           # an app that crashed at least this many times today is a finding
BATTERY_WEAR_PERCENT = 70.0     # battery holding less than this fraction of design capacity is worn

MAX_ATTEMPTS = 3                # per issue, before Jarvis gives up and says so once
MAX_ACTIONS_PER_HOUR = 10       # a runaway fix loop can't do more than this
MAX_MOVE_GB_PER_DAY = 25.0      # cap on how much the user's data a cleanup may move in a day

# Risk tiers. GREEN/YELLOW run on their own; RED is routed to jarvis.py's catastrophic gate.
GREEN, YELLOW, RED = "green", "yellow", "red"

SEVERITIES = ("info", "warn", "high", "critical")


# A sensor "owns" these categories: when it ran fine and no longer reports one, that issue is resolved.
SENSOR_CATEGORIES = {
    "storage": {"storage"}, "processes": {"process"}, "crashes": {"crash"}, "disk_health": {"disk_health"},
    "updates": {"update"}, "network": {"network"}, "battery": {"battery"},
    "self": {"self_skill", "self_job", "self_agent", "self_mcp", "self_doctor", "self_crash", "self_other"},
}
GAVE_UP_RETRY_HOURS = 24        # an issue Jarvis gave up on is tried again after this long, with a clean slate


# --- findings (what a sensor noticed) -----------------------------------------------------------
@dataclass
class Finding:
    key: str                    # stable id for this problem, e.g. "disk:C" or "skill:gmail_watch"
    category: str               # which playbook family: storage|process|crash|disk_health|update|network|
                                #   battery|self_skill|self_agent|self_job|self_mcp|self_doctor|self_crash|other
    severity: str               # one of SEVERITIES
    title: str                  # one plain sentence for the dashboard/summary
    evidence: dict = field(default_factory=dict)   # raw numbers/strings the fix and the report use

    def as_row(self) -> dict:
        return {"key": self.key, "category": self.category, "severity": self.severity,
                "title": self.title, "evidence": self.evidence}


def _sev(level: str) -> str:
    return level if level in SEVERITIES else "warn"


# --- sensor classifiers: raw numbers in, a Finding or None out (pure, so unit-tested) -----------
def storage_finding(drive: str, percent: float, free_gb: float,
                     reclaimable_gb: float = 0.0, grew_gb_today: float = 0.0) -> Finding | None:
    """Classify one drive. jarvis.py reads the numbers from psutil and the cache-folder sizes."""
    if percent < DISK_WARN_PERCENT:
        return None
    sev = "high" if percent >= DISK_HIGH_PERCENT else "warn"
    if percent >= 97.0:
        sev = "critical"
    bits = [f"{drive} is {percent:.0f}% full ({free_gb:.1f} GB free)"]
    if grew_gb_today >= 1.0:
        bits.append(f"up {grew_gb_today:.1f} GB today")
    if reclaimable_gb >= 0.5:
        bits.append(f"about {reclaimable_gb:.1f} GB looks reclaimable")
    return Finding(key=f"disk:{drive}", category="storage", severity=sev,
                   title="; ".join(bits) + ".",
                   evidence={"drive": drive, "percent": percent, "free_gb": free_gb,
                             "reclaimable_gb": reclaimable_gb, "grew_gb_today": grew_gb_today,
                             "urgent": percent >= DISK_HIGH_PERCENT})


def process_finding(name: str, cpu_percent: float, sustained_min: float,
                    in_front: bool, pid: int | None = None) -> Finding | None:
    if cpu_percent < PROCESS_CPU_PERCENT or sustained_min < PROCESS_SUSTAINED_MIN:
        return None
    return Finding(key=f"proc:{name.lower()}", category="process",
                   severity="high" if cpu_percent >= 70 else "warn",
                   title=f"{name} has been using {cpu_percent:.0f}% CPU for {sustained_min:.0f} minutes.",
                   evidence={"name": name, "cpu_percent": cpu_percent, "sustained_min": sustained_min,
                             "in_front": bool(in_front), "pid": pid})


def crash_finding(app: str, count_today: int, module: str = "") -> Finding | None:
    if count_today < CRASH_COUNT_TODAY:
        return None
    t = f"{app} has crashed {count_today} times today"
    if module:
        t += f" (faulting module {module})"
    return Finding(key=f"crash:{app.lower()}", category="crash", severity="warn",
                   title=t + ".", evidence={"app": app, "count_today": count_today, "module": module})


def disk_health_finding(drive: str, status: str) -> Finding | None:
    """status from Get-PhysicalDisk HealthStatus: Healthy|Warning|Unhealthy. Never auto-fixed."""
    s = (status or "").strip().lower()
    if s in ("", "healthy"):
        return None
    return Finding(key=f"diskhealth:{drive}", category="disk_health", severity="critical",
                   title=f"The disk reports '{status}' health. Back up important files now.",
                   evidence={"drive": drive, "status": status})


def update_finding(failed_count: int, defender_defs_age_days: int | None = None) -> Finding | None:
    bits = []
    if failed_count >= 2:
        bits.append(f"Windows Update has failed {failed_count} times")
    if defender_defs_age_days is not None and defender_defs_age_days >= 7:
        bits.append(f"virus definitions are {defender_defs_age_days} days old")
    if not bits:
        return None
    return Finding(key="update:windows", category="update", severity="warn",
                   title="; ".join(bits) + ".",
                   evidence={"failed_count": failed_count, "defs_age_days": defender_defs_age_days})


def network_finding(gateway_ok: bool, dns_ok: bool, adapter_up: bool) -> Finding | None:
    if adapter_up and gateway_ok and dns_ok:
        return None
    if not adapter_up:
        title, detail = "The network adapter is down.", "adapter_down"
    elif not gateway_ok:
        title, detail = "The router isn't reachable.", "gateway_unreachable"
    else:
        title, detail = "Online, but name lookups (DNS) are failing.", "dns_failing"
    return Finding(key="network:lan", category="network", severity="warn",
                   title=title, evidence={"detail": detail, "gateway_ok": gateway_ok,
                                          "dns_ok": dns_ok, "adapter_up": adapter_up})


def battery_finding(design_fraction: float | None) -> Finding | None:
    if design_fraction is None or design_fraction * 100 >= BATTERY_WEAR_PERCENT:
        return None
    return Finding(key="battery:wear", category="battery", severity="info",
                   title=f"The battery now holds about {design_fraction*100:.0f}% of its original charge.",
                   evidence={"design_fraction": design_fraction})


def self_failure_finding(kind: str, name: str, error: str, count: int) -> Finding | None:
    """Jarvis's own repeated failures. kind: skill|agent|job|mcp|doctor|crash. jarvis.py reads the count
    from its own tables (failed runs, down servers, doctor problems, crash log)."""
    kind = kind.lower()
    if kind not in ("skill", "agent", "job", "mcp", "doctor", "crash"):
        kind = "other"
    threshold = 1 if kind in ("mcp", "doctor", "crash") else 2
    if count < threshold:
        return None
    who = f"{kind} {name}".strip()
    sev = "high" if count >= 4 else "warn"
    return Finding(key=f"self_{kind}:{name.lower()}", category=f"self_{kind}", severity=sev,
                   title=f"Jarvis's {who} has been failing ({count}x): {error[:120].strip().rstrip('.')}.",
                   evidence={"kind": kind, "name": name, "error": error, "count": count})


# --- issue tracker: the memory that stops Jarvis repeating itself -------------------------------
class Store:
    """caretaker_issues (one row per problem, so 'this keeps failing' is a count) and
    caretaker_actions (every fix step, with how to undo it). jarvis.py passes a connect callable."""

    def __init__(self, connect):
        self._connect = connect

    def _conn(self) -> sqlite3.Connection:
        c = self._connect()
        c.execute("""CREATE TABLE IF NOT EXISTS caretaker_issues (
            key TEXT PRIMARY KEY, category TEXT, severity TEXT, title TEXT, evidence TEXT,
            status TEXT DEFAULT 'open', attempts INTEGER DEFAULT 0, tried TEXT,
            first_seen TEXT, last_seen TEXT, resolved_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS caretaker_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, issue_key TEXT, ts TEXT, tier TEXT,
            action TEXT, detail TEXT, result TEXT, freed_bytes INTEGER DEFAULT 0,
            undo TEXT, undone INTEGER DEFAULT 0)""")
        return c

    def ingest(self, findings: list[Finding]) -> list[dict]:
        """Upsert findings. A key already 'ignored' stays ignored; a key that was 'fixed' and is
        seen again reopens. Returns the rows that are open and still need work."""
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as c:
            for f in findings:
                row = c.execute("SELECT status, first_seen FROM caretaker_issues WHERE key=?",
                                (f.key,)).fetchone()
                if row is None:
                    c.execute("""INSERT INTO caretaker_issues
                        (key,category,severity,title,evidence,status,attempts,first_seen,last_seen)
                        VALUES (?,?,?,?,?,'open',0,?,?)""",
                              (f.key, f.category, f.severity, f.title,
                               json.dumps(f.evidence), now, now))
                    continue
                status, first_seen = row
                if status == "ignored":
                    c.execute("UPDATE caretaker_issues SET last_seen=?,severity=?,title=?,evidence=? WHERE key=?",
                              (now, f.severity, f.title, json.dumps(f.evidence), f.key))
                    continue
                if status == "gave_up":
                    gu = c.execute("SELECT resolved_at FROM caretaker_issues WHERE key=?", (f.key,)).fetchone()[0]
                    try:
                        retry = datetime.now() - datetime.fromisoformat(gu) >= timedelta(hours=GAVE_UP_RETRY_HOURS)
                    except (TypeError, ValueError):
                        retry = True
                    if not retry:   # still the same problem: keep it as gave_up, just refresh what it looks like
                        c.execute("UPDATE caretaker_issues SET severity=?,title=?,evidence=?,last_seen=? WHERE key=?",
                                  (f.severity, f.title, json.dumps(f.evidence), now, f.key))
                        continue
                    c.execute("UPDATE caretaker_issues SET attempts=0,tried=NULL WHERE key=?", (f.key,))
                new_status = "open" if status in ("fixed", "resolved", "gave_up") else status
                c.execute("""UPDATE caretaker_issues SET severity=?,title=?,evidence=?,status=?,
                             last_seen=?,resolved_at=NULL WHERE key=?""",
                          (f.severity, f.title, json.dumps(f.evidence), new_status, now, f.key))
        return self.open_issues()

    def resolve_missing(self, current_keys: set, sensors_ok: set) -> list[str]:
        """Close issues whose sensor ran fine and no longer reports them. 'fixed' when Jarvis acted on it,
        'resolved' when it went away by itself. Ignored issues are left alone. Returns the keys closed."""
        owned: set = set()
        for name in sensors_ok:
            owned |= SENSOR_CATEGORIES.get(name, set())
        closed: list[str] = []
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as c:
            rows = c.execute("""SELECT key,category FROM caretaker_issues
                                WHERE status IN ('open','fixing','gave_up')""").fetchall()
            for key, cat in rows:
                if key in current_keys or cat not in owned:
                    continue
                acted = c.execute("SELECT 1 FROM caretaker_actions WHERE issue_key=? LIMIT 1", (key,)).fetchone()
                c.execute("UPDATE caretaker_issues SET status=?,resolved_at=? WHERE key=?",
                          ("fixed" if acted else "resolved", now, key))
                closed.append(key)
        return closed

    def open_issues(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("""SELECT key,category,severity,title,evidence,status,attempts,tried,
                                first_seen,last_seen FROM caretaker_issues
                                WHERE status IN ('open','fixing') ORDER BY
                                CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                                WHEN 'warn' THEN 2 ELSE 3 END, last_seen DESC""").fetchall()
        return [self._row(r) for r in rows]

    def visible_issues(self) -> list[dict]:
        """What the owner should see: open work AND problems Jarvis gave up on (those need them most)."""
        with self._conn() as c:
            rows = c.execute("""SELECT key,category,severity,title,evidence,status,attempts,tried,
                                first_seen,last_seen FROM caretaker_issues
                                WHERE status IN ('open','fixing','gave_up') ORDER BY
                                CASE status WHEN 'gave_up' THEN 0 ELSE 1 END,
                                CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                                WHEN 'warn' THEN 2 ELSE 3 END, last_seen DESC""").fetchall()
        return [self._row(r) for r in rows]

    def all_issues(self, limit: int = 100) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("""SELECT key,category,severity,title,evidence,status,attempts,tried,
                                first_seen,last_seen FROM caretaker_issues
                                ORDER BY last_seen DESC LIMIT ?""", (limit,)).fetchall()
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(r) -> dict:
        try:
            ev = json.loads(r[4]) if r[4] else {}
        except (ValueError, TypeError):
            ev = {}
        try:
            tried = json.loads(r[7]) if r[7] else []
        except (ValueError, TypeError):
            tried = []
        return {"key": r[0], "category": r[1], "severity": r[2], "title": r[3], "evidence": ev,
                "status": r[5], "attempts": r[6], "tried": tried,
                "first_seen": r[8], "last_seen": r[9]}

    def get(self, key: str) -> dict | None:
        with self._conn() as c:
            r = c.execute("""SELECT key,category,severity,title,evidence,status,attempts,tried,
                             first_seen,last_seen FROM caretaker_issues WHERE key=?""", (key,)).fetchone()
        return self._row(r) if r else None

    def set_status(self, key: str, status: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        resolved = now if status in ("fixed", "ignored") else None
        with self._conn() as c:
            c.execute("UPDATE caretaker_issues SET status=?,resolved_at=? WHERE key=?",
                      (status, resolved, key))

    def note_attempt(self, key: str, what_failed: str) -> int:
        """Record a failed attempt and what didn't work; returns the new attempt count."""
        iss = self.get(key)
        tried = (iss["tried"] if iss else []) + [what_failed]
        n = (iss["attempts"] if iss else 0) + 1
        status = "gave_up" if n >= MAX_ATTEMPTS else "open"
        with self._conn() as c:
            c.execute("UPDATE caretaker_issues SET attempts=?,tried=?,status=?,resolved_at=? WHERE key=?",
                      (n, json.dumps(tried[-10:]), status,
                       datetime.now().isoformat(timespec="seconds") if status == "gave_up" else None, key))
        return n

    def log_action(self, issue_key: str, tier: str, action: str, detail: str,
                   result: str, freed_bytes: int = 0, undo: dict | None = None) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as c:
            cur = c.execute("""INSERT INTO caretaker_actions
                (issue_key,ts,tier,action,detail,result,freed_bytes,undo)
                VALUES (?,?,?,?,?,?,?,?)""",
                            (issue_key, now, tier, action, detail, result, int(freed_bytes),
                             json.dumps(undo) if undo else None))
            return cur.lastrowid

    def recent_actions(self, limit: int = 50, undoable_only: bool = False) -> list[dict]:
        q = """SELECT id,issue_key,ts,tier,action,detail,result,freed_bytes,undo,undone
               FROM caretaker_actions {} ORDER BY id DESC LIMIT ?"""
        where = "WHERE undo IS NOT NULL AND undone=0" if undoable_only else ""
        with self._conn() as c:
            rows = c.execute(q.format(where), (limit,)).fetchall()
        out = []
        for r in rows:
            try:
                undo = json.loads(r[8]) if r[8] else None
            except (ValueError, TypeError):
                undo = None
            out.append({"id": r[0], "issue_key": r[1], "ts": r[2], "tier": r[3], "action": r[4],
                        "detail": r[5], "result": r[6], "freed_bytes": r[7], "undo": undo,
                        "undone": bool(r[9])})
        return out

    def mark_undone(self, action_id: int) -> None:
        with self._conn() as c:
            c.execute("UPDATE caretaker_actions SET undone=1 WHERE id=?", (action_id,))

    def actions_in_last_hour(self) -> int:
        cutoff = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM caretaker_actions WHERE ts>=?", (cutoff,)).fetchone()[0]

    def bytes_moved_today(self) -> int:
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
        with self._conn() as c:
            r = c.execute("""SELECT COALESCE(SUM(freed_bytes),0) FROM caretaker_actions
                             WHERE ts>=? AND tier=? AND undo IS NOT NULL""", (start, YELLOW)).fetchone()
        return int(r[0] or 0)

    def summary_since(self, hours: int = 24) -> dict:
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
        with self._conn() as c:
            # Yellow actions MOVE files to the holding folder: that frees nothing until the days are up, so it is
            # reported as "held", never counted as freed space.
            freed = c.execute("SELECT COALESCE(SUM(freed_bytes),0) FROM caretaker_actions WHERE ts>=? AND tier!=?",
                              (cutoff, YELLOW)).fetchone()[0]
            held = c.execute("""SELECT COALESCE(SUM(freed_bytes),0) FROM caretaker_actions
                                WHERE ts>=? AND tier=? AND undo IS NOT NULL AND undone=0""",
                             (cutoff, YELLOW)).fetchone()[0]
            fixed = c.execute("""SELECT COUNT(*) FROM caretaker_issues
                                 WHERE status='fixed' AND resolved_at>=?""", (cutoff,)).fetchone()[0]
            acted = c.execute("SELECT COUNT(*) FROM caretaker_actions WHERE ts>=?", (cutoff,)).fetchone()[0]
            gave_up = c.execute("""SELECT key,title FROM caretaker_issues
                                   WHERE status='gave_up' AND last_seen>=?""", (cutoff,)).fetchall()
        return {"freed_bytes": int(freed or 0), "held_bytes": int(held or 0), "fixed": fixed, "actions": acted,
                "gave_up": [{"key": g[0], "title": g[1]} for g in gave_up]}


# --- budgets / policy (pure) --------------------------------------------------------------------
def budget_blocked(store: Store, move_bytes: int = 0) -> str | None:
    """Why the caretaker must not act right now (None = go ahead). A runaway fix loop can't exceed
    these; they are the circuit breaker the AIOps guardrail literature calls for."""
    if store.actions_in_last_hour() >= MAX_ACTIONS_PER_HOUR:
        return f"already did {MAX_ACTIONS_PER_HOUR} fixes this hour"
    if move_bytes and store.bytes_moved_today() + move_bytes > MAX_MOVE_GB_PER_DAY * (1024 ** 3):
        return f"would move more than {MAX_MOVE_GB_PER_DAY:.0f} GB of your files today"
    return None


def human_bytes(n: int | float) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit not in ("B", "KB") else f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
