"""Caretaker sensors (2026-10-16): the OS-facing half of jarvis_caretaker. Reads only, never changes anything.

Every probe is independent and fail-soft (a missing tool, a non-Windows machine or a permission error returns
nothing, never raises), so one broken sensor can't blind the rest. Never imports jarvis.py: jarvis.py passes in
what it owns (DB connect, MCP failures, doctor problems). Output is jarvis_caretaker.Finding objects.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import jarvis_caretaker as ct
import jarvis_caretaker_ai as ct_ai

IS_WIN = sys.platform == "win32"
_cpu_since: dict[str, float] = {}   # process name -> monotonic time it first went above the CPU threshold
_disk_first_today: dict[str, tuple[str, float]] = {}   # drive -> (date, used_gb at first look today)


def _ps(script: str, timeout: int = 20) -> str:
    """Run one PowerShell snippet, return stdout ('' on any failure). Windows only."""
    if not IS_WIN:
        return ""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                           capture_output=True, text=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


# --- reclaimable space: sizes of folders that rebuild themselves (read-only walk, bounded) ------
def cache_roots() -> list[Path]:
    """Folders whose contents regenerate. Deliberately a fixed list: the caretaker never guesses."""
    roots: list[Path] = [Path(tempfile.gettempdir())]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        L = Path(local)
        # Not uv's cache: its archive-v0 folder holds the unpacked Python environments that `uvx` runs tools from
        # (Windows-MCP, ...). Deleting single old files there leaves a half-package ("No module named
        # 'windows_mcp.__main__'", 2026-10-16). Only `uv cache clean` may empty it.
        roots += [L / "Temp", L / "npm-cache", L / "pip" / "Cache",
                  L / "CrashDumps", L / "Microsoft" / "Windows" / "INetCache",
                  L / "Opera Software" / "Opera GX Stable" / "Cache",
                  L / "Opera Software" / "Opera GX Stable" / "Code Cache",
                  L / "Google" / "Chrome" / "User Data" / "Default" / "Cache",
                  L / "Microsoft" / "Edge" / "User Data" / "Default" / "Cache"]
    roam = os.environ.get("APPDATA")
    if roam:
        R = Path(roam)
        roots += [R / "discord" / "Cache", R / "discord" / "Code Cache", R / "Microsoft" / "Teams" / "Cache"]
    seen, out = set(), []
    for p in roots:
        try:
            rp = p.resolve()
        except OSError:
            continue
        if rp not in seen and rp.is_dir():
            seen.add(rp)
            out.append(rp)
    return out


def folder_size(path: Path, limit_files: int = 60000) -> int:
    """Total bytes under path, bounded so a huge cache can't stall a tick; symlinks never followed."""
    total, seen = 0, 0
    stack = [path]
    while stack and seen < limit_files:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    seen += 1
                    try:
                        if e.is_symlink():
                            continue
                        if e.is_dir(follow_symlinks=False):
                            stack.append(Path(e.path))
                        else:
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


# --- sensors -------------------------------------------------------------------------------------
def probe_storage() -> list[ct.Finding]:
    try:
        import psutil
    except ImportError:
        return []
    out: list[ct.Finding] = []
    today = datetime.now().date().isoformat()
    reclaimable = None
    for part in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        drive = part.device.rstrip("\\") or part.mountpoint
        used_gb = u.used / 1024 ** 3
        first = _disk_first_today.get(drive)
        if not first or first[0] != today:
            _disk_first_today[drive] = first = (today, used_gb)
        if u.percent >= ct.DISK_WARN_PERCENT and reclaimable is None:
            reclaimable = sum(folder_size(r) for r in cache_roots()) / 1024 ** 3
        f = ct.storage_finding(drive, u.percent, u.free / 1024 ** 3,
                               reclaimable_gb=reclaimable or 0.0,
                               grew_gb_today=max(0.0, used_gb - first[1]))
        if f:
            f.evidence["mount"] = part.mountpoint
            out.append(f)
    return out


