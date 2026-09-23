"""Mute every other app's audio while Jarvis speaks, and unmute it afterwards.

Per-app mute through Windows Core Audio sessions (pycaw, already a dependency), so music/videos keep
playing silently and come back where they are. Only sessions that were *unmuted* when Jarvis started
talking are muted, and only those are unmuted again - an app the user muted themselves stays muted.
The unmute waits RELEASE_DELAY_S after the last playback ends, so the short gaps between sentences
don't flicker the other apps' sound back on.

JARVIS_DUCK_OTHER_AUDIO=0 turns it off. A no-op off Windows, without pycaw, and under pytest (the
real machine's audio is never touched by tests; tests inject fake sessions via _sessions).
"""
from __future__ import annotations

import atexit
import logging
import os
import sys
import threading

log = logging.getLogger("jarvis")

RELEASE_DELAY_S = float(os.environ.get("JARVIS_DUCK_RELEASE_S") or 1.0)

_lock = threading.Lock()
_depth = 0
_muted: set[str] = set()  # InstanceIdentifier of every session we muted
_timer: threading.Timer | None = None


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


def _restore() -> None:
    global _timer
    with _lock:
        _timer = None
        if _depth > 0 or not _muted:
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
        if _depth or not _muted:
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
