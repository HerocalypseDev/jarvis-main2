"""Tests for jarvis_guest_reminders (the stranger -> "disable reminders?" Telegram flow) and its
integration with jarvis.py's notification gate, reminder delivery and the phone reply path.
Nothing here touches Telegram, the real DB or the real session_state.json.
Run: python -m pytest test_guest_reminders.py -v"""

import pytest

import jarvis_guest_reminders as gr


class Phone:
    """Stands in for Telegram: records what Jarvis texts, and can be made to fail."""

    def __init__(self, ok=True):
        self.sent, self.ok, self.released = [], ok, 0

    def send(self, text):
        self.sent.append(text)
        return self.ok

    def release(self):
        self.released += 1


@pytest.fixture()
def phone():
    p = Phone()
    gr.reset()
    gr.configure(p.send, p.release)
    yield p
    gr.reset()
    gr.configure(None, None)


T0 = 1_000_000.0


# --- asking ----------------------------------------------------------------------------------
def test_a_stranger_triggers_one_question_and_holds_reminders(phone):
    gr.on_stranger_arrived(T0)
    assert phone.sent == [gr.ASK_TEXT] and "disable reminders" in phone.sent[0]
    assert gr.state() == gr.AWAITING_ANSWER
    assert gr.holding_reminders() and gr.has_open_question() and not gr.should_forward()
    gr.on_stranger_arrived(T0 + 5)  # still the same visit: no second question
    assert len(phone.sent) == 1


def test_question_cooldown_stops_telegram_spam_when_a_visitor_flaps(phone):
    gr.on_stranger_arrived(T0)
    gr.on_stranger_left()  # unanswered question goes stale
    assert gr.state() == gr.NORMAL
    gr.on_stranger_arrived(T0 + 60)  # back within 10 minutes: no new prompt
    assert len(phone.sent) == 1 and gr.state() == gr.NORMAL
    gr.on_stranger_arrived(T0 + gr.QUESTION_COOLDOWN_S + 1)
    assert len(phone.sent) == 2 and gr.state() == gr.AWAITING_ANSWER


def test_no_telegram_means_no_question_and_no_new_hold(phone):
    phone.ok = False  # sending fails (not configured / offline)
    gr.on_stranger_arrived(T0)
    assert gr.state() == gr.NORMAL and not gr.holding_reminders()  # falls back to the generic hold
    gr.configure(None, None)
    gr.on_stranger_arrived(T0 + 5000)
    assert gr.state() == gr.NORMAL


# --- yes -> disabled -> ask again on leave -> yes -> back on -------------------------------------
def test_full_yes_cycle(phone):
    gr.on_stranger_arrived(T0)
    assert "off" in gr.answer("Yes")
    assert gr.state() == gr.DISABLED and gr.holding_reminders() and gr.should_forward()
    assert not gr.has_open_question()
    gr.on_stranger_left()
    assert phone.sent[-1] == gr.REENABLE_TEXT and gr.state() == gr.AWAITING_REENABLE
    assert gr.holding_reminders() and gr.has_open_question()  # still held until the owner says so
    assert "back on" in gr.answer("yes")
    assert gr.state() == gr.NORMAL and not gr.holding_reminders()
    assert phone.released == 1  # held reminders are read out


def test_no_at_first_question_keeps_reminders_on_and_releases_whats_held(phone):
    gr.on_stranger_arrived(T0)
    assert "stay on" in gr.answer("no")
    assert gr.state() == gr.ALLOWED and gr.reminders_allowed() and not gr.holding_reminders()
    assert phone.released == 1
    gr.on_stranger_left()
    assert gr.state() == gr.NORMAL


def test_no_at_the_reenable_question_keeps_them_off(phone):
    gr.on_stranger_arrived(T0)
    gr.answer("yes")
    gr.on_stranger_left()
    assert "stay off" in gr.answer("no thanks")
    assert gr.state() == gr.DISABLED and phone.released == 0 and not gr.has_open_question()