def probe_processes(front_process_name: str = "") -> list[ct.Finding]:
    try:
        import psutil
    except ImportError:
        return []
    now, hot = time.monotonic(), {}
    skip = {"system idle process", "system", "idle", "jarvis", "python.exe", "pythonw.exe"}
    for p in psutil.process_iter(["name", "pid"]):
        try:
            name = (p.info["name"] or "").strip()
            if not name or name.lower() in skip:
                continue
            cpu = p.cpu_percent(interval=None) / max(1, psutil.cpu_count() or 1)
            if cpu >= ct.PROCESS_CPU_PERCENT:
                hot[name] = (max(cpu, hot.get(name, (0, 0))[0]), p.info["pid"])
        except (psutil.Error, OSError):
            continue
    for name in list(_cpu_since):
        if name not in hot:
            _cpu_since.pop(name, None)
    out = []
    for name, (cpu, pid) in hot.items():
        since = _cpu_since.setdefault(name, now)
        f = ct.process_finding(name, cpu, (now - since) / 60.0,
                               in_front=name.lower() == (front_process_name or "").lower(), pid=pid)
        if f:
            out.append(f)
    return out


def probe_crashes() -> list[ct.Finding]:
    """Application crash events (1000) since midnight, grouped by app. Windows only."""
    raw = _ps("Get-WinEvent -FilterHashtable @{LogName='Application';Id=1000;StartTime=(Get-Date).Date} "
              "-ErrorAction SilentlyContinue | ForEach-Object { $_.Properties[0].Value + '|' + $_.Properties[3].Value }")
    counts: dict[str, tuple[int, str]] = {}
    for line in raw.splitlines():
        app, _, mod = line.strip().partition("|")
        if app:
            n, m = counts.get(app, (0, ""))
            counts[app] = (n + 1, mod or m)
    return [f for app, (n, mod) in counts.items() if (f := ct.crash_finding(app, n, mod))]


def probe_disk_health() -> list[ct.Finding]:
    raw = _ps("Get-PhysicalDisk | ForEach-Object { $_.DeviceId + '|' + $_.HealthStatus }")
    out = []
    for line in raw.splitlines():
        dev, _, status = line.strip().partition("|")
        if dev and (f := ct.disk_health_finding(dev, status)):
            out.append(f)
    return out


def probe_updates() -> list[ct.Finding]:
    failed = _ps("(Get-WinEvent -FilterHashtable @{LogName='System';ProviderName='Microsoft-Windows-WindowsUpdateClient';"
                 "Id=20;StartTime=(Get-Date).AddDays(-7)} -ErrorAction SilentlyContinue | Measure-Object).Count").strip()
    age = _ps("((Get-Date) - (Get-MpComputerStatus).AntivirusSignatureLastUpdated).Days").strip()
    f = ct.update_finding(int(failed) if failed.isdigit() else 0, int(age) if age.lstrip("-").isdigit() else None)
    return [f] if f else []


def probe_network() -> list[ct.Finding]:
    import socket
    dns_ok = True
    try:
        socket.setdefaulttimeout(3)
        socket.gethostbyname("www.cloudflare.com")
    except OSError:
        dns_ok = False
    # a raw TCP connect to a public IP separates "no internet" from "DNS broken" without ICMP/admin rights
    link_ok = False
    for ip in ("1.1.1.1", "8.8.8.8"):
        try:
            with socket.create_connection((ip, 443), timeout=3):
                link_ok = True
                break
        except OSError:
            continue
    f = ct.network_finding(gateway_ok=link_ok, dns_ok=dns_ok, adapter_up=link_ok or dns_ok or _any_adapter_up())
    return [f] if f else []


def _any_adapter_up() -> bool:
    try:
        import psutil
        return any(s.isup for n, s in psutil.net_if_stats().items() if "loopback" not in n.lower())
    except Exception:
        return True


def probe_battery() -> list[ct.Finding]:
    raw = _ps("$b=Get-CimInstance -Namespace root\\wmi -ClassName BatteryFullChargedCapacity -ErrorAction SilentlyContinue;"
              "$s=Get-CimInstance -Namespace root\\wmi -ClassName BatteryStaticData -ErrorAction SilentlyContinue;"
              "if($b -and $s){[math]::Round($b.FullChargedCapacity/$s.DesignedCapacity,3)}").strip()
    try:
        f = ct.battery_finding(float(raw)) if raw else None
    except ValueError:
        f = None
    return [f] if f else []


