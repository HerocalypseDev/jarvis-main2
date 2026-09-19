"""Sleep Mode for Jarvis.

Self-contained, like the other jarvis_*.py modules: owns its own sqlite tables in
jarvis_memory.db, no import-time dependency back on jarvis.py. jarvis.py wires it in by
passing callbacks (run_system_action, speak_fn) rather than this module importing jarvis.py
directly, and by calling should_suppress()/tts_overrides()/system_prompt_context_line() from
its own notification/TTS/prompt-building code.

What's real, on this Windows desktop-assistant architecture:
  - Notification/reminder quieting: should_suppress() gates jarvis.py's existing
    queue_or_deliver_notification the same way its work-hours busy check already does —
    urgent=True (already used for medication/security-style alerts) or a whitelisted sender
    always gets through; everything else queues until sleep mode ends.
  - Dark mode: real Windows registry toggle (AppsUseLightTheme/SystemUsesLightTheme).
  - Volume: lowered/restored via the existing relative volume_up/down system actions (no
    absolute volume API is wired up in jarvis.py, so this is N steps down, N steps up).
  - Distraction blocking: real hosts-file redirect of a configurable domain list. Needs the
    process to be elevated (admin) to write %SystemRoot%\\System32\\drivers\\etc\\hosts; if
    it isn't, this fails soft with a warning instead of breaking the rest of sleep mode.
  - Sleep tracking: real sqlite log of start/end/duration, with a rolling history summary.
  - Smart wake-up: a scheduled gradual volume ramp + spoken morning line, checked from
    jarvis.py's existing 60s scheduler tick — no new background thread needed.
  - Calmer voice: real Piper SynthesisConfig knobs (length_scale slower, volume softer).
  - Ambient sound / breathing: opens a curated calming stream, or speaks a short guided
    breathing script through the existing TTS.

What's explicitly NOT implemented (would need each app's own API/OS integration, not
reachable from a local script): muting Discord/WhatsApp/Gmail's own native notifications,
Windows Focus Assist / Night Light (registry-undocumented and unreliable across builds),
filtering YouTube/streaming recommendations, and calendar UI changes.
"""

from __future__ import annotations

import logging
import math
import os
import sqlite3
import sys
import threading
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("jarvis.sleep_mode")

# --- config (overridable via .env, same convention as jarvis.py) -----------------------
WHITELIST_CONTACTS = [
    c.strip().lower()
    for c in (os.environ.get("JARVIS_SLEEP_WHITELIST_CONTACTS") or "").split(",")
    if c.strip()
]
BLOCK_DOMAINS = [
    d.strip().lower()
    for d in (
        os.environ.get("JARVIS_SLEEP_BLOCK_DOMAINS")
        or "youtube.com,twitter.com,x.com,reddit.com,instagram.com,tiktok.com,facebook.com"
    ).split(",")
    if d.strip()
]
VOLUME_DOWN_STEPS = int(os.environ.get("JARVIS_SLEEP_VOLUME_STEPS") or 8)
DEFAULT_WAKE_RAMP_MINUTES = int(os.environ.get("JARVIS_SLEEP_WAKE_RAMP_MINUTES") or 10)
MEDIA_AUTOPAUSE_MINUTES = int(os.environ.get("JARVIS_SLEEP_MEDIA_AUTOPAUSE_MINUTES") or 30)
# Calmer TTS: slower (higher length_scale) and quieter (lower volume) than the default 1.0/1.0.
SLEEP_LENGTH_SCALE = float(os.environ.get("JARVIS_SLEEP_TTS_LENGTH_SCALE") or 1.25)
SLEEP_TTS_VOLUME = float(os.environ.get("JARVIS_SLEEP_TTS_VOLUME") or 0.7)

