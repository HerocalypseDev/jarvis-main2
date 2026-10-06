"""Personalities (2026-10-06): a Settings/voice switch for how Jarvis talks (Classic, Playful, Serious, Gen Z, Tired, Hype
coach, Naija) plus Auto (time of day, Tired after a busy day). Temp DB only, no network, no audio."""

import random
from datetime import datetime

import pytest

import jarvis_personality as p


@pytest.mark.parametrize("said,choice", [
    ("switch to playful mode", "playful"), ("be serious", "serious"), ("talk like gen z", "genz"),
    ("Jarvis, switch your personality to naija", "naija"), ("talk in pidgin", "naija"), ("hype mode", "hype"),
    ("be more sarcastic", "tired"), ("go back to normal", "classic"), ("switch to auto mode", "auto"),
    ("what's your personality", "status"), ("list your personalities", "status"),
    ("be quiet", None), ("a serious problem with my code", None), ("play something fun", None),
])
def test_switching_is_whole_utterances_only(said, choice):
    assert p.parse_switch(said) == choice


def test_auto_follows_the_time_of_day_and_tires_after_a_busy_day():
    day = datetime(2026, 10, 6)
    assert p.pick("auto", day.replace(hour=7))[0] == "hype"        # energetic in the morning
    assert p.pick("auto", day.replace(hour=13))[0] == "playful"
    assert p.pick("auto", day.replace(hour=19))[0] == "classic"
    assert p.pick("auto", day.replace(hour=23))[0] == "tired"      # tired at night
    assert p.pick("auto", day.replace(hour=2))[0] == "tired"       # before the first slot = last night's
    name, why = p.pick("auto", day.replace(hour=7), commands_today=75)
    assert name == "tired" and "75 commands" in why
    assert p.pick("auto", day.replace(hour=7), commands_today=75, tired_after=0)[0] == "hype"
    assert p.pick("playful", day.replace(hour=23), commands_today=500)[0] == "playful"  # a fixed choice stays put
    own = "6am serious, 9 pm naija"
    assert p.pick("auto", day.replace(hour=12), schedule=own)[0] == "serious"
    assert p.pick("auto", day.replace(hour=22), schedule=own)[0] == "naija"
    assert p.parse_schedule("nonsense") == p.parse_schedule(p.DEFAULT_SCHEDULE)


def test_code_built_lines_keep_their_exact_words():
    """A reminder in any personality still contains the whole reminder, unchanged."""
    line = "Reminder: Post the parcel at 5 PM"
    for name in p.choices():
        out = p.flavor(line, name, random.Random(1))
        assert line in out
    assert p.flavor(line, "classic") == line and p.flavor(line, "serious") == line
    assert p.flavor(line, "tired", random.Random(1)) != line


def test_start_lines_take_the_personalitys_own_lead_word():
    assert p.flavor_start("Sure, I'll check your mail.", "genz") == "Bet, I'll check your mail."
    assert p.flavor_start("Sure, I'll check your mail.", "serious") == "I'll check your mail."
    assert p.flavor_start("Sure, I'll check your mail.", "hype") == "Let's go! I'll check your mail."
    assert p.flavor_start("Sure, I'll check your mail.", "classic") == "Sure, I'll check your mail."
    assert p.flavor_start("Checking the bitcoin price.", "tired") == "Fine, checking the bitcoin price."


def test_the_prompt_line_keeps_tasks_safety_and_other_peoples_text_plain():
    assert p.prompt_line("classic") == ""
    for name in ("playful", "serious", "genz", "tired", "hype", "naija"):
        line = p.prompt_line(name)
        assert "never makes you refuse" in line and "dangerous action that needs a yes) plainly first" in line
        assert "emails, messages, documents and code you write for other people stay in a normal" in line
    assert p.prompt_line("auto") == ""  # auto is resolved by the caller first; unresolved never guesses


@pytest.fixture
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "p.db"))
    import jarvis as j
    monkeypatch.setattr(j.settings, "set_setting", lambda k, v: monkeypatch.setenv(k, v) or {"ok": True})
    j._personality_busy.update(at=0.0, count=0)
    return j


def test_voice_switch_saves_the_setting_and_answers_in_the_new_voice(J, monkeypatch):
    monkeypatch.setenv("JARVIS_PERSONALITY", "classic")
    assert J._deterministic_intent_reply("personality", "switch to gen z mode") == p.switched_reply("genz")
    assert J.os.environ["JARVIS_PERSONALITY"] == "genz" and J._personality_name() == "genz"
    assert "Gen Z mode" in J._deterministic_intent_reply("personality", "what's your personality")
    out = J._deterministic_intent_reply("personality", "switch to auto mode")
    assert J.os.environ["JARVIS_PERSONALITY"] == "auto" and "Auto mode" in out


def test_the_prompt_and_reply_cache_follow_the_personality(J, monkeypatch):
    monkeypatch.setenv("JARVIS_PERSONALITY", "tired")
    blocks = J.build_system_blocks("", "what's the weather")
    assert "Personality (the user's standing choice): TIRED" in str(blocks)
    monkeypatch.setenv("JARVIS_PERSONALITY", "classic")
    assert "Personality (the user's standing choice)" not in str(J.build_system_blocks("", "what's the weather"))


def test_auto_counts_todays_commands(J, monkeypatch):
    monkeypatch.setenv("JARVIS_PERSONALITY", "auto")
    monkeypatch.setenv("JARVIS_PERSONALITY_TIRED_AFTER", "3")
    for i in range(3):
        J.dashboard.start_session("voice", f"command {i}")
    J.dashboard.start_session("scheduled", "gmail_watch: checking")  # Jarvis's own runs don't tire it
    name, why = J._personality_now()
    assert name == "tired" and "3 commands" in why


def test_settings_offer_every_personality():
    import jarvis_settings as s
    spec = next(x for x in s.SETTINGS if x["key"] == "JARVIS_PERSONALITY")
    assert spec["choices"] == p.choices() and spec["default"] == "classic"


def test_a_quick_answer_is_said_in_the_personality_with_the_same_facts(J, monkeypatch):
    spoken = []
    monkeypatch.setenv("JARVIS_PERSONALITY", "tired")
    monkeypatch.setenv("JARVIS_ACK_PHRASES", "0")
    monkeypatch.setattr(J, "speak_text", lambda t, **k: spoken.append(t))
    monkeypatch.setattr(J, "flush_pending_notifications", lambda: None)
    monkeypatch.setattr(J, "_log_action_audit", lambda *a, **k: None)
    monkeypatch.setattr(J, "_deterministic_intent_reply", lambda intent, t="": "It's 3:05 PM."
                        if intent == "time" else None)
    J.handle_text_command("what time is it", source="text")
    assert spoken and "It's 3:05 PM." in spoken[-1] and spoken[-1] != "It's 3:05 PM."


def test_silent_and_replayed_answers_never_reach_the_ai_in_any_personality(J, monkeypatch):
    """Found while building: a misplaced flavour step sent 'stop talking' to the AI."""
    spoken = []
    monkeypatch.setenv("JARVIS_PERSONALITY", "genz")
    monkeypatch.setattr(J.sd, "stop", lambda: None)
    monkeypatch.setattr(J, "speak_text", lambda t, **k: spoken.append(t))
    monkeypatch.setattr(J, "flush_pending_notifications", lambda: None)
    monkeypatch.setattr(J, "_log_action_audit", lambda *a, **k: None)
    monkeypatch.setattr(J, "run_agent_loop", lambda *a, **k: pytest.fail("no AI call expected"))
    J.handle_text_command("stop talking", source="voice")
    assert spoken == []
