"""Caretaker core (jarvis_caretaker.py): classifiers, issue store, budgets. Pure: no OS, temp DB only."""
import sqlite3
from datetime import datetime, timedelta

import pytest

import jarvis_caretaker as ct


@pytest.fixture()
def store(tmp_path):
    path = tmp_path / "c.db"
    return ct.Store(lambda: sqlite3.connect(path))


def test_storage_finding_thresholds():
    assert ct.storage_finding("C:", 70, 100) is None
    f = ct.storage_finding("C:", 91, 8.0, reclaimable_gb=3.2, grew_gb_today=4.0)
    assert f.key == "disk:C:" and f.severity == "high" and f.evidence["urgent"] is True
    assert "3.2 GB" in f.title and "4.0 GB today" in f.title
    assert ct.storage_finding("C:", 98, 1.0).severity == "critical"
    assert ct.storage_finding("C:", 86, 40).severity == "warn"


def test_process_and_crash_findings():
    assert ct.process_finding("a.exe", 20, 30, False) is None
    assert ct.process_finding("a.exe", 80, 5, False) is None
    f = ct.process_finding("Chrome.exe", 80, 25, True, pid=4)
    assert f.key == "proc:chrome.exe" and f.severity == "high" and f.evidence["in_front"] is True
    assert ct.crash_finding("opera", 2) is None
    assert "faulting module x.dll" in ct.crash_finding("opera", 5, "x.dll").title


def test_other_findings():
    assert ct.disk_health_finding("0", "Healthy") is None
    assert ct.disk_health_finding("0", "Warning").severity == "critical"
    assert ct.update_finding(1, 3) is None
    assert "9 days old" in ct.update_finding(0, 9).title
    assert ct.network_finding(True, True, True) is None
    assert ct.network_finding(True, False, True).evidence["detail"] == "dns_failing"
    assert ct.network_finding(False, False, False).evidence["detail"] == "adapter_down"
    assert ct.battery_finding(0.9) is None and ct.battery_finding(0.5) is not None


def test_self_failure_thresholds():
    assert ct.self_failure_finding("skill", "gmail_watch", "err", 1) is None
    f = ct.self_failure_finding("skill", "gmail_watch", "invalid_grant", 4)
    assert f.key == "self_skill:gmail_watch" and f.severity == "high"
    assert ct.self_failure_finding("mcp", "gmail", "down", 1) is not None  # servers/doctor/crash: 1 is enough


def test_store_ingest_reopen_and_ignore(store):
    f = ct.storage_finding("C:", 91, 8)
    assert [i["key"] for i in store.ingest([f])] == ["disk:C:"]
    store.set_status("disk:C:", "fixed")
    assert store.open_issues() == []
    assert len(store.ingest([f])) == 1  # seen again -> reopens
    store.set_status("disk:C:", "ignored")
    assert store.ingest([f]) == []      # ignored stays ignored


def test_attempts_give_up_and_remember_what_failed(store):
    store.ingest([ct.network_finding(True, False, True)])
    for i in range(ct.MAX_ATTEMPTS):
        n = store.note_attempt("network:lan", f"try {i}")
    assert n == ct.MAX_ATTEMPTS
    iss = store.get("network:lan")
    assert iss["status"] == "gave_up" and iss["tried"] == ["try 0", "try 1", "try 2"]
    assert store.open_issues() == []


def test_actions_undo_and_summary(store):
    store.ingest([ct.storage_finding("C:", 91, 8)])
    a = store.log_action("disk:C:", ct.GREEN, "clear_temp", "temp", "ok", freed_bytes=5 * 1024 ** 3)
    b = store.log_action("disk:C:", ct.YELLOW, "move_old", "x", "ok", freed_bytes=1024, undo={"restore": ["a"]})
    assert [x["id"] for x in store.recent_actions(undoable_only=True)] == [b]
    store.mark_undone(b)
    assert store.recent_actions(undoable_only=True) == []
    store.set_status("disk:C:", "fixed")
    s = store.summary_since(24)
    # the yellow action MOVED files (and was just undone): neither freed space nor still held
    assert s["fixed"] == 1 and s["actions"] == 2 and s["freed_bytes"] == 5 * 1024 ** 3 and s["held_bytes"] == 0
    assert a != b


