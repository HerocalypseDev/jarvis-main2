"""Caretaker phase 4: the Windows playbooks (priority of a CPU hog, network, crashing apps). The OS is faked
everywhere: a psutil-shaped object, a command runner and a re-check callable. Nothing here touches a real process."""
from datetime import datetime, timedelta

import pytest

import jarvis_caretaker as ct
import jarvis_caretaker_windows as cw


# --- fakes ---------------------------------------------------------------------------------------
class _Err(Exception):
    pass


class _Proc:
    def __init__(self, pid, name, user="me", nice=cw.NORMAL, fail=False):
        self.pid, self._name, self._user, self._nice, self._fail = pid, name, user, nice, fail
        self.info = {"name": name, "pid": pid}

    def username(self):
        return "PC\\" + self._user

    def name(self):
        return self._name

    def nice(self, value=None):
        if value is None:
            return self._nice
        if self._fail:
            raise _Err("denied")
        self._nice = value


class _PS:
    Error = _Err
    BELOW_NORMAL_PRIORITY_CLASS = cw.BELOW_NORMAL
    IDLE_PRIORITY_CLASS = cw.IDLE

    def __init__(self, procs):
        self.procs = procs

    def process_iter(self, attrs=None):
        return list(self.procs)

    def Process(self, pid=None):
        if pid is None:
            return _Proc(0, "python.exe")
        for p in self.procs:
            if p.pid == pid:
                return p
        raise _Err("gone")


# --- priority ------------------------------------------------------------------------------------
def test_only_my_own_instances_of_that_program_are_lowered():
    a, b = _Proc(1, "Handbrake.exe"), _Proc(2, "Handbrake.exe")
    other_user, other_prog = _Proc(3, "Handbrake.exe", user="someone"), _Proc(4, "chrome.exe")
    already = _Proc(5, "Handbrake.exe", nice=cw.BELOW_NORMAL)
    r = cw.lower_priority("handbrake.exe", psutil_mod=_PS([a, b, other_user, other_prog, already]), me="me")
    assert [c["pid"] for c in r["changed"]] == [1, 2] and all(c["prev"] == cw.NORMAL for c in r["changed"])
    assert a.nice() == cw.BELOW_NORMAL and b.nice() == cw.BELOW_NORMAL
    assert other_user.nice() == cw.NORMAL and other_prog.nice() == cw.NORMAL      # nobody else's is touched
    assert r["skipped"] == 2 and r["protected"] is False


@pytest.mark.parametrize("name", ["svchost.exe", "MsMpEng.exe", "explorer.exe", "python.exe", "dwm.exe", "System"])
def test_windows_security_and_jarvis_processes_are_never_touched(name):
    p = _Proc(9, name)
    r = cw.lower_priority(name, psutil_mod=_PS([p]), me="me")
    assert r["changed"] == [] and r["protected"] is True and p.nice() == cw.NORMAL


def test_a_process_that_refuses_is_skipped_not_fatal():
    r = cw.lower_priority("x.exe", psutil_mod=_PS([_Proc(1, "x.exe", fail=True), _Proc(2, "x.exe")]), me="me")
    assert [c["pid"] for c in r["changed"]] == [2] and r["skipped"] == 1


def test_undo_puts_the_priority_back_only_for_the_same_program():
    p = _Proc(1, "Handbrake.exe")
    ps = _PS([p])
    r = cw.lower_priority("Handbrake.exe", psutil_mod=ps, me="me")
    info = {"kind": "priority", "name": "Handbrake.exe", "items": r["changed"]}
    assert cw.restore_priority(info, psutil_mod=ps).startswith("Put back") and p.nice() == cw.NORMAL
    # the pid now belongs to another program: leave it alone
    reused = _Proc(1, "chrome.exe", nice=cw.BELOW_NORMAL)
    out = cw.restore_priority(info, psutil_mod=_PS([reused]))
    assert out.startswith("Nothing to put back") and reused.nice() == cw.BELOW_NORMAL


# --- network -------------------------------------------------------------------------------------
class _Runner:
    def __init__(self, replies=None):
        self.calls, self.replies = [], replies or {}

    def __call__(self, cmd, timeout=25):
        self.calls.append(cmd)
        for key, val in self.replies.items():
            if key in " ".join(cmd):
                return val
        return 0, ""


