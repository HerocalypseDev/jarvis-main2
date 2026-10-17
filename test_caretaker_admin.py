"""Caretaker phase 6: the admin helper. Five fixed Windows tasks that the owner sets up once by accepting Windows' own
prompt. There is no PowerShell here, so everything below runs against a fake Windows (a runner that answers the
status/start commands and a reader for the script files). What matters: a task takes no input, nothing but the fixed
scripts can ever run elevated, and Jarvis refuses to run a task or script that is not exactly what it installed."""
import base64
import hashlib
import json
import re
import time
from pathlib import Path
from datetime import datetime, timedelta

import pytest

import jarvis_caretaker as ct
import jarvis_caretaker_admin as adm
import jarvis_caretaker_ai as ai

ENV = {"ProgramFiles": r"C:\Program Files", "USERDOMAIN": "PC", "USERNAME": "x", "LOCALAPPDATA": r"C:\Users\x\AppData\Local"}
ME = "PC\\x"
NAMES = list(adm.ADMIN_ACTIONS)
_REAL_SLEEP = time.sleep      # captured before any test patches the (shared) time module


# --- a fake Windows ------------------------------------------------------------------------------
class FakeWin:
    """Answers the commands the module sends. Tasks are rows like the status script returns."""

    def __init__(self, env=ENV, user=ME):
        self.env, self.user = env, user
        self.tasks = {n: {"name": n, "state": "Ready", "level": "Highest", "user": user, "actions": 1,
                          "exe": "powershell.exe", "args": adm.task_arguments(n, env),
                          "last": "2026-10-16T08:00:00.0000000+01:00", "code": 0} for n in NAMES}
        self.files = {adm.script_path(n, env): a["script"] for n, a in adm.ADMIN_ACTIONS.items()}
        self.started, self.calls = [], []
        self.result = {}            # name -> exit code a run ends with (default 0)
        self.never_runs = set()     # names whose task does not start for real
        self.polls_running = 0      # how many status reads show "Running" after a start
        self.start_rc = 0
        self.status_rc = 0
        self.groups = '"Administrators","S-1-5-32-544","Group used for deny only"'
        self._clock = 0

    def reader(self, path):
        return self.files.get(path)

    def run(self, argv, timeout=60):
        self.calls.append(argv)
        if argv[0] == "whoami":
            return 0, self.groups
        script = adm.decode_ps_argv(argv)
        if "Get-ScheduledTask " in script:
            if self.status_rc:
                return self.status_rc, ""
            for t in self.tasks.values():
                if t["state"] == "Running":
                    self.polls_running -= 1
                    if self.polls_running <= 0:
                        t["state"] = "Ready"
            return 0, json.dumps(list(self.tasks.values()))
        m = re.search(r"Start-ScheduledTask .*-TaskName '([a-z_]+)'", script)
        if m:
            if self.start_rc:
                return self.start_rc, ""
            name = m.group(1)
            self.started.append(name)
            if name not in self.never_runs:
                t = self.tasks[name]
                self._clock += 1
                t["last"] = f"2026-10-16T09:00:{self._clock:02d}.0000000+01:00"
                t["code"] = self.result.get(name, 0)
                if self.polls_running:
                    t["state"] = "Running"
            return 0, ""
        return 0, ""


class Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


def _status(w, **kw):
    return adm.status(w.run, env=w.env, reader=w.reader, me=w.user, **kw)


def _run(w, name, **kw):
    c = Clock()
    return adm.run_action(name, runner=w.run, sleep=c.sleep, now=c.now, env=w.env, reader=w.reader, me=w.user, **kw)


# --- the scripts and the tasks are fixed ----------------------------------------------------------
def test_there_are_exactly_five_fixed_actions_each_with_a_plain_description():
    assert NAMES == ["flush_dns", "restart_adapter", "update_defender", "reset_windows_update", "clear_windows_temp"]
    for d in adm.describe():
        assert d["desc"].endswith(".") and d["tier"] in (ct.GREEN, ct.YELLOW)


@pytest.mark.parametrize("name", NAMES)
def test_a_script_has_no_input_channel_and_no_way_to_run_other_code(name):
    s = adm.ADMIN_ACTIONS[name]["script"]
    for bad in ("param(", "$args", "$input", "Invoke-Expression", "iex ", "Invoke-WebRequest", "Invoke-RestMethod",
                "DownloadString", "Start-Process", "Read-Host", "GetCommandLineArgs", "-EncodedCommand",
                "Invoke-Command", "& $", "&(", "[scriptblock]", "cmd /c", "$env:ARG"):
        assert bad.lower() not in s.lower(), (name, bad)
    assert s.rstrip().endswith("exit $code")
    assert "$ErrorActionPreference = 'Stop'" in s


def test_the_task_runs_one_fixed_script_file_with_no_arguments_of_its_own():
    a = adm.task_arguments("flush_dns", ENV)
    assert a == ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File '
                 '"C:\\Program Files\\JarvisHelper\\flush_dns.ps1"')
    assert adm.script_path("flush_dns", ENV) == r"C:\Program Files\JarvisHelper\flush_dns.ps1"


def test_the_install_script_registers_five_on_demand_elevated_tasks_in_a_locked_folder():
    s = adm.install_script(ME, ENV)
    assert s.count("Register-ScheduledTask") == 1 and "-RunLevel Highest" in s
    assert "-Trigger" not in s                                       # on demand: nothing starts them but Jarvis
    assert "/inheritance:r" in s and "'Users:(OI)(CI)RX'" in s and "'Administrators:(OI)(CI)F'" in s
    assert "$user = 'PC\\x'" in s
    rows = re.findall(r"@\('([a-z_]+)', '([A-Za-z0-9+/=]+)'\)", s)
    assert [n for n, _ in rows] == NAMES
    for n, b in rows:                                                # the files written are exactly the fixed scripts
        assert base64.b64decode(b).decode("utf-8") == adm.ADMIN_ACTIONS[n]["script"]