def probe_self(conn_factory, mcp_failed: dict | None = None, doctor_problems: list | None = None) -> list[ct.Finding]:
    """Jarvis's own repeated failures, read from the tables it already writes."""
    out: list[ct.Finding] = []
    try:
        conn = conn_factory()
    except Exception:
        conn = None
    if conn is not None:
        try:
            # scheduled skills: consecutive failed sessions per skill name (transcript is "<skill>: <line>")
            rows = conn.execute("SELECT transcript,status,COALESCE(reply,'') FROM dashboard_sessions "
                                "WHERE source='scheduled' ORDER BY id DESC LIMIT 200").fetchall()
            streak: dict[str, list] = {}   # name -> [consecutive failures, last error, closed]
            for transcript, status, reply in rows:
                name = transcript.split(":", 1)[0].strip()
                if not name or status == "active":
                    continue
                s = streak.setdefault(name, [0, "", False])
                if s[2]:
                    continue
                if status == "failed":
                    s[0] += 1
                    s[1] = s[1] or (reply or "failed")[:160]
                else:
                    s[2] = True
            for name, (n, err, _) in streak.items():
                if f := ct.self_failure_finding("skill", name, err, n):
                    out.append(f)
        except Exception:
            pass
        try:
            rows = conn.execute("SELECT instruction,COALESCE(result,'') FROM autonomy_deferred_jobs "
                                "WHERE status='failed' AND finished_at >= datetime('now','-2 days')").fetchall()
            for instruction, result in rows:
                key = " ".join(instruction.split()[:6])
                if f := ct.self_failure_finding("job", key, result[:160] or "failed", 2):
                    out.append(f)
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
    if conn_factory is not None:
        try:
            c2 = conn_factory()
            try:
                # an agent whose last run failed (the agents module already says so once and then stays quiet)
                for name, result in c2.execute("SELECT name,COALESCE(last_result,'') FROM background_agents "
                                               "WHERE enabled=1 AND last_ok=0").fetchall():
                    if f := ct.self_failure_finding("agent", name, result[:160] or "failed", 2):
                        out.append(f)
            finally:
                c2.close()
        except Exception:
            pass   # no agents table yet, or the column set differs: not a problem to report
    for name, info in (mcp_failed or {}).items():
        if f := ct.self_failure_finding("mcp", name, "could not connect", 1):
            out.append(f)
    for p in doctor_problems or []:
        if p.get("quiet"):
            continue
        if f := ct.self_failure_finding("doctor", p.get("name", "check"), p.get("detail", ""), 1):
            f.evidence["fix"] = p.get("fix", "")
            out.append(f)
    return out


def run_all(*, conn_factory=None, mcp_failed=None, doctor_problems=None, front_process_name: str = "",
            skip: set[str] | None = None, report: dict | None = None) -> list[ct.Finding]:
    """Every sensor, each isolated. `skip` names sensors to leave out (settings / tests). `report["ok"]` is filled
    with the sensors that ran without error, so a skipped or crashed one never "resolves" its issues."""
    skip = skip or set()
    ok: set[str] = set()
    sensors = [
        ("storage", probe_storage), ("processes", lambda: probe_processes(front_process_name)),
        ("crashes", probe_crashes), ("disk_health", probe_disk_health), ("updates", probe_updates),
        ("network", probe_network), ("battery", probe_battery),
        ("self", lambda: probe_self(conn_factory, mcp_failed, doctor_problems) if conn_factory else []),
    ]
    out: list[ct.Finding] = []
    for name, fn in sensors:
        if name in skip:
            continue
        try:
            out.extend(fn())
            ok.add(name)
        except Exception:
            continue
    if report is not None:
        report["ok"] = ok
    return out


