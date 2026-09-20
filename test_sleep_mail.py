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


# --- test mode + own-message guard -----------------------------------------------------------
def test_test_mode_answers_only_the_test_address_even_if_it_is_own(db):
    g = FakeGmail(_search(("a", "hello", "Me <me@x.com>"), ("b", "hey", "sis@x.com"), ("c", "promo", "p@shop.com")))
    rec = []
    stats = sm.run_cycle(mcp=g, claude=lambda s, u, n: "hi there", record=rec.append,
                         since_iso=STARTED, sleep_started_at=STARTED, sleep=lambda s: None,
                         test_address="me@x.com")
    assert stats["family_replied"] == 1 and [m["to"] for m in g.sent] == [["me@x.com"]]
    conn = sm._connect()
    assert conn.execute("SELECT message_id FROM sleep_mail_handled").fetchall() == [("a",)]  # others untouched
    conn.close()


def test_inbound_hook_receives_the_full_body_not_just_the_subject(db):
    g = FakeGmail(_search(("p1", "Meeting Friday", "Promo <p@shop.com>")))
    seen = []
    sm.run_cycle(mcp=g, claude=lambda s, u, n: "", record=lambda t: None, since_iso=STARTED,
                 sleep_started_at=STARTED, sleep=lambda s: None, on_inbound=seen.append)
    assert seen and seen[0]["subject"] == "Meeting Friday" and seen[0]["id"] == "p1"
    assert "Are you coming to dinner Sunday?" in seen[0]["body"]


def test_own_signature_is_skipped_but_quoted_signature_is_not(db):
    sig = sm._sig_line()
    assert sm._is_our_own_message(f"Hi\n\n{sig}")
    assert not sm._is_our_own_message(f"Thanks!\n\nOn Sat, Jarvis wrote:\n> Hi\n> {sig}")

    class G(FakeGmail):
        def __call__(self, tool, args):
            if tool == "read_email":
                return f"Thread ID: T1\nSubject: s\nFrom: f\n\nHi there\n\n{sig}"
            return super().__call__(tool, args)

    g = G(_search(("m1", "Re: Dinner", "sis@x.com")))
    stats = _run(g, lambda s, u, n: "x", [])
    assert g.sent == [] and stats["skipped"] == 1


def test_quoted_history_is_stripped_from_replies():
    raw = ("Thread ID: T1\nSubject: Re: hi\nFrom: f\n\nbut am scared, summarize the note\n\n"
           "On Sat, 19 Sept 2026 at 05:54, Someone <a@b.com> wrote:\n> Hello. I am Jarvis.\n> more")
    tid, body = sm._body_of(raw)
    assert tid == "T1" and body == "but am scared, summarize the note"


# --- attachments ----------------------------------------------------------------------------
READ_WITH_ATT = ("Thread ID: T1\nSubject: notes\nFrom: f\n\nplease summarize\n\n"
                 "Attachments (2):\n- Chemical bonding notes.pdf (application/pdf, 12 KB, ID: AAA111)\n"
                 "- plan.txt (text/plain, 1 KB, ID: BBB222)")


def test_parse_attachments_and_body_excludes_listing():
    atts = sm.parse_attachments(READ_WITH_ATT)
    assert [(a["name"], a["mime"], a["id"]) for a in atts] == [
        ("Chemical bonding notes.pdf", "application/pdf", "AAA111"), ("plan.txt", "text/plain", "BBB222")]
    assert sm._body_of(READ_WITH_ATT)[1] == "please summarize"


class AttGmail(FakeGmail):
    """Writes the 'downloaded' file where the real tool would."""
    files = {"plan.txt": b"Step 1: revise ionic bonding.", "Chemical bonding notes.pdf": b"%PDF-scan-no-text",
             "pic.png": b"\x89PNG", "evil.exe": b"MZ"}

    def __call__(self, tool, args):
        if tool == "read_email":
            return READ_WITH_ATT
        if tool == "download_attachment":
            from pathlib import Path
            if args["filename"] not in self.files:
                return "MCP tool call failed: not found"
            (Path(args["savePath"]) / args["filename"]).write_bytes(self.files[args["filename"]])
            return "Attachment downloaded successfully"
        return super().__call__(tool, args)


