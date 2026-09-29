"""Speed pass (2026-09-29): Gemini streaming into speech, stall protection + backup racing, connection
reuse, the spoken-length cap and the spoken lead-in. Nothing here touches the real network: transports
are fakes, and the keep-alive test talks to a throwaway server on 127.0.0.1."""
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import jarvis_cache as cache
import jarvis_gemini as g


@pytest.fixture(autouse=True)
def _gemini_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("JARVIS_GEMINI_MODEL", "gemini-3.5-flash-lite")
    for k in ("JARVIS_GEMINI_FALLBACK_MODEL", "JARVIS_GEMINI_BACKUP_ON_RATE_LIMIT", "JARVIS_GEMINI_HEDGE_S", "JARVIS_GEMINI_ATTEMPT_TIMEOUT_S",
              "JARVIS_GEMINI_STREAM", "JARVIS_GEMINI_KEEPALIVE", "JARVIS_GEMINI_FIRST_TOKEN_S"):
        monkeypatch.delenv(k, raising=False)


BODY = {"max_tokens": 200, "system": "s", "messages": [{"role": "user", "content": "hi"}], "tools": []}


def _chunk(*parts, finish=None, usage=None):
    cand = {"content": {"role": "model", "parts": list(parts)}}
    if finish:
        cand["finishReason"] = finish
    out = {"candidates": [cand]}
    if usage:
        out["usageMetadata"] = usage
    return out


def _sse(*chunks):
    return [("data: " + json.dumps(c) + "\r\n").encode() if i % 2 == 0 else b"\r\n"
            for c in chunks for i in (0, 1)]


# --- merging + streaming ------------------------------------------------------------------------
def test_merge_chunks_joins_text_keeps_calls_and_last_usage():
    merged = g._merge_chunks([
        _chunk({"text": "Hello "}),
        _chunk({"text": "there."}),
        _chunk({"functionCall": {"name": "get_time", "args": {}}, "thoughtSignature": "sig"},
               finish="STOP", usage={"promptTokenCount": 10, "candidatesTokenCount": 3}),
    ])
    out = g.from_response(merged, "gemini-3.5-flash-lite")
    assert [b["type"] for b in out["content"]] == ["text", "tool_use"]
    assert out["content"][0]["text"] == "Hello there."
    assert out["content"][1]["name"] == "get_time" and out["content"][1]["_thought_signature"] == "sig"
    assert out["stop_reason"] == "tool_use"
    assert out["usage"]["input_tokens"] == 10 and out["usage"]["output_tokens"] == 3


def test_stream_round_hands_text_over_as_it_arrives_and_stops_at_the_first_call():
    seen, events = [], []
    lines = _sse(_chunk({"text": "Let me check. "}), _chunk({"text": "One more bit."}),
                 _chunk({"functionCall": {"name": "system_status", "args": {}}}),
                 _chunk({"text": "after the call"}, finish="STOP", usage={"promptTokenCount": 5}))
    out = g.stream_round(BODY, 5, on_text=seen.append, on_text_done=lambda: events.append("done"),
                         on_first_token=lambda: events.append("first"), opener=lambda req, t: iter(lines))
    assert seen == ["Let me check. ", "One more bit."]  # nothing after the function call is spoken
    assert events == ["first", "done"]  # first token once, then the leading text ended (once)
    assert [b["type"] for b in out["content"]] == ["text", "tool_use", "text"]
    assert out["stop_reason"] == "tool_use"


def test_stream_round_plain_answer_reports_done_at_the_end():
    events = []
    lines = _sse(_chunk({"text": "Paris."}), _chunk({"text": " It is big."}, finish="STOP"))
    out = g.stream_round(BODY, 5, on_text=lambda d: events.append(d), on_text_done=lambda: events.append("done"),
                         opener=lambda req, t: iter(lines))
    assert events == ["Paris.", " It is big.", "done"]
    assert out["content"][0]["text"] == "Paris. It is big." and out["stop_reason"] == "end_turn"


def test_stream_round_failure_before_any_text_returns_none():
    def opener(req, t):
        raise urllib.error.HTTPError(req.full_url, 503, "busy", None, None)

    assert g.stream_round(BODY, 5, on_text=lambda d: None, opener=opener) is None


def test_stream_round_break_after_speech_returns_what_arrived_instead_of_repeating_it():
    def opener(req, t):
        def gen():
            yield from _sse(_chunk({"text": "First sentence. "}))
            raise ConnectionResetError("dropped")
        return gen()

    spoken = []
    out = g.stream_round(BODY, 5, on_text=spoken.append, opener=opener)
    assert spoken == ["First sentence. "]
    assert out is not None and out["content"][0]["text"] == "First sentence. "  # not None: no double-speak retry


