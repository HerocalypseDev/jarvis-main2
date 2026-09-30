"""Optional "Hey Jarvis" wake word: detector plumbing, capture seeding, transcript check, settings."""

import numpy as np

import jarvis_followup as fu
import jarvis_wakeword as ww

SR = 44100
BLOCK = int(SR * 0.04)


class FakeModel:
    def __init__(self, scores):
        self.scores = list(scores)
        self.calls = 0
        self.resets = 0
        self.frame_lens = []

    def predict(self, frame):
        self.calls += 1
        self.frame_lens.append((len(frame), frame.dtype))
        return {"hey_jarvis_v0.1": self.scores.pop(0) if self.scores else 0.0}

    def reset(self):
        self.resets += 1


def _blocks(level, seconds, sr=SR):
    rng = np.random.default_rng(1)
    n = int(sr * 0.04)
    return [rng.normal(0, level, n).astype(np.float32) for _ in range(int(seconds / 0.04))]


def test_frames_are_resampled_to_16k_int16_1280():
    m = FakeModel([0.0] * 100)
    w = ww.WakeListener(SR, model_factory=lambda: m)
    for b in _blocks(0.05, 1.0):
        w.feed(b)
    assert m.calls >= 10  # 1 s of audio = ~12 frames of 80 ms
    assert set(m.frame_lens) == {(1280, np.dtype("int16"))}


def test_score_over_threshold_fires_once_and_cools_down():
    m = FakeModel([0.0, 0.0, 0.9, 0.95, 0.9, 0.0])
    w = ww.WakeListener(SR, model_factory=lambda: m, thr=0.5, cooldown_s=2.5)
    hits, t = [], 0.0
    for b in _blocks(0.05, 0.8):
        if w.feed(b, now=t):
            hits.append(t)
        t += 0.04
    assert len(hits) == 1  # the same phrase scoring high on several frames is one wake
    assert m.resets >= 1
    # inside the cool-down a new high score does nothing; after it, it fires again
    m.scores = [0.9] * 20
    assert not any(w.feed(b, now=t + i * 0.04) for i, b in enumerate(_blocks(0.05, 0.4)))
    m.scores = [0.9] * 20
    assert any(w.feed(b, now=t + 5.0 + i * 0.04) for i, b in enumerate(_blocks(0.05, 0.4)))


def test_low_scores_never_fire():
    w = ww.WakeListener(SR, model_factory=lambda: FakeModel([0.3] * 50), thr=0.5)
    assert not any(w.feed(b) for b in _blocks(0.05, 2.0))


def test_missing_package_or_model_turns_the_feature_off_quietly():
    def boom():
        raise ImportError("No module named openwakeword")

    w = ww.WakeListener(SR, model_factory=boom)
    assert not any(w.feed(b) for b in _blocks(0.05, 0.5))
    assert w.available is False


def test_model_error_at_runtime_switches_it_off_instead_of_crashing():
    class Bad(FakeModel):
        def predict(self, frame):
            raise RuntimeError("onnx exploded")

    w = ww.WakeListener(SR, model_factory=lambda: Bad([]))
    assert not any(w.feed(b) for b in _blocks(0.05, 0.5))
    assert w.available is False


def test_async_load_does_not_block_and_starts_detecting_once_ready():
    import threading

    gate = threading.Event()

    def slow():
        gate.wait(5)
        return FakeModel([0.9] * 100)

    w = ww.WakeListener(SR, model_factory=slow, thr=0.5, async_load=True)
    assert w.feed(_blocks(0.05, 0.04)[0]) is False  # returns at once while the model loads
    gate.set()
    for _ in range(200):
        if w._model is not None:
            break
        threading.Event().wait(0.01)
    assert any(w.feed(b) for b in _blocks(0.05, 0.6))


def test_recent_audio_is_bounded_and_reset_clears_it():
    w = ww.WakeListener(SR, model_factory=lambda: FakeModel([]))
    for b in _blocks(0.05, 5.0):
        w.feed(b)
    got = w.recent_audio()
    assert sum(len(b) for b in got) / SR <= ww.RECENT_S + 0.05
    w.reset()
    assert w.recent_audio() == []


