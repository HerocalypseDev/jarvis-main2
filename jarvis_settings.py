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
# TOPIC/CHAT_ID: the ntfy topic name works like a password (anyone who knows it can send Jarvis
# commands), and the Telegram chat id is only a little less sensitive.
_SECRET_RE = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSCODE|PIN\b|_PIN|CREDENTIAL|COOKIE|TOPIC|CHAT_ID", re.I)
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
    {"key": "JARVIS_GEMINI_FALLBACK_MODEL", "label": "Gemini backup model (overloaded or slow)", "kind": "text",
     "default": "", "help": "Tried once when your Gemini model says it's overloaded (503 high demand), and asked "
     "in parallel when your model hasn't answered within the race time below (the first answer wins). Never used "
     "for quota limits. e.g. gemini-flash-lite-latest. Empty = off.", "live": "env"},
    {"key": "JARVIS_GEMINI_BACKUP_ON_RATE_LIMIT", "label": "Use the backup model when Gemini hits its limit", "kind": "bool",
     "default": "0", "help": "Free tiers give every model its own daily allowance (e.g. 500 requests/day on 3.5-flash-lite, 20 on "
     "3.5-flash). On: when your model says it hit its limit (429), the backup model answers at once instead of "
     "Jarvis waiting or failing. Needs a backup model above. Off (default): Jarvis waits, or fails with the reason.", "live": "env"},
    {"key": "JARVIS_GEMINI_HEDGE_S", "label": "Race the backup after (seconds)", "kind": "number", "default": "8",
     "help": "Needs a backup model. If Gemini hasn't answered after this long, the backup is asked too. 0 = never.",
     "live": "env"},
    {"key": "JARVIS_GEMINI_ATTEMPT_TIMEOUT_S", "label": "Gemini attempt time limit (seconds)", "kind": "number",
     "default": "60", "help": "A single Gemini request is abandoned after this long (then tried once more).",
     "live": "env"},
    {"key": "JARVIS_GEMINI_STREAM", "label": "Speak Gemini replies as they are written", "kind": "bool", "default": "1",
     "help": "Jarvis starts talking with the first sentence instead of waiting for the whole answer.", "live": "env"},
    {"key": "JARVIS_LIVE_SPEECH_MAX_CHARS", "label": "Longest spoken reply (characters)", "kind": "number",
     "default": "400", "help": "A streamed Gemini answer is spoken up to about this length, then Jarvis offers the "
     "rest; the dashboard always shows all of it. 0 = read everything. Asking \"in detail\" also lifts it.",
     "live": "env"},
    {"key": "JARVIS_ACK_PHRASES", "label": "Say \"On it\" for tasks", "kind": "bool", "default": "1",
     "help": "A short spoken acknowledgement right away when you ask for something that takes a moment.",
     "live": "env"},
    {"key": "JARVIS_ANNOUNCE_TASKS", "label": "Say what task I'm starting", "kind": "bool", "default": "1",
     "help": "Once the model has picked a slow tool (file search, web search, email, code...), Jarvis says one "
     "friendly sentence about that task, e.g. \"Sure, I'll search your whole PC for weird.\" Needs the \"On it\" "
     "switch above to be on.", "live": "env"},
    {"key": "JARVIS_GEMINI_SMART_MODEL", "label": "Gemini model to escalate to", "kind": "text", "default": "",
     "help": "When a command goes wrong on Gemini (tool failed, repeated command, claimed action that didn't "
             "happen), the rest of it runs on this model, e.g. gemini-3.6-flash. Empty = off.", "live": "env"},
    {"key": "JARVIS_OLLAMA_MODEL", "label": "Local brain model (Ollama)", "kind": "text", "default": "qwen3:8b",
     "help": "Used when the brain is 'local'. Pull it first: ollama pull <model>. Bigger = smarter, slower.", "live": "env"},
    {"key": "JARVIS_OLLAMA_URL", "label": "Local brain server", "kind": "text", "default": "http://127.0.0.1:11434",
     "help": "Ollama on this PC or your home network. Public addresses are refused.", "live": "env"},
    {"key": "JARVIS_EMBEDDINGS", "label": "Meaning-based memory search", "kind": "choice", "default": "auto",
     "choices": ["auto", "on", "off"], "help": "Gemini embeddings for recalling facts. auto = only on the Gemini brain.",
     "live": "env"},
    {"key": "JARVIS_LESSONS", "label": "Learn from mistakes", "kind": "bool", "default": "1",
     "help": "After a failed or corrected command, save a one-line lesson and use it next time.", "live": "env"},
    {"key": "JARVIS_DAILY_PLAN_TIME", "label": "Daily plan time", "kind": "text", "default": "07:45",
     "help": "When today's plan is made (HH:MM). JARVIS_DAILY_PLAN=0 turns plan + review off.", "live": "env"},
    {"key": "JARVIS_DAILY_REVIEW_TIME", "label": "Evening review time", "kind": "text", "default": "21:00",
     "help": "When the day is reviewed and unfinished items carried over (HH:MM).", "live": "env"},
    {"key": "JARVIS_TOOL_NARROWING", "label": "Tool narrowing", "kind": "choice", "default": "auto",
     "choices": ["auto", "on", "off"],
     "help": "Send the brain only the ~28 tools a command needs (+ a find_tools helper). auto = Gemini only "
             "(keeps Claude's prompt cache); on = both.", "live": "env"},
    {"key": "JARVIS_SAFE_MODE", "label": "Safe mode", "kind": "bool", "default": "0",
     "help": "Pauses autonomy, turns off the follow-up window and holds non-urgent announcements. "
             "Commands and the confirmation step work as normal.", "live": "env"},
    {"key": "JARVIS_MAIL_AUTOREPLY", "label": "Answer emails automatically", "kind": "bool", "default": "1",
     "help": "Replies to new emails from your calendar and memory, and SENDS them. People you know (an address in "
             "memory, or anyone you've emailed) may get anything from memory and the calendar; strangers get a polite "
             "reply with nothing personal. Never newsletters/no-reply mail or threads you already answered; 3 replies per "
             "sender and 20 in all per day; never accepts or promises anything. Replies show under \"what did I miss\".",
     "live": "env"},
    {"key": "JARVIS_MAIL_AUTOREPLY_MIN", "label": "Check mail to answer every (minutes)", "kind": "number", "default": "5",
     "help": "How often new mail is checked for an automatic reply (minimum 2).", "live": "env"},
    {"key": "JARVIS_LEARN_FROM_SPEECH", "label": "Learn facts from what you say", "kind": "bool", "default": "1",
     "help": "\"My exam score was 280\", \"I live in Paris\", \"call me Sam\": remembered at once, no AI call. "
             "Questions, commands and passing states (\"my phone is dead\") are ignored. See and edit them on the Memory page.",
     "live": "env"},
    {"key": "JARVIS_PROACTIVE_SPEECH", "label": "Unprompted speech", "kind": "choice", "default": "important",
     "choices": ["important", "all"],
     "help": "important: Jarvis only speaks on its own for your reminders, urgent things and jobs you asked for; the "
             "rest waits for \"what did I miss?\" and the Home card. all: the old behaviour (every update is said).",
     "live": "env"},
    {"key": "JARVIS_REPLY_STYLE", "label": "Reply length", "kind": "choice", "default": "normal",
     "choices": ["normal", "brief", "detailed"], "help": "Also by voice: \"be brief from now on\".", "live": "env"},
    {"key": "JARVIS_DAILY_BUDGET_USD", "label": "Daily API budget alert ($)", "kind": "number", "default": "5",
     "help": "One heads-up a day when today's estimated spend passes this. 0 = off.", "live": "env"},
    {"key": "JARVIS_MEETING_HEADSUP_MIN", "label": "Meeting heads-up (minutes before)", "kind": "number",
     "default": "10", "help": "Says what's coming up and recent mail from the people in it. 0 = off.", "live": "env"},
    {"key": "JARVIS_LLM_FAILOVER", "label": "Fall back to Gemini when Claude fails", "kind": "bool", "default": "1",
     "help": "Credit, key or outage problems are answered by Gemini instead.", "live": "env"},
    {"key": "JARVIS_GEMINI_MODEL", "label": "Gemini model", "kind": "text", "default": "gemini-3.1-flash-lite",
     "options_from": "gemini",
     "help": "Chat models your Gemini key can use (list refreshed hourly). If this one's daily free quota runs out, pick another here.",
     "live": "env"},
    {"key": "JARVIS_FOLLOWUP_S", "label": "Follow-up listening window (seconds)", "kind": "number", "default": "5",
     "help": "Keep listening this long after a spoken reply. 0 = off.", "live": ("jarvis", "followup.window_s", float)},
    {"key": "JARVIS_WAKE_WORD", "label": "\"Hey Jarvis\" wake word", "kind": "bool", "default": "0",
     "help": "Say \"Hey Jarvis, ...\" instead of holding the push-to-talk key. Runs a small model on this PC "
     "(about 140 MB of memory and a few percent of one CPU core) and needs `pip install openwakeword`; nothing "
     "leaves the PC until the phrase is heard. Off in Safe Mode and Sleep Mode. A wake-word command can never "
     "confirm a shutdown/format: use the push-to-talk key for that.", "live": "env"},
    {"key": "JARVIS_WAKE_THRESHOLD", "label": "Wake word sensitivity", "kind": "number", "default": "0.5",
     "help": "0.1-0.99. Lower if \"Hey Jarvis\" is often missed; raise if it fires on TV or chatter.", "live": "env"},
    {"key": "JARVIS_FOLLOWUP_MIN_RMS", "label": "Follow-up mic sensitivity", "kind": "number", "default": "0.01",
     "help": "Lower if follow-ups never trigger; raise if background noise triggers them.",
     "live": ("jarvis_followup", "MIN_RMS", float)},
    {"key": "JARVIS_SELECTION_KEY", "label": "Selected-text hotkey", "kind": "text", "default": "",
     "help": "Hold it alone and speak to act on selected text. Empty = off. Right Ctrl works (shortcuts like "
             "Ctrl+Win+Arrow are left alone); Shift/Alt/Win can't be used. A non-modifier key (e.g. f9) "
             "repeats into the focused app while held.", "live": ("jarvis", "JARVIS_SELECTION_KEY", str)},
    {"key": "JARVIS_APPSHOT_KEY", "label": "Ask-about-this-window hotkey (appshot)", "kind": "text", "default": "",
     "help": "Hold it alone and ask about the window in front of you; its title and a picture of it go to "
             "the AI with your question. Empty = off. Suggested: right ctrl. Nothing is typed into any app.",
     "live": ("jarvis", "JARVIS_APPSHOT_KEY", str)},
    {"key": "JARVIS_DICTATION_KEY", "label": "Dictation hotkey", "kind": "text", "default": "",
     "help": "Hold it alone and speak: the words are typed into the app you're in. Start with \"Jarvis,\" to "
             "run it as a command instead. Empty = off. Use a different key from the other hotkeys.",
     "live": ("jarvis", "JARVIS_DICTATION_KEY", str)},
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
    {"key": "JARVIS_DEEPGRAM_LANGUAGE", "label": "Speech recognition language", "kind": "text", "default": "en",
     "help": "Deepgram language code, or \"multi\" for mixed-language speech.",
     "live": ("jarvis_stt_deepgram", "DEEPGRAM_LANGUAGE", str)},
    {"key": "JARVIS_TTS_JITTER_BUFFER_MS", "label": "Voice buffer (ms)", "kind": "number", "default": "120",
     "help": "Audio held back before a streamed reply starts playing. Raise if the voice breaks up.",
     "live": ("jarvis", "TTS_JITTER_BUFFER_MS", float)},
    {"key": "JARVIS_TTS_LIVE_STREAM_MIN_CHARS", "label": "Shortest sentence to stream (chars)", "kind": "number",
     "default": "40", "help": "Shorter lines (greetings) use one fast request instead, so they never cut off.",
     "live": ("jarvis", "TTS_LIVE_STREAM_MIN_CHARS", int)},
    {"key": "JARVIS_LLM_TTS_STREAM", "label": "Start speaking while the answer is written", "kind": "bool", "default": "1",
     "help": "Faster first words.", "live": "env"},
    # Feature batch 2026-09-27 (FEATURES.md)
    {"key": "JARVIS_CLIPBOARD_HISTORY", "label": "Clipboard history", "kind": "bool", "default": "1",
     "help": "Keep the last 50 copies, searchable by voice and in the Toolbox. Secrets keep length only.",
     "live": None},
    {"key": "JARVIS_EVERYTHING_URL", "label": "Everything HTTP server", "kind": "text", "default": "",
     "help": "Instant file search. Install voidtools Everything, enable Tools > Options > HTTP Server on "
             "127.0.0.1, put its address here (e.g. http://127.0.0.1:8080). Empty = try ports 80 and 8080, "
             "then es.exe.", "live": "env"},
    {"key": "JARVIS_NETSCAN_ANNOUNCE_NAMED", "label": "Announce named devices joining", "kind": "bool", "default": "1",
     "help": "Say \"John's iPhone joined the network\" when a named device comes back after 30+ minutes away, or after Jarvis already said it left.",
     "live": "env"},
    {"key": "JARVIS_NETSCAN_ANNOUNCE_LEFT", "label": "Announce named devices leaving", "kind": "bool", "default": "1",
     "help": "Say \"John's iPhone left the network\" when a named device has been gone from the scans for 5 minutes.",
     "live": "env"},
    {"key": "JARVIS_SPEEDTEST_MAX_MB", "label": "Speed test data limit (MB)", "kind": "number", "default": "40",
     "help": "\"What's my internet speed?\" downloads at most this much (and uploads half of it). A test usually stops "
     "sooner, after about 8 seconds; only a fast line reaches the limit. 10-500.", "live": "env"},
    {"key": "JARVIS_SPEEDTEST_UNIT", "label": "Speed test unit", "kind": "choice", "default": "megabits",
     "choices": ["megabits", "megabytes", "kilobits", "kilobytes", "gigabits"],
     "help": "How a speed test answers when you don't name a unit. Internet plans are sold in megabits per second; "
     "megabytes per second (8 times smaller) is what a download window shows. Saying \"in megabytes\" always wins.",
     "live": "env"},
    {"key": "JARVIS_BROWSER", "label": "Main web browser", "kind": "choice", "default": "operagx",
     "choices": ["operagx", "firefox", "chrome", "edge", "default"],
     "help": "\"Open browser\" and every link Jarvis opens use this one. default = whatever Windows opens links with. "
     "For tabs (read, summarize, close, reopen), also install the Jarvis Tabs extension from the browser_extension "
     "folder in that browser.", "live": "env"},
    {"key": "JARVIS_BROWSER_TABS", "label": "See and manage browser tabs", "kind": "bool", "default": "1",
     "help": "Lets the Jarvis Tabs extension connect (127.0.0.1 only, paired with a secret key). Restart Jarvis after "
     "changing it.", "live": None},
    {"key": "JARVIS_BROWSER_BRIDGE_PORT", "label": "Browser tabs port", "kind": "number", "default": "8767",
     "help": "The local port the extension connects to. After changing it restart Jarvis, then reload the extension.",
     "live": None},
    {"key": "JARVIS_BATTERY_SAVER", "label": "Battery saver", "kind": "bool", "default": "1",
     "help": "On battery: less background work when low, scanning paused and quiet announcements when very low.",
     "live": "env"},
    {"key": "JARVIS_BATTERY_LOW_PCT", "label": "Battery low at (%)", "kind": "number", "default": "20",
     "help": "Background work slows down below this.", "live": "env"},
    {"key": "JARVIS_BATTERY_CRITICAL_PCT", "label": "Battery very low at (%)", "kind": "number", "default": "10",
     "help": "Network scan pauses and non-urgent announcements wait below this.", "live": "env"},
    {"key": "JARVIS_MEETING_AUTO", "label": "Auto-start meeting notes", "kind": "bool", "default": "0",
     "help": "Start meeting notes by itself when a Zoom/Teams/Meet/Webex window is in front. Off = only when "
             "you say \"start meeting notes\". Call audio goes to Deepgram (or local Whisper) and the AI.",
     "live": "env"},
    {"key": "JARVIS_MEETING_MAX_MIN", "label": "Meeting notes: longest session (minutes)", "kind": "number",
     "default": "120", "help": "Stops by itself after this long.", "live": "env"},
    {"key": "JARVIS_MEETING_SILENCE_MIN", "label": "Meeting notes: stop after silence (minutes)", "kind": "number",
     "default": "10", "help": "Stops when the speakers have been quiet this long.", "live": "env"},
    {"key": "JARVIS_FILE_TAG_LLM_PER_HOUR", "label": "AI file tags per hour", "kind": "number", "default": "10",
     "help": "New documents that rules can't tag get one AI call each (first 1500 characters). 0 = rules only.",
     "live": "env"},
    {"key": "JARVIS_NOTIFY_SMART", "label": "Learn which announcements to batch", "kind": "bool", "default": "1",
     "help": "Kinds of announcement you keep cutting off wait for an hourly digest. Reminders never wait.",
     "live": "env"},
    {"key": "JARVIS_NOTIFY_DIGEST_MIN", "label": "Announcement digest every (minutes)", "kind": "number",
     "default": "60", "help": "How often batched announcements are read out together.", "live": "env"},
    {"key": "JARVIS_CODE_ROOTS", "label": "Code search folders", "kind": "text", "default": "",
     "help": "Folders searched when you don't name one, separated by ;", "live": "env"},
    {"key": "JARVIS_RG_PATH", "label": "ripgrep (rg.exe) path", "kind": "text", "default": "",
     "help": "Faster code search. Empty = rg on the PATH, else git grep, else a bounded scan.", "live": "env"},
    {"key": "JARVIS_AUTONOMY_SPEECH", "label": "Autonomy speaks", "kind": "choice", "default": "minimal",
     "choices": ["minimal", "normal"],
     "help": "minimal: autonomy and scheduled jobs speak only failures, reminders and \"needs your yes\"; the "
             "Autonomy/Toolbox pages show everything else. normal: also says what it started and finished.",
     "live": "env"},
    {"key": "JARVIS_AUTONOMY_EMAIL_MAX_PER_RECIPIENT_DAY", "label": "Autonomous emails per person per day",
     "kind": "number", "default": "3", "help": "Stops reply loops. Never to your own address.", "live": "env"},
    {"key": "JARVIS_AUTONOMY_EMAIL_MAX_PER_DAY", "label": "Autonomous emails per day", "kind": "number",
     "default": "20", "help": "Total cap on emails autonomy sends by itself in a day.", "live": "env"},
    {"key": "JARVIS_PTT_KEY", "label": "Push-to-talk key", "kind": "text", "default": "right shift",
     "help": "Applies after a restart.", "live": None},
    {"key": "JARVIS_TEXT_HOTKEY_KEY", "label": "Typed-command hotkey (hold 2s)", "kind": "text", "default": "left alt",
     "help": "Applies after a restart.", "live": None},
    {"key": "JARVIS_FACE_ENABLED", "label": "Face recognition", "kind": "bool", "default": "0",
     "help": "Applies after a restart.", "live": None},
]
_BY_KEY = {s["key"]: s for s in SETTINGS}
_HOLD_KEYS = ("JARVIS_SELECTION_KEY", "JARVIS_APPSHOT_KEY", "JARVIS_DICTATION_KEY")


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