# Sleep stats: a Sleep Mode session shorter than this is treated as an accidental toggle, not a
# night's sleep, and left out of averages. Goal is the nightly target used for "sleep debt".
MIN_SESSION_MINUTES = int(os.environ.get("JARVIS_SLEEP_MIN_SESSION_MINUTES") or 20)
SLEEP_GOAL_HOURS = float(os.environ.get("JARVIS_SLEEP_GOAL_HOURS") or 8)
# A nap is a session the user starts with nap mode (enable(kind="nap")). Naps are tracked on
# their own and never count toward night averages, bedtime, sleep debt or the goal streak. A nap
# shorter than NAP_MIN_MINUTES is treated as an accidental toggle and ignored.
NAP_MIN_MINUTES = int(os.environ.get("JARVIS_NAP_MIN_MINUTES") or 10)

AMBIENT_SOUNDS = {
    "rain": "https://www.youtube.com/results?search_query=rain+sounds+for+sleep+10+hours",
    "white_noise": "https://www.youtube.com/results?search_query=white+noise+for+sleep+10+hours",
    "lofi": "https://www.youtube.com/results?search_query=lofi+sleep+ambient+mix",
    "meditation": "https://www.youtube.com/results?search_query=sleep+meditation+guided",
}

BREATHING_SCRIPT: list[tuple[str, float]] = [
    ("Let's do a short breathing exercise. Get comfortable.", 2.0),
    ("Breathe in slowly through your nose.", 4.0),
    ("Hold it.", 4.0),
    ("Breathe out slowly through your mouth.", 6.0),
    ("One more. Breathe in.", 4.0),
    ("Hold.", 4.0),
    ("And out, slowly.", 6.0),
    ("Good. Let your body settle. Goodnight.", 0.0),
]


