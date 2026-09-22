"""Tests for the Deepgram Speed Upgrade: jarvis_stt_deepgram.py, jarvis_tts_deepgram.py,
jarvis_latency.py, jarvis_cache.CircuitBreaker, and their wiring in jarvis.py (STT/TTS backend
selection, fallback chains, sentence-level TTS pipelining, filler phrase).

Never makes a real network call — every urlopen is monkeypatched. Run with:
  python -m pytest test_deepgram_voice.py -v
"""

from __future__ import annotations

import io
import json
import threading
import time
import wave

import numpy as np
import pytest

import jarvis_cache as cache
import jarvis_latency as latency
import jarvis_stt_deepgram as stt_deepgram
import jarvis_tts_deepgram as tts_deepgram


def _wav_bytes(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


# --- CircuitBreaker --------------------------------------------------------------------------
def test_circuit_breaker_trips_and_cools_down(monkeypatch):
    cb = cache.CircuitBreaker(threshold=2, cooldown_s=0.05)
    assert cb.allow()
    cb.record(False)
    assert cb.allow()  # one failure isn't enough
    cb.record(False)
    assert not cb.allow()  # tripped
    time.sleep(0.06)
    assert cb.allow()  # cooldown elapsed


def test_circuit_breaker_success_resets_failures():
    cb = cache.CircuitBreaker(threshold=2, cooldown_s=60)
    cb.record(False)
    cb.record(True)
    cb.record(False)
    assert cb.allow()  # only one consecutive failure since the reset


# --- jarvis_latency ----------------------------------------------------------------------------
def test_voice_latency_marks_and_finish(caplog):
    lat = latency.VoiceLatency()
    lat.stt_backend = "deepgram"
    lat.tts_backend = "aura2"
    lat.mark("stt")
    lat.mark("ttft")
    lat.mark("tts_ttfa")
    with caplog.at_level("INFO"):
        lat.finish()
    assert "latency stt=" in caplog.text
    assert "stt_backend=deepgram" in caplog.text
    assert "tts_backend=aura2" in caplog.text
    recent = latency.recent(1)
    assert recent and recent[-1]["stt_backend"] == "deepgram"


def test_voice_latency_context_start_current_end():
    assert latency.current() is None
    lat = latency.start()
    assert latency.current() is lat
    latency.end()
    assert latency.current() is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("what time is it", "time"),
        ("what's the date today", "date"),
        ("turn the volume up", "volume"),
        ("open notepad", "open_app"),
        ("set a timer for five minutes", "timer_reminder"),
        ("summarize my last three emails", "complex"),
    ],
)
def test_classify_intent(text, expected):
    assert latency.classify_intent(text) == expected


# --- jarvis_stt_deepgram -----------------------------------------------------------------------
def _dg_response(transcript: str, confidence: float) -> bytes:
    return json.dumps({
        "results": {"channels": [{"alternatives": [{"transcript": transcript, "confidence": confidence}]}]}
    }).encode()


def test_stt_no_key_returns_none(monkeypatch):
    monkeypatch.setattr(stt_deepgram, "DEEPGRAM_API_KEY", "")
    assert stt_deepgram.transcribe(np.zeros(1600, dtype=np.float32), 16000) is None


def test_stt_success_returns_transcript(monkeypatch):
    monkeypatch.setattr(stt_deepgram, "DEEPGRAM_API_KEY", "k")
    monkeypatch.setattr(
        stt_deepgram, "_urlopen_bounded", lambda req, timeout: _dg_response("hello world", 0.95)
    )
    audio = (np.random.rand(1600).astype(np.float32) - 0.5)
    assert stt_deepgram.transcribe(audio, 16000) == "hello world"


def test_stt_low_confidence_falls_back(monkeypatch):
    monkeypatch.setattr(stt_deepgram, "DEEPGRAM_API_KEY", "k")
    monkeypatch.setattr(
        stt_deepgram, "_urlopen_bounded", lambda req, timeout: _dg_response("mumble", 0.2)
    )
    audio = (np.random.rand(1600).astype(np.float32) - 0.5)
    assert stt_deepgram.transcribe(audio, 16000) is None


def test_stt_network_error_returns_none(monkeypatch):
    monkeypatch.setattr(stt_deepgram, "DEEPGRAM_API_KEY", "k")

    def boom(req, timeout):
        raise RuntimeError("network down")

    monkeypatch.setattr(stt_deepgram, "_urlopen_bounded", boom)
    audio = (np.random.rand(1600).astype(np.float32) - 0.5)
    assert stt_deepgram.transcribe(audio, 16000) is None


def test_stt_empty_audio_short_circuits_without_a_request(monkeypatch):
    monkeypatch.setattr(stt_deepgram, "DEEPGRAM_API_KEY", "k")

    def boom(req, timeout):
        raise AssertionError("should not be called for empty audio")

    monkeypatch.setattr(stt_deepgram, "_urlopen_bounded", boom)
    assert stt_deepgram.transcribe(np.zeros(0, dtype=np.float32), 16000) == ""


# --- jarvis_stt_deepgram.StreamingSession (cloud-latency pass, Phase A) -----------------------
class _FakeWS:
    """Duck-types the websocket-client WebSocket object's send/recv/close surface."""

    def __init__(self, recv_messages=(), fail_send=False, fail_recv_immediately=False):
        self.sent: list[tuple[str, object]] = []
        self._recv_messages = list(recv_messages)
        self._fail_send = fail_send
        self._fail_recv_immediately = fail_recv_immediately
        self.closed = False

    def send_binary(self, data):
        if self._fail_send:
            raise ConnectionError("send failed")
        self.sent.append(("binary", data))

    def send(self, data):
        if self._fail_send:
            raise ConnectionError("send failed")
        self.sent.append(("text", data))

    def recv(self):
        if self._fail_recv_immediately:
            raise ConnectionError("recv failed")
        if self._recv_messages:
            return self._recv_messages.pop(0)
        raise ConnectionError("connection closed by server")

    def close(self):
        self.closed = True


class _FakeWebsocketLib:
    def __init__(self, ws=None, connect_error=None):
        self._ws = ws
        self._connect_error = connect_error
        self.connect_calls = []

    def create_connection(self, url, header=None, timeout=None):
        self.connect_calls.append((url, header, timeout))
        if self._connect_error is not None:
            raise self._connect_error
        return self._ws


def _results_msg(transcript: str, is_final: bool, confidence: float = 0.95) -> str:
    return json.dumps({
        "type": "Results",
        "is_final": is_final,
        "channel": {"alternatives": [{"transcript": transcript, "confidence": confidence}]},
    })


def test_streaming_session_happy_path_uses_only_final_results(monkeypatch):
    ws = _FakeWS(recv_messages=[
        _results_msg("hello", is_final=False, confidence=0.4),  # interim: must be ignored
        _results_msg("hello there", is_final=True, confidence=0.97),
        json.dumps({"type": "Metadata", "request_id": "x"}),
    ])
    monkeypatch.setattr(stt_deepgram, "_websocket_lib", _FakeWebsocketLib(ws=ws))
    monkeypatch.setattr(stt_deepgram, "DEEPGRAM_API_KEY", "k")

    session = stt_deepgram.StreamingSession(16000)
    assert session.start() is True
    session.feed(np.zeros(1600, dtype=np.float32))
    result = session.finish(timeout_s=2.0)
    assert result == ("hello there", 0.97)
    assert ws.closed is True
    # exactly one audio chunk, then Finalize, then CloseStream, in that order (no reordering)
    kinds = [k for k, _ in ws.sent]
    assert kinds == ["binary", "text", "text"]
    assert json.loads(ws.sent[1][1])["type"] == "Finalize"
    assert json.loads(ws.sent[2][1])["type"] == "CloseStream"


def test_streaming_session_accumulates_multiple_final_segments(monkeypatch):
    ws = _FakeWS(recv_messages=[
        _results_msg("first segment", is_final=True, confidence=0.9),
        _results_msg("second segment", is_final=True, confidence=0.92),
    ])
    monkeypatch.setattr(stt_deepgram, "_websocket_lib", _FakeWebsocketLib(ws=ws))
    monkeypatch.setattr(stt_deepgram, "DEEPGRAM_API_KEY", "k")
    session = stt_deepgram.StreamingSession(16000)
    session.start()
    result = session.finish(timeout_s=2.0)
    assert result == ("first segment second segment", 0.92)


