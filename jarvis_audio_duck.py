"""Mute every other app's audio while Jarvis speaks, and unmute it afterwards.

Per-app mute through Windows Core Audio sessions (pycaw, already a dependency), so music/videos keep
playing silently and come back where they are. Only sessions that were *unmuted* when Jarvis started
talking are muted, and only those are unmuted again - an app the user muted themselves stays muted.
The unmute waits RELEASE_DELAY_S after the last playback ends, so the short gaps between sentences
don't flicker the other apps' sound back on.

Exception for music players (Opera GX's sidebar player by default): besides the mute, their Windows
media session (SMTC, the same thing the media keys/volume flyout control) is *paused* and resumed
afterwards, so a song doesn't silently run on under Jarvis. Only sessions that were Playing and that
Jarvis paused are resumed. There's no WinRT package installed, so this goes through PowerShell on one
background worker thread (FIFO, so a resume never overtakes its pause); the mute covers the ~1s it
takes. JARVIS_DUCK_PAUSE_APPS is a regex over the app id (empty = off).

JARVIS_DUCK_OTHER_AUDIO=0 turns it off. A no-op off Windows, without pycaw, and under pytest (the
real machine's audio is never touched by tests; tests inject fake sessions via _sessions).
"""
from __future__ import annotations

import atexit
import logging
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger("jarvis")

RELEASE_DELAY_S = float(os.environ.get("JARVIS_DUCK_RELEASE_S") or 1.0)

_lock = threading.Lock()
_depth = 0
_muted: set[str] = set()  # InstanceIdentifier of every session we muted
_timer: threading.Timer | None = None
_paused: list[str] = []  # SMTC app ids we paused (touched only on the _media_worker thread)
_media_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="duck-media")

_SMTC_HEAD = r"""
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | ? { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $t) { $k = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $k.Wait(5000) | Out-Null; $k.Result }
[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager,Windows.Media.Control,ContentType=WindowsRuntime] | Out-Null
$m = Await ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])
"""
# Pause (Playing -> print id) or resume (only ids in JARVIS_DUCK_IDS that are still Paused).
_SMTC_PS = _SMTC_HEAD + r"""
$ids = $env:JARVIS_DUCK_IDS -split "`n"
foreach ($s in $m.GetSessions()) {
  $id = $s.SourceAppUserModelId; $st = [string]$s.GetPlaybackInfo().PlaybackStatus
  if ($env:JARVIS_DUCK_ACTION -eq 'pause') {
    if ($st -eq 'Playing' -and $id -match $env:JARVIS_DUCK_PAUSE_RE) { if (Await ($s.TryPauseAsync()) ([bool])) { $id } }
  } elseif ($ids -contains $id -and $st -eq 'Paused') { Await ($s.TryPlayAsync()) ([bool]) | Out-Null }
}
"""


def enabled() -> bool:
    return (os.environ.get("JARVIS_DUCK_OTHER_AUDIO") or "1").strip().lower() not in ("0", "false", "no", "off")


def _real_sessions(fn) -> None:
    """Runs fn(sessions) with COM initialised on this thread; sessions = (instance_id, pid, simple_volume)."""
    if sys.platform != "win32" or os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        import comtypes
        from pycaw.pycaw import AudioUtilities
    except ImportError:
        return
    comtypes.CoInitialize()
    try:
        fn([(s.InstanceIdentifier, s.ProcessId, s.SimpleAudioVolume) for s in AudioUtilities.GetAllSessions()])
    finally:
        comtypes.CoUninitialize()


_sessions = _real_sessions  # swapped out by tests


def _pause_pattern() -> str:
    return os.environ.get("JARVIS_DUCK_PAUSE_APPS", "OperaGX").strip()


def _real_media(action: str, ids: list[str]) -> list[str]:
    """Pause matching Playing SMTC sessions (returns their ids) or resume `ids`."""
    if sys.platform != "win32" or os.environ.get("PYTEST_CURRENT_TEST"):
        return []
    env = dict(os.environ, JARVIS_DUCK_ACTION=action, JARVIS_DUCK_IDS="\n".join(ids),
               JARVIS_DUCK_PAUSE_RE=_pause_pattern())
    out = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _SMTC_PS],
        env=env, capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


_media = _real_media  # swapped out by tests

