"""Caretaker admin helper (phase 6, 2026-10-16): the few repairs that need administrator rights, done through a
small FIXED set of Windows Scheduled Tasks that run with highest privileges, registered once after the owner accepts
Windows' own "Do you want to allow this app to make changes?" prompt.

This is deliberately NOT "Jarvis runs as admin". What exists after the one-time setup:
- five tasks under \\Jarvis\\Caretaker\\, each running ONE fixed script from a folder only administrators can write
  (Program Files\\JarvisHelper). A task takes no input: there is no argument, file or message anyone (the AI, an
  email, a web page, another program) could use to make it do something else.
- before every run Jarvis re-reads the task definition and the script and refuses unless both are exactly what it
  installed (so a tampered helper is reported, not run).
- everything else (shutdown, format, wiping, force-closing programs, installing software) is not here and keeps
  its yes.
Removal goes through the same prompt. Never imports jarvis.py; the OS is reached through an injected `runner`, so all
of it is unit-tested with fakes (no PowerShell exists in the test container).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path, PureWindowsPath
from typing import Callable

import jarvis_caretaker_windows as win

IS_WIN = sys.platform == "win32"
TASK_PATH = "\\Jarvis\\Caretaker\\"
HELPER_DIRNAME = "JarvisHelper"
SCRIPT_TIMEOUT_S = 15 * 60

_NAME_RE = re.compile(r"^[a-z][a-z_]{1,31}$")
_USER_RE = re.compile(r"^[\w .\-@]{1,64}\\[\w .\-@]{1,64}$")

GREEN, YELLOW = "green", "yellow"      # same tiers as jarvis_caretaker


def _wrap(body: str) -> str:
    """Every script ends in an explicit exit code: 0 done, 1 failed, 3 'not now', 4 'nothing to do'."""
    return "$ErrorActionPreference = 'Stop'\n$code = 1\n" + body.strip("\n") + "\nexit $code\n"


# name -> what it is for (plain words, shown on the page), the exact script, how often it may run, what the codes mean.
ADMIN_ACTIONS: dict[str, dict] = {
    "flush_dns": {
        "desc": "Empty the DNS cache when websites stop resolving.",
        "tier": GREEN, "gap_min": 10, "timeout_s": 30, "did": "flushed the DNS cache",
        "codes": {},
        "script": _wrap("try { Clear-DnsClientCache; $code = 0 } catch { $code = 1 }"),
    },
    "restart_adapter": {
        "desc": "Restart the network adapter that is connected, when the router is unreachable.",
        "tier": GREEN, "gap_min": 30, "timeout_s": 90, "did": "restarted the network adapter",
        "codes": {4: "there is no connected network adapter to restart"},
        "script": _wrap(
            "try {\n"
            "  $a = @(Get-NetAdapter -Physical | Where-Object { $_.Status -eq 'Up' })\n"
            "  if ($a.Count -eq 0) { $code = 4 } else { $a | Restart-NetAdapter -Confirm:$false; $code = 0 }\n"
            "} catch { $code = 1 }"),
    },
    "update_defender": {
        "desc": "Update the Windows Defender virus definitions when they are old.",
        "tier": GREEN, "gap_min": 12 * 60, "timeout_s": 300, "did": "updated the virus definitions",
        "codes": {},
        "script": _wrap("try { Update-MpSignature; $code = 0 } catch { $code = 1 }"),
    },
    "reset_windows_update": {
        "desc": ("Reset a stuck Windows Update: the update download cache is renamed (kept 7 days, then removed) "
                 "and Windows rebuilds it. Not while an update is installing."),
        "tier": YELLOW, "gap_min": 7 * 24 * 60, "timeout_s": 180,
        "did": "reset the Windows Update download cache (the old one is kept 7 days)",
        "codes": {3: "Windows is installing an update right now, so I left it alone"},
        "script": _wrap(
            "if (Get-Process -Name 'TiWorker' -ErrorAction SilentlyContinue) { $code = 3 } else {\n"
            "  try {\n"
            "    Get-ChildItem -LiteralPath $env:SystemRoot -Directory -Filter 'SoftwareDistribution.jarvis-*' "
            "-ErrorAction SilentlyContinue | ForEach-Object {\n"
            "      if ($_.Name -match '^SoftwareDistribution\\.jarvis-(\\d{8}-\\d{6})$') {\n"
            "        $d = [datetime]::ParseExact($Matches[1], 'yyyyMMdd-HHmmss', $null)\n"
            "        if ($d -lt (Get-Date).AddDays(-7)) { Remove-Item -LiteralPath $_.FullName -Recurse -Force "
            "-ErrorAction SilentlyContinue }\n"
            "      }\n"
            "    }\n"
            "    Stop-Service -Name 'wuauserv' -Force\n"
            "    Stop-Service -Name 'bits' -Force\n"
            "    $new = 'SoftwareDistribution.jarvis-' + (Get-Date -Format 'yyyyMMdd-HHmmss')\n"
            "    Rename-Item -LiteralPath (Join-Path $env:SystemRoot 'SoftwareDistribution') -NewName $new\n"
            "    $code = 0\n"
            "  } catch { $code = 1 } finally {\n"
            "    Start-Service -Name 'bits' -ErrorAction SilentlyContinue\n"
            "    Start-Service -Name 'wuauserv' -ErrorAction SilentlyContinue\n"
            "  }\n"
            "}"),
    },
    "clear_windows_temp": {
        "desc": "Delete files in the Windows temp folder that are more than 7 days old (programs in use are skipped).",
        "tier": GREEN, "gap_min": 24 * 60, "timeout_s": 300, "did": "cleared old Windows temp files",
        "codes": {},
        "script": _wrap(
            "try {\n"
            "  $cut = (Get-Date).AddDays(-7)\n"
            "  Get-ChildItem -LiteralPath (Join-Path $env:SystemRoot 'Temp') -Recurse -Force -File "
            "-ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -lt $cut } | "
            "Remove-Item -Force -ErrorAction SilentlyContinue\n"
            "  $code = 0\n"
            "} catch { $code = 1 }"),
    },
}

for _n in ADMIN_ACTIONS:           # a name ends up inside a path and a task name: keep it boring
    assert _NAME_RE.match(_n), _n

# Which kinds of problem the AI planner may use an admin action for (jarvis_caretaker_ai.register_action). The storage
# cleanup is not here on purpose: the storage playbook already runs it by itself, and storage is never sent to the model.
AI_CATEGORIES: dict[str, set] = {
    "flush_dns": {"network"}, "restart_adapter": {"network"},
    "update_defender": {"update"}, "reset_windows_update": {"update"},
}


# --- pieces of PowerShell --------------------------------------------------------------------------
def _psq(s: str) -> str:
    """A PowerShell single-quoted string literal (nothing inside is expanded)."""
    return "'" + str(s).replace("'", "''") + "'"


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-16-le")).decode("ascii")


def ps_argv(script: str) -> list[str]:
    """powershell.exe with the script as -EncodedCommand: no quoting to get wrong, whatever the script holds."""
    return ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", _b64(script)]


def decode_ps_argv(argv: list[str]) -> str:
    """The script inside a `ps_argv` (used by tests and the self-check)."""
    return base64.b64decode(argv[argv.index("-EncodedCommand") + 1]).decode("utf-16-le")


def helper_dir(env=None) -> PureWindowsPath:
    env = os.environ if env is None else env
    return PureWindowsPath(env.get("ProgramFiles") or r"C:\Program Files") / HELPER_DIRNAME


def script_path(name: str, env=None) -> str:
    return str(helper_dir(env)) + "\\" + name + ".ps1"


def task_arguments(name: str, env=None) -> str:
    return ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "%s"'
            % script_path(name, env))


def valid_user(user: str) -> bool:
    return bool(_USER_RE.match(user or ""))


def current_user(env=None) -> str:
    env = os.environ if env is None else env
    dom, name = env.get("USERDOMAIN") or env.get("COMPUTERNAME") or "", env.get("USERNAME") or ""
    return f"{dom}\\{name}" if dom and name else ""


# --- the one-time installer / remover (run elevated, after the owner accepts Windows' prompt) ------------
def install_script(user: str, env=None) -> str:
    """Creates the admin-only folder with the five fixed scripts and registers the five on-demand tasks."""
    if not valid_user(user):
        raise ValueError("unusable Windows user name")
    d = str(helper_dir(env))
    rows = ",\n".join(f"  @({_psq(n)}, {_psq(_b64_utf8(a['script']))})" for n, a in ADMIN_ACTIONS.items())
    return (
        "$ErrorActionPreference = 'Stop'\n"
        f"$user = {_psq(user)}\n"
        f"$dir = {_psq(d)}\n"
        f"$taskPath = {_psq(TASK_PATH)}\n"
        "if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }\n"
        "& icacls.exe $dir /inheritance:r /grant:r 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' "
        "'Users:(OI)(CI)RX' | Out-Null\n"
        "if ($LASTEXITCODE -ne 0) { throw 'could not lock the helper folder' }\n"
        "$tasks = @(\n" + rows + "\n)\n"
        "foreach ($t in $tasks) {\n"
        "  $p = Join-Path $dir ($t[0] + '.ps1')\n"
        "  $text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($t[1]))\n"
        "  [IO.File]::WriteAllText($p, $text, (New-Object Text.UTF8Encoding($false)))\n"
        "  $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "
        "('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File \"' + $p + '\"')\n"
        "  $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest\n"
        f"  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        f"-MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds {SCRIPT_TIMEOUT_S})\n"
        "  Register-ScheduledTask -TaskName $t[0] -TaskPath $taskPath -Action $action -Principal $principal "
        "-Settings $settings -Description 'Jarvis Caretaker: one fixed repair, started only by Jarvis' -Force | "
        "Out-Null\n"
        "}\n")


def _b64_utf8(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def remove_script(env=None) -> str:
    return (
        "$ErrorActionPreference = 'SilentlyContinue'\n"
        f"Get-ScheduledTask -TaskPath {_psq(TASK_PATH)} | Unregister-ScheduledTask -Confirm:$false\n"
        f"Remove-Item -LiteralPath {_psq(str(helper_dir(env)))} -Recurse -Force\n")


def launcher_argv(script_text: str, script_file: str) -> list[str]:
    """The command Jarvis (not elevated) runs to raise Windows' "allow this app to make changes?" prompt. The
    elevated side reads the script file ONCE into memory, checks its SHA-256 against the value fixed here, and only
    then runs that text, so nothing written to the file after this point can run elevated."""
    digest = hashlib.sha256(script_text.encode("utf-8")).hexdigest()
    stub = (
        f"$f = {_psq(script_file)}\n"
        "$t = [IO.File]::ReadAllText($f)\n"
        "$h = ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash("
        "[Text.Encoding]::UTF8.GetBytes($t))) -replace '-', '').ToLower()\n"
        f"if ($h -ne {_psq(digest)}) {{ exit 9 }}\n"
        "Invoke-Expression $t\n")
    launcher = (
        "$ErrorActionPreference = 'Stop'\n"
        "Start-Process -FilePath 'powershell.exe' -Verb RunAs -WindowStyle Hidden -ArgumentList @("
        f"'-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', {_psq(_b64(stub))})\n")
    return ps_argv(launcher)


def stage_script(text: str, dest_dir: Path, filename: str) -> str:
    """Write an installer/remover where only this user writes (the hash in `launcher_argv` makes that safe)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    p = dest_dir / filename
    p.write_bytes(text.encode("utf-8"))
    return str(p)