def test_stream_round_gives_up_quickly_when_nothing_arrives(monkeypatch):
    monkeypatch.setattr(g, "first_token_timeout_s", lambda: 0.2)
    release = threading.Event()

    def opener(req, t):
        def gen():
            release.wait(5)
            yield from ()
        return gen()

    started = time.monotonic()
    try:
        assert g.stream_round(BODY, 30, on_text=lambda d: None, opener=opener) is None
        assert time.monotonic() - started < 3
    finally:
        release.set()


def test_stream_round_off_switch_and_missing_key(monkeypatch):
    monkeypatch.setenv("JARVIS_GEMINI_STREAM", "0")
    assert g.stream_round(BODY, 5, opener=lambda r, t: iter([])) is None
    monkeypatch.delenv("JARVIS_GEMINI_STREAM")
    monkeypatch.delenv("GEMINI_API_KEY")
    assert g.stream_round(BODY, 5, opener=lambda r, t: iter([])) is None


def test_stream_round_uses_the_escalation_model_named_in_the_body():
    urls = []

    def opener(req, t):
        urls.append(req.full_url)
        return iter(_sse(_chunk({"text": "ok"}, finish="STOP")))

    g.stream_round({**BODY, "model": "gemini-3.5-flash"}, 5, opener=opener)
    assert "gemini-3.5-flash:streamGenerateContent" in urls[0] and urls[0].endswith("alt=sse")


# --- stall protection + backup racing -----------------------------------------------------------
def _ok(text="answer"):
    return json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode()


def test_a_timing_out_model_is_tried_twice_not_four_times():
    calls = []

    def http(req, timeout):
        calls.append(timeout)
        raise TimeoutError("slow")

    assert g.call(BODY, 180, http, sleep=lambda s: None) is None
    assert len(calls) == g.MAX_TIMEOUT_ATTEMPTS == 2
    assert calls[0] == g.attempt_timeout_s() == 60.0  # not the loop's 180 s round cap


def test_attempt_timeout_is_configurable(monkeypatch):
    monkeypatch.setenv("JARVIS_GEMINI_ATTEMPT_TIMEOUT_S", "20")
    seen = []
    g.call(BODY, 180, lambda req, t: seen.append(t) or _ok(), sleep=lambda s: None)
    assert seen == [20.0]


def test_slow_primary_is_raced_by_the_backup_and_the_first_answer_wins(monkeypatch):
    monkeypatch.setenv("JARVIS_GEMINI_FALLBACK_MODEL", "gemini-flash-lite-latest")
    monkeypatch.setenv("JARVIS_GEMINI_HEDGE_S", "0.2")
    release = threading.Event()
    models = []

    def http(req, timeout):
        model = req.full_url.split("/models/")[1].split(":")[0]
        models.append(model)
        if model == "gemini-3.5-flash-lite":
            release.wait(10)  # a stalled primary
            return _ok("slow answer")
        return _ok("backup answer")

    started = time.monotonic()
    try:
        out = g.call(BODY, 180, http, sleep=lambda s: None)
        assert out["content"][0]["text"] == "backup answer"
        assert time.monotonic() - started < 3
        assert models[0] == "gemini-3.5-flash-lite" and "gemini-flash-lite-latest" in models
    finally:
        release.set()


def test_fast_primary_never_calls_the_backup(monkeypatch):
    monkeypatch.setenv("JARVIS_GEMINI_FALLBACK_MODEL", "gemini-flash-lite-latest")
    monkeypatch.setenv("JARVIS_GEMINI_HEDGE_S", "5")
    models = []

    def http(req, timeout):
        models.append(req.full_url.split("/models/")[1].split(":")[0])
        return _ok()

    assert g.call(BODY, 180, http)["content"][0]["text"] == "answer"
    assert models == ["gemini-3.5-flash-lite"]


def test_no_backup_configured_means_no_racing(monkeypatch):
    monkeypatch.setenv("JARVIS_GEMINI_HEDGE_S", "0.05")
    models = []

    def http(req, timeout):
        models.append(req.full_url)
        time.sleep(0.2)
        return _ok()

    assert g.call(BODY, 180, http) is not None
    assert len(models) == 1  # the user chooses models (2026-09-25); nothing is switched behind their back


