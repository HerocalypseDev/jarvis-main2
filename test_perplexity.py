"""Perplexity web search (jarvis_perplexity): no network, urlopen is faked."""
import io
import json

import pytest

import jarvis_perplexity as px


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_urlopen(payload, seen):
    def fake(req, timeout=0):
        seen.append({"url": req.full_url, "auth": req.headers.get("Authorization"),
                     "body": json.loads(req.data.decode())})
        return _Resp(json.dumps(payload).encode())
    return fake


def test_search_returns_answer_and_deduped_web_sources(monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test")
    monkeypatch.delenv("JARVIS_PERPLEXITY_MODEL", raising=False)
    seen = []
    payload = {"model": "sonar", "choices": [{"message": {"content": "It will rain in Leeds tomorrow."}}],
               "citations": ["https://a.example/x", "https://a.example/x", "javascript:alert(1)"],
               "search_results": [{"url": "https://b.example/y"}]}
    monkeypatch.setattr(px.urllib.request, "urlopen", _fake_urlopen(payload, seen))
    res = px.search("weather leeds tomorrow")
    assert res["answer"].startswith("It will rain") and res["sources"] == ["https://a.example/x", "https://b.example/y"]
    assert seen[0]["url"] == px.API_URL and seen[0]["auth"] == "Bearer pplx-test"
    assert seen[0]["body"]["model"] == "sonar"
    text = px.format_result(res)
    assert "Sources: [1] https://a.example/x [2] https://b.example/y" in text


def test_search_failures_return_none_and_never_log_the_key(monkeypatch, caplog):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-secret-123")

    def boom(req, timeout=0):
        raise px.urllib.error.HTTPError(req.full_url, 401, "bad", {}, io.BytesIO(b"invalid key pplx-secret-123"))
    monkeypatch.setattr(px.urllib.request, "urlopen", boom)
    assert px.search("x") is None
    assert "pplx-secret-123" not in caplog.text
    monkeypatch.setattr(px.urllib.request, "urlopen", _fake_urlopen({"choices": []}, []))
    assert px.search("x") is None
    monkeypatch.delenv("PERPLEXITY_API_KEY")
    assert px.search("x") is None and not px.enabled()


@pytest.fixture
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("JARVIS_LLM_TTS_STREAM", "0")
    import jarvis as j
    return j


def test_web_search_tool_uses_perplexity_and_falls_back_to_duckduckgo(jarvis, monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test")
    calls = []
    monkeypatch.setattr(jarvis.perplexity, "search",
                        lambda q, detailed=False: calls.append((q, detailed)) or {"answer": "Answer.", "sources": ["https://s.example"]})
    monkeypatch.setattr(jarvis, "_duckduckgo_search", lambda q: pytest.fail("DuckDuckGo must not run when Perplexity answered"))
    out = jarvis.web_search_and_summarize("research the best budget standing desks", "budget standing desks")
    assert out.startswith("Answer.") and "https://s.example" in out
    assert calls == [("budget standing desks", True)]           # research wording asks for a detailed answer
    # Perplexity down -> the old DuckDuckGo path still answers
    monkeypatch.setattr(jarvis.perplexity, "search", lambda q, detailed=False: None)
    monkeypatch.setattr(jarvis, "_duckduckgo_search", lambda q: [("Title", "Snippet")])
    monkeypatch.setattr(jarvis, "_llm_configured", lambda: False)
    assert jarvis.web_search_and_summarize("q", "q") == "Title. Snippet"
    # opt-out switch keeps DuckDuckGo even with a key
    monkeypatch.setenv("JARVIS_WEB_SEARCH", "duckduckgo")
    assert not jarvis.perplexity.enabled()


def test_perplexity_key_is_write_only_in_settings():
    import jarvis_settings as settings
    assert settings.is_secret("PERPLEXITY_API_KEY") and not settings.is_secret("JARVIS_PERPLEXITY_MODEL")
