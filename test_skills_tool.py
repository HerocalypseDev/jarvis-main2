"""Managing skills by voice (2026-10-03 debug report): "cancel my billing monitoring 9 PM task" searched reminders,
queued tasks, macros and Windows Task Scheduler for 65 seconds and said there was no record, because scheduled skills
(skills/*.json) had no tool. Temp skills folder and DB only."""

import json
from datetime import datetime

import pytest


@pytest.fixture
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "s.db"))
    d = tmp_path / "skills"
    d.mkdir()
    (d / "billing_watch.json").write_text(json.dumps({
        "name": "billing_watch", "description": "Runs once a day to check Anthropic API spend and report it.",
        "instructions": "Check the spend.", "schedule": {"daily_at": "21:00"}}))
    (d / "gmail_watch.json").write_text(json.dumps({
        "name": "gmail_watch", "description": "Checks Gmail every hour for important new mail.",
        "instructions": "Check mail.", "schedule": {"every_minutes": 60}}))
    monkeypatch.setenv("JARVIS_SKILLS_DIR", str(d))
    monkeypatch.delenv("JARVIS_SKILLS_OFF", raising=False)
    import jarvis as j
    monkeypatch.setattr(j.pro, "skill_paths", lambda: [])
    monkeypatch.setattr(j.settings, "set_setting", lambda k, v: monkeypatch.setenv(k, v))
    j._skills_cache = None
    j._command_ctx.source = "voice"
    yield j
    j._command_ctx.source = None
    j._skills_cache = None


def test_cancel_my_billing_monitoring_finds_and_turns_it_off(J, monkeypatch):
    said = "Cancel my billing monitoring 9AM nine 9PM task."
    assert "skills" in J._narrowing_core(said)
    out = J._execute_tool("skills", {"action": "off", "name": "billing monitoring"}, said)
    assert out.startswith("Turned off the billing_watch skill")
    started = []
    monkeypatch.setattr(J, "_run_single_flight", lambda name, fn, skill: started.append(skill["name"]))
    monkeypatch.setattr(J, "_skill_is_due", lambda skill, now: True)
    J._start_due_skills(datetime.now())
    assert started == ["gmail_watch"]  # the billing check no longer runs
    assert "billing_watch" not in J.get_skills_context() and "gmail_watch" in J.get_skills_context()
    assert "billing_watch (daily at 21:00, off)" in J._execute_tool("skills", {"action": "list"}, "what skills do I have")
    assert J._execute_tool("skills", {"action": "on", "name": "billing"}, "turn it back on").startswith("Turned the billing_watch")


def test_delete_removes_the_users_own_skill_file(J, tmp_path):
    out = J._execute_tool("skills", {"action": "delete", "name": "billing"}, "remove the billing monitor")
    assert out.startswith("Deleted the billing_watch skill") and not (tmp_path / "skills" / "billing_watch.json").exists()
    assert [s["name"] for s in J._load_skills()] == ["gmail_watch"]


def test_unclear_or_unattended_requests_change_nothing(J, tmp_path):
    assert J._execute_tool("skills", {"action": "delete", "name": "api gmail"}, "delete the api gmail one").startswith(
        "Tool failed: More than one skill matches")
    J._command_ctx.source = "phone"
    assert "only be changed from the PC" in J._execute_tool("skills", {"action": "delete", "name": "billing"}, "x")
    assert (tmp_path / "skills" / "billing_watch.json").exists()


def test_the_billing_skill_is_gone_from_the_repo():
    """The owner asked for it to be removed (it needs an admin key personal accounts can't have, so it failed nightly)."""
    import pathlib
    assert not (pathlib.Path(__file__).parent / "skills" / "billing_watch.json").exists()


def test_a_deleted_skill_is_kept_aside_and_never_loaded_again(J, tmp_path):
    """Audit 2026-10-04: delete erased the file; a hand-written skill (often not in git) was lost for good."""
    out = J._execute_tool("skills", {"action": "delete", "name": "billing"}, "remove the billing monitor")
    kept = list((tmp_path / "skills" / ".deleted").glob("billing_watch-*.json"))
    assert kept and ".deleted" in out
    J._skills_cache = None
    assert all(s["name"] != "billing_watch" for s in J._load_skills())