def _db_path() -> Path:
    override = (os.environ.get("JARVIS_MEMORY_DB_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent / "jarvis_memory.db"


_db_lock = threading.Lock()
# jarvis.py registers this so disable() can hand off "what was queued while you slept" without
# this module importing jarvis.py. Called as handler(started_at_iso, ended_at_iso, kind).
_wake_digest_handler = None


def set_wake_digest_handler(fn) -> None:
    global _wake_digest_handler
    _wake_digest_handler = fn


def save_digest(started_at: str, digest: str) -> None:
    with _db_lock:
        conn = _connect()
        try:
            conn.execute(
                "UPDATE sleep_log SET digest = ? WHERE started_at = ?", (digest, started_at)
            )
            conn.commit()
        finally:
            conn.close()


_media_autopause_timer: threading.Timer | None = None


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sleep_state ("
        "id INTEGER PRIMARY KEY CHECK (id = 1), "
        "active INTEGER NOT NULL DEFAULT 0, "
        "started_at TEXT, "
        "wake_time TEXT, "
        "wake_ramp_minutes INTEGER, "
        "wake_fired_date TEXT, "
        "dark_mode_was_on INTEGER, "
        "hosts_blocked INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sleep_log ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "started_at TEXT NOT NULL, "
        "ended_at TEXT, "
        "duration_minutes REAL)"
    )
    for ddl in (
        "ALTER TABLE sleep_log ADD COLUMN digest TEXT",
        "ALTER TABLE sleep_log ADD COLUMN kind TEXT",    # 'sleep' | 'nap'; NULL (old rows) = sleep
        "ALTER TABLE sleep_state ADD COLUMN kind TEXT",
    ):
        try:
            conn.execute(ddl)
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.execute("INSERT OR IGNORE INTO sleep_state (id, active) VALUES (1, 0)")
    return conn


def _get_state() -> dict:
    with _db_lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT active, started_at, wake_time, wake_ramp_minutes, wake_fired_date, "
                "dark_mode_was_on, hosts_blocked, kind FROM sleep_state WHERE id = 1"
            ).fetchone()
        finally:
            conn.close()
    keys = (
        "active", "started_at", "wake_time", "wake_ramp_minutes", "wake_fired_date",
        "dark_mode_was_on", "hosts_blocked", "kind",
    )
    return dict(zip(keys, row)) if row else {k: None for k in keys}


def _set_state(**fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    with _db_lock:
        conn = _connect()
        try:
            conn.execute(f"UPDATE sleep_state SET {cols} WHERE id = 1", list(fields.values()))
            conn.commit()
        finally:
            conn.close()


def started_at() -> str | None:
    """ISO start time of the current Sleep Mode session, or None if it's off."""
    state = _get_state()
    return state.get("started_at") if state.get("active") else None


def is_active() -> bool:
    return bool(_get_state().get("active"))


def is_whitelisted_sender(sender: str | None) -> bool:
    if not sender:
        return False
    s = sender.strip().lower()
    return any(w in s or s in w for w in WHITELIST_CONTACTS)


def should_suppress(urgent: bool, sender: str | None = None) -> bool:
    """True if a notification should be queued (silenced) rather than spoken/pushed
    immediately. Mirrors jarvis.py's existing work-hours busy gate: urgent always wins,
    a whitelisted sender (family/emergency contacts) always wins."""
    if not is_active():
        return False
    if urgent or is_whitelisted_sender(sender):
        return False
    return True


def system_prompt_context_line() -> str:
    if not is_active():
        return ""
    return (
        "\n\nSleep Mode is currently active: keep replies to one or two short sentences, use "
        "a calm and gentle tone, don't ask clarifying questions unless truly necessary, and "
        "avoid loud/bright actions (opening new windows, playing media at volume) unless the "
        "user clearly asked for them."
    )


def tts_overrides() -> dict | None:
    """Piper SynthesisConfig kwargs for calmer speech while Sleep Mode is active, or None."""
    if not is_active():
        return None
    return {"length_scale": SLEEP_LENGTH_SCALE, "volume": SLEEP_TTS_VOLUME}


def fish_audio_prosody_overrides() -> dict | None:
    """Fish Audio's prosody equivalent of tts_overrides() above — same calmer/quieter-at-night
    intent, translated from Piper's length_scale (a slowdown multiplier, higher = slower) and
    linear 0-1 volume into Fish Audio's speed (0.5-2.0, lower = slower) and volume in dB. Not a
    precise unit conversion between the two engines, just the same intent carried over."""
    if not is_active():
        return None
    speed = (1.0 / SLEEP_LENGTH_SCALE) if SLEEP_LENGTH_SCALE else 1.0
    volume_db = 20 * math.log10(SLEEP_TTS_VOLUME) if SLEEP_TTS_VOLUME > 0 else 0.0
    return {"speed": max(0.5, min(2.0, speed)), "volume": volume_db}


# --- Windows dark mode (real registry toggle) -------------------------------------------
def _dark_mode_is_on() -> bool | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return value == 0
    except OSError as e:
        log.warning("Could not read current theme: %s", e)
        return None


def _set_dark_mode(dark: bool) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            0,
            winreg.KEY_SET_VALUE,
        )
        value = 0 if dark else 1
        winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, value)
        winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, value)
        winreg.CloseKey(key)
        return True
    except OSError as e:
        log.warning("Could not set theme: %s", e)
        return False


# --- distraction blocking (real hosts-file redirect; needs admin to write) --------------
_HOSTS_BLOCK_MARK = "# jarvis-sleep-mode"


def _hosts_path() -> Path:
    return Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "drivers" / "etc" / "hosts"


