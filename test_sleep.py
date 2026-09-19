"""Tests for sleep trend stats and the wake-up digest.
Run with: python -m pytest test_sleep.py -v

Isolated temp DB and session-state file; Claude and TTS are faked, nothing real is spoken or billed.
"""

from __future__ import annotations

import threading
from datetime import datetime

import pytest

import jarvis_sleep_mode as sm

NOW = datetime(2026, 9, 19, 12, 0, 0)


@pytest.fixture()
def db(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(sm, "_wake_digest_handler", None)
    monkeypatch.setattr(sm, "SLEEP_GOAL_HOURS", 8.0)  # .env may set another goal; don't let it leak in
    monkeypatch.setattr(sm, "_system_action", None)
    return tmp_path


def _log(start: str, end: str):
    minutes = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60
    with sm._db_lock:
        conn = sm._connect()
        conn.execute(
            "INSERT INTO sleep_log (started_at, ended_at, duration_minutes) VALUES (?, ?, ?)",
            (start, end, minutes),
        )
        conn.commit()
        conn.close()


def test_stats_empty(db):
    s = sm.stats_summary(NOW)
    assert s["week"]["nights_tracked"] == 0 and s["week"]["avg_hours"] is None
    assert len(s["daily"]) == 90 and s["digests"] == []


def test_stats_nights_bedtime_past_midnight_and_short_sessions(db):
    _log("2026-09-17T23:00:00", "2026-09-18T07:00:00")  # 8h, night of the 18th
    _log("2026-09-19T00:30:00", "2026-09-19T06:30:00")  # 6h, bed after midnight
    _log("2026-09-19T07:00:00", "2026-09-19T07:05:00")  # accidental toggle, ignored
    s = sm.stats_summary(NOW)
    assert s["week"]["nights_tracked"] == 2
    assert s["week"]["avg_hours"] == 7.0
    assert s["week"]["best_hours"] == 8.0 and s["week"]["worst_hours"] == 6.0
    assert s["week"]["avg_bedtime"] == "23:45"  # mean of 23:00 and 00:30
    assert s["week"]["avg_wake"] == "06:45"
    assert s["week"]["goal_hit_nights"] == 1 and s["week"]["debt_hours"] == 2.0
    last = s["daily"][-1]
    assert last["date"] == "2026-09-19" and last["hours"] == 6.0 and last["bedtime"] == "00:30"


def test_stats_two_sessions_same_night_are_summed(db):
    _log("2026-09-18T23:00:00", "2026-09-19T03:00:00")
    _log("2026-09-19T03:30:00", "2026-09-19T07:30:00")
    d = sm.stats_summary(NOW)["daily"][-1]
    assert d["hours"] == 8.0 and d["sessions"] == 2 and d["bedtime"] == "23:00" and d["wake"] == "07:30"


def test_disable_calls_digest_handler_and_digest_is_saved(db):
    calls = []
    sm.set_wake_digest_handler(lambda a, b, kind: calls.append((a, b)))
    sm._set_state(active=1, started_at="2026-09-18T23:00:00", dark_mode_was_on=1)
    _log("2026-09-18T23:00:00", "2026-09-18T23:00:00")  # placeholder row to attach digest to
    sm.disable()
    assert len(calls) == 1 and calls[0][0] == "2026-09-18T23:00:00"
    sm.save_digest("2026-09-18T23:00:00", "Hero, while you were asleep, nothing.")
    assert sm.stats_summary()["digests"][0]["digest"].startswith("Hero, while")


# --- jarvis.py wiring ------------------------------------------------------------------------
@pytest.fixture()
def jarvis(monkeypatch, tmp_path, db):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import jarvis as j

    monkeypatch.setattr(j, "SESSION_STATE_PATH", tmp_path / "session_state.json")
    monkeypatch.setattr(j, "_session_context", j._default_session_context())
    monkeypatch.setattr(j, "_notify_phone", lambda *a, **k: None)
    monkeypatch.setattr(j, "refresh_session_context", lambda: None)
    return j


def test_notifications_queued_in_sleep_are_flagged_and_skipped_by_flush(jarvis, monkeypatch):
    spoken = []
    monkeypatch.setattr(jarvis, "_speak_shaped", spoken.append)
    monkeypatch.setattr(jarvis.sleep_mode, "should_suppress", lambda urgent, sender=None: True)
    jarvis.queue_or_deliver_notification("Reminder: call mom")
    assert jarvis._session_context["pending_notifications"][0]["during_sleep"] is True
    jarvis.flush_pending_notifications()  # the user talking mid-sleep must not replay it
    assert spoken == []
    assert len(jarvis._session_context["pending_notifications"]) == 1


def test_wake_digest_summarizes_speaks_and_drains(jarvis, monkeypatch):
    jarvis._session_context["pending_notifications"] = [
        {"text": "Reminder: call mom", "queued_at": "x", "during_sleep": True},
        {"text": "Busy-gate item", "queued_at": "x"},
    ]
    seen = {}

    def fake_claude(body, timeout=None):
        seen["body"] = body
        return {"content": [{"type": "text", "text": "Hero, while you were asleep, nothing important happened. On a lighter note, you had one reminder."}]}

    spoken, done, saved = [], threading.Event(), []
    monkeypatch.setattr(jarvis, "_claude_request", fake_claude)
    monkeypatch.setattr(jarvis.sleep_mode, "save_digest", lambda a, d: saved.append((a, d)))
    monkeypatch.setattr(jarvis, "speak_text", lambda t: (spoken.append(t), done.set()))
    jarvis._sleep_wake_digest("2026-09-18T23:00:00", "2026-09-19T07:00:00")
    assert done.wait(5)
    assert spoken == ["Hero, while you were asleep, nothing important happened. On a lighter note, you had one reminder."]
    assert "call mom" in seen["body"]["messages"][0]["content"]
    assert "Busy-gate" not in seen["body"]["messages"][0]["content"]
    assert saved and saved[0][0] == "2026-09-18T23:00:00"
    # Only the sleep-queued item was drained; the busy-gate one stays for normal flushing.
    assert [i["text"] for i in jarvis._session_context["pending_notifications"]] == ["Busy-gate item"]


def test_digest_fallback_when_claude_fails_and_empty_case(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_claude_request", lambda *a, **k: None)
    items = [{"text": "Reminder: call mom"}, {"text": "Build finished"}]
    text = jarvis._build_sleep_digest(items)
    assert text.startswith("Hero, while you were asleep, nothing important happened.")
    assert "On a lighter note," in text and "call mom" in text
    assert "nothing came in" in jarvis._build_sleep_digest([])


def test_digest_important_first_then_lighter_note(jarvis, monkeypatch):
    seen = {}

    def fake(body, timeout=None):
        seen["user"] = body["messages"][0]["content"]
        return {"content": [{"type": "text", "text":
                "Hero, while you were asleep, the door alarm fired. On a lighter note, you had a reminder."}]}

    monkeypatch.setattr(jarvis, "_claude_request", fake)
    items = [{"text": "Reminder: call mom"}, {"text": "Door alarm triggered", "important": True}]
    text = jarvis._build_sleep_digest(items)
    assert "On a lighter note" in text
    u = seen["user"]
    assert u.index("IMPORTANT") < u.index("Door alarm") < u.index("LIGHTER") < u.index("call mom")


def test_digest_falls_back_when_model_drops_the_lighter_note(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_claude_request",
                        lambda *a, **k: {"content": [{"type": "text", "text": "Hero, while you were asleep, stuff."}]})
    items = [{"text": "Door alarm", "important": True}, {"text": "Reminder: call mom"}]
    text = jarvis._build_sleep_digest(items)
    assert "Door alarm" in text and "On a lighter note, Reminder: call mom" in text
    # No lighter items -> no "lighter note" required or added.
    only = jarvis._build_sleep_digest([{"text": "Door alarm", "important": True}])
    assert "lighter" not in only


def test_urgent_during_sleep_is_spoken_live_and_recorded_as_important(jarvis, monkeypatch):
    spoken = []
    monkeypatch.setattr(jarvis, "_speak_shaped", spoken.append)
    monkeypatch.setattr(jarvis.sleep_mode, "is_active", lambda: True)
    jarvis.queue_or_deliver_notification("Smoke alarm!", urgent=True)
    assert spoken == ["Smoke alarm!"]
    item = jarvis._session_context["pending_notifications"][0]
    assert item["important"] is True and item["during_sleep"] is True


def test_dotenv_is_loaded_before_module_imports():
    """A .env setting read at import time (sleep goal) must reach the modules jarvis.py imports."""
    import subprocess, sys, tempfile, textwrap
    from pathlib import Path

    root = Path(__file__).resolve().parent
    code = textwrap.dedent(f"""
        import sys; sys.path.insert(0, r"{root}")
        import os
        os.environ.pop("JARVIS_SLEEP_GOAL_HOURS", None)
        import jarvis, jarvis_sleep_mode
        print(jarvis_sleep_mode.SLEEP_GOAL_HOURS)
    """)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                         env={**__import__("os").environ, "JARVIS_MEMORY_DB_PATH": tempfile.mkdtemp() + "/t.db"})
    expected = None
    for line in (root / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("JARVIS_SLEEP_GOAL_HOURS="):
            expected = float(line.split("=", 1)[1])
    if expected is None:
        import pytest
        pytest.skip("no JARVIS_SLEEP_GOAL_HOURS in .env on this machine")
    assert out.stdout.strip().splitlines()[-1] == str(expected), out.stderr[-500:]


# --- naps ------------------------------------------------------------------------------------
def _log_kind(start: str, end: str, kind: str | None):
    minutes = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60
    with sm._db_lock:
        conn = sm._connect()
        conn.execute("INSERT INTO sleep_log (started_at, ended_at, duration_minutes, kind) VALUES (?, ?, ?, ?)",
                     (start, end, minutes, kind))
        conn.commit()
        conn.close()


def test_nap_is_chosen_by_the_user_not_the_clock(db):
    _log_kind("2026-09-19T14:00:00", "2026-09-19T14:45:00", None)      # old row / plain sleep at 2pm: a night
    _log_kind("2026-09-19T23:00:00", "2026-09-19T23:50:00", "nap")     # nap at 11pm: still a nap
    s = sm.stats_summary(NOW)
    assert s["week"]["nights_tracked"] == 1 and s["week"]["nap_count"] == 1


def test_naps_are_separate_from_nights(db):
    _log_kind("2026-09-18T23:00:00", "2026-09-19T05:00:00", "sleep")   # 6h night
    _log_kind("2026-09-19T14:00:00", "2026-09-19T14:45:00", "nap")
    _log_kind("2026-09-19T15:30:00", "2026-09-19T15:40:00", "nap")     # 10 min: counted
    _log_kind("2026-09-19T16:00:00", "2026-09-19T16:05:00", "nap")     # 5 min: ignored
    s = sm.stats_summary(NOW)
    assert s["week"]["nights_tracked"] == 1 and s["week"]["avg_hours"] == 6.0  # nap did not inflate the night
    assert s["week"]["avg_bedtime"] == "23:00" and s["week"]["debt_hours"] == 2.0  # 6h night vs the 8h goal
    assert s["week"]["nap_count"] == 2 and s["week"]["nap_days"] == 1
    assert s["week"]["nap_avg_minutes"] == 28 and s["week"]["nap_total_hours"] == 0.92
    d = s["daily"][-1]
    assert d["hours"] == 6.0 and d["nap_hours"] == 0.92 and d["naps"] == 2


def test_nap_only_day_has_no_night_and_status_line_separates_them(db):
    _log_kind("2026-09-19T14:00:00", "2026-09-19T14:30:00", "nap")
    d = sm.stats_summary(NOW)["daily"][-1]
    assert d["hours"] is None and d["bedtime"] is None and d["nap_hours"] == 0.5
    assert sm.stats_summary(NOW)["week"]["nights_tracked"] == 0
    assert "nap(s) recently" in sm.status() and "night(s)" not in sm.status()


def test_enable_nap_logs_kind_and_disable_reports_it(db, monkeypatch):
    monkeypatch.setattr(sm, "_set_dark_mode", lambda d: True)
    monkeypatch.setattr(sm, "_dark_mode_is_on", lambda: False)
    monkeypatch.setattr(sm, "_start_media_autopause", lambda r: None)
    monkeypatch.setattr(sm, "_cancel_media_autopause", lambda: None)
    spoken, handled = [], []
    sm.set_wake_digest_handler(lambda a, b, kind: handled.append(kind))
    out = sm.enable(lambda a: None, spoken.append, kind="nap")
    assert "Nap mode is on" in out and "won't count toward your sleep time" in out
    assert spoken[0].startswith("Nap mode on.") and sm.is_active()
    assert sm.stats_summary(NOW)["current"]["is_nap"] is True
    assert sm.enable(lambda a: None, spoken.append) == "Sleep Mode is already on."   # can't start a second
    off = sm.disable()
    assert "Nap logged" in off and "doesn't count" in off and handled == ["nap"] and not sm.is_active()
    conn = sm._connect()
    assert conn.execute("SELECT kind FROM sleep_log").fetchall() == [("nap",)]
    conn.close()
    # A normal sleep session afterwards is logged as sleep and hands the handler 'sleep'.
    sm.enable(lambda a: None, spoken.append)
    assert "You were in Sleep Mode" in sm.disable() and handled == ["nap", "sleep"]


def test_recap_wording_for_a_nap(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_claude_request", lambda *a, **k: None)
    assert jarvis._build_sleep_digest([], nap=True) == "Hero, nothing came in while you were napping."
    assert "while you were napping" in jarvis._build_sleep_digest([{"text": "x"}], nap=True)
    assert "while you were asleep" in jarvis._build_sleep_digest([{"text": "x"}])


def test_text_hotkey_and_ptt_defaults():
    import subprocess, sys, os
    from pathlib import Path
    root = Path(__file__).resolve().parent
    env = {k: v for k, v in os.environ.items() if k not in ("JARVIS_TEXT_HOTKEY_KEY", "JARVIS_PTT_KEY")}
    env["JARVIS_MEMORY_DB_PATH"] = str(Path(os.environ.get("TEMP", ".")) / "hk_test.db")
    code = f"import sys; sys.path.insert(0, r'{root}'); import jarvis; print(jarvis.JARVIS_TEXT_HOTKEY_KEY, '|', jarvis.JARVIS_PTT_KEY)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env=env)
    assert out.stdout.strip().splitlines()[-1] == "left ctrl | right shift", out.stderr[-300:]


def test_tool_nap_action_starts_a_nap_and_recap_uses_kind(jarvis, monkeypatch):
    seen = {}
    monkeypatch.setattr(jarvis.sleep_mode, "enable", lambda run, speak, kind="sleep": seen.setdefault("kind", kind) and "ok")
    monkeypatch.setattr(jarvis, "_log_action_audit", lambda *a, **k: None)
    jarvis._execute_tool_impl("sleep_mode", {"action": "nap"}, "nap mode")
    assert seen.get("kind") == "nap"
    schema = next(t for t in jarvis.AGENT_TOOLS if t["name"] == "sleep_mode")
    assert "nap" in schema["input_schema"]["properties"]["action"]["enum"]
    # wake-digest handler wording follows the session kind
    texts = []
    monkeypatch.setattr(jarvis, "_build_sleep_digest", lambda items, nap=False: texts.append(nap) or "x")
    monkeypatch.setattr(jarvis.sleep_mode, "save_digest", lambda *a: None)
    monkeypatch.setattr(jarvis, "speak_text", lambda t: None)
    jarvis._sleep_wake_digest("2026-09-19T14:00:00", "2026-09-19T14:40:00", "nap")
    import time as _t; _t.sleep(0.3)
    assert texts == [True]


# --- what Sleep Mode actually does, and undoing it -------------------------------------------
def _fake_env(monkeypatch, dark=False, dark_ok=True):
    monkeypatch.setattr(sm, "_dark_mode_is_on", lambda: dark)
    monkeypatch.setattr(sm, "_set_dark_mode", lambda d: dark_ok)
    monkeypatch.setattr(sm, "_start_media_autopause", lambda r: None)
    monkeypatch.setattr(sm, "_cancel_media_autopause", lambda: None)


def test_enable_reports_what_really_happened(db, monkeypatch):
    _fake_env(monkeypatch, dark=True)
    out = sm.enable(lambda a: None, lambda t: None)
    assert "dark mode was already on" in out and "lowered 8 steps" in out
    assert "site" not in out.lower()
    sm.disable()
    _fake_env(monkeypatch, dark=False, dark_ok=False)
    out = sm.enable(lambda a: None, lambda t: None)
    assert "couldn't switch dark mode" in out


def test_disable_puts_the_volume_back(db, monkeypatch):
    _fake_env(monkeypatch)
    pressed = []
    sm.enable(pressed.append, lambda t: None)
    assert pressed.count("volume_down") == 8
    out = sm.disable()
    assert pressed.count("volume_up") == 8 and "Volume restored." in out
    assert sm._get_state()["volume_steps"] is None


def test_disable_restores_volume_via_registered_handler_after_a_restart(db, monkeypatch):
    _fake_env(monkeypatch)
    sm.enable(lambda a: None, lambda t: None)
    sm._system_action = None                      # simulates Jarvis restarting mid-sleep
    pressed = []
    sm.set_system_action_handler(pressed.append)  # jarvis.py registers this at import
    sm.disable()
    assert pressed == ["volume_up"] * 8


def test_failed_volume_press_records_only_the_steps_done(db, monkeypatch):
    _fake_env(monkeypatch)
    n = {"c": 0}

    def flaky(a):
        n["c"] += 1
        if n["c"] > 3:
            raise RuntimeError("no keyboard")

    out = sm.enable(flaky, lambda t: None)
    assert "lowered 3 steps" in out and sm._get_state()["volume_steps"] == 3


def test_wake_alarm_and_site_blocking_are_gone(jarvis):
    for name in ("schedule_wakeup", "check_wakeup", "_block_distractions", "_unblock_distractions",
                 "cleanup_stale_blocks", "_ramp_volume_up"):
        assert not hasattr(sm, name), name
    assert not any(t["name"] == "schedule_sleep_wakeup" for t in jarvis.AGENT_TOOLS)
    assert "wake-up alarm" not in sm.status().lower()


def test_volume_goes_to_zero_and_comes_back_to_the_exact_level(db, monkeypatch):
    _fake_env(monkeypatch)
    level = {"now": 0.44}
    monkeypatch.setattr(sm, "_get_volume", lambda: level["now"])
    monkeypatch.setattr(sm, "_set_volume", lambda v: level.update(now=v) or True)
    pressed = []
    out = sm.enable(pressed.append, lambda t: None)
    assert level["now"] == 0.0 and pressed == []                    # exact zero, no key presses
    assert "volume set to 0% (it was 44%" in out
    assert sm._get_state()["volume_level"] == 0.44
    off = sm.disable()
    assert level["now"] == 0.44 and "Volume restored to 44%." in off and pressed == []


def test_volume_target_is_configurable_and_confirmation_is_spoken_before_muting(db, monkeypatch):
    _fake_env(monkeypatch)
    monkeypatch.setattr(sm, "SLEEP_VOLUME_PERCENT", 10)
    level = {"now": 0.5}
    monkeypatch.setattr(sm, "_get_volume", lambda: level["now"])
    monkeypatch.setattr(sm, "_set_volume", lambda v: level.update(now=v) or True)
    heard_at = []
    sm.enable(lambda a: None, lambda t: heard_at.append(level["now"]))
    assert heard_at == [0.5]          # spoken while still audible
    assert level["now"] == 0.1


def test_falls_back_to_key_presses_when_exact_control_is_unavailable(db, monkeypatch):
    _fake_env(monkeypatch)
    monkeypatch.setattr(sm, "_get_volume", lambda: None)
    monkeypatch.setattr(sm, "_set_volume", lambda v: False)
    pressed = []
    out = sm.enable(pressed.append, lambda t: None)
    assert pressed.count("volume_down") == 8 and "volume lowered 8 steps" in out
    sm.disable()
    assert pressed.count("volume_up") == 8


def test_old_style_state_without_a_saved_level_still_restores_by_steps(db, monkeypatch):
    """A mode started by the previous version (volume_steps only) must still end cleanly."""
    _fake_env(monkeypatch)
    sm._set_state(active=1, started_at="2026-09-19T06:49:04", kind="nap", volume_steps=8, volume_level=None)
    pressed = []
    sm.set_system_action_handler(pressed.append)
    assert "Volume restored." in sm.disable() and pressed == ["volume_up"] * 8
