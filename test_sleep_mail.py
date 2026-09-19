"""Tests for the Sleep Mode mail take-over. Run: python -m pytest test_sleep_mail.py -v
Gmail and the model are faked; nothing is sent, read or billed. Isolated temp DB."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

import jarvis_sleep_mail as sm

STARTED = "2026-09-19T23:00:00"


@pytest.fixture()
def db(monkeypatch, tmp_path):
    path = tmp_path / "t.db"
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(path))
    monkeypatch.delenv("JARVIS_SLEEP_FAMILY_EXCLUDE", raising=False)
    monkeypatch.delenv("JARVIS_OWN_EMAILS", raising=False)
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE user_profile (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    c.execute("CREATE TABLE memory_facts (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, "
              "key TEXT, content TEXT NOT NULL, created_at TEXT NOT NULL, superseded_at TEXT, superseded_by INTEGER)")
    c.execute("INSERT INTO user_profile VALUES ('email', 'me@x.com')")
    facts = [
        ("relationship", "user_elder_sister", "Hero's elder sister Deborah (spelled D-E-B), email sis@x.com", None),
        ("relationship", "old", "Hero's elder sister Tebura, email old@x.com", "2026-09-18"),  # superseded
        ("relationship", "user_mom", "Hero's mom, email mom@x.com", None),
        ("relationship", "user_dad", "Hero's dad Jacob, email me@x.com", None),  # equals own address
        ("fact", "note", "Hero likes tea, someone@x.com", None),  # not a relationship
    ]
    for cat, k, content, sup in facts:
        c.execute("INSERT INTO memory_facts (category,key,content,created_at,superseded_at) VALUES (?,?,?,?,?)",
                  (cat, k, content, "2026-09-16", sup))
    c.commit()
    c.close()
    return path


def test_load_family_uses_current_relationships_and_excludes_own_and_env(db, monkeypatch):
    assert sm.load_family() == {"sis@x.com": "elder sister Deborah", "mom@x.com": "mom"}
    monkeypatch.setenv("JARVIS_SLEEP_FAMILY_EXCLUDE", "mom@x.com")
    assert sm.load_family() == {"sis@x.com": "elder sister Deborah"}


# --- retry -----------------------------------------------------------------------------------
def test_send_retries_every_minute_then_succeeds():
    sleeps, calls = [], {"n": 0}

    def send():
        calls["n"] += 1
        return (calls["n"] >= 4, "boom")

    ok, _, used = sm.send_with_retry(send, sleep=sleeps.append)
    assert ok and calls["n"] == 4 and used == 3 and sleeps == [60, 60, 60]


def test_send_gives_up_after_five_retries():
    sleeps, calls = [], {"n": 0}

    def send():
        calls["n"] += 1
        return False, "still down"

    ok, detail, used = sm.send_with_retry(send, sleep=sleeps.append)
    assert not ok and calls["n"] == 6 and used == 5 and sleeps == [60] * 5 and detail == "still down"


def test_send_exception_counts_as_failure():
    ok, detail, _ = sm.send_with_retry(lambda: (_ for _ in ()).throw(RuntimeError("x")), retries=1, sleep=lambda s: None)
    assert not ok and "RuntimeError" in detail


# --- the cycle -------------------------------------------------------------------------------
def _search(*msgs):
    return "\n\n".join(f"ID: {i}\nSubject: {s}\nFrom: {f}\nDate: now" for i, s, f in msgs)


class FakeGmail:
    def __init__(self, search, fail_sends=0):
        self.search, self.fail_sends, self.sent, self.calls = search, fail_sends, [], []

    def __call__(self, tool, args):
        self.calls.append(tool)
        if tool == "search_emails":
            return self.search
        if tool == "read_email":
            return "Thread ID: T1\nSubject: s\nFrom: f\n\nAre you coming to dinner Sunday?"
        if tool == "send_email":
            if self.fail_sends > 0:
                self.fail_sends -= 1
                return "MCP tool call failed: network"
            self.sent.append(args)
            return "Email sent"
        raise AssertionError(tool)


def _run(gmail, claude, records, sleeps=None):
    return sm.run_cycle(mcp=gmail, claude=claude, record=records.append, since_iso=STARTED,
                        sleep_started_at=STARTED, sleep=(sleeps.append if sleeps is not None else lambda s: None))


def test_family_email_gets_reply_recorded_and_not_repeated(db):
    g = FakeGmail(_search(("m1", "Dinner?", "Deb <sis@x.com>")))
    rec = []
    claude = lambda system, user, n: "Hi! Jarvis here, Hero is asleep."
    stats = _run(g, claude, rec)
    assert stats["family_replied"] == 1
    sent = g.sent[0]
    assert sent["to"] == ["sis@x.com"] and sent["subject"] == "Re: Dinner?" and sent["threadId"] == "T1"
    assert "Jarvis" in sent["body"] and "asleep" in sent["body"].split("Hi! Jarvis here")[1]
    assert len(rec) == 1 and "elder sister Deborah" in rec[0] and "Dinner?" in rec[0]
    _run(g, claude, rec)  # same message again: already handled
    assert len(g.sent) == 1 and len(rec) == 1


def test_first_reply_introduces_later_ones_dont(db):
    prompts = []
    g = FakeGmail(_search(("m1", "Hi", "sis@x.com")))
    _run(g, lambda s, u, n: prompts.append(s) or "ok", [])
    g.search = _search(("m2", "Re: Hi", "sis@x.com"))
    _run(g, lambda s, u, n: prompts.append(s) or "ok", [])
    assert "first reply" in prompts[0] and "already introduced" in prompts[1]


def test_send_failure_retries_then_reports(db):
    g = FakeGmail(_search(("m1", "Help", "mom@x.com")), fail_sends=99)
    rec, sleeps = [], []
    stats = _run(g, lambda s, u, n: "reply", rec, sleeps)
    assert stats["family_failed"] == 1 and sleeps == [60] * 5
    assert g.calls.count("send_email") == 6
    assert "could not send" in rec[0] and "6 tries" in rec[0]


def test_send_recovers_after_errors(db):
    g = FakeGmail(_search(("m1", "Help", "mom@x.com")), fail_sends=2)
    rec, sleeps = [], []
    stats = _run(g, lambda s, u, n: "reply", rec, sleeps)
    assert stats["family_replied"] == 1 and sleeps == [60, 60] and len(g.sent) == 1


def test_own_address_and_unknown_senders(db):
    g = FakeGmail(_search(("a", "me", "me@x.com"), ("b", "Your account was locked", "Bank <alerts@bank.com>"),
                          ("c", "50% off", "promo@shop.com")))
    rec = []
    classify = lambda system, user, n: "[0]" if "locked" in user.split("\n")[0] else "[]"
    stats = _run(g, classify, rec)
    assert g.sent == [] and "send_email" not in g.calls  # never replies to non-family or self
    assert stats["skipped"] == 1 and stats["critical"] == 1
    assert "alerts@bank.com" in rec[0] and "did not reply" in rec[0]


def test_reply_cap_per_sender_per_night(db, monkeypatch):
    monkeypatch.setattr(sm, "MAX_REPLIES_PER_SENDER", 2)
    g, rec = FakeGmail(""), []
    for i in range(4):
        g.search = _search((f"m{i}", "ping", "sis@x.com"))
        _run(g, lambda s, u, n: "pong", rec)
    assert len(g.sent) == 2 and "reply limit" in rec[-1]


def test_search_error_is_harmless(db):
    g = FakeGmail("MCP tool call failed: offline")
    rec = []
    assert _run(g, lambda *a: "x", rec)["seen"] == 0 and rec == []


# --- jarvis.py wiring ------------------------------------------------------------------------
@pytest.fixture()
def jarvis(monkeypatch, tmp_path, db):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import jarvis as j

    monkeypatch.setattr(j, "SESSION_STATE_PATH", tmp_path / "session_state.json")
    monkeypatch.setattr(j, "_session_context", j._default_session_context())
    monkeypatch.setattr(j, "_notify_phone", lambda *a, **k: None)
    monkeypatch.setattr(j, "refresh_session_context", lambda: None)
    return j


def test_agent_finished_asleep_is_held_not_spoken(jarvis, monkeypatch):
    spoken = []
    monkeypatch.setattr(jarvis, "_speak_shaped", spoken.append)
    monkeypatch.setattr(jarvis.sleep_mode, "is_active", lambda: True)
    jarvis.queue_or_deliver_notification("Agent finished: tests pass", urgent=True, quiet_asleep=True)
    assert spoken == []
    item = jarvis._session_context["pending_notifications"][0]
    assert item["important"] and item["during_sleep"]
    monkeypatch.setattr(jarvis.sleep_mode, "is_active", lambda: False)  # awake: spoken as before
    jarvis.queue_or_deliver_notification("Agent finished: again", urgent=True, quiet_asleep=True)
    assert spoken == ["Agent finished: again"]


def test_tick_runs_every_30_minutes_only_while_asleep(jarvis, monkeypatch):
    runs = []
    monkeypatch.setattr(jarvis.sleep_mail, "run_cycle", lambda **k: runs.append(k["since_iso"]))
    monkeypatch.setattr(jarvis, "ensure_mcp_started", lambda: None)
    monkeypatch.setitem(jarvis._mcp_tool_index, "mcp_gmail_search_emails", ("gmail", "search_emails"))
    started = datetime(2026, 9, 19, 23, 0)
    monkeypatch.setattr(jarvis.sleep_mode, "started_at", lambda: started.isoformat())
    jarvis._sleep_mail_last_check = None

    def tick(minutes):
        jarvis._sleep_mail_tick(started + timedelta(minutes=minutes))
        import time; time.sleep(0.15)  # let the worker thread run

    tick(10); assert runs == []
    tick(31); assert len(runs) == 1
    tick(45); assert len(runs) == 1
    tick(62); assert len(runs) == 2
    monkeypatch.setattr(jarvis.sleep_mode, "started_at", lambda: None)
    tick(200); assert len(runs) == 2 and jarvis._sleep_mail_last_check is None
