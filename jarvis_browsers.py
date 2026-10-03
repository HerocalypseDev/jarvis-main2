"""The user's main web browser (2026-10-03, owner request): one setting instead of Chrome hard-coded everywhere.

JARVIS_BROWSER picks it: operagx (default here), firefox, chrome, edge, or default (whatever Windows opens links with).
"open browser" / "open opera" / "open firefox" and every web link Jarvis opens go to this browser, so switching browsers
is one change in Settings. The Jarvis Tabs extension (browser_extension/) is how Jarvis sees the tabs inside it.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import webbrowser

log = logging.getLogger("jarvis.browsers")

DEFAULT_BROWSER = "operagx"
CHOICES = ("operagx", "firefox", "chrome", "edge", "default")
LABELS = {"operagx": "Opera GX", "firefox": "Firefox", "chrome": "Chrome", "edge": "Edge", "default": "your default browser"}
# What the user may say -> browser key. "browser" means the main one.
SPOKEN = {"opera gx": "operagx", "operagx": "operagx", "opera": "operagx", "firefox": "firefox", "mozilla": "firefox",
          "chrome": "chrome", "google chrome": "chrome", "edge": "edge", "microsoft edge": "edge"}
# Process names, for "is the browser the window in front?"
PROCESS_NAMES = {"operagx": ("opera.exe", "launcher.exe"), "firefox": ("firefox.exe",), "chrome": ("chrome.exe",),
                 "edge": ("msedge.exe",)}
ALL_BROWSER_PROCESSES = {"opera.exe", "firefox.exe", "chrome.exe", "msedge.exe", "brave.exe", "vivaldi.exe"}


def main_browser() -> str:
    v = (os.environ.get("JARVIS_BROWSER") or DEFAULT_BROWSER).strip().lower().replace(" ", "")
    return v if v in CHOICES else SPOKEN.get(v, DEFAULT_BROWSER)


def label(key: str | None = None) -> str:
    return LABELS.get(key or main_browser(), "your browser")


def _app_paths(exe: str) -> list[str]:
    """Windows' own record of where an app is installed (App Paths), current user first."""
    if sys.platform != "win32":
        return []
    import winreg
    out = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as k:
                out.append(str(winreg.QueryValue(k, None)).strip('"'))
        except OSError:
            continue
    return out


def executable(key: str | None = None) -> str | None:
    """Full path of a browser's program, or None when it isn't installed (or key is 'default')."""
    key = key or main_browser()
    if key == "default":
        return None
    candidates: list[str] = []
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        if key == "operagx":
            # Opera GX installs per user by default; launcher.exe is the stable entry point next to its versioned folders.
            for base in (os.path.join(local, "Programs", "Opera GX"), os.path.join(pf, "Opera GX"), os.path.join(pf86, "Opera GX")):
                candidates += [os.path.join(base, "launcher.exe"), os.path.join(base, "opera.exe")]
        elif key == "firefox":
            candidates += [os.path.join(pf, "Mozilla Firefox", "firefox.exe"), os.path.join(pf86, "Mozilla Firefox", "firefox.exe"),
                           os.path.join(local, "Mozilla Firefox", "firefox.exe")]
            candidates += _app_paths("firefox.exe")
        elif key == "chrome":
            candidates += [os.path.join(b, "Google", "Chrome", "Application", "chrome.exe") for b in (pf, pf86, local) if b]
            candidates += _app_paths("chrome.exe")
        elif key == "edge":
            candidates += [os.path.join(b, "Microsoft", "Edge", "Application", "msedge.exe") for b in (pf86, pf) if b]
            candidates += _app_paths("msedge.exe")
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    names = {"operagx": ("opera",), "firefox": ("firefox",), "chrome": ("google-chrome", "chrome"),
             "edge": ("microsoft-edge", "msedge")}.get(key, ())
    for n in names:
        found = shutil.which(n)
        if found:
            return found
    return None


def _popen(args: list[str]) -> None:
    kw: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.Popen(args, **kw)


def launch(key: str | None = None) -> str:
    """Opens a browser (the main one unless key names another). Falls back to the default browser. Returns its label."""
    key = key or main_browser()
    exe = executable(key)
    if exe:
        try:
            _popen([exe])
            return label(key)
        except OSError as e:
            log.warning("Could not open %s: %s", label(key), e)
    elif key != "default":
        log.warning("%s isn't installed where Jarvis looks; opening the default browser instead.", label(key))
    webbrowser.open("about:blank")
    return label("default")


def open_link(url: str) -> bool:
    """Opens an http(s) link in the main browser. False when the caller should use the system default instead
    (setting is 'default', browser not found, or the link isn't a web link)."""
    u = (url or "").strip()
    if not u.lower().startswith(("http://", "https://")):
        return False
    exe = executable()
    if not exe:
        return False
    try:
        _popen([exe, u])
        return True
    except OSError as e:
        log.warning("Could not open the link in %s: %s", label(), e)
        return False


def is_browser_process(app: str | None) -> bool:
    return bool(app) and str(app).lower() in ALL_BROWSER_PROCESSES