NO_SLEEP = dict(sleep=lambda s: None)


def test_a_blip_that_clears_by_itself_touches_nothing():
    run = _Runner()
    r = cw.fix_network("dns_failing", recheck=lambda: True, runner=run, **NO_SLEEP)
    assert r["cleared"] and run.calls == [] and "by itself" in r["steps"][0]


def test_dns_trouble_flushes_the_cache_and_checks_again():
    checks = iter([False, True])
    run = _Runner()
    r = cw.fix_network("dns_failing", recheck=lambda: next(checks), runner=run, **NO_SLEEP)
    assert r["cleared"] and run.calls == [["ipconfig", "/flushdns"]] and r["steps"] == ["flushed the DNS cache"]


def test_a_flush_windows_refuses_is_left_for_the_admin_helper():
    run = _Runner({"flushdns": (1, "Could not flush the DNS Resolver Cache: Access is denied")})
    r = cw.fix_network("dns_failing", recheck=lambda: False, runner=run, **NO_SLEEP)
    assert not r["cleared"] and r["needs_admin"] == ["flush_dns"]


def test_a_lost_router_reconnects_the_wifi_profile_as_one_argument():
    show = "    Name : Wi-Fi\n    Profile                : Home Net 5G\n    State : connected\n"
    run = _Runner({"show interfaces": (0, show)})
    checks = iter([False, True])
    r = cw.fix_network("gateway_unreachable", recheck=lambda: next(checks), runner=run, **NO_SLEEP)
    assert r["cleared"] and r["steps"] == ["reconnected to the Wi-Fi network 'Home Net 5G'"]
    assert ["netsh", "wlan", "disconnect"] in run.calls
    assert ["netsh", "wlan", "connect", "name=Home Net 5G"] in run.calls      # a list, never a shell string


def test_a_wired_or_odd_profile_name_needs_the_admin_helper_instead():
    wired = _Runner({"show interfaces": (0, "There is 1 interface on the system:\n  Name : Ethernet\n")})
    assert cw.fix_network("adapter_down", recheck=lambda: False, runner=wired, **NO_SLEEP)["needs_admin"] == ["restart_adapter"]
    evil = _Runner({"show interfaces": (0, '    Profile : x" & shutdown /s\n')})
    assert cw.wlan_profile(evil) == ""      # a quote in the name: nothing is passed on


# --- crashing apps -------------------------------------------------------------------------------
def test_crash_advice_points_at_the_graphics_driver_when_it_is_blamed():
    assert "graphics driver" in ct.crash_advice("nvwgf2umx.dll")
    assert "reinstall" in ct.crash_advice("ntdll.dll") and "reinstall" in ct.crash_advice("")
    f = ct.crash_finding("opera.exe", 4, "d3d11.dll")
    assert "graphics driver" in f.evidence["advice"]
    assert "can't repair" in ct.disk_health_finding("0", "Warning").evidence["advice"]


def test_known_apps_have_cache_folders_unknown_apps_do_not(tmp_path):
    local, roam = tmp_path / "L", tmp_path / "R"
    op = local / "Opera Software" / "Opera GX Stable" / "Cache"
    op.mkdir(parents=True)
    (roam / "discord" / "Cache").mkdir(parents=True)
    env = {"LOCALAPPDATA": str(local), "APPDATA": str(roam)}
    assert cw.app_cache_dirs("opera.exe", env) == [op]
    assert [p.name for p in cw.app_cache_dirs("Discord.exe", env)] == ["Cache"]
    assert cw.app_cache_dirs("photoshop.exe", env) == []


def test_a_running_app_keeps_its_cache(tmp_path):
    local = tmp_path / "L"
    cache = local / "Google" / "Chrome" / "User Data" / "Default" / "Cache"
    cache.mkdir(parents=True)
    f = cache / "data_1"
    f.write_bytes(b"x" * 100)
    env = {"LOCALAPPDATA": str(local)}
    running = _PS([_Proc(1, "chrome.exe")])
    r = cw.clear_app_cache("chrome.exe", psutil_mod=running, env=env)
    assert r["why_not"] == "it is running right now" and f.exists()
    r = cw.clear_app_cache("chrome.exe", psutil_mod=_PS([]), env=env)
    assert r["why_not"] is None and r["freed"] == 100 and not f.exists()
    assert cw.clear_app_cache("photoshop.exe", psutil_mod=_PS([]), env=env)["why_not"] == "no cache folder I know of"


