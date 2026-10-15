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
