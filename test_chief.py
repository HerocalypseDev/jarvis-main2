"""Chief-of-staff second wave: reply style, "stop talking", quiet hours, daily spend alert,
meeting heads-up, voice-speed route, STT language. Temp DB/.env only, no network."""

import json
from datetime import datetime, timedelta

import pytest

import jarvis_chief as chief

NOW = datetime(2026, 9, 23, 9, 50)


def test_quiet_hours_parsing_and_midnight_wrap():
    assert chief.in_quiet_hours("22:00-07:00", datetime(2026, 9, 23, 23, 30))
    assert chief.in_quiet_hours("22-7", datetime(2026, 9, 23, 6, 59))
    assert not chief.in_quiet_hours("22-7", datetime(2026, 9, 23, 7, 0))
    assert chief.in_quiet_hours("13:00-14:30", datetime(2026, 9, 23, 14, 0))
    for bad in ("", "soon", "25-7", "22-22"):
        assert not chief.in_quiet_hours(bad, datetime(2026, 9, 23, 23, 0))


def test_budget_alert_once_per_day():
    assert chief.budget_alert(6.2, 5, None, "2026-09-23").startswith("Heads up: I've used about $6.20")
    assert chief.budget_alert(6.2, 5, "2026-09-23", "2026-09-23") is None
    assert chief.budget_alert(4.9, 5, None, "2026-09-23") is None
    assert chief.budget_alert(99, 0, None, "2026-09-23") is None  # 0 = off


def test_meetings_starting_skips_declined_cancelled_and_far_events():
    raw = json.dumps({"events": [
        {"id": "a", "summary": "Standup", "start": {"dateTime": "2026-09-23T10:00:00"},
         "attendees": [{"email": "me@x.com", "self": True}, {"email": "sam@x.com", "displayName": "Sam"},
                       {"email": "room@resource.calendar.google.com", "resource": True}]},
        {"id": "b", "summary": "Skipped", "start": {"dateTime": "2026-09-23T10:00:00"},
         "attendees": [{"email": "me@x.com", "self": True, "responseStatus": "declined"}]},
        {"id": "c", "summary": "Later", "start": {"dateTime": "2026-09-23T11:00:00"}},
        {"id": "d", "summary": "Gone", "status": "cancelled", "start": {"dateTime": "2026-09-23T10:00:00"}},
    ]})
    ms = chief.meetings_starting(raw, NOW, 10, {"me@x.com"})
    assert [m["id"] for m in ms] == ["a"] and ms[0]["attendees"] == [("Sam", "sam@x.com")]
    assert chief.headsup_text(ms[0], NOW, ["Sam: Budget draft"]) == \
        "In 10 minutes: Standup with Sam. Recent mail: Sam: Budget draft."
    assert chief.meetings_starting("not json", NOW, 10) == []


def test_reply_style_parsing():
    assert chief.parse_reply_style("be brief from now on") == "brief"
    assert chief.parse_reply_style("more detailed answers") == "detailed"
    assert chief.parse_reply_style("go back to normal answers") == "normal"
    assert chief.reply_style_line("normal") == "" and "brief" in chief.reply_style_line("brief")


@pytest.fixture
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("JARVIS_ENV_PATH", str(tmp_path / ".env"))
    for k in ("JARVIS_REPLY_STYLE", "JARVIS_QUIET_HOURS", "JARVIS_SAFE_MODE"):
        monkeypatch.delenv(k, raising=False)
    import jarvis as j
    monkeypatch.setattr(j.settings, "JARVIS_MODULE", None)
    monkeypatch.setattr(j, "_session_context", {"pending_notifications": []})
    monkeypatch.setattr(j, "_save_session_context_locked", lambda: None)
    yield j
    import os
    os.environ.pop("JARVIS_REPLY_STYLE", None)


def test_reply_style_is_sticky_and_reaches_the_prompt(jarvis):
    assert jarvis._deterministic_intent_reply("reply_style", "be brief from now on") == "Okay, short answers from now on."
    volatile = jarvis.build_system_blocks("", "")[1]["text"]
    assert "Reply style (the user's standing choice): brief" in volatile
    jarvis._deterministic_intent_reply("reply_style", "go back to normal answers")
    assert "Reply style" not in jarvis.build_system_blocks("", "")[1]["text"]


def test_stop_talking_interrupts_and_says_nothing(jarvis, monkeypatch):
    stopped, spoken = [], []
    monkeypatch.setattr(jarvis.sd, "stop", lambda: stopped.append(1))
    monkeypatch.setattr(jarvis, "speak_text", lambda t: spoken.append(t))
    monkeypatch.setattr(jarvis, "_log_action_audit", lambda *a, **k: None)
    monkeypatch.setattr(jarvis, "_append_history", lambda *a, **k: None)
    monkeypatch.setattr(jarvis.autonomy, "after_turn", lambda *a, **k: None)
    monkeypatch.setattr(jarvis.autonomy, "enabled", lambda: False)
    monkeypatch.setattr(jarvis, "flush_pending_notifications", lambda: None)
    monkeypatch.setattr(jarvis, "run_agent_loop", lambda *a, **k: pytest.fail("no LLM call for 'stop talking'"))
    jarvis.handle_text_command("stop talking", source="voice")
    assert stopped and spoken == []


