"""Jarvis asks the user when a tool needs their answer, and resumes that call (2026-10-16 debug report: the watch tool
asked two questions, the model ran a speed test instead and said "I'll keep tracking that"; a scheduled Gmail check read
the chat and acted on it; "scheduled work" never reached schedule_jarvis_task).
Run: python -m pytest test_asks.py -v"""
import json

import pytest

import jarvis_asks as asks


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
    monkeypatch.setattr(j.dashboard, "notify", lambda *a, **k: None)
    for k in ("autonomous", "untrusted_origin", "outside_text_seen", "scheduled_skill"):
        monkeypatch.setattr(j._command_ctx, k, None if k == "scheduled_skill" else False, raising=False)
    monkeypatch.setattr(j._command_ctx, "source", "text", raising=False)
    j._reply_cache.clear()
    j._tool_result_cache.clear()
    return j


WATCH_FAIL = ("Tool failed: the watch is NOT saved yet, some details are missing or unclear. Ask the user these "
              "questions in one short message, then call watches create again with everything (keep what they "
              "already said). Don't say the watch is set up.\n1. Where should I look for 'exam timetable': a file, "
              "your Google Calendar, your email, or a website?\n2. How often should I check?")


def _tool_round(name, inp, tid="t1"):
    return {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}


def _text(text):
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": text}]}


def _drive(J, monkeypatch, rounds):
    it, seen = iter(rounds), []
    monkeypatch.setattr(J, "_claude_request", lambda body, timeout: seen.append(body) or next(it))
    return seen


def _open(J):
    return asks.open_asks(J._memory_db_connect, J._memory_db_lock)


# --- detection --------------------------------------------------------------------------------------------------------
def test_needs_user_reads_questions_and_choices_but_not_ordinary_errors():
    assert asks.needs_user(WATCH_FAIL) == ("1. Where should I look for 'exam timetable': a file, your Google Calendar, "
                                           "your email, or a website?\n2. How often should I check?")
    assert "a, b" in asks.needs_user("More than one skill matches: a, b. Say which one.")
    assert "Say which one" in asks.needs_user("More than one tab matches: #1 x; #2 y. Say which one (or use its id).")
    assert asks.needs_user("Do it now; don't ask the user anything.") is None
    for plain in ("Tool failed: couldn't open notepad: not installed.", "Download 23 megabits per second.",
                  "Saved skill 'x'.", "", None):
        assert asks.needs_user(plain) is None


def test_reply_asks():
    q = asks.needs_user(WATCH_FAIL)
    assert asks.reply_asks("Where should I look for it, and how often?", q)
    assert not asks.reply_asks("I'll keep tracking that for you in the background.", q)


# --- the agent loop makes sure the user is asked ------------------------------------------------------------------------
def test_skipped_questions_get_a_nudge_then_are_added_in_code_and_saved(J, monkeypatch):
    inp = {"action": "create", "name": "exams", "what": "exam timetable", "rule": "exam dates and results",
           "announce": "how many days are left"}
    seen = _drive(J, monkeypatch, [_tool_round("watches", inp),
                                   _text("I'll keep tracking that for you."),
                                   _text("Okay, all done.")])
    reply = J.run_agent_loop("watch my exam timetable")
    assert "needs the user's answer" in json.dumps(seen[2]["messages"][-1]["content"])
    assert "Before I can finish that I need a bit more from you" in reply and "How often should I check" in reply
    rows = _open(J)
    assert len(rows) == 1 and rows[0]["tool"] == "watches" and rows[0]["request"] == "watch my exam timetable"
    assert json.loads(rows[0]["tool_input"])["what"] == "exam timetable"


def test_a_reply_that_asks_is_left_alone(J, monkeypatch):
    inp = {"action": "create", "name": "exams", "what": "exam timetable", "rule": "exam dates and results",
           "announce": "how many days are left"}
    seen = _drive(J, monkeypatch, [_tool_round("watches", inp),
                                   _text("Where should I look for your timetable, and how often should I check?")])
    reply = J.run_agent_loop("watch my exam timetable")
    assert len(seen) == 2 and reply == "Where should I look for your timetable, and how often should I check?"
    assert len(_open(J)) == 1


def test_next_command_carries_the_question_and_success_closes_it(J, monkeypatch):
    ask_id, _ = asks.save(J._memory_db_connect, J._memory_db_lock, tool="watches",
                          tool_input={"action": "create", "name": "exams"}, questions="1. How often should I check?",
                          request="watch my exam timetable", origin="text")
    line = J.build_system_blocks("", "every day at 8")[1]["text"]
    assert f"#{ask_id}" in line and "How often should I check" in line and '"name": "exams"' in line
    full = {"action": "create", "name": "exams", "what": "the exam timetable PDF in Downloads",
            "rule": "exam dates and results", "announce": "how many days are left", "schedule": "every day at 8"}
    _drive(J, monkeypatch, [_tool_round("watches", full), _text("Done, I made the exams watch.")])
    J.run_agent_loop("every day at 8")
    assert _open(J) == []
    assert asks.get(J._memory_db_connect, J._memory_db_lock, ask_id)["status"] == "answered"