def test_budgets(store):
    assert ct.budget_blocked(store) is None
    for _ in range(ct.MAX_ACTIONS_PER_HOUR):
        store.log_action("k", ct.GREEN, "a", "", "ok")
    assert "this hour" in ct.budget_blocked(store)


def test_daily_move_cap(store):
    store.log_action("k", ct.YELLOW, "move", "", "ok", freed_bytes=int(24 * 1024 ** 3), undo={"x": 1})
    assert ct.budget_blocked(store, move_bytes=int(2 * 1024 ** 3)) is not None
    assert ct.budget_blocked(store, move_bytes=int(0.5 * 1024 ** 3)) is None


def test_human_bytes():
    assert ct.human_bytes(512) == "512 B" and ct.human_bytes(1536) == "2 KB"
    assert ct.human_bytes(5 * 1024 ** 3) == "5.0 GB"


# --- sensors (jarvis_caretaker_probe): OS access faked, so these run on any platform ------------
import jarvis_caretaker_probe as probe  # noqa: E402


class _FakePart:
    def __init__(self, device, mountpoint):
        self.device, self.mountpoint = device, mountpoint


class _FakeUsage:
    def __init__(self, percent, free, used=0, total=100):
        self.percent, self.free, self.used, self.total = percent, free, used, total


def test_probe_storage_reads_psutil_and_tracks_growth(monkeypatch):
    fake = type("m", (), {})()
    fake.disk_partitions = lambda all=False: [_FakePart("C:\\", "C:\\")]
    fake.disk_usage = lambda mp: _FakeUsage(92.0, 8 * 1024 ** 3, used=92 * 1024 ** 3)
    monkeypatch.setitem(__import__("sys").modules, "psutil", fake)
    monkeypatch.setattr(probe, "cache_roots", lambda: [])
    probe._disk_first_today.clear()
    out = probe.probe_storage()
    assert len(out) == 1 and out[0].key == "disk:C:" and out[0].evidence["urgent"] is True
    # second look the same day with more used space reports the growth
    fake.disk_usage = lambda mp: _FakeUsage(93.0, 6 * 1024 ** 3, used=95 * 1024 ** 3)
    assert probe.probe_storage()[0].evidence["grew_gb_today"] == pytest.approx(3.0, abs=0.01)


def test_probe_storage_quiet_when_disk_is_fine(monkeypatch):
    fake = type("m", (), {})()
    fake.disk_partitions = lambda all=False: [_FakePart("C:\\", "C:\\")]
    fake.disk_usage = lambda mp: _FakeUsage(40.0, 400 * 1024 ** 3, used=40 * 1024 ** 3)
    monkeypatch.setitem(__import__("sys").modules, "psutil", fake)
    probe._disk_first_today.clear()
    assert probe.probe_storage() == []


def test_probe_crashes_groups_by_app(monkeypatch):
    monkeypatch.setattr(probe, "_ps", lambda *a, **k: "opera.exe|mod.dll\nopera.exe|mod.dll\nopera.exe|\nnote.exe|x")
    out = probe.probe_crashes()
    assert len(out) == 1 and out[0].evidence["count_today"] == 3 and out[0].evidence["module"] == "mod.dll"


def test_probe_disk_health_and_updates(monkeypatch):
    monkeypatch.setattr(probe, "_ps", lambda *a, **k: "0|Healthy\n1|Warning")
    out = probe.probe_disk_health()
    assert [f.evidence["drive"] for f in out] == ["1"] and out[0].severity == "critical"
    monkeypatch.setattr(probe, "_ps", lambda s, **k: "3" if "Id=20" in s else "9")
    u = probe.probe_updates()[0]
    assert u.evidence["failed_count"] == 3 and u.evidence["defs_age_days"] == 9


def test_probe_self_finds_a_failing_skill_streak(tmp_path):
    db = tmp_path / "m.db"

    def connect():
        c = sqlite3.connect(db)
        c.execute("CREATE TABLE IF NOT EXISTS dashboard_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                  "source TEXT, transcript TEXT, status TEXT, reply TEXT)")
        return c

    c = connect()
    # oldest first: an old success, then the two most recent runs failed -> a live streak of 2
    for status, reply in [("done", "ok"), ("failed", "invalid_grant"), ("failed", "invalid_grant")]:
        c.execute("INSERT INTO dashboard_sessions (source,transcript,status,reply) VALUES "
                  "('scheduled','gmail_watch: checking mail',?,?)", (status, reply))
    c.execute("INSERT INTO dashboard_sessions (source,transcript,status,reply) VALUES "
              "('scheduled','morning_briefing: hi','done','ok')")
    c.commit(); c.close()
    out = probe.probe_self(connect)
    # newest first: 2 failures then a success closes the streak, so exactly one finding
    assert [f.key for f in out] == ["self_skill:gmail_watch"]
    assert out[0].evidence["count"] == 2 and "invalid_grant" in out[0].title