def test_quiet_hours_queue_non_urgent_only(jarvis, monkeypatch):
    spoken = []
    monkeypatch.setenv("JARVIS_QUIET_HOURS", "00:00-23:59")
    monkeypatch.setattr(jarvis, "_speak_shaped", lambda t: spoken.append(t))
    monkeypatch.setattr(jarvis, "_notify_phone", lambda *a, **k: None)
    monkeypatch.setattr(jarvis, "refresh_session_context", lambda: None)
    monkeypatch.setattr(jarvis.focus_mode, "should_suppress", lambda u: False)
    monkeypatch.setattr(jarvis.sleep_mode, "should_suppress", lambda u: False)
    monkeypatch.setattr(jarvis.sleep_mode, "is_active", lambda: False)
    jarvis.queue_or_deliver_notification("Your build finished.")
    jarvis.queue_or_deliver_notification("Timer done.", urgent=True)
    assert spoken == ["Timer done."] and jarvis._session_context["pending_notifications"][0]["text"] == "Your build finished."


def test_budget_check_alerts_once(jarvis, monkeypatch):
    sent = []
    monkeypatch.setenv("JARVIS_DAILY_BUDGET_USD", "1")
    monkeypatch.setattr(jarvis, "queue_or_deliver_notification", lambda t, **k: sent.append(t))
    monkeypatch.setattr(jarvis.billing, "local_summary", lambda c, l: {"periods": {"today": {"cost_usd": 1.5}}})
    jarvis._budget_check(NOW)
    jarvis._budget_check(NOW)
    assert len(sent) == 1 and "$1.50" in sent[0]


def test_meeting_headsup_once_per_event_with_recent_mail(jarvis, monkeypatch):
    sent = []
    raw = json.dumps({"events": [{"id": "a", "summary": "Standup", "start": {"dateTime": "2026-09-23T10:00:00"},
                                  "attendees": [{"email": "sam@x.com", "displayName": "Sam"}]}]})
    monkeypatch.setattr(jarvis, "_calendar_events_raw", lambda a, b: raw)
    monkeypatch.setattr(jarvis, "_mcp_tool_index", {"mcp_gmail_search_emails": ("gmail", "search_emails")})
    monkeypatch.setattr(jarvis, "_sleep_mail_mcp", lambda tool, args: "ID: 1\nSubject: Budget draft\nFrom: Sam <sam@x.com>\nDate: x")
    monkeypatch.setattr(jarvis.sleep_mail, "own_addresses", lambda: set())
    monkeypatch.setattr(jarvis, "queue_or_deliver_notification", lambda t, **k: sent.append(t))
    jarvis._meeting_headsup(NOW, 10)
    jarvis._meeting_headsup(NOW, 10)
    assert sent == ["In 10 minutes: Standup with Sam. Recent mail: Sam: Budget draft."]


def test_latency_route(jarvis, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(jarvis.latency, "recent", lambda n=20: [{"e2e_ms": 900}])
    client = TestClient(jarvis.dashboard._build_app(), base_url="http://127.0.0.1:8765")
    assert client.get("/api/latency").json() == {"recent": [{"e2e_ms": 900}]}


def test_asking_for_detail_reads_the_whole_reply(jarvis, monkeypatch):
    spoken = []
    long_reply = "Here is everything the search found. " * 20
    monkeypatch.setattr(jarvis, "speak_text", lambda t: spoken.append(t))
    monkeypatch.setattr(jarvis, "_summarize_for_speech", lambda t: "short summary")
    monkeypatch.setattr(jarvis, "_log_action_audit", lambda *a, **k: None)
    monkeypatch.setattr(jarvis, "_append_history", lambda *a, **k: None)
    monkeypatch.setattr(jarvis.autonomy, "after_turn", lambda *a, **k: None)
    monkeypatch.setattr(jarvis.autonomy, "enabled", lambda: False)
    monkeypatch.setattr(jarvis, "flush_pending_notifications", lambda: None)
    monkeypatch.setattr(jarvis, "run_agent_loop", lambda *a, **k: long_reply)
    jarvis.handle_text_command("look up black holes", source="text")
    jarvis.handle_text_command("explain black holes in detail", source="text")
    jarvis.handle_text_command("search for black holes and don't summarize", source="text")
    assert spoken == ["short summary", long_reply, long_reply]
    monkeypatch.setenv("JARVIS_REPLY_STYLE", "detailed")  # "be more detailed from now on"
    jarvis.handle_text_command("look up black holes", source="text")
    assert spoken[-1] == long_reply
