"""Dashboard Settings page backend (QOL pass, 2026-09-23): view and change Jarvis's .env options
without editing the file by hand.

Writes go to .env (so they survive a restart) and os.environ; settings whose value Jarvis holds in
a module variable are also pushed into that variable so they apply immediately ("live"). Any
other key can be edited too (by the user's full-permission decision), but secret-looking values
(API keys, tokens, PINs) are never sent back to the browser, only whether they're set.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
from pathlib import Path

log = logging.getLogger("jarvis.settings")

_TRUE = ("1", "true", "yes", "on")
_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_SECRET_RE = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSCODE|PIN\b|_PIN|CREDENTIAL|COOKIE", re.I)
_lock = threading.Lock()
JARVIS_MODULE = None  # set by jarvis.py at import


def _bool(v: str) -> bool:
    return str(v).strip().lower() in _TRUE


# key, label, kind (bool/number/text/choice), default, help, [choices], live target (module, attr, cast) or None
SETTINGS: list[dict] = [
    {"key": "JARVIS_SMART_MODEL", "label": "Smart model for hard tasks", "kind": "text", "default": "claude-sonnet-5",
     "help": "Research/planning/writing go here. Empty = always use the normal model.", "live": ("jarvis", "SMART_MODEL", str)},
    {"key": "JARVIS_SMART_MODEL_EFFORT", "label": "Smart model effort", "kind": "choice", "default": "medium",
     "choices": ["low", "medium", "high", "xhigh", "max"], "help": "Higher = smarter, slower, pricier.",
     "live": ("jarvis", "SMART_MODEL_EFFORT", str)},
    {"key": "JARVIS_SMART_MODEL_MIN_WORDS", "label": "Words that count as a long request", "kind": "number", "default": "40",
     "help": "Requests at least this long go to the smart model.", "live": ("jarvis", "SMART_MODEL_MIN_WORDS", int)},
    {"key": "JARVIS_LLM_FAILOVER", "label": "Fall back to Gemini when Claude fails", "kind": "bool", "default": "1",
     "help": "Credit, key or outage problems are answered by Gemini instead.", "live": "env"},
    {"key": "JARVIS_FOLLOWUP_S", "label": "Follow-up listening window (seconds)", "kind": "number", "default": "5",
     "help": "Keep listening this long after a spoken reply. 0 = off.", "live": ("jarvis", "followup.window_s", float)},
    {"key": "JARVIS_FOLLOWUP_MIN_RMS", "label": "Follow-up mic sensitivity", "kind": "number", "default": "0.01",
     "help": "Lower if follow-ups never trigger; raise if background noise triggers them.",
     "live": ("jarvis_followup", "MIN_RMS", float)},
    {"key": "JARVIS_SELECTION_KEY", "label": "Selected-text hotkey", "kind": "text", "default": "right ctrl",
     "help": "Hold it and speak to act on selected text. Empty = off.", "live": ("jarvis", "JARVIS_SELECTION_KEY", str)},
    {"key": "JARVIS_WEATHER_LOCATION", "label": "Weather location", "kind": "text", "default": "",
     "help": "Town for weather. Empty = work it out from your internet connection.", "live": "env"},
    {"key": "JARVIS_WEATHER_UNITS", "label": "Temperature units", "kind": "choice", "default": "c", "choices": ["c", "f"],
     "help": "Celsius or Fahrenheit.", "live": "env"},
    {"key": "JARVIS_PHONE_PROACTIVE_NOTIFICATIONS", "label": "Push proactive messages to phone", "kind": "bool", "default": "0",
     "help": "Reminders/alerts also go to Telegram/ntfy.", "live": ("jarvis", "JARVIS_PHONE_PROACTIVE_NOTIFICATIONS", _bool)},
    {"key": "JARVIS_TTS_BACKEND", "label": "Voice engine", "kind": "choice", "default": "auto",
     "choices": ["auto", "deepgram", "fish", "piper"], "help": "auto = best available, with fallback.", "live": "env"},
    {"key": "JARVIS_STT_BACKEND", "label": "Speech recognition", "kind": "choice", "default": "auto",
     "choices": ["auto", "deepgram", "whisper"], "help": "auto = Deepgram if configured, else local Whisper.", "live": "env"},
    {"key": "JARVIS_LLM_TTS_STREAM", "label": "Start speaking while the answer is written", "kind": "bool", "default": "1",
     "help": "Faster first words.", "live": "env"},
    {"key": "JARVIS_PTT_KEY", "label": "Push-to-talk key", "kind": "text", "default": "right shift",
     "help": "Applies after a restart.", "live": None},
    {"key": "JARVIS_TEXT_HOTKEY_KEY", "label": "Typed-command hotkey (hold 2s)", "kind": "text", "default": "left alt",
     "help": "Applies after a restart.", "live": None},
    {"key": "JARVIS_FACE_ENABLED", "label": "Face recognition", "kind": "bool", "default": "0",
     "help": "Applies after a restart.", "live": None},
]
_BY_KEY = {s["key"]: s for s in SETTINGS}


def env_path() -> Path:
    return Path(os.environ.get("JARVIS_ENV_PATH") or Path(__file__).resolve().parent / ".env")


def _parse_env(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if m:
            v = m.group(2).strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            out[m.group(1)] = v
    return out


def is_secret(key: str) -> bool:
    return bool(_SECRET_RE.search(key))


def list_settings() -> dict:
    try:
        file_vals = _parse_env(env_path().read_text(encoding="utf-8"))
    except OSError:
        file_vals = {}
    known = []
    for s in SETTINGS:
        cur = os.environ.get(s["key"], file_vals.get(s["key"], s["default"]))
        known.append({k: v for k, v in s.items() if k != "live"} | {
            "value": cur, "applies": "restart" if s["live"] is None else "now"})
    other = [{"key": k, "secret": is_secret(k), "set": bool(v), "value": None if is_secret(k) else v}
             for k, v in sorted(file_vals.items()) if k not in _BY_KEY]
    return {"known": known, "other": other}


def _write_env_value(key: str, value: str) -> None:
    path = env_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    new_line = f"{key}={value}"
    pat = re.compile(rf"^\s*(?:export\s+)?{re.escape(key)}\s*=")
    for i, line in enumerate(lines):
        if pat.match(line):
            lines[i] = new_line
            break
    else:
        lines.append(new_line)
    tmp = path.with_suffix(".env.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _apply_live(spec) -> bool:
    live = spec.get("live") if spec else None
    if live is None:
        return False
    if live == "env":
        return True  # read from os.environ on every use
    mod_name, attr, cast = live
    # jarvis.py registers itself (it runs as __main__ when started directly, so a name lookup
    # could find a second, unused copy)
    mod = JARVIS_MODULE if mod_name == "jarvis" else sys.modules.get(mod_name)
    if mod is None:
        return False
    target, _, last = attr.rpartition(".")
    obj = getattr(mod, target) if target else mod
    raw = os.environ.get(spec["key"], "")
    try:
        setattr(obj, last, cast(raw) if raw != "" or cast is str else cast(spec["default"]))
    except (TypeError, ValueError):
        return False
    return True


def set_setting(key: str, value: str) -> dict:
    key = (key or "").strip()
    value = "" if value is None else str(value)
    if not _KEY_RE.match(key):
        return {"ok": False, "error": "Setting names are CAPITALS_WITH_UNDERSCORES."}
    if "\n" in value or "\r" in value:
        return {"ok": False, "error": "Values must be a single line."}
    spec = _BY_KEY.get(key)
    if spec and spec["kind"] == "choice" and value not in spec["choices"]:
        return {"ok": False, "error": f"Pick one of: {', '.join(spec['choices'])}."}
    if spec and spec["kind"] == "number":
        try:
            float(value)
        except ValueError:
            return {"ok": False, "error": "That needs to be a number."}
    if spec and spec["kind"] == "bool":
        value = "1" if _bool(value) else "0"
    with _lock:
        _write_env_value(key, value)
        os.environ[key] = value
        live = _apply_live(spec)
    log.info("Setting %s changed from the dashboard (%s).", key, "live" if live else "after restart")
    return {"ok": True, "key": key, "applies": "now" if live else "restart"}