def _block_distractions() -> bool:
    if sys.platform != "win32" or not BLOCK_DOMAINS:
        return False
    path = _hosts_path()
    try:
        original = path.read_text(encoding="utf-8", errors="ignore")
        if _HOSTS_BLOCK_MARK in original:
            return True  # already blocked (e.g. from a prior crash before disable ran)
        lines = [f"127.0.0.1 {d} {_HOSTS_BLOCK_MARK}" for d in BLOCK_DOMAINS]
        lines += [f"127.0.0.1 www.{d} {_HOSTS_BLOCK_MARK}" for d in BLOCK_DOMAINS]
        with path.open("a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(lines) + "\n")
        return True
    except OSError as e:
        log.warning(
            "Could not edit hosts file to block distractions (run as admin?): %s", e
        )
        return False


def _unblock_distractions() -> None:
    if sys.platform != "win32":
        return
    path = _hosts_path()
    try:
        original = path.read_text(encoding="utf-8", errors="ignore")
        if _HOSTS_BLOCK_MARK not in original:
            return
        kept = [ln for ln in original.splitlines() if _HOSTS_BLOCK_MARK not in ln]
        path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    except OSError as e:
        log.warning("Could not remove hosts-file blocks (run as admin?): %s", e)


# --- media auto-pause --------------------------------------------------------------------
def _cancel_media_autopause() -> None:
    global _media_autopause_timer
    if _media_autopause_timer is not None:
        _media_autopause_timer.cancel()
        _media_autopause_timer = None


def _start_media_autopause(run_system_action) -> None:
    global _media_autopause_timer
    _cancel_media_autopause()

    def _pause():
        try:
            run_system_action("media_stop")
            log.info("Sleep Mode: auto-paused media after %d minutes.", MEDIA_AUTOPAUSE_MINUTES)
        except Exception as e:
            log.warning("Sleep Mode media auto-pause failed: %s", e)

    _media_autopause_timer = threading.Timer(MEDIA_AUTOPAUSE_MINUTES * 60, _pause)
    _media_autopause_timer.daemon = True
    _media_autopause_timer.start()


# --- enable/disable ------------------------------------------------------------------------
def enable(run_system_action, speak_fn, kind: str = "sleep") -> str:
    """kind='nap' runs the exact same mode (quiet notifications, mail take-over, dark mode, recap on
    wake) but the session is logged as a nap and never counts toward sleep time."""
    kind = "nap" if kind == "nap" else "sleep"
    if is_active():
        return "Sleep Mode is already on."

    was_dark = _dark_mode_is_on()
    _set_dark_mode(True)
    hosts_ok = _block_distractions()
    try:
        for _ in range(VOLUME_DOWN_STEPS):
            run_system_action("volume_down")
    except Exception as e:
        log.warning("Sleep Mode could not lower volume: %s", e)
    _start_media_autopause(run_system_action)

    now = datetime.now()
    _set_state(
        active=1,
        started_at=now.isoformat(timespec="seconds"),
        dark_mode_was_on=(1 if was_dark else 0) if was_dark is not None else None,
        hosts_blocked=1 if hosts_ok else 0,
        kind=kind,
    )
    with _db_lock:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO sleep_log (started_at, kind) VALUES (?, ?)",
                (now.isoformat(timespec="seconds"), kind),
            )
            conn.commit()
        finally:
            conn.close()

    label = "Nap mode" if kind == "nap" else "Sleep Mode"
    try:
        speak_fn(f"{label} on. I'll keep things quiet — only urgent or family messages will come through.")
    except Exception as e:
        log.warning("Sleep Mode speak failed: %s", e)
    log.info("%s enabled.", label)
    return (f"{label} is on: notifications quieted, dark mode on, volume lowered, media will "
            "auto-pause." + (" This nap won't count toward your sleep time." if kind == "nap" else ""))