def test_read_attachments_text_scanned_pdf_image_and_unreadable(db, monkeypatch):
    monkeypatch.setattr(sm, "MAX_ATTACHMENTS", 4)
    g = AttGmail("")
    atts = [{"name": "plan.txt", "mime": "text/plain", "kb": 1, "id": "b"},
            {"name": "Chemical bonding notes.pdf", "mime": "application/pdf", "kb": 12, "id": "a"},
            {"name": "pic.png", "mime": "image/png", "kb": 1, "id": "c"},
            {"name": "evil.exe", "mime": "application/x-msdownload", "kb": 1, "id": "d"}]
    text, blocks = sm.read_attachments(g, "msg1", atts)
    assert "revise ionic bonding" in text and "can't read" in text  # .txt read, .exe refused
    assert [b["type"] for b in blocks] == ["text", "document", "text", "image"]  # scanned PDF + image -> model
    assert blocks[1]["source"]["media_type"] == "application/pdf"
    from pathlib import Path
    assert not any((Path(sm.__file__).parent / ".cache" / "sleep_mail_att" / "msg1").glob("*"))  # cleaned up


def test_oversized_and_failed_downloads_are_reported(db):
    g = AttGmail("")
    g.files = {}
    text, blocks = sm.read_attachments(g, "m2", [
        {"name": "huge.pdf", "mime": "application/pdf", "kb": 999999, "id": "x"},
        {"name": "missing.txt", "mime": "text/plain", "kb": 1, "id": "y"}])
    assert "too large" in text and "could not be" in text and blocks == []
    text, _ = sm.read_attachments(g, "m3", [{"name": f"f{i}.bin", "mime": "x/y", "kb": 1, "id": str(i)} for i in range(5)])
    assert "2 more attachment(s) were not read" in text


def test_family_reply_with_attachment_sends_blocks_to_model(db):
    g = AttGmail(_search(("m1", "Notes", "sis@x.com")))
    got = {}

    def claude(system, user, n):
        got["user"] = user
        return "Here is the summary."

    rec = []
    stats = _run(g, claude, rec)
    assert stats["family_replied"] == 1 and stats["inbound"] == 1
    assert isinstance(got["user"], list) and got["user"][0]["type"] == "text"
    assert "revise ionic bonding" in got["user"][0]["text"] and any(b["type"] == "document" for b in got["user"])
    assert "with attachment: Chemical bonding notes.pdf, plan.txt" in rec[0]


def test_inbound_counts_real_messages_only(db):
    g = FakeGmail(_search(("a", "x", "me@x.com"), ("b", "promo", "p@shop.com")))
    assert _run(g, lambda *a: "[]", [])["inbound"] == 1  # own address doesn't count


def test_cadence_defaults():
    assert sm.SLEEP_MAIL_INTERVAL_MIN == 15 and sm.ACTIVE_INTERVAL_MIN == 2


def test_tick_speeds_up_to_2_minutes_after_a_message_then_relaxes(jarvis, monkeypatch):
    import time as _t
    runs, script = [], iter([{"inbound": 1}, {"inbound": 0}, {"inbound": 0}, {"inbound": 0}])
    monkeypatch.setattr(jarvis.sleep_mail, "run_cycle", lambda **k: runs.append(1) or next(script))
    monkeypatch.setattr(jarvis, "ensure_mcp_started", lambda: None)
    monkeypatch.setitem(jarvis._mcp_tool_index, "mcp_gmail_search_emails", ("gmail", "search_emails"))
    started = datetime.now().replace(microsecond=0)
    monkeypatch.setattr(jarvis.sleep_mode, "started_at", lambda: started.isoformat())
    jarvis._sleep_mail_last_check = jarvis._sleep_mail_fast_until = None

    def tick(minutes):
        jarvis._sleep_mail_tick(started + timedelta(minutes=minutes))
        _t.sleep(0.15)

    tick(16); assert len(runs) == 1          # normal 15-min cadence: first check
    tick(17); assert len(runs) == 1          # only 1 min later, and (fast window runs from wall-clock now)
    jarvis._sleep_mail_fast_until = started + timedelta(minutes=16 + 20)  # window as set by the message
    tick(19); assert len(runs) == 2          # >= 2 min later while fast
    tick(21); assert len(runs) == 3
    tick(23); assert len(runs) == 4
    tick(60); tick(61)                       # window over: back to 15-min cadence
    assert len(runs) == 4 or len(runs) == 5  # at most one check, not one per 2 min


def test_inbound_hook_is_not_fed_and_no_body_is_read_when_it_says_it_is_disabled(db):
    g = FakeGmail(_search(("p2", "Meeting Friday", "Promo <p@shop.com>")))
    seen = []

    def hook(m):
        seen.append(m)

    hook.enabled = lambda: False
    sm.run_cycle(mcp=g, claude=lambda s, u, n: "", record=lambda t: None, since_iso=STARTED,
                 sleep_started_at=STARTED, sleep=lambda s: None, on_inbound=hook)
    assert seen == [] and "read_email" not in g.calls