def test_a_quota_error_is_never_raced_or_swapped(monkeypatch):
    monkeypatch.setenv("JARVIS_GEMINI_FALLBACK_MODEL", "gemini-flash-lite-latest")
    monkeypatch.setenv("JARVIS_GEMINI_HEDGE_S", "0.05")
    models = []

    def http(req, timeout):
        models.append(req.full_url.split("/models/")[1].split(":")[0])
        raise urllib.error.HTTPError(req.full_url, 429, "quota", None,
                                     __import__("io").BytesIO(b'{"error":{"details":[{"retryDelay":"3600s"}]}}'))

    assert g.call(BODY, 180, http, sleep=lambda s: None) is None
    assert models == ["gemini-3.5-flash-lite"]


def test_overload_still_falls_back_to_the_backup_once(monkeypatch):
    monkeypatch.setenv("JARVIS_GEMINI_FALLBACK_MODEL", "gemini-flash-lite-latest")
    monkeypatch.setenv("JARVIS_GEMINI_HEDGE_S", "0")  # racing off: the old overload fallback path
    models = []

    def http(req, timeout):
        model = req.full_url.split("/models/")[1].split(":")[0]
        models.append(model)
        if model == "gemini-3.5-flash-lite":
            raise urllib.error.HTTPError(req.full_url, 503, "busy", None, __import__("io").BytesIO(b"{}"))
        return _ok("from backup")

    out = g.call(BODY, 180, http, sleep=lambda s: None)
    assert out["content"][0]["text"] == "from backup"


def test_429_wait_cap_covers_real_free_tier_delays():
    # Found live (2026-09-29): the free tier allows ~5 requests/min per model and Google asks for 17-27 s.
    # A 15 s cap made every such burst fail with "couldn't reach Gemini".
    assert g.MAX_RETRY_WAIT_S >= 27


def test_a_short_429_is_waited_out_and_answered():
    waits, calls = [], []

    def http(req, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "quota", None,
                                         __import__("io").BytesIO(b'{"error":{"details":[{"retryDelay":"26s"}]}}'))
        return _ok("after the wait")

    out = g.call(BODY, 180, http, sleep=waits.append)
    assert out["content"][0]["text"] == "after the wait" and waits == [26.5] and len(calls) == 2


def test_stream_waits_out_a_short_rate_limit_instead_of_wasting_a_request(monkeypatch):
    slept, opens = [], []
    monkeypatch.setattr(g.time, "sleep", slept.append)

    def opener(req, t):
        opens.append(1)
        if len(opens) == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "quota", None,
                                         __import__("io").BytesIO(b'{"error":{"details":[{"retryDelay":"17s"}]}}'))
        return iter(_sse(_chunk({"text": "Hello there."}, finish="STOP")))

    out = g.stream_round(BODY, 60, on_text=lambda d: None, opener=opener)
    assert out is not None and out["content"][0]["text"] == "Hello there."
    assert slept == [17.5] and len(opens) == 2


def test_stream_does_not_wait_for_a_long_quota_reset(monkeypatch):
    slept = []
    monkeypatch.setattr(g.time, "sleep", slept.append)

    def opener(req, t):
        raise urllib.error.HTTPError(req.full_url, 429, "quota", None,
                                     __import__("io").BytesIO(b'{"error":{"details":[{"retryDelay":"3600s"}]}}'))

    assert g.stream_round(BODY, 60, on_text=lambda d: None, opener=opener) is None
    assert slept == [] and "used up" in g.last_error_reason()


# --- readable failure reasons + the diagnostic --------------------------------------------------
def test_failures_are_explained_in_plain_words():
    m = "gemini-3.5-flash-lite"
    assert "try again in about 27 seconds" in g.reason_from_http(429, '{"retryDelay":"26s"}', m)
    assert "used up" in g.reason_from_http(429, '{"retryDelay":"3600s"}', m)
    assert "overloaded" in g.reason_from_http(503, "", m)
    assert "rejected the API key" in g.reason_from_http(400, "API key not valid. Please pass a valid API key.", m)
    assert "rejected the API key" in g.reason_from_http(401, "", m)
    assert "denied access" in g.reason_from_http(403, "", m)
    assert "isn't available" in g.reason_from_http(404, "", m)
    assert "timed out" in g.reason_from_exception(TimeoutError("x"))
    assert "certificate" in g.reason_from_exception(OSError("CERTIFICATE_VERIFY_FAILED"))
    assert "couldn't connect" in g.reason_from_exception(ConnectionResetError("reset"))