def disable() -> str:
    state = _get_state()
    if not state.get("active"):
        return "Sleep Mode is already off."

    _cancel_media_autopause()
    if not state.get("dark_mode_was_on"):
        _set_dark_mode(False)
    if state.get("hosts_blocked"):
        _unblock_distractions()

    now = datetime.now()
    duration_line = ""
    started_at = state.get("started_at")
    if started_at:
        try:
            started = datetime.fromisoformat(started_at)
            minutes = (now - started).total_seconds() / 60
            hours, mins = divmod(int(minutes), 60)
            duration_line = (
                f" Nap logged: {hours}h {mins}m. It doesn't count toward your sleep time."
                if state.get("kind") == "nap"
                else f" You were in Sleep Mode for {hours}h {mins}m."
            )
            with _db_lock:
                conn = _connect()
                try:
                    conn.execute(
                        "UPDATE sleep_log SET ended_at = ?, duration_minutes = ? "
                        "WHERE started_at = ? AND ended_at IS NULL",
                        (now.isoformat(timespec="seconds"), minutes, started_at),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except ValueError:
            pass

    _set_state(
        active=0, started_at=None, wake_time=None, wake_ramp_minutes=None,
        wake_fired_date=None, dark_mode_was_on=None, hosts_blocked=0, kind=None,
    )
    log.info("Sleep Mode disabled.%s", duration_line)
    if _wake_digest_handler and started_at:
        try:
            _wake_digest_handler(started_at, now.isoformat(timespec="seconds"), state.get("kind") or "sleep")
        except Exception as e:
            log.warning("Sleep Mode wake digest failed: %s", e)
    return f"Sleep Mode is off.{duration_line}"


def toggle(run_system_action, speak_fn) -> str:
    return disable() if is_active() else enable(run_system_action, speak_fn)


def status() -> str:
    state = _get_state()
    lines = []
    if state.get("active"):
        started_at = state.get("started_at")
        since = ""
        if started_at:
            try:
                started = datetime.fromisoformat(started_at)
                minutes = (datetime.now() - started).total_seconds() / 60
                hours, mins = divmod(int(minutes), 60)
                since = f" (on for {hours}h {mins}m)"
            except ValueError:
                pass
        lines.append(f"Sleep Mode is ON{since}.")
        if state.get("wake_time"):
            lines.append(f"Wake-up alarm set for {state['wake_time']}.")
    else:
        lines.append("Sleep Mode is OFF.")

    with _db_lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT kind, duration_minutes FROM sleep_log "
                "WHERE duration_minutes IS NOT NULL ORDER BY id DESC LIMIT 30"
            ).fetchall()
        finally:
            conn.close()
    nights, naps = [], []
    for kind, minutes in rows:
        (naps if kind == "nap" else nights).append(minutes)
    nights = nights[:7]
    if nights:
        avg = sum(nights) / len(nights)
        lines.append(
            f"Last {len(nights)} night(s) averaged {int(avg // 60)}h {int(avg % 60)}m."
        )
    if naps:
        lines.append(f"{len(naps)} nap(s) recently, averaging {int(sum(naps) / len(naps))} minutes.")
    return " ".join(lines)


