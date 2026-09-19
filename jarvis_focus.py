"""Focus Mode, optionally triggered by the mood of what Spotify is playing.

Mood detection is deliberately local and credential-free: the Spotify desktop app puts
"Artist - Track" in its window title while playing, and that string is matched against keyword
lists. No Spotify Web API, no OAuth, nothing leaves the machine. The limit of that approach is
that it only sees artist/track words (e.g. "lofi", "study", "instrumental"), not audio features.

Focus Mode does three things, all reversible: it queues non-urgent notifications (urgent ones
still come through, same rule as Sleep Mode), opens the apps named in JARVIS_FOCUS_APPS through
Jarvis's own whitelisted launcher, and switches Windows to dark mode (restored afterwards; set
JARVIS_FOCUS_DARK_MODE=0 to skip). There is no smart-light integration.

Auto-start from Spotify is opt-in (JARVIS_FOCUS_AUTO=1): it needs the focus mood on two
consecutive checks, and never ends a session on its own.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
from datetime import datetime

import jarvis_sleep_mode as sleep_mode

log = logging.getLogger("jarvis")

CHECK_INTERVAL_S = 60
_lock = threading.Lock()
_state: dict = {"active": False, "started_at": None, "auto": False, "restore_dark": None}
_last_check = 0.0
_focus_streak = 0

_MOODS = {
    "focus": (
        "lofi", "lo-fi", "study", "focus", "instrumental", "ambient", "piano", "deep work",
        "brain food", "white noise", "classical", "concentration", "binaural", "chillhop",
    ),
    "energetic": ("workout", "edm", "metal", "hype", "phonk", "gym", "rave", "drill", "rage"),
    "relaxed": ("chill", "acoustic", "sleep", "calm", "jazz", "soft", "coffee", "sunset"),
}


def _enabled_flag(name: str, default: bool) -> bool:
    return os.environ.get(name, "1" if default else "0").strip().lower() in ("1", "true", "yes")


def _spotify_window_titles() -> list[str]:
    """Titles of visible top-level windows owned by Spotify.exe (Windows only)."""
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        from ctypes import wintypes

        import psutil

        user32 = ctypes.windll.user32
        titles: list[str] = []
        proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                if psutil.Process(pid.value).name().lower() != "spotify.exe":
                    return True
            except Exception:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            titles.append(buf.value.strip())
            return True

        user32.EnumWindows(proc_type(cb), 0)
        return titles
    except Exception as e:
        log.debug("Spotify window scan failed: %s", e)
        return []


def current_track(titles: list[str] | None = None) -> str | None:
    """'Artist - Track' if Spotify is playing, else None (paused shows just 'Spotify ...')."""
    for t in _spotify_window_titles() if titles is None else titles:
        if " - " in t and not t.lower().startswith("spotify"):
            return t
    return None


def classify_mood(track: str | None) -> dict:
    if not track:
        return {"mood": "none", "focus_suggested": False, "track": None}
    low = track.lower()
    for mood, words in _MOODS.items():
        if any(re.search(r"(?<![a-z])" + re.escape(w), low) for w in words):
            return {"mood": mood, "focus_suggested": mood == "focus", "track": track}
    return {"mood": "unknown", "focus_suggested": False, "track": track}


def is_active() -> bool:
    return bool(_state.get("active"))


def should_suppress(urgent: bool) -> bool:
    """Queue non-urgent notifications while Focus Mode is on; urgent ones always get through."""
    return is_active() and not urgent


def enable(launch_app, auto: bool = False) -> str:
    """launch_app(name) opens a whitelisted app. Returns a plain-English summary."""
    with _lock:
        if _state["active"]:
            return "Focus Mode is already on."
        _state.update(active=True, started_at=datetime.now().isoformat(timespec="seconds"), auto=auto)
    parts = ["notifications silenced (urgent ones still come through)"]
    apps = [a.strip().lower() for a in os.environ.get("JARVIS_FOCUS_APPS", "").split(",") if a.strip()]
    opened = []
    for app in apps:
        try:
            launch_app(app)
            opened.append(app)
        except Exception as e:
            log.warning("Focus Mode could not open %s: %s", app, e)
    parts.append(f"opened {', '.join(opened)}" if opened else "no tools opened (set JARVIS_FOCUS_APPS)")
    if _enabled_flag("JARVIS_FOCUS_DARK_MODE", True):
        was_dark = sleep_mode._dark_mode_is_on()
        if was_dark is False and sleep_mode._set_dark_mode(True):
            _state["restore_dark"] = False
            parts.append("dark mode on")
        elif was_dark:
            parts.append("dark mode was already on")
    return "Focus Mode on: " + "; ".join(parts) + "."


def disable() -> str:
    with _lock:
        if not _state["active"]:
            return "Focus Mode is not on."
        restore = _state["restore_dark"]
        _state.update(active=False, started_at=None, auto=False, restore_dark=None)
    if restore is False:
        sleep_mode._set_dark_mode(False)
    return "Focus Mode off."


def status() -> str:
    mood = classify_mood(current_track())
    base = "Focus Mode is on." if is_active() else "Focus Mode is off."
    if mood["track"]:
        return f"{base} Spotify: {mood['track']} (mood: {mood['mood']})."
    return f"{base} Spotify isn't playing."


def tick(launch_app, notify) -> None:
    """Scheduler hook: opt-in auto-start when the music mood says focus (twice in a row)."""
    global _last_check, _focus_streak
    if not _enabled_flag("JARVIS_FOCUS_AUTO", False) or is_active() or sleep_mode.is_active():
        return
    import time

    now = time.time()
    if now - _last_check < CHECK_INTERVAL_S:
        return
    _last_check = now
    _focus_streak = _focus_streak + 1 if classify_mood(current_track())["focus_suggested"] else 0
    if _focus_streak >= 2:
        _focus_streak = 0
        notify("Your music says focus time, so I've started Focus Mode. " + enable(launch_app, auto=True))