def test_last_error_is_kept_until_a_call_works():
    g._clear_error()

    def bad(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 503, "busy", None, __import__("io").BytesIO(b"{}"))

    assert g.call(BODY, 30, bad, sleep=lambda s: None) is None
    assert "overloaded" in g.last_error_reason()
    assert g.call(BODY, 30, lambda req, t: _ok(), sleep=lambda s: None) is not None
    assert g.last_error_reason() == ""
    g._note_error("old")
    g._last_error["ts"] -= 500
    assert g.last_error_reason() == ""  # stale reasons are not spoken


def test_missing_key_is_a_reason_too(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    assert g.call(BODY, 30, lambda r, t: b"") is None
    assert "no Gemini API key" in g.last_error_reason()


def test_diagnose_reports_a_key_that_differs_between_windows_and_env_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("GEMINI_API_KEY=AIzaOLDKEY000000000000\nJARVIS_GEMINI_MODEL=gemini-3.1-flash-lite\n")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaNEWKEY111111111111")

    def boom(*a, **k):
        raise urllib.error.URLError("no network in tests")

    monkeypatch.setattr(g.urllib.request, "urlopen", boom)
    monkeypatch.setattr(g, "_open", boom)
    lines = []
    problems = g.diagnose(tmp_path / ".env", out=lines.append)
    text = "\n".join(lines)
    assert any("differs" in p for p in problems)
    assert "AIza...1111" in text and "OLDKEY" not in text  # never prints a full key
    assert "gemini-3.5-flash-lite" in text  # the environment's model beats .env until a restart
    assert any("couldn't connect" in p for p in problems)


def test_diagnose_without_any_key_says_so(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    problems = g.diagnose(tmp_path / ".env", out=lambda *_: None)
    assert problems and "No Gemini key" in problems[0]


# --- connection reuse ---------------------------------------------------------------------------
class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        if self.path.startswith("/bad"):
            body, code = b'{"error":"nope"}', 400
        else:
            body, code = b'{"ok": true}', 200
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture()
def local_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _post(url, data=b"{}"):
    return urllib.request.Request(url, data=data, method="POST", headers={"content-type": "application/json"})


def test_connection_is_reused_between_requests(local_server):
    pool = g._Pool()
    g._pool = pool
    for _ in range(3):
        key, conn, resp = g._open(_post(local_server + "/x"), 5)
        assert json.loads(resp.read()) == {"ok": True}
        g._finish(key, conn, resp)
    assert pool.opened == 1 and pool.reused == 2


def test_error_status_raises_httperror_with_a_readable_body(local_server):
    g._pool = g._Pool()
    with pytest.raises(urllib.error.HTTPError) as ei:
        g._open(_post(local_server + "/bad"), 5)
    assert ei.value.code == 400 and b"nope" in ei.value.read()


def test_a_stale_pooled_connection_is_replaced_transparently(local_server):
    pool = g._Pool()
    g._pool = pool
    key, conn, resp = g._open(_post(local_server + "/x"), 5)
    resp.read()
    g._finish(key, conn, resp)
    conn.sock.close()  # the server/network dropped it while idle
    key, conn, resp = g._open(_post(local_server + "/x"), 5)
    assert json.loads(resp.read()) == {"ok": True}
    assert pool.opened == 2


def test_idle_connections_expire(local_server, monkeypatch):
    pool = g._Pool()
    g._pool = pool
    key, conn, resp = g._open(_post(local_server + "/x"), 5)
    resp.read()
    g._finish(key, conn, resp)
    monkeypatch.setattr(g, "POOL_IDLE_S", -1.0)
    g._open(_post(local_server + "/x"), 5)
    assert pool.opened == 2 and pool.reused == 0


def test_http_post_uses_plain_urllib_for_non_https_and_when_switched_off(monkeypatch):
    calls = []

    class _R:
        def read(self):
            return b"x"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(g.urllib.request, "urlopen", lambda req, timeout=None: calls.append(req.full_url) or _R())
    assert g.http_post(_post("http://example.test/a"), 5) == b"x"
    monkeypatch.setenv("JARVIS_GEMINI_KEEPALIVE", "0")
    assert g.http_post(_post("https://example.test/a"), 5) == b"x"
    assert len(calls) == 2


# --- jarvis.py: streaming loop, spoken cap, lead-in ---------------------------------------------
@pytest.fixture()
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import jarvis as j

    monkeypatch.setattr(j, "LLM_SETTINGS_PATH", tmp_path / "llm_provider.json")
    monkeypatch.delenv("JARVIS_LLM_PROVIDER", raising=False)
    monkeypatch.setattr(j, "get_mcp_tool_schemas", lambda: [])
    monkeypatch.setattr(j, "_history_snapshot", lambda: [])
    monkeypatch.setattr(j, "_append_history", lambda *a, **k: None)
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    monkeypatch.setattr(j, "_tts_disk_cache", cache.TTSDiskCache(tmp_path / "tts"))
    monkeypatch.setenv("JARVIS_LLM_TTS_STREAM", "1")
    monkeypatch.setenv("JARVIS_ACK_PHRASES", "0")
    j._reply_cache.clear()
    j._tool_result_cache.clear()
    cache.reset_stats()
    monkeypatch.setattr(j, "_llm_provider", lambda: "gemini")
    return j


def test_gemini_rounds_stream_sentences_into_speech_and_mark_the_reply_spoken(jarvis, monkeypatch):
    spoken = []
    monkeypatch.setattr(jarvis, "speak_text", lambda t: spoken.append(t))
    lines = _sse(_chunk({"text": "Paris is the capital of France. "}),
                 _chunk({"text": "It sits on the Seine river."}, finish="STOP"))
    monkeypatch.setattr(jarvis.gemini, "stream_round",
                        lambda body, timeout, on_text=None, on_text_done=None, on_first_token=None, opener=None:
                        _drive(on_text, on_text_done, on_first_token, ["Paris is the capital of France. ",
                                                                        "It sits on the Seine river."]))
    monkeypatch.setattr(jarvis, "_claude_request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no fallback")))
    reply = jarvis.run_agent_loop("tell me about paris", narrate=True)
    assert reply == "Paris is the capital of France. It sits on the Seine river."
    assert spoken == ["Paris is the capital of France.", "It sits on the Seine river."]
    assert jarvis.reply_already_spoken_via_stream() is True
    assert lines  # (fixture data kept for readability of the scenario)


