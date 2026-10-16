"""Self-scheduling (owner 2026-10-16, "All but email"): Jarvis's own runs may create jobs, background agents,
watches, skills and campaign steps; a run that came from or read someone else's text may not.
Run: python -m pytest test_self_scheduling.py -v"""
import json

import pytest


@pytest.fixture()
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("JARVIS_SKILLS_DIR", str(tmp_path / "skills"))
    import jarvis
    monkeypatch.setattr(jarvis, "_log_action_audit", lambda *a, **k: None)
    ctx = jarvis._command_ctx
    for k in ("autonomous", "untrusted_origin", "outside_text_seen"):
        monkeypatch.setattr(ctx, k, False, raising=False)
    monkeypatch.setattr(ctx, "source", None, raising=False)
    monkeypatch.setattr(ctx, "taint_watch", True, raising=False)  # what a scheduled skill / queued task run looks like
    return jarvis


def _run(J, tool, inp):
    return J._execute_tool_impl(tool, inp, "scheduled run")


def _agent(name):
    return {"action": "create", "name": name, "trigger_type": "interval", "trigger_config": {"every_min": 30},
            "steps": [{"tool": "create_reminder", "input": {"text": "drink water", "due_in_minutes": 1}}]}


def _watch(name):
    return {"action": "create", "name": name, "what": "my Google Calendar", "rule": "an exam within 3 days",
            "announce": "Say which exam and when", "schedule": "every day at 8am"}


def test_own_unattended_run_can_schedule_everything(J, tmp_path):
    job = _run(J, "schedule_jarvis_task", {"instruction": "Run a speed test", "due_in_minutes": 30})
    assert "Scheduled job #" in job
    assert J.deferred.list_jobs(J._deferred_store)[0]["origin"] == "jarvis"
    assert "Queued" in _run(J, "queue_task", {"description": "tidy", "instructions": "tidy downloads"})
    assert "Reminder set" in _run(J, "create_reminder", {"text": "stretch", "due_in_minutes": 20})
    assert "Saved skill" in _run(J, "save_skill", {"name": "self_made", "description": "d", "instructions": "i",
                                                   "schedule": {"every_minutes": 60}})
    assert json.loads((tmp_path / "skills" / "self_made.json").read_text())["schedule"] == {"every_minutes": 60}
    agent = _run(J, "background_agents", _agent("water"))
    assert "Refused" not in agent and "only be changed" not in agent, agent
    watch = _run(J, "watches", _watch("exams"))
    assert "can't be made" not in watch, watch
    project = _run(J, "autonomy", {"action": "add_project", "name": "Thesis", "goal": "finish it"})
    assert "only accepted" not in project, project


@pytest.mark.parametrize("flag", ["untrusted_origin", "outside_text_seen"])
def test_runs_from_or_after_outside_text_still_cannot(J, flag):
    setattr(J._command_ctx, flag, True)
    assert _run(J, "schedule_jarvis_task", {"instruction": "x", "due_in_minutes": 5}).startswith("Refused")
    assert _run(J, "background_agents", _agent("evil")).startswith("Refused")
    assert "can't be made" in _run(J, "watches", _watch("evil"))
    assert _run(J, "save_skill", {"name": "evil", "description": "d", "instructions": "i"}).startswith("Refused")
    assert "only accepted" in J.autonomy.handle_tool({"action": "add_project", "name": "x"}, None, self_run=False)
    assert J.deferred.list_jobs(J._deferred_store) == []


def test_card_approval_stays_with_the_owner(J):
    assert "only accepted" in J.autonomy.handle_tool({"action": "approve", "id": 1}, None, self_run=True)


def test_self_made_jobs_are_capped(J, monkeypatch):
    monkeypatch.setattr(J, "SELF_JOBS_MAX_PENDING", 2)
    for i in range(2):
        assert "Scheduled job #" in _run(J, "schedule_jarvis_task",
                                         {"instruction": f"Job number {i} totally different words {'x' * i}",
                                          "due_in_minutes": 30 + 40 * i})
    assert "already waiting" in _run(J, "schedule_jarvis_task", {"instruction": "one more", "due_in_minutes": 200})


def test_owner_request_keeps_origin_user(J):
    J._command_ctx.source = "voice"
    _run(J, "schedule_jarvis_task", {"instruction": "Run the tests", "due_in_minutes": 10})
    assert J.deferred.list_jobs(J._deferred_store)[0]["origin"] == "user"
