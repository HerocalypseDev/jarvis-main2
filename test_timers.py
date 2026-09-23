"""Persistent named timers (P5). Temp DB only; no real waiting beyond fractions of a second."""

import time
from datetime import datetime, timedelta

import pytest

import jarvis_latency as latency


@pytest.fixture
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "t.db"))
    import jarvis as j
    fired = []
    monkeypatch.setattr(j, "queue_or_deliver_notification", lambda text, urgent=False, **k: fired.append((text, urgent)))
    monkeypatch.setattr(j, "_timers", {})
    j._test_fired = fired
    yield j
    for t in j._timers.values():
        t["timer"].cancel()


@pytest.mark.parametrize("text,name", [
    ("set a pasta timer for 10 minutes", "pasta"), ("set a timer called break for 5 minutes", "break"),
    ("set a 10 minute timer", None), ("set a timer for 10 minutes for tea", "tea"),
    ("cancel all timers", None), ("how long is left on the pasta timer", "pasta"),
])
def test_timer_names(jarvis, text, name):
    assert jarvis._timer_name(text) == name


def test_named_timers_list_and_cancel_by_name(jarvis):
    assert jarvis._timer_reply("set a pasta timer for 10 minutes") == "Pasta timer set for 10 minutes."
    assert jarvis._timer_reply("set a break timer for 5 minutes") == "Break timer set for 5 minutes."
    listing = jarvis._timer_reply("what timers are running")
    assert listing.index("break timer") < listing.index("pasta timer")  # soonest first
    left = jarvis._timer_reply("how long is left on the pasta timer")
    assert left.startswith("pasta timer: ") and "break" not in left
    assert jarvis._timer_reply("cancel the pasta timer") == "Cancelled the pasta timer."
    assert jarvis._timer_reply("cancel the soup timer") == "There's no soup timer."
    assert [t["name"] for t in jarvis._timers.values()] == ["break"]


def test_timers_survive_a_restart_and_missed_ones_are_announced(jarvis, monkeypatch):
    jarvis._timer_reply("set a pasta timer for 10 minutes")
    jarvis._timers_db("INSERT INTO timers (name, label, ends_at, created_at) VALUES (?, ?, ?, ?)",
                      ("tea", "tea", (datetime.now() - timedelta(minutes=3)).isoformat(timespec="seconds"),
                       datetime.now().isoformat(timespec="seconds")))
    for t in jarvis._timers.values():  # "restart": in-memory timers are gone
        t["timer"].cancel()
    monkeypatch.setattr(jarvis, "_timers", {})
    jarvis._restore_timers()
    assert [t["name"] for t in jarvis._timers.values()] == ["pasta"]
    assert len(jarvis._test_fired) == 1 and "tea timer went off" in jarvis._test_fired[0][0] and jarvis._test_fired[0][1]
    assert jarvis._timers_db("SELECT status FROM timers WHERE name = 'tea'") == [("done",)]
    jarvis._restore_timers()  # a second restart doesn't announce it again
    assert len(jarvis._test_fired) == 1


def test_timer_fires_urgent_and_is_closed_in_the_db(jarvis):
    jarvis._timer_reply("set an egg timer for 0.05 seconds")
    time.sleep(0.4)
    assert jarvis._test_fired == [("Your egg timer is done.", True)]
    assert jarvis._timers_db("SELECT status FROM timers") == [("done",)]


def test_named_timer_phrases_route_to_the_timer_fast_path():
    for text in ("set a pasta timer for 10 minutes", "cancel the pasta timer", "how long is left on the pasta timer"):
        assert latency.classify_intent(text) == "timer"