@pytest.mark.parametrize("bad", ["", "x", "PC\\x'; calc #", 'PC\\"x', "PC\\x\nnet user", "PC\\x;y", "a\\b\\c" + "$"])
def test_an_unusable_windows_user_name_is_refused(bad):
    assert not adm.valid_user(bad)
    with pytest.raises(ValueError):
        adm.install_script(bad, ENV)


def test_normal_user_names_are_accepted():
    for ok in ("PC\\x", "DESKTOP-AB12\\Sam Lee", "WORKGROUP\\a.b-c_d", "MicrosoftAccount\\me@mail.example"):
        assert adm.valid_user(ok), ok


def test_the_remove_script_only_removes_this_folder_and_these_tasks():
    s = adm.remove_script(ENV)
    assert "Unregister-ScheduledTask" in s and "\\Jarvis\\Caretaker\\" in s
    assert "C:\\Program Files\\JarvisHelper" in s and "Register-ScheduledTask" not in s


def test_the_elevated_launcher_runs_only_text_whose_hash_was_fixed_before_the_prompt(tmp_path):
    text = adm.install_script(ME, ENV)
    path = adm.stage_script(text, tmp_path / "setup", "install_helper.ps1")
    assert open(path, "rb").read() == text.encode("utf-8")
    argv = adm.launcher_argv(text, path)
    outer = adm.decode_ps_argv(argv)
    assert "-Verb RunAs" in outer and "Start-Process" in outer
    inner = base64.b64decode(re.search(r"'-EncodedCommand', '([A-Za-z0-9+/=]+)'", outer).group(1)).decode("utf-16-le")
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() in inner
    assert inner.index("exit 9") < inner.index("Invoke-Expression")      # compare first, run second
    assert "ReadAllText" in inner and path in inner                       # read once into memory: no re-read after the check
    other = adm.install_script("PC\\y", ENV)
    assert hashlib.sha256(other.encode("utf-8")).hexdigest() not in inner  # a different script has a different hash


def _inner_stub(argv):
    outer = adm.decode_ps_argv(argv)
    return base64.b64decode(re.search(r"'-EncodedCommand', '([A-Za-z0-9+/=]+)'", outer).group(1)).decode("utf-16-le")


def test_the_launcher_with_a_result_file_still_checks_the_hash_before_running_and_reports_either_way(tmp_path):
    text = adm.install_script(ME, ENV)
    path = adm.stage_script(text, tmp_path / "setup", "install_helper.ps1")
    res = str(tmp_path / "setup" / "install_helper.result.txt")
    inner = _inner_stub(adm.launcher_argv(text, path, res))
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() in inner
    assert inner.index("exit 9") < inner.index("Invoke-Expression")      # nothing changes about compare-then-run
    assert "catch" in inner and "'FAIL: ' + $_.Exception.Message" in inner and "'OK'" in inner
    assert "FAIL: the setup file changed" in inner and res in inner
    assert inner.index("Invoke-Expression") < inner.index("'OK'")          # OK is written only after the script ran


def test_without_a_result_file_the_launcher_is_the_original_one(tmp_path):
    text = adm.remove_script(ENV)
    path = adm.stage_script(text, tmp_path / "setup", "remove_helper.ps1")
    inner = _inner_stub(adm.launcher_argv(text, path))
    assert "catch" not in inner and "WriteAllText" not in inner


def test_reading_what_the_elevated_setup_wrote(tmp_path):
    f = tmp_path / "r.txt"
    assert adm.read_setup_result(f) == (None, "")                         # nothing yet
    f.write_text("OK", encoding="utf-8")
    assert adm.read_setup_result(f) == ("ok", "")
    f.write_text("\ufeffOK\r\n", encoding="utf-8")
    assert adm.read_setup_result(f) == ("ok", "")
    f.write_text("FAIL: could not lock the helper folder", encoding="utf-8")
    assert adm.read_setup_result(f) == ("fail", "could not lock the helper folder")
    f.write_text("FAIL: bad\x00\x1b[31m thing\nsecond line " + "x" * 400, encoding="utf-8")
    verdict, why = adm.read_setup_result(f)
    assert verdict == "fail" and len(why) <= 160 and "\n" not in why and "\x1b" not in why
    f.write_text("anything else", encoding="utf-8")
    assert adm.read_setup_result(f) == (None, "")


# --- reading what is installed --------------------------------------------------------------------
def test_everything_as_installed_is_ready():
    w = FakeWin()
    st = _status(w)
    assert st["known"] and st["installed"] and st["ready"] == NAMES and st["changed"] == []
    assert all(a["ok"] for a in st["actions"].values())


def test_nothing_installed_is_not_an_error_just_not_set_up():
    w = FakeWin()
    w.tasks.clear()
    st = _status(w)
    assert st["known"] and not st["installed"] and st["ready"] == [] and st["changed"] == []
    assert st["actions"]["flush_dns"]["why"] == "not set up"


def test_windows_that_cannot_be_asked_is_unknown_not_ready():
    w = FakeWin()
    w.status_rc = 1
    st = _status(w)
    assert not st["known"] and st["ready"] == []


def test_status_says_why_windows_could_not_be_asked():
    w = FakeWin()
    w.status_rc = 1
    assert "code 1" in _status(w)["error"]
    w.status_rc = -1
    assert "didn't answer" in _status(w)["error"]
    w2 = FakeWin()
    orig = w2.run
    w2.run = lambda argv, timeout=60: (0, "not json{") if "Get-ScheduledTask" in adm.decode_ps_argv(argv) else orig(argv, timeout)
    st = adm.status(w2.run, env=w2.env, reader=w2.reader, me=w2.user)
    assert not st["known"] and "couldn't read" in st["error"]
    assert "error" not in _status(FakeWin())                              # a good read carries no error


def _noisy_status(w, wrap):
    """Status read where PowerShell's real answer comes back wrapped by `wrap` (stdout and stderr are read together)."""
    orig = w.run

    def run(argv, timeout=60):
        rc, out = orig(argv, timeout)
        if "Get-ScheduledTask" in adm.decode_ps_argv(argv):
            return rc, wrap(out)
        return rc, out
    return adm.status(run, env=w.env, reader=w.reader, me=w.user)