# --- reading what is installed -----------------------------------------------------------------------
_STATUS_SCRIPT = (
    "$ErrorActionPreference = 'SilentlyContinue'\n"
    "$rows = @(Get-ScheduledTask -TaskPath " + _psq(TASK_PATH) + " | ForEach-Object {\n"
    "  $i = $_ | Get-ScheduledTaskInfo\n"
    "  [pscustomobject]@{ name = $_.TaskName; state = [string]$_.State; level = [string]$_.Principal.RunLevel;\n"
    "    user = [string]$_.Principal.UserId; actions = @($_.Actions).Count; exe = [string]$_.Actions[0].Execute;\n"
    "    args = [string]$_.Actions[0].Arguments; last = $i.LastRunTime.ToString('o'); code = [int]$i.LastTaskResult }\n"
    "})\n"
    "ConvertTo-Json -InputObject $rows -Compress\n")


def _read_tasks(runner: Callable) -> list[dict] | None:
    """The tasks under \\Jarvis\\Caretaker\\ as dicts, or None when Windows can't be asked."""
    rc, out = runner(ps_argv(_STATUS_SCRIPT))
    if rc != 0:
        return None
    out = (out or "").strip()
    if not out:
        return []
    try:
        data = json.loads(out)
    except ValueError:
        return None
    if isinstance(data, dict):
        data = [data]
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else None