# --- wiring in jarvis.py -------------------------------------------------------------------------
@pytest.fixture()
def jv(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "jv.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import jarvis as j
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    monkeypatch.setattr(j, "_caretaker_store", ct.Store(j._memory_db_connect))
    monkeypatch.setattr(j, "_caretaker_state", {"check": 0.0, "running": False, "last": None, "announced": set()})
    monkeypatch.setattr(j.doctor, "problems", lambda *a, **k: [])
    monkeypatch.setattr(j.autonomy, "hard_disabled", lambda: False)
    monkeypatch.setattr(j, "_foreground_window", lambda: {"app": "code.exe"})
    said = []
    monkeypatch.setattr(j, "queue_or_deliver_notification", lambda t, **kw: said.append((t, kw)))
    monkeypatch.setattr(j, "alert_owner", lambda t, level="important", key=None, source="": said.append((t, {"level": level, "important": level != "minor", "urgent": level == "urgent"})))
    j._said = said
    return j


def _open(jv, finding):
    jv._caretaker_store.ingest([finding])
    return finding.key


def _age(jv, key, minutes):
    ts = (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    c = jv._memory_db_connect()
    with c:
        c.execute("UPDATE caretaker_actions SET ts=? WHERE issue_key=?", (ts, key))


def test_a_cpu_hog_gets_a_lower_priority_once_and_says_so_quietly(jv, monkeypatch):
    calls = []
    monkeypatch.setattr(jv.caretaker_win, "lower_priority",
                        lambda name, **k: calls.append(name) or {"changed": [{"pid": 7, "prev": cw.NORMAL}],
                                                                  "skipped": 0, "protected": False, "reason": None})
    key = _open(jv, ct.process_finding("Handbrake.exe", 80, 25, in_front=False, pid=7))
    assert jv._caretaker_fix_all() == ["lowered the priority of Handbrake.exe"]
    assert jv._caretaker_fix_all() == [] and calls == ["Handbrake.exe"]       # once, not every pass
    act = jv._caretaker_store.recent_actions(5)[0]
    assert act["action"] == "lower_priority" and act["undo"]["kind"] == "priority"
    assert len(jv._said) == 1 and "won't slow your other apps" in jv._said[0][0]
    assert not jv._said[0][1].get("important") and not jv._said[0][1].get("urgent")
    assert jv._caretaker_store.get(key)["status"] == "open"        # it stays listed until the CPU use stops


def test_what_the_user_is_working_in_is_never_touched(jv, monkeypatch):
    calls = []
    monkeypatch.setattr(jv.caretaker_win, "lower_priority", lambda *a, **k: calls.append(1))
    _open(jv, ct.process_finding("code.exe", 80, 25, in_front=True, pid=7))
    assert jv._caretaker_fix_all() == [] and calls == []
    # the finding said "not in front" a moment ago, but the window in front is that program now
    _open(jv, ct.process_finding("Code.exe", 80, 25, in_front=False, pid=7))
    jv._caretaker_fix_all()
    assert calls == []


def test_a_protected_hog_is_explained_not_touched(jv):
    key = _open(jv, ct.process_finding("svchost.exe", 90, 30, in_front=False, pid=4))
    assert jv._caretaker_fix_all() == []
    i = jv._caretaker_store.get(key)
    assert i["status"] == "gave_up" and "leave it alone" in jv._said[0][0]


def test_undoing_a_priority_change_goes_through_the_undo_tool(jv, monkeypatch):
    monkeypatch.setattr(jv.caretaker_win, "lower_priority",
                        lambda name, **k: {"changed": [{"pid": 7, "prev": cw.NORMAL}], "skipped": 0,
                                           "protected": False, "reason": None})
    restored = []
    monkeypatch.setattr(jv.caretaker_win, "restore_priority",
                        lambda info, **k: restored.append(info) or "Put back the normal priority of X (1 process(es)).")
    _open(jv, ct.process_finding("Handbrake.exe", 80, 25, in_front=False, pid=7))
    jv._caretaker_fix_all()
    out = jv._caretaker_undo()
    assert out.startswith("Put back") and restored[0]["items"] == [{"pid": 7, "prev": cw.NORMAL}]
    assert jv._caretaker_store.recent_actions(5)[0]["undone"] is True


def test_a_network_fix_that_works_closes_the_issue(jv, monkeypatch):
    monkeypatch.setattr(jv.caretaker_win, "fix_network",
                        lambda detail, **k: {"cleared": True, "steps": ["flushed the DNS cache"], "needs_admin": []})
    key = _open(jv, ct.network_finding(True, False, True))
    assert jv._caretaker_fix_all() == ["network: flushed the DNS cache"]
    assert jv._caretaker_store.get(key)["status"] == "fixed"


def test_a_network_that_stays_down_is_tried_three_times_then_explained_once(jv, monkeypatch):
    monkeypatch.setattr(jv.caretaker_win, "fix_network",
                        lambda detail, **k: {"cleared": False, "steps": ["flushed the DNS cache"],
                                             "needs_admin": ["restart_adapter"]})
    key = _open(jv, ct.network_finding(False, False, True))
    jv._caretaker_fix_all()
    assert jv._caretaker_fix_all() == [] and jv._caretaker_store.get(key)["attempts"] == 1   # 5-minute gap
    for _ in range(2):
        _age(jv, key, 10)
        jv._caretaker_fix_all()
    i = jv._caretaker_store.get(key)
    assert i["status"] == "gave_up" and i["attempts"] == 3
    msgs = [t for t, _ in jv._said if "still down" in t]
    assert len(msgs) == 1 and "restart the router" in msgs[0] and "administrator" in msgs[0]
    assert jv._caretaker_state["needs_admin"][key] == ["restart_adapter"]


def test_a_crashing_app_gets_its_cache_cleared_once_a_day_and_the_advice(jv, monkeypatch):
    calls = []
    monkeypatch.setattr(jv.caretaker_win, "clear_app_cache",
                        lambda app, **k: calls.append(app) or {"freed": 5000, "files": 3, "dirs": 2, "why_not": None})
    key = _open(jv, ct.crash_finding("opera.exe", 4, "d3d11.dll"))
    assert jv._caretaker_fix_all() == ["cleared opera.exe's cache"]
    assert jv._caretaker_fix_all() == [] and calls == ["opera.exe"]
    assert "graphics driver" in jv._said[0][0] and len(jv._said) == 1
    assert jv._caretaker_store.summary_since(24)["freed_bytes"] == 5000
    assert jv._caretaker_store.get(key)["status"] == "open"


def test_a_running_app_is_retried_later_and_an_unknown_app_only_gets_advice(jv, monkeypatch):
    answers = iter([{"freed": 0, "files": 0, "dirs": 1, "why_not": "it is running right now"},
                    {"freed": 0, "files": 0, "dirs": 0, "why_not": "no cache folder I know of"}])
    monkeypatch.setattr(jv.caretaker_win, "clear_app_cache", lambda app, **k: next(answers))
    _open(jv, ct.crash_finding("chrome.exe", 4, ""))
    assert jv._caretaker_fix_all() == [] and jv._said == []
    assert jv._caretaker_fix_all() == [] and len(jv._said) == 1 and "reinstall" in jv._said[0][0]


def test_a_failing_disk_and_windows_update_have_no_automatic_fix(jv, monkeypatch):
    monkeypatch.setenv("JARVIS_CARETAKER_AI", "0")      # the AI fallback has its own tests
    _open(jv, ct.disk_health_finding("0", "Warning"))
    _open(jv, ct.update_finding(3, 9))
    assert jv._caretaker_fix_all() == [] and len(jv._caretaker_store.open_issues()) == 2
    assert jv._caretaker_store.recent_actions(5) == []


def test_none_of_the_playbooks_run_in_safe_mode(jv, monkeypatch):
    hit = []
    for fn in ("lower_priority", "fix_network", "clear_app_cache"):
        monkeypatch.setattr(jv.caretaker_win, fn, lambda *a, **k: hit.append(1))
    _open(jv, ct.process_finding("Handbrake.exe", 80, 25, in_front=False, pid=7))
    _open(jv, ct.network_finding(False, False, True))
    _open(jv, ct.crash_finding("opera.exe", 4))
    monkeypatch.setattr(jv.autonomy, "hard_disabled", lambda: True)
    assert jv._caretaker_fix_all() == [] and hit == []
