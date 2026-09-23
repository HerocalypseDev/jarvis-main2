"""Follow-up window VAD (jarvis_followup) and barge-in cutoff."""

import numpy as np

import jarvis_followup as fu

SR = 16000
BLOCK = SR // 25  # 40 ms


def _blocks(level, seconds):
    rng = np.random.default_rng(0)
    return [rng.normal(0, level, BLOCK).astype(np.float32) for _ in range(int(seconds / 0.04))]


def _run(listener, blocks, t0=0.0):
    out, t = [], t0
    for b in blocks:
        r = listener.feed(b, now=t)
        t += 0.04
        if r is not None:
            out.append(r)
    return out


def test_speech_inside_window_is_captured_with_preroll():
    ls = fu.FollowUpListener(SR, window_s=5)
    ls.arm(now=0.0)
    got = _run(ls, _blocks(0.002, 1.0) + _blocks(0.1, 1.0) + _blocks(0.002, 1.2))
    assert len(got) == 1
    assert 1.0 + fu.SILENCE_S <= len(got[0]) / SR <= 1.0 + fu.PREROLL_S + fu.SILENCE_S + 0.1


def test_nothing_captured_when_not_armed_or_window_expired():
    ls = fu.FollowUpListener(SR, window_s=5)
    assert _run(ls, _blocks(0.002, 1.0) + _blocks(0.1, 1.0) + _blocks(0.002, 1.2)) == []  # never armed
    ls.arm(now=0.0)
    assert _run(ls, _blocks(0.002, 1.0) + _blocks(0.1, 1.0), t0=6.0) == []  # window over


def test_short_click_is_dropped_and_background_noise_raises_threshold():
    ls = fu.FollowUpListener(SR, window_s=5)
    ls.arm(now=0.0)
    assert _run(ls, _blocks(0.002, 1.0) + _blocks(0.1, 0.12) + _blocks(0.002, 1.2)) == []
    noisy = fu.FollowUpListener(SR, window_s=5)
    noisy.arm(now=0.0)
    # a steady fan at 0.02 is learned as background, not taken as speech
    assert _run(noisy, _blocks(0.02, 3.0)) == []


def test_disabled_with_zero_window():
    ls = fu.FollowUpListener(SR, window_s=0)
    ls.arm(now=0.0)
    assert _run(ls, _blocks(0.002, 1.0) + _blocks(0.1, 1.0) + _blocks(0.002, 1.2)) == []


def test_cough_keeps_the_window_and_chain_limit_closes_it():
    ls = fu.FollowUpListener(SR, window_s=5)
    ls.arm(now=0.0)
    # a 0.12 s click is dropped, and the window stays open for real speech after it
    assert len(_run(ls, _blocks(0.002, 1.0) + _blocks(0.1, 0.12) + _blocks(0.002, 1.0)
                    + _blocks(0.1, 1.0) + _blocks(0.002, 1.2))) == 1
    for _ in range(fu.MAX_CHAIN - 1):
        ls.arm(now=0.0, chained=True)
        assert ls._deadline > 0
    ls.arm(now=0.0, chained=True)  # one hands-free turn too many: the key is needed again
    assert ls._deadline == 0.0
    ls.arm(now=0.0)  # a push-to-talk reply resets the chain
    assert ls._deadline == 5.0


def test_steady_noise_outside_the_window_raises_the_threshold():
    ls = fu.FollowUpListener(SR, window_s=5)
    _run(ls, _blocks(0.03, 4.0))  # a TV at 0.03 before the window opens is learned as background
    ls.arm(now=100.0)
    assert _run(ls, _blocks(0.03, 3.0), t0=100.0) == []


def test_barge_in_silences_the_interrupted_commands_later_speech(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "t.db"))
    import time
    import jarvis
    played = []
    monkeypatch.setattr(jarvis, "_sanitize_for_speech", lambda t: t)
    monkeypatch.setattr(jarvis, "_play_pcm_bytes", lambda raw, sr: played.append(raw))
    monkeypatch.setattr(jarvis, "_tts_disk_cache", None, raising=False)
    monkeypatch.setattr(jarvis.sd, "stop", lambda: None)
    jarvis._command_ctx.started = time.monotonic()
    try:
        jarvis._interrupt_speech()  # user pressed push-to-talk mid-reply
        jarvis.speak_text("The rest of the old answer.")
        assert played == []  # nothing more from the interrupted command
    finally:
        jarvis._command_ctx.started = None
    assert jarvis._speech_cancelled_since(time.monotonic()) is False  # later speech is unaffected


def test_barge_in_before_the_first_streamed_chunk_is_not_replayed_over_rest(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "t.db"))
    import time
    import jarvis
    played = []
    monkeypatch.setattr(jarvis, "_sanitize_for_speech", lambda t: t)
    monkeypatch.setattr(jarvis, "_tts_cache_peek", lambda s: None)
    monkeypatch.setattr(jarvis, "_use_deepgram_tts_stream", lambda: True)

    def stream(sentence, on_first_audio=None):
        jarvis._interrupt_speech()  # the user pressed the key before any audio arrived
        return False, b"", 0, "", False

    monkeypatch.setattr(jarvis, "_speak_streamed", stream)
    monkeypatch.setattr(jarvis, "_synthesize_and_cache", lambda s: (b"x", 16000, "rest"))
    monkeypatch.setattr(jarvis, "_play_pcm_bytes", lambda raw, sr: played.append(raw))
    monkeypatch.setattr(jarvis.sd, "stop", lambda: None)
    jarvis._command_ctx.started = time.monotonic()
    try:
        jarvis.speak_text("A reply that is long enough to use the live streaming path here.")
    finally:
        jarvis._command_ctx.started = None
    assert played == []
