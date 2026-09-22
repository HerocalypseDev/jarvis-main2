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