# --- sleep trends (dashboard) ------------------------------------------------------------
def _hhmm(minutes: float) -> str:
    m = int(round(minutes)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def _period_stats(nights: dict, end_day, days: int, goal_h: float, naps: dict | None = None) -> dict:
    """Stats over the `days` calendar days ending at end_day (inclusive): tracked nights (goal,
    bedtime, debt) plus, separately, naps."""
    keys = [(end_day - timedelta(days=i)).isoformat() for i in range(days)]
    rows = [nights[k] for k in keys if k in nights]
    nap_rows = [naps[k] for k in keys if naps and k in naps]
    nap_count = sum(n["count"] for n in nap_rows)
    nap_minutes = sum(n["minutes"] for n in nap_rows)
    out = {
        "days": days, "nights_tracked": len(rows), "avg_hours": None, "best_hours": None,
        "worst_hours": None, "total_hours": None, "avg_bedtime": None, "avg_wake": None,
        "bedtime_variability_min": None, "goal_hit_nights": 0, "debt_hours": 0.0,
        "nap_count": nap_count, "nap_days": len(nap_rows),
        "nap_total_hours": round(nap_minutes / 60, 2),
        "nap_avg_minutes": round(nap_minutes / nap_count) if nap_count else None,
    }
    if not rows:
        return out
    hours = [r["hours"] for r in rows]
    out["avg_hours"] = round(sum(hours) / len(hours), 2)
    out["best_hours"] = round(max(hours), 2)
    out["worst_hours"] = round(min(hours), 2)
    out["total_hours"] = round(sum(hours), 1)
    out["goal_hit_nights"] = sum(1 for h in hours if h >= goal_h)
    out["debt_hours"] = round(sum(max(0.0, goal_h - h) for h in hours), 1)
    # Bedtime is measured from 18:00 so a 23:30 and a 00:30 bedtime average sensibly.
    bed = [r["bed_min"] for r in rows]
    mean_bed = sum(bed) / len(bed)
    out["avg_bedtime"] = _hhmm(mean_bed + 18 * 60)
    out["bedtime_variability_min"] = round(
        math.sqrt(sum((b - mean_bed) ** 2 for b in bed) / len(bed))
    )
    wake = [r["wake_min"] for r in rows]
    out["avg_wake"] = _hhmm(sum(wake) / len(wake))
    return out


def stats_summary(now: datetime | None = None) -> dict:
    """Read-only sleep trends for the dashboard, from sleep_log alone (no new tables). Sessions are
    grouped by the calendar day they ended on, so a night that crosses midnight is one night.
    Time in Sleep Mode is a proxy for sleep, not a measurement of it."""
    now = now or datetime.now()
    today = now.date()
    goal = SLEEP_GOAL_HOURS
    with _db_lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT started_at, ended_at, duration_minutes, kind FROM sleep_log "
                "WHERE ended_at IS NOT NULL AND duration_minutes >= ? ORDER BY id",
                (min(MIN_SESSION_MINUTES, NAP_MIN_MINUTES),),
            ).fetchall()
            digests = conn.execute(
                "SELECT started_at, ended_at, digest FROM sleep_log "
                "WHERE digest IS NOT NULL AND digest != '' ORDER BY id DESC LIMIT 8"
            ).fetchall()
        finally:
            conn.close()

    nights: dict[str, dict] = {}
    naps: dict[str, dict] = {}
    for started_at, ended_at, minutes, kind in rows:
        try:
            start, end = datetime.fromisoformat(started_at), datetime.fromisoformat(ended_at)
        except (TypeError, ValueError):
            continue
        if kind == "nap":
            if minutes >= NAP_MIN_MINUTES:
                nap = naps.setdefault(end.date().isoformat(), {"minutes": 0.0, "count": 0})
                nap["minutes"] += minutes
                nap["count"] += 1
            continue
        if minutes < MIN_SESSION_MINUTES:
            continue
        n = nights.setdefault(end.date().isoformat(), {
            "minutes": 0.0, "sessions": 0, "first_start": start, "last_end": end,
        })
        n["minutes"] += minutes
        n["sessions"] += 1
        n["first_start"] = min(n["first_start"], start)
        n["last_end"] = max(n["last_end"], end)
    for n in nights.values():
        n["hours"] = n["minutes"] / 60
        n["bed_min"] = (n["first_start"].hour * 60 + n["first_start"].minute - 18 * 60) % 1440
        n["wake_min"] = n["last_end"].hour * 60 + n["last_end"].minute

    daily = []
    for i in range(89, -1, -1):
        d = today - timedelta(days=i)
        n = nights.get(d.isoformat())
        nap = naps.get(d.isoformat())
        daily.append({
            "date": d.isoformat(),
            "nap_hours": round(nap["minutes"] / 60, 2) if nap else None,
            "naps": nap["count"] if nap else 0,
            "hours": round(n["hours"], 2) if n else None,
            "bedtime": _hhmm(n["bed_min"] + 18 * 60) if n else None,
            "wake": _hhmm(n["wake_min"]) if n else None,
            "bed_min": n["bed_min"] if n else None,
            "wake_min": n["wake_min"] if n else None,
            "sessions": n["sessions"] if n else 0,
        })

    weekday = []
    for wd, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
        vals = [d["hours"] for d in daily if d["hours"] is not None
                and datetime.fromisoformat(d["date"]).weekday() == wd]
        weekday.append({"day": name, "avg_hours": round(sum(vals) / len(vals), 2) if vals else None,
                        "nights": len(vals)})

    streak = 0
    for i in range(0, 90):
        n = nights.get((today - timedelta(days=i)).isoformat())
        if n is None and i == 0:
            continue  # today's sleep may not be logged yet
        if n is None or n["hours"] < goal:
            break
        streak += 1

    state = _get_state()
    current = None
    if state.get("active") and state.get("started_at"):
        try:
            started_dt = datetime.fromisoformat(state["started_at"])
            elapsed = (now - started_dt).total_seconds() / 60
            current = {
                "started_at": state["started_at"],
                "elapsed_minutes": round(elapsed),
                "is_nap": state.get("kind") == "nap",
            }
        except ValueError:
            pass

    return {
        "goal_hours": goal,
        "min_session_minutes": MIN_SESSION_MINUTES,
        "current": current,
        "week": _period_stats(nights, today, 7, goal, naps),
        "prev_week": _period_stats(nights, today - timedelta(days=7), 7, goal, naps),
        "month": _period_stats(nights, today, 30, goal, naps),
        "prev_month": _period_stats(nights, today - timedelta(days=30), 30, goal, naps),
        "goal_streak_nights": streak,
        "daily": daily,
        "weekday": weekday,
        "digests": [{"started_at": a, "ended_at": b, "digest": c} for a, b, c in digests],
        "note": (
            "Based on time spent in Sleep Mode, not measured sleep: turn it on when you go to "
            f"bed and off when you get up. Night sessions under {MIN_SESSION_MINUTES} min are "
            "ignored. Say \"nap mode\" to start a nap: it works the same but is shown separately "
            "and never counts toward your sleep time or goal."
        ),
    }