def _user_key(u: str) -> str:
    return (u or "").split("\\")[-1].strip().lower()


def _script_text(path: str, reader: Callable[[str], str | None]) -> str | None:
    t = reader(path)
    return None if t is None else t.lstrip("\ufeff").replace("\r\n", "\n")


def _read_file(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def status(runner: Callable = win.run_cmd, *, env=None, reader: Callable[[str], str | None] = _read_file,
           me: str | None = None) -> dict:
    """{"supported", "actions": {name: {"ok", "why", "state", "last", "code"}}, "ready": [names that may run],
    "changed": [names whose task or script is not what was installed], "installed": bool (all five usable)}."""
    out = {"supported": IS_WIN or runner is not win.run_cmd, "actions": {}, "ready": [], "changed": [],
           "installed": False, "known": False}
    if not out["supported"]:
        return out
    rows = _read_tasks(runner)
    if rows is None:
        return out
    out["known"] = True
    by_name = {r.get("name"): r for r in rows}
    me_key = _user_key(me if me is not None else current_user(env))
    for name, spec in ADMIN_ACTIONS.items():
        r = by_name.get(name)
        if r is None:
            out["actions"][name] = {"ok": False, "why": "not set up"}
            continue
        why = None
        if r.get("exe", "").lower() != "powershell.exe" or int(r.get("actions") or 0) != 1 \
                or r.get("args") != task_arguments(name, env):
            why = "the task was changed"
        elif r.get("level") != "Highest":
            why = "the task doesn't run with administrator rights"
        elif me_key and _user_key(r.get("user", "")) != me_key:
            why = "the task belongs to another Windows user"
        elif r.get("state") == "Disabled":
            why = "the task is switched off in Windows"
        else:
            text = _script_text(script_path(name, env), reader)
            if text is None:
                why = "its script is missing"
            elif text != spec["script"].replace("\r\n", "\n"):
                why = "its script was changed"
        out["actions"][name] = {"ok": why is None, "why": why, "state": r.get("state"), "last": r.get("last"),
                                "code": r.get("code")}
        if why is None:
            out["ready"].append(name)
        elif why in ("the task was changed", "its script was changed", "its script is missing",
                     "the task doesn't run with administrator rights"):
            out["changed"].append(name)
    out["installed"] = len(out["ready"]) == len(ADMIN_ACTIONS)
    return out


def is_admin_account(runner: Callable = win.run_cmd) -> bool | None:
    """True when this Windows user is in the Administrators group (a split-token admin still lists it, as 'deny
    only'), False for a standard user (the helper could not elevate anything), None when unknown."""
    rc, out = runner(["whoami", "/groups", "/fo", "csv", "/nh"])
    if rc != 0 or not out:
        return None
    return "S-1-5-32-544" in out


# --- running one action ---------------------------------------------------------------------------------
def run_action(name: str, *, runner: Callable = win.run_cmd, sleep: Callable[[float], None] = time.sleep,
               now: Callable[[], float] = time.monotonic, env=None, reader: Callable[[str], str | None] = _read_file,
               me: str | None = None, poll_s: float = 2.0) -> dict:
    """Start one installed task and wait for it. {"ok", "skipped", "code", "detail"}; `skipped` = it chose not to
    act (an update is installing, nothing to restart), which is not a failure."""
    spec = ADMIN_ACTIONS.get(name)
    if spec is None:
        return {"ok": False, "skipped": False, "code": None, "detail": "that isn't one of my admin actions"}
    st = status(runner, env=env, reader=reader, me=me)
    a = st["actions"].get(name) or {}
    if not st["known"]:
        return {"ok": False, "skipped": False, "code": None, "detail": "I can't ask Windows about the helper"}
    if not a.get("ok"):
        return {"ok": False, "skipped": False, "code": None,
                "detail": "the admin helper isn't ready: " + str(a.get("why") or "not set up")}
    before = a.get("last")
    rc, _ = runner(ps_argv(f"Start-ScheduledTask -TaskPath {_psq(TASK_PATH)} -TaskName {_psq(name)}"))
    if rc != 0:
        return {"ok": False, "skipped": False, "code": None, "detail": "Windows wouldn't start the helper task"}
    started = now()
    seen_running = False
    while now() - started < spec["timeout_s"]:
        sleep(poll_s)
        cur = (_read_tasks(runner) or [])
        row = next((r for r in cur if r.get("name") == name), None)
        if row is None:
            continue
        state = row.get("state")
        if state in ("Running", "Queued"):
            seen_running = True
            continue
        if row.get("last") != before or seen_running:
            code = row.get("code")
            if code == 0:
                return {"ok": True, "skipped": False, "code": 0, "detail": spec["did"]}
            if code in spec["codes"]:
                return {"ok": False, "skipped": True, "code": code, "detail": spec["codes"][code]}
            return {"ok": False, "skipped": False, "code": code, "detail": f"the helper reported an error (code {code})"}
        if now() - started > 20:      # still 'Ready' with no new run after 20 s: it never started
            return {"ok": False, "skipped": False, "code": None, "detail": "the helper task never started"}
    return {"ok": False, "skipped": False, "code": None, "detail": "the helper took too long"}


def describe() -> list[dict]:
    """What the page shows before the owner agrees: every fixed action in plain words."""
    return [{"name": n, "desc": a["desc"], "tier": a["tier"]} for n, a in ADMIN_ACTIONS.items()]
