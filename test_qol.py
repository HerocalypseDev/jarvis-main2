"""QOL pass (2026-09-23): Claude->Gemini failover, self-check, timers/stopwatch, repeat/shorter,
last actions, undo, log cleanup. No real network: every request is faked."""

import io
import os
import time
import urllib.error

import pytest

import jarvis
import jarvis_latency as latency


@pytest.fixture(autouse=True)
def _reset(monkeypatch, tmp_path):
    # Never touch the real jarvis_memory.db (sessions, audit, autonomy all write there).
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(jarvis, "_log_action_audit", lambda *a, **k: None)
    monkeypatch.setattr(jarvis, "_append_history", lambda *a, **k: None)
    monkeypatch.setattr(jarvis.autonomy, "after_turn", lambda *a, **k: None)
    monkeypatch.setattr(jarvis.autonomy, "enabled", lambda: False)
    monkeypatch.setattr(jarvis, "_llm_failover", {"skip_claude_until": 0.0, "last_reason": "", "announced": False})
    monkeypatch.setattr(jarvis, "_llm_provider", lambda: "claude")
    monkeypatch.setattr(jarvis, "queue_or_deliver_notification", lambda *a, **k: None)
    monkeypatch.setattr(jarvis, "_record_api_usage", lambda *a, **k: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("JARVIS_LLM_FAILOVER", raising=False)


def _http_error(code, body):
    return urllib.error.HTTPError("u", code, "err", {}, io.BytesIO(body.encode()))


def test_credit_error_fails_over_to_gemini_and_skips_claude_for_a_while(monkeypatch):
    calls = {"claude": 0, "gemini": 0}

    def fake_urlopen(req, timeout):
        calls["claude"] += 1
        raise _http_error(400, '{"error":{"message":"Your credit balance is too low"}}')

    def fake_gemini(body, timeout, opener):
        calls["gemini"] += 1
        return {"content": [{"type": "text", "text": "from gemini"}], "stop_reason": "end_turn"}

    monkeypatch.setattr(jarvis, "_urlopen_hard_timeout", fake_urlopen)
    monkeypatch.setattr(jarvis.gemini, "call", fake_gemini)
    monkeypatch.setattr(jarvis.gemini, "api_key", lambda: "g-key")
    body = {"model": "m", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]}
    assert jarvis._claude_request(body, 5)["content"][0]["text"] == "from gemini"
    assert calls == {"claude": 1, "gemini": 1}  # a 400 is not retried
    jarvis._claude_request(body, 5)  # inside the cooldown: Claude isn't even tried
    assert calls == {"claude": 1, "gemini": 2}
    assert "credit balance" in jarvis._llm_failover["last_reason"]


def test_no_failover_without_gemini_key_or_when_disabled(monkeypatch):
    monkeypatch.setattr(jarvis, "_urlopen_hard_timeout",
                        lambda r, t: (_ for _ in ()).throw(_http_error(401, "bad key")))
    monkeypatch.setattr(jarvis.gemini, "call", lambda *a: pytest.fail("must not call Gemini"))
    monkeypatch.setattr(jarvis.gemini, "api_key", lambda: "")
    body = {"model": "m", "max_tokens": 5, "messages": []}
    assert jarvis._claude_request(body, 5) is None
    monkeypatch.setattr(jarvis.gemini, "api_key", lambda: "g-key")
    monkeypatch.setenv("JARVIS_LLM_FAILOVER", "0")
    monkeypatch.setattr(jarvis, "_llm_failover", {"skip_claude_until": 0.0, "last_reason": "", "announced": False})
    assert jarvis._claude_request(body, 5) is None


@pytest.mark.parametrize("text,intent", [
    ("run a self check", "self_check"), ("are you ok", "self_check"), ("repeat that", "repeat"),
    ("say that shorter", "shorter"), ("what did you just do", "last_actions"), ("undo that", "undo"),
    ("set a timer for 5 minutes", "timer"), ("stop the stopwatch", "timer"),
    ("set a reminder to call mom", "timer_reminder"), ("what time is it", "time"),
    ("undo my last email to bob", "complex"),  # specific undo requests go to the full agent loop
])
def test_new_intents(text, intent):
    assert latency.classify_intent(text) == intent