change_hook = None  # fn(key, value_or_None, applied_live), set by jarvis.py


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
        row = {k: v for k, v in s.items() if k not in ("live", "options_from")} | {
            "value": cur, "applies": "restart" if s["live"] is None else "now"}
        if s.get("options_from") == "gemini":
            import jarvis_gemini
            row["options"] = jarvis_gemini.list_models()
        known.append(row)
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
    tmp = path.with_name(path.name + ".tmp")  # .env.tmp, gitignored like .env
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
    if key in _HOLD_KEYS and value.strip():
        if re.search(r"shift|alt|win|cmd|super|meta", value, re.I):
            return {"ok": False, "error": "Shift, Alt and Win can't be a hold key (they open menus/Start or "
                                          "change the keys Jarvis presses). Use a Ctrl key or a spare key like f9."}
        v = value.strip().lower()
        for other in _HOLD_KEYS + ("JARVIS_PTT_KEY",):
            cur = (os.environ.get(other) or ("right shift" if other == "JARVIS_PTT_KEY" else "")).strip().lower()
            if other != key and cur == v:
                return {"ok": False, "error": f"{v!r} is already used by {_BY_KEY[other]['label'].lower()}."}
    if spec and spec["kind"] == "bool":
        value = "1" if _bool(value) else "0"
    with _lock:
        _write_env_value(key, value)
        os.environ[key] = value
        live = _apply_live(spec)
    log.info("Setting %s changed from the dashboard (%s).", key, "live" if live else "after restart")
    hook = change_hook
    if hook is not None:  # self-awareness journal; the value is only passed on for non-secret keys
        try:
            hook(key, None if is_secret(key) else value[:60], live)
        except Exception as e:
            log.debug("settings change hook failed: %s", e)
    return {"ok": True, "key": key, "applies": "now" if live else "restart"}