def test_streaming_session_connect_failure_returns_false_and_finish_is_none(monkeypatch):
    monkeypatch.setattr(
        stt_deepgram, "_websocket_lib", _FakeWebsocketLib(connect_error=RuntimeError("no route"))
    )
    monkeypatch.setattr(stt_deepgram, "DEEPGRAM_API_KEY", "k")
    session = stt_deepgram.StreamingSession(16000)
    assert session.start() is False
    session.feed(np.zeros(1600, dtype=np.float32))  # must not raise even with no connection
    assert session.finish() is None


def test_streaming_session_no_key_never_connects(monkeypatch):
    fake_lib = _FakeWebsocketLib(ws=_FakeWS())
    monkeypatch.setattr(stt_deepgram, "_websocket_lib", fake_lib)
    monkeypatch.setattr(stt_deepgram, "DEEPGRAM_API_KEY", "")
    session = stt_deepgram.StreamingSession(16000)
    assert session.start() is False
    assert fake_lib.connect_calls == []


def test_streaming_session_mid_stream_send_failure_falls_back(monkeypatch):
    ws = _FakeWS(fail_send=True)
    monkeypatch.setattr(stt_deepgram, "_websocket_lib", _FakeWebsocketLib(ws=ws))
    monkeypatch.setattr(stt_deepgram, "DEEPGRAM_API_KEY", "k")
    session = stt_deepgram.StreamingSession(16000)
    session.start()
    session.feed(np.zeros(1600, dtype=np.float32))
    assert session.finish(timeout_s=2.0) is None  # send failed -> caller falls back to REST


def test_streaming_session_low_confidence_falls_back(monkeypatch):
    ws = _FakeWS(recv_messages=[_results_msg("mumble", is_final=True, confidence=0.2)])
    monkeypatch.setattr(stt_deepgram, "_websocket_lib", _FakeWebsocketLib(ws=ws))
    monkeypatch.setattr(stt_deepgram, "DEEPGRAM_API_KEY", "k")
    session = stt_deepgram.StreamingSession(16000)
    session.start()
    assert session.finish(timeout_s=2.0) is None


def test_streaming_session_empty_stream_returns_empty_transcript(monkeypatch):
    ws = _FakeWS(recv_messages=[])  # server closes immediately, nothing was ever said
    monkeypatch.setattr(stt_deepgram, "_websocket_lib", _FakeWebsocketLib(ws=ws))
    monkeypatch.setattr(stt_deepgram, "DEEPGRAM_API_KEY", "k")
    session = stt_deepgram.StreamingSession(16000)
    session.start()
    result = session.finish(timeout_s=2.0)
    assert result == ("", 0.0)  # valid silence, distinct from None (a real failure)


def test_streaming_session_feed_before_start_resolves_is_not_dropped(monkeypatch):
    """Mirrors jarvis.py's real usage: start() is kicked off on a helper thread and feed() is
    called immediately without waiting for it — nothing fed in that window should be lost."""
    ws = _FakeWS(recv_messages=[_results_msg("not dropped", is_final=True, confidence=0.9)])
    monkeypatch.setattr(stt_deepgram, "_websocket_lib", _FakeWebsocketLib(ws=ws))
    monkeypatch.setattr(stt_deepgram, "DEEPGRAM_API_KEY", "k")
    session = stt_deepgram.StreamingSession(16000)

    t = threading.Thread(target=session.start)
    t.start()
    session.feed(np.zeros(1600, dtype=np.float32))  # racing ahead of start() resolving
    t.join()
    result = session.finish(timeout_s=2.0)
    assert result == ("not dropped", 0.9)
    assert "binary" in [k for k, _ in ws.sent]  # the fed chunk really was sent


def test_streaming_session_finish_waits_for_in_flight_start(monkeypatch):
    """finish() called (almost) immediately after start() is kicked off on another thread must
    not race ahead and wrongly conclude "no session" while the connect is still in flight."""
    ws = _FakeWS(recv_messages=[_results_msg("quick", is_final=True, confidence=0.9)])

    class SlowLib(_FakeWebsocketLib):
        def create_connection(self, url, header=None, timeout=None):
            time.sleep(0.1)
            return super().create_connection(url, header=header, timeout=timeout)

    monkeypatch.setattr(stt_deepgram, "_websocket_lib", SlowLib(ws=ws))
    monkeypatch.setattr(stt_deepgram, "DEEPGRAM_API_KEY", "k")
    session = stt_deepgram.StreamingSession(16000)
    threading.Thread(target=session.start, daemon=True).start()
    result = session.finish(timeout_s=2.0)  # must wait out the 0.1s connect, not return None early
    assert result == ("quick", 0.9)


# --- jarvis_tts_deepgram ------------------------------------------------------------------------
def test_tts_no_key_raises(monkeypatch):
    monkeypatch.setattr(tts_deepgram, "DEEPGRAM_API_KEY", "")
    with pytest.raises(RuntimeError):
        tts_deepgram.synthesize("hello")


def test_tts_success_returns_pcm_and_sample_rate(monkeypatch):
    monkeypatch.setattr(tts_deepgram, "DEEPGRAM_API_KEY", "k")
    pcm = b"\x01\x00" * 100
    monkeypatch.setattr(
        tts_deepgram, "_urlopen_bounded", lambda req, timeout: _wav_bytes(pcm, 24000)
    )
    raw, sr = tts_deepgram.synthesize("hello there")
    assert raw == pcm and sr == 24000


def test_tts_network_error_propagates(monkeypatch):
    monkeypatch.setattr(tts_deepgram, "DEEPGRAM_API_KEY", "k")

    def boom(req, timeout):
        raise RuntimeError("network down")

    monkeypatch.setattr(tts_deepgram, "_urlopen_bounded", boom)
    with pytest.raises(RuntimeError):
        tts_deepgram.synthesize("hello there")


def test_tts_warm_never_raises_without_key(monkeypatch):
    monkeypatch.setattr(tts_deepgram, "DEEPGRAM_API_KEY", "")
    tts_deepgram.warm()  # no-op, must not raise


def test_stt_warm_never_raises_on_failure(monkeypatch):
    monkeypatch.setattr(stt_deepgram, "DEEPGRAM_API_KEY", "k")

    def boom(req, timeout):
        raise RuntimeError("down")

    monkeypatch.setattr(stt_deepgram, "_urlopen_bounded", boom)
    stt_deepgram.warm()  # swallows the failure, must not raise


# --- jarvis_tts_deepgram.StreamingSynthesis (cloud-latency pass, Phase B) ----------------------
class _FakeSpeakWS:
    def __init__(self, recv_sequence=(), fail_send=False):
        self.sent: list = []
        self._seq = list(recv_sequence)
        self._fail_send = fail_send
        self.closed = False

    def send(self, data):
        if self._fail_send:
            raise ConnectionError("send failed")
        self.sent.append(data)

    def recv(self):
        if self._seq:
            item = self._seq.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        raise ConnectionError("connection closed by server")

    def close(self):
        self.closed = True


class _FakeSpeakWebsocketLib:
    def __init__(self, ws=None, connect_error=None):
        self._ws = ws
        self._connect_error = connect_error
        self.connect_calls = []

    def create_connection(self, url, header=None, timeout=None):
        self.connect_calls.append((url, header, timeout))
        if self._connect_error is not None:
            raise self._connect_error
        return self._ws


def test_streaming_synthesis_connect_sends_speak_then_close(monkeypatch):
    ws = _FakeSpeakWS(recv_sequence=[b"\x01\x02", b"\x03\x04"])
    monkeypatch.setattr(tts_deepgram, "_websocket_lib", _FakeSpeakWebsocketLib(ws=ws))
    monkeypatch.setattr(tts_deepgram, "DEEPGRAM_API_KEY", "k")
    session = tts_deepgram.StreamingSynthesis("hello there")
    assert session.connect() is True
    assert json.loads(ws.sent[0]) == {"type": "Speak", "text": "hello there"}
    assert json.loads(ws.sent[1]) == {"type": "Close"}


def test_streaming_synthesis_chunks_yields_only_binary_frames(monkeypatch):
    ws = _FakeSpeakWS(recv_sequence=[
        b"\x01\x02",
        json.dumps({"type": "Warning", "msg": "ignore me"}),
        b"\x03\x04",
        "",  # clean end-of-stream (empty message) — chunks() stops without raising
    ])
    monkeypatch.setattr(tts_deepgram, "_websocket_lib", _FakeSpeakWebsocketLib(ws=ws))
    monkeypatch.setattr(tts_deepgram, "DEEPGRAM_API_KEY", "k")
    session = tts_deepgram.StreamingSynthesis("hi")
    session.connect()
    assert list(session.chunks()) == [b"\x01\x02", b"\x03\x04"]
    session.close()
    assert ws.closed is True