def _drive(on_text, on_done, on_first, deltas):
    if on_first:
        on_first()
    for d in deltas:
        on_text(d)
    on_done()
    text = "".join(deltas)
    return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "usage": {}}


def test_final_answer_after_a_tool_call_is_streamed_too_on_gemini(jarvis, monkeypatch):
    spoken, executed = [], []
    monkeypatch.setattr(jarvis, "speak_text", lambda t: spoken.append(t))
    monkeypatch.setattr(jarvis, "_execute_tool", lambda name, inp, transcript: executed.append(name) or "42 percent")
    rounds = iter([
        lambda on_text, on_done, on_first: (on_first(), on_text("Let me check that."), on_done(),
                                            {"content": [{"type": "text", "text": "Let me check that."},
                                                         {"type": "tool_use", "id": "t1", "name": "system_status",
                                                          "input": {}}], "stop_reason": "tool_use", "usage": {}})[-1],
        lambda on_text, on_done, on_first: _drive(on_text, on_done, on_first, ["Your CPU is at 42 percent."]),
    ])

    def fake_stream(body, timeout, on_text=None, on_text_done=None, on_first_token=None, opener=None):
        return next(rounds)(on_text, on_text_done, on_first_token)

    monkeypatch.setattr(jarvis.gemini, "stream_round", fake_stream)
    monkeypatch.setattr(jarvis, "_claude_request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no fallback")))
    reply = jarvis.run_agent_loop("what's my cpu usage", narrate=True)
    assert executed == ["system_status"]
    assert spoken == ["Let me check that.", "Your CPU is at 42 percent."]  # each spoken once, live
    assert reply == "Your CPU is at 42 percent." and jarvis.reply_already_spoken_via_stream() is True


def test_gemini_stream_failure_falls_back_to_the_normal_call(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "speak_text", lambda t: None)
    monkeypatch.setattr(jarvis.gemini, "stream_round", lambda *a, **k: None)
    monkeypatch.setattr(jarvis, "_claude_request",
                        lambda body, timeout: {"content": [{"type": "text", "text": "Fallback."}],
                                               "stop_reason": "end_turn", "usage": {}})
    assert jarvis.run_agent_loop("hello there", narrate=True) == "Fallback."
    assert jarvis.reply_already_spoken_via_stream() is False


