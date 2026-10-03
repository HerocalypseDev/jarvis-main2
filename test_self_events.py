"""Jarvis knows what already happened in its own space (debug report 2026-10-03): "in 5 mins run a git pull then restart
yourself" ran as job #6 at 10:05; after the restart autonomy queued the same work again for 10:12, Jarvis told the user
"my scheduled restart will happen in about a minute", and a true "I sent you a message" was forced into a false apology
plus a second send. Temp DB only; nothing real runs."""

import time
from datetime import datetime, timedelta

import pytest

import jarvis_deferred as deferred


@pytest.fixture
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "e.db"))
    monkeypatch.delenv("JARVIS_AUTONOMY_DISABLED", raising=False)
    monkeypatch.delenv("JARVIS_SAFE_MODE", raising=False)
    import jarvis as j
    j.autonomy._initialized_paths.clear()
    j.autonomy.init_autonomy_tables()
    j.autonomy.configure(j._autonomy_callbacks())
    j.autonomy.set_enabled(True)
    said = []
    monkeypatch.setattr(j, "queue_or_deliver_notification", lambda text, urgent=False, **k: said.append(text))
    monkeypatch.setattr(j, "_deferred_store", deferred.Store(j._memory_db_connect, j._memory_db_lock))
    monkeypatch.setattr(j, "_commands_in_flight", lambda: 0)
    monkeypatch.setattr(j, "_set_scheduled_task_running", lambda on: None)
    j._test_said = said
    yield j
    j._take_pending_action()


def _run_job(J, monkeypatch, instruction, reply):
    jid, _ = deferred.schedule(J._deferred_store, instruction, datetime.now() + timedelta(seconds=1), origin="user")
    J._deferred_store.q("UPDATE autonomy_deferred_jobs SET due_at=? WHERE id=?",
                        ((datetime.now() - timedelta(seconds=1)).isoformat(timespec="seconds"), jid), write=True)
    monkeypatch.setattr(J, "run_agent_loop", lambda *a, **k: reply)
    J._deferred_tick(datetime.now())
    t = time.time()
    while J._deferred_running and time.time() - t < 5:
        time.sleep(0.02)
    time.sleep(0.05)
    return jid


def test_a_finished_job_is_in_the_conversation_memory_and_journal(J, monkeypatch):
    J._append_history("in 5 mins time run a git pull then restart yourself",
                      "I have scheduled that task for you. In five minutes, I will pull and restart.")
    jid = _run_job(J, monkeypatch, "git pull && restart_jarvis", "Restarting now, back in about half a minute.")
    msgs = J._history_snapshot()
    assert msgs[-2]["role"] == "user" and f"scheduled job #{jid} ran at" in msgs[-2]["content"]
    assert "not words the user said" in msgs[-2]["content"]
    assert msgs[-1]["content"].startswith("(Done at") and "Restarting now" in msgs[-1]["content"]
    assert any(f"scheduled job #{jid} done" in r["summary"] for r in J.selfaware.recent(10, "tasks"))
    # the action log names it as a scheduled job, not as something the user said just now
    assert "for \"a scheduled job: git pull && restart_jarvis\"" in J._recent_actions_line()


def test_autonomy_does_not_queue_the_finished_restart_again(J, monkeypatch):
    """The exact classifier output from the report is dropped, so nothing is queued for 10:12."""
    a = J.autonomy
    J._append_history("in 5 mins time run a git pull then restart yourself",
                      "I have scheduled that task for you.")
    _run_job(J, monkeypatch, "git pull && restart_jarvis", "Restarting now.")
    routed = []
    monkeypatch.setattr(a, "_route", lambda *x, **k: routed.append(x) or "act")
    monkeypatch.setattr(a, "memory_context", lambda q="": "stored")
    monkeypatch.setattr(a, "_ask_model", lambda prompt, n=700: {
        "has_need": True, "type": "deadline", "confidence": 0.9, "suggested_action": "act",
        "description": "User requested a git pull and system restart at 10:12 (5 minutes after 10:07).",
        "action_payload": {"action_type": "background_task", "details": {"instruction": "git pull and restart"}}})
    a._classifier_step(datetime.now(), force=True)
    assert routed == []
    why = a._rows("SELECT policy_reason FROM autonomy_decisions ORDER BY id DESC LIMIT 1")[0]["policy_reason"]
    assert "already handled" in why and "job #" in why
    # the classifier is told about the job too
    assert "Jarvis's own scheduled jobs" in a._context_summary(datetime.now())
    assert "never queue it again" in a.AUTONOMY_TICK_CLASSIFIER_PROMPT


def test_a_real_new_need_still_goes_through(J, monkeypatch):
    a = J.autonomy
    J._append_history("in 5 mins time run a git pull then restart yourself", "Scheduled.")
    now = datetime.now()
    assert a._repeats_handled_work("Prepare notes for the physics exam tomorrow", "background_task", now) == ""
    # the request itself, with no job yet, is still a repeat of what the conversation handled
    assert "conversation" in a._repeats_handled_work("Run git pull and restart Jarvis", "background_task", now)
    # a spoken note about something the user mentioned is allowed
    assert a._repeats_handled_work("Run git pull and restart Jarvis", "notification", now) == ""


def test_action_log_leaves_out_autonomys_reasoning(J):
    J._log_action_audit("autonomy_decision", {"decision": "act"}, "(autonomy)",
                        "User requested a git pull and system restart at 10:12 (5 minutes after 10:07).")
    J._log_action_audit("restart_jarvis", {"force": True}, "(autonomy deferred) git pull && restart_jarvis",
                        "Restart scheduled: Jarvis will close in a few seconds and reopen with the latest code.")
    line = J._recent_actions_line()
    assert "10:12" not in line and "restart_jarvis (done)" in line


def test_the_start_after_a_restart_says_why_and_that_it_is_done(J, monkeypatch):
    sa = J.selfaware
    J._command_ctx.source = "dashboard"
    monkeypatch.setattr(J.restart_mod, "restart", lambda *a, **k: "Restart scheduled.")
    try:
        J._execute_tool("restart_jarvis", {}, "(autonomy deferred) git pull && restart_jarvis")
    finally:
        J._command_ctx.source = None
    sa.startup()
    line = sa.prompt_line()
    assert "(re)started at" in line and "git pull && restart_jarvis" in line and "DONE, not still to come" in line


def test_asking_what_was_sent_earlier_is_not_called_a_false_claim(J):
    J._log_action_audit("send_to_my_phone", {"text": "Testing connection"}, "Okay. Let's test things out.",
                        "Sent to your telegram: Testing connection")
    reply = "I sent you a message saying: Testing connection, this is a test message to your Telegram."
    assert J._unbacked_claims(reply, []) == ["send that"]  # nothing ran this command...
    asked = "Okay. What message did you send to me on Telegram?"
    assert J._unbacked_claims(reply, J._recent_succeeded_tools(asked)) == []  # ...but it did, one command ago
    # an instruction (not a question) still needs a real send this time
    assert J._recent_succeeded_tools("send it to me on Telegram") == []


def test_audit_page_finds_a_tool_by_name(J):
    J._log_action_audit("run_shell", {"command": "git log"}, "what changed", "commit: new send_to_my_phone tool")
    J._log_action_audit("send_to_my_phone", {"text": "hi"}, "test it", "Sent to your telegram: hi")
    rows = J._dashboard_page_audit("send_to_my_phone")["rows"]
    assert [r["tool_name"] for r in rows] == ["send_to_my_phone"]
    assert J._dashboard_page_audit("git log")["rows"]  # free text still works