def disk_free_fraction(path: str | os.PathLike = ".") -> float:
    """Free fraction of the drive holding `path` (used to know when a cleanup has done enough)."""
    try:
        u = shutil.disk_usage(path)
        return u.free / u.total if u.total else 1.0
    except OSError:
        return 1.0


# --- read-only diagnostics the AI fallback (and "why is my PC slow?") may ask for -----------------
# Fixed menu (jarvis_caretaker_ai.DIAGNOSTICS). Arguments are re-checked here even though the caller already did:
# the PowerShell below only ever receives an enum value, an int in range, or a name matching a strict pattern.
def _diag_top_processes(by: str = "cpu") -> str:
    try:
        import psutil
    except ImportError:
        return ""
    procs = list(psutil.process_iter(["name", "memory_info"]))
    for p in procs:                       # the first cpu_percent() call only primes the counter
        try:
            p.cpu_percent(interval=None)
        except (psutil.Error, OSError):
            pass
    time.sleep(0.5)
    rows = []
    for p in procs:
        try:
            cpu = p.cpu_percent(interval=None) / max(1, psutil.cpu_count() or 1)
            mem = (p.info.get("memory_info").rss if p.info.get("memory_info") else 0) / 1024 ** 2
            rows.append((p.info.get("name") or "?", cpu, mem))
        except (psutil.Error, OSError):
            continue
    rows.sort(key=lambda r: r[1] if by == "cpu" else r[2], reverse=True)
    return "\n".join(f"{n}: {c:.0f}% CPU, {m:.0f} MB" for n, c, m in rows[:8])


def _diag_disk_usage() -> str:
    try:
        import psutil
    except ImportError:
        return ""
    out = []
    for part in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        out.append(f"{part.device or part.mountpoint}: {u.percent:.0f}% used, {u.free / 1024 ** 3:.1f} GB free")
    return "\n".join(out)


def _diag_network_summary() -> str:
    lines = []
    try:
        import psutil
        up = [n for n, s in psutil.net_if_stats().items() if s.isup and "loopback" not in n.lower()]
        lines.append("adapters up: " + (", ".join(up[:6]) or "none"))
    except Exception:
        pass
    findings = probe_network()
    lines.append("internet and DNS answer normally" if not findings else findings[0].title)
    return "\n".join(lines)


def diagnostic(name: str, args: dict | None = None) -> str:
    """One read-only look at the machine as short plain text ('' on any failure or a bad request)."""
    clean = ct_ai.check_diagnostic(name, args)
    if clean is None:
        return ""
    try:
        if name == "top_processes":
            return _diag_top_processes(clean.get("by", "cpu"))
        if name == "disk_usage":
            return _diag_disk_usage()
        if name == "network_summary":
            return _diag_network_summary()
        if name == "service_status":
            return _ps(f"Get-Service -Name '{clean['name']}' -ErrorAction SilentlyContinue | "
                       "ForEach-Object { $_.Name + ': ' + $_.Status + ', starts ' + $_.StartType }").strip()
        if name == "recent_errors":
            src = f";ProviderName='{clean['source']}'" if clean.get("source") else ""
            return _ps(f"Get-WinEvent -FilterHashtable @{{LogName='{clean['log']}';Level=1,2;"
                       f"StartTime=(Get-Date).AddHours(-{int(clean['hours'])}){src}}} -MaxEvents 8 "
                       "-ErrorAction SilentlyContinue | ForEach-Object { $_.TimeCreated.ToString('HH:mm') + ' ' + "
                       "$_.ProviderName + ' ' + $_.Id + ': ' + (($_.Message -split \"`n\")[0]) }").strip()
        if name == "updates_summary":
            hot = _ps("Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 3 | "
                      "ForEach-Object { $_.HotFixID + ' installed ' + $_.InstalledOn.ToString('yyyy-MM-dd') }").strip()
            age = _ps("((Get-Date) - (Get-MpComputerStatus).AntivirusSignatureLastUpdated).Days").strip()
            return (hot + ("\n" if hot else "") + (f"antivirus definitions are {age} day(s) old" if age else "")).strip()
    except Exception:
        return ""
    return ""