def test_can_stream_round_rules(jarvis, monkeypatch):
    assert jarvis._can_stream_round(0, True, False, 0) and jarvis._can_stream_round(3, True, False, 0)  # gemini: every round
    assert not jarvis._can_stream_round(0, False, False, 0)  # nobody is listening (phone)
    assert not jarvis._can_stream_round(0, True, True, 0)  # smart-model round
    assert not jarvis._can_stream_round(1, True, False, jarvis.MAX_NARRATED_LINES)  # narration cap reached
    monkeypatch.setenv("JARVIS_GEMINI_STREAM", "0")
    assert not jarvis._can_stream_round(0, True, False, 0)
    monkeypatch.setattr(jarvis, "_llm_provider", lambda: "claude")
    assert jarvis._can_stream_round(0, True, False, 0) and not jarvis._can_stream_round(1, True, False, 0)
    monkeypatch.setattr(jarvis, "_llm_provider", lambda: "ollama")
    assert not jarvis._can_stream_round(0, True, False, 0)


def test_long_streamed_reply_is_cut_for_speech_and_says_so(jarvis, monkeypatch):
    spoken = []
    monkeypatch.setattr(jarvis, "speak_text", lambda t: spoken.append(t))
    monkeypatch.setenv("JARVIS_LIVE_SPEECH_MAX_CHARS", "100")
    sentences = [f"This is spoken sentence number {i} of the answer. " for i in range(1, 7)]
    monkeypatch.setattr(jarvis.gemini, "stream_round",
                        lambda body, timeout, on_text=None, on_text_done=None, on_first_token=None, opener=None:
                        _drive(on_text, on_text_done, on_first_token, sentences))
    reply = jarvis.run_agent_loop("tell me a long story", narrate=True)
    assert reply.count("sentence number") == 6  # the returned reply (dashboard/history) is never trimmed
    assert spoken[-1] == jarvis.CUT_SPEECH_HINT
    said = [s for s in spoken[:-1]]
    assert 1 <= len(said) < 6 and sum(map(len, said)) <= 100 + len(said[0])


def test_asking_for_detail_or_detailed_style_lifts_the_cap(jarvis, monkeypatch):
    assert jarvis._live_speech_limit("explain how engines work in detail") == 0
    assert jarvis._live_speech_limit("tell me about engines") == jarvis.LIVE_SPEECH_MAX_CHARS
    monkeypatch.setenv("JARVIS_REPLY_STYLE", "detailed")
    assert jarvis._live_speech_limit("tell me about engines") == 0
    monkeypatch.delenv("JARVIS_REPLY_STYLE")
    monkeypatch.setenv("JARVIS_LIVE_SPEECH_MAX_CHARS", "0")
    assert jarvis._live_speech_limit("tell me about engines") == 0
    monkeypatch.setattr(jarvis, "_llm_provider", lambda: "claude")
    assert jarvis._live_speech_limit("tell me about engines") == 0  # Claude keeps its existing behaviour


def test_live_speaker_always_says_the_first_sentence_even_if_it_is_long(jarvis, monkeypatch):
    spoken = []
    monkeypatch.setattr(jarvis, "speak_text", lambda t: spoken.append(t))
    sp = jarvis._LiveSpeaker(20)
    sp("A very long first sentence that is over the limit on its own.")
    sp("Second.")
    assert spoken == ["A very long first sentence that is over the limit on its own."] and sp.cut and sp.dropped == 7


def test_ack_kind_recognises_work_not_questions(jarvis):
    assert jarvis._ack_kind("open my notes and find the budget") == "lookup"
    assert jarvis._ack_kind("hey jarvis, can you please send an email to sam") == "action"
    assert jarvis._ack_kind("search for the best pizza near me") == "lookup"
    assert jarvis._ack_kind("what is the capital of france") is None
    assert jarvis._ack_kind("thanks") is None and jarvis._ack_kind("") is None
    assert jarvis._ack_kind("open") is None  # one word: nothing to acknowledge yet


def test_ack_plays_first_and_the_reply_waits_for_it(jarvis, monkeypatch):
    monkeypatch.setenv("JARVIS_ACK_PHRASES", "1")
    monkeypatch.setattr(jarvis.sleep_mode, "is_active", lambda: False)
    order = []
    real_await = jarvis._await_ack

    def fake_speak(text):
        real_await()  # the real speak_text does this first
        order.append(("start", text))
        time.sleep(0.15 if text in jarvis.ACK_PHRASES else 0)
        order.append(("end", text))

    monkeypatch.setattr(jarvis, "speak_text", fake_speak)
    jarvis._command_ctx.ack_started = False
    jarvis._command_ctx.ack_thread = None
    jarvis._command_ctx.started = time.monotonic()
    assert jarvis._start_ack("action") is True
    fake_speak("Here is the real reply.")
    kinds = [(k, t in jarvis.ACK_PHRASES) for k, t in order]
    assert kinds == [("start", True), ("end", True), ("start", False), ("end", False)]  # no overlap, ack first


