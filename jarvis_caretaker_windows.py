"""Caretaker Windows playbooks (phase 4, 2026-10-16): the small, reversible things Jarvis may do on its own to the
laptop itself, without administrator rights. The OS is reached through injected callables / a psutil-shaped object,
so every function here is unit-tested with fakes; nothing is run unless jarvis.py calls it.

What is here and, just as important, what is not:
- a CPU hog that is not what the user is working in gets its priority lowered (undoable). It is NEVER closed: a
  windowless process can be a render, an encode or a build, and closing it loses work.
- a network problem gets a re-check, a DNS-cache flush or a Wi-Fi reconnect; anything that needs administrator
  rights is reported as `needs_admin` for the phase-6 helper instead of being attempted.
- an app that keeps crashing gets its own cache folders cleared (only while it isn't running).
- a failing disk is never "fixed": the finding says so.
Never imports jarvis.py.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import jarvis_caretaker_fix as cfix

IS_WIN = sys.platform == "win32"

# Windows priority classes (psutil exposes the same numbers on Windows only)
BELOW_NORMAL, IDLE, NORMAL = 0x4000, 0x40, 0x20

# Never touched, even to lower the priority: the shell, the security stack, drivers' hosts, Jarvis itself.
PROTECTED_PROCESSES = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe", "msmpeng.exe", "nissrv.exe",
    "audiodg.exe", "fontdrvhost.exe", "sihost.exe", "ctfmon.exe", "searchhost.exe", "runtimebroker.exe",
    "startmenuexperiencehost.exe", "shellexperiencehost.exe", "taskhostw.exe", "securityhealthservice.exe",
    "memcompression", "vmmem", "python.exe", "pythonw.exe", "jarvis", "cmd.exe", "powershell.exe", "pwsh.exe",
    "windowsterminal.exe", "conhost.exe",
}


def _psutil():
    try:
        import psutil
        return psutil
    except ImportError:
        return None


def _user_key(name: str | None) -> str:
    return (name or "").split("\\")[-1].strip().lower()


def current_user(ps=None) -> str:
    ps = ps or _psutil()
    try:
        return _user_key(ps.Process().username())
    except Exception:
        return _user_key(os.environ.get("USERNAME") or os.environ.get("USER"))


# --- 1. a runaway process: lower its priority (undoable), never close it -----------------------------
def lower_priority(name: str, *, psutil_mod=None, me: str | None = None) -> dict:
    """Lower every instance of `name` that belongs to the current user to below-normal priority.
    Returns {"changed": [{"pid", "prev"}], "skipped": int, "reason": str|None, "protected": bool}."""
    ps = psutil_mod or _psutil()
    if ps is None:
        return {"changed": [], "skipped": 0, "protected": False, "reason": "I can't read the process list here."}
    low = (name or "").strip().lower()
    if not low or low in PROTECTED_PROCESSES:
        return {"changed": [], "skipped": 0, "protected": True,
                "reason": f"{name or 'That'} is a Windows, security or system process, so I leave it alone."}
    me = _user_key(me) or current_user(ps)
    below = getattr(ps, "BELOW_NORMAL_PRIORITY_CLASS", BELOW_NORMAL)
    idle = getattr(ps, "IDLE_PRIORITY_CLASS", IDLE)
    changed, skipped = [], 0
    for p in ps.process_iter(["name", "pid"]):
        try:
            if (p.info.get("name") or "").strip().lower() != low:
                continue
            if me and _user_key(p.username()) != me:
                skipped += 1               # someone else's or the system's: not mine to change
                continue
            prev = p.nice()
            if prev in (below, idle):
                skipped += 1
                continue
            p.nice(below)
            changed.append({"pid": p.pid, "prev": prev})
        except (getattr(ps, "Error", OSError), OSError):
            skipped += 1
    reason = None if changed else ("It was already at a low priority." if skipped else "It isn't running any more.")
    return {"changed": changed, "skipped": skipped, "protected": False, "reason": reason}


def restore_priority(info: dict, *, psutil_mod=None) -> str:
    """Undo `lower_priority`: put each process back, but only when the pid still belongs to the same program."""
    ps = psutil_mod or _psutil()
    name = (info or {}).get("name", "")
    done = 0
    for item in (info or {}).get("items", []):
        try:
            p = ps.Process(int(item["pid"]))
            if (p.name() or "").strip().lower() != name.strip().lower():
                continue                   # the pid was reused by another program
            p.nice(int(item.get("prev", NORMAL)))
            done += 1
        except Exception:
            continue
    if done:
        return f"Put back the normal priority of {name} ({done} process(es))."
    return f"Nothing to put back: {name or 'that program'} isn't running any more."


# --- 2. network: look again, flush the DNS cache, reconnect Wi-Fi ------------------------------------
def run_cmd(cmd: list[str], timeout: int = 25) -> tuple[int, str]:
    """Run one command without a window. (return code, combined output); (-1, '') when it can't run."""
    if not IS_WIN:
        return -1, ""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError):
        return -1, ""


_WLAN_PROFILE_RE = re.compile(r"^\s*Profile\s*:\s*(.+?)\s*$", re.I | re.M)


