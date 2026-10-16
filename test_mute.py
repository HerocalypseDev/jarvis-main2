"""Temporary mute ("shut up for 10 minutes"): intent routing and speak_text skipping."""
import time

import pytest


@pytest.fixture
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "m.db"))
    import jarvis as j
    monkeypatch.setattr(j, "_muted_until", 0.0)
    return j


@pytest.mark.parametrize("phrase", ["shut up for 10 minutes", "Jarvis, be quiet for the next 5 minutes",
                                    "mute for 2 minutes please"])
def test_mute_phrases_route_to_mute(phrase):
    import jarvis_latency as latency
    assert latency.classify_intent(phrase) == "mute"


@pytest.mark.parametrize("phrase", ["shut up", "stop talking", "mute the music"])
def test_other_phrases_are_not_mute(phrase):
    import jarvis_latency as latency
    assert latency.classify_intent(phrase) != "mute"


def test_mute_sets_deadline_and_speak_text_stays_silent(J, monkeypatch):
    reply = J._deterministic_intent_reply("mute", "shut up for 10 minutes")
    assert "10 minutes" in reply
    assert J._is_muted()
    assert J._muted_until > time.monotonic() + 9 * 60
    monkeypatch.setattr(J, "_await_ack", lambda: (_ for _ in ()).throw(AssertionError("should not speak")))
    J.speak_text("hello there")  # returns before any audio work


def test_not_muted_by_default(J):
    assert not J._is_muted()


def test_mute_out_of_range_is_refused(J):
    assert "between 1 and 1440" in J._deterministic_intent_reply("mute", "mute for 5000 minutes")
    assert not J._is_muted()


# Owner report 2026-10-16: "shut up" and Jarvis still read out "file changed in a watched folder".

@pytest.mark.parametrize("phrase", ["unmute", "you can talk again", "Jarvis, talk again please", "start talking"])
def test_unmute_phrases_route_to_mute_and_cancel_it(J, phrase):
    import jarvis_latency as latency
    assert latency.classify_intent(phrase) == "mute"
    J._muted_until = time.monotonic() + 600
    assert "cancelled" in J._deterministic_intent_reply("mute", phrase)
    assert not J._is_muted()


def test_bare_shut_up_mutes_but_stop_only_interrupts(J, monkeypatch):
    monkeypatch.setattr(J, "_interrupt_speech", lambda: None)
    assert J._deterministic_intent_reply("hush", "stop") == ""
    assert not J._is_muted()
    assert J._deterministic_intent_reply("hush", "shut up") == ""
    assert J._muted_until > time.monotonic() + (J.HUSH_MUTE_MIN - 1) * 60


def test_muted_notifications_go_to_the_inbox_even_urgent_ones(J, monkeypatch):
    said, kept = [], []
    monkeypatch.setattr(J, "_speak_shaped", said.append)
    monkeypatch.setattr(J, "_add_missed", lambda text, source="": kept.append(text))
    monkeypatch.setattr(J, "_notify_phone", lambda *a, **k: None)
    J._muted_until = time.monotonic() + 600
    J.queue_or_deliver_notification("File changed in a watched folder: big.zip (900 MB)", urgent=True)
    assert said == [] and kept and "big.zip" in kept[0]


def test_a_reply_to_a_new_command_still_speaks_while_muted(J, monkeypatch):
    J._muted_until = time.monotonic() + 600
    reached = []
    monkeypatch.setattr(J, "_await_ack", lambda: reached.append(1) or (_ for _ in ()).throw(RuntimeError("stop")))
    J._command_ctx.source = "voice"
    try:
        with pytest.raises(RuntimeError):
            J.speak_text("It's 3 PM.")
    finally:
        J._command_ctx.source = None
    assert reached


def test_file_watcher_announcements_are_not_urgent():
    import pathlib
    src = pathlib.Path(__file__).with_name("jarvis.py").read_text(encoding="utf-8")
    assert "notifier=lambda text, urgent: queue_or_deliver_notification(text)" in src