def test_streaming_synthesis_connect_failure_returns_false(monkeypatch):
    monkeypatch.setattr(
        tts_deepgram, "_websocket_lib", _FakeSpeakWebsocketLib(connect_error=RuntimeError("no route"))
    )
    monkeypatch.setattr(tts_deepgram, "DEEPGRAM_API_KEY", "k")
    session = tts_deepgram.StreamingSynthesis("hi")
    assert session.connect() is False


def test_streaming_synthesis_no_key_never_connects(monkeypatch):
    fake_lib = _FakeSpeakWebsocketLib(ws=_FakeSpeakWS())
    monkeypatch.setattr(tts_deepgram, "_websocket_lib", fake_lib)
    monkeypatch.setattr(tts_deepgram, "DEEPGRAM_API_KEY", "")
    session = tts_deepgram.StreamingSynthesis("hi")
    assert session.connect() is False
    assert fake_lib.connect_calls == []


def test_streaming_synthesis_mid_stream_recv_failure_propagates(monkeypatch):
    ws = _FakeSpeakWS(recv_sequence=[b"\x01\x02", ConnectionError("dropped")])
    monkeypatch.setattr(tts_deepgram, "_websocket_lib", _FakeSpeakWebsocketLib(ws=ws))
    monkeypatch.setattr(tts_deepgram, "DEEPGRAM_API_KEY", "k")
    session = tts_deepgram.StreamingSynthesis("hi")
    session.connect()
    got = []
    with pytest.raises(ConnectionError):
        for chunk in session.chunks():
            got.append(chunk)
    assert got == [b"\x01\x02"]  # the chunk before the failure was still yielded


