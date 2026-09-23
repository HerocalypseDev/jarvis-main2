"""Morning briefing v2 / "what's urgent?" (jarvis_briefing). No network, temp DB only."""

import json
import time
from datetime import datetime, timedelta

import pytest

import jarvis_briefing as b
import jarvis_latency as latency

NOW = datetime(2026, 9, 23, 8, 0)


def test_compose_omits_empty_failed_and_slow_sections():
    def boom():
        raise RuntimeError("calendar down")

    out = b.compose("morning", {
        "pending": lambda: [],
        "calendar": boom,
        "mail": lambda: time.sleep(2) or ["late"],
        "deadlines": lambda: ["overdue: send the report"],
        "weather": lambda: None,
    }, NOW, timeout=0.3)
    assert [s["key"] for s in out["sections"]] == ["deadlines"]
    assert out["speech"] == "Good morning. Deadlines: overdue: send the report."


def test_speech_caps_items_and_length():
    many = [f"item {i}" for i in range(10)]
    sections = [{"key": "mail", "title": "Mail", "items": many}] + [
        {"key": f"k{i}", "title": f"Section {i}", "items": ["x" * 150]} for i in range(10)]
    text = b.speech("urgent", sections)
    assert "item 0; item 1; item 2; and 7 more." in text
    assert len(text) <= b.SPEECH_MAX_CHARS + 60 and text.endswith("There's more on the dashboard.")
    assert b.speech("urgent", []) == "Nothing needs you right now."


def test_calendar_items_parse_mcp_json_and_flag_overlaps():
    raw = json.dumps({"events": [
        {"summary": "Standup", "start": {"dateTime": "2026-09-23T09:30:00"}, "end": {"dateTime": "2026-09-23T10:00:00"}},
        {"summary": "Dentist", "start": {"dateTime": "2026-09-23T09:45:00"}, "end": {"dateTime": "2026-09-23T10:30:00"}},
        {"summary": "Old", "start": {"dateTime": "2026-09-23T06:00:00"}, "end": {"dateTime": "2026-09-23T07:00:00"}},
        {"summary": "Holiday", "start": {"date": "2026-09-23"}, "end": {"date": "2026-09-24"}},
        {"summary": "Gone", "status": "cancelled", "start": {"dateTime": "2026-09-23T11:00:00"}},
    ]})
    items = b.calendar_items(raw, NOW, NOW + timedelta(hours=12))
    assert items == ["all day: Holiday", "9:30 AM Standup (overlaps another event)",
                     "9:45 AM Dentist (overlaps another event)"]
    assert b.calendar_items("MCP tool reported an error: invalid_grant", NOW, NOW) is None


def test_deadline_mail_and_sleep_formatters():
    rows = [{"description": "Send the report", "deadline_iso": "2026-09-22T17:00:00"},
            {"description": "Pay rent", "deadline_iso": "2026-09-23T18:00:00"},
            {"description": "Far away", "deadline_iso": "2026-10-30T18:00:00"},
            {"description": "No date"}]
    assert b.deadline_items(rows, NOW) == ["overdue: Send the report", "Pay rent, due today at 6:00 PM"]
    assert b.mail_items([{"from": '"Bob Smith" <bob@x.com>', "subject": "Contract"}]) == ["Bob Smith: Contract"]
    stats = {"goal_hours": 8, "daily": [{"date": "2026-09-23", "hours": 6.5}], "week": {"debt_hours": 4.5}}
    assert b.sleep_items(stats, NOW) == ["last night 6.5 hours (goal 8)", "4.5 hours of sleep debt this week"]


@pytest.mark.parametrize("text,intent", [
    ("good morning", "briefing"), ("Good morning, Jarvis.", "briefing"), ("morning briefing", "briefing"),
    ("give me my briefing", "briefing"), ("what's urgent", "urgent"), ("what needs me?", "urgent"),
    ("what needs my attention", "urgent"),
    ("good morning, can you draft an email to Sam", "complex"),  # a real request after the greeting
])
def test_briefing_intents(text, intent):
    assert latency.classify_intent(text) == intent


def test_briefing_report_reads_real_reminders_and_pending(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "t.db"))
    import jarvis
    monkeypatch.setattr(jarvis, "_mcp_tool_index", {})  # no calendar/Gmail connected: sections omitted
    monkeypatch.setattr(jarvis.autonomy, "enabled", lambda: False)
    monkeypatch.setattr(jarvis, "_dashboard_get_pending",
                        lambda: {"tool_name": "run_shell", "reason": "shut down the computer"})
    due = (datetime.now() + timedelta(minutes=30)).isoformat(timespec="seconds")
    jarvis.create_reminder("stretch", due_at=due)
    out = jarvis.briefing_report("urgent")
    keys = [s["key"] for s in out["sections"]]
    assert keys[:2] == ["pending", "reminders"] and "calendar" not in keys and "mail" not in keys
    assert "stretch" in out["speech"] and "shut down the computer" in out["speech"]


def test_briefing_voice_reply_is_not_summarized_away(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "t.db"))
    import jarvis
    spoken = []
    monkeypatch.setattr(jarvis, "_log_action_audit", lambda *a, **k: None)
    monkeypatch.setattr(jarvis, "_append_history", lambda *a, **k: None)
    monkeypatch.setattr(jarvis.autonomy, "after_turn", lambda *a, **k: None)
    monkeypatch.setattr(jarvis.autonomy, "enabled", lambda: False)
    monkeypatch.setattr(jarvis, "flush_pending_notifications", lambda: None)
    monkeypatch.setattr(jarvis, "speak_text", lambda t: spoken.append(t))
    monkeypatch.setattr(jarvis, "_summarize_for_speech", lambda t: pytest.fail("briefing must not be re-summarized"))
    monkeypatch.setattr(jarvis, "run_agent_loop", lambda *a, **k: pytest.fail("no LLM call for a briefing"))
    monkeypatch.setattr(jarvis, "briefing_report", lambda kind: {"speech": f"{kind} speech " + "x" * 400})
    jarvis.handle_text_command("what's urgent", source="text")
    assert spoken == ["urgent speech " + "x" * 400]