def test_enabled_and_threshold_read_the_environment(monkeypatch):
    monkeypatch.delenv("JARVIS_WAKE_WORD", raising=False)
    assert not ww.enabled()
    monkeypatch.setenv("JARVIS_WAKE_WORD", "1")
    assert ww.enabled()
    monkeypatch.setenv("JARVIS_WAKE_THRESHOLD", "abc")
    assert ww.threshold() == ww.DEFAULT_THRESHOLD
    monkeypatch.setenv("JARVIS_WAKE_THRESHOLD", "7")
    assert ww.threshold() == 0.99


def test_transcript_check_strips_the_name_and_rejects_other_speech():
    assert ww.strip_wake_phrase("Hey Jarvis, what's the weather?") == (True, "what's the weather")
    assert ww.strip_wake_phrase("Jarvis open notepad") == (True, "open notepad")
    assert ww.strip_wake_phrase("hey jarvis") == (True, "")
    assert ww.strip_wake_phrase("Okay Jarvis. Set a timer for ten minutes") == (True, "Set a timer for ten minutes")
    assert ww.strip_wake_phrase("Hey Travis, what time is it") == (True, "what time is it")  # common mishearing
    heard, _ = ww.strip_wake_phrase("please tell Jarvis I said hello")
    assert heard is False  # the name has to open the sentence
    assert ww.strip_wake_phrase("the weather is nice")[0] is False
    assert ww.strip_wake_phrase("")[0] is False


# --- seeding the follow-up capture --------------------------------------------------------------
def _run(ls, blocks, t0=0.0):
    out, t = [], t0
    for b in blocks:
        r = ls.feed(b, now=t)
        t += 0.04
        if r is not None:
            out.append(r)
    return out


def test_seeded_capture_includes_the_lead_up_and_the_rest_of_the_sentence():
    ls = fu.FollowUpListener(SR)
    lead = _blocks(0.1, 1.0)
    ls.seed(lead, now=0.0)
    assert ls.capturing and ls.armed and not ls.last_seeded
    got = _run(ls, _blocks(0.1, 1.5) + _blocks(0.002, 1.2))
    assert len(got) == 1 and ls.last_seeded
    assert len(got[0]) / SR >= 1.0 + 1.5  # wake phrase + the command
    assert not ls.capturing


def test_only_the_name_and_a_pause_still_ends_the_capture_after_the_grace():
    ls = fu.FollowUpListener(SR)
    ls.seed(_blocks(0.1, 1.0), now=0.0)
    quiet = _blocks(0.002, fu.WAKE_GRACE_S + 0.4)
    # a plain 0.8 s pause would already have ended a normal capture; the grace keeps waiting longer
    assert _run(ls, quiet[:int((fu.SILENCE_S + 0.2) / 0.04)]) == []
    got = _run(ls, quiet, t0=1.0)
    assert len(got) == 1 and ls.last_seeded


def test_a_normal_follow_up_is_not_marked_as_a_wake_capture():
    ls = fu.FollowUpListener(SR, window_s=5)
    ls.arm(now=0.0)
    got = _run(ls, _blocks(0.002, 1.0) + _blocks(0.1, 1.0) + _blocks(0.002, 1.2))
    assert len(got) == 1 and ls.last_seeded is False


def test_cancel_drops_a_seeded_capture():
    ls = fu.FollowUpListener(SR)
    ls.seed(_blocks(0.1, 0.5), now=0.0)
    ls.cancel()
    assert not ls.capturing and not ls.armed


def test_settings_page_lists_the_wake_word_switch_off_by_default():
    import jarvis_settings as js

    entries = {e["key"]: e for e in js.SETTINGS}
    assert entries["JARVIS_WAKE_WORD"]["default"] == "0"
    assert entries["JARVIS_WAKE_WORD"]["kind"] == "bool"
    assert "JARVIS_WAKE_THRESHOLD" in entries