def test_probe_self_reports_down_servers_and_doctor_problems(tmp_path):
    out = probe.probe_self(None, mcp_failed={"gmail": {}},
                           doctor_problems=[{"name": "Google sign-in", "detail": "expires soon", "fix": "re-auth"},
                                            {"name": "Tool arguments", "detail": "dev note", "quiet": True}])
    keys = [f.key for f in out]
    assert "self_mcp:gmail" in keys and "self_doctor:google sign-in" in keys
    assert not any("tool arguments" in k for k in keys)   # quiet developer notes are not the owner's problems
    assert next(f for f in out if f.category == "self_doctor").evidence["fix"] == "re-auth"


def test_run_all_isolates_a_broken_sensor(monkeypatch):
    monkeypatch.setattr(probe, "probe_storage", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(probe, "probe_network", lambda: [ct.network_finding(True, False, True)])
    out = probe.run_all(skip={"processes", "crashes", "disk_health", "updates", "battery", "self"})
    assert [f.key for f in out] == ["network:lan"]


def test_probe_self_ignores_a_skill_whose_latest_run_succeeded(tmp_path):
    """A skill that failed twice but worked on its newest run is not a live problem."""
    db = tmp_path / "m2.db"

    def connect():
        c = sqlite3.connect(db)
        c.execute("CREATE TABLE IF NOT EXISTS dashboard_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                  "source TEXT, transcript TEXT, status TEXT, reply TEXT)")
        return c

    c = connect()
    for status in ("failed", "failed", "done"):   # oldest first -> newest is the success
        c.execute("INSERT INTO dashboard_sessions (source,transcript,status,reply) VALUES "
                  "('scheduled','gmail_watch: checking mail',?,'x')", (status,))
    c.commit(); c.close()
    assert probe.probe_self(connect) == []


# --- wiring in jarvis.py: tool, dashboard feature, scheduler step --------------------------------
@pytest.fixture()
def jv(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "jv.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import jarvis as j
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    monkeypatch.setattr(j, "_caretaker_store", ct.Store(j._memory_db_connect))
    monkeypatch.setattr(j, "_caretaker_state", {"check": 0.0, "running": False, "last": None, "announced": set()})
    monkeypatch.setattr(j.doctor, "problems", lambda *a, **k: [])
    monkeypatch.setattr(j, "_foreground_window", lambda: {"app": "code.exe"})
    return j


def test_caretaker_is_registered_as_a_tool_and_a_dashboard_page(jv):
    assert "caretaker" in jv._BATCH_TOOL_HANDLERS
    assert any(t["name"] == "caretaker" for t in jv.BATCH_TOOLS)
    assert "caretaker" in jv._FEATURE_PROVIDERS
    assert "caretaker" in jv._dashboard_pages()          # so "what's wrong with my PC" can read it
    assert any(name == "caretaker" for name, _, _ in jv._scheduler_steps(__import__("datetime").datetime.now()))


def test_tool_status_lists_findings_and_scan_is_quiet_when_clean(jv, monkeypatch):
    monkeypatch.setattr(jv.caretaker_probe, "run_all", lambda **k: [])
    assert "nothing wrong" in jv._caretaker_tool({"action": "scan"}).lower()
    monkeypatch.setattr(jv.caretaker_probe, "run_all",
                        lambda **k: [ct.storage_finding("C:", 93, 6.0, reclaimable_gb=3.0)])
    assert "1 open issue" in jv._caretaker_tool({"action": "scan"})
    out = jv._caretaker_tool({"action": "status"})
    assert "HIGH" in out and "disk:C:" in out and "93% full" in out


def test_tool_ignore_needs_a_real_key_and_then_stops_tracking(jv, monkeypatch):
    monkeypatch.setattr(jv.caretaker_probe, "run_all",
                        lambda **k: [ct.storage_finding("C:", 93, 6.0)])
    jv._caretaker_tool({"action": "scan"})
    assert jv._caretaker_tool({"action": "ignore", "key": ""}).startswith("Tool failed")
    assert jv._caretaker_tool({"action": "ignore", "key": "disk:Z:"}).startswith("Tool failed")
    assert "Leaving disk:C:" in jv._caretaker_tool({"action": "ignore", "key": "disk:C:"})
    assert jv._caretaker_store.open_issues() == []
    assert jv._caretaker_tool({"action": "status"}).startswith("Nothing wrong")


def test_only_critical_findings_are_spoken(jv, monkeypatch):
    """The owner's quiet rule: a warning is read on the page, only an unmissable problem interrupts."""
    said = []
    monkeypatch.setattr(jv, "queue_or_deliver_notification",
                        lambda text, **kw: said.append((text, kw)))
    monkeypatch.setattr(jv.caretaker_probe, "run_all",
                        lambda **k: [ct.storage_finding("C:", 91, 8.0),
                                     ct.disk_health_finding("0", "Warning")])
    jv._caretaker_run()
    assert len(said) == 1 and "disk reports" in said[0][0] and said[0][1]["important"] is True
    jv._caretaker_run()                       # a second pass must not repeat it
    assert len(said) == 1


def test_a_failing_sensor_never_breaks_the_tick(jv, monkeypatch):
    monkeypatch.setattr(jv.caretaker_probe, "run_all", lambda **k: (_ for _ in ()).throw(RuntimeError("boom")))
    jv._caretaker_run()                        # must not raise
    assert jv._caretaker_state["running"] is False


def test_caretaker_can_be_switched_off(jv, monkeypatch):
    monkeypatch.setenv("JARVIS_CARETAKER", "0")
    assert jv.caretaker_enabled() is False
    monkeypatch.setattr(jv.caretaker_probe, "run_all", lambda **k: [ct.storage_finding("C:", 95, 2.0)])
    jv._caretaker_tick()
    assert jv._caretaker_state["last"] is None   # the tick did nothing at all


def test_feature_route_get_scan_and_ignore(jv, monkeypatch):
    monkeypatch.setattr(jv.caretaker_probe, "run_all", lambda **k: [ct.storage_finding("C:", 93, 6.0)])
    assert len(jv._feature_caretaker("scan", {})["issues"]) == 1
    rep = jv._feature_caretaker("get", {})
    assert rep["enabled"] is True and rep["issues"][0]["key"] == "disk:C:" and "summary" in rep
    assert jv._feature_caretaker("ignore", {})["ok"] is False
    assert jv._feature_caretaker("ignore", {"key": "disk:C:"})["issues"] == []
    assert jv._feature_caretaker("nonsense", {}) is None


def test_issues_jarvis_gave_up_on_stay_visible(store):
    """Found in the headless check: a gave_up issue vanished from the page, but it's the one that needs the owner."""
    store.ingest([ct.network_finding(True, False, True), ct.storage_finding("C:", 91, 8)])
    for i in range(ct.MAX_ATTEMPTS):
        store.note_attempt("network:lan", f"try {i}")
    assert [i["key"] for i in store.open_issues()] == ["disk:C:"]          # no more work on it
    vis = store.visible_issues()
    assert [i["key"] for i in vis] == ["network:lan", "disk:C:"]            # but shown, first
    assert vis[0]["status"] == "gave_up" and vis[0]["attempts"] == ct.MAX_ATTEMPTS


def test_report_and_tool_show_gave_up_issues(jv, monkeypatch):
    monkeypatch.setattr(jv.caretaker_probe, "run_all", lambda **k: [ct.network_finding(True, False, True)])
    jv._caretaker_tool({"action": "scan"})
    for i in range(ct.MAX_ATTEMPTS):
        jv._caretaker_store.note_attempt("network:lan", f"try {i}")
    assert jv.caretaker_report()["issues"][0]["status"] == "gave_up"
    assert "gave up after 3 tries" in jv._caretaker_tool({"action": "status"})


def test_failure_title_has_one_full_stop():
    f = ct.self_failure_finding("skill", "x", "Token has been expired or revoked.", 3)
    assert f.title.endswith("revoked.") and ".." not in f.title


# --- resolving, retry window (phase 2) ------------------------------------------------------------
def test_resolve_missing_closes_only_what_its_sensor_stopped_reporting(store):
    store.ingest([ct.storage_finding("C:", 91, 8), ct.network_finding(True, False, True),
                  ct.self_failure_finding("skill", "x", "e", 3)])
    store.log_action("disk:C:", ct.GREEN, "clear_caches", "", "ok")          # Jarvis acted on the disk issue
    # storage and network ran fine and now report nothing; the "self" sensor did NOT run this time
    closed = store.resolve_missing(set(), {"storage", "network"})
    assert sorted(closed) == ["disk:C:", "network:lan"]
    assert store.get("disk:C:")["status"] == "fixed"        # Jarvis acted on it
    assert store.get("network:lan")["status"] == "resolved"  # went away by itself
    assert store.get("self_skill:x")["status"] == "open"    # its sensor didn't run: left alone


def test_resolve_missing_leaves_ignored_and_still_reported_issues(store):
    store.ingest([ct.storage_finding("C:", 91, 8), ct.network_finding(True, False, True)])
    store.set_status("network:lan", "ignored")
    assert store.resolve_missing({"disk:C:"}, {"storage", "network"}) == []
    assert store.get("disk:C:")["status"] == "open" and store.get("network:lan")["status"] == "ignored"


def test_gave_up_stays_gave_up_until_the_retry_window(store):
    f = ct.network_finding(True, False, True)
    store.ingest([f])
    for i in range(ct.MAX_ATTEMPTS):
        store.note_attempt("network:lan", f"t{i}")
    store.ingest([f])                                         # seen again soon: still the same problem
    assert store.get("network:lan")["status"] == "gave_up"
    # pretend it gave up a day and an hour ago -> a fresh start
    old = (datetime.now() - timedelta(hours=ct.GAVE_UP_RETRY_HOURS + 1)).isoformat(timespec="seconds")
    c = store._conn(); c.execute("UPDATE caretaker_issues SET resolved_at=? WHERE key='network:lan'", (old,)); c.commit()
    store.ingest([f])
    iss = store.get("network:lan")
    assert iss["status"] == "open" and iss["attempts"] == 0 and iss["tried"] == []


# --- the fix path through jarvis.py ---------------------------------------------------------------
def _env_for(jv, tmp_path, free):
    home = tmp_path / "home"
    (home / "Downloads").mkdir(parents=True, exist_ok=True)
    env = jv.caretaker_fix.StorageEnv(cache_roots=[tmp_path / "cache"], bin_dirs=[], downloads=home / "Downloads",
                                      holding_root=tmp_path / "hold", home=home, free_fraction=lambda: free[0])
    return env, home


def _old_file(path, size=100, days=9):
    import os, time
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    t = time.time() - days * 86400
    os.utime(path, (t, t))
    return path


def test_a_storage_issue_is_fixed_on_its_own_and_then_closed(jv, monkeypatch, tmp_path):
    free = [0.05]
    env, home = _env_for(jv, tmp_path, free)
    f = _old_file(tmp_path / "cache" / "junk.bin", 5000)
    orig = jv.caretaker_fix.clear_caches
    monkeypatch.setattr(jv.caretaker_fix, "clear_caches", lambda *a, **k: (free.__setitem__(0, 0.30), orig(*a, **k))[1])
    monkeypatch.setattr(jv, "_caretaker_storage_env", lambda mount: env)
    monkeypatch.setattr(jv.autonomy, "hard_disabled", lambda: False)
    monkeypatch.setattr(jv.caretaker_probe, "run_all",
                        lambda **k: (k["report"].__setitem__("ok", {"storage"}) or
                                     [ct.storage_finding("C:", 95, 5.0)]))
    jv._caretaker_run()
    assert not f.exists()
    assert jv._caretaker_store.get("disk:C:")["status"] == "fixed"
    # next scan: the disk is fine, nothing reported -> stays closed, "fixed today" counts it
    monkeypatch.setattr(jv.caretaker_probe, "run_all",
                        lambda **k: (k["report"].__setitem__("ok", {"storage"}) or []))
    jv._caretaker_run()
    assert jv._caretaker_store.summary_since(24)["fixed"] == 1 and jv._caretaker_store.open_issues() == []


def test_nothing_is_touched_in_safe_mode_or_with_fixes_switched_off(jv, monkeypatch, tmp_path):
    env, _ = _env_for(jv, tmp_path, [0.05])
    f = _old_file(tmp_path / "cache" / "junk.bin")
    monkeypatch.setattr(jv, "_caretaker_storage_env", lambda mount: env)
    monkeypatch.setattr(jv.caretaker_probe, "run_all",
                        lambda **k: [ct.storage_finding("C:", 95, 5.0)])
    monkeypatch.setenv("JARVIS_SAFE_MODE", "1")
    jv._caretaker_run()
    assert f.exists() and "safe mode" in jv._caretaker_why_not_act()
    monkeypatch.delenv("JARVIS_SAFE_MODE")
    monkeypatch.setenv("JARVIS_CARETAKER_ACT", "0")
    jv._caretaker_run()
    assert f.exists() and "switched off" in jv._caretaker_why_not_act()
    assert jv._caretaker_tool({"action": "fix"}).startswith("Not fixing anything")


def test_it_says_so_once_when_nothing_safe_is_left(jv, monkeypatch, tmp_path):
    env, _ = _env_for(jv, tmp_path, [0.05])                  # nothing to clean, nothing to hold
    said = []
    monkeypatch.setattr(jv, "queue_or_deliver_notification", lambda t, **kw: said.append((t, kw)))
    monkeypatch.setattr(jv, "_caretaker_storage_env", lambda mount: env)
    monkeypatch.setattr(jv.autonomy, "hard_disabled", lambda: False)
    monkeypatch.setattr(jv.caretaker_probe, "run_all", lambda **k: [ct.storage_finding("C:", 95, 5.0)])
    for _ in range(6):
        jv._caretaker_run()
    assert jv._caretaker_store.get("disk:C:")["status"] == "gave_up"
    msgs = [t for t, kw in said if "nothing left I can safely clear" in t]
    assert len(msgs) == 1 and said[-1][1]["important"] is True


def test_undo_tool_restores_held_files_and_marks_it_undone(jv, tmp_path, monkeypatch):
    monkeypatch.setattr(jv, "_caretaker_holding_root", lambda: tmp_path / "hold")
    env, home = _env_for(jv, tmp_path, [0.05])
    inst = _old_file(home / "Downloads" / "setup.iso", 60 * 1024 * 1024, days=90)
    r = jv.caretaker_fix.hold([str(inst)], env.holding_root, home=home)
    aid = jv._caretaker_store.log_action("disk:C:", ct.YELLOW, "hold_files", "x", "held", 5,
                                         undo={"kind": "hold", "manifest": r["manifest"]})
    assert "setup.iso" in jv._caretaker_tool({"action": "holding"})
    assert not inst.exists()
    assert "Put 1 file" in jv._caretaker_tool({"action": "undo", "id": aid}) and inst.exists()
    assert jv._caretaker_tool({"action": "undo"}).startswith("Tool failed")        # nothing left to undo
    assert jv._caretaker_tool({"action": "undo", "id": "abc"}).startswith("Tool failed")


def test_the_caretaker_tool_is_blocked_for_untrusted_runs(jv):
    assert "caretaker" in jv._UNTRUSTED_BLOCKED_TOOLS and "caretaker" in jv._TAINT_BLOCKED_TOOLS


def test_tool_narrowing_offers_the_caretaker_for_disk_and_cleanup_wording(jv):
    for text in ("my disk is almost full", "clean up my laptop storage", "what's wrong with my PC",
                 "undo the cleanup", "what did you fix today"):
        assert jv._CARETAKER_RE.search(text), text
    for text in ("play some music", "what's the weather", "open notepad"):
        assert not jv._CARETAKER_RE.search(text), text


def test_daily_housekeeping_removes_old_holding_batches_once(jv, monkeypatch, tmp_path):
    from datetime import datetime as _dt, timedelta as _td
    monkeypatch.setattr(jv, "_caretaker_holding_root", lambda: tmp_path / "hold")
    env, home = _env_for(jv, tmp_path, [0.05])
    inst = _old_file(home / "Downloads" / "a.zip", 1000, days=90)
    jv.caretaker_fix.hold([str(inst)], tmp_path / "hold", home=home, now=_dt.now() - _td(days=ct.HOLDING_DAYS + 2))
    monkeypatch.setattr(jv, "queue_or_deliver_notification", lambda *a, **k: None)
    jv._caretaker_housekeeping()
    assert not list((tmp_path / "hold").iterdir())
    acts = jv._caretaker_store.recent_actions()
    assert [a["action"] for a in acts] == ["purge_holding"]
    jv._caretaker_housekeeping()                              # same day: does nothing more
    assert len(jv._caretaker_store.recent_actions()) == 1
