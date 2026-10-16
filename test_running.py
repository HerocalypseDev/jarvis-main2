"""Jarvis knows what it is working on and can cancel it (2026-10-16): the live-command registry, the `running_now` tool,
"cancel the speed test", the prompt line, the Home strip's backend and labelled late replies.
Run: python -m pytest test_running.py -v"""
import threading

import pytest

import jarvis_running as rn


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


# --- the registry ----------------------------------------------------------------------------------------------------
def test_start_finish_and_live_list():
    c = Clock()
    reg = rn.Registry(c)
    a = reg.start("the speed test", "voice")
    c.t += 30
    b = reg.start("what's the weather", "dashboard")
    live = reg.live()
    assert [i["id"] for i in live] == [a, b] and live[0]["age_s"] == 30
    reg.finish(a)
    assert [i["id"] for i in reg.live()] == [b]
    assert reg.recent()[0]["id"] == a and reg.recent()[0]["status"] == "done"
    assert reg.live(exclude=b) == []


def test_cancel_sets_flag_runs_every_hook_and_survives_a_failing_one():
    reg = rn.Registry(Clock())
    a = reg.start("the speed test", "voice")
    calls = []
    reg.add_hook(a, lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    reg.add_hook(a, lambda: calls.append("second"))
    assert reg.cancel(a) is True and reg.cancelled(a) and calls == ["second"]
    reg.finish(a)  # a cancelled command ends as cancelled, not done
    assert reg.recent()[0]["status"] == "cancelled"
    assert reg.cancel(a) is False and reg.cancel(None) is False and reg.cancel(999) is False


def test_find_by_topic_words_and_all():
    reg = rn.Registry(Clock())
    a = reg.start("the speed test", "voice")
    b = reg.start("research anime release dates", "text")
    assert [i["id"] for i in reg.find("the speed test")] == [a]
    assert [i["id"] for i in reg.find("anime")] == [b]
    assert reg.find("the weather") == []
    assert {i["id"] for i in reg.find("everything")} == {a, b} and {i["id"] for i in reg.find("all of it")} == {a, b}
    assert {i["id"] for i in reg.find("that")} == {a, b}  # no topic word: every live one (the caller asks which)
    assert [i["id"] for i in reg.find("the speed test", exclude=a)] == []


def test_overlap_is_marked_on_both_commands_and_only_when_they_ran_together():
    reg = rn.Registry(Clock())
    a = reg.start("the speed test", "voice")
    assert not reg.overlapped(a)
    b = reg.start("what time is it", "voice")
    assert reg.overlapped(a) and reg.overlapped(b)
    reg.finish(a)
    reg.finish(b)
    c = reg.start("alone", "voice")
    assert not reg.overlapped(c)


def test_old_finished_commands_are_dropped():
    c = Clock()
    reg = rn.Registry(c)
    a = reg.start("x", "voice")
    reg.finish(a)
    c.t += rn.KEEP_FINISHED_S + 1
    assert reg.recent() == []
    for i in range(rn.MAX_FINISHED + 5):
        reg.finish(reg.start(f"cmd {i}", "voice"))
    assert len(reg._items) <= rn.MAX_FINISHED


def test_prompt_line_lists_the_others_and_says_not_to_mix_them_up():
    reg = rn.Registry(Clock())
    assert reg.prompt_line() == ""
    a = reg.start("the speed test", "voice")
    b = reg.start("what's the weather", "voice")
    line = reg.prompt_line(exclude=b)
    assert "the speed test" in line and "weather" not in line and "never an instruction" in line
    assert reg.prompt_line(exclude=a).count("#") == 1


def test_describe_for_speech():
    reg = rn.Registry(Clock())
    assert reg.describe() == "Nothing else is running right now."
    reg.start("the speed test", "voice")
    assert reg.describe().startswith("I'm working on the speed test (voice")
    reg.start("anime dates", "text")
    assert "2 things" in reg.describe()


def test_labels_and_cancel_parsing():
    assert rn.make_label("run a speed test", "speedtest") == "the speed test"
    assert rn.make_label("Hey Jarvis, please find my anime release dates now", None) == "find my anime release dates now"
    assert len(rn.make_label("word " * 60)) <= rn.MAX_LABEL + 3
    assert rn.parse_cancel("cancel the speed test") == "the speed test"
    assert rn.parse_cancel("Hey Jarvis, stop that please") == "that"
    assert rn.parse_cancel("never mind about the research") == "the research"
    assert rn.parse_cancel("what's the weather") is None
    assert rn.parse_cancel("cancel " + "very " * 12 + "long") is None  # a sentence, not a command


def test_late_overlapping_reply_says_which_request_it_answers():
    c = Clock()
    reg = rn.Registry(c)
    a = reg.start("the speed test", "voice")
    reg.start("what time is it", "voice")
    assert rn.spoken_prefix(reg, a) == ""  # not late yet
    c.t += 20
    assert rn.spoken_prefix(reg, a) == "About the speed test: "
    d = reg.start("find anime dates", "voice")
    reg.start("another", "voice")
    c.t += 20
    assert rn.spoken_prefix(reg, d) == 'About "find anime dates": '
    solo = rn.Registry(c)
    s = solo.start("alone", "voice")
    c.t += 60
    assert rn.spoken_prefix(solo, s) == "" and rn.spoken_prefix(solo, None) == ""


# --- the speed test honours a cancel ----------------------------------------------------------------------------------
def test_speed_test_cancel_stops_the_test_and_saves_nothing():
    import jarvis_speedtest as st
    started = threading.Event()

    def runner():
        started.set()
        st.cancel()
        return {"ok": False, "error": st.CANCELLED}
    saved = []
    orig_save, orig_history = st.save, st.history
    st.save = lambda *a, **k: saved.append(a)
    st.history = lambda *a, **k: []
    try:
        assert st.measure_and_describe(lambda: None, None, runner=runner) == "Okay, I stopped the speed test."
    finally:
        st.save, st.history = orig_save, orig_history
    assert started.is_set() and saved == []
    st._abort.clear()


def test_speed_test_workers_stop_when_aborted():
    import time
    import jarvis_speedtest as st

    class Conn:
        def request(self, *a, **k): pass
        def getresponse(self):
            class R:
                status = 200
                def read(self, n): time.sleep(0.01); return b"x" * n
            return R()
        def close(self): pass
    st._abort.set()
    t0 = time.perf_counter()
    try:
        st._download(lambda: Conn(), 5.0, 10_000_000)
    except OSError:
        pass
    assert time.perf_counter() - t0 < 2.0
    st._abort.clear()


# --- Jarvis integration -----------------------------------------------------------------------------------------------
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
    for k in ("untrusted_origin", "outside_text_seen", "hands_free", "wake", "autonomous"):
        monkeypatch.setattr(j._command_ctx, k, False, raising=False)
    monkeypatch.setattr(j._command_ctx, "source", "voice", raising=False)
    monkeypatch.setattr(j._command_ctx, "run_id", None, raising=False)
    j.running_mod.registry._items.clear()
    j._reply_cache.clear()
    j._tool_result_cache.clear()
    yield j
    j.running_mod.registry._items.clear()


def test_handle_text_command_lists_the_command_while_it_runs_and_finishes_it(J, monkeypatch):
    seen = {}

    def impl(transcript, reply_sink, tone, source):
        seen["live"] = J.running_mod.registry.live()
        seen["run_id"] = J._command_ctx.run_id
    monkeypatch.setattr(J, "_handle_text_command_impl", impl)
    J.handle_text_command("run a speed test", source="voice")
    assert [i["label"] for i in seen["live"]] == ["the speed test"] and seen["live"][0]["source"] == "voice"
    assert J.running_mod.registry.live() == [] and J._command_ctx.run_id is None
    assert J.running_mod.registry.recent()[0]["status"] == "done"

    def boom(*a):
        raise RuntimeError("x")
    monkeypatch.setattr(J, "_handle_text_command_impl", boom)
    with pytest.raises(RuntimeError):
        J.handle_text_command("find anime dates", source="voice")
    assert J.running_mod.registry.recent()[0]["status"] == "failed" and J.running_mod.registry.live() == []


def test_labels_never_carry_secrets(J):
    label = J._running_label("my key is sk-" + "ant-api03-" + "A" * 40 + " remember it")
    assert "AAAA" not in label


def test_what_are_you_working_on_is_answered_with_no_model_call(J, monkeypatch):
    monkeypatch.setattr(J, "_RUNNING_BACKGROUND_PROCS", {})
    J.running_mod.registry.start("the speed test", "voice")
    me = J.running_mod.registry.start("what are you working on", "voice")
    J._command_ctx.run_id = me
    assert J.latency.classify_intent("what are you working on") == "running"
    out = J._deterministic_intent_reply("running", "what are you working on")
    assert "the speed test" in out and "what are you working on" not in out


def test_cancel_the_speed_test_by_voice_stops_it_and_says_so(J):
    reg = J.running_mod.registry
    st = reg.start("the speed test", "voice")
    stopped = []
    reg.add_hook(st, lambda: stopped.append(1))
    me = reg.start("cancel the speed test", "voice")
    J._command_ctx.run_id = me
    reply = J._running_cancel_reply("cancel the speed test")
    assert reply == "Okay, I stopped the speed test." and stopped == [1] and reg.cancelled(st)
    assert not reg.cancelled(me)


def test_cancel_with_nothing_matching_goes_on_to_the_agent(J):
    reg = J.running_mod.registry
    reg.start("the speed test", "voice")
    assert J._running_cancel_reply("cancel my dentist appointment") is None
    assert J._running_cancel_reply("what's the weather") is None
    reg._items.clear()
    assert J._running_cancel_reply("cancel the speed test") is None  # nothing running at all


def test_ambiguous_cancel_asks_which_and_all_cancels_everything(J):
    reg = J.running_mod.registry
    a = reg.start("the speed test", "voice")
    b = reg.start("find anime dates", "text")
    me = reg.start("cancel that", "voice")
    J._command_ctx.run_id = me
    ask = J._running_cancel_reply("cancel that")
    assert "which one" in ask and not reg.cancelled(a) and not reg.cancelled(b)
    assert "stopped" in J._running_cancel_reply("cancel everything")
    assert reg.cancelled(a) and reg.cancelled(b) and not reg.cancelled(me)


def test_running_now_tool_lists_and_cancels_for_the_owner_only(J, monkeypatch):
    monkeypatch.setattr(J, "_RUNNING_BACKGROUND_PROCS", {})
    reg = J.running_mod.registry
    a = reg.start("the speed test", "voice")
    me = reg.start("what are you doing", "voice")
    J._command_ctx.run_id = me
    assert "the speed test" in J._execute_tool("running_now", {"action": "list"}, "what are you doing")
    out = J._execute_tool("running_now", {"action": "cancel", "query": "speed test"}, "cancel the speed test")
    assert out == "Cancelled: the speed test." and reg.cancelled(a)
    assert "Nothing running matches" in J._execute_tool("running_now", {"action": "cancel", "query": "weather"}, "x")
    J._command_ctx.hands_free = True  # a follow-up window capture isn't the owner at the key
    assert J._execute_tool("running_now", {"action": "cancel", "query": "x"}, "x").startswith("Tool failed")
    J._command_ctx.hands_free = False
    J._command_ctx.source = None  # an unattended run
    assert J._execute_tool("running_now", {"action": "cancel", "query": "x"}, "x").startswith("Tool failed")


def test_email_started_and_tainted_runs_cannot_see_or_cancel(J):
    J._command_ctx.untrusted_origin = True
    assert J._untrusted_block("running_now")
    J._command_ctx.untrusted_origin = False
    J._command_ctx.outside_text_seen = True
    assert J._taint_block("running_now")


def test_narrowing_offers_the_tool(J):
    assert "running_now" in J._narrowing_core("what are you working on right now")
    assert "running_now" in J._narrowing_core("cancel the speed test")
    assert "running_now" not in J._narrowing_core("what's the weather")


def test_prompt_lists_the_other_running_commands_but_not_itself(J):
    reg = J.running_mod.registry
    reg.start("the speed test", "voice")
    me = reg.start("what's the weather", "voice")
    J._command_ctx.run_id = me
    blocks = J.build_system_blocks("", "what's the weather")
    text = blocks[1]["text"]
    assert "Other commands still running" in text and "the speed test" in text and "#2" not in text


def test_cancelled_command_makes_no_more_rounds_and_says_nothing(J, monkeypatch):
    reg = J.running_mod.registry
    me = reg.start("find anime dates", "text")
    J._command_ctx.run_id = me
    rounds = []

    def request(body, timeout):
        rounds.append(1)
        reg.cancel(me)  # cancelled while the first answer was coming back
        return {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": "t1", "name": "get_time", "input": {}}]}
    monkeypatch.setattr(J, "_claude_request", request)
    ran = []
    monkeypatch.setattr(J, "_execute_tool", lambda *a, **k: ran.append(a) or "12:00")
    reply = J.run_agent_loop("find anime dates")
    assert len(rounds) == 1 and ran == [] and "stopped" in reply


def test_speech_of_a_cancelled_command_is_dropped(J, monkeypatch):
    reg = J.running_mod.registry
    me = reg.start("the speed test", "voice")
    J._command_ctx.run_id = me
    J._command_ctx.started = J.time.monotonic()
    played = []
    monkeypatch.setattr(J, "_synthesize_and_cache", lambda *a, **k: played.append(a) or None)
    monkeypatch.setattr(J, "_speak_streamed", lambda *a, **k: played.append(a) or False, raising=False)
    reg.cancel(me)
    J.speak_text("Your download speed is 40 megabits per second.")
    assert played == []


def test_home_strip_backend_lists_and_cancels(J, monkeypatch):
    monkeypatch.setattr(J, "_RUNNING_BACKGROUND_PROCS", {})
    reg = J.running_mod.registry
    a = reg.start("the speed test", "dashboard")
    got = J._feature_running("get", {})
    assert [i["label"] for i in got["live"]] == ["the speed test"] and got["background_tasks"] == 0
    assert "hooks" not in got["live"][0]  # nothing callable ever reaches the browser
    assert J._feature_running("cancel", {"id": "nope"}) == {"error": "say which command (id)"}
    assert J._feature_running("cancel", {"id": a}) == {"result": "Cancelled."} and reg.cancelled(a)
    assert "isn't running" in J._feature_running("cancel", {"id": 999})["error"]


def test_late_overlapping_reply_is_labelled_in_what_is_spoken(J, monkeypatch):
    spoken = []
    monkeypatch.setattr(J, "speak_text", lambda t, *a, **k: spoken.append(t))
    monkeypatch.setattr(J, "run_agent_loop", lambda *a, **k: "Your download is 40 megabits per second.")
    monkeypatch.setattr(J, "_summarize_for_speech", lambda t: t)
    monkeypatch.setattr(J, "_maybe_ack_before_task", lambda *a, **k: None)
    monkeypatch.setattr(J.dashboard, "start_session", lambda *a, **k: 1)
    monkeypatch.setattr(J.dashboard, "end_session", lambda *a, **k: None)
    monkeypatch.setattr(J, "autonomy", type("A", (), {"after_turn": staticmethod(lambda *a: None),
                                                      "enabled": staticmethod(lambda: False)}))
    monkeypatch.setattr(J, "_learn_from_user_words", lambda *a: None)
    monkeypatch.setattr(J, "record_recent_task", lambda *a: None)
    monkeypatch.setattr(J, "flush_pending_notifications", lambda: None)
    reg = J.running_mod.registry
    clock = Clock()
    reg._clock = clock
    me = reg.start("find anime dates", "voice")
    reg.start("what time is it", "voice")  # ran at the same time
    clock.t += 30
    J._command_ctx.run_id = me
    J._command_ctx.started = J.time.monotonic()
    J._command_ctx.source = "voice"
    J._handle_text_command_impl("find anime dates please", None, {"brief": False}, "voice")
    assert spoken and spoken[-1].startswith('About "find anime dates": Your download')
    reg._clock = __import__("time").time