# --- smart wake-up ---------------------------------------------------------------------
def schedule_wakeup(wake_time: str, ramp_minutes: int | None = None) -> str:
    """wake_time: 'HH:MM' 24h local time. Checked every scheduler tick by check_wakeup()."""
    wake_time = (wake_time or "").strip()
    try:
        datetime.strptime(wake_time, "%H:%M")
    except ValueError:
        return "Give the wake time as HH:MM, e.g. 07:30."
    _set_state(
        wake_time=wake_time,
        wake_ramp_minutes=int(ramp_minutes) if ramp_minutes else DEFAULT_WAKE_RAMP_MINUTES,
        wake_fired_date=None,
    )
    return f"Wake-up alarm set for {wake_time}, with a gentle volume ramp beforehand."


def _ramp_volume_up(run_system_action, steps: int) -> None:
    def _run():
        for _ in range(steps):
            try:
                run_system_action("volume_up")
            except Exception as e:
                log.warning("Sleep Mode wake ramp failed: %s", e)
                return
            threading.Event().wait(20)  # spread the ramp out instead of one loud jump

    threading.Thread(target=_run, daemon=True, name="sleep-wake-ramp").start()


def check_wakeup(now: datetime, run_system_action, speak_fn) -> None:
    """Call once per scheduler tick (jarvis.py's existing 60s loop). Fires at most once per
    calendar day for the configured wake_time, ramping volume up over wake_ramp_minutes and
    then speaking a brief morning line, and turns Sleep Mode off."""
    state = _get_state()
    wake_time = state.get("wake_time")
    if not wake_time or not state.get("active"):
        return
    today = now.date().isoformat()
    if state.get("wake_fired_date") == today:
        return
    try:
        target = datetime.strptime(wake_time, "%H:%M").time()
    except ValueError:
        return
    ramp_minutes = state.get("wake_ramp_minutes") or DEFAULT_WAKE_RAMP_MINUTES
    ramp_start = (datetime.combine(now.date(), target) - timedelta(minutes=ramp_minutes)).time()
    if not (ramp_start <= now.time() <= target):
        return
    _set_state(wake_fired_date=today)
    _ramp_volume_up(run_system_action, steps=max(1, ramp_minutes // 2))
    try:
        speak_fn("Good morning. Gently waking you up now.")
    except Exception as e:
        log.warning("Sleep Mode wake speak failed: %s", e)
    disable()
    log.info("Sleep Mode: smart wake-up fired for %s.", wake_time)


# --- ambient sound / breathing -----------------------------------------------------------
def play_ambient(kind: str) -> str:
    kind = (kind or "rain").strip().lower()
    url = AMBIENT_SOUNDS.get(kind)
    if not url:
        return f"{kind!r} isn't a known ambient sound (try rain, white_noise, lofi, or meditation)."
    try:
        webbrowser.open(url)
    except OSError as e:
        return f"Could not open ambient sound: {e}"
    return f"Playing {kind.replace('_', ' ')} sounds."


def guided_breathing_steps() -> list[tuple[str, float]]:
    return list(BREATHING_SCRIPT)