_CLIXML = ('#< CLIXML\r\n<Objs Version="1.1.0.1" xmlns="http://schemas.microsoft.com/powershell/2004/04">'
           '<Obj S="progress" RefId="0"><TN RefId="0"><T>System.Management.Automation.PSCustomObject</T></TN>'
           '<MS><I64 N="SourceId">1</I64><PR N="Record"><AV>Preparing modules for first use.</AV></PR></MS></Obj></Objs>')


@pytest.mark.parametrize("wrap", [
    lambda o: _CLIXML + "\r\n" + o,                      # progress record on stderr, read first
    lambda o: o + "\r\n" + _CLIXML,                      # ... or last
    lambda o: "\ufeff" + o,                               # byte-order mark
    lambda o: "WARNING: something harmless\r\n" + o + "\r\n",
])
def test_status_reads_through_powershell_noise(wrap):
    w = FakeWin()
    st = _noisy_status(w, wrap)
    assert st["known"] and "error" not in st, st
    assert set(st["ready"]) == set(adm.ADMIN_ACTIONS)


def test_status_error_shows_what_windows_returned():
    w = FakeWin()
    st = _noisy_status(w, lambda o: "Something odd happened\x00\x01 here")
    assert not st["known"]
    assert "couldn't read" in st["error"] and "Something odd happened" in st["error"]
    assert "\x00" not in st["error"]


@pytest.mark.parametrize("change,why", [
    (lambda w: w.tasks["flush_dns"].update(args=w.tasks["flush_dns"]["args"] + " -Command calc"), "the task was changed"),
    (lambda w: w.tasks["flush_dns"].update(exe="cmd.exe"), "the task was changed"),
    (lambda w: w.tasks["flush_dns"].update(actions=2), "the task was changed"),
    (lambda w: w.tasks["flush_dns"].update(args=w.tasks["flush_dns"]["args"].replace("flush_dns", "..\\evil")),
     "the task was changed"),
    (lambda w: w.tasks["flush_dns"].update(level="Limited"), "the task doesn't run with administrator rights"),
    (lambda w: w.tasks["flush_dns"].update(user="PC\\someone"), "the task belongs to another Windows user"),
    (lambda w: w.tasks["flush_dns"].update(state="Disabled"), "the task is switched off in Windows"),
    (lambda w: w.files.pop(adm.script_path("flush_dns", ENV)), "its script is missing"),
    (lambda w: w.files.update({adm.script_path("flush_dns", ENV): "Clear-DnsClientCache\ncalc.exe\nexit 0\n"}),
     "its script was changed"),
])
def test_a_task_or_script_that_is_not_what_was_installed_is_never_ready(change, why):
    w = FakeWin()
    change(w)
    st = _status(w)
    assert "flush_dns" not in st["ready"] and st["actions"]["flush_dns"]["why"] == why
    assert not st["installed"] and st["ready"] == NAMES[1:]              # the other four are still fine
    r = _run(w, "flush_dns")
    assert not r["ok"] and w.started == [] and why in r["detail"]


def test_a_script_with_windows_line_endings_or_a_bom_is_still_the_same_script():
    w = FakeWin()
    p = adm.script_path("flush_dns", ENV)
    w.files[p] = "\ufeff" + adm.ADMIN_ACTIONS["flush_dns"]["script"].replace("\n", "\r\n")
    assert "flush_dns" in _status(w)["ready"]


def test_is_admin_account_reads_the_administrators_group():
    w = FakeWin()
    assert adm.is_admin_account(w.run) is True
    w.groups = '"Everyone","S-1-1-0","Mandatory group"'
    assert adm.is_admin_account(w.run) is False
    assert adm.is_admin_account(lambda a, **k: (1, "")) is None


# --- running one action ---------------------------------------------------------------------------
def test_a_run_starts_the_task_and_reports_its_result():
    w = FakeWin()
    r = _run(w, "flush_dns")
    assert r == {"ok": True, "skipped": False, "code": 0, "detail": "flushed the DNS cache"} and w.started == ["flush_dns"]


def test_a_run_waits_while_the_task_is_running():
    w = FakeWin()
    w.polls_running = 3
    r = _run(w, "update_defender")
    assert r["ok"] and r["detail"] == "updated the virus definitions"


def test_a_failing_task_is_a_failure_with_its_code():
    w = FakeWin()
    w.result["flush_dns"] = 1
    r = _run(w, "flush_dns")
    assert not r["ok"] and not r["skipped"] and r["code"] == 1 and "code 1" in r["detail"]


def test_not_now_and_nothing_to_do_are_skips_not_failures():
    w = FakeWin()
    w.result["reset_windows_update"] = 3
    r = _run(w, "reset_windows_update")
    assert r["skipped"] and not r["ok"] and "installing an update" in r["detail"]
    w.result["restart_adapter"] = 4
    r = _run(w, "restart_adapter")
    assert r["skipped"] and "no connected network adapter" in r["detail"]


def test_a_task_that_never_starts_or_windows_refusing_to_start_it_is_reported():
    w = FakeWin()
    w.never_runs.add("flush_dns")
    r = _run(w, "flush_dns")
    assert not r["ok"] and "never started" in r["detail"]
    w2 = FakeWin()
    w2.start_rc = 1
    assert "wouldn't start" in _run(w2, "flush_dns")["detail"]


def test_a_task_that_runs_for_ever_is_given_up_on():
    w = FakeWin()
    w.polls_running = 10 ** 6
    r = _run(w, "flush_dns")
    assert not r["ok"] and "too long" in r["detail"]


def test_an_unknown_action_name_never_reaches_windows():
    w = FakeWin()
    for bad in ("calc", "flush_dns; calc", "../x", ""):
        assert not _run(w, bad)["ok"]
    assert w.started == [] and w.calls == []


