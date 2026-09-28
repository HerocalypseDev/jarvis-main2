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