# Voice media control: prefer a session whose app id matches JARVIS_MEDIA_APP (Opera's sidebar
# player by default; a Playing one first), else Windows' current media session. Prints ok|fail|none.
_CONTROL_PS = _SMTC_HEAD + r"""
$c = @($m.GetSessions() | ? { $env:JARVIS_MEDIA_RE -and $_.SourceAppUserModelId -match $env:JARVIS_MEDIA_RE })
$s = $c | ? { [string]$_.GetPlaybackInfo().PlaybackStatus -eq 'Playing' } | select -First 1
if (-not $s) { $s = $c | select -First 1 }
if (-not $s) { $s = $m.GetCurrentSession() }
if (-not $s) { 'none'; exit }
$op = switch ($env:JARVIS_MEDIA_ACTION) { 'play' { $s.TryPlayAsync() } 'pause' { $s.TryPauseAsync() }
  'next' { $s.TrySkipNextAsync() } 'previous' { $s.TrySkipPreviousAsync() } }
if (Await $op ([bool])) { 'ok' } else { 'fail' }
"""


def media_control(action: str) -> str:
    """play|pause|next|previous on the preferred media session. Returns 'ok', 'fail' or 'none';
    raises if PowerShell/WinRT isn't usable (caller falls back to the media keys)."""
    if sys.platform != "win32" or os.environ.get("PYTEST_CURRENT_TEST"):
        raise RuntimeError("media session control unavailable")
    env = dict(os.environ, JARVIS_MEDIA_ACTION=action,
               JARVIS_MEDIA_RE=os.environ.get("JARVIS_MEDIA_APP", "Opera").strip())
    out = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _CONTROL_PS],
        env=env, capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    result = (out.stdout.strip().splitlines() or [""])[-1].strip()
    if result not in ("ok", "fail", "none"):
        raise RuntimeError(out.stderr.strip()[:200] or "no result")
    return result


def _pause_music() -> None:
    try:
        re.compile(_pause_pattern())
        for sid in _media("pause", []):
            if sid not in _paused:
                _paused.append(sid)
    except Exception as e:
        log.warning("Could not pause music player: %s", e)


def _resume_music() -> None:
    if not _paused:
        return
    try:
        _media("resume", list(_paused))
    except Exception as e:
        log.warning("Could not resume music player: %s", e)
    _paused.clear()


def _mute_others(sessions) -> None:
    own = os.getpid()
    for sid, pid, vol in sessions:
        try:
            if pid != own and sid not in _muted and not vol.GetMute():
                vol.SetMute(1, None)
                _muted.add(sid)
        except Exception as e:
            log.debug("duck: could not mute session %s: %s", pid, e)


def _unmute_ours(sessions) -> None:
    for sid, _pid, vol in sessions:
        if sid in _muted:
            try:
                vol.SetMute(0, None)
            except Exception as e:
                log.debug("duck: could not unmute session %s: %s", _pid, e)
    _muted.clear()  # a session that vanished meanwhile has nothing left to restore


def duck() -> None:
    """Call when Jarvis's audio starts. Nested/overlapping calls are counted."""
    global _depth, _timer
    if not enabled():
        return
    with _lock:
        _depth += 1
        if _timer is not None:
            _timer.cancel()
            _timer = None
        try:
            _sessions(_mute_others)  # also catches an app that started playing mid-reply
        except Exception as e:
            log.warning("Could not mute other apps' audio: %s", e)
        if _depth == 1 and _pause_pattern():
            _media_worker.submit(_pause_music)


def _restore() -> None:
    global _timer
    with _lock:
        _timer = None
        if _depth > 0:
            return
        try:
            _media_worker.submit(_resume_music)
        except RuntimeError:  # interpreter exiting, worker already shut down
            _resume_music()
        if not _muted:
            return
        try:
            _sessions(_unmute_ours)
        except Exception as e:
            log.warning("Could not unmute other apps' audio: %s", e)


def release(delay: float | None = None) -> None:
    """Call when Jarvis's audio ends; other apps are unmuted `delay` seconds after the last one."""
    global _depth, _timer
    if not enabled():
        return
    with _lock:
        _depth = max(0, _depth - 1)
        if _depth:
            return
        d = RELEASE_DELAY_S if delay is None else delay
        if d <= 0:
            _timer = None
        else:
            _timer = threading.Timer(d, _restore)
            _timer.daemon = True
            _timer.start()
            return
    _restore()


def _restore_now() -> None:
    global _depth
    with _lock:
        _depth = 0
    _restore()


atexit.register(_restore_now)  # never leave other apps muted on a normal exit
