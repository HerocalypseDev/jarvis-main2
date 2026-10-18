"""Real status checks (2026-10-18 debug report: "is my Windows MCP working?" was answered from a port scan and a
Windows service called McpManagementService). Status questions are answered by real checks, or "I can't check that".
Run: python -m pytest test_status.py -v"""
import asyncio
import time
import urllib.error

import pytest

import jarvis_status as st


def _checks():
    C = st.Check
    ok = lambda: (st.WORKING, "fine")  # noqa: E731
    return [C("mcp:windows", "Windows MCP", ("windows mcp", "windows tools"), ok),
            C("mcp:gmail", "the gmail tool server", ("gmail", "email"), ok),
            C("browser_tabs", "browser tabs", ("browser tabs", "browser extension"), ok),
            C("mcp:browser", "the browser tool server", ("browser",), ok),
            C("telegram", "the Telegram listener", ("telegram", "telegram bot"), ok),
            C("internet", "the internet", ("internet",), ok)]


@pytest.mark.parametrize("q,keys", [
    ("I'm Jarvis. It's my Windows MCP work now?", ["mcp:windows"]),   # the real (garbled) voice transcript
    ("is my windows mcp working", ["mcp:windows"]),
    ("is gmail working?", ["mcp:gmail"]),
    ("is the telegram bot up?", ["telegram"]),
    ("check if the internet is working", ["internet"]),
    ("is the browser tabs extension connected", ["browser_tabs"]),   # longest alias wins, not also "browser"
])
def test_status_questions_find_the_right_part(q, keys):
    assert st.is_status_question(q)
    assert st.match(q, _checks()) == keys


@pytest.mark.parametrize("q", ["open whatsapp", "send an email to mum", "what's the weather", "is it going to rain",
                               "is my calendar free tomorrow", "read my email"])
def test_ordinary_requests_are_not_status_questions(q):
    assert not st.is_status_question(q)


def test_everything_questions():
    for q in ("is everything working", "what's broken", "any problems?", "give me a system status report"):
        assert st.is_status_question(q) and st.asks_everything(q), q


def test_a_failing_or_slow_check_is_unknown_never_working():
    def boom():
        raise RuntimeError("nope")

    def slow():
        time.sleep(3)
        return st.WORKING, "late"
    checks = [st.Check("a", "A", (), boom), st.Check("b", "B", (), slow), st.Check("c", "C", (), lambda: ("great", ""))]
    res = {r["key"]: r for r in st.run(checks, ["a", "b", "c"], timeout=0.5)}
    assert all(r["state"] == st.UNKNOWN for r in res.values())
    assert "RuntimeError" in res["a"]["detail"] and "didn't answer" in res["b"]["detail"]
    assert "couldn't tell" in st.render(list(res.values()))


def test_everything_report_puts_problems_first():
    checks = [st.Check("a", "Alpha", (), lambda: (st.WORKING, "")), st.Check("b", "Beta", (), lambda: (st.DOWN, "it broke")),
              st.Check("c", "Gamma", (), lambda: (st.OFF, "")), st.Check("d", "Delta", (), lambda: (st.WORKING, ""))]
    text = st.render(st.run(checks, None), everything=True)
    assert text.startswith("1 thing is not working: Beta (it broke).")
    assert "Working: Alpha, Delta." in text and "1 more is switched off" in text


# --- jarvis.py wiring -------------------------------------------------------------------------------------------------
@pytest.fixture
def j(monkeypatch):
    import jarvis
    monkeypatch.setattr(jarvis, "_load_mcp_server_configs", lambda: {"windows": {"command": "uvx"}})
    monkeypatch.setattr(jarvis, "_mcp_started", True)
    monkeypatch.setattr(jarvis, "_start_announcement", lambda *a, **k: None)
    monkeypatch.setattr(jarvis, "_mcp_handles", {})
    monkeypatch.setattr(jarvis, "_mcp_failed_servers", {})
    return jarvis


def _handle(j, error=None):
    h = j._McpServerHandle.__new__(j._McpServerHandle)
    h.tools, h.error = [], error
    h.ready = type("E", (), {"is_set": lambda self: True})()
    return h


def test_windows_mcp_question_is_answered_by_asking_the_server(j, monkeypatch):
    j._mcp_handles["windows"] = _handle(j)
    asked = []
    monkeypatch.setattr(j, "_mcp_probe", lambda name, timeout=8.0: asked.append(name) or 17)
    assert j._status_question_keys("I'm Jarvis. It's my Windows MCP work now?") == ["mcp:windows"]
    reply = j._status_reply("I'm Jarvis. It's my Windows MCP work now?")
    assert asked == ["windows"] and reply.startswith("Windows MCP is working") and "17 tools" in reply


