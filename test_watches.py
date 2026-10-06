"""Watches (2026-10-06): keep checking what the user names and speak up, once per stage, when something matches the
user's own rule for "important". Temp DB only, no network, no audio, no real model call."""

import json
import sqlite3
import threading
from datetime import date, datetime, timedelta

import pytest

import jarvis_watches as w


@pytest.mark.parametrize("said,schedule", [
    (None, {"daily_at": "08:00"}),
    ("0 8 * * *", {"daily_at": "08:00"}),
    ("30 19 * * 1-5", {"daily_at": "19:30", "days": "mon,tue,wed,thu,fri"}),
    ("0 */3 * * *", {"every_minutes": 180}),
    ("every day at 8", {"daily_at": "08:00"}),
    ("daily at 7:30 pm", {"daily_at": "19:30"}),
    ("every morning", {"daily_at": "08:00"}),
    ("weekdays at 6am", {"daily_at": "06:00", "days": "mon,tue,wed,thu,fri"}),
    ("every Monday at 9", {"daily_at": "09:00", "days": "mon"}),
    ("every 3 hours", {"every_minutes": 180}),
    ("hourly", {"every_minutes": 60}),
    ({"daily_at": "21:00"}, {"daily_at": "21:00"}),
])
def test_schedules_in_words_cron_or_dicts_are_understood(said, schedule):
    got, _note = w.parse_schedule(said)
    assert got == schedule


def test_an_unreadable_or_too_frequent_schedule_is_said_not_silently_dropped():
    assert w.parse_schedule("whenever you feel like it")[0] is None
    assert w.parse_schedule({"daily_at": "25:00"})[0] is None
    got, note = w.parse_schedule("every 1 minute")
    assert got == {"every_minutes": w.MIN_EVERY_MINUTES} and "shortest" in note


def test_a_daily_watch_is_due_once_after_its_time_and_retries_a_failed_check():
    watch = {"enabled": 1, "schedule": {"daily_at": "08:00"}, "last_run": None, "fails": 0}
    assert not w.is_due(watch, datetime(2026, 10, 6, 7, 59))
    assert w.is_due(watch, datetime(2026, 10, 6, 8, 1))
    assert not w.is_due(watch, datetime(2026, 10, 6, 23, 0))  # switched on too late: wait for tomorrow
    done = dict(watch, last_run="2026-10-06T08:01:00")
    assert not w.is_due(done, datetime(2026, 10, 6, 9, 0))
    assert w.is_due(done, datetime(2026, 10, 7, 8, 0))
    failed = dict(done, fails=1)
    assert w.is_due(failed, datetime(2026, 10, 6, 8, 40))
    assert not w.is_due(dict(failed, fails=w.RETRY_MAX + 1), datetime(2026, 10, 6, 8, 40))
    assert not w.is_due(dict(watch, enabled=0), datetime(2026, 10, 6, 8, 1))


def test_each_item_is_said_once_per_stage():
    today = date(2026, 10, 6)
    exam = {"item": "Maths final exam", "date": "2026-10-16", "say": "Hero, your maths final is in 10 days."}
    told: list[dict] = []

    def run(day, alerts):
        new = w.pick_new(alerts, told, day)
        for a in new:
            told.append({"item": a["item"], "event_date": a["date"], "stage": a["stage"], "said": a["say"],
                         "told_at": day.isoformat()})
        return [a["stage"] for a in new]

    assert run(today, [exam]) == ["2 weeks"]
    assert run(today + timedelta(days=1), [dict(exam, item="Maths final examination")]) == []  # reworded, same stage
    assert run(date(2026, 10, 13), [exam]) == ["3 days"]
    assert run(date(2026, 10, 14), [exam]) == []
    assert run(date(2026, 10, 15), [exam]) == ["tomorrow"]
    assert run(date(2026, 10, 16), [exam]) == ["today"]
    assert run(date(2026, 10, 30), [exam]) == []  # long past: stale
    other = {"item": "Maths final exam paper 2", "date": "2026-10-20", "say": "Paper two is on the 20th."}
    assert run(date(2026, 10, 15), [other]) == ["2 weeks"]  # a different date is a different item


def test_a_far_item_gets_one_first_notice_and_a_check_now_repeats():
    told = [{"item": "Results out", "event_date": "2026-12-01", "stage": "ahead", "said": "x", "told_at": "2026-10-01"}]
    item = {"item": "Results out", "date": "2026-12-01", "say": "Results come out on 1 December."}
    assert w.pick_new([item], told, date(2026, 10, 6)) == []
    assert [a["stage"] for a in w.pick_new([item], told, date(2026, 10, 6), repeat=True)] == ["ahead"]
    undated = {"item": "Portal open", "date": "", "say": "The portal is open."}
    assert [a["stage"] for a in w.pick_new([undated], [], date(2026, 10, 6))] == ["now"]


