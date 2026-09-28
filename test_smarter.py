"""Smarter/autonomous batch (2026-09-28): tool narrowing, claim checker, escalation, lessons memory,
embedding retrieval, eval runner, autonomy upgrades, local brain. Isolated temp DB; no network."""
import pytest

import jarvis_cache as cache
import jarvis_tool_router as router


@pytest.fixture()
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("JARVIS_LLM_TTS_STREAM", "0")
    monkeypatch.delenv("JARVIS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("JARVIS_TOOL_NARROWING", raising=False)
    import jarvis as j

    monkeypatch.setattr(j, "LLM_SETTINGS_PATH", tmp_path / "llm_provider.json")
    monkeypatch.setattr(j.stt_deepgram, "DEEPGRAM_API_KEY", "")
    monkeypatch.setattr(j.tts_deepgram, "DEEPGRAM_API_KEY", "")
    monkeypatch.setattr(j, "get_mcp_tool_schemas", lambda: [])
    monkeypatch.setattr(j, "_history_snapshot", lambda: [])
    monkeypatch.setattr(j, "_append_history", lambda *a, **k: None)
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    j._reply_cache.clear()
    j._tool_result_cache.clear()
    cache.reset_stats()
    return j


def _script(monkeypatch, j, replies):
    """Fake model: returns the scripted Anthropic-shaped responses in order; records each body."""
    it, seen = iter(replies), []
    monkeypatch.setattr(j, "_claude_request", lambda body, timeout: seen.append(body) or next(it))
    return seen


def _text(t):
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": t}]}


def _call(name, inp=None, i="t1"):
    return {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": i, "name": name, "input": inp or {}}]}


# --- Phase 1: tool narrowing -------------------------------------------------------------------
def test_router_ranks_the_right_tools_and_keeps_core_and_find_tools(jarvis):
    tools = jarvis.AGENT_TOOLS
    names = [t["name"] for t in router.select("turn on sleep mode", tools, limit=20)]
    assert "sleep_mode" in names and "remember_fact" in names and names[-1] == router.FIND_TOOLS_NAME
    assert len(names) <= 21
    assert router.index_for(tools).search("resize this window to half", 3)[0]["name"] in (
        "resize_all_windows", "control_window")


def test_narrowing_is_gemini_only_by_default(jarvis, monkeypatch):
    assert jarvis._tool_narrowing_on() is False  # Claude: keep the cached full prefix
    monkeypatch.setattr(jarvis, "_llm_provider", lambda: "gemini")
    assert jarvis._tool_narrowing_on() is True
    monkeypatch.setenv("JARVIS_TOOL_NARROWING", "off")
    assert jarvis._tool_narrowing_on() is False


def test_find_tools_widens_the_next_round_without_running_anything(jarvis, monkeypatch):
    monkeypatch.setenv("JARVIS_TOOL_NARROWING", "on")
    ran = []
    monkeypatch.setattr(jarvis, "_execute_tool_impl", lambda name, *a, **k: ran.append(name) or "done")
    seen = _script(monkeypatch, jarvis, [
        _call("find_tools", {"query": "guided breathing"}),
        _call("guided_breathing_exercise", {}, "t2"),
        _text("Breathing exercise started."),
    ])
    reply = jarvis.run_agent_loop("hmm help me calm down a bit")
    first = {t["name"] for t in seen[0]["tools"]}
    second = {t["name"] for t in seen[1]["tools"]}
    assert "find_tools" in first and len(first) < len(jarvis.AGENT_TOOLS)
    assert "guided_breathing_exercise" in second
    assert ran == ["guided_breathing_exercise"]  # find_tools itself never reaches _execute_tool
    assert reply == "Breathing exercise started."


# --- Phase 2: claim checker + escalate on failure ------------------------------------------------
@pytest.mark.parametrize("text,used,expected", [
    ("I've set a reminder for 5pm.", [], ["set that reminder"]),
    ("I've set a reminder for 5pm.", ["create_reminder"], []),
    ("Done, I sent the email to Sam.", [], ["send that"]),
    ("Done, I sent the email to Sam.", ["mcp_gmail_send_email"], []),
    ("I've added the meeting to your calendar.", [], ["add that to your calendar"]),
    ("Shall I set a reminder for that?", [], []),
    ("Do you want me to send it?", [], []),
    ("I can set a reminder if you like.", [], []),
    ("I've saved the notes to a document.", ["write_file"], []),
])
def test_unbacked_claims(jarvis, text, used, expected):
    assert jarvis._unbacked_claims(text, used) == expected


def test_unbacked_claim_is_nudged_into_the_real_call(jarvis, monkeypatch):
    ran = []
    monkeypatch.setattr(jarvis, "_execute_tool_impl", lambda name, *a, **k: ran.append(name) or "Reminder #4 set for 17:00.")
    seen = _script(monkeypatch, jarvis, [
        _text("I've set a reminder for 5pm to call mum."),
        _call("create_reminder", {"text": "call mum", "due_at": "17:00"}),
        _text("Reminder set for 5pm."),
    ])
    reply = jarvis.run_agent_loop("remind me to call mum at 5")
    assert ran == ["create_reminder"] and reply == "Reminder set for 5pm."
    assert "did NOT happen" in str(seen[1]["messages"][-1]["content"])


def test_claim_still_unbacked_after_nudge_is_corrected(jarvis, monkeypatch):
    _script(monkeypatch, jarvis, [_text("I've sent the email to Sam."), _text("I've sent the email to Sam.")])
    reply = jarvis.run_agent_loop("email sam the report")
    assert "didn't actually send that" in reply


def test_tool_failure_escalates_rest_of_command_without_thinking(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "SMART_MODEL", "claude-sonnet-5")
    monkeypatch.setattr(jarvis, "_execute_tool_impl", lambda *a, **k: "Error: folder not found")
    seen = _script(monkeypatch, jarvis, [_call("read_file", {"path": "x"}), _text("That folder doesn't exist.")])
    jarvis.run_agent_loop("open my notes")
    assert seen[0]["model"] == jarvis.CLAUDE_MODEL
    assert seen[1]["model"] == "claude-sonnet-5" and "thinking" not in seen[1]


def test_repeated_command_starts_on_the_smart_model(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "SMART_MODEL", "claude-sonnet-5")
    seen = _script(monkeypatch, jarvis, [_text("Here it is.")])
    jarvis.run_agent_loop("open my notes", tone={"repeated": True})
    assert seen[0]["model"] == "claude-sonnet-5"


def test_gemini_escalation_model_falls_back_to_the_configured_one(monkeypatch):
    import urllib.error
    import jarvis_gemini as g
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("JARVIS_GEMINI_MODEL", "gemini-3.1-flash-lite")
    asked = []

    def http(req, timeout):
        asked.append(req.full_url.split("/models/")[1].split(":")[0])
        if "3.6" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 503, "busy", {}, None)
        return b'{"candidates":[{"content":{"parts":[{"text":"ok"}]},"finishReason":"STOP"}]}'

    out = g.call({"model": "gemini-3.6-flash", "messages": [{"role": "user", "content": "hi"}]}, 5, http,
                 sleep=lambda s: None)
    assert out["content"][0]["text"] == "ok"
    assert asked == ["gemini-3.6-flash", "gemini-3.6-flash", "gemini-3.1-flash-lite"]
