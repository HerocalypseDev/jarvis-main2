"""Speed fixes for slow file saves (2026-10-16 debug report: one "write a file" command took 1.5-3 minutes).
1) A quiet Gemini stream (a long tool call being written) is kept open while the ordinary call runs next to it,
   instead of being thrown away after 8 s and re-sent. 2) A workspace setting that can't be used falls back to
   the default folder instead of failing every plain-name save. No real network: transports are fakes."""
import json
import threading
import time

import pytest

import jarvis_gemini as g
import jarvis_workspace as ws


@pytest.fixture(autouse=True)
def _gemini_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("JARVIS_GEMINI_MODEL", "gemini-3.5-flash-lite")
    for k in ("JARVIS_GEMINI_STREAM", "JARVIS_GEMINI_KEEPALIVE", "JARVIS_GEMINI_FIRST_TOKEN_S"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(g, "first_token_timeout_s", lambda: 0.2)


BODY = {"max_tokens": 200, "system": "s", "messages": [{"role": "user", "content": "hi"}], "tools": []}
CALL = {"candidates": [{"content": {"role": "model", "parts": [
    {"functionCall": {"name": "write_file", "args": {"path": "a.docx", "content": "x"}}}]}, "finishReason": "STOP"}]}
SIDE = {"content": [{"type": "text", "text": "from the normal call"}], "stop_reason": "end_turn", "usage": {}}


def _slow_opener(delay, chunks, release=None):
    def opener(req, t):
        def gen():
            if release is not None:
                release.wait(delay)
            else:
                time.sleep(delay)
            for c in chunks:
                yield ("data: " + json.dumps(c) + "\r\n").encode()
        return gen()
    return opener


def test_quiet_stream_is_kept_and_wins_when_it_answers_first():
    calls = []

    def race():
        calls.append(1)
        time.sleep(2)
        return SIDE
    out = g.stream_round(BODY, 10, opener=_slow_opener(0.5, [CALL]), race=race)
    assert calls == [1]  # the normal call was started once the stream went quiet...
    assert out is not SIDE and out["content"][0]["name"] == "write_file"  # ...but the stream's work was kept


def test_normal_call_wins_when_the_stream_stays_quiet():
    release = threading.Event()
    try:
        started = time.monotonic()
        out = g.stream_round(BODY, 10, opener=_slow_opener(5, [CALL], release), race=lambda: SIDE)
        assert out is SIDE and time.monotonic() - started < 2
    finally:
        release.set()


def test_stream_failure_waits_for_the_running_normal_call():
    def opener(req, t):
        def gen():
            time.sleep(0.4)
            raise OSError("connection reset")
            yield b""
        return gen()

    def race():
        time.sleep(0.6)
        return SIDE
    assert g.stream_round(BODY, 10, opener=opener, race=race) is SIDE


def test_without_race_the_old_give_up_rule_still_applies():
    release = threading.Event()
    try:
        assert g.stream_round(BODY, 10, opener=_slow_opener(5, [CALL], release)) is None
    finally:
        release.set()


# --- the agent loop uses the raced answer, and never repeats a failed one ---------------------------------
@pytest.fixture
def jarvis(monkeypatch, tmp_path):
    import jarvis as j
    monkeypatch.setenv("JARVIS_ACK_PHRASES", "0")
    monkeypatch.setattr(j, "_llm_provider", lambda: "gemini")
    monkeypatch.setattr(j, "speak_text", lambda t: None)
    j._reply_cache.clear()
    j._tool_result_cache.clear()
    return j


def test_agent_loop_uses_the_raced_answer_and_does_not_mark_it_spoken(jarvis, monkeypatch):
    requests = []
    monkeypatch.setattr(jarvis, "_claude_request", lambda body, timeout: requests.append(1) or SIDE)
    monkeypatch.setattr(jarvis.gemini, "stream_round", lambda body, timeout, race=None, **k: race())
    jarvis._reset_reply_stream_spoken()  # a command starts clean; an earlier test on this thread may have left it set
    assert jarvis.run_agent_loop("hello there", narrate=True) == "from the normal call"
    assert requests == [1]  # one request, not the race plus a second fallback call
    assert jarvis.reply_already_spoken_via_stream() is False  # nothing was spoken live: say it normally


def test_agent_loop_does_not_repeat_a_raced_call_that_failed(jarvis, monkeypatch):
    requests = []
    monkeypatch.setattr(jarvis, "_claude_request", lambda body, timeout: requests.append(1) or None)

    def fake_stream(body, timeout, race=None, **k):
        race()
        return None
    monkeypatch.setattr(jarvis.gemini, "stream_round", fake_stream)
    jarvis.run_agent_loop("hello there", narrate=True)
    assert requests == [1]


# --- workspace setting that can't be used --------------------------------------------------------------
def test_unusable_workspace_setting_falls_back_to_the_default(monkeypatch, tmp_path):
    blocker = tmp_path / "a_file"
    blocker.write_text("x")
    monkeypatch.setattr(ws, "DEFAULT_ROOT", str(tmp_path / "default_ws"))
    monkeypatch.setenv("JARVIS_WORKSPACE_DIR", str(blocker / "Jarvis_Workspace"))  # can't be created
    ws._root_checked.clear()
    assert ws.root() == tmp_path / "default_ws"
    assert "JARVIS_WORKSPACE_DIR" in ws.root_problem()
    target, refusal = ws.resolve_write_path("Checklist.docx", "1. item")
    assert refusal == "" and str(target).startswith(str(tmp_path / "default_ws"))


def test_good_workspace_setting_is_used_and_created(monkeypatch, tmp_path):
    want = tmp_path / "mine" / "Jarvis_Workspace"
    monkeypatch.setenv("JARVIS_WORKSPACE_DIR", str(want))
    ws._root_checked.clear()
    assert ws.root() == want and want.is_dir() and ws.root_problem() == ""


def test_write_file_saves_and_says_the_setting_is_wrong(monkeypatch, tmp_path):
    import jarvis as j
    blocker = tmp_path / "a_file"
    blocker.write_text("x")
    monkeypatch.setattr(ws, "DEFAULT_ROOT", str(tmp_path / "default_ws"))
    monkeypatch.setenv("JARVIS_WORKSPACE_DIR", str(blocker / "ws"))
    ws._root_checked.clear()
    out = j._write_file_tool("notes.txt", "hello", False)
    assert out.startswith("Wrote 5 chars") and "JARVIS_WORKSPACE_DIR" in out
    assert (tmp_path / "default_ws" / "Notes" / "notes.txt").read_text() == "hello"