def test_connected_but_not_answering_is_down(j, monkeypatch):
    j._mcp_handles["windows"] = _handle(j)

    def dead(name, timeout=8.0):
        raise RuntimeError("Connection closed")
    monkeypatch.setattr(j, "_mcp_probe", dead)
    assert "NOT working" in j._status_reply("is windows mcp working?")


def test_a_failed_server_is_reconnected_now_so_a_fix_shows_at_once(j, monkeypatch):
    """"I fixed my Windows MCP but Jarvis still thinks it's down": the check reconnects before answering."""
    j._mcp_handles["windows"] = _handle(j, error="ModuleNotFoundError: No module named 'windows_mcp.__main__'")
    j._mcp_failed_servers["windows"] = {"cfg": {}, "last_attempt": None}

    def reconnect(name):
        j._mcp_handles[name] = _handle(j)
        j._mcp_failed_servers.pop(name, None)
    monkeypatch.setattr(j, "_mcp_reconnect_now", reconnect)
    monkeypatch.setattr(j, "_mcp_probe", lambda name, timeout=8.0: 9)
    assert j._status_reply("is my windows mcp working").startswith("Windows MCP is working")


def test_a_still_broken_server_says_why_and_how_to_fix_it(j, monkeypatch):
    j._mcp_handles["windows"] = _handle(j, error="ModuleNotFoundError: No module named 'windows_mcp.__main__'")
    j._mcp_failed_servers["windows"] = {"cfg": {}, "last_attempt": None}
    monkeypatch.setattr(j, "_mcp_reconnect_now", lambda name: None)
    reply = j._status_reply("is my windows mcp working")
    assert "NOT working" in reply and "uv cache clean" in reply


def test_windows_update_is_not_windows_mcp(j):
    assert j._status_question_keys("is windows update working?") is None


def test_probing_ports_and_processes_is_refused_during_a_status_question(j, monkeypatch):
    monkeypatch.setattr(j._command_ctx, "status_question", [], raising=False)
    assert j._status_probe_problem("Get-CimInstance Win32_Service -Filter \"Name like '%mcp%'\"")
    assert j._status_probe_problem("Get-NetTCPConnection -LocalPort 3000") is None  # unmatched question: shell is fine
    monkeypatch.setattr(j._command_ctx, "status_question", ["mcp:windows"])
    assert j._status_probe_problem("Get-NetTCPConnection -LocalPort 3000, 8080, 5000")
    assert j._status_probe_problem("Get-Process node, python")
    monkeypatch.setattr(j._command_ctx, "status_question", None)
    assert j._status_probe_problem("Get-Process node") is None  # not a status question: untouched


def test_telegram_listener_reports_a_wrong_token(j, monkeypatch):
    monkeypatch.setattr(j, "_listener_health", {})
    j._listener_ok("telegram")
    j._listener_failed("telegram", urllib.error.HTTPError("u", 404, "Not Found", {}, None))
    state, detail = j._listener_state("telegram", True, "x")
    assert state == st.DOWN and "bot token" in detail
    assert j._listener_state("telegram", False, "TELEGRAM_BOT_TOKEN")[0] == st.OFF
    j._listener_ok("telegram")
    assert j._listener_state("telegram", True, "x")[0] == st.WORKING


def test_unknown_things_get_an_honest_no_check(j):
    out = j._status_check_tool({"component": "my printer"})
    assert "No check exists" in out and "can't check" in out
    assert "mcp:windows" in j._status_check_tool({"component": "list"})


def test_every_registered_check_runs_without_crashing(j, monkeypatch):
    """Each check answers with a real state (or UNKNOWN with why) on a machine with nothing set up."""
    monkeypatch.setattr(j, "_claude_live_problem", lambda: "no Anthropic API key is set")
    monkeypatch.setattr(j, "_gemini_live_problem", lambda: "no Gemini API key is set")
    monkeypatch.setattr(j, "_mcp_reconnect_now", lambda name: None)
    monkeypatch.setattr(j, "_tcp_ok", lambda *a, **k: False)
    res = st.run(j._status_checks(), [c.key for c in j._status_checks()], timeout=20)
    assert res and all(r["state"] in st.STATES for r in res)
    crashed = [r for r in res if "check itself failed" in r["detail"]]
    allowed = {"mic", "speakers"}  # no audio hardware in a container
    assert not [r for r in crashed if r["key"] not in allowed], crashed


def test_supervisor_answers_a_probe_with_list_tools():
    import jarvis
    assert "_MCP_PROBE" in jarvis._mcp_server_supervisor.__code__.co_names
