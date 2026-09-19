"""restart_jarvis: let Jarvis restart itself (voice: "restart yourself") to pick up new code.

Order of operations, chosen so a bad edit can never leave the assistant dead:
  1. refuse if delegated background tasks are still running (unless force) — they'd be orphaned;
  2. byte-compile every jarvis*.py; a syntax error aborts *before* anything is stopped;
  3. spawn a detached helper that waits for this PID to exit, then runs Jarvis.vbs (the same
     hidden launcher as the Desktop shortcut, so the new copy is a standalone one);
  4. after the spoken reply has finished, stop this process (and the MCP/npx children it owns,
     which would otherwise be orphaned and hold their ports/credentials).
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

MIN_DELAY_S = 8.0  # the model still has to write the reply and TTS has to start speaking it
MAX_WAIT_S = 40.0  # never wait forever for speech to finish


def check_syntax(project_dir: Path) -> str | None:
    """Error text for the first jarvis*.py that doesn't compile, else None."""
    for f in sorted(project_dir.glob("jarvis*.py")):
        try:
            compile(f.read_bytes(), str(f), "exec")
        except (SyntaxError, ValueError) as e:
            return f"{f.name}: {e}"
    return None


def helper_command(pid: int, launcher: Path) -> list[str]:
    script = (
        f"Wait-Process -Id {pid} -ErrorAction SilentlyContinue; Start-Sleep -Seconds 2; "
        f"Start-Process -FilePath wscript.exe -ArgumentList '\"{launcher}\"'"
    )
    return ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script]


def _stop_self(helper_pid: int, speaking: threading.Event, exit_fn, sleep=time.sleep) -> None:
    sleep(MIN_DELAY_S)
    waited = 0.0
    while speaking.is_set() and waited < MAX_WAIT_S:
        sleep(0.5)
        waited += 0.5
    try:
        import psutil

        for child in psutil.Process().children(recursive=True):
            if child.pid != helper_pid:
                try:
                    child.kill()
                except Exception:
                    pass
    except Exception:
        pass
    exit_fn(0)


def restart(
    project_dir: Path,
    busy_tasks: int,
    force: bool,
    speaking: threading.Event,
    *,
    popen=subprocess.Popen,
    exit_fn=os._exit,
    sleep=time.sleep,
    background: bool = True,
) -> str:
    launcher = project_dir / "Jarvis.vbs"
    if not launcher.exists():
        return "Can't restart: Jarvis.vbs is missing from the project folder."
    if busy_tasks and not force:
        return (
            f"{busy_tasks} background task(s) are still running and would be cut off by a "
            "restart. Tell the user, and only restart if they confirm (call again with force)."
        )
    err = check_syntax(project_dir)
    if err:
        return f"Not restarting: the code has a syntax error ({err}). Still running the old version."
    flags = 0
    if sys.platform == "win32":
        # NOT DETACHED_PROCESS: verified live that a PowerShell helper started with it never
        # manages to launch the new Jarvis. It still outlives this process without it.
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    try:
        helper = popen(
            helper_command(os.getpid(), launcher),
            creationflags=flags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except OSError as e:
        return f"Couldn't start the restart helper: {e}. Not restarting."
    args = (getattr(helper, "pid", 0), speaking, exit_fn, sleep)
    if background:
        threading.Thread(target=_stop_self, args=args, daemon=True).start()
    else:
        _stop_self(*args)
    return "Restart scheduled: Jarvis will close in a few seconds and reopen with the latest code."