def test_visitor_returning_before_reenable_keeps_reminders_off(phone):
    gr.on_stranger_arrived(T0)
    gr.answer("yes")
    gr.on_stranger_left()
    n = len(phone.sent)
    gr.on_stranger_arrived(T0 + 30)  # back before the owner replied: no new question, stay off
    assert gr.state() == gr.DISABLED and len(phone.sent) == n and not gr.has_open_question()


def test_answer_after_the_visitor_left_is_stale_and_ignored(phone):
    gr.on_stranger_arrived(T0)
    gr.on_stranger_left()  # question never answered
    assert gr.answer("yes") is None  # a later "yes" is not swallowed by an old question
    assert gr.state() == gr.NORMAL


# --- strict parsing --------------------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("yes", True), ("Yes!", True), (" YEP ", True), ("Sure", True), ("yes please", True), ("\U0001F44D", True),
    ("no", False), ("Nope.", False), ("no thanks", False), ("don't", False), ("\U0001F44E", False),
    ("yes but first tell me the weather", None), ("no problem, open notepad", None),
    ("yesterday", None), ("know", None), ("okay so what time is it", None), ("", None), ("maybe", None),
])
def test_parse_yes_no_is_strict_whole_message(phone, text, expected):
    assert gr.parse_yes_no(text, gr.AWAITING_ANSWER) is expected


def test_context_phrases_mean_opposite_things_in_the_two_questions(phone):
    assert gr.parse_yes_no("disable them", gr.AWAITING_ANSWER) is True
    assert gr.parse_yes_no("keep them on", gr.AWAITING_ANSWER) is False
    assert gr.parse_yes_no("enable reminders", gr.AWAITING_REENABLE) is True
    assert gr.parse_yes_no("keep them off", gr.AWAITING_REENABLE) is False
    assert gr.parse_yes_no("enable reminders", gr.AWAITING_ANSWER) is None  # wrong question: not an answer
    assert gr.parse_yes_no("keep them off", gr.AWAITING_ANSWER) is None


def test_unclear_reply_leaves_the_question_open(phone):
    gr.on_stranger_arrived(T0)
    assert gr.answer("what reminders do I have?") is None
    assert gr.state() == gr.AWAITING_ANSWER
    assert "off" in gr.answer("yes")


def test_answer_without_an_open_question_is_ignored(phone):
    assert gr.answer("yes") is None and gr.state() == gr.NORMAL


# --- explicit control + forwarding ---------------------------------------------------------------------
def test_tool_controls_and_forwarding_text(phone):
    assert "off" in gr.set_disabled(True) and gr.should_forward()
    gr.forward_reminder("Reminder: buy milk")
    assert phone.sent[-1] == "Held reminder: buy milk"  # no doubled "Reminder:"
    assert "on" in gr.set_disabled(False) and phone.released == 1 and gr.state() == gr.NORMAL
    assert gr.set_disabled(False) == "Reminders are on." and phone.released == 1  # nothing held: no readout
    assert "on" in gr.status()


def test_state_is_memory_only_so_a_restart_returns_to_normal(phone):
    gr.set_disabled(True)
    gr.reset()  # what a restart amounts to
    assert gr.state() == gr.NORMAL and not gr.holding_reminders()


# ===============================================================================================
# jarvis.py integration
# ===============================================================================================
@pytest.fixture()
def j(monkeypatch, tmp_path, phone):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    import jarvis as jv
    import jarvis_face as face

    spoken, toasts = [], []
    monkeypatch.setattr(jv, "_session_context", jv._default_session_context())
    monkeypatch.setattr(jv, "_save_session_context_locked", lambda: None)
    monkeypatch.setattr(jv, "refresh_session_context", lambda: None)
    monkeypatch.setattr(jv, "_notify_phone", lambda *a, **k: None)
    monkeypatch.setattr(jv, "_speak_shaped", spoken.append)
    monkeypatch.setattr(jv, "send_windows_toast", lambda t, m: toasts.append((t, m)))
    monkeypatch.setattr(jv, "record_recent_task", lambda *a, **k: None)
    monkeypatch.setattr(jv.focus_mode, "should_suppress", lambda urgent, *a: False)
    monkeypatch.setattr(jv.sleep_mode, "should_suppress", lambda urgent, *a, **k: False)
    monkeypatch.setattr(jv.sleep_mode, "is_active", lambda: False)
    monkeypatch.setattr(jv, "user_is_actively_working", lambda: False)
    monkeypatch.setattr(face, "group_safe", lambda now=None: False)
    monkeypatch.setattr(jv, "_release_held_reminders", lambda: jv.flush_pending_notifications())
    gr.configure(phone.send, lambda: jv.flush_pending_notifications())
    jv._spoken, jv._toasts = spoken, toasts
    return jv


