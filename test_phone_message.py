"""Messages to the owner's own phone (2026-10-03, debug report): "send a random message to me on Telegram" got "I can't",
after the model ran a placeholder script and claimed it was sent. Temp DB; nothing is really sent."""

import pytest

import jarvis_tool_router as tool_router


@pytest.fixture
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "p.db"))
    import jarvis as j
    sent = []
    monkeypatch.setattr(j, "TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setattr(j, "TELEGRAM_CHAT_ID", "42")
    monkeypatch.setattr(j, "NTFY_TOPIC", "")
    monkeypatch.setattr(j, "_telegram_send", lambda text: sent.append(("telegram", text)) or True)
    monkeypatch.setattr(j, "_ntfy_publish", lambda text, title="Jarvis", priority="default": sent.append(("ntfy", text)) or True)
    monkeypatch.setattr(j, "_phone_sent", [])
    j._test_sent = sent
    return j


def test_send_me_a_message_on_telegram_works(J):
    out = J._execute_tool("send_to_my_phone", {"text": "Hello from Jarvis"}, "send a random message to me on telegram")
    assert out.startswith("Sent to your telegram: Hello from Jarvis")
    assert J._test_sent == [("telegram", "Hello from Jarvis")]
    # the claim check accepts "I've sent it" once this tool ran
    claim = next(c for c in J._ACTION_CLAIMS if c[0] == "send that")
    assert claim[2].search("send_to_my_phone")


def test_only_the_owners_own_channels_and_a_clear_setup_hint(J, monkeypatch):
    schema = next(t for t in J.AGENT_TOOLS if t["name"] == "send_to_my_phone")["input_schema"]
    assert set(schema["properties"]) == {"text", "channel"}  # no recipient field: it can only reach the owner
    out = J._execute_tool("send_to_my_phone", {"text": "hi", "channel": "ntfy"}, "push it to my phone")
    assert out.startswith("Tool failed:") and "NTFY_TOPIC" in out and J._test_sent == []
    monkeypatch.setattr(J, "_telegram_send", lambda text: False)
    assert J._execute_tool("send_to_my_phone", {"text": "hi"}, "text me").startswith("Tool failed:")


def test_phone_messages_are_rate_limited(J):
    for i in range(J.PHONE_MESSAGES_PER_HOUR):
        assert J._send_to_my_phone_tool({"text": f"m{i}"}).startswith("Sent")
    assert "already sent" in J._send_to_my_phone_tool({"text": "one too many"})
    assert len(J._test_sent) == J.PHONE_MESSAGES_PER_HOUR


def test_the_placeholder_script_from_the_report_is_refused(J, monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("must not run"))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("must not run"))
    J._command_ctx.source = "voice"
    try:
        out = J._execute_tool("run_shell", {"command": (
            "python -c \"import requests; requests.post('https://api.telegram.org/bot<YOUR_BOT_TOKEN>/sendMessage', "
            "data={'chat_id': '<YOUR_CHAT_ID>', 'text': 'Hello'})\"")}, "send a message to me on telegram")
        assert "send_to_my_phone" in out
        out = J._execute_tool("run_python", {"code": "api_key = 'YOUR_API_KEY'\nprint(call(api_key))"}, "do it")
        assert "placeholder" in out
    finally:
        J._command_ctx.source = None
    assert J._placeholder_code_problem("print('hello')") is None
    assert J._placeholder_code_problem("git grep -n sendMessage src/") is None  # searching code is fine


def test_tool_search_finds_it(J):
    said = "Hey, Jarvis. Send a message to me on time telegram, a random message."
    picked = [t["name"] for t in tool_router.select(said, J.AGENT_TOOLS, limit=J.TOOL_NARROWING_LIMIT)]
    assert "send_to_my_phone" in picked
    assert "send_to_my_phone" in J._narrowing_core(said)  # always offered when the phone/Telegram is named
    assert "send_to_my_phone" not in J._narrowing_core("open notepad")
