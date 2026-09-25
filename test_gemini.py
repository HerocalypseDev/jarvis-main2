"""Tests for the Gemini backend (jarvis_gemini.py) and the Claude<->Gemini switch in jarvis.py.
Run with: python -m pytest test_gemini.py -v

No network: every HTTP call is a fake, and the DB path is redirected to a temp file.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

import jarvis_gemini as g


# --- provider choice ----------------------------------------------------------------------------
def test_provider_precedence_file_over_env_over_default(tmp_path, monkeypatch):
    path = tmp_path / "llm_provider.json"
    monkeypatch.delenv("JARVIS_LLM_PROVIDER", raising=False)
    assert g.get_provider(path) == "claude"  # default
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "gemini")
    assert g.get_provider(path) == "gemini"  # env
    g.set_provider(path, "claude")
    assert g.get_provider(path) == "claude"  # file wins over env
    path.write_text("not json", encoding="utf-8")
    assert g.get_provider(path) == "gemini"  # corrupt file falls back to env
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "bogus")
    assert g.get_provider(path) == "claude"
    with pytest.raises(ValueError):
        g.set_provider(path, "openai")


# --- request translation ------------------------------------------------------------------------
def test_messages_tool_roundtrip_maps_ids_to_names_and_keeps_signatures():
    msgs = [
        {"role": "user", "content": "what is my status"},
        {"role": "assistant", "content": [
            {"type": "text", "text": "checking"},
            {"type": "tool_use", "id": "t1", "name": "system_status", "input": {}, "_thought_signature": "SIG"},
        ]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "CPU 5 percent"}]},
    ]
    c = g.convert_messages(msgs)
    assert [x["role"] for x in c] == ["user", "model", "user"]
    assert c[0]["parts"] == [{"text": "what is my status"}]
    assert c[1]["parts"][1] == {"functionCall": {"name": "system_status", "args": {}}, "thoughtSignature": "SIG"}
    assert c[2]["parts"] == [{"functionResponse": {"name": "system_status", "response": {"result": "CPU 5 percent"}}}]


def test_messages_image_and_empty_content():
    c = g.convert_messages([
        {"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAAA"}},
            {"type": "text", "text": "what is this"},
        ]},
        {"role": "assistant", "content": []},
    ])
    assert c[0]["parts"][0] == {"inlineData": {"mimeType": "image/jpeg", "data": "AAAA"}}
    assert c[1]["parts"] == [{"text": " "}]  # Gemini rejects a content with no parts


def test_tools_conversion_omits_empty_schemas_and_ignores_cache_control():
    tools = [
        {"name": "system_status", "description": "status", "input_schema": {"type": "object", "properties": {}}},
        {"name": "run_shell", "description": "shell", "cache_control": {"type": "ephemeral", "ttl": "1h"},
         "input_schema": {"$schema": "x", "type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    ]
    decls = g.convert_tools(tools)[0]["functionDeclarations"]
    assert "parametersJsonSchema" not in decls[0]
    assert decls[1]["parametersJsonSchema"]["required"] == ["command"]
    assert "$schema" not in decls[1]["parametersJsonSchema"]
    assert "cache_control" not in json.dumps(decls)
    assert g.convert_tools([]) == []


def test_to_request_system_blocks_max_tokens_and_thinking(monkeypatch):
    monkeypatch.delenv("JARVIS_GEMINI_THINKING", raising=False)
    body = {
        "system": [{"type": "text", "text": "STABLE", "cache_control": {"type": "ephemeral"}}, {"type": "text", "text": "VOLATILE"}],
        "messages": [{"role": "user", "content": "hi"}], "max_tokens": 321,
    }
    r = g.to_request(body, "gemini-3.1-flash-lite")
    assert r["systemInstruction"]["parts"][0]["text"] == "STABLE\n\nVOLATILE"
    assert r["generationConfig"] == {"maxOutputTokens": 321, "thinkingConfig": {"thinkingLevel": "minimal"}}
    assert g.to_request(body, "gemini-2.5-flash")["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}
    assert "thinkingConfig" not in g.to_request(body, "gemini-2.5-pro")["generationConfig"]  # can't be disabled
    assert "thinkingConfig" not in g.to_request(body, "gemini-3.1-flash-lite", think=False)["generationConfig"]
    monkeypatch.setenv("JARVIS_GEMINI_THINKING", "default")
    assert "thinkingConfig" not in g.to_request(body, "gemini-3.1-flash-lite")["generationConfig"]
    assert g.to_request({"messages": [], "system": "plain string"}, "m")["systemInstruction"]["parts"][0]["text"] == "plain string"


# --- response translation -----------------------------------------------------------------------
def test_response_text_tool_call_signature_usage_and_stop_reason():
    data = {
        "candidates": [{"finishReason": "STOP", "content": {"parts": [
            {"text": "internal thought", "thought": True},
            {"text": "Checking."},
            {"functionCall": {"name": "system_status", "args": {"a": 1}}, "thoughtSignature": "SIG"},
        ]}}],
        "usageMetadata": {"promptTokenCount": 1000, "cachedContentTokenCount": 800, "candidatesTokenCount": 20, "thoughtsTokenCount": 5},
    }
    r = g.from_response(data, "gemini-3.1-flash-lite")
    assert r["stop_reason"] == "tool_use" and r["model"] == "gemini-3.1-flash-lite"
    assert [b["type"] for b in r["content"]] == ["text", "tool_use"]  # thought part dropped
    tu = r["content"][1]
    assert tu["name"] == "system_status" and tu["input"] == {"a": 1} and tu["_thought_signature"] == "SIG"
    assert tu["id"].startswith("gemini_")
    assert r["usage"] == {"input_tokens": 200, "cache_read_input_tokens": 800,
                          "cache_creation_input_tokens": 0, "output_tokens": 25}


def test_response_stop_reasons_and_blocked_prompt():
    text = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "cut off"}]}}]}
    assert g.from_response(text, "m")["stop_reason"] == "max_tokens"
    done = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "ok"}]}}]}
    assert g.from_response(done, "m")["stop_reason"] == "end_turn"
    blocked = g.from_response({"promptFeedback": {"blockReason": "SAFETY"}}, "m")
    assert blocked["content"] == [] and blocked["stop_reason"] == "end_turn"  # caller falls back to its own message


# --- network behaviour --------------------------------------------------------------------------
def _ok(text="hello"):
    return json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}], "usageMetadata": {"promptTokenCount": 3}}).encode()


def _http_error(code, body):
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(body.encode()))


@pytest.fixture()
def gem_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("JARVIS_GEMINI_MODEL", "gemini-3.1-flash-lite")


def test_call_success_sends_key_in_header_and_returns_anthropic_shape(gem_env):
    seen = []

    def http(req, timeout):
        seen.append(req)
        return _ok("hi there")

    r = g.call({"messages": [{"role": "user", "content": "yo"}], "max_tokens": 50}, 10, http)
    assert r["content"] == [{"type": "text", "text": "hi there"}]
    assert seen[0].get_header("X-goog-api-key") == "test-key" and "gemini-3.1-flash-lite:generateContent" in seen[0].full_url
    assert "test-key" not in seen[0].full_url  # never in the URL


def test_call_without_key_returns_none(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert g.call({"messages": []}, 5, lambda r, t: b"{}") is None


def test_call_waits_out_a_short_429_then_succeeds(gem_env):
    calls, slept = [], []

    def http(req, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise _http_error(429, '{"error":{"details":[{"retryDelay":"7s"}]}}')
        return _ok()

    r = g.call({"messages": []}, 5, http, sleep=slept.append)
    assert r is not None and len(calls) == 2 and slept == [7.5]


def test_call_does_not_wait_for_a_long_quota_reset(gem_env):
    slept = []

    def http(req, timeout):
        raise _http_error(429, '{"error":{"details":[{"retryDelay":"3600s"}]}}')

    assert g.call({"messages": []}, 5, http, sleep=slept.append) is None
    assert slept == []  # a daily-quota 429 fails fast instead of hanging the command


def test_call_retries_once_without_thinking_config_on_400(gem_env):
    payloads = []

    def http(req, timeout):
        payloads.append(json.loads(req.data))
        if "thinkingConfig" in payloads[-1]["generationConfig"]:
            raise _http_error(400, '{"error":{"message":"thinking level not supported"}}')
        return _ok()

    assert g.call({"messages": []}, 5, http) is not None
    assert len(payloads) == 2 and "thinkingConfig" not in payloads[1]["generationConfig"]


def test_call_gives_up_on_other_client_errors_and_retries_server_errors(gem_env):
    n = []

    def bad(req, timeout):
        n.append(1)
        raise _http_error(403, "{}")

    assert g.call({"messages": []}, 5, bad, sleep=lambda s: None) is None and len(n) == 1

    m = []

    def flaky(req, timeout):
        m.append(1)
        if len(m) < 3:
            raise _http_error(503, "{}")
        return _ok()

    assert g.call({"messages": []}, 5, flaky, sleep=lambda s: None) is not None and len(m) == 3


# --- wiring in jarvis.py ------------------------------------------------------------------------
@pytest.fixture()
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "test.db"))
    import jarvis as j

    monkeypatch.setattr(j, "LLM_SETTINGS_PATH", tmp_path / "llm_provider.json")
    monkeypatch.delenv("JARVIS_LLM_PROVIDER", raising=False)
    monkeypatch.setattr(j, "get_mcp_tool_schemas", lambda: [])
    monkeypatch.setattr(j, "_history_snapshot", lambda: [])
    monkeypatch.setattr(j, "_append_history", lambda *a, **k: None)
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    j._reply_cache.clear()
    j._tool_result_cache.clear()
    return j


def test_claude_request_routes_to_gemini_when_selected_and_records_that_model(jarvis, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    g.set_provider(jarvis.LLM_SETTINGS_PATH, "gemini")
    fake = {"content": [{"type": "text", "text": "hi"}], "stop_reason": "end_turn", "model": "gemini-3.1-flash-lite",
            "usage": {"input_tokens": 5, "output_tokens": 2}}
    monkeypatch.setattr(jarvis.gemini, "call", lambda body, timeout, http: fake)
    recorded = []
    monkeypatch.setattr(jarvis.billing, "record_usage", lambda *a: recorded.append(a))
    assert jarvis._claude_request({"model": "claude-haiku-4-5", "messages": []}, 5) is fake
    import time
    time.sleep(0.2)
    assert recorded and recorded[0][2] == "gemini-3.1-flash-lite"  # the model that answered, not the Claude default


def test_agent_loop_works_on_gemini_alone_without_an_anthropic_key(jarvis, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    g.set_provider(jarvis.LLM_SETTINGS_PATH, "gemini")
    monkeypatch.setattr(
        jarvis.gemini, "call",
        lambda body, timeout, http: {"content": [{"type": "text", "text": "Hello from Gemini."}], "stop_reason": "end_turn", "usage": {}},
    )
    assert jarvis.run_agent_loop("say hello") == "Hello from Gemini."
    monkeypatch.setattr(jarvis.gemini, "call", lambda *a: None)
    assert "Gemini" in jarvis.run_agent_loop("say hello again")  # failure message names the active brain


def test_set_llm_provider_validation_and_persistence(jarvis, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert "isn't set up" in jarvis.set_llm_provider("gemini")  # no key: refuse, don't strand Jarvis
    assert jarvis._llm_provider() == "claude"
    assert "Unknown brain" in jarvis.set_llm_provider("openai")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    msg = jarvis.set_llm_provider("gemini")
    assert msg.startswith("Switched to Gemini") and "improve its products" in msg  # privacy note
    assert jarvis._llm_provider() == "gemini" and jarvis.LLM_SETTINGS_PATH.is_file()
    assert jarvis.set_llm_provider("claude").startswith("Switched to Claude") and jarvis._llm_provider() == "claude"
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert "isn't set up" in jarvis.set_llm_provider("claude")


def test_set_llm_provider_tool_is_registered_and_dispatches(jarvis, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    tool = next(t for t in jarvis.AGENT_TOOLS if t["name"] == "set_llm_provider")
    assert tool["input_schema"]["properties"]["provider"]["enum"] == ["claude", "gemini"]
    assert jarvis._execute_tool_impl("set_llm_provider", {"provider": "gemini"}, "switch to gemini").startswith("Switched to Gemini")
    assert jarvis._llm_status()["provider"] == "gemini"


def test_warmup_is_skipped_on_gemini(jarvis, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    g.set_provider(jarvis.LLM_SETTINGS_PATH, "gemini")
    started = []
    monkeypatch.setattr(jarvis.threading, "Thread", lambda *a, **k: started.append(1) or type("T", (), {"start": lambda s: None})())
    jarvis.start_prompt_cache_warmup()
    assert started == []  # Anthropic prompt-cache warmup never fires for Gemini


def test_gemini_models_have_prices_so_they_are_not_flagged_approximate():
    import jarvis_billing as b

    for model in ("gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"):
        assert b.compute_cost(model, {"input_tokens": 1_000_000})[2] is True
    assert b.compute_cost("gemini-3.5-flash-lite", {"input_tokens": 1_000_000})[0] == pytest.approx(0.30)  # not the shorter -flash prefix
    assert b.compute_cost("gemini-3.8-flash", {"input_tokens": 1})[2] is False  # unpriced: flagged approximate


# --- dashboard endpoints ------------------------------------------------------------------------
def test_dashboard_llm_endpoints(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "d.db"))
    import importlib
    import jarvis_dashboard as dash
    from fastapi.testclient import TestClient

    importlib.reload(dash)
    state = {"provider": "claude"}

    def get_llm():
        return {"provider": state["provider"], "gemini_model": "gm", "claude_model": "cm"}

    def set_llm(p):
        if p == "gemini":
            state["provider"] = "gemini"
            return "Switched to Gemini (gm)."
        return "Gemini isn't set up."

    with TestClient(dash._build_app(), base_url="http://127.0.0.1:8765") as c:  # not wired: harmless defaults
        assert c.get("/api/llm").json() == {"llm": None}
        assert c.post("/api/llm", json={"provider": "gemini"}).status_code == 501
    with TestClient(dash._build_app(get_llm=get_llm, set_llm=set_llm), base_url="http://127.0.0.1:8765") as c:
        assert c.get("/api/llm").json()["llm"]["provider"] == "claude"
        r = c.post("/api/llm", json={"provider": "gemini"})
        assert r.status_code == 200 and r.json()["ok"] and r.json()["llm"]["provider"] == "gemini"
        bad = c.post("/api/llm", json={"provider": "nope"})
        assert bad.status_code == 400 and not bad.json()["ok"]
    with TestClient(dash._build_app(get_llm=lambda: 1 / 0, set_llm=set_llm), base_url="http://127.0.0.1:8765") as c:
        assert c.get("/api/llm").json() == {"llm": None}  # a failing provider lookup never breaks the page