def test_timers_and_stopwatch(monkeypatch):
    fired = []
    monkeypatch.setattr(jarvis, "queue_or_deliver_notification", lambda text, urgent=False, **k: fired.append((text, urgent)))
    assert jarvis._parse_duration_s("1 hour 30 minutes") == 5400
    assert jarvis._parse_duration_s("a ten minute timer") == 600
    assert jarvis._timer_reply("set a timer for 0.05 seconds") == "Timer set for 0 seconds."
    time.sleep(0.3)
    assert fired == [("Your 0 seconds timer is done.", True)]  # urgent: never held by quiet hours
    assert jarvis._timer_reply("set a timer for 2 minutes") == "Timer set for 2 minutes."
    assert "left" in jarvis._timer_reply("how long is left on my timer")
    assert jarvis._timer_reply("cancel my timers") == "Cancelled 1 timer."
    assert jarvis._timer_reply("set a timer to remind me to call mom") is None  # needs a reminder
    assert jarvis._timer_reply("stop the stopwatch") == "The stopwatch isn't running."
    assert jarvis._timer_reply("start the stopwatch") == "Stopwatch started."
    assert jarvis._timer_reply("stop the stopwatch").startswith("Stopped at")


def test_repeat_and_last_reply_tracking(monkeypatch):
    spoken = []
    monkeypatch.setattr(jarvis, "speak_text", lambda t: spoken.append(t))
    monkeypatch.setattr(jarvis, "flush_pending_notifications", lambda: None)
    monkeypatch.setattr(jarvis, "run_agent_loop", lambda *a, **k: "The meeting is at 3 PM.")
    monkeypatch.setattr(jarvis, "_last_reply", {"text": ""})
    jarvis.handle_text_command("when is my meeting", source="text")
    jarvis.handle_text_command("repeat that", source="text")
    assert spoken[-1] == "The meeting is at 3 PM."
    assert jarvis._last_reply["text"] == "The meeting is at 3 PM."


def test_undo_hands_recent_actions_to_the_agent_loop(monkeypatch):
    seen = {}
    monkeypatch.setattr(jarvis, "_recent_actions", lambda limit=5: [
        ("2026-09-23T10:00:00", "set_reminder", '{"text": "call mom"}', "Reminder set (id 7).")])
    monkeypatch.setattr(jarvis, "run_agent_loop", lambda t, **k: seen.setdefault("t", t) and "Undid it.")
    monkeypatch.setattr(jarvis, "speak_text", lambda t: None)
    monkeypatch.setattr(jarvis, "flush_pending_notifications", lambda: None)
    jarvis.handle_text_command("undo that", source="text")
    assert "set_reminder" in seen["t"] and "Reverse the newest one" in seen["t"]


def test_self_check_reports_problems_first(monkeypatch):
    monkeypatch.setattr(jarvis, "_claude_live_problem", lambda: "the Anthropic credit balance is too low")
    monkeypatch.setattr(jarvis, "_gemini_live_problem", lambda: None)
    monkeypatch.setattr(jarvis, "_dashboard_get_services_status", lambda: [
        {"name": "gmail", "status": "connected", "detail": "5 tool(s)"},
        {"name": "context7", "status": "failed", "detail": "last tried 10:00"}])
    report = jarvis.self_check_report()
    assert report.startswith("2 problems:")
    assert "credit balance" in report and "context7" in report and "1 of 2 tool servers" in report


def test_cleanup_old_logs(tmp_path):
    old, new, live = tmp_path / "old.log", tmp_path / "new.log", tmp_path / "jarvis_standalone.log"
    for f in (old, new, live):
        f.write_text("x")
    past = time.time() - 30 * 86400
    os.utime(old, (past, past))
    os.utime(live, (past, past))
    assert jarvis._cleanup_old_logs(tmp_path, days=14) == 1
    assert not old.exists() and new.exists() and live.exists()
