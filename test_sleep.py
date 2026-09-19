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
    sm.set_wake_digest_handler(lambda a, b: calls.append((a, b)))
    sm._set_state(active=1, started_at="2026-09-18T23:00:00", hosts_blocked=0, dark_mode_was_on=1)
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
        return {"content": [{"type": "text", "text": "Hero, while you were asleep, you had one reminder."}]}

    spoken, done, saved = [], threading.Event(), []
    monkeypatch.setattr(jarvis, "_claude_request", fake_claude)
    monkeypatch.setattr(jarvis.sleep_mode, "save_digest", lambda a, d: saved.append((a, d)))
    monkeypatch.setattr(jarvis, "speak_text", lambda t: (spoken.append(t), done.set()))
    jarvis._sleep_wake_digest("2026-09-18T23:00:00", "2026-09-19T07:00:00")
    assert done.wait(5)
    assert spoken == ["Hero, while you were asleep, you had one reminder."]
    assert "call mom" in seen["body"]["messages"][0]["content"]
    assert "Busy-gate" not in seen["body"]["messages"][0]["content"]
    assert saved and saved[0][0] == "2026-09-18T23:00:00"
    # Only the sleep-queued item was drained; the busy-gate one stays for normal flushing.
    assert [i["text"] for i in jarvis._session_context["pending_notifications"]] == ["Busy-gate item"]


def test_digest_fallback_when_claude_fails_and_empty_case(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_claude_request", lambda *a, **k: None)
    items = [{"text": "Reminder: call mom"}, {"text": "Build finished"}]
    text = jarvis._build_sleep_digest(items)
    assert text.startswith("Hero, while you were asleep, 2 things came in") and "call mom" in text
    assert "nothing came in" in jarvis._build_sleep_digest([])
