"""Quiet assistant (2026-10-03, owner: "it should not say out autonomous messages or reminders unless it is something very
important"). Only the owner's own reminders, urgent things and what they asked for are spoken on Jarvis's own; the rest
waits for "what did I miss?" and the Home card. Temp DB only; nothing is spoken (speak is faked)."""

import time

import pytest

import jarvis_latency as latency
import jarvis_missed as missed


@pytest.fixture
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "q.db"))
    monkeypatch.delenv("JARVIS_PROACTIVE_SPEECH", raising=False)
    import jarvis as j
    spoken = []
    monkeypatch.setattr(j, "_speak_shaped", lambda text: spoken.append(text))
    monkeypatch.setattr(j, "_notify_phone", lambda *a, **k: None)
    monkeypatch.setattr(j, "user_is_actively_working", lambda: False)
    monkeypatch.setattr(j.sleep_mode, "is_active", lambda: False)
    monkeypatch.setattr(j.sleep_mode, "should_suppress", lambda urgent: False)
    monkeypatch.setattr(j.focus_mode, "should_suppress", lambda urgent: False)
    monkeypatch.setattr(j, "safe_mode_on", lambda: False)
    monkeypatch.setattr(j.face, "group_safe_suppress", lambda urgent: False)
    monkeypatch.setattr(j.battery, "current", lambda: "ok")
    monkeypatch.setitem(j._cascade_flags, "hold_announcements", False)
    j._test_spoken = spoken
    yield j


def _unseen(J):
    return [i["text"] for i in missed.unseen(J._memory_db_connect, J._memory_db_lock)]


def test_only_reminders_urgent_and_asked_for_things_are_spoken(J):
    J.queue_or_deliver_notification("Reminder: call mum", bypass_busy_gate=True, is_reminder=True)
    J.queue_or_deliver_notification("Someone signed in to your Google account from a new device.", urgent=True)
    J.queue_or_deliver_notification("In 10 minutes: Standup with Sam.", important=True)
    J.queue_or_deliver_notification("Sam's iPhone joined the network.")
    J.queue_or_deliver_notification("CPU has been at 95% for 10 minutes.")
    assert J._test_spoken == ["Reminder: call mum", "Someone signed in to your Google account from a new device.",
                              "In 10 minutes: Standup with Sam."]
    assert _unseen(J) == ["Sam's iPhone joined the network.", "CPU has been at 95% for 10 minutes."]


def test_all_mode_brings_back_the_old_behaviour(J, monkeypatch):
    monkeypatch.setenv("JARVIS_PROACTIVE_SPEECH", "all")
    J.queue_or_deliver_notification("Sam's iPhone joined the network.")
    assert J._test_spoken == ["Sam's iPhone joined the network."] and _unseen(J) == []


@pytest.mark.parametrize("said", ["what did I miss", "What did I miss?", "Hey Jarvis, what did I miss",
                                  "did I miss anything", "anything new?", "what's new", "catch me up",
                                  "any updates for me", "what happened while I was away"])
def test_what_did_i_miss_is_a_built_in_command(said):
    assert latency.classify_intent(said) == "missed"


@pytest.mark.parametrize("said", ["what's new with you", "any updates on my order from Jumia", "what did I miss in class"])
def test_other_sentences_are_not(said):
    assert latency.classify_intent(said) != "missed"


def test_what_did_i_miss_reads_them_once(J, monkeypatch):
    monkeypatch.setattr(J, "run_agent_loop", lambda *a, **k: pytest.fail("no model call"))
    J.queue_or_deliver_notification("Sam's iPhone joined the network.")
    J.queue_or_deliver_notification("Sam's iPhone joined the network.")  # a repeat is stored once
    J.queue_or_deliver_notification("Your Vercel build finished.")
    out = J._deterministic_intent_reply("missed", "what did I miss")
    assert out.startswith("2 things came in") and "Sam's iPhone joined the network." in out and "Vercel" in out
    assert J._deterministic_intent_reply("missed", "what did I miss").startswith("Nothing new")
    page = J._feature_missed("get", {})
    assert page["unseen"] == 0 and len(page["items"]) == 2  # still on the Home card, marked read


