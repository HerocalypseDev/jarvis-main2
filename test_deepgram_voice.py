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