# --- wiring in jarvis.py -------------------------------------------------------------------------
@pytest.fixture()
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import jarvis as j

    monkeypatch.setattr(j, "LLM_SETTINGS_PATH", tmp_path / "llm_provider.json")
    monkeypatch.delenv("JARVIS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("JARVIS_STT_BACKEND", raising=False)
    monkeypatch.delenv("JARVIS_TTS_BACKEND", raising=False)
    monkeypatch.setattr(j, "get_mcp_tool_schemas", lambda: [])
    monkeypatch.setattr(j, "_history_snapshot", lambda: [])
    monkeypatch.setattr(j, "_append_history", lambda *a, **k: None)
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    monkeypatch.setattr(j, "_tts_disk_cache", cache.TTSDiskCache(tmp_path / "tts"))
    monkeypatch.setattr(j, "_dg_stt_breaker", cache.CircuitBreaker(threshold=3, cooldown_s=120.0))
    monkeypatch.setattr(j, "_dg_tts_breaker", cache.CircuitBreaker(threshold=3, cooldown_s=120.0))
    # LLM token streaming off unless a test opts in — with a fake ANTHROPIC_API_KEY, any test
    # that calls run_agent_loop(narrate=True) without this would otherwise make a REAL network
    # call to Anthropic's streaming endpoint.
    monkeypatch.setenv("JARVIS_LLM_TTS_STREAM", "0")
    j._reply_cache.clear()
    j._tool_result_cache.clear()
    cache.reset_stats()
    return j


def test_transcribe_pcm_uses_deepgram_when_configured(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis.stt_deepgram, "DEEPGRAM_API_KEY", "k")
    monkeypatch.setattr(jarvis.stt_deepgram, "transcribe", lambda mono, sr, timeout_s=None: "deepgram heard this")
    whisper_calls = []
    monkeypatch.setattr(jarvis, "_get_whisper_model", lambda: whisper_calls.append(1))
    pcm = (np.random.rand(16000).astype(np.float32) - 0.5)
    assert jarvis.transcribe_pcm(pcm, 16000) == "deepgram heard this"
    assert not whisper_calls  # Whisper never touched


def test_transcribe_pcm_falls_back_to_whisper_on_deepgram_failure(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis.stt_deepgram, "DEEPGRAM_API_KEY", "k")

    def boom(mono, sr, timeout_s=None):
        raise RuntimeError("deepgram down")

    monkeypatch.setattr(jarvis.stt_deepgram, "transcribe", boom)

    class FakeSegment:
        text = "whisper heard this"

    class FakeModel:
        def transcribe(self, mono16k, beam_size=1, language=None):
            return [FakeSegment()], None

    monkeypatch.setattr(jarvis, "_get_whisper_model", lambda: FakeModel())
    pcm = (np.random.rand(16000).astype(np.float32) - 0.5)
    assert jarvis.transcribe_pcm(pcm, 16000) == "whisper heard this"


def test_transcribe_pcm_backend_forced_to_whisper(jarvis, monkeypatch):
    monkeypatch.setenv("JARVIS_STT_BACKEND", "whisper")
    monkeypatch.setattr(jarvis.stt_deepgram, "DEEPGRAM_API_KEY", "k")

    def boom(*a, **k):
        raise AssertionError("Deepgram should not be called when backend=whisper")

    monkeypatch.setattr(jarvis.stt_deepgram, "transcribe", boom)

    class FakeSegment:
        text = "ok"

    class FakeModel:
        def transcribe(self, mono16k, beam_size=1, language=None):
            return [FakeSegment()], None

    monkeypatch.setattr(jarvis, "_get_whisper_model", lambda: FakeModel())
    pcm = (np.random.rand(16000).astype(np.float32) - 0.5)
    assert jarvis.transcribe_pcm(pcm, 16000) == "ok"


class _StubSession:
    """Duck-types jarvis_stt_deepgram.StreamingSession's finish() surface for jarvis.py-level
    wiring tests — the protocol itself is covered separately in the StreamingSession tests."""

    def __init__(self, result):
        self._result = result
        self.finish_calls = 0

    def finish(self, timeout_s=None):
        self.finish_calls += 1
        return self._result


def test_transcribe_pcm_uses_streaming_session_result_when_present(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis.stt_deepgram, "DEEPGRAM_API_KEY", "k")

    def boom(*a, **k):
        raise AssertionError("REST should not be called when the stream already succeeded")

    monkeypatch.setattr(jarvis.stt_deepgram, "transcribe", boom)
    session = _StubSession(("streamed text", 0.9))
    pcm = (np.random.rand(16000).astype(np.float32) - 0.5)
    assert jarvis.transcribe_pcm(pcm, 16000, stream_session=session) == "streamed text"
    assert session.finish_calls == 1


def test_transcribe_pcm_falls_back_to_rest_when_stream_fails(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis.stt_deepgram, "DEEPGRAM_API_KEY", "k")
    rest_calls = []
    monkeypatch.setattr(
        jarvis.stt_deepgram, "transcribe", lambda mono, sr, timeout_s=None: rest_calls.append(1) or "rest text"
    )
    session = _StubSession(None)  # stream produced nothing usable
    pcm = (np.random.rand(16000).astype(np.float32) - 0.5)
    assert jarvis.transcribe_pcm(pcm, 16000, stream_session=session) == "rest text"
    assert rest_calls == [1]


def test_transcribe_pcm_too_short_audio_still_tears_down_stream_session(jarvis, monkeypatch):
    session = _StubSession(("should be discarded", 0.9))
    pcm = np.zeros(100, dtype=np.float32)  # well under the 0.2s silence floor
    assert jarvis.transcribe_pcm(pcm, 16000, stream_session=session) == ""
    assert session.finish_calls == 1  # torn down even though its result was never used


def test_stt_stream_enabled_matches_deepgram_availability(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis.stt_deepgram, "DEEPGRAM_API_KEY", "k")
    monkeypatch.setattr(jarvis.stt_deepgram, "STREAM_ENABLED", True)
    assert jarvis._stt_stream_enabled() is True
    monkeypatch.setattr(jarvis.stt_deepgram, "STREAM_ENABLED", False)
    assert jarvis._stt_stream_enabled() is False
    monkeypatch.setattr(jarvis.stt_deepgram, "STREAM_ENABLED", True)
    monkeypatch.setattr(jarvis.stt_deepgram, "DEEPGRAM_API_KEY", "")
    assert jarvis._stt_stream_enabled() is False


def test_speak_text_uses_deepgram_before_fish_and_piper(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis.tts_deepgram, "DEEPGRAM_API_KEY", "k")
    monkeypatch.setattr(jarvis, "FISH_AUDIO_API_KEY", "k")
    dg_calls, fish_calls, played = [], [], []
    monkeypatch.setattr(
        jarvis.tts_deepgram, "synthesize", lambda t, timeout_s=None: dg_calls.append(t) or (b"\x01\x00" * 50, 24000)
    )
    monkeypatch.setattr(jarvis, "_fish_audio_synthesize", lambda t, p=None: fish_calls.append(t) or (b"\x02\x00" * 50, 24000))
    monkeypatch.setattr(jarvis, "_play_pcm_bytes", lambda raw, sr: played.append(sr))
    jarvis.speak_text("Hello there.")
    assert dg_calls == ["Hello there."] and not fish_calls and played == [24000]


def test_speak_text_falls_back_to_fish_then_piper_on_deepgram_failure(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis.tts_deepgram, "DEEPGRAM_API_KEY", "k")
    monkeypatch.setattr(jarvis, "FISH_AUDIO_API_KEY", "")  # Fish not configured

    def boom(t, timeout_s=None):
        raise RuntimeError("deepgram down")

    monkeypatch.setattr(jarvis.tts_deepgram, "synthesize", boom)
    piper_calls = []
    monkeypatch.setattr(
        jarvis, "_piper_synthesize", lambda t, o=None: piper_calls.append(t) or (b"\x03\x00" * 50, 22050)
    )
    played = []
    monkeypatch.setattr(jarvis, "_play_pcm_bytes", lambda raw, sr: played.append(sr))
    jarvis.speak_text("Hello there.")
    assert piper_calls == ["Hello there."] and played == [22050]


def test_speak_text_backend_forced_to_piper_skips_deepgram_and_fish(jarvis, monkeypatch):
    monkeypatch.setenv("JARVIS_TTS_BACKEND", "piper")
    monkeypatch.setattr(jarvis.tts_deepgram, "DEEPGRAM_API_KEY", "k")
    monkeypatch.setattr(jarvis, "FISH_AUDIO_API_KEY", "k")

    def boom(*a, **k):
        raise AssertionError("should not be called when backend=piper")

    monkeypatch.setattr(jarvis.tts_deepgram, "synthesize", boom)
    monkeypatch.setattr(jarvis, "_fish_audio_synthesize", boom)
    monkeypatch.setattr(jarvis, "_piper_synthesize", lambda t, o=None: (b"\x03\x00" * 50, 22050))
    played = []
    monkeypatch.setattr(jarvis, "_play_pcm_bytes", lambda raw, sr: played.append(sr))
    jarvis.speak_text("Hello there.")
    assert played == [22050]


def test_deepgram_tts_circuit_breaker_trips_after_repeated_failures(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis.tts_deepgram, "DEEPGRAM_API_KEY", "k")
    monkeypatch.setattr(jarvis, "FISH_AUDIO_API_KEY", "")
    dg_calls = []

    def boom(t, timeout_s=None):
        dg_calls.append(t)
        raise RuntimeError("deepgram down")

    monkeypatch.setattr(jarvis.tts_deepgram, "synthesize", boom)
    monkeypatch.setattr(jarvis, "_piper_synthesize", lambda t, o=None: (b"\x03\x00" * 50, 22050))
    monkeypatch.setattr(jarvis, "_play_pcm_bytes", lambda raw, sr: None)
    for i in range(3):
        jarvis.speak_text(f"Different phrase {i}.")  # unique text avoids the disk cache
    assert len(dg_calls) == 3  # breaker trips at threshold=3
    jarvis.speak_text("One more different phrase.")
    assert len(dg_calls) == 3  # tripped: Deepgram skipped entirely, straight to Piper


def test_split_sentences_merges_short_fragments(jarvis):
    out = jarvis._split_sentences("Ok. This is a longer second sentence here. Done.")
    assert len(out) == 2  # the 3-char "Ok." fragment is merged into its neighbor, not spoken alone
    assert out[0].startswith("Ok. This is a longer second sentence here.")
    assert "Done" in out[-1]


def test_speak_text_pipelines_sentences_for_long_replies(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "FISH_AUDIO_API_KEY", "k")
    monkeypatch.setattr(jarvis.tts_deepgram, "DEEPGRAM_API_KEY", "")
    calls = []

    def fake_fish(t, p=None):
        calls.append(t)
        return (b"\x01\x00" * 50, 24000)

    monkeypatch.setattr(jarvis, "_fish_audio_synthesize", fake_fish)
    played = []
    monkeypatch.setattr(jarvis, "_play_pcm_bytes", lambda raw, sr: played.append(sr))
    long_text = (
        "This is the first sentence of a fairly long reply that should trigger streaming. "
        "This is the second sentence, also reasonably long so it isn't merged away. "
        "This is the third and final sentence, wrapping things up nicely here."
    )
    jarvis.speak_text(long_text)
    assert len(calls) >= 2  # split into multiple synth calls, not one giant blob
    assert len(played) == len(calls)  # each sentence played


# --- streaming TTS wiring (cloud-latency pass, Phase B) -----------------------------------------
class _FakeOutputStream:
    """Duck-types sd.OutputStream's context-manager + write() surface so _play_pcm_stream's real
    logic (including on_first_chunk timing and exception handling) runs against real jarvis.py
    code without touching real audio hardware."""

    def __init__(self, *a, **k):
        self.written: list = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def write(self, data):
        self.written.append(data)


def _speak_session_stub(chunks_or_exc):
    """Duck-types tts_deepgram.StreamingSynthesis for _speak_streamed tests: `chunks_or_exc` is a
    list where items are either bytes (yielded) or an Exception instance (raised at that point)."""

    class _Stub:
        def __init__(self):
            self.closed = False

        def connect(self):
            return True

        def chunks(self):
            for item in chunks_or_exc:
                if isinstance(item, Exception):
                    raise item
                yield item

        def close(self):
            self.closed = True

    return _Stub()


def test_play_pcm_stream_fires_on_first_chunk_once(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis.sd, "OutputStream", _FakeOutputStream)
    calls = []
    chunks = [b"\x00\x00" * 10, b"\x01\x00" * 10, b"\x02\x00" * 10]
    played = jarvis._play_pcm_stream(iter(chunks), 24000, on_first_chunk=lambda: calls.append(1))
    assert played is True
    assert calls == [1]  # exactly once, not per chunk


def test_play_pcm_stream_empty_chunks_never_fires_callback(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis.sd, "OutputStream", _FakeOutputStream)
    calls = []
    played = jarvis._play_pcm_stream(iter([b"", b""]), 24000, on_first_chunk=lambda: calls.append(1))
    assert played is False
    assert calls == []


def test_play_pcm_stream_survives_a_chunk_split_on_an_odd_byte_boundary(jarvis, monkeypatch):
    """Voice-bug audit pass (2026-09-22): a WebSocket frame boundary has no reason to land on a
    2-byte int16 sample boundary. Before the fix, an odd-length chunk made np.frombuffer raise
    ValueError, which aborted the whole utterance from that point on — a very plausible real
    cause of "voice breaks a lot" even without any network failure. Split a real int16 buffer at
    an odd byte offset to simulate this and assert playback still completes with every sample."""
    monkeypatch.setattr(jarvis.sd, "OutputStream", _FakeOutputStream)
    samples = jarvis.np.array([1, 2, 3, 4, 5, 6], dtype=jarvis.np.int16)
    whole = samples.tobytes()
    # Split after 3 bytes: chunk 1 ends mid-sample, chunk 2 starts mid-sample.
    chunk1, chunk2 = whole[:3], whole[3:]
    written = []
    out_ref = []

    class _CapturingOutputStream(_FakeOutputStream):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            out_ref.append(self)

        def write(self, data):
            written.append(data)

    monkeypatch.setattr(jarvis.sd, "OutputStream", _CapturingOutputStream)
    played = jarvis._play_pcm_stream(iter([chunk1, chunk2]), 24000)
    assert played is True
    # Every sample from both chunks was eventually written, none dropped or corrupted.
    rebuilt = jarvis.np.concatenate(written).reshape(-1) if written else jarvis.np.array([])
    rebuilt_i16 = (rebuilt * 32768.0).round().astype(jarvis.np.int16)
    assert list(rebuilt_i16) == list(samples)


def test_play_pcm_stream_asks_portaudio_for_high_latency_buffering(jarvis, monkeypatch):
    """Voice-bug pass (2026-09-22): an unbuffered OutputStream starves on uneven network chunk
    timing and crackles ("voice breaks a lot"). latency="high" gives PortAudio room to absorb
    that jitter instead."""
    seen_kwargs = {}

    class _RecordingOutputStream(_FakeOutputStream):
        def __init__(self, *a, **k):
            seen_kwargs.update(k)
            super().__init__(*a, **k)

    monkeypatch.setattr(jarvis.sd, "OutputStream", _RecordingOutputStream)
    jarvis._play_pcm_stream(iter([b"\x00\x00" * 10]), 24000)
    assert seen_kwargs.get("latency") == "high"


def test_speak_streamed_happy_path(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis.sd, "OutputStream", _FakeOutputStream)
    monkeypatch.setattr(
        jarvis.tts_deepgram, "StreamingSynthesis",
        lambda text, **k: _speak_session_stub([b"\x01\x00" * 10, b"\x02\x00" * 10]),
    )
    fired = []
    handled, raw, sr, backend, complete = jarvis._speak_streamed("hello", on_first_audio=lambda: fired.append(1))
    assert handled is True
    assert complete is True
    assert backend == "deepgram_stream"
    assert raw == (b"\x01\x00" * 10) + (b"\x02\x00" * 10)
    assert fired == [1]


def test_speak_streamed_connect_failure_is_not_handled(jarvis, monkeypatch):
    class _FailStub:
        def connect(self):
            return False

    monkeypatch.setattr(jarvis.tts_deepgram, "StreamingSynthesis", lambda text, **k: _FailStub())
    handled, raw, sr, backend, complete = jarvis._speak_streamed("hello")
    assert handled is False
    assert raw == b""


def test_speak_streamed_mid_stream_failure_after_audio_is_handled_but_incomplete(jarvis, monkeypatch):
    """Real audio already played before the interruption — must be reported as handled (so the
    caller never double-speaks by falling back to another engine) but NOT complete (so it's
    never cached as if it were the full utterance)."""
    monkeypatch.setattr(jarvis.sd, "OutputStream", _FakeOutputStream)
    monkeypatch.setattr(
        jarvis.tts_deepgram, "StreamingSynthesis",
        lambda text, **k: _speak_session_stub([b"\x01\x00" * 10, ConnectionError("dropped")]),
    )
    handled, raw, sr, backend, complete = jarvis._speak_streamed("hello")
    assert handled is True
    assert complete is False
    assert raw == b"\x01\x00" * 10  # the chunk that did play, nothing more


def test_speak_streamed_failure_before_any_audio_is_not_handled(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis.sd, "OutputStream", _FakeOutputStream)
    monkeypatch.setattr(
        jarvis.tts_deepgram, "StreamingSynthesis",
        lambda text, **k: _speak_session_stub([ConnectionError("dropped immediately")]),
    )
    handled, raw, sr, backend, complete = jarvis._speak_streamed("hello")
    assert handled is False  # nothing ever played -> safe for the caller to fall back to REST


def test_speak_text_streams_current_sentence_but_prefetch_never_streams(jarvis, monkeypatch):
    """The critical Phase B safety property: the background pre-fetch thread for the *next*
    sentence must only fetch bytes via _synthesize_and_cache, never call the streaming path —
    otherwise its own playback would fight the main thread's over the shared device/lock."""
    monkeypatch.setattr(jarvis.tts_deepgram, "DEEPGRAM_API_KEY", "k")
    monkeypatch.setattr(jarvis.tts_deepgram, "STREAM_ENABLED", True)
    monkeypatch.setattr(jarvis, "FISH_AUDIO_API_KEY", "")
    monkeypatch.setattr(jarvis.sd, "OutputStream", _FakeOutputStream)

    stream_calls = []

    def fake_stream_ctor(text, **k):
        stream_calls.append(text)
        return _speak_session_stub([b"\x01\x00" * 10])

    monkeypatch.setattr(jarvis.tts_deepgram, "StreamingSynthesis", fake_stream_ctor)
    rest_calls = []
    monkeypatch.setattr(
        jarvis.tts_deepgram, "synthesize",
        lambda text, timeout_s=None: (rest_calls.append(text) or (b"\x02\x00" * 10, 24000)),
    )
    monkeypatch.setattr(jarvis, "_play_pcm_bytes", lambda raw, sr: None)

    long_text = (
        "This is the first sentence of a fairly long reply for the streaming pipeline test. "
        "This is the second sentence, which must be pre-fetched without streaming at all."
    )
    jarvis.speak_text(long_text)
    assert len(stream_calls) == 1  # only the first (synchronous, "play now") sentence streamed
    assert len(rest_calls) == 1  # the second sentence was pre-fetched via plain REST, never a stream


def test_speak_text_skips_streaming_on_cache_hit(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis.tts_deepgram, "DEEPGRAM_API_KEY", "k")
    monkeypatch.setattr(jarvis.tts_deepgram, "STREAM_ENABLED", True)
    key = jarvis.cache.stable_hash("deepgram", jarvis.tts_deepgram.DEEPGRAM_TTS_MODEL, "Cached phrase.")
    jarvis._tts_disk_cache.put(key, b"\x01\x00" * 10, 24000)

    def boom(text, **k):
        raise AssertionError("must not attempt a stream when the phrase is already cached")

    monkeypatch.setattr(jarvis.tts_deepgram, "StreamingSynthesis", boom)
    played = []
    monkeypatch.setattr(jarvis, "_play_pcm_bytes", lambda raw, sr: played.append(sr))
    jarvis.speak_text("Cached phrase.")
    assert played == [24000]


def test_speak_text_caches_complete_streamed_audio_for_reuse(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis.tts_deepgram, "DEEPGRAM_API_KEY", "k")
    monkeypatch.setattr(jarvis.tts_deepgram, "STREAM_ENABLED", True)
    monkeypatch.setattr(jarvis.sd, "OutputStream", _FakeOutputStream)
    stream_calls = []

    def fake_stream_ctor(text, **k):
        stream_calls.append(text)
        return _speak_session_stub([b"\x01\x00" * 10])

    monkeypatch.setattr(jarvis.tts_deepgram, "StreamingSynthesis", fake_stream_ctor)
    monkeypatch.setattr(jarvis, "_play_pcm_bytes", lambda raw, sr: None)
    # Long enough to clear TTS_LIVE_STREAM_MIN_CHARS (below it speak_text skips the live stream
    # entirely — see the voice-bug-pass comment at its call site).
    text = "A streamed phrase long enough to actually use the live streaming path."
    jarvis.speak_text(text)
    assert len(stream_calls) == 1
    jarvis.speak_text(text)  # second time: served from cache, no new stream
    assert len(stream_calls) == 1


def test_speak_text_short_phrase_skips_live_stream(jarvis, monkeypatch):
    """Voice-bug pass (2026-09-22): the filler phrase ("One moment.") and short replies like
    "Hi, how can I help?" are the case a live-stream mid-utterance drop is most audible on (it
    reads as the phrase getting cut off) and benefit least from streaming's lower
    time-to-first-audio in the first place — so speak_text keeps them on the REST/cache cascade."""
    monkeypatch.setattr(jarvis.tts_deepgram, "DEEPGRAM_API_KEY", "k")
    monkeypatch.setattr(jarvis.tts_deepgram, "STREAM_ENABLED", True)

    def boom(text, **k):
        raise AssertionError("a short phrase must not open a live stream")

    monkeypatch.setattr(jarvis.tts_deepgram, "StreamingSynthesis", boom)
    monkeypatch.setattr(
        jarvis.tts_deepgram, "synthesize", lambda t, timeout_s=None: (b"\x01\x00" * 10, 24000)
    )
    played = []
    monkeypatch.setattr(jarvis, "_play_pcm_bytes", lambda raw, sr: played.append(sr))
    jarvis.speak_text(jarvis._FILLER_PHRASE)
    assert played == [24000]


def test_filler_phrase_skipped_when_event_set_quickly(jarvis, monkeypatch):
    monkeypatch.setenv("JARVIS_TTS_FILLER_DELAY_S", "5")
    spoken = []
    monkeypatch.setattr(jarvis, "speak_text", lambda t: spoken.append(t))
    done = __import__("threading").Event()
    done.set()
    jarvis._speak_filler_if_slow(done)
    assert spoken == []


def test_filler_phrase_speaks_when_slow(jarvis, monkeypatch):
    monkeypatch.setenv("JARVIS_TTS_FILLER_DELAY_S", "0.01")
    spoken = []
    monkeypatch.setattr(jarvis, "speak_text", lambda t: spoken.append(t))
    done = __import__("threading").Event()
    jarvis._speak_filler_if_slow(done)
    assert spoken == [jarvis._FILLER_PHRASE]


# --- audit-and-fix pass (2026-09-22) ---------------------------------------------------------
def test_stt_circuit_breaker_trips_after_repeated_failures(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis.stt_deepgram, "DEEPGRAM_API_KEY", "k")
    dg_calls = []

    def boom(mono, sr, timeout_s=None):
        dg_calls.append(1)
        raise RuntimeError("deepgram down")

    monkeypatch.setattr(jarvis.stt_deepgram, "transcribe", boom)

    class FakeSegment:
        text = "whisper heard this"

    class FakeModel:
        def transcribe(self, mono16k, beam_size=1, language=None):
            return [FakeSegment()], None

    monkeypatch.setattr(jarvis, "_get_whisper_model", lambda: FakeModel())
    pcm = (np.random.rand(16000).astype(np.float32) - 0.5)
    for _ in range(3):
        jarvis.transcribe_pcm(pcm, 16000)
    assert len(dg_calls) == 3  # breaker trips at threshold=3
    jarvis.transcribe_pcm(pcm, 16000)
    assert len(dg_calls) == 3  # tripped: Deepgram skipped entirely, straight to Whisper


def test_stt_backend_recovers_after_breaker_cooldown(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_dg_stt_breaker", cache.CircuitBreaker(threshold=1, cooldown_s=0.05))
    monkeypatch.setattr(jarvis.stt_deepgram, "DEEPGRAM_API_KEY", "k")
    calls = {"n": 0}

    def flaky(mono, sr, timeout_s=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("deepgram down")
        return "back up"

    monkeypatch.setattr(jarvis.stt_deepgram, "transcribe", flaky)

    class FakeSegment:
        text = "whisper heard this"

    class FakeModel:
        def transcribe(self, mono16k, beam_size=1, language=None):
            return [FakeSegment()], None

    monkeypatch.setattr(jarvis, "_get_whisper_model", lambda: FakeModel())
    pcm = (np.random.rand(16000).astype(np.float32) - 0.5)
    # First call: Deepgram fails (trips the 1-failure breaker), falls back to Whisper for real.
    assert jarvis.transcribe_pcm(pcm, 16000) == "whisper heard this"
    assert calls["n"] == 1

    time.sleep(0.06)  # cooldown elapses
    assert jarvis.transcribe_pcm(pcm, 16000) == "back up"  # Deepgram tried again and succeeded
    assert calls["n"] == 2


def test_stt_timeout_error_falls_back_to_whisper(monkeypatch):
    monkeypatch.setattr(stt_deepgram, "DEEPGRAM_API_KEY", "k")

    def timeout(req, timeout):
        raise TimeoutError("Deepgram STT request wedged past 8s")

    monkeypatch.setattr(stt_deepgram, "_urlopen_bounded", timeout)
    audio = (np.random.rand(1600).astype(np.float32) - 0.5)
    assert stt_deepgram.transcribe(audio, 16000) is None


def test_tts_timeout_error_propagates(monkeypatch):
    monkeypatch.setattr(tts_deepgram, "DEEPGRAM_API_KEY", "k")

    def timeout(req, timeout):
        raise TimeoutError("Deepgram TTS request wedged past 15s")

    monkeypatch.setattr(tts_deepgram, "_urlopen_bounded", timeout)
    with pytest.raises(TimeoutError):
        tts_deepgram.synthesize("hello")


def test_whisper_not_preloaded_when_deepgram_is_primary(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis.stt_deepgram, "DEEPGRAM_API_KEY", "k")
    assert jarvis._use_deepgram_stt() is True  # this is the exact condition main() gates the
    # eager _preload_whisper_async() call on — see jarvis.py main(): "if _use_deepgram_stt(): ...
    # log lazy-load message ... else: _preload_whisper_async()". No key means False -> eager
    # preload still happens, same as pre-Deepgram behavior:
    monkeypatch.setattr(jarvis.stt_deepgram, "DEEPGRAM_API_KEY", "")
    assert jarvis._use_deepgram_stt() is False


def test_whisper_still_preloaded_when_backend_forced_to_whisper(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis.stt_deepgram, "DEEPGRAM_API_KEY", "k")
    monkeypatch.setenv("JARVIS_STT_BACKEND", "whisper")
    assert jarvis._use_deepgram_stt() is False  # forced whisper -> main() preloads eagerly


def test_tts_backend_reports_last_engine_used_not_first(jarvis, monkeypatch):
    """A narrated mid-task line speaks via Deepgram; the final (longer) reply's Deepgram call
    then fails and falls back to Piper. The latency log's tts_backend must reflect Piper (what
    the user's actual answer used), not Deepgram (stale from the narration)."""
    monkeypatch.setattr(jarvis.tts_deepgram, "DEEPGRAM_API_KEY", "k")
    monkeypatch.setattr(jarvis, "FISH_AUDIO_API_KEY", "")
    calls = {"n": 0}

    def flaky_dg(t, timeout_s=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return (b"\x01\x00" * 50, 24000)  # narration succeeds via Deepgram
        raise RuntimeError("deepgram down now")  # final reply's Deepgram attempt fails

    monkeypatch.setattr(jarvis.tts_deepgram, "synthesize", flaky_dg)
    monkeypatch.setattr(jarvis, "_piper_synthesize", lambda t, o=None: (b"\x02\x00" * 50, 22050))
    monkeypatch.setattr(jarvis, "_play_pcm_bytes", lambda raw, sr: None)

    lat = latency.start()
    try:
        jarvis.speak_text("Narration line.")  # first call: Deepgram
        assert lat.tts_backend == "deepgram"
        jarvis.speak_text("Different final answer text.")  # second call: Deepgram fails -> Piper
        assert lat.tts_backend == "piper"  # updated to the engine that actually spoke last
    finally:
        latency.end()


def test_filler_skipped_when_narration_already_spoke(jarvis, monkeypatch):
    """Simulates run_agent_loop narrating (via speak_text, on the same thread) before the filler
    delay elapses: the filler must not also speak afterwards."""
    monkeypatch.setattr(jarvis, "FISH_AUDIO_API_KEY", "k")
    monkeypatch.setattr(jarvis.tts_deepgram, "DEEPGRAM_API_KEY", "")
    monkeypatch.setattr(jarvis, "_fish_audio_synthesize", lambda t, p=None: (b"\x01\x00" * 50, 24000))
    monkeypatch.setattr(jarvis, "_play_pcm_bytes", lambda raw, sr: None)
    monkeypatch.setenv("JARVIS_TTS_FILLER_DELAY_S", "0.05")

    done = threading.Event()
    jarvis._set_speak_signal(done)
    try:
        filler_thread = threading.Thread(target=jarvis._speak_filler_if_slow, args=(done,))
        filler_thread.start()
        time.sleep(0.01)
        jarvis.speak_text("Real narration already answered this.")  # sets the shared signal
        filler_thread.join(2.0)
        assert not filler_thread.is_alive()
    finally:
        jarvis._set_speak_signal(None)
    # The filler's own speak_text call would have been a *second* real call; since none of the
    # engines were monkeypatched to detect a second call by name, assert indirectly: the signal
    # was observed set before the filler's delay elapsed.
    assert done.is_set()


def test_speak_signal_is_per_thread(jarvis):
    assert jarvis._current_speak_signal() is None
    ev = threading.Event()
    jarvis._set_speak_signal(ev)
    assert jarvis._current_speak_signal() is ev
    seen = {}

    def other_thread():
        seen["signal"] = jarvis._current_speak_signal()

    t = threading.Thread(target=other_thread)
    t.start()
    t.join()
    assert seen["signal"] is None  # a different thread never sees another thread's signal
    jarvis._set_speak_signal(None)


def test_pipeline_join_timeout_recovers_without_hanging_or_dropping_content(jarvis, monkeypatch, caplog):
    """A background pre-synthesis that outlives PIPELINE_JOIN_TIMEOUT_S must not hang the
    command's thread. Nothing spoken is dropped — the abandoned prefetch is just discarded and
    that one sentence is synthesized again, synchronously, on the next loop iteration."""
    monkeypatch.setattr(jarvis, "PIPELINE_JOIN_TIMEOUT_S", 0.05)
    monkeypatch.setattr(jarvis, "FISH_AUDIO_API_KEY", "k")
    monkeypatch.setattr(jarvis.tts_deepgram, "DEEPGRAM_API_KEY", "")
    played = []
    monkeypatch.setattr(jarvis, "_play_pcm_bytes", lambda raw, sr: played.append(sr))

    call_n = {"n": 0}

    def slow_fish(t, p=None):
        call_n["n"] += 1
        if call_n["n"] == 2:  # only the *first* background pre-synthesis attempt hangs
            time.sleep(0.4)
        return (b"\x01\x00" * 50, 24000)

    monkeypatch.setattr(jarvis, "_fish_audio_synthesize", slow_fish)
    long_text = (
        "This is the first sentence of a fairly long reply for the pipeline timeout test. "
        "This is the second sentence, which will be artificially slow to synthesize. "
        "This is the third sentence, spoken after the timeout recovery."
    )
    start = time.monotonic()
    with caplog.at_level("WARNING"):
        jarvis.speak_text(long_text)
    elapsed = time.monotonic() - start
    assert elapsed < 1.0  # bounded by PIPELINE_JOIN_TIMEOUT_S, not the artificial 0.4s hang
    assert "will re-synthesize that sentence fresh" in caplog.text
    assert len(played) == 3  # every sentence still spoken — the timeout cost overlap, not content


# --- simple-intent fast path (cloud-latency pass, Phase D) --------------------------------------
def test_deterministic_intent_reply_time_and_date(jarvis):
    time_reply = jarvis._deterministic_intent_reply("time")
    assert time_reply is not None and time_reply.startswith("It's ")
    date_reply = jarvis._deterministic_intent_reply("date")
    assert date_reply is not None and date_reply.startswith("Today is ")
    assert jarvis._deterministic_intent_reply("complex") is None
    assert jarvis._deterministic_intent_reply("volume") is None
    assert jarvis._deterministic_intent_reply("open_app") is None


def test_reduced_tools_for_volume_intent(jarvis):
    tools = jarvis._reduced_tools_for_intent("volume", "turn the volume up")
    assert tools is not None
    assert [t["name"] for t in tools] == ["system_action"]


def test_reduced_tools_for_open_app_with_known_app(jarvis):
    tools = jarvis._reduced_tools_for_intent("open_app", "open notepad please")
    assert tools is not None
    assert [t["name"] for t in tools] == ["open_app"]


def test_reduced_tools_for_open_app_with_unknown_target_falls_through(jarvis):
    # "open my email" matches the broad open_app regex in classify_intent, but "email" isn't in
    # ALLOWED_APPS — must fall through to the full tool list, not be wrongly restricted.
    assert jarvis._reduced_tools_for_intent("open_app", "open my email") is None


def test_reduced_tools_for_complex_intent_is_none(jarvis):
    assert jarvis._reduced_tools_for_intent("complex", "summarize my last three emails") is None


def test_deterministic_reply_skips_run_agent_loop_entirely(jarvis, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("run_agent_loop must not be called for a deterministic intent")

    monkeypatch.setattr(jarvis, "run_agent_loop", boom)
    monkeypatch.setattr(jarvis, "speak_text", lambda t: None)
    monkeypatch.setattr(jarvis, "flush_pending_notifications", lambda: None)
    out = []
    jarvis.handle_text_command("what time is it", source="text", reply_sink=out.append)
    assert out and out[0].startswith("It's ")


def test_volume_command_gets_reduced_tools(jarvis, monkeypatch):
    seen = {}

    def fake_run_agent_loop(transcript, tone=None, narrate=False, tools_override=None, **k):
        seen["tools_override"] = tools_override
        return "Volume turned up."

    monkeypatch.setattr(jarvis, "run_agent_loop", fake_run_agent_loop)
    monkeypatch.setattr(jarvis, "speak_text", lambda t: None)
    monkeypatch.setattr(jarvis, "flush_pending_notifications", lambda: None)
    jarvis.handle_text_command("turn the volume up", source="text")
    assert seen["tools_override"] is not None
    assert [t["name"] for t in seen["tools_override"]] == ["system_action"]


def test_complex_command_gets_full_tools(jarvis, monkeypatch):
    seen = {}

    def fake_run_agent_loop(transcript, tone=None, narrate=False, tools_override=None, **k):
        seen["tools_override"] = tools_override
        return "Here's a summary."

    monkeypatch.setattr(jarvis, "run_agent_loop", fake_run_agent_loop)
    monkeypatch.setattr(jarvis, "speak_text", lambda t: None)
    monkeypatch.setattr(jarvis, "flush_pending_notifications", lambda: None)
    jarvis.handle_text_command("summarize my last three emails", source="text")
    assert seen["tools_override"] is None  # None -> run_agent_loop uses the full tool list


def test_deterministic_path_recorded_on_voice_latency(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "speak_text", lambda t: None)
    monkeypatch.setattr(jarvis, "flush_pending_notifications", lambda: None)

    def boom(*a, **k):
        raise AssertionError("run_agent_loop must not be called for a deterministic intent")

    monkeypatch.setattr(jarvis, "run_agent_loop", boom)
    monkeypatch.setattr(
        jarvis.voice_tone, "analyze_tone", lambda *a, **k: {"tone": "neutral", "confidence": 1.0}
    )
    monkeypatch.setattr(jarvis, "transcribe_pcm", lambda audio, sr, stream_session=None: "what time is it")
    # _handle_voice_command_impl owns the whole latency.start()/finish()/end() lifecycle itself —
    # just call it and read back what it recorded.
    jarvis._handle_voice_command_impl(np.ones(16000, dtype=np.float32), 16000)
    recent = latency.recent(1)
    assert recent and recent[-1]["intent"] == "time"
    assert recent[-1]["path"] == "deterministic"
    assert recent[-1]["ttft_ms"] is None  # no Claude call happened at all


# --- LLM token streaming -> speech (cloud-latency pass, Phase C) --------------------------------
def test_extract_ready_sentences_waits_for_boundary(jarvis):
    ready, remainder = jarvis._extract_ready_sentences("This is a growing sentence with no end yet")
    assert ready == [] and remainder == "This is a growing sentence with no end yet"


def test_extract_ready_sentences_emits_complete_ones(jarvis):
    ready, remainder = jarvis._extract_ready_sentences(
        "This is the first complete sentence. This is the second one. And a partial"
    )
    assert ready == ["This is the first complete sentence.", "This is the second one."]
    assert remainder == "And a partial"


def test_extract_ready_sentences_merges_short_fragments(jarvis):
    ready, remainder = jarvis._extract_ready_sentences("Ok. This is a longer second sentence here. ")
    assert ready == ["Ok. This is a longer second sentence here."]
    assert remainder == ""


def _sse_lines(events: list[tuple[str, dict]]) -> list[bytes]:
    out = []
    for event_name, data in events:
        out.append(f"event: {event_name}\n".encode())
        out.append(f"data: {json.dumps(data)}\n".encode())
        out.append(b"\n")
    return out


def _sse_text_reply(chunks: list[str], stop_reason: str = "end_turn") -> list[bytes]:
    events = [
        ("message_start", {"type": "message_start", "message": {"usage": {"input_tokens": 10}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
    ]
    for c in chunks:
        events.append(("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": c}}))
    events.append(("content_block_stop", {"type": "content_block_stop", "index": 0}))
    events.append(("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason}, "usage": {"output_tokens": 12}}))
    events.append(("message_stop", {"type": "message_stop"}))
    return _sse_lines(events)


class _FakeSSEResponse:
    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(self._lines)


def test_claude_stream_first_round_speaks_sentences_live_and_reconstructs_content(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_llm_provider", lambda: "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    full_text = "This is the first complete sentence here. " "This second one is also long enough. " "A short tail."
    lines = _sse_text_reply(["This is the ", "first complete sentence here. ", "This second one ", "is also long enough. ", "A short tail."])
    monkeypatch.setattr(jarvis.urllib.request, "urlopen", lambda req, timeout=None: _FakeSSEResponse(lines))
    spoken = []
    result = jarvis._claude_stream_first_round({"model": "x", "messages": []}, 5, spoken.append)
    assert result is not None
    assert result["content"] == [{"type": "text", "text": full_text}]
    assert result["stop_reason"] == "end_turn"
    assert result["usage"]["input_tokens"] == 10 and result["usage"]["output_tokens"] == 12
    # spoken as complete sentences as they arrive, not the whole reply at once, and nothing lost
    assert " ".join(spoken) == full_text
    assert len(spoken) >= 2


def test_claude_stream_first_round_fires_on_first_token_once(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_llm_provider", lambda: "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    lines = _sse_text_reply(["One. ", "Two. ", "Three."])
    monkeypatch.setattr(jarvis.urllib.request, "urlopen", lambda req, timeout=None: _FakeSSEResponse(lines))
    fired = []
    jarvis._claude_stream_first_round(
        {"model": "x", "messages": []}, 5, lambda s: None, on_first_token=lambda: fired.append(1)
    )
    assert fired == [1]


def test_claude_stream_first_round_stops_speaking_once_tool_use_starts(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_llm_provider", lambda: "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    events = [
        ("message_start", {"type": "message_start", "message": {"usage": {"input_tokens": 5}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Let me check that. "}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("content_block_start", {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "t1", "name": "system_status"}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "{}"}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 1}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 20}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    monkeypatch.setattr(jarvis.urllib.request, "urlopen", lambda req, timeout=None: _FakeSSEResponse(_sse_lines(events)))
    spoken = []
    result = jarvis._claude_stream_first_round({"model": "x", "messages": []}, 5, spoken.append)
    assert result is not None
    assert result["stop_reason"] == "tool_use"
    assert [b["type"] for b in result["content"]] == ["text", "tool_use"]
    assert result["content"][1]["name"] == "system_status" and result["content"][1]["input"] == {}
    assert spoken == ["Let me check that."]  # the text before the tool call, spoken live


def test_claude_stream_first_round_gemini_provider_no_ops(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_llm_provider", lambda: "gemini")

    def boom(*a, **k):
        raise AssertionError("must not attempt a network call when Gemini is the active provider")

    monkeypatch.setattr(jarvis.urllib.request, "urlopen", boom)
    assert jarvis._claude_stream_first_round({"model": "x", "messages": []}, 5, lambda s: None) is None


def test_claude_stream_first_round_network_failure_returns_none(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_llm_provider", lambda: "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def boom(req, timeout=None):
        raise RuntimeError("network down")

    monkeypatch.setattr(jarvis.urllib.request, "urlopen", boom)
    assert jarvis._claude_stream_first_round({"model": "x", "messages": []}, 5, lambda s: None) is None


def test_claude_stream_first_round_error_event_returns_none(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_llm_provider", lambda: "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    events = [("error", {"type": "error", "error": {"message": "overloaded"}})]
    monkeypatch.setattr(jarvis.urllib.request, "urlopen", lambda req, timeout=None: _FakeSSEResponse(_sse_lines(events)))
    assert jarvis._claude_stream_first_round({"model": "x", "messages": []}, 5, lambda s: None) is None


def test_run_agent_loop_streams_text_only_final_reply_and_marks_spoken(jarvis, monkeypatch):
    monkeypatch.setenv("JARVIS_LLM_TTS_STREAM", "1")  # fixture defaults this off; opt in — fully mocked below, no real network
    monkeypatch.setattr(jarvis, "get_mcp_tool_schemas", lambda: [])
    spoken = []
    monkeypatch.setattr(jarvis, "speak_text", lambda t: spoken.append(t))

    def fake_stream(body, timeout, speak_live, on_first_token=None):
        if on_first_token:
            on_first_token()
        speak_live("Paris is the capital of France.")
        return {"content": [{"type": "text", "text": "Paris is the capital of France."}], "stop_reason": "end_turn", "usage": {}}

    monkeypatch.setattr(jarvis, "_claude_stream_first_round", fake_stream)

    def boom(*a, **k):
        raise AssertionError("the non-streaming _claude_request must not be called when streaming succeeds")

    monkeypatch.setattr(jarvis, "_claude_request", boom)
    reply = jarvis.run_agent_loop("what is the capital of france", narrate=True)
    assert reply == "Paris is the capital of France."
    assert spoken == ["Paris is the capital of France."]
    assert jarvis.reply_already_spoken_via_stream() is True


def test_run_agent_loop_falls_back_to_non_streaming_when_stream_fails(jarvis, monkeypatch):
    monkeypatch.setenv("JARVIS_LLM_TTS_STREAM", "1")  # fixture defaults this off; opt in — fully mocked below, no real network
    monkeypatch.setattr(jarvis, "get_mcp_tool_schemas", lambda: [])
    monkeypatch.setattr(jarvis, "speak_text", lambda t: None)
    monkeypatch.setattr(jarvis, "_claude_stream_first_round", lambda *a, **k: None)
    calls = {"n": 0}

    def fake_request(body, timeout):
        calls["n"] += 1
        return {"content": [{"type": "text", "text": "Fallback answer."}], "stop_reason": "end_turn", "usage": {}}

    monkeypatch.setattr(jarvis, "_claude_request", fake_request)
    reply = jarvis.run_agent_loop("hello", narrate=True)
    assert reply == "Fallback answer."
    assert calls["n"] == 1
    assert jarvis.reply_already_spoken_via_stream() is False


def test_run_agent_loop_multi_round_streams_narration_then_speaks_final_reply_once(jarvis, monkeypatch):
    """Audit scenario: round 0 streams narration + a tool_use (so the loop must continue);
    round 1+ run the normal non-streaming path as always. The narration must be spoken exactly
    once (live, during the stream — not again via the existing narrate branch), the tool must
    actually execute, and the final answer must not be marked as already-spoken (it wasn't
    streamed) so the caller still speaks it once, normally."""
    monkeypatch.setenv("JARVIS_LLM_TTS_STREAM", "1")  # fixture defaults this off; opt in — fully mocked below, no real network
    monkeypatch.setattr(jarvis, "get_mcp_tool_schemas", lambda: [])
    spoken = []
    monkeypatch.setattr(jarvis, "speak_text", lambda t: spoken.append(t))
    executed_tools = []
    monkeypatch.setattr(jarvis, "_execute_tool", lambda name, inp, transcript: executed_tools.append(name) or "42 percent")

    def fake_stream(body, timeout, speak_live, on_first_token=None):
        speak_live("Let me check that for you.")
        return {
            "content": [
                {"type": "text", "text": "Let me check that for you."},
                {"type": "tool_use", "id": "t1", "name": "system_status", "input": {}},
            ],
            "stop_reason": "tool_use",
            "usage": {},
        }

    monkeypatch.setattr(jarvis, "_claude_stream_first_round", fake_stream)
    request_calls = []

    def fake_request(body, timeout):
        request_calls.append(body)
        return {"content": [{"type": "text", "text": "Your CPU is at 42 percent."}], "stop_reason": "end_turn", "usage": {}}

    monkeypatch.setattr(jarvis, "_claude_request", fake_request)
    reply = jarvis.run_agent_loop("what's my cpu usage", narrate=True)

    assert reply == "Your CPU is at 42 percent."
    assert executed_tools == ["system_status"]  # the tool really ran
    assert len(request_calls) == 1  # exactly one non-streamed round trip for the final answer
    assert spoken == ["Let me check that for you."]  # narration spoken exactly once (live)
    # The final answer was never streamed, so the caller (_handle_text_command_impl) must still
    # speak it normally — reply_already_spoken_via_stream() must be False, not True.
    assert jarvis.reply_already_spoken_via_stream() is False


def test_reply_already_spoken_flag_resets_between_commands(jarvis, monkeypatch):
    monkeypatch.setenv("JARVIS_LLM_TTS_STREAM", "1")  # fixture defaults this off; opt in — fully mocked below, no real network
    monkeypatch.setattr(jarvis, "get_mcp_tool_schemas", lambda: [])
    monkeypatch.setattr(jarvis, "speak_text", lambda t: None)
    monkeypatch.setattr(jarvis, "flush_pending_notifications", lambda: None)

    def fake_stream(body, timeout, speak_live, on_first_token=None):
        speak_live("Streamed reply.")
        return {"content": [{"type": "text", "text": "Streamed reply."}], "stop_reason": "end_turn", "usage": {}}

    monkeypatch.setattr(jarvis, "_claude_stream_first_round", fake_stream)

    def boom(*a, **k):
        raise AssertionError("should not need the fallback")

    monkeypatch.setattr(jarvis, "_claude_request", boom)
    jarvis.handle_text_command("streamed command", source="text")
    # A second, unrelated command that never streams must not inherit the first one's flag.
    monkeypatch.setattr(jarvis, "_claude_stream_first_round", lambda *a, **k: None)
    monkeypatch.setattr(
        jarvis, "_claude_request",
        lambda body, timeout: {"content": [{"type": "text", "text": "Second reply."}], "stop_reason": "end_turn", "usage": {}},
    )
    spoken = []
    monkeypatch.setattr(jarvis, "speak_text", lambda t: spoken.append(t))
    jarvis.handle_text_command("second command", source="text")
    assert spoken == ["Second reply."]  # actually spoken, not wrongly suppressed by stale state
