"""Speed + focus pass (2026-10-03, owner: "Jarvis is slow, and brings up the last thing I talked about"). Measured in the
debug reports: ~15,700 tokens per model call (up to 16,000 characters of skill text, 8 earlier exchanges) and ~2.5 s of
speech-to-text for every "Hey Jarvis"/follow-up command (push-to-talk streams in ~0.4 s). Temp DB only."""

import json

import numpy as np
import pytest

import jarvis_context as ctx
import jarvis_followup


SKILLS = [
    {"name": "quiz_me", "description": "Quizzes the user on a subject they are studying.", "instructions": "Ask 5 questions."},
    {"name": "morning_briefing", "description": "Morning briefing with weather, calendar and mail.",
     "instructions": "Say the weather first."},
] + [{"name": f"pack_skill_{i}", "description": "Something from the Pro pack " * 3, "instructions": "x" * 900}
     for i in range(50)]


def test_skills_index_is_short_and_only_matching_steps_are_sent():
    index = ctx.skills_index(SKILLS)
    assert len(index) <= 2700 and "quiz_me" in index and "Ask 5 questions" not in index
    assert [s["name"] for s in ctx.relevant_skills(SKILLS, "quiz me on biology")] == ["quiz_me"]
    assert ctx.relevant_skills(SKILLS, "what's the time") == []


def _pairs(*topics):
    out = []
    for t in topics:
        out += [{"role": "user", "content": f"tell me about {t}"}, {"role": "assistant", "content": f"Here is {t}."}]
    return out


def test_old_unrelated_exchanges_are_left_out():
    hist = _pairs("telegram messages", "football scores", "restart job", "weather lagos", "spotify playlist")
    kept = ctx.pick_history(hist, "what's on my calendar")
    assert [m["content"] for m in kept if m["role"] == "user"] == ["tell me about weather lagos",
                                                                 "tell me about spotify playlist"]  # last two only
    kept = ctx.pick_history(hist, "who won the football yesterday")
    assert "tell me about football scores" in [m["content"] for m in kept]  # related older exchange stays
    assert ctx.pick_history(hist, "do that again") == hist  # refers back: everything
    assert all(kept[i]["role"] == "user" for i in range(0, len(kept), 2))  # still user/assistant pairs


@pytest.fixture
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "a.db"))
    d = tmp_path / "skills"
    d.mkdir()
    for s in SKILLS[:2]:
        (d / f"{s['name']}.json").write_text(json.dumps(s))
    monkeypatch.setenv("JARVIS_SKILLS_DIR", str(d))
    import jarvis as j
    monkeypatch.setattr(j.pro, "skill_paths", lambda: [])
    j._skills_cache = None
    yield j
    j._skills_cache = None


def test_the_prompt_carries_the_index_and_only_the_matching_skill(J):
    stable, volatile = (b["text"] for b in J.build_system_blocks("", "quiz me on biology"))
    assert "- quiz_me:" in stable and "Ask 5 questions" not in stable  # the cached part stays the same every call
    assert "Ask 5 questions" in volatile and "Say the weather first" not in volatile
    assert "NEWEST message" in J.AGENT_SYSTEM_PROMPT
    assert "Ask 5 questions" in J._skills_tool({"action": "show", "name": "quiz"})


def test_history_sent_with_a_request_skips_unrelated_old_exchanges(J):
    for t in ("telegram messages", "football scores", "restart job", "weather lagos"):
        J._append_history(f"tell me about {t}", f"Here is {t}.")
    sent = [m["content"] for m in J._history_snapshot("what's on my calendar") if m["role"] == "user"]
    assert sent == ["tell me about restart job", "tell me about weather lagos"]
    assert len(J._history_snapshot()) == 8  # without a request (other callers) nothing changes


class FakeStream:
    def __init__(self, rate):
        self.fed, self.started, self.finished = [], False, False

    def start(self):
        self.started = True

    def feed(self, block):
        self.fed.append(block)

    def finish(self):
        self.finished = True


def test_hands_free_commands_stream_their_audio_while_you_speak(J, monkeypatch):
    lis = jarvis_followup.FollowUpListener(16000)
    monkeypatch.setattr(J, "followup", lis)
    monkeypatch.setattr(J.stt_deepgram, "StreamingSession", FakeStream)
    monkeypatch.setattr(J, "_stt_stream_enabled", lambda: True)
    lis.seed([np.ones(1600, dtype=np.float32) * 0.2])  # "Hey Jarvis" just heard
    s = J._feed_hands_free_stream(None)
    assert isinstance(s, FakeStream) and len(s.fed) == 1  # the wake audio went in at once
    lis.feed(np.ones(1600, dtype=np.float32) * 0.2)
    assert J._feed_hands_free_stream(s) is s and len(s.fed) == 2  # and each new block as it arrives
    lis.cancel()
    import time
    assert J._feed_hands_free_stream(s) is None
    time.sleep(0.05)
    assert s.finished  # a capture that ended without a command closes its stream