def test_only_one_ack_per_command_and_never_in_sleep_mode(jarvis, monkeypatch):
    monkeypatch.setenv("JARVIS_ACK_PHRASES", "1")
    monkeypatch.setattr(jarvis, "speak_text", lambda t: None)
    monkeypatch.setattr(jarvis.sleep_mode, "is_active", lambda: False)
    jarvis._command_ctx.ack_started = False
    jarvis._command_ctx.ack_thread = None
    jarvis._command_ctx.started = time.monotonic()
    assert jarvis._start_ack("action") is True
    assert jarvis._start_ack("lookup") is False  # once per command
    jarvis._await_ack()
    jarvis._command_ctx.ack_started = False
    monkeypatch.setattr(jarvis.sleep_mode, "is_active", lambda: True)
    assert jarvis._start_ack("action") is False
    monkeypatch.setattr(jarvis.sleep_mode, "is_active", lambda: False)
    monkeypatch.setenv("JARVIS_ACK_PHRASES", "0")
    assert jarvis._start_ack("action") is False


def test_ack_phrases_rotate_and_never_repeat_back_to_back(jarvis):
    picked = [jarvis._pick_ack("action") for _ in range(30)]
    assert all(a != b for a, b in zip(picked, picked[1:]))
    assert set(picked) <= set(jarvis.ACK_ACTION)


def test_ack_is_dropped_after_a_barge_in(jarvis, monkeypatch):
    monkeypatch.setenv("JARVIS_ACK_PHRASES", "1")
    monkeypatch.setattr(jarvis.sleep_mode, "is_active", lambda: False)
    jarvis._command_ctx.ack_started = False
    jarvis._command_ctx.started = time.monotonic() - 1
    monkeypatch.setattr(jarvis, "_speech_interrupted_at", [time.monotonic()])
    assert jarvis._start_ack("action") is False


def test_tool_call_with_no_words_triggers_a_lead_in_during_the_loop(jarvis, monkeypatch):
    monkeypatch.setenv("JARVIS_ACK_PHRASES", "1")
    monkeypatch.setattr(jarvis.sleep_mode, "is_active", lambda: False)
    spoken = []
    real_await = jarvis._await_ack
    monkeypatch.setattr(jarvis, "speak_text", lambda t: (real_await(), spoken.append(t)))
    monkeypatch.setattr(jarvis, "_execute_tool", lambda name, inp, transcript: "42 percent")
    jarvis._command_ctx.ack_started = False
    jarvis._command_ctx.ack_thread = None
    jarvis._command_ctx.started = time.monotonic()
    rounds = iter([
        lambda on_text, on_done, on_first: (on_first(), on_done(),
                                            {"content": [{"type": "tool_use", "id": "t1", "name": "system_status",
                                                          "input": {}}], "stop_reason": "tool_use", "usage": {}})[-1],
        lambda on_text, on_done, on_first: _drive(on_text, on_done, on_first, ["Your CPU is at 42 percent."]),
    ])
    monkeypatch.setattr(jarvis.gemini, "stream_round",
                        lambda body, timeout, on_text=None, on_text_done=None, on_first_token=None, opener=None:
                        next(rounds)(on_text, on_text_done, on_first_token))
    jarvis.run_agent_loop("how is my computer doing", narrate=True)
    assert spoken[0] in jarvis.ACK_PHRASES and spoken[-1] == "Your CPU is at 42 percent."
    assert len(spoken) == 2


def test_lead_in_is_not_added_when_the_model_already_narrated(jarvis, monkeypatch):
    monkeypatch.setenv("JARVIS_ACK_PHRASES", "1")
    monkeypatch.setattr(jarvis.sleep_mode, "is_active", lambda: False)
    spoken = []
    monkeypatch.setattr(jarvis, "speak_text", lambda t: spoken.append(t))
    monkeypatch.setattr(jarvis, "_execute_tool", lambda name, inp, transcript: "ok")
    jarvis._command_ctx.ack_started = False
    jarvis._command_ctx.ack_thread = None
    jarvis._command_ctx.started = time.monotonic()
    rounds = iter([
        lambda on_text, on_done, on_first: (on_text("Sure, checking now."), on_done(),
                                            {"content": [{"type": "text", "text": "Sure, checking now."},
                                                         {"type": "tool_use", "id": "t1", "name": "system_status",
                                                          "input": {}}], "stop_reason": "tool_use", "usage": {}})[-1],
        lambda on_text, on_done, on_first: _drive(on_text, on_done, on_first, ["All good."]),
    ])
    monkeypatch.setattr(jarvis.gemini, "stream_round",
                        lambda body, timeout, on_text=None, on_text_done=None, on_first_token=None, opener=None:
                        next(rounds)(on_text, on_text_done, on_first_token))
    jarvis.run_agent_loop("what's happening", narrate=True)
    time.sleep(0.05)
    assert not any(p in jarvis.ACK_PHRASES for p in spoken)