def test_background_run_says_it_once_and_keeps_it_for_the_card(J, monkeypatch):
    told = []
    monkeypatch.setattr(J, "queue_or_deliver_notification", lambda text, **kw: told.append((text, kw)))
    monkeypatch.setattr(J._command_ctx, "source", None, raising=False)
    monkeypatch.setattr(J._command_ctx, "scheduled_skill", "exam_helper", raising=False)
    inp = {"action": "create", "name": "exams", "what": "exam timetable", "rule": "exam dates and results",
           "announce": "how many days are left"}
    for _ in range(2):  # the skill runs again later and hits the same question
        _drive(J, monkeypatch, [_tool_round("watches", inp), _text("Nothing to report.")])
        assert "Before I can finish" not in J.run_agent_loop("(scheduled run) check exams", record_history=False)
    assert len(told) == 1 and told[0][1].get("important")
    assert told[0][0].startswith("I need your answer for your exam helper skill: Where should I look")
    assert len(_open(J)) == 1


def test_questions_from_someone_elses_text_are_never_kept(J, monkeypatch):
    monkeypatch.setattr(J._command_ctx, "untrusted_origin", True, raising=False)
    assert J._handle_pending_asks("x", "Done.", [{"tool": "watches", "input": {}, "questions": "1. Which?"}])
    assert _open(J) == []


def test_home_card_answer_resumes_the_call_and_dismiss_closes(J, monkeypatch):
    ask_id, _ = asks.save(J._memory_db_connect, J._memory_db_lock, tool="watches", tool_input={"name": "exams"},
                          questions="1. How often should I check?", request="watch my exams", origin="text")
    feature = J.dashboard.providers["feature:asks"]
    assert feature("get", {})["items"][0]["id"] == ask_id
    ran = []
    monkeypatch.setattr(J, "handle_text_command", lambda text, **kw: ran.append((text, kw)))
    out = feature("answer", {"id": ask_id, "text": "every day at 8"})
    assert out["result"].startswith("Sent")
    import time
    for _ in range(50):
        if ran:
            break
        time.sleep(0.02)
    text, kw = ran[0]
    assert text.startswith(f"Answer to your question #{ask_id}") and '"name": "exams"' in text
    assert "every day at 8" in text and kw["source"] == "dashboard"
    # that command's prompt puts this question first even if others were shown more
    monkeypatch.setattr(J._command_ctx, "source", "dashboard", raising=False)
    assert f"#{ask_id}" in J._asks_line(text)
    assert feature("dismiss", {"id": ask_id})["result"] == "Dismissed."
    assert _open(J) == [] and feature("answer", {"id": ask_id, "text": "x"})["error"]


# --- the rest of the report ----------------------------------------------------------------------------------------------
def test_a_watch_on_a_live_reading_is_sent_to_scheduled_work_without_questions(J):
    out = J._execute_tool("watches", {"action": "create", "name": "low_speed", "what": "internet speed test",
                                      "rule": "download speed is below 5 mbps", "schedule": "every 5 minutes",
                                      "announce": "your speed dropped"}, "set a scheduled work")
    assert "schedule_jarvis_task" in out and asks.needs_user(out) is None


def test_unattended_runs_never_see_the_conversation(J, monkeypatch):
    monkeypatch.setattr(J, "_history_snapshot", lambda: [{"role": "user", "content": "make my speed monitor"},
                                                         {"role": "assistant", "content": "ok"}])
    seen = _drive(J, monkeypatch, [_text("No new mail."), _text("Sure.")])
    J.run_agent_loop("(scheduled run) check gmail", record_history=False)
    assert len(seen[0]["messages"]) == 1 and "make my speed monitor" not in json.dumps(seen[0]["messages"])
    J.run_agent_loop("what about it", record_history=True)
    assert "make my speed monitor" in json.dumps(seen[1]["messages"])


def test_scheduled_work_wording_offers_the_scheduler(J):
    for said in ("set a sceduled work for you to chek my internet speed every 5mins",
                 "if it's still below 10 it should check again", "in 10 mins run the speed test"):
        assert {"schedule_jarvis_task", "scheduled_jobs"} <= J._narrowing_core(said), said
    assert "scheduled_jobs" not in J._narrowing_core("what's the weather")


def test_agent_result_says_exactly_what_it_does(J):
    out = J._execute_tool("background_agents", {"action": "create", "name": "speed", "trigger_type": "interval",
                                                "trigger_config": {"every_min": 5},
                                                "steps": [{"tool": "speed_test", "input": {"action": "run"}}]}, "x")
    assert "Each run does only this: speed_test" in out and "no conditions" in out


def test_open_roblox(J, monkeypatch):
    opened = []
    monkeypatch.setattr(J, "_open_uri", lambda u: opened.append(u) or True)
    monkeypatch.setattr(J.sys, "platform", "linux")
    out = J._execute_tool("open_app", {"app": "roblox"}, "open roblox")
    assert "roblox.com" in out and opened == ["https://www.roblox.com/home"]
    assert "roblox" in J.ALLOWED_APPS
