"""Phone calls through CallMeBot (2026-10-17, owner: own number only, urgent alerts only). Nothing is really called:
every test hands in a fake opener or stubs callmebot.call."""

import io
import urllib.parse

import pytest

import jarvis_callmebot as callmebot


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _opener(body="Call queued", seen=None):
    def open_(req, timeout=None):
        if seen is not None:
            seen.append(req.full_url)
        return _Resp(body.encode())
    return open_


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    callmebot.reset_for_tests()
    monkeypatch.setenv("CALLMEBOT_TELEGRAM_USER", "@hero_test")
    yield
    callmebot.reset_for_tests()


def test_calls_only_the_configured_user_with_a_short_clean_text():
    seen = []
    ok, what = callmebot.call("Exam moved!\nSee https://example.com/x " + "word " * 200, opener=_opener(seen=seen))
    assert ok and "ringing" in what
    q = urllib.parse.parse_qs(urllib.parse.urlparse(seen[0]).query)
    assert q["user"] == ["@hero_test"] and q["rpt"] == ["2"]
    assert "\n" not in q["text"][0] and "example.com" not in q["text"][0]
    assert len(q["text"][0]) <= callmebot.MAX_TEXT_CHARS + 1


def test_user_forms(monkeypatch):
    for raw, want in (("hero_test", "@hero_test"), ("+234 801 234 5678", "+2348012345678"),
                      ("2348012345678", "+2348012345678"), ("bad name!", ""), ("", "")):
        monkeypatch.setenv("CALLMEBOT_TELEGRAM_USER", raw)
        assert callmebot.user() == want


def test_not_set_up_daily_cap_and_same_text_gap(monkeypatch):
    monkeypatch.setenv("CALLMEBOT_TELEGRAM_USER", "")
    ok, what = callmebot.call("hi", opener=_opener())
    assert not ok and "CALLMEBOT_TELEGRAM_USER" in what
    monkeypatch.setenv("CALLMEBOT_TELEGRAM_USER", "@hero_test")
    monkeypatch.setenv("JARVIS_CALLS_PER_DAY", "2")
    assert callmebot.call("one", opener=_opener())[0]
    ok, what = callmebot.call("one", opener=_opener())
    assert not ok and "last hour" in what
    assert callmebot.call("two", opener=_opener())[0]
    ok, what = callmebot.call("three", opener=_opener())
    assert not ok and "2 calls today" in what


def test_failures_say_why_and_dont_use_up_the_cap(monkeypatch):
    monkeypatch.setenv("JARVIS_CALLS_PER_DAY", "1")
    ok, what = callmebot.call("x", opener=_opener("<p>User not authorized to receive calls</p>"))
    assert not ok and "@CallMeBot_API" in what

    def boom(req, timeout=None):
        raise OSError("no network")
    ok, what = callmebot.call("x", opener=boom)
    assert not ok and "couldn't reach" in what
    assert callmebot.call("x", opener=_opener())[0]  # neither failure counted toward the 1-a-day cap


@pytest.fixture
def J(monkeypatch):
    import jarvis as j
    calls = []
    monkeypatch.setattr(j.callmebot, "call", lambda text, opener=None: calls.append(text) or (True, "CallMeBot is ringing your Telegram"))
    j._test_calls = calls
    return j


def test_call_me_tool_rings_only_the_owner(J):
    schema = next(t for t in J.AGENT_TOOLS if t["name"] == "send_to_my_phone")["input_schema"]
    assert "call" in schema["properties"]["channel"]["enum"] and set(schema["properties"]) == {"text", "channel"}
    out = J._execute_tool("send_to_my_phone", {"text": "Your build finished", "channel": "call"}, "call me when it's done")
    assert out.startswith("CallMeBot is ringing") and J._test_calls == ["Your build finished"]
    assert "send_to_my_phone" in J._narrowing_core("call me on my phone")


def test_tool_failure_is_reported_as_failed(J, monkeypatch):
    monkeypatch.setattr(J.callmebot, "call", lambda text, opener=None: (False, "already made 5 calls today"))
    out = J._execute_tool("send_to_my_phone", {"text": "hi", "channel": "call"}, "ring me")
    assert out.startswith("Tool failed:") and "5 calls" in out


def test_urgent_alert_calls_only_when_away_and_awake(J, monkeypatch):
    monkeypatch.setenv("JARVIS_TEST_ALLOW_CALLS", "1")
    monkeypatch.setattr(J.callmebot, "configured", lambda: True)

    class _T:
        def __init__(self, target, **kw):
            self.target = target

        def start(self):
            self.target()
    monkeypatch.setattr(J.threading, "Thread", _T)
    monkeypatch.setattr(J.sleep_mode, "is_active", lambda: False)
    monkeypatch.setattr(J, "_get_idle_seconds", lambda: 30.0)
    J._maybe_call_for_urgent("Server down")
    assert J._test_calls == []  # owner is at the PC: it's spoken, not phoned
    monkeypatch.setattr(J, "_get_idle_seconds", lambda: None)
    J._maybe_call_for_urgent("Server down")
    assert J._test_calls == []  # unknown idle never calls
    monkeypatch.setattr(J, "_get_idle_seconds", lambda: 900.0)
    monkeypatch.setattr(J.sleep_mode, "is_active", lambda: True)
    J._maybe_call_for_urgent("Server down")
    assert J._test_calls == []  # asleep: no call
    monkeypatch.setattr(J.sleep_mode, "is_active", lambda: False)
    monkeypatch.setenv("JARVIS_CALL_ON_URGENT", "0")
    J._maybe_call_for_urgent("Server down")
    assert J._test_calls == []
    monkeypatch.setenv("JARVIS_CALL_ON_URGENT", "1")
    J._maybe_call_for_urgent("Server down")
    assert J._test_calls == ["Jarvis here. Server down"]


def test_ai_can_not_change_who_gets_called():
    import jarvis_selfmanage as sm
    assert "CALLMEBOT_TELEGRAM_USER" in sm.AI_DENIED and "JARVIS_CALLS_PER_DAY" in sm.AI_DENIED