def wlan_profile(runner: Callable = run_cmd) -> str:
    """The Wi-Fi profile this PC is connected to ('' = wired, not connected or unknown)."""
    rc, out = runner(["netsh", "wlan", "show", "interfaces"])
    m = _WLAN_PROFILE_RE.search(out or "") if rc == 0 else None
    name = m.group(1) if m else ""
    # the name goes to netsh as one argument (no shell), but keep to what a profile name can sensibly hold
    return name if name and len(name) <= 64 and not re.search(r"[\x00-\x1f\"]", name) else ""


def fix_network(detail: str, *, recheck: Callable[[], bool], runner: Callable = run_cmd,
                sleep: Callable[[float], None] = time.sleep, settle_s: float = 15.0) -> dict:
    """Try the harmless fixes in order, checking after each. `recheck()` is True when the network works.
    Returns {"cleared": bool, "steps": [what was done], "needs_admin": [helper action names]}."""
    steps: list[str] = []
    needs_admin: list[str] = []
    sleep(settle_s)                      # many blips clear alone
    if recheck():
        return {"cleared": True, "steps": ["waited, and it came back by itself"], "needs_admin": []}
    if detail == "dns_failing":
        rc, out = runner(["ipconfig", "/flushdns"])
        if rc == 0:
            steps.append("flushed the DNS cache")
            sleep(2)
            if recheck():
                return {"cleared": True, "steps": steps, "needs_admin": []}
        else:
            needs_admin.append("flush_dns")   # Windows wants administrator rights for this one
    else:                                    # gateway_unreachable / adapter_down
        profile = wlan_profile(runner)
        if profile:
            runner(["netsh", "wlan", "disconnect"])
            sleep(2)
            rc, _ = runner(["netsh", "wlan", "connect", f"name={profile}"])
            steps.append(f"reconnected to the Wi-Fi network '{profile}'" if rc == 0
                         else "tried to reconnect to the Wi-Fi network")
            sleep(8)
            if recheck():
                return {"cleared": True, "steps": steps, "needs_admin": []}
        else:
            needs_admin.append("restart_adapter")   # a wired adapter can only be restarted with admin rights
    return {"cleared": False, "steps": steps, "needs_admin": needs_admin}


# --- 3. an app that keeps crashing: clear its own caches (only while it isn't running) ---------------
def app_cache_dirs(app: str, env=None) -> list[Path]:
    """Cache folders of a few well-known apps (fixed list, nothing guessed)."""
    env = os.environ if env is None else env
    local, roam = env.get("LOCALAPPDATA"), env.get("APPDATA")
    stem = (app or "").lower().removesuffix(".exe")
    out: list[Path] = []
    if local:
        L = Path(local)
        if stem in ("opera", "opera_gx", "opera gx", "launcher"):
            out = [L / "Opera Software" / "Opera GX Stable" / "Cache",
                   L / "Opera Software" / "Opera GX Stable" / "Code Cache",
                   L / "Opera Software" / "Opera GX Stable" / "GPUCache"]
        elif stem == "chrome":
            out = [L / "Google" / "Chrome" / "User Data" / "Default" / "Cache",
                   L / "Google" / "Chrome" / "User Data" / "Default" / "Code Cache",
                   L / "Google" / "Chrome" / "User Data" / "Default" / "GPUCache"]
        elif stem == "msedge":
            out = [L / "Microsoft" / "Edge" / "User Data" / "Default" / "Cache",
                   L / "Microsoft" / "Edge" / "User Data" / "Default" / "Code Cache",
                   L / "Microsoft" / "Edge" / "User Data" / "Default" / "GPUCache"]
    if roam and stem == "discord":
        R = Path(roam)
        out = [R / "discord" / "Cache", R / "discord" / "Code Cache", R / "discord" / "GPUCache"]
    if roam and stem in ("teams", "ms-teams"):
        out = [Path(roam) / "Microsoft" / "Teams" / "Cache"]
    return [p for p in out if p.is_dir()]


def is_running(app: str, *, psutil_mod=None) -> bool:
    ps = psutil_mod or _psutil()
    if ps is None:
        return True       # can't tell: assume it is, and touch nothing
    low = (app or "").lower()
    low_exe = low if low.endswith(".exe") else low + ".exe"
    try:
        return any((p.info.get("name") or "").lower() in (low, low_exe) for p in ps.process_iter(["name"]))
    except Exception:
        return True


def clear_app_cache(app: str, *, psutil_mod=None, env=None) -> dict:
    """{"freed", "files", "dirs", "why_not"}: why_not is set (and nothing is touched) when the app is running or has
    no known cache folder."""
    dirs = app_cache_dirs(app, env)
    if not dirs:
        return {"freed": 0, "files": 0, "dirs": 0, "why_not": "no cache folder I know of"}
    if is_running(app, psutil_mod=psutil_mod):
        return {"freed": 0, "files": 0, "dirs": len(dirs), "why_not": "it is running right now"}
    r = cfix.clear_caches(dirs, min_age_days=0)
    return {"freed": r["freed"], "files": r["files"], "dirs": len(dirs), "why_not": None}
