"""Main memory (2026-10-03, owner: "Jarvis should be the main memory: if something happens it should double check all
sources for something related", and "learn from what I say"). Every request gets the reminders, jobs, tasks and older
conversations that match it; the calendar only for time/plans/people; facts from the owner's own words are stored at
once with no model call. Temp DB only; no calendar or model is reached."""

import json
from datetime import datetime, timedelta

import pytest

import jarvis_context as ctx
import jarvis_quickfacts as qf


@pytest.mark.parametrize("said, content", [
    ("my entrance exam score was 280", "The user's entrance exam score was 280."),
    ("I live in Paris", "The user lives in Paris."),
    ("call me Sam", "The user wants to be called Sam."),
    ("My favourite anime is One Piece", "The user's favourite anime is One Piece."),
    ("I scored 280 in my entrance exam", "The user scored 280 in their entrance exam."),
    ("I love jollof rice", "The user loves jollof rice."),
    ("I am 17 years old", "The user is 17 years old."),
    ("my brother's name is Peter", "The user's brother's name is Peter."),
    ("my birthday is on the 5th of May", "The user's birthday is on the 5th of May."),
])
def test_clear_statements_about_the_owner_are_learned(said, content):
    assert [f["content"] for f in qf.extract(said)] == [content]


@pytest.mark.parametrize("said", [
    "my phone is dead", "my head is hurting", "my laptop is at 20%", "my exam is tomorrow",
    "what is my entrance exam score?", "is my score good", "remember that my birthday is May 5",
    "if my score is 200 what can I study", "I like that", "I hate when you do that", "I am a bit tired",
    "reply to Sam that my birthday is Friday", "open spotify", "my email is me@example.com",
])
def test_questions_commands_and_passing_states_are_not(said):
    assert qf.extract(said) == []


def test_family_facts_are_relationships_without_an_address():
    f = qf.extract("Hey Jarvis, my sister is Ada and she is 15")
    assert f == [{"category": "relationship", "key": "auto:my_sister", "content": "The user's sister is Ada."}]


@pytest.fixture
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "m.db"))
    import jarvis as j
    j._people_cache.update(at=0.0, names=frozenset())
    j._calendar_cache.update(at=0.0, lines=None, busy=False)
    yield j


def _facts(J):
    conn = J._memory_db_connect()
    try:
        return [(r[0], r[1]) for r in conn.execute(
            "SELECT content, key FROM memory_facts WHERE superseded_at IS NULL ORDER BY id")]
    finally:
        conn.close()


def test_learned_at_once_and_updated_not_duplicated(J):
    J._learn_from_user_words("my entrance exam score was 280", "voice")
    J._learn_from_user_words("my entrance exam score was 280", "voice")  # said again: stored once
    J._learn_from_user_words("Actually my entrance exam score was 285", "text")  # a correction replaces it
    assert _facts(J) == [("The user's entrance exam score was 285.", "auto:my_entrance_exam_score")]
    J._learn_from_user_words("I live in Paris", "autonomy")  # not the owner talking
    J._learn_from_user_words("my favourite colour is blue" + J.SELECTION_TAG + " selected text", "voice")
    assert len(_facts(J)) == 1


def test_a_fact_the_model_just_saved_is_not_stored_twice(J):
    J.remember_fact("fact", "User's birthday: 5th of May")
    J._learn_from_user_words("my birthday is on the 5th of May", "voice")
    assert len(_facts(J)) == 1


def test_switch_off(J, monkeypatch):
    monkeypatch.setenv("JARVIS_LEARN_FROM_SPEECH", "0")
    J._learn_from_user_words("I live in Paris", "voice")
    assert _facts(J) == []


def _add_turns(J, pairs):
    for u, a in pairs:
        J._append_history(u, a)


def test_related_reminders_jobs_and_old_conversations_come_with_the_request(J):
    _add_turns(J, [("my entrance exam exam result comes out on friday", "Okay, I'll keep that in mind.")]
               + [(f"filler topic {i}", f"filler answer {i}") for i in range(10)])
    J.create_reminder("Check the entrance exam result portal", (datetime.now() + timedelta(days=2)).isoformat())
    J.create_reminder("Buy bread", (datetime.now() + timedelta(hours=2)).isoformat())
    line = J._related_context_line("did my entrance exam result come out")
    assert "Check the entrance exam result portal" in line and "Buy bread" not in line
    assert "entrance exam exam result comes out on friday" in line
    assert "filler" not in line
    assert J._related_context_line("open notepad") == ""


def test_calendar_only_for_time_plans_or_people(J, monkeypatch):
    now = datetime.now()
    raw = json.dumps({"events": [{"summary": "Church", "start": {"dateTime": (now + timedelta(days=1)).isoformat()},
                                  "end": {"dateTime": (now + timedelta(days=1, hours=2)).isoformat()}}]})
    calls = []
    monkeypatch.setitem(J._mcp_tool_index, "mcp_calendar_list-events", ("calendar", "list-events"))
    monkeypatch.setattr(J, "_calendar_events_raw", lambda a, b: calls.append(1) or raw)
    assert "Calendar" not in J._related_context_line("open notepad and type hello")
    assert not calls
    line = J._related_context_line("am I free on Sunday")
    assert "Calendar, next 7 days:" in line and "Church" in line
    J._related_context_line("what about saturday evening")
    assert len(calls) == 1  # cached for 5 minutes
    J.remember_fact("relationship", "The user's sister is Ada.")
    J._people_cache.update(at=0.0)
    J._calendar_cache.update(at=0.0, lines=None)
    assert "Church" in J._related_context_line("did Ada ask anything")  # a known person
    assert "mail/message tools" in J._related_context_line("did Ada send me an email")


def test_the_prompt_says_check_before_saying_i_dont_know(J):
    assert "main memory" in J.AGENT_SYSTEM_PROMPT and "never say you don't know before checking" in J.AGENT_SYSTEM_PROMPT


def test_calendar_lines_include_the_day():
    now = datetime(2026, 10, 3, 9, 0)
    raw = json.dumps([{"summary": "Standup", "start": {"dateTime": "2026-10-05T09:30:00"}},
                      {"summary": "Trip", "start": {"date": "2026-10-06"}},
                      {"summary": "Old", "start": {"dateTime": "2026-10-02T09:30:00"},
                       "end": {"dateTime": "2026-10-02T10:00:00"}}])
    assert ctx.calendar_lines(raw, now, now + timedelta(days=7)) == ["Mon 05 Oct 9:30 AM Standup", "Tue 06 Oct all day: Trip"]