def test_settings_page_lists_the_new_speed_knobs():
    import jarvis_settings as s
    keys = {e["key"] for e in s.SETTINGS}
    for k in ("JARVIS_GEMINI_FALLBACK_MODEL", "JARVIS_GEMINI_HEDGE_S", "JARVIS_GEMINI_STREAM",
              "JARVIS_ACK_PHRASES", "JARVIS_LIVE_SPEECH_MAX_CHARS", "JARVIS_GEMINI_ATTEMPT_TIMEOUT_S"):
        assert k in keys, k


def test_unavailable_reply_names_the_real_reason(jarvis, monkeypatch):
    g._note_error("gemini-3.5-flash-lite is rate limited, try again in about 27 seconds")
    assert jarvis._llm_unavailable_reply() == (
        "Sorry, I couldn't reach Gemini: gemini-3.5-flash-lite is rate limited, try again in about 27 seconds.")
    g._clear_error()
    assert jarvis._llm_unavailable_reply() == "Sorry, I couldn't reach Gemini just now."


def _rate_limited_primary(models):
    def http(req, timeout):
        model = req.full_url.split("/models/")[1].split(":")[0]
        models.append(model)
        if model == "gemini-3.5-flash-lite":
            raise urllib.error.HTTPError(req.full_url, 429, "quota", None,
                                         __import__("io").BytesIO(b'{"error":{"details":[{"retryDelay":"26s"}]}}'))
        return _ok("from backup")
    return http


def test_opt_in_backup_answers_at_once_when_the_main_model_is_rate_limited(monkeypatch):
    monkeypatch.setenv("JARVIS_GEMINI_FALLBACK_MODEL", "gemini-flash-lite-latest")
    monkeypatch.setenv("JARVIS_GEMINI_BACKUP_ON_RATE_LIMIT", "1")
    models, waits = [], []
    out = g.call(BODY, 180, _rate_limited_primary(models), sleep=waits.append)
    assert out["content"][0]["text"] == "from backup"
    assert models == ["gemini-3.5-flash-lite", "gemini-flash-lite-latest"] and waits == []  # no 26 s wait


def test_backup_is_not_used_for_rate_limits_unless_switched_on(monkeypatch):
    monkeypatch.setenv("JARVIS_GEMINI_FALLBACK_MODEL", "gemini-flash-lite-latest")
    models, waits = [], []
    out = g.call(BODY, 180, _rate_limited_primary(models), sleep=waits.append)
    assert waits and set(waits) == {26.5}  # the old behaviour: wait it out on the same model, retrying
    assert "gemini-flash-lite-latest" not in models and out is None


def test_switch_without_a_backup_model_changes_nothing(monkeypatch):
    monkeypatch.setenv("JARVIS_GEMINI_BACKUP_ON_RATE_LIMIT", "1")
    models, waits = [], []
    g.call(BODY, 180, _rate_limited_primary(models), sleep=waits.append)
    assert waits and set(waits) == {26.5} and set(models) == {"gemini-3.5-flash-lite"}


def test_stream_does_not_wait_when_the_backup_is_switched_on_for_rate_limits(monkeypatch):
    monkeypatch.setenv("JARVIS_GEMINI_FALLBACK_MODEL", "gemini-flash-lite-latest")
    monkeypatch.setenv("JARVIS_GEMINI_BACKUP_ON_RATE_LIMIT", "1")
    slept = []
    monkeypatch.setattr(g.time, "sleep", slept.append)

    def opener(req, t):
        raise urllib.error.HTTPError(req.full_url, 429, "quota", None,
                                     __import__("io").BytesIO(b'{"error":{"details":[{"retryDelay":"17s"}]}}'))

    assert g.stream_round(BODY, 60, on_text=lambda d: None, opener=opener) is None  # call() then uses the backup
    assert slept == []
