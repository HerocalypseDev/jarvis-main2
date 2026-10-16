"""False "still monitoring" / "I have successfully created it" claims (owner report 2026-10-16).
A self-rescheduling speed check couldn't schedule its next run, and half an hour later Jarvis still said "I'm still
monitoring it for you"; "I have successfully created the Word document" came after two failed saves.
Run: python -m pytest test_false_claims.py -v"""
import pytest


@pytest.fixture()
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("JARVIS_SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("JARVIS_LLM_TTS_STREAM", "0")
    monkeypatch.setenv("JARVIS_ACK_PHRASES", "0")
    import jarvis as j
    monkeypatch.setattr(j, "LLM_SETTINGS_PATH", tmp_path / "llm_provider.json")
    monkeypatch.delenv("JARVIS_LLM_PROVIDER", raising=False)
    monkeypatch.setattr(j, "get_mcp_tool_schemas", lambda: [])
    monkeypatch.setattr(j, "_history_snapshot", lambda: [])
    monkeypatch.setattr(j, "_append_history", lambda *a, **k: None)
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    monkeypatch.setattr(j, "_recent_succeeded_tools", lambda *a, **k: [])
    for k in ("autonomous", "untrusted_origin", "outside_text_seen"):
        monkeypatch.setattr(j._command_ctx, k, False, raising=False)
    monkeypatch.setattr(j._command_ctx, "source", "text", raising=False)
    j._reply_cache.clear()
    j._tool_result_cache.clear()
    return j


ONGOING = "set anything up to keep checking that: nothing is scheduled for it"


def _job(J, instruction):
    J._command_ctx.source = None  # a job Jarvis makes for itself
    try:
        assert "Scheduled job #" in J._schedule_jarvis_task_tool({"instruction": instruction, "due_in_minutes": 10})
    finally:
        J._command_ctx.source = "text"


@pytest.mark.parametrize("reply", [
    "I'm still monitoring your network speed for you.",
    "I am currently keeping an eye on it.",
    "I'll check the speed again in 10 minutes.",
    "I'll let you know as soon as it goes above 10 megabits.",
    "Don't worry, I'll keep monitoring it.",
])
def test_ongoing_claim_with_nothing_scheduled_is_unbacked(J, reply):
    assert J._unbacked_claims(reply, [], "what's my network speed") == [ONGOING]


def test_ongoing_claim_is_backed_by_a_related_pending_job_only(J):
    _job(J, "speed_test -unit megabits; if above 10 tell me, else check again in 10 minutes")
    assert J._unbacked_claims("I'm still monitoring your network speed.", [], "what's my network speed") == []
    # a pending job about something else doesn't back it
    assert J._unbacked_claims("I'm still monitoring the price of bitcoin.", [], "is bitcoin up") == [ONGOING]


def test_a_job_that_already_ran_no_longer_backs_it(J):
    _job(J, "run a speed test and check again in 10 minutes")
    job = J.deferred.list_jobs(J._deferred_store)[0]
    J.deferred.finish(J._deferred_store, job["id"], True, "couldn't schedule the next check", J.deferred.MAX_ATTEMPTS)
    assert J._unbacked_claims("I'm still monitoring your network speed.", [], "network speed?") == [ONGOING]


def test_scheduling_this_turn_backs_it_but_a_failed_one_does_not(J):
    claim = "I'll check your speed again in 10 minutes."
    assert J._unbacked_claims(claim, ["schedule_jarvis_task"], "speed") == []
    assert J._unbacked_claims(claim, ["watches"], "speed") == []
    assert J._unbacked_claims(claim, ["speed_test"], "speed") == [ONGOING]


def test_offers_and_questions_are_not_claims(J):
    assert J._unbacked_claims("Want me to keep monitoring it every 10 minutes?", [], "speed") == []
    assert J._unbacked_claims("I can keep an eye on it if you'd like.", [], "speed") == []
    assert J._unbacked_claims("Download 2.9 megabits per second.", [], "speed") == []


def test_adverbs_no_longer_hide_a_done_claim(J):
    """Debug report 2026-10-16: two failed write_file calls, then this reply, uncorrected."""
    reply = ("I have successfully created the complete Word document containing all fifty essential items for "
             "boarding school.")
    assert J._unbacked_claims(reply, []) == ["save that file"]
    assert J._unbacked_claims(reply, ["write_file"]) == []
    assert J._unbacked_claims("I've already set a reminder for that.", []) == ["set that reminder"]
    assert J._unbacked_claims("I went ahead and sent the email.", []) == ["send that"]
    assert J._unbacked_claims("The document has been saved.", []) == ["save that file"]


def test_agent_loop_corrects_a_false_still_monitoring(J, monkeypatch):
    replies = iter([{"stop_reason": "end_turn", "content": [{"type": "text", "text":
                     "I'm still monitoring your network speed for you."}]}] * 2)
    seen = []
    monkeypatch.setattr(J, "_claude_request", lambda body, timeout: seen.append(body["messages"]) or next(replies))
    reply = J.run_agent_loop("what is my network speed now")
    assert len(seen) == 2 and "nothing is scheduled for it" in str(seen[1][-1]["content"])
    assert "Correction: I didn't actually set anything up to keep checking that" in reply


def test_self_made_job_speaks_only_when_flagged(J, monkeypatch):
    """Owner's choice 2026-10-16: a job Jarvis scheduled for itself stays quiet unless its run flags the result."""
    told, inbox = [], []
    monkeypatch.setattr(J, "queue_or_deliver_notification", lambda text, **kw: told.append((text, kw)))
    monkeypatch.setattr(J, "_deferred_speech", lambda text, **kw: inbox.append(text))
    for name in ("_remember_deferred_job",):
        monkeypatch.setattr(J, name, lambda *a, **k: None)
    monkeypatch.setattr(J.deferred, "finish", lambda *a, **k: "done")
    monkeypatch.setattr(J.dashboard, "end_session", lambda *a, **k: None)
    monkeypatch.setattr(J.dashboard, "notify", lambda *a, **k: None)
    monkeypatch.setattr(J, "_dashboard_get_pending", lambda: None)
    job = {"id": 3, "attempts": 1, "instruction": "speed check", "origin": "jarvis"}
    J._finish_deferred_job(job, True, "Still 4 Mbps, checking again in 10 minutes.", False, "t", 1)
    assert told == [] and inbox  # quiet path (inbox / minimal speech)
    J._finish_deferred_job(job, True, "URGENT: Your speed is 14 Mbps, opening Roblox.", False, "t", 1)
    assert told and told[-1][0] == "Your speed is 14 Mbps, opening Roblox." and told[-1][1].get("important")