def test_the_checks_answer_is_read_from_json_even_with_extra_text():
    reply = 'Here you go:\n```json\n{"alerts": [{"item": "Exam", "date": "2026-10-16", "say": "Hero, exams soon."}]}\n```'
    assert w.parse_alerts(reply) == [{"item": "Exam", "date": "2026-10-16", "say": "Hero, exams soon."}]
    assert w.parse_alerts('{"alerts": []}') == []
    assert w.parse_alerts("I couldn't open the file.") is None
    assert w.parse_alerts('{"alerts": [{"item": "x", "date": "16/10/2026", "say": "y"}]}')[0]["date"] == ""


def test_the_prompt_carries_the_users_rule_and_what_was_already_said():
    p = w.check_prompt({"name": "exam_timetable", "what": "the university calendar PDF in Downloads",
                        "rule": "exams, results and resumption dates"},
                       [{"item": "Exam", "event_date": "2026-10-16", "stage": "2 weeks", "told_at": "2026-10-06"}],
                       datetime(2026, 10, 7, 8, 0), "Hero")
    assert "the university calendar PDF in Downloads" in p and "exams, results and resumption dates" in p
    assert "Exam (2026-10-16): told at stage '2 weeks'" in p and "Never invent" in p and "starting with their name" in p


@pytest.fixture
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "w.db"))
    import jarvis as j
    monkeypatch.setattr(j, "_current_command_source", lambda: "voice")
    return j


def _make(J, **extra):
    inp = {"action": "create", "name": "exam_timetable", "what": "my university calendar PDF and my Google Calendar",
           "rule": "exams coming up and results being released", "schedule": "0 8 * * *",
           "announce": "how many days are left, and ask how I feel"}
    inp.update(extra)
    return J._watches_tool(inp)


def test_make_list_edit_and_delete_a_watch(J):
    assert "Made watch #1 'exam_timetable'" in _make(J)
    assert "every day at 08:00" in _make(J, name="other", what="the bitcoin price on coindesk.com")
    assert "already exists" in _make(J)
    listed = J._watches_tool({"action": "list"})
    assert "exam_timetable (on, every day at 08:00)" in listed
    assert "Updated" in J._watches_tool({"action": "edit", "name": "exam", "schedule": "every 3 hours"})
    assert "every 3 hours" in J._watches_tool({"action": "show", "name": "exam_timetable"})
    assert "Tool failed" in J._watches_tool({"action": "create", "name": "x", "what": "y"})  # no rule
    assert "Turned off" in J._watches_tool({"action": "off", "name": "exam_timetable"})
    assert "Deleted" in J._watches_tool({"action": "delete", "name": "exam_timetable"})
    assert "exam_timetable" not in J._watches_tool({"action": "list"})


def test_an_automatic_run_cannot_make_or_change_a_watch(J, monkeypatch):
    _make(J)
    monkeypatch.setattr(J, "_current_command_source", lambda: None)
    assert "can only be made or changed by the user" in J._watches_tool(
        {"action": "create", "name": "x", "what": "y", "rule": "z"})
    assert "can only be made or changed by the user" in J._watches_tool({"action": "delete", "name": "exam_timetable"})
    assert "exam_timetable" in J._watches_tool({"action": "list"})  # reading is fine


def test_a_check_speaks_only_new_alerts_and_remembers_them(J, monkeypatch):
    _make(J)
    soon = (datetime.now().date() + timedelta(days=2)).isoformat()
    answer = json.dumps({"alerts": [{"item": "Maths final exam", "date": soon, "say": "Hero, your exam is in two days. "
                                                                                     "How are you feeling about it?"}]})
    prompts, spoken = [], []
    monkeypatch.setattr(J, "run_agent_loop", lambda prompt, **k: prompts.append(prompt) or answer)
    monkeypatch.setattr(J, "queue_or_deliver_notification", lambda text, **k: spoken.append((text, k)))
    monkeypatch.setattr(J.dashboard, "start_session", lambda *a: 1)
    monkeypatch.setattr(J.dashboard, "end_session", lambda *a, **k: None)
    monkeypatch.setattr(J.dashboard, "notify", lambda *a, **k: None)
    watch = J._watches().all()[0]
    J._run_watch(watch)
    assert spoken == [("Hero, your exam is in two days. How are you feeling about it?",
                       {"important": True, "bypass_busy_gate": True})]
    assert "exams coming up and results being released" in prompts[0]
    J._run_watch(J._watches().all()[0])          # the next scheduled check: same stage, nothing said
    assert len(spoken) == 1 and "Maths final exam" in prompts[1]
    J._run_watch(J._watches().all()[0], True)    # "check my exam watch" now: said again
    assert len(spoken) == 2
    w_now = J._watches().all()[0]
    assert w_now["last_status"] == "ok" and w_now["fails"] == 0 and w_now["last_run"]