def _held(jv):
    return [i for i in jv._session_context["pending_notifications"] if i.get("reminder_hold")]


def test_reminders_speak_normally_when_nobody_is_visiting(j):
    j.queue_or_deliver_notification("Reminder: stretch", bypass_busy_gate=True, is_reminder=True)
    assert j._spoken == ["Reminder: stretch"] and _held(j) == []


def test_reminders_are_held_texted_and_silent_once_disabled(j, phone):
    gr.set_disabled(True)
    j.queue_or_deliver_notification("Reminder: call mum", bypass_busy_gate=True, is_reminder=True)
    j.queue_or_deliver_notification("Reminder: take medication", urgent=True, bypass_busy_gate=True, is_reminder=True)
    assert j._spoken == []  # not even the urgent one: the owner said reminders off
    assert len(_held(j)) == 2 and all(i["forwarded"] for i in _held(j))
    assert phone.sent == ["Held reminder: call mum", "Held reminder: take medication"]  # nothing is lost


def test_toast_is_not_shown_while_held_but_is_when_normal(j, monkeypatch):
    from datetime import datetime

    rows = [(1, "secret plan", 0, 0)]

    class Conn:
        def execute(self, sql, *a):
            class R:
                def fetchall(_s):
                    return rows if sql.lstrip().startswith("SELECT") else []
            return R()

        def commit(self): pass
        def close(self): pass

    monkeypatch.setattr(j, "_memory_db_connect", lambda: Conn())
    gr.set_disabled(True)
    j._check_due_reminders(datetime.now())
    assert j._toasts == [] and len(_held(j)) == 1  # no banner showing the text in front of a visitor
    gr.set_disabled(False)
    j._session_context["pending_notifications"].clear()
    j._check_due_reminders(datetime.now())
    assert j._toasts == [("Jarvis Reminder", "secret plan")]


def test_pending_question_holds_reminders_but_does_not_text_them_yet(j, phone):
    gr.on_stranger_arrived(T0)
    j.queue_or_deliver_notification("Reminder: x", bypass_busy_gate=True, is_reminder=True)
    assert j._spoken == [] and len(_held(j)) == 1 and _held(j)[0]["forwarded"] is False
    assert phone.sent == [gr.ASK_TEXT]  # only the question, not the reminder


def test_saying_yes_after_reminders_were_already_held_texts_them_then(j, phone):
    gr.on_stranger_arrived(T0)
    j.queue_or_deliver_notification("Reminder: pay rent", bypass_busy_gate=True, is_reminder=True)
    out = []
    j.handle_text_command("yes", source="phone", reply_sink=out.append)
    assert "off" in out[0] and gr.state() == gr.DISABLED
    assert "Held reminder: pay rent" in phone.sent and _held(j)[0]["forwarded"] is True


def test_saying_no_reads_the_held_reminders_out(j):
    gr.on_stranger_arrived(T0)
    j.queue_or_deliver_notification("Reminder: pay rent", bypass_busy_gate=True, is_reminder=True)
    out = []
    j.handle_text_command("no", source="phone", reply_sink=out.append)
    assert "stay on" in out[0] and _held(j) == []
    assert "Reminder: pay rent" in j._spoken
    j.queue_or_deliver_notification("Reminder: later", bypass_busy_gate=True, is_reminder=True)
    assert j._spoken[-1] == "Reminder: later"  # and new ones speak even with the visitor there


def test_reenabling_reads_out_the_held_reminders(j):
    gr.set_disabled(True)
    j.queue_or_deliver_notification("Reminder: pay rent", bypass_busy_gate=True, is_reminder=True)
    assert j._spoken == []
    gr.on_stranger_left()  # -> asks to re-enable
    out = []
    j.handle_text_command("yes", source="phone", reply_sink=out.append)
    assert "back on" in out[0] and "Reminder: pay rent" in j._spoken and _held(j) == []


