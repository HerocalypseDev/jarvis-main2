"""Second full audit (2026-10-04). One test per defect found; temp DB only, no network, no real hardware."""

import pytest


@pytest.fixture
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "a2.db"))
    import jarvis as j
    j._command_ctx.untrusted_origin = False
    yield j
    j._command_ctx.untrusted_origin = False


def test_an_email_started_task_cannot_drive_the_screen_or_whatsapp(J):
    """mcp_windows_* was blocked for untrusted runs, but the built-in screen tools (read/click/scroll/close windows)
    and the WhatsApp tools were not: an injected email could still read the screen or message someone as the owner."""
    J._command_ctx.untrusted_origin = True
    try:
        for name in ("read_screen", "click_at", "scroll_screen", "control_window",
                     "mcp_whatsapp_browser_type", "mcp_whatsapp_browser_snapshot"):
            assert J._untrusted_block(name), name
        assert J._untrusted_block("create_reminder") is None
    finally:
        J._command_ctx.untrusted_origin = False
    assert J._untrusted_block("read_screen") is None  # the owner's own commands are unaffected


def test_claims_about_closing_tabs_or_turning_off_a_skill_need_a_tool_behind_them(J):
    """The claim checker had no entry for tabs/windows, and "clear those" didn't know skills/monitoring/routines, so
    "I've closed the YouTube tab" or "I've cancelled your billing monitoring" with nothing run went unchallenged."""
    assert J._unbacked_claims("I've closed the YouTube tab.", []) == ["close that"]
    assert J._unbacked_claims("I've closed the YouTube tab.", ["browser_tabs"]) == []
    assert J._unbacked_claims("Done, I've cancelled your billing monitoring.", []) == ["clear those"]
    assert J._unbacked_claims("I've turned off that skill.", ["skills"]) == []
    assert J._unbacked_claims("I've turned off that skill.", []) == ["clear those"]
    assert J._unbacked_claims("Shall I close the other tabs?", []) == []
    assert J._unbacked_claims("You have 4 tabs open in Opera GX.", []) == []


def test_a_macro_with_a_long_name_can_be_saved_again(tmp_path):
    import sqlite3
    import threading
    import jarvis_macros as macros
    connect = lambda: sqlite3.connect(tmp_path / "m.db")  # noqa: E731
    lock = threading.Lock()
    name = "start my whole evening study routine with music and the lights and focus mode on"  # > 60 chars
    steps = [{"tool": "open_app", "input": {"app": "notepad"}}]
    assert macros.save(connect, lock, name, ["evening study time"], steps, {"open_app"}).startswith("Saved")
    again = macros.save(connect, lock, name, ["evening study time", "study time now"], steps, {"open_app"})
    assert again.startswith("Saved"), again
    assert len(macros.list_macros(connect, lock)) == 1


def _deferred_store(tmp_path):
    import sqlite3
    import threading
    import jarvis_deferred as deferred
    return deferred, deferred.Store(lambda: sqlite3.connect(tmp_path / "d.db"), threading.Lock())


def test_a_job_cut_off_by_its_own_restart_is_never_run_again(tmp_path):
    """A stale 'running' job was reset to pending with no attempt limit: "git pull then restart yourself", cut off
    by its own restart, would run (and restart Jarvis) again every 90 minutes for ever."""
    from datetime import datetime, timedelta
    deferred, store = _deferred_store(tmp_path)
    t0 = datetime(2026, 10, 4, 10, 0)
    jid, _ = deferred.schedule(store, "Run a git pull, then restart yourself", t0, now=t0 - timedelta(minutes=5))
    assert [j["id"] for j in deferred.claim_due(store, t0)] == [jid]       # claimed, then Jarvis exits mid-job
    later = t0 + timedelta(minutes=deferred.STALE_RUNNING_MIN + 1)
    assert deferred.claim_due(store, later) == []                          # not run again
    row = store.q("SELECT status, result FROM autonomy_deferred_jobs WHERE id=?", (jid,))[0]
    assert row["status"] == "done" and "restart" in row["result"]


def test_a_job_that_keeps_getting_cut_off_stops_after_its_attempts(tmp_path):
    from datetime import datetime, timedelta
    deferred, store = _deferred_store(tmp_path)
    t = datetime(2026, 10, 4, 10, 0)
    jid, _ = deferred.schedule(store, "Summarise the research folder", t, now=t - timedelta(minutes=5))
    runs = 0
    for _ in range(6):
        if deferred.claim_due(store, t):
            runs += 1
        t += timedelta(minutes=deferred.STALE_RUNNING_MIN + 1)
    assert runs == deferred.MAX_ATTEMPTS
    assert store.q("SELECT status FROM autonomy_deferred_jobs WHERE id=?", (jid,))[0]["status"] == "failed"