def test_a_failed_check_is_retried_and_says_nothing(J, monkeypatch):
    _make(J)
    spoken = []
    monkeypatch.setattr(J, "run_agent_loop", lambda prompt, **k: J._llm_unavailable_reply())
    monkeypatch.setattr(J, "queue_or_deliver_notification", lambda text, **k: spoken.append(text))
    monkeypatch.setattr(J.dashboard, "start_session", lambda *a: 1)
    monkeypatch.setattr(J.dashboard, "end_session", lambda *a, **k: None)
    monkeypatch.setattr(J.dashboard, "notify", lambda *a, **k: None)
    J._run_watch(J._watches().all()[0])
    after = J._watches().all()[0]
    assert spoken == [] and after["last_status"] == "failed" and after["fails"] == 1


def test_save_skill_no_longer_drops_a_cron_schedule(J, monkeypatch, tmp_path):
    """Found live 2026-10-06: schedule '0 8 * * *' was dropped and the skill said 'runs only when asked'."""
    monkeypatch.setattr(J, "_skills_dir", lambda: tmp_path)
    out = J.save_skill("cal", "Check my calendar", "1. list events", "0 8 * * *")
    assert "scheduled" in out
    assert json.loads((tmp_path / "cal.json").read_text(encoding="utf-8"))["schedule"] == {"daily_at": "08:00"}
    assert "wasn't saved" in J.save_skill("cal2", "d", "1. x", "whenever")


def test_monitoring_requests_are_offered_the_watches_tool(J):
    for said in ("monitor my timetable and tell me when exams are near", "keep an eye on the university portal",
                 "let me know when my results are out", "turn off my exam watch"):
        assert "watches" in J._narrowing_core(said), said
    assert "watches" not in J._narrowing_core("what's the weather")


def test_the_toolbox_panel_reads_and_acts_on_watches(J, monkeypatch):
    _make(J)
    data = J.dashboard.providers["feature:watches"]("get", {})
    assert data["watches"][0]["schedule_text"] == "every day at 08:00" and data["watches"][0]["told"] == []
    monkeypatch.setattr(J, "_log_action_audit", lambda *a, **k: None)
    res = J.dashboard.providers["feature:watches"]("off", {"name": str(data["watches"][0]["id"])})
    assert "Turned off" in res["result"]


def test_store_survives_on_its_own(tmp_path):
    store = w.Store(lambda: sqlite3.connect(tmp_path / "s.db"), threading.Lock())
    wid = store.create("a", "b", "c", {"daily_at": "08:00"})
    store.mark_told(wid, {"item": "x", "date": "", "stage": "now", "say": "hi"})
    assert store.told(wid)[0]["said"] == "hi" and store.find("a")[0]["id"] == wid
    store.delete(wid)
    assert store.all() == [] and store.told(wid) == []


@pytest.mark.parametrize("inp,asked", [
    ({"what": "my stuff"}, "Where should I look"),
    ({"what": "my timetable"}, "Where should I look"),
    ({"rule": "anything important"}, "What counts as important"),
    ({"announce": ""}, "what should I say"),
    ({"schedule": ""}, "How often should I check"),
    ({"schedule": "whenever"}, "couldn't understand the timing"),
    ({"name": ""}, "What should this watch be called"),
])
def test_an_incomplete_watch_is_not_saved_and_the_user_is_asked(J, inp, asked):
    """Owner, 2026-10-06: if not enough is given, Jarvis asks again instead of saving a half-made watch."""
    out = _make(J, **inp)
    assert out.startswith("Tool failed: the watch is NOT saved yet") and asked in out and "set up" in out
    assert "No watches yet" in J._watches_tool({"action": "list"})


def test_a_watch_for_the_same_thing_is_not_made_twice(J):
    _make(J)
    out = _make(J, name="exam_dates")
    assert "already a watch for that" in out and "exam_timetable" in out
    J._watches_tool({"action": "off", "name": "exam_timetable"})
    assert "action=on" in _make(J, name="exam_dates")


def test_an_edit_cannot_make_a_watch_too_vague(J):
    _make(J)
    assert "not changed" in J._watches_tool({"action": "edit", "name": "exam_timetable", "rule": "anything"})
    assert "Updated" in J._watches_tool({"action": "edit", "name": "exam_timetable",
                                         "announce": "just the date, no questions"})
    assert "just the date" in J._watches_tool({"action": "show", "name": "exam_timetable"})


def test_the_check_prompt_carries_what_to_say():
    p = w.check_prompt({"name": "n", "what": "x", "rule": "y", "announce": "days left and ask how I feel"}, [],
                       datetime(2026, 10, 7, 8, 0))
    assert "What the user wants to hear when something matches: days left and ask how I feel" in p