def test_long_lists_are_cut_for_speech():
    now = time.time()
    items = [{"id": i, "ts": now - 60 * (10 - i), "text": f"Update number {i}"} for i in range(10)]
    out = missed.spoken_summary(items, now)
    assert out.startswith("10 things came in") and "Update number 9" in out and "Update number 3" not in out
    assert out.endswith("Ask again for the 4 older ones.")


def test_scheduled_skill_is_quiet_unless_urgent_or_announced(J, monkeypatch):
    seen = []
    monkeypatch.setattr(J, "run_agent_loop", lambda t, **k: seen.append(t) or replies.pop(0))
    monkeypatch.setattr(J, "_remember_skill_mail", lambda *a: None)
    replies = ["You have 3 unread emails, none important.",
               "URGENT: Your bank says a payment of 50,000 naira failed; it needs an answer today.",
               "Good morning. 29 degrees and cloudy."]
    J._run_scheduled_skill({"name": "gmail_watch", "instructions": "Check Gmail."})
    J._run_scheduled_skill({"name": "gmail_watch", "instructions": "Check Gmail."})
    J._run_scheduled_skill({"name": "morning_briefing", "instructions": "Brief me.", "announce": True})
    assert "URGENT:" in seen[0] and "URGENT:" not in seen[2]  # only quiet skills get told how to break the silence
    assert J._test_spoken == ["Your bank says a payment of 50,000 naira failed; it needs an answer today.",
                              "Good morning. 29 degrees and cloudy."]
    assert _unseen(J) == ["You have 3 unread emails, none important."]


def test_the_announce_flag_is_read_from_the_skill_file(J, monkeypatch, tmp_path):
    d = tmp_path / "skills"
    d.mkdir()
    (d / "a.json").write_text('{"name": "a", "instructions": "x", "announce": true}')
    (d / "b.json").write_text('{"name": "b", "instructions": "x", "announce": "yes"}')
    monkeypatch.setenv("JARVIS_SKILLS_DIR", str(d))
    monkeypatch.setattr(J.pro, "skill_paths", lambda: [])
    J._skills_cache = None
    try:
        got = {s["name"]: s.get("announce") for s in J._load_skills()}
    finally:
        J._skills_cache = None
    assert got == {"a": True, "b": None}


def test_user_scheduled_job_results_and_failures_are_still_said(J, monkeypatch):
    monkeypatch.setattr(J.autonomy, "speech_minimal", lambda: False)
    J._deferred_speech("As you asked earlier: 11 Mbps down.", asked=True)
    J._deferred_speech("The scheduled job \"run the test\" failed: no internet.", failure=True)
    J._deferred_speech("Starting: run the test")
    assert J._test_spoken == ["As you asked earlier: 11 Mbps down.",
                              "The scheduled job \"run the test\" failed: no internet."]
    assert _unseen(J) == ["Starting: run the test"]


def test_the_model_is_told_to_leave_old_things_alone(J):
    J.queue_or_deliver_notification("Sam's iPhone joined the network.")
    volatile = J.build_system_blocks("", "what's the weather")[1]["text"]
    assert "1 unread item in the user's 'what did I miss' list" in volatile
    import jarvis_selfaware as sa
    assert "don't mention it unless the newest message asks" in sa.prompt_line(["safe mode on"])


def test_a_bare_what_happened_still_goes_to_the_model():
    assert latency.classify_intent("what happened?") != "missed"  # usually about the last thing said


def test_an_important_message_is_never_batched_or_held_for_the_next_command(J, monkeypatch):
    """Audit 2026-10-04: a meeting heads-up (important) could land in the hourly digest of a kind the user often cuts
    off, or wait for the next command while the user typed during work hours."""
    monkeypatch.setattr(J.notify_priority, "should_batch", lambda *a: True)
    monkeypatch.setattr(J, "user_is_actively_working", lambda: True)
    monkeypatch.setattr(J, "_is_preferred_work_hours", lambda: True)
    J.queue_or_deliver_notification("In 10 minutes: Standup with Sam.", important=True)
    assert J._test_spoken == ["In 10 minutes: Standup with Sam."]