def test_the_start_command_names_the_task_with_a_quoted_literal():
    w = FakeWin()
    _run(w, "flush_dns")
    starts = [adm.decode_ps_argv(c) for c in w.calls if c[0] != "whoami" and "Start-ScheduledTask" in adm.decode_ps_argv(c)]
    assert starts == ["Start-ScheduledTask -TaskPath '\\Jarvis\\Caretaker\\' -TaskName 'flush_dns'"]


# =========================== the wiring in jarvis.py ====================================================
@pytest.fixture()
def jv(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "jv.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("JARVIS_CARETAKER_ADMIN", raising=False)
    import jarvis as j
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    monkeypatch.setattr(j, "_caretaker_store", ct.Store(j._memory_db_connect))
    monkeypatch.setattr(j, "_caretaker_state", {"check": 0.0, "running": False, "last": None, "announced": set()})
    monkeypatch.setattr(j, "_caretaker_admin_cache", {"at": 0.0, "status": None})
    monkeypatch.setattr(j, "CARETAKER_ADMIN_SETTLE_S", 0)
    monkeypatch.setattr(j.doctor, "problems", lambda *a, **k: [])
    monkeypatch.setattr(j.autonomy, "hard_disabled", lambda: False)
    monkeypatch.setattr(j, "_foreground_window", lambda: {"app": "code.exe"})
    said = []
    monkeypatch.setattr(j, "queue_or_deliver_notification", lambda t, **kw: said.append((t, kw)))
    j._said = said
    j._model_calls = []
    j._admin_runs = []
    yield j
    ai.set_admin_ready(())


def _helper(jv, monkeypatch, ready=NAMES, results=None, installed=None):
    """Pretend the helper is set up (ready = the names that may run); every run is recorded in jv._admin_runs."""
    st = {"supported": True, "known": True, "actions": {n: {"ok": n in ready, "why": None if n in ready else "not set up"}
                                                         for n in NAMES},
          "ready": list(ready), "changed": [], "installed": installed if installed is not None else len(ready) == 5}
    monkeypatch.setattr(jv.caretaker_admin, "status", lambda *a, **k: dict(st))

    def run(name, **k):
        jv._admin_runs.append(name)
        return (results or {}).get(name) or {"ok": True, "skipped": False, "code": 0,
                                              "detail": adm.ADMIN_ACTIONS[name]["did"]}
    monkeypatch.setattr(jv.caretaker_admin, "run_action", run)
    return st


def _open(jv, finding):
    jv._caretaker_store.ingest([finding])
    return finding.key


def _age(jv, key, minutes, action=None):
    ts = (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    c = jv._memory_db_connect()
    with c:
        c.execute("UPDATE caretaker_actions SET ts=? WHERE issue_key=?" + (" AND action LIKE ?" if action else ""),
                  (ts, key) + ((action,) if action else ()))


def _net_down(jv, monkeypatch, needs):
    monkeypatch.setattr(jv.caretaker_win, "fix_network",
                        lambda detail, **k: {"cleared": False, "steps": [], "needs_admin": list(needs)})


def test_a_network_problem_that_needs_admin_rights_is_fixed_through_the_helper(jv, monkeypatch):
    _helper(jv, monkeypatch)
    _net_down(jv, monkeypatch, ["flush_dns"])
    monkeypatch.setattr(jv.caretaker_probe, "probe_network", lambda: None)      # None = no problem found: back online
    key = _open(jv, ct.network_finding(True, False, True))
    assert jv._caretaker_fix_all() == ["network: flushed the DNS cache"]
    assert jv._admin_runs == ["flush_dns"] and jv._caretaker_store.get(key)["status"] == "fixed"
    acts = {a["action"]: a for a in jv._caretaker_store.recent_actions(10)}
    assert acts["admin:flush_dns"]["tier"] == ct.GREEN and acts["admin:flush_dns"]["result"] == "done"


def test_a_helper_step_that_does_not_bring_the_network_back_moves_on_to_the_next_one(jv, monkeypatch):
    _helper(jv, monkeypatch)
    _net_down(jv, monkeypatch, ["flush_dns", "restart_adapter"])
    seen = []
    monkeypatch.setattr(jv.caretaker_probe, "probe_network",
                        lambda: seen.append(1) or (ct.network_finding(False, False, True) if len(seen) == 1 else None))
    key = _open(jv, ct.network_finding(False, False, True))
    assert jv._caretaker_fix_all() == ["network: flushed the DNS cache; restarted the network adapter"]
    assert jv._admin_runs == ["flush_dns", "restart_adapter"] and jv._caretaker_store.get(key)["status"] == "fixed"


def test_without_the_helper_nothing_runs_and_the_page_hint_stays(jv, monkeypatch):
    _helper(jv, monkeypatch, ready=[])
    _net_down(jv, monkeypatch, ["restart_adapter"])
    key = _open(jv, ct.network_finding(False, False, True))
    jv._caretaker_fix_all()
    assert jv._admin_runs == [] and jv._caretaker_state["needs_admin"][key] == ["restart_adapter"]
    assert jv.caretaker_report()["needs_admin"] == {key: ["restart_adapter"]}


def test_the_switch_and_safe_mode_stop_every_admin_run(jv, monkeypatch):
    _helper(jv, monkeypatch)
    assert jv._caretaker_admin_run("k", "flush_dns")["ok"]
    monkeypatch.setenv("JARVIS_CARETAKER_ADMIN", "0")
    r = jv._caretaker_admin_run("k", "restart_adapter")
    assert r["skipped"] and "switched off" in r["detail"]
    monkeypatch.delenv("JARVIS_CARETAKER_ADMIN")
    monkeypatch.setattr(jv.autonomy, "hard_disabled", lambda: True)
    assert jv._caretaker_admin_run("k", "restart_adapter")["skipped"]
    monkeypatch.setenv("JARVIS_CARETAKER_ACT", "0")
    monkeypatch.setattr(jv.autonomy, "hard_disabled", lambda: False)
    assert jv._caretaker_admin_run("k", "restart_adapter")["skipped"]
    assert jv._admin_runs == ["flush_dns"]


def test_the_same_repair_waits_its_gap_and_a_failed_one_waits_an_hour(jv, monkeypatch):
    _helper(jv, monkeypatch, results={"restart_adapter": {"ok": False, "skipped": False, "code": 1, "detail": "boom"}})
    assert jv._caretaker_admin_run("k", "flush_dns")["ok"]
    again = jv._caretaker_admin_run("k", "flush_dns")
    assert again["skipped"] and "recently" in again["detail"]
    _age(jv, "k", adm.ADMIN_ACTIONS["flush_dns"]["gap_min"] + 1)
    assert jv._caretaker_admin_run("k", "flush_dns")["ok"] and jv._admin_runs == ["flush_dns", "flush_dns"]
    assert not jv._caretaker_admin_run("k", "restart_adapter")["ok"]
    wait = jv._caretaker_admin_run("k", "restart_adapter")
    assert wait["skipped"] and "waiting" in wait["detail"] and jv._admin_runs.count("restart_adapter") == 1
    assert jv._caretaker_store.recent_actions(10)[0]["action"] == "admin_failed:restart_adapter"
    _age(jv, "k", jv.CARETAKER_ADMIN_FAIL_RETRY_MIN + 1, "admin_failed:%")
    assert not jv._caretaker_admin_run("k", "restart_adapter")["skipped"]


def test_a_skip_from_the_helper_is_not_logged_as_an_action(jv, monkeypatch):
    _helper(jv, monkeypatch, results={"reset_windows_update": {"ok": False, "skipped": True, "code": 3,
                                                               "detail": "Windows is installing an update right now"}})
    r = jv._caretaker_admin_run("k", "reset_windows_update")
    assert r["skipped"] and jv._caretaker_store.recent_actions(5) == []


def test_a_helper_that_crashes_is_a_failed_action_not_an_exception(jv, monkeypatch):
    _helper(jv, monkeypatch)
    monkeypatch.setattr(jv.caretaker_admin, "run_action", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    r = jv._caretaker_admin_run("k", "flush_dns")
    assert not r["ok"] and "crashed" in r["detail"]


def test_a_name_that_is_not_one_of_the_five_is_refused(jv, monkeypatch):
    _helper(jv, monkeypatch)
    for bad in ("run_shell", "flush_dns; calc", "", "../x"):
        assert jv._caretaker_admin_run("k", bad)["skipped"]
    assert jv._admin_runs == []


def test_old_virus_definitions_are_updated_through_the_helper_but_not_young_ones(jv, monkeypatch):
    _helper(jv, monkeypatch)
    monkeypatch.setenv("JARVIS_CARETAKER_AI", "0")
    _open(jv, ct.update_finding(0, 3 + 4))                        # 7 days old
    assert jv._caretaker_fix_all() == ["updated the virus definitions"]
    assert jv._admin_runs == ["update_defender"]
    c = jv._memory_db_connect()
    with c:
        c.execute("DELETE FROM caretaker_issues")
    jv._admin_runs.clear()
    _open(jv, ct.update_finding(3, 2))                           # failed updates, young definitions: advice only
    jv._caretaker_fix_all()
    assert jv._admin_runs == []


def test_an_update_problem_without_the_helper_is_left_alone(jv, monkeypatch):
    _helper(jv, monkeypatch, ready=[])
    monkeypatch.setenv("JARVIS_CARETAKER_AI", "0")
    _open(jv, ct.update_finding(0, 30))
    assert jv._caretaker_fix_all() == [] and jv._admin_runs == []


def test_the_storage_playbook_clears_windows_temp_when_user_level_cleanup_is_not_enough(jv, monkeypatch):
    _helper(jv, monkeypatch)
    free = {"v": 10_000}
    monkeypatch.setattr(jv, "_free_bytes", lambda mount: free["v"])
    monkeypatch.setattr(jv.caretaker_admin, "run_action",
                        lambda name, **k: free.update(v=free["v"] + 3_000_000_000) or jv._admin_runs.append(name)
                        or {"ok": True, "skipped": False, "code": 0, "detail": "cleared old Windows temp files"})
    fx = {"freed": 0, "held": 0, "steps": [], "reached": False, "free_after": 0.05, "blocked": None}
    monkeypatch.setattr(jv.caretaker_fix, "fix_storage", lambda *a, **k: dict(fx, steps=list(fx["steps"])))

    class Env:
        def free_fraction(self):
            return 0.2 if free["v"] > 1_000_000 else 0.05
    monkeypatch.setattr(jv, "_caretaker_storage_env", lambda mount: Env())
    key = _open(jv, ct.storage_finding("C:", 95, 20))
    ev_mount = "C:\\"
    out = jv._caretaker_fix_storage({"key": key, "evidence": {"drive": "C:", "mount": ev_mount, "percent": 95}})
    assert jv._admin_runs == ["clear_windows_temp"] and "cleared old Windows temp files (" in out
    assert jv._caretaker_store.get(key)["status"] == "fixed"
    assert jv._caretaker_store.recent_actions(5)[0]["freed_bytes"] == 3_000_000_000


def test_storage_does_not_use_the_helper_when_the_cleanup_already_got_there_or_was_blocked(jv, monkeypatch):
    _helper(jv, monkeypatch)
    monkeypatch.setattr(jv, "_caretaker_storage_env", lambda mount: None)
    key = _open(jv, ct.storage_finding("C:", 95, 20))
    iss = {"key": key, "evidence": {"drive": "C:", "mount": "C:\\"}}
    monkeypatch.setattr(jv.caretaker_fix, "fix_storage", lambda *a, **k: {
        "freed": 1, "held": 0, "steps": ["cleared caches"], "reached": True, "free_after": 0.2, "blocked": None})
    jv._caretaker_fix_storage(iss)
    monkeypatch.setattr(jv.caretaker_fix, "fix_storage", lambda *a, **k: {
        "freed": 0, "held": 0, "steps": [], "reached": False, "free_after": 0.05, "blocked": "10 actions an hour"})
    jv._caretaker_fix_storage(iss)
    assert jv._admin_runs == []


# --- the AI menu ----------------------------------------------------------------------------------
NET = ct.network_finding(False, False, True)


def _issue(f):
    return {"key": f.key, "category": f.category, "severity": f.severity, "title": f.title, "evidence": f.evidence,
            "status": "gave_up", "attempts": 3, "tried": []}


def test_admin_actions_are_on_the_models_menu_only_while_the_helper_is_ready():
    iss, upd = _issue(NET), _issue(ct.update_finding(3, 9))
    assert "flush_dns" not in ai.actions_for(iss) and "update_defender" not in ai.actions_for(upd)
    ai.set_admin_ready(["flush_dns", "reset_windows_update"])
    try:
        assert "flush_dns" in ai.actions_for(iss) and "restart_adapter" not in ai.actions_for(iss)
        assert "reset_windows_update" in ai.actions_for(upd) and "update_defender" not in ai.actions_for(upd)
        assert "flush_dns" not in ai.actions_for(upd)                    # tied to its own kind of problem
        assert ai.validate({"steps": [{"action": "flush_dns"}]}, iss)["steps"] == [{"action": "flush_dns", "args": {}}]
        assert ai.validate({"steps": [{"action": "flush_dns", "args": {"x": 1}}]}, iss)["steps"] == []
    finally:
        ai.set_admin_ready(())
    assert ai.validate({"steps": [{"action": "flush_dns"}]}, iss)["steps"] == []


def test_the_clear_temp_repair_is_never_on_the_models_menu():
    ai.set_admin_ready(NAMES)
    try:
        for f in (NET, ct.update_finding(3, 9), ct.storage_finding("C:", 95, 20)):
            assert "clear_windows_temp" not in ai.actions_for(_issue(f))
    finally:
        ai.set_admin_ready(())


def _script(jv, monkeypatch, *replies):
    it = iter(replies)

    def call(system, user, max_tokens):
        jv._model_calls.append(user)
        r = next(it, None)
        return json.dumps(r) if isinstance(r, dict) else r
    monkeypatch.setattr(jv, "_caretaker_ai_call", call)


def test_the_model_can_pick_an_admin_repair_and_it_runs_through_the_helper(jv, monkeypatch):
    _helper(jv, monkeypatch)
    monkeypatch.setattr(jv.caretaker_win, "fix_network", lambda detail, **k: {"cleared": False, "steps": [], "needs_admin": []})
    _script(jv, monkeypatch, {"cause": "A stale DNS cache.", "advice": "Restart the router if it stays down.",
                              "steps": [{"action": "flush_dns"}, {"action": "restart_adapter", "args": {"name": "x"}}]})
    jv._caretaker_store.ingest([NET])
    for _ in range(ct.MAX_ATTEMPTS):
        jv._caretaker_store.note_attempt(NET.key, "tried")
    jv._caretaker_fix_all()
    assert jv._admin_runs == ["flush_dns"]                          # the second step had a stray argument: rejected
    assert "flush_dns" in jv._model_calls[0]                        # it was on the menu the model saw
    acts = {a["action"] for a in jv._caretaker_store.recent_actions(10)}
    assert {"ai:flush_dns", "admin:flush_dns"} <= acts


def test_the_model_never_sees_admin_repairs_when_the_helper_is_not_set_up(jv, monkeypatch):
    _helper(jv, monkeypatch, ready=[])
    _script(jv, monkeypatch, {"advice": "Restart the router.", "steps": [{"action": "flush_dns"}]})
    jv._caretaker_store.ingest([NET])
    for _ in range(ct.MAX_ATTEMPTS):
        jv._caretaker_store.note_attempt(NET.key, "tried")
    jv._caretaker_fix_all()
    assert "flush_dns" not in jv._model_calls[0] and jv._admin_runs == []
    assert "ai:flush_dns" not in {a["action"] for a in jv._caretaker_store.recent_actions(10)}


def test_a_status_check_that_fails_closes_the_menu(jv, monkeypatch):
    monkeypatch.setattr(jv.caretaker_admin, "status", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no powershell")))
    ai.set_admin_ready(NAMES)
    _script(jv, monkeypatch, {"advice": "x"})
    jv._caretaker_store.ingest([NET])
    for _ in range(ct.MAX_ATTEMPTS):
        jv._caretaker_store.note_attempt(NET.key, "tried")
    jv._caretaker_fix_all()
    assert "flush_dns" not in jv._model_calls[0]


# --- setup / remove -------------------------------------------------------------------------------
def _setup_env(jv, monkeypatch, tmp_path, *, admin=True, rc=0, installed_after=True):
    monkeypatch.setattr(jv.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(jv.caretaker_admin, "is_admin_account", lambda *a, **k: admin)
    monkeypatch.setattr(jv.caretaker_admin, "current_user", lambda *a, **k: ME)
    seen = {}

    def run_cmd(argv, timeout=60):
        seen["argv"] = argv
        return rc, ""
    monkeypatch.setattr(jv.caretaker_win, "run_cmd", run_cmd)
    monkeypatch.setattr(jv.time, "sleep", lambda s: _REAL_SLEEP(0.001))
    monkeypatch.setattr(jv.caretaker_admin, "status", lambda *a, **k: {
        "supported": True, "known": True, "installed": installed_after, "ready": NAMES if installed_after else [],
        "changed": [], "actions": {}})
    return seen


def _wait_setup(jv):
    for _ in range(500):
        if (jv._caretaker_state.get("helper_setup") or {}).get("state") not in ("waiting", "checking"):
            if jv._helper_setup_lock.acquire(timeout=2):        # the worker lets go of the lock right after the state
                jv._helper_setup_lock.release()
            return jv._caretaker_state["helper_setup"]
        _REAL_SLEEP(0.02)
    raise AssertionError("setup never finished")


def test_setting_up_the_helper_raises_windows_prompt_and_reports_done(jv, monkeypatch, tmp_path):
    seen = _setup_env(jv, monkeypatch, tmp_path)
    res = jv._caretaker_helper_setup("install")
    assert res["ok"] and "Windows is asking" in res["message"]
    assert _wait_setup(jv)["state"] == "done"
    assert "-Verb RunAs" in adm.decode_ps_argv(seen["argv"])
    assert list((tmp_path / "Jarvis" / "helper_setup").glob("*.ps1")) == []      # the staged installer is deleted
    assert jv._helper_setup_lock.acquire(blocking=False) and (jv._helper_setup_lock.release() or True)


def test_a_declined_prompt_changes_nothing(jv, monkeypatch, tmp_path):
    _setup_env(jv, monkeypatch, tmp_path, rc=1, installed_after=False)
    assert jv._caretaker_helper_setup("install")["ok"]
    s = _wait_setup(jv)
    assert s["state"] == "declined" and "nothing changed" in s["detail"]


def _elevated_writes(jv, monkeypatch, text):
    """Make the fake 'elevated window' write `text` into the result file (None = write nothing)."""
    real = jv.caretaker_win.run_cmd

    def run_cmd(argv, timeout=60):
        rc, out = real(argv, timeout)
        if text is not None:
            m = re.search(r"\$r = '([^']+)'", _inner_stub(argv))
            Path(m.group(1)).write_text(text, encoding="utf-8")
        return rc, out
    monkeypatch.setattr(jv.caretaker_win, "run_cmd", run_cmd)


def test_after_the_prompt_is_accepted_the_page_says_it_is_checking_not_waiting(jv, monkeypatch, tmp_path):
    _setup_env(jv, monkeypatch, tmp_path, installed_after=False)
    states = []
    real_refresh = jv._caretaker_admin_refresh
    monkeypatch.setattr(jv, "_caretaker_admin_refresh",
                        lambda: states.append(jv._caretaker_state["helper_setup"]["state"]) or real_refresh())
    monkeypatch.setattr(jv, "HELPER_CHECK_WINDOW_S", 0.05)
    assert jv._caretaker_helper_setup("install")["ok"]
    _wait_setup(jv)
    assert states and set(states) == {"checking"}


def test_a_failure_inside_the_hidden_elevated_window_is_reported_with_its_reason(jv, monkeypatch, tmp_path):
    _setup_env(jv, monkeypatch, tmp_path, installed_after=False)
    _elevated_writes(jv, monkeypatch, "FAIL: could not lock the helper folder")
    assert jv._caretaker_helper_setup("install")["ok"]
    s = _wait_setup(jv)
    assert s["state"] == "failed" and "could not lock the helper folder" in s["detail"]
    assert list((tmp_path / "Jarvis" / "helper_setup").glob("*")) == []      # script and result file both cleaned up


def test_finished_but_not_confirmed_names_the_task_that_does_not_match(jv, monkeypatch, tmp_path):
    _setup_env(jv, monkeypatch, tmp_path, installed_after=False)
    _elevated_writes(jv, monkeypatch, "OK")
    monkeypatch.setattr(jv.caretaker_admin, "status", lambda *a, **k: {
        "supported": True, "known": True, "installed": False, "ready": [], "changed": [],
        "actions": {"flush_dns": {"ok": False, "why": "not set up"}}})
    assert jv._caretaker_helper_setup("install")["ok"]
    s = _wait_setup(jv)
    assert s["state"] == "failed" and "can't confirm" in s["detail"] and "flush dns: not set up" in s["detail"]


def test_finished_but_windows_cannot_be_read_says_so_with_the_reason(jv, monkeypatch, tmp_path):
    _setup_env(jv, monkeypatch, tmp_path, installed_after=False)
    _elevated_writes(jv, monkeypatch, "OK")
    monkeypatch.setattr(jv.caretaker_admin, "status", lambda *a, **k: {
        "supported": True, "known": False, "installed": False, "ready": [], "changed": [], "actions": {},
        "error": "PowerShell didn't answer (it may have timed out or been blocked)"})
    monkeypatch.setattr(jv, "HELPER_CHECK_WINDOW_S", 0.05)
    assert jv._caretaker_helper_setup("install")["ok"]
    s = _wait_setup(jv)
    assert s["state"] == "failed" and "can't read Windows' task list" in s["detail"] and "didn't answer" in s["detail"]


def test_the_wait_ends_by_the_clock_even_when_nothing_ever_answers(jv, monkeypatch, tmp_path):
    _setup_env(jv, monkeypatch, tmp_path, installed_after=False)
    monkeypatch.setattr(jv, "HELPER_CHECK_WINDOW_S", 0.05)
    assert jv._caretaker_helper_setup("install")["ok"]
    s = _wait_setup(jv)
    assert s["state"] == "failed" and "nothing confirmed it in time" in s["detail"]


def test_a_result_file_left_by_an_earlier_try_is_not_mistaken_for_this_one(jv, monkeypatch, tmp_path):
    _setup_env(jv, monkeypatch, tmp_path, installed_after=False)
    folder = tmp_path / "Jarvis" / "helper_setup"
    folder.mkdir(parents=True)
    (folder / "install_helper.result.txt").write_text("FAIL: old problem", encoding="utf-8")
    monkeypatch.setattr(jv, "HELPER_CHECK_WINDOW_S", 0.05)
    assert jv._caretaker_helper_setup("install")["ok"]
    s = _wait_setup(jv)
    assert "old problem" not in s["detail"]


def test_a_standard_account_is_told_so_and_nothing_is_staged(jv, monkeypatch, tmp_path):
    seen = _setup_env(jv, monkeypatch, tmp_path, admin=False)
    res = jv._caretaker_helper_setup("install")
    assert not res["ok"] and "isn't an administrator" in res["error"] and "argv" not in seen
    assert not (tmp_path / "Jarvis").exists()


def test_an_unreadable_user_name_installs_nothing(jv, monkeypatch, tmp_path):
    seen = _setup_env(jv, monkeypatch, tmp_path)
    monkeypatch.setattr(jv.caretaker_admin, "current_user", lambda *a, **k: "PC\\x'; calc #")
    res = jv._caretaker_helper_setup("install")
    assert not res["ok"] and "user name" in res["error"] and "argv" not in seen


def test_removing_the_helper_works_for_a_standard_account_too(jv, monkeypatch, tmp_path):
    _setup_env(jv, monkeypatch, tmp_path, admin=False, installed_after=False)
    assert jv._caretaker_helper_setup("remove")["ok"]
    assert _wait_setup(jv)["state"] == "done"


def test_only_one_setup_waits_at_a_time(jv, monkeypatch, tmp_path):
    _setup_env(jv, monkeypatch, tmp_path)
    assert jv._helper_setup_lock.acquire(blocking=False)
    try:
        res = jv._caretaker_helper_setup("install")
        assert not res["ok"] and "already waiting" in res["error"]
    finally:
        jv._helper_setup_lock.release()


def test_off_windows_the_helper_says_so(jv, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(jv.sys, "platform", "linux")
    assert "only works on Windows" in jv._caretaker_helper_setup("install")["error"]


# --- the tool and the page route ------------------------------------------------------------------
def test_setting_up_or_removing_the_helper_by_tool_needs_a_person_at_the_pc(jv, monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(jv, "_caretaker_helper_setup", lambda kind: started.append(kind) or {"ok": True, "message": "ok"})
    for src in ("phone", "scheduled", "autonomy", None):
        monkeypatch.setattr(jv, "_current_command_source", lambda s=src: s)
        for act in ("install_helper", "remove_helper"):
            assert jv._caretaker_tool({"action": act}).startswith("Tool failed")
    assert started == []
    monkeypatch.setattr(jv, "_current_command_source", lambda: "voice")
    assert jv._caretaker_tool({"action": "install_helper"}) == "ok" and started == ["install"]
    assert jv._caretaker_tool({"action": "remove_helper"}) == "ok" and started == ["install", "remove"]


def test_the_caretaker_tool_stays_blocked_in_untrusted_and_tainted_runs():
    import jarvis as j
    assert "caretaker" in j._UNTRUSTED_BLOCKED_TOOLS and "caretaker" in j._TAINT_BLOCKED_TOOLS


def test_the_helper_status_text_says_what_it_can_do(jv, monkeypatch):
    _helper(jv, monkeypatch)
    t = jv._caretaker_tool({"action": "helper"})
    assert "set up" in t and "DNS cache" in t and "temp folder" in t
    _helper(jv, monkeypatch, ready=[])
    assert "isn't set up" in jv._caretaker_tool({"action": "helper"})
    monkeypatch.setenv("JARVIS_CARETAKER_ADMIN", "0")
    assert "switched off" in jv._caretaker_tool({"action": "helper"})


def test_a_changed_helper_is_called_out_in_plain_words(jv, monkeypatch):
    st = _helper(jv, monkeypatch, ready=NAMES[1:])
    st["changed"] = ["flush_dns"]
    assert "no longer match" in jv._caretaker_tool({"action": "helper"})


def test_the_page_route_carries_the_helper_state_and_the_setup_buttons(jv, monkeypatch, tmp_path):
    _helper(jv, monkeypatch)
    rep = jv._feature_caretaker("helper_refresh", {})
    h = rep["helper"]
    assert h["enabled"] and h["installed"] and [a["name"] for a in h["actions"]] == NAMES and all(a["ok"] for a in h["actions"])
    _setup_env(jv, monkeypatch, tmp_path)
    monkeypatch.setattr(jv, "HELPER_CHECK_WINDOW_S", 0.2)      # the fake Windows never reports the removal
    res = jv._feature_caretaker("helper_install", {})
    assert res["ok"] and "helper" in res and "needs_admin" in res
    _wait_setup(jv)
    assert jv._feature_caretaker("helper_remove", {})["ok"]
    _wait_setup(jv)


def test_the_summary_for_the_page_never_starts_powershell(jv, monkeypatch):
    calls = []
    monkeypatch.setattr(jv.caretaker_admin, "status", lambda *a, **k: calls.append(1) or {})
    s = jv._caretaker_admin_summary()
    jv.caretaker_report()
    assert calls == [] and [a["name"] for a in s["actions"]] == NAMES


def test_each_scan_refreshes_the_helper_status_once(jv, monkeypatch):
    calls = []
    monkeypatch.setattr(jv.caretaker_admin, "status", lambda *a, **k: calls.append(1) or {"supported": True, "ready": [],
                                                                                        "actions": {}, "known": True})
    monkeypatch.setattr(jv, "_caretaker_scan", lambda: [])
    monkeypatch.setattr(jv, "_caretaker_fix_all", lambda: [])
    monkeypatch.setattr(jv, "_caretaker_housekeeping", lambda: None)
    monkeypatch.setattr(jv.dashboard, "notify", lambda *a, **k: None)
    jv._caretaker_run()
    assert calls == [1]
    monkeypatch.setenv("JARVIS_CARETAKER_ADMIN", "0")
    jv._caretaker_run()
    assert calls == [1]


def test_the_five_admin_actions_are_registered_for_the_ai_with_their_kinds_of_problem(jv):
    for name, cats in adm.AI_CATEGORIES.items():
        spec = ai.ACTIONS[name]
        assert spec["admin"] is True and spec["categories"] == cats and spec["bind"] == {}
    assert "clear_windows_temp" not in ai.ACTIONS


def test_the_page_lists_the_helper_block_and_buttons():
    html = open("dashboard_static/index.html", encoding="utf-8").read()
    js = open("dashboard_static/caretaker.js", encoding="utf-8").read()
    for ident in ("ct-helper-block", "ct-helper-status", "ct-helper-actions", "ct-helper-install", "ct-helper-remove"):
        assert f'id="{ident}"' in html and ident in js
    assert "helper_install" in js and "helper_remove" in js and "Windows will ask for permission" in js


def test_the_summary_for_the_page_carries_why_windows_could_not_be_read(jv, monkeypatch):
    monkeypatch.setitem(jv._caretaker_admin_cache, "status", {"supported": True, "known": False, "error": "PowerShell didn't answer"})
    s = jv._caretaker_admin_summary()
    assert s["known"] is False and s["error"] == "PowerShell didn't answer"
    assert all(not a["ok"] for a in s["actions"])