def test_flush_on_any_command_does_not_leak_held_reminders(j):
    gr.set_disabled(True)
    j.queue_or_deliver_notification("Reminder: private", bypass_busy_gate=True, is_reminder=True)
    j.flush_pending_notifications()  # runs at the start of every command
    assert j._spoken == [] and len(_held(j)) == 1


def test_default_group_safe_hold_still_lets_urgent_reminders_speak(j, monkeypatch):
    import jarvis_face as face

    monkeypatch.setattr(face, "group_safe", lambda now=None: True)  # a visitor, but no answer/policy yet
    j.queue_or_deliver_notification("Reminder: chat", bypass_busy_gate=True, is_reminder=True)
    j.queue_or_deliver_notification("Reminder: meds", urgent=True, bypass_busy_gate=True, is_reminder=True)
    assert j._spoken == ["Reminder: meds"] and [i["text"] for i in _held(j)] == ["Reminder: chat"]


# --- the phone reply path ---------------------------------------------------------------------------------
def test_only_the_phone_can_answer(j, monkeypatch):
    gr.on_stranger_arrived(T0)
    monkeypatch.setattr(j, "run_agent_loop", lambda *a, **k: "ok")
    for src in ("voice", "text", "dashboard"):
        assert gr.state() == gr.AWAITING_ANSWER
        j.handle_text_command("yes", source=src, reply_sink=lambda r: None)
    assert gr.state() == gr.AWAITING_ANSWER  # a voice "yes" is never taken as the Telegram answer


def test_a_non_answer_from_the_phone_is_an_ordinary_command(j, monkeypatch):
    gr.on_stranger_arrived(T0)
    ran = []
    monkeypatch.setattr(
        j, "run_agent_loop",
        lambda t, tone=None, narrate=False, tools_override=None: ran.append(t) or "done",
    )
    out = []
    j.handle_text_command("what's the weather", source="phone", reply_sink=out.append)
    assert ran == ["what's the weather"] and out == ["done"] and gr.state() == gr.AWAITING_ANSWER


def test_a_yes_for_the_question_never_approves_a_staged_catastrophic_action(j, monkeypatch):
    """The reminders question runs before the confirmation gate, and cancels (never runs) whatever
    was staged - so a stray "yes" cannot shut the computer down."""
    executed = []
    monkeypatch.setattr(j, "_execute_confirmed_action", lambda step, sink=None: executed.append(step))
    with j._pending_action_lock:
        j._pending_action = {"tool_name": "run_shell", "tool_input": {"command": "shutdown /s /t 0"}}
    gr.on_stranger_arrived(T0)
    out = []
    j.handle_text_command("yes", source="phone", reply_sink=out.append)
    assert executed == []  # the gate did NOT run it
    assert j._pending_action is None  # it was cancelled instead
    assert "cancelled the action" in out[0] and gr.state() == gr.DISABLED


def test_the_gate_still_works_normally_when_no_question_is_open(j, monkeypatch):
    executed = []
    monkeypatch.setattr(j, "_execute_confirmed_action", lambda step, sink=None: executed.append(step))
    with j._pending_action_lock:
        j._pending_action = {"tool_name": "run_shell", "tool_input": {"command": "x"}}
    j.handle_text_command("yes", source="phone", reply_sink=lambda r: None)
    assert len(executed) == 1  # unchanged behaviour: no open reminders question, so the gate gets it


def test_reminders_mode_tool_from_any_source(j, monkeypatch):
    out = []

    def run(action):
        def agent(transcript, tone=None, narrate=False, tools_override=None):
            out.append(j._execute_tool("reminders_mode", {"action": action}, transcript))
            return "ok"

        monkeypatch.setattr(j, "run_agent_loop", agent)
        j.handle_text_command("t", source="phone", reply_sink=lambda r: None)

    run("off")
    assert "Reminders are off" in out[-1] and gr.state() == gr.DISABLED
    run("status")
    assert "off" in out[-1]
    run("on")
    assert gr.state() == gr.NORMAL
