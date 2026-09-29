"""Full-codebase audit (2026-09-29): scheduler reliability. Temp DBs only."""
import threading
import time
from datetime import datetime, timedelta

import pytest


def test_queued_task_that_uses_the_task_queue_does_not_deadlock(monkeypatch, tmp_path):
    """The queued task's agent loop ran while tick() held the task queue's non-reentrant lock, so a task
    whose agent listed/cancelled/planned the queue froze the scheduler thread (and every reminder) forever."""
    import jarvis_task_scheduler as ts
    monkeypatch.setattr(ts, "_db_path", lambda: tmp_path / "q.db", raising=False)
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "q.db"))
    ts._initialized = False if hasattr(ts, "_initialized") else None
    now = datetime.now()
    ts.queue_task("tidy notes", priority="normal", instructions="list my queue")
    with ts._db_lock:
        conn = ts._connect()
        conn.execute("UPDATE task_queue SET status='scheduled', scheduled_start=?, scheduled_end=?",
                     ((now - timedelta(minutes=1)).isoformat(timespec="seconds"),
                      (now + timedelta(minutes=30)).isoformat(timespec="seconds")))
        conn.commit()
        conn.close()
    seen = []

    def agent(description, instructions):
        seen.append(ts.list_task_queue())          # needs _db_lock: deadlocked before the fix

    t = threading.Thread(target=ts.tick, args=(now, agent, None), daemon=True)
    t.start()
    t.join(10)
    assert not t.is_alive(), "task scheduler deadlocked"
    assert seen and "tidy notes" in seen[0]
    assert "done" in ts.list_task_queue(include_done=True).lower()


@pytest.fixture
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "j.db"))
    import jarvis as j
    return j


def test_a_failing_scheduler_step_no_longer_skips_reminders(J, monkeypatch):
    ran = []
    monkeypatch.setattr(J, "_load_skills", lambda: (_ for _ in ()).throw(RuntimeError("bad skill file")))
    monkeypatch.setattr(J, "_check_due_reminders", lambda now: ran.append("reminders"))
    monkeypatch.setattr(J, "_deferred_tick", lambda now: ran.append("deferred"))
    monkeypatch.setattr(J, "_digest_tick", lambda: ran.append("digest"))
    for name in ("_check_background_tasks", "_retry_failed_mcp_servers", "_sleep_mail_tick", "_autonomy_tick_battery_aware",
                 "_chief_tick", "_agents_tick", "_daily_plan_tick"):
        monkeypatch.setattr(J, name, lambda now: None)
    for name in ("_battery_tick", "_netscan_tick", "_meeting_tick", "_cascade_tick", "_kg_sync_tick"):
        monkeypatch.setattr(J, name, lambda: None)
    monkeypatch.setattr(J, "_run_single_flight", lambda *a, **k: True)
    monkeypatch.setattr(J.focus_mode, "tick", lambda *a: None)
    monkeypatch.setattr(J.roblox, "tick", lambda *a: None)
    J._scheduler_tick(datetime.now())
    assert ran == ["reminders", "deferred", "digest"]


def test_scheduled_skills_run_off_thread_and_one_at_a_time(J, monkeypatch):
    gate = threading.Event()
    runs = []
    monkeypatch.setattr(J, "_load_skills", lambda: [{"name": "slow", "instructions": "x", "schedule": {"every_minutes": 1}}])
    monkeypatch.setattr(J, "_skill_is_due", lambda skill, now: True)
    monkeypatch.setattr(J, "_run_scheduled_skill", lambda skill: runs.append(skill["name"]) or gate.wait(5))
    t0 = time.monotonic()
    J._start_due_skills(datetime.now())
    J._start_due_skills(datetime.now())              # still running: must not start a second copy
    assert time.monotonic() - t0 < 1.0               # the scheduler thread was not held up
    time.sleep(0.2)
    assert runs == ["slow"]
    gate.set()
    for _ in range(50):
        if "skill:slow" not in J._single_flight_running:
            break
        time.sleep(0.05)
    J._start_due_skills(datetime.now())
    time.sleep(0.2)
    assert runs == ["slow", "slow"]
    gate.set()


def test_bad_numeric_settings_never_stop_jarvis_starting(monkeypatch):
    """Settings accepts any number, but several settings were parsed with int() at import: saving "12.5"
    (or a typo) in .env made the next start crash before the dashboard even existed."""
    import importlib
    import jarvis_env
    from jarvis_env import env_float, env_int
    monkeypatch.setenv("X_INT", "12.5")
    monkeypatch.setenv("X_BAD", "twelve")
    monkeypatch.setenv("X_F", "0.25")
    assert env_int("X_INT", 40) == 12 and env_int("X_BAD", 40) == 40 and env_int("X_UNSET", 7) == 7
    assert env_float("X_F", 1.0) == 0.25 and env_float("X_BAD", 1.5) == 1.5
    monkeypatch.setenv("JARVIS_SLEEP_GOAL_HOURS", "eight")
    monkeypatch.setenv("JARVIS_DEEPGRAM_STT_TIMEOUT_S", "")
    monkeypatch.setenv("JARVIS_SLEEP_MAIL_MAX_REPLIES", "6.0")
    import jarvis_sleep_mode, jarvis_stt_deepgram, jarvis_sleep_mail
    for m in (jarvis_sleep_mode, jarvis_stt_deepgram, jarvis_sleep_mail):
        importlib.reload(m)
    assert jarvis_sleep_mode.SLEEP_GOAL_HOURS == 8 and jarvis_sleep_mail.MAX_REPLIES_PER_SENDER == 6
    assert jarvis_stt_deepgram.DEEPGRAM_STT_TIMEOUT_S == 8.0
    monkeypatch.undo()
    for m in (jarvis_sleep_mode, jarvis_stt_deepgram, jarvis_sleep_mail):
        importlib.reload(m)
