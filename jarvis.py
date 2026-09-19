#!/usr/bin/env python3
"""
Jarvis desktop voice assistant: push-to-talk (hold a key, speak, release) plus a typed-command
hotkey, both running local Whisper transcription and Claude tool-use against this machine.

Run:
  python -m pip install -r requirements.txt
  python jarvis.py

Tuning (constants below):
  SAMPLE_RATE   — usually 44100 or 48000; match your device if needed.
  BLOCK_MS      — analysis window size for audio capture.
  FOCUS_EXISTING_CURSOR_WINDOW — if True, focus an existing Cursor instance instead of a new one.
  OPEN_NEW_CURSOR_WINDOW — if True, also launch a new Cursor window (-n).
  CURSOR_OPEN_FULLSCREEN — Windows: after focus/launch, send F11 to enter Cursor/VS Code-style fullscreen (toggle off with F11).
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from datetime import datetime, timedelta
from html.parser import HTMLParser
import webbrowser
from pathlib import Path

from dotenv import load_dotenv
import numpy as np
import sounddevice as sd

# Modular improvements — each is self-contained (owns its own DB tables/connection,
# no import-time dependency back on this module) and exposed here as extra agent tools.
import jarvis_workflow as workflow
import jarvis_proactive as proactive
import jarvis_tech_understanding as tech_understanding
import jarvis_memory_enhance as memory_enhance
import jarvis_filewatcher as filewatcher
import jarvis_window_control as window_control
import jarvis_task_scheduler as task_scheduler
import jarvis_voice_tone as voice_tone
import jarvis_sleep_mode as sleep_mode
import jarvis_cache as cache
import jarvis_billing as billing
import jarvis_gemini as gemini
import jarvis_dashboard as dashboard

# --- tuning knobs -----------------------------------------------------------
SAMPLE_RATE = 44100
BLOCK_MS = 40
CHANNELS = 1

# Startup mic probe: if default input RMS stays below this, scan for a louder device.
INPUT_PROBE_S = 0.5
INPUT_SILENT_RMS = 0.001

# Cursor: focus existing instance (no -n). Set OPEN_NEW_CURSOR_WINDOW for a new window as well.
FOCUS_EXISTING_CURSOR_WINDOW = True
OPEN_NEW_CURSOR_WINDOW = False
CURSOR_OPEN_FULLSCREEN = False

load_dotenv(Path(__file__).resolve().parent / ".env")

# Push-to-talk voice commands: hold JARVIS_PTT_KEY, speak, release. Local Whisper
# transcribes, Claude decides zero or more actions from a fixed safe set, Piper speaks the reply.
JARVIS_PTT_ENABLED = True
JARVIS_PTT_KEY = (os.environ.get("JARVIS_PTT_KEY") or "left shift").strip() or "left shift"
WHISPER_MODEL_SIZE = (os.environ.get("WHISPER_MODEL_SIZE") or "base").strip() or "base"
CLAUDE_MODEL = (
    os.environ.get("CLAUDE_MODEL") or "claude-haiku-4-5-20251001"
).strip() or "claude-haiku-4-5-20251001"

# Typed commands: hold JARVIS_TEXT_HOTKEY_KEY for JARVIS_TEXT_HOTKEY_HOLD_S seconds to pop up
# a small always-on-top text box; Enter sends the text through the same Claude tool loop as a
# voice command (no Whisper involved), Escape/closing the box cancels.
JARVIS_TEXT_HOTKEY_ENABLED = True
JARVIS_TEXT_HOTKEY_KEY = (
    os.environ.get("JARVIS_TEXT_HOTKEY_KEY") or "right ctrl"
).strip() or "right ctrl"
JARVIS_TEXT_HOTKEY_HOLD_S = float(os.environ.get("JARVIS_TEXT_HOTKEY_HOLD_S") or 2.0)

# Phone integration: two independent, optionally-both-enabled channels. Both push every
# proactive notification (reminders, background-task completions, health-check suggestions —
# anything that already goes through queue_or_deliver_notification) to your phone immediately,
# bypassing the busy/work-hours queueing that gates the in-room spoken announcement, since a
# silent push doesn't interrupt anything the way audio would. Both also let you send a message
# back that runs through the exact same command pipeline as the text-hotkey box — full tool
# access, same confirmation gate for the catastrophic-action tier, nothing else held back.
#
# ntfy.sh: free, no account. NTFY_TOPIC is really a shared secret on the free public service —
# anyone who learns the topic name can publish to your command topic and run arbitrary Jarvis
# commands, so pick (or generate) a long random one, never something guessable, and never
# commit it — this reads it from .env like everything else. Outbound alerts go to
# {NTFY_TOPIC}; inbound commands are read from a *separate* {NTFY_TOPIC}-cmd topic so Jarvis's
# own outbound pushes can't loop back in as commands.
NTFY_TOPIC = (os.environ.get("NTFY_TOPIC") or "").strip()
NTFY_SERVER = (os.environ.get("NTFY_SERVER") or "https://ntfy.sh").strip().rstrip("/")

# Telegram bot: needs a one-time setup (message @BotFather to create a bot and get a token,
# then message your own bot once to learn your chat ID) but is authenticated by the bot token
# itself, not a guessable topic name, and only TELEGRAM_CHAT_ID's messages are ever accepted —
# a stronger boundary than the ntfy command channel.
TELEGRAM_BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()

# Off by default per explicit user request (2026-09-18): "I don't want notifications sent to
# my telegram and ntfy all the time unless I type a message there." This only gates *proactive*
# pushes (_notify_phone, called from queue_or_deliver_notification for scheduled skills, health
# suggestions, reminders, background task completions) — a direct reply to something the user
# typed FROM ntfy/Telegram always goes back through reply_sink regardless of this setting, since
# that's a separate path (_ntfy_listen_loop/_telegram_listen_loop), not this one.
JARVIS_PHONE_PROACTIVE_NOTIFICATIONS = (
    os.environ.get("JARVIS_PHONE_PROACTIVE_NOTIFICATIONS") or ""
).strip().lower() in ("1", "true", "yes")

# Local supervision dashboard (jarvis_dashboard.py): FastAPI + WebSocket UI, off by default,
# localhost-only when enabled. See CLAUDE.md's "Dashboard" section for the risk rules around
# this before changing any of it.
JARVIS_DASHBOARD_ENABLED = (
    os.environ.get("JARVIS_DASHBOARD_ENABLED") or ""
).strip().lower() in ("1", "true", "yes")
JARVIS_DASHBOARD_PORT = int(os.environ.get("JARVIS_DASHBOARD_PORT") or 8765)
JARVIS_DASHBOARD_AUTO_OPEN = (
    os.environ.get("JARVIS_DASHBOARD_AUTO_OPEN") or "1"
).strip().lower() in ("1", "true", "yes")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("jarvis")

# Set while any Jarvis TTS audio is actually playing through the speakers. The main loop
# skips PTT detection while this is set, so the mic can't hear Jarvis's own voice
# bleed through and misread it as a new command (an audio feedback loop that would
# otherwise cut playback off mid-word and restart it, since sd.play() stops prior playback).
jarvis_speaking = threading.Event()
# Multiple push-to-talk commands can run concurrently on separate threads (see
# handle_voice_command); sd.play()/PortAudio is not safe to call from more than one thread
# at once — concurrent calls can crash the whole process (observed: a segfault when four
# overlapping voice commands all tried to speak their replies at the same moment). Every
# actual playback call must hold this lock for its full sd.play()+sd.wait() duration.
_playback_lock = threading.Lock()

# --- confirmation gate: one narrow tier of catastrophic, whole-machine action (shutdown/ ---
# --- restart/sign-out, disk reformat, or recursively wiping an entire drive or user profile) ---
# --- stages instead of running immediately, and waits for an explicit spoken "yes" on the next ---
# --- turn. Everything else Jarvis can do — including individual deletes, messaging, clicking, ---
# --- and arbitrary shell/Python — runs with no confirmation step, by explicit user request. ---
_CONFIRM_YES_WORDS = (
    "yes", "yeah", "yep", "yup", "confirm", "confirmed", "do it", "go ahead",
    "send it", "sure", "correct", "affirmative", "please do",
)
_pending_action_lock = threading.Lock()
_pending_action: dict | None = None

# Best-effort text patterns over a shell command or Python snippet's *source text* — not a
# sandbox, just a tripwire — for the one class of damage that's both irreversible and
# plausibly triggered by a misheard Whisper transcription or injected screen/clipboard text:
# powering off/restarting/signing out the machine, reformatting a disk, or recursively
# deleting an entire drive or the user's whole profile (as opposed to an individual file).
_CATASTROPHIC_PATTERNS: tuple[tuple["re.Pattern[str]", str], ...] = (
    (
        re.compile(
            r"\bshutdown\b[^\n]{0,20}(/s\b|/r\b|-s\b)|shutdown\.exe|restart-computer|"
            r"stop-computer|logoff\.exe|\blogoff\b|exitwindowsex",
            re.I,
        ),
        "shut down, restart, or sign out of the machine",
    ),
    (
        re.compile(
            r"\bformat\s+[a-z]:|diskpart|remove-partition|clear-disk|initialize-disk|\bmkfs\b",
            re.I,
        ),
        "reformat or repartition a disk",
    ),
    (
        re.compile(
            r"(rm\s+-rf|remove-item[^\n]*-recurse|rd\s+/s|rmdir\s+/s|del\s+/s\s+/q)[^\n]{0,40}"
            r"([a-z]:\\?\s*[\"']?$|[a-z]:/\s*$|%userprofile%\s*$|\$env:userprofile\s*$|"
            r"~\s*[\"']?$|/\s*[\"']?$)",
            re.I,
        ),
        "recursively delete an entire drive or your whole user profile",
    ),
    (
        re.compile(r"shutil\.rmtree\([\"'](?:[a-z]:[\\/]{1,2}|~|/)[\"']\)", re.I),
        "recursively delete an entire drive or your whole user profile",
    ),
)


def _catastrophic_reason(text: str) -> str | None:
    """Short human description if `text` (a shell command or Python snippet) matches the one
    tier of action that still requires spoken confirmation, else None."""
    for pattern, reason in _CATASTROPHIC_PATTERNS:
        if pattern.search(text or ""):
            return reason
    return None


def _is_confirmation_yes(transcript: str) -> bool:
    t = transcript.lower()
    return any(word in t for word in _CONFIRM_YES_WORDS)


def _queue_pending_confirmation(tool_name: str, tool_input: dict, reason: str) -> bool:
    """Stores a catastrophic tool call awaiting a "yes" on the next push-to-talk press.
    Returns False (and queues nothing) if something is already pending."""
    global _pending_action
    with _pending_action_lock:
        if _pending_action is not None:
            log.warning("A confirmation is already pending; dropping %r.", tool_name)
            return False
        _pending_action = {"tool_name": tool_name, "tool_input": tool_input, "reason": reason}
    dashboard.notify({"type": "pending_action", "data": dict(_pending_action)})
    return True


def _take_pending_action() -> dict | None:
    global _pending_action
    with _pending_action_lock:
        step, _pending_action = _pending_action, None
    return step


def _execute_confirmed_action(step: dict, reply_sink=None) -> None:
    tool_name = str(step.get("tool_name") or "")
    tool_input = step.get("tool_input") or {}
    log.info("Confirmed by user: executing staged %s(%r)", tool_name, tool_input)
    result = _execute_tool(tool_name, tool_input, transcript="", skip_confirmation=True)
    reply = result or "Done."
    # A phone-originated command already got its "Message received." ack up front, in
    # handle_text_command — the full result goes back to the phone only, not spoken locally.
    if reply_sink:
        reply_sink(reply)
    else:
        _speak_shaped(reply)


def _dashboard_get_pending() -> dict | None:
    """Read-only snapshot of _pending_action for the dashboard's top approval bar."""
    with _pending_action_lock:
        return dict(_pending_action) if _pending_action is not None else None


def _dashboard_approve_pending() -> str | None:
    """Phase 2: the dashboard's one-click Approve. Per the Phase 0 risk review, the user
    explicitly accepted (2026-09-18, recorded in CLAUDE.md's Dashboard section) that this can
    approve catastrophic-tier actions from the UI — on the condition that the click only ever
    happens from the mandatory detail/review view (see dashboard_static/app.js), never a bare
    list-row button. This calls the *exact same* _execute_confirmed_action used by the spoken
    "yes" path — never a reimplementation — so there is no second, weaker confirmation logic."""
    step = _take_pending_action()
    if not step:
        return None
    log.info(
        "Dashboard approved pending action: %s(%r)", step.get("tool_name"), step.get("tool_input")
    )

    def _sink(reply: str) -> None:
        _speak_shaped(reply)
        dashboard.notify({"type": "pending_result", "data": {"reply": reply}})

    threading.Thread(target=_execute_confirmed_action, args=(step, _sink), daemon=True).start()
    return "Approved — running now."


def _dashboard_reject_pending() -> bool:
    step = _take_pending_action()
    if step:
        log.info(
            "Dashboard rejected pending action: %s(%r)", step.get("tool_name"), step.get("tool_input")
        )
        dashboard.notify({"type": "pending_result", "data": {"reply": "Rejected from dashboard."}})
    return step is not None


def block_samples() -> int:
    n = int(SAMPLE_RATE * BLOCK_MS / 1000)
    return max(n, 1)


def rms_mono(block: np.ndarray) -> float:
    if block.ndim > 1:
        block = np.mean(block.astype(np.float64), axis=1)
    else:
        block = block.astype(np.float64)
    if block.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(block**2)))


def _input_devices() -> list[tuple[int, dict]]:
    return [
        (i, dev)
        for i, dev in enumerate(sd.query_devices())
        if dev["max_input_channels"] >= 1
    ]


def _resolve_input_device_index(spec: str) -> int:
    spec = spec.strip()
    if spec.isdigit():
        idx = int(spec)
        sd.query_devices(idx)
        return idx
    needle = spec.lower()
    for idx, dev in _input_devices():
        if needle in dev["name"].lower():
            return idx
    raise ValueError(f"No input device matches {spec!r}")


def _probe_input_max_rms(device: int, blocksize: int) -> float | None:
    try:
        with sd.InputStream(
            device=device,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=blocksize,
        ) as stream:
            peak = 0.0
            deadline = time.monotonic() + INPUT_PROBE_S
            while time.monotonic() < deadline:
                data, _ = stream.read(blocksize)
                peak = max(peak, rms_mono(data))
            return peak
    except sd.PortAudioError:
        return None


def _choose_input_device(blocksize: int) -> int:
    log.info("Audio devices:\n%s", sd.query_devices())

    override = (os.environ.get("JARVIS_INPUT_DEVICE") or "").strip()
    if override:
        try:
            idx = _resolve_input_device_index(override)
        except ValueError as e:
            log.error("%s", e)
            log.error("Set JARVIS_INPUT_DEVICE to a device index or name substring.")
            raise SystemExit(1) from e
        name = sd.query_devices(idx)["name"]
        peak = _probe_input_max_rms(idx, blocksize)
        log.info("Using JARVIS_INPUT_DEVICE [%d]: %s", idx, name)
        if peak is None:
            log.warning("Could not open configured mic; trying anyway.")
        elif peak < INPUT_SILENT_RMS:
            log.warning(
                "Configured mic looks silent (probe rms=%.5f). "
                "Check Windows input level or try another JARVIS_INPUT_DEVICE.",
                peak,
            )
        else:
            log.info("Mic probe OK (rms=%.5f).", peak)
        return idx

    default = sd.default.device[0]
    if default is not None and default >= 0:
        default_name = sd.query_devices(default)["name"]
        peak = _probe_input_max_rms(default, blocksize)
        if peak is not None and peak >= INPUT_SILENT_RMS:
            log.info(
                "Using default microphone [%d]: %s (probe rms=%.5f)",
                default,
                default_name,
                peak,
            )
            return default
        log.warning(
            "Default mic [%d] %s is silent or unavailable (probe rms=%s); "
            "scanning other inputs...",
            default,
            default_name,
            f"{peak:.5f}" if peak is not None else "unopenable",
        )

    best_idx: int | None = None
    best_peak = -1.0
    for idx, dev in _input_devices():
        if default is not None and idx == default:
            continue
        peak = _probe_input_max_rms(idx, blocksize)
        if peak is not None and peak > best_peak:
            best_peak = peak
            best_idx = idx

    if best_idx is not None and best_peak >= INPUT_SILENT_RMS:
        log.info(
            "Auto-selected microphone [%d]: %s (probe rms=%.5f)",
            best_idx,
            sd.query_devices(best_idx)["name"],
            best_peak,
        )
        return best_idx

    if default is not None and default >= 0:
        log.warning("No active mic found; falling back to default [%d].", default)
        return default
    inputs = _input_devices()
    if not inputs:
        log.error("No input devices found.")
        raise SystemExit(1)
    idx, dev = inputs[0]
    log.warning("No active mic found; falling back to [%d] %s.", idx, dev["name"])
    return idx


_keyboard_warned = False


def _keyboard_is_pressed(key: str) -> bool:
    global _keyboard_warned
    try:
        import keyboard
    except ImportError:
        if not _keyboard_warned:
            _keyboard_warned = True
            log.warning("Install `keyboard` (see requirements.txt) for push-to-talk.")
        return False
    try:
        return bool(keyboard.is_pressed(key))
    except Exception as e:
        if not _keyboard_warned:
            _keyboard_warned = True
            log.warning(
                "Push-to-talk key check failed (%s). On Windows, try running the "
                "terminal as Administrator if the hotkey never fires.",
                e,
            )
        return False


_whisper_model = None
_whisper_lock = threading.Lock()


def _get_whisper_model():
    global _whisper_model
    with _whisper_lock:
        if _whisper_model is None:
            from faster_whisper import WhisperModel

            log.info("Loading local Whisper model (%s)...", WHISPER_MODEL_SIZE)
            _whisper_model = WhisperModel(
                WHISPER_MODEL_SIZE, device="cpu", compute_type="int8"
            )
            log.info("Whisper model ready.")
    return _whisper_model


def _preload_whisper_async() -> None:
    threading.Thread(target=_get_whisper_model, daemon=True).start()


def _resample_to_16k(mono: np.ndarray, orig_sr: int) -> np.ndarray:
    if orig_sr == 16000 or mono.size == 0:
        return mono.astype(np.float32)
    duration = mono.shape[0] / orig_sr
    n_target = max(0, int(round(duration * 16000)))
    if n_target == 0:
        return np.zeros(0, dtype=np.float32)
    orig_idx = np.arange(mono.shape[0]) / orig_sr
    target_idx = np.arange(n_target) / 16000
    return np.interp(target_idx, orig_idx, mono).astype(np.float32)


def transcribe_pcm(pcm: np.ndarray, sample_rate: int) -> str:
    if pcm.ndim > 1:
        mono = np.mean(pcm.astype(np.float64), axis=1).astype(np.float32)
    else:
        mono = pcm.astype(np.float32)
    mono16k = _resample_to_16k(mono, sample_rate)
    if mono16k.size < int(16000 * 0.2):
        return ""
    model = _get_whisper_model()
    language = (os.environ.get("WHISPER_LANGUAGE") or "en").strip() or None
    segments, _info = model.transcribe(mono16k, beam_size=1, language=language)
    return " ".join(seg.text.strip() for seg in segments).strip()


# --- text-to-speech: Fish Audio (cloud) primary, Piper (local/offline/free) fallback -------
# Double-checked (2026-09-18, user request — locked in: free s2.1-pro-free tier, user's own
# reference_id voice, automatic fallback to Piper on any Fish Audio failure): cost is zero on
# the free tier; data exposure is every spoken reply's text leaving the machine to Fish Audio's
# API (same category as every Claude API call already does, not a new kind of exposure);
# reliability is covered by the Piper fallback below, so a network/API outage degrades the
# *voice*, not into silence.
FISH_AUDIO_API_KEY = (os.environ.get("FISH_AUDIO_API_KEY") or "").strip()
FISH_AUDIO_VOICE_ID = (os.environ.get("FISH_AUDIO_VOICE_ID") or "").strip()
FISH_AUDIO_MODEL = (os.environ.get("FISH_AUDIO_MODEL") or "s2.1-pro-free").strip() or "s2.1-pro-free"
FISH_AUDIO_TTS_URL = "https://api.fish.audio/v1/tts"
FISH_AUDIO_TIMEOUT_S = 20

PIPER_VOICE = (os.environ.get("PIPER_VOICE") or "en_US-lessac-medium").strip() or "en_US-lessac-medium"

_piper_voice_obj = None
_piper_lock = threading.Lock()

# On-disk TTS audio cache (.cache/tts/, gitignored): repeated phrases ("Message received.",
# reminder/sleep-mode lines, short acks) skip synthesis entirely. JARVIS_TTS_CACHE=0 disables.
TTS_CACHE_MAX_CHARS = 200
_tts_disk_cache = cache.TTSDiskCache(Path(__file__).resolve().parent / ".cache" / "tts")


def _piper_voices_dir() -> Path:
    base = Path(__file__).resolve().parent
    override = (os.environ.get("PIPER_VOICES_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return base / ".cache" / "piper_voices"


def _get_piper_voice():
    global _piper_voice_obj
    with _piper_lock:
        if _piper_voice_obj is None:
            from piper import PiperVoice
            from piper.download_voices import download_voice

            voices_dir = _piper_voices_dir()
            voices_dir.mkdir(parents=True, exist_ok=True)
            model_path = voices_dir / f"{PIPER_VOICE}.onnx"
            if not model_path.is_file():
                log.info("Downloading Piper voice model (%s, one-time)...", PIPER_VOICE)
                download_voice(PIPER_VOICE, voices_dir)
            log.info("Loading local Piper voice (%s)...", PIPER_VOICE)
            _piper_voice_obj = PiperVoice.load(str(model_path))
            log.info("Piper voice ready.")
    return _piper_voice_obj


def _preload_piper_async() -> None:
    threading.Thread(target=_get_piper_voice, daemon=True).start()


def _piper_synthesize(text: str, syn_overrides: dict | None = None) -> tuple[bytes, int]:
    voice = _get_piper_voice()
    syn_config = None
    if syn_overrides:
        from piper.config import SynthesisConfig

        syn_config = SynthesisConfig(**syn_overrides)
    chunks = list(voice.synthesize(text, syn_config=syn_config))
    if not chunks:
        return b"", voice.config.sample_rate
    raw = b"".join(ch.audio_int16_bytes for ch in chunks)
    return raw, chunks[0].sample_rate


def _fish_audio_synthesize(text: str, prosody_overrides: dict | None = None) -> tuple[bytes, int]:
    """Calls Fish Audio's TTS REST API and returns (pcm_int16_bytes, sample_rate) — the exact
    same contract as _piper_synthesize, so speak_text can use either interchangeably. Requests
    WAV (not raw PCM) specifically so the sample rate is read from the response's own header
    instead of guessed/hardcoded — a WAV file is self-describing, raw PCM isn't. Raises on any
    failure (missing key, network error, non-2xx, malformed audio); the caller decides whether
    to fall back to Piper."""
    if not FISH_AUDIO_API_KEY:
        raise RuntimeError("FISH_AUDIO_API_KEY is not set")
    body: dict = {"text": text, "format": "wav"}
    if FISH_AUDIO_VOICE_ID:
        body["reference_id"] = FISH_AUDIO_VOICE_ID
    if prosody_overrides:
        body["prosody"] = prosody_overrides
    req = urllib.request.Request(
        FISH_AUDIO_TTS_URL,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {FISH_AUDIO_API_KEY}",
            "Content-Type": "application/json",
            "model": FISH_AUDIO_MODEL,
        },
    )
    raw_wav = _urlopen_hard_timeout(req, FISH_AUDIO_TIMEOUT_S)
    with wave.open(io.BytesIO(raw_wav), "rb") as wf:
        sample_rate = wf.getframerate()
        pcm = wf.readframes(wf.getnframes())
    return pcm, sample_rate


def _play_pcm_bytes(raw: bytes, sample_rate: int) -> None:
    pcm_i16 = np.frombuffer(raw, dtype=np.int16)
    pcm_f = pcm_i16.astype(np.float32) / 32768.0
    with _playback_lock:
        jarvis_speaking.set()
        try:
            sd.play(pcm_f, sample_rate)
            sd.wait()
        except Exception as e:
            log.warning("Could not play audio: %s", e)
        finally:
            jarvis_speaking.clear()


# Piper's espeak-based phonemizer has no concept of markdown or symbol-as-word — fed "**Discord**"
# or "$76,300" literally, it tries to pronounce the asterisks/dollar sign as speech sounds and
# produces garbled noise instead of skipping them. Claude's replies are meant to be spoken, not
# displayed, but it still reaches for markdown/raw symbols out of habit (especially when summarizing
# something like a web search result that already contains them), so this is a defensive cleanup
# pass, not the primary fix — see the "never use markdown" instruction in AGENT_SYSTEM_PROMPT.
_SPEECH_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_SPEECH_MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_SPEECH_MD_ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)|_([^_]+)_")
_SPEECH_MD_CODE_RE = re.compile(r"`([^`]+)`")
_SPEECH_MD_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_SPEECH_MD_BULLET_RE = re.compile(r"^\s*[-*•]\s+", re.MULTILINE)
_SPEECH_MD_NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
_SPEECH_DOLLAR_RE = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)")
_SPEECH_HASH_NUM_RE = re.compile(r"#(\d+)\b")
_SPEECH_LEFTOVER_SYMBOLS_RE = re.compile(r"[*_#~^|<>{}\[\]`]")


def _sanitize_for_speech(text: str) -> str:
    """Strips markdown and rewrites symbols Piper's phonemizer mangles into garbled noise, so
    replies are read as natural words instead of nonsense syllables."""
    t = text
    t = _SPEECH_MD_LINK_RE.sub(r"\1", t)
    t = _SPEECH_MD_BOLD_RE.sub(r"\1", t)
    t = _SPEECH_MD_ITALIC_RE.sub(lambda m: m.group(1) or m.group(2) or "", t)
    t = _SPEECH_MD_CODE_RE.sub(r"\1", t)
    t = _SPEECH_MD_HEADER_RE.sub("", t)
    t = _SPEECH_MD_BULLET_RE.sub("", t)
    t = _SPEECH_MD_NUMBERED_RE.sub("", t)
    t = _SPEECH_DOLLAR_RE.sub(lambda m: f"{m.group(1)} dollars", t)
    t = _SPEECH_HASH_NUM_RE.sub(r"number \1", t)
    t = t.replace("&", " and ").replace("%", " percent")
    t = _SPEECH_LEFTOVER_SYMBOLS_RE.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def speak_text(text: str) -> None:
    """Speak arbitrary dynamic text (voice-command replies). Fish Audio (cloud) is the primary
    voice when FISH_AUDIO_API_KEY is set; Piper (local/offline/free) is the automatic fallback
    if Fish Audio errors for any reason (no key, network down, rate limited, bad response) —
    a TTS-provider failure degrades the *voice*, not into silence. Uses Sleep Mode's
    calmer/slower voice settings (see jarvis_sleep_mode.tts_overrides/
    fish_audio_prosody_overrides) when Sleep Mode is active."""
    t = _sanitize_for_speech(text)
    if not t:
        return

    # Disk cache (short phrases only — long one-off replies never repeat and would just churn
    # the cache). Keyed per engine, so a Piper fallback clip is never stored under the Fish
    # key and later served in place of the real voice; on a Fish outage the Fish key can still
    # hit from earlier good audio, which is strictly better than falling back.
    fish_prosody = sleep_mode.fish_audio_prosody_overrides()
    piper_overrides = sleep_mode.tts_overrides()
    use_cache = cache.enabled("tts") and len(t) <= TTS_CACHE_MAX_CHARS
    fish_key = piper_key = None
    if use_cache:
        piper_key = cache.stable_hash("piper", PIPER_VOICE, t, piper_overrides)
        if FISH_AUDIO_API_KEY:
            fish_key = cache.stable_hash(
                "fish", FISH_AUDIO_MODEL, FISH_AUDIO_VOICE_ID, t, fish_prosody
            )
        for key in (fish_key, piper_key):
            hit = _tts_disk_cache.get(key) if key else None
            if hit:
                cache.record("tts", True, repr(t[:30]))
                _play_pcm_bytes(*hit)
                return
        cache.record("tts", False, repr(t[:30]))

    raw, sample_rate = b"", 0
    used_key = None
    if FISH_AUDIO_API_KEY:
        try:
            raw, sample_rate = _fish_audio_synthesize(t, fish_prosody)
            used_key = fish_key
        except Exception as e:
            log.warning("Fish Audio TTS failed, falling back to Piper: %s", e)
            raw = b""

    if not raw:
        try:
            raw, sample_rate = _piper_synthesize(t, piper_overrides)
            used_key = piper_key
        except Exception as e:
            log.warning("Piper TTS failed: %s", e)
            return

    if raw and used_key:
        _tts_disk_cache.put(used_key, raw, sample_rate)

    if not raw:
        log.warning("TTS returned empty audio.")
        return
    _play_pcm_bytes(raw, sample_rate)


def _open_uri(uri: str) -> None:
    u = uri.strip()
    if not u:
        return
    try:
        if sys.platform == "win32":
            os.startfile(u)
        else:
            webbrowser.open(u)
    except OSError as e:
        log.warning("Could not open %s: %s", u, e)


# --- push-to-talk: Claude decides zero or more actions from a fixed, safe set ---------
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_API_VERSION = "2023-06-01"
ALLOWED_APPS = ("cursor", "notepad", "calculator", "explorer", "chrome", "spotify")
ALLOWED_SYSTEM_ACTIONS = (
    "lock",
    "minimize_all",
    "minimize_active",
    "volume_up",
    "volume_down",
    "volume_mute",
    "media_play_pause",
    "media_next",
    "media_previous",
    "media_stop",
)
ALLOWED_MOUSE_BUTTONS = ("left", "right", "middle")
MEMORY_FACT_CATEGORIES = ("preference", "decision", "directive", "goal", "relationship", "fact")
MAX_TOOL_CALLS_PER_TURN = 5  # cap on parallel tool calls Claude can request in one turn
# Cap on observe-act-observe round trips per command. Each round trip resends the full
# message history, so cost per round trip grows with how far into the task you are — but
# it's only spent on commands complex enough to actually need that many tool calls; a
# simple command still stops as soon as Claude replies without a tool_use. Was 6, which a
# compound multi-step instruction (search email, build a file, send it, confirm) could
# exhaust and get cut off mid-task even with nothing going wrong.
MAX_AGENT_ITERATIONS = 12
# Cap on round trips for a single set_plan step (jarvis.py _run_plan_step). Deliberately
# small — a step is meant to be one focused sub-task, not a whole task in itself; if a step
# needs more than this it should probably have been split into two steps in the plan.
MAX_STEP_ITERATIONS = 4
CONVERSATION_HISTORY_MAX_TURNS = 6  # 3 user+assistant exchanges

# Persona names Jarvis uses in speech instead of narrating tool/mechanism names — "I'll give it
# to James" (or "Michael's checking your inbox") reads far more naturally out loud than "I'll
# start a background task" or "let me query the Gmail API." Defined here, ahead of both
# AGENT_SYSTEM_PROMPT and AGENT_TOOLS below (each interpolates them at import time), so renaming
# one later is a single-line change instead of a hunt through every prompt/string.
CODING_AGENT_NAME = "James"  # delegate_to_claude_code's background coding/debugging agent
MAIL_CALENDAR_AGENT_NAME = "Michael"  # Gmail/Calendar MCP tools specifically — no persona for
# delegate_research or any other MCP integration (Slack, Discord, etc.) by explicit request.

AGENT_SYSTEM_PROMPT = f"""You are Jarvis, a desktop voice assistant with real tool access to this \
Windows machine — not a fixed menu of canned actions. The user's spoken command was transcribed by \
local speech recognition and may contain errors.

You have named tools for the common, well-understood things: opening apps/URLs, clicking, typing, \
reading the screen or clipboard, web search, WhatsApp, scanning for large files, and more — use \
whichever matches. For anything that doesn't match a specific tool, reach for run_shell, \
run_python, read_file, write_file, or http_request — general-purpose tools with full system \
access. Never tell the user something "isn't supported" when a shell command, a Python snippet, a \
file operation, or an HTTP call could actually do it; you're expected to figure out how to \
accomplish novel requests with these general tools, the way a capable engineer sitting at this \
machine would.

Call tools as needed — you can call several in a row, look at each result, and decide what to do \
next, before giving your final spoken reply. When you're done, reply with a short (1-4 sentence) \
spoken summary of the outcome; don't narrate tool mechanics. Always end your turn with that \
spoken reply — never end a turn with only a tool call and no text, even when the tool result \
already says everything that needs saying; briefly restate it instead of leaving Jarvis silent.

Your reply is spoken aloud by a text-to-speech engine, not displayed as text — never use markdown \
(no **bold**, no bullet points or numbered lists, no headers, no code blocks/backticks) and never \
use symbols that aren't natural to say out loud. Write numbers and symbols as words instead: "76 \
thousand dollars" not "$76,000", "94 percent" not "94%", "X and Y" not "X & Y". If a tool result \
(e.g. a web search) contains markdown or symbols, rephrase it in plain spoken sentences rather than \
repeating it verbatim.

You have persistent memory across sessions via remember_fact/recall_facts — call remember_fact \
proactively whenever the user states a preference, decision, standing instruction, goal, or fact \
about themselves worth recalling later, without waiting to be asked to "remember" it. Facts you've \
already remembered are listed below in this same prompt every turn; use recall_facts only when you \
need something not already shown there (e.g. older or superseded facts).

Any skills below (under "User-defined skills") are pre-written procedures — follow them when they \
match the request instead of improvising from scratch. When the user asks you to turn something \
you just did into a routine, remember how to do something, or learn a new skill, call save_skill \
so it's available in every future session too. Pass save_skill a "schedule" when the user wants \
something to happen on its own — a daily briefing, a periodic check — instead of only when asked; \
a scheduled skill runs automatically and speaks its result unprompted.

For a one-off or repeating nudge rather than a full recurring procedure, use create_reminder \
instead of save_skill — "remind me in 20 minutes to stretch," "don't let me forget my 3pm call," \
"don't forget your afternoon work session." list_reminders/cancel_reminder manage existing ones. \
Ongoing projects/tasks the user is tracking with you (any "ongoing projects" list below, kept via \
update_project_status) are what makes quick_recall — and future sessions — actually know what's \
going on; call update_project_status whenever the user mentions progress or what's next on \
something, and reach for quick_recall when they ask what you were doing or want to jump back in.

The `gh` CLI is installed and already authenticated on this machine — for GitHub issues, PRs, \
repos, or notifications, run `gh` commands via run_shell rather than guessing at a raw API call. \
Any tools named "mcp_<server>_..." below are live integrations (Gmail, Calendar, Slack, etc., \
depending on what's configured) reached the same way Claude Code reaches its own integrations — \
use them directly like any other tool. Specifically for the Gmail/Calendar tools (mcp_gmail_*, \
mcp_googlecalendar_*) — checking email, reading messages, creating/looking up events — refer to \
it in speech as {MAIL_CALENDAR_AGENT_NAME} handling it (e.g. "Let me have {MAIL_CALENDAR_AGENT_NAME} \
check your inbox" / "{MAIL_CALENDAR_AGENT_NAME}'s adding that to your calendar") rather than \
naming the tool or saying "I checked your email" yourself. Other integrations (Slack, Discord, \
etc.) don't get a persona — just use them plainly.

For actual software development work — writing code, fixing a bug, adding a feature, running a \
test suite — use delegate_to_claude_code instead of doing it yourself with run_shell/write_file. \
It hands the task to a full Claude Code agent, which you refer to by name in speech — \
{CODING_AGENT_NAME} — rather than "Claude Code" or "a background task" (e.g. "I'll hand that \
off to {CODING_AGENT_NAME}, he'll let you know once it's done"). It runs in the background: it \
returns as soon as the task starts, not once it's done, so tell the user {CODING_AGENT_NAME} is \
on it and you'll let them know — then you actually will, unprompted, once {CODING_AGENT_NAME} \
finishes. For a substantial websearch-and-summarize-to-a-file task, use delegate_research the \
same way instead of doing it yourself with web_search/write_file (no persona needed for this \
one) — cheaper, since it skips a \
full Claude Code session. list_background_tasks shows what's currently running if asked.

For a compound instruction that's really several distinct sub-tasks chained together (roughly \
3+ actions — e.g. "find the attachment, summarize it, save a PDF, email it back, then delete \
the old email and send the update"), use set_plan instead of working through every step \
inline here: it runs each step as its own focused background request, checkpoints progress \
after each one, and respects the ordering you give it via depends_on. Don't use it for a \
simple 1-2 step ask — just do those directly. No persona for set_plan itself; the steps \
inside it still use James/{MAIL_CALENDAR_AGENT_NAME} where those tools apply.

For real technical/coding work, reach for these proactively rather than only when explicitly \
asked: get_workflow_status to ground yourself in the current repo's actual git branch/state before \
starting or picking up a task (any workspace context already known is shown below); \
check_project_health before/after significant coding work to catch bare excepts, hardcoded \
secrets, leftover merge markers, and similar issues early rather than after they cause a real bug; \
analyze_error whenever the user reads or pastes an error/traceback back to you, instead of just \
repeating it; analyze_code and trace_dependencies when asked to review a file or judge the impact \
of changing/removing something across a multi-file project. Use remember_decision (not just \
remember_fact) when the user explains *why* they chose something, and remember_code_pattern when \
they state or demonstrate a coding convention they want followed consistently — both make future \
suggestions better-informed. semantic_recall is recall_facts' sibling for when the right memory \
probably exists but the wording won't literally match a keyword search.

Jarvis watches Downloads (and any folder added via add_watched_folder) for new/changed files in \
the background and already announces large ones (over 100MB) unprompted — use \
list_watched_folders/get_recent_file_events/remove_watched_folder only when the user asks about \
watched folders directly, not proactively.

For window management, use control_window (minimize/maximize/restore/close/snap/resize by \
title substring — resize takes width/height in pixels or width_percent/height_percent for a \
free-form size, snap is for the fixed preset zones), resize_all_windows when the user means \
every open window rather than one, arrange_windows to lay out several at once, and \
save_window_layout/restore_window_layout to name and recall a set of window positions later.

For something the user wants done "sometime today" rather than at an exact time, use \
queue_task (not create_reminder, which is for an exact time) then plan_task_queue to give it \
a slot — if the user has Calendar access connected, fetch their events first and pass them as \
plan_task_queue's busy_intervals so queued tasks land in real free time instead of over a \
meeting. list_task_queue/cancel_queued_task manage what's already queued.

Jarvis already reads a rough emotional tone off spoken/typed commands (frustrated, urgent, \
curious, sad, positive) and folds it into this very prompt as "Voice tone detected" when \
confident enough — there's no tool for this, just let it shape how you respond (terser when \
frustrated, more explanatory when curious, etc.) without narrating that you detected it.

One narrow tier of action stays gated: shutting down/restarting/signing out the machine, \
reformatting or repartitioning a disk, and recursively wiping an entire drive or the user's whole \
profile. If a run_shell or run_python call would do one of those, it gets staged instead of run — \
say what you're about to do and that the user needs to say "yes" on their next turn to actually run \
it. You MUST actually make that run_shell/run_python call (e.g. run_shell with `shutdown /s /t 0` \
for "shut down my computer") — the call is what stages the action and puts it in front of the user \
(dashboard approval bar and the spoken "yes" path). NEVER tell the user you're about to shut down, \
restart, or wipe anything, or ask them to say "yes", without having made that tool call in the same \
turn: with no call nothing is staged, nothing appears on the dashboard, and their "yes" does \
nothing. Every other action, including individual file deletes, sending messages, and clicking, \
executes immediately with no confirmation — the user has explicitly asked for that.

If a request is genuinely ambiguous (e.g. which of several possible files/contacts/windows they \
mean), ask a brief clarifying question in your reply instead of guessing — but don't ask just \
because something isn't in a predefined list; try the general tools first."""

AGENT_TOOLS = [
    {
        "name": "open_url",
        "description": "Open a full https URL in the default browser.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "play_media",
        "description": (
            "Open a spotify: URI or a full https URL (e.g. a YouTube search/results URL) to "
            "play a song, artist, or playlist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "open_app",
        "description": "Open or focus a known desktop application.",
        "input_schema": {
            "type": "object",
            "properties": {"app": {"type": "string", "enum": list(ALLOWED_APPS)}},
            "required": ["app"],
        },
    },
    {
        "name": "system_action",
        "description": (
            "Run a system-level action: lock the workstation, minimize windows, or control "
            "media/volume."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "system_action": {"type": "string", "enum": list(ALLOWED_SYSTEM_ACTIONS)},
            },
            "required": ["system_action"],
        },
    },
    {
        "name": "read_screen",
        "description": (
            "Take a screenshot and have a vision model describe, explain, summarize, or debug "
            "what's on screen. If the user explicitly asked for a visible error/bug to be "
            "fixed/corrected/typed (not just explained), the correction is typed out automatically."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "web_search",
        "description": "Search the web and summarize the top results.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "type_text",
        "description": (
            "Type exact text at the user's current cursor/focus. Never presses Enter or "
            "submits anything."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "system_status",
        "description": "Report machine health: CPU, RAM, disk, battery, uptime.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "api_spend",
        "description": (
            "Report how much the user has spent on the Anthropic (Claude) API. Uses Anthropic's "
            "own billing data when an admin key is configured (total for the last N days, "
            "today's spend, biggest models); otherwise gives Jarvis's own locally-tracked "
            "estimate (today, last 7 days, this month, all time, and what prompt caching saved). "
            "Use for questions like 'how much have I spent on Claude', 'what's my API bill', "
            "'how much did Jarvis cost today'. Read-only."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "How many days back to include (default 30, max 90). Use 1 for today only.",
                }
            },
        },
    },
    {
        "name": "read_clipboard",
        "description": "Read and describe/summarize whatever is currently on the clipboard.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "refactor_clipboard_code",
        "description": (
            "Fix, clean up, or refactor a code snippet currently on the clipboard. The result "
            "is typed out and copied back to the clipboard automatically."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "click_at",
        "description": (
            "Click the mouse at an explicit screen pixel position. Only use with coordinates "
            "the user stated, or that were already established earlier in the conversation "
            "(e.g. from read_screen) — never guess."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "button": {"type": "string", "enum": list(ALLOWED_MOUSE_BUTTONS)},
                "clicks": {"type": "integer", "description": "1 for single click, 2 for double-click"},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "drag_and_drop",
        "description": "Drag from one explicit screen position to another. Same coordinate caveat as click_at.",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "end_x": {"type": "integer"},
                "end_y": {"type": "integer"},
                "button": {"type": "string", "enum": list(ALLOWED_MOUSE_BUTTONS)},
            },
            "required": ["x", "y", "end_x", "end_y"],
        },
    },
    {
        "name": "scroll_screen",
        "description": "Scroll at the current cursor position, or an explicit x/y.",
        "input_schema": {
            "type": "object",
            "properties": {
                "scroll_amount": {
                    "type": "integer",
                    "description": "signed; positive = up, negative = down",
                },
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            },
            "required": ["scroll_amount"],
        },
    },
    {
        "name": "focus_window",
        "description": "Bring an application window to the front by a substring of its title.",
        "input_schema": {
            "type": "object",
            "properties": {"window_title": {"type": "string"}},
            "required": ["window_title"],
        },
    },
    {
        "name": "sleep_mode",
        "description": (
            "Turn Jarvis's Sleep Mode on, off, or check its status. Sleep Mode quiets "
            "non-urgent notifications and reminders (family/whitelisted senders and urgent "
            "items still get through), switches to dark mode, lowers system volume, "
            "auto-pauses media after a while, blocks distracting sites, speaks more softly "
            "and briefly, and logs how long you slept."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"action": {"type": "string", "enum": ["on", "off", "toggle", "status"]}},
            "required": ["action"],
        },
    },
    {
        "name": "schedule_sleep_wakeup",
        "description": (
            "Set a smart wake-up alarm for when Sleep Mode is on: volume gradually ramps up "
            "before the target time, Jarvis speaks a short morning greeting, and Sleep Mode "
            "turns itself off."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "wake_time": {"type": "string", "description": "24h HH:MM, e.g. '07:30'"},
                "ramp_minutes": {
                    "type": "integer",
                    "description": "how many minutes before wake_time to start the volume ramp, default 10",
                },
            },
            "required": ["wake_time"],
        },
    },
    {
        "name": "play_ambient_sound",
        "description": "Play calming ambient/sleep sounds to help you fall asleep.",
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": list(sleep_mode.AMBIENT_SOUNDS.keys())},
            },
            "required": ["kind"],
        },
    },
    {
        "name": "guided_breathing_exercise",
        "description": "Speak a short guided breathing exercise to help you relax before sleep.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "send_whatsapp_message",
        "description": (
            "Send a WhatsApp message to a contact by name via WhatsApp Desktop. Fires "
            "immediately — only call this when both the contact and exact message are clearly "
            "stated; never invent either."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "contact_name": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["contact_name", "message"],
        },
    },
    {
        "name": "scan_large_files",
        "description": "Recursively scan a folder/drive (read-only, never deletes) for large files/folders.",
        "input_schema": {
            "type": "object",
            "properties": {
                "root_path": {"type": "string", "description": "omit for the user's home folder"},
                "min_size_gb": {"type": "number", "description": "default 2.0"},
            },
        },
    },
    {
        "name": "run_shell",
        "description": (
            "Run an arbitrary Windows PowerShell command with full system access — the "
            "general-purpose escape hatch for anything not covered by a more specific tool "
            "above. Prefer a specific tool when one exists (it's more reliable); reach for "
            "this for everything else rather than saying something can't be done. Returns "
            "stdout/stderr/exit code. A narrow tier of commands that would shut down/restart/"
            "sign out the machine, reformat a disk, or recursively wipe an entire drive or the "
            "whole user profile is staged instead of run immediately, and needs a spoken \"yes\" "
            "on the next turn — everything else executes right away with no confirmation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "run_python",
        "description": (
            "Run arbitrary Python code (in a fresh subprocess, stdout/stderr captured) with "
            "full system access — for anything a shell one-liner can't express cleanly. Same "
            "confirmation carve-out as run_shell for the shutdown/reformat/whole-drive-wipe tier."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a text file from anywhere on disk and return its contents (truncated if very large).",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write (or append to) a text file anywhere on disk, creating parent folders if needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "append": {"type": "boolean", "description": "true to append instead of overwrite"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "http_request",
        "description": "Make an arbitrary HTTP request (any API, webhook, or URL) and return the response.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "method": {"type": "string", "description": "default GET"},
                "headers": {"type": "object", "description": "optional header map"},
                "body": {"type": "string", "description": "optional request body"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "remember_fact",
        "description": (
            "Permanently remember something durable about the user for future sessions: a "
            "preference, decision, standing instruction/directive, goal, or relationship. Call "
            "this whenever the user states something worth recalling later — don't wait to be "
            "asked to remember. If this updates or contradicts an earlier fact of the same "
            "kind, pass the same \"key\" so the old one is marked superseded instead of "
            "duplicated (e.g. key=\"editor_theme\" for both \"prefers dark mode\" and a later "
            "\"actually prefers light mode\" — both stay in history, but only the latest counts)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": list(MEMORY_FACT_CATEGORIES)},
                "content": {"type": "string", "description": "the fact, in plain words"},
                "key": {
                    "type": "string",
                    "description": "optional short slug grouping updates to the same fact over time",
                },
            },
            "required": ["category", "content"],
        },
    },
    {
        "name": "recall_facts",
        "description": (
            "Search remembered facts about the user beyond what's already listed in your "
            "system prompt — useful for digging into older or superseded facts (e.g. \"what did "
            "I used to prefer before I changed my mind\")."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "keyword to search for; omit to list the most recent facts",
                },
                "include_superseded": {
                    "type": "boolean",
                    "description": "true to include outdated/replaced facts",
                },
            },
        },
    },
    {
        "name": "save_skill",
        "description": (
            "Save a reusable, step-by-step procedure as a named skill for future sessions. "
            "Use this when the user asks you to learn, remember how to do, or turn into a "
            "routine something you just did or figured out (e.g. \"make this your morning "
            "briefing\", \"remember these steps for next time\", \"turn this into a skill\"). "
            "Skills are automatically loaded into every future conversation's system prompt and "
            "followed whenever they match what's being asked — you carry out the steps using "
            "your normal tools (run_shell, web_search, etc.), the skill just codifies the "
            "procedure so you don't have to work it out from scratch again. Pass \"schedule\" "
            "to make it run automatically, proactively speaking the result, instead of only "
            "when asked (e.g. \"give me a briefing every morning at 8\", \"check this every 30 "
            "minutes\")."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "short identifier, e.g. morning_briefing or free_up_ram",
                },
                "description": {
                    "type": "string",
                    "description": "when this skill should be used",
                },
                "instructions": {
                    "type": "string",
                    "description": (
                        "the step-by-step procedure to follow, referencing tools by name where "
                        "relevant (e.g. \"run_shell to list...\")"
                    ),
                },
                "schedule": {
                    "type": "object",
                    "description": (
                        "optional — makes this skill run on its own, unprompted, speaking "
                        "whatever it produces. Provide exactly one of the two properties below. "
                        "Omit \"schedule\" entirely for a skill that only runs when asked."
                    ),
                    "properties": {
                        "daily_at": {
                            "type": "string",
                            "description": "24-hour local time, e.g. \"08:00\", to run once a day",
                        },
                        "every_minutes": {
                            "type": "number",
                            "description": "run repeatedly on this interval instead of daily",
                        },
                    },
                },
            },
            "required": ["name", "instructions"],
        },
    },
    {
        "name": "create_reminder",
        "description": (
            "Schedule a reminder Jarvis will bring up on its own later, at a specific time "
            "(\"due_at\") or after a delay (\"due_in_minutes\"), optionally repeating. Use this "
            "whenever the user asks to be reminded, nudged, or followed up with later (e.g. "
            "\"remind me in 30 minutes to take a break\", \"don't let me forget my 3pm call\", "
            "\"check in on that project every couple hours\", \"don't forget your afternoon work "
            "session\"). Delivered through the same interrupt-aware channel as other proactive "
            "notices — it won't talk over the user mid-focus-block, but is never lost, and gets "
            "spoken as soon as they next talk to Jarvis if it was held back."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "what to remind the user about"},
                "due_at": {
                    "type": "string",
                    "description": (
                        "an absolute local date/time, e.g. \"2026-09-16 15:00\" — use this for a "
                        "specific time the user named"
                    ),
                },
                "due_in_minutes": {
                    "type": "number",
                    "description": "minutes from now — use this for a relative delay instead of due_at",
                },
                "repeat_every_minutes": {
                    "type": "number",
                    "description": "optional — repeat this reminder on this interval instead of firing once",
                },
                "urgent": {
                    "type": "boolean",
                    "description": "true to speak it immediately even during the user's focus hours",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "list_reminders",
        "description": "List upcoming (or all) reminders that have been scheduled.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_delivered": {
                    "type": "boolean",
                    "description": "true to also show already-delivered ones",
                },
            },
        },
    },
    {
        "name": "cancel_reminder",
        "description": "Cancel a scheduled reminder by its id, as shown by list_reminders.",
        "input_schema": {
            "type": "object",
            "properties": {"reminder_id": {"type": "integer"}},
            "required": ["reminder_id"],
        },
    },
    {
        "name": "queue_task",
        "description": (
            "Add a task to the free-time queue — for something that should happen 'at some "
            "point during free time' rather than at an exact time (use create_reminder for "
            "an exact time). Call plan_task_queue afterward to actually give it a slot. If "
            "instructions is given, Jarvis runs it itself (like a scheduled skill) when its "
            "slot arrives; otherwise it just becomes a spoken nudge to go do it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "estimate_minutes": {"type": "integer", "description": "how long this should take, default 30"},
                "priority": {"type": "string", "enum": list(task_scheduler.PRIORITY_LEVELS)},
                "instructions": {"type": "string", "description": "optional — what Jarvis itself should do when the slot arrives"},
                "earliest_start": {"type": "string", "description": "optional ISO datetime — don't schedule before this"},
                "deadline": {"type": "string", "description": "optional ISO datetime — must finish by this"},
            },
            "required": ["description"],
        },
    },
    {
        "name": "plan_task_queue",
        "description": (
            "Fit every pending queued task into free time slots. Pass busy_intervals fetched "
            "from the user's calendar (e.g. via mcp_googlecalendar_* tools) as a list of "
            "{start, end} ISO datetimes so tasks don't land on top of real events; omit it to "
            "plan against a plain 9am-9pm workday with no calendar awareness. Call this after "
            "queue_task, or to replan after checking the calendar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "busy_intervals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"start": {"type": "string"}, "end": {"type": "string"}},
                    },
                    "description": "busy time blocks to schedule around, e.g. from the calendar",
                },
                "day_start": {"type": "string", "description": "e.g. '09:00', default 09:00"},
                "day_end": {"type": "string", "description": "e.g. '21:00', default 21:00"},
            },
        },
    },
    {
        "name": "list_task_queue",
        "description": "List queued tasks and their planned time slots (or all, including finished, if asked).",
        "input_schema": {
            "type": "object",
            "properties": {"include_done": {"type": "boolean"}},
        },
    },
    {
        "name": "cancel_queued_task",
        "description": "Cancel a pending or scheduled queued task by its id, as shown by list_task_queue.",
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "update_project_status",
        "description": (
            "Record or update the status and next step of an ongoing project or task the user "
            "is tracking with you. Call this whenever the user mentions progress, a milestone, "
            "or what's next on something they're working on — this is what makes quick_recall "
            "and future sessions actually know what's going on, instead of the user having to "
            "re-explain. Facts here persist across restarts and show up in every future prompt."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "short project/task name"},
                "status": {"type": "string", "description": "current status in a few words"},
                "next_step": {"type": "string", "description": "the next concrete action, if known"},
            },
            "required": ["name", "status"],
        },
    },
    {
        "name": "quick_recall",
        "description": (
            "Summarize where things were left off: ongoing projects and their next steps, "
            "recently run commands or skills, the last thing the user was active in, and any "
            "upcoming reminders. Use this when the user asks something like \"what were we "
            "doing\", \"catch me up\", or \"where did we leave off\"."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_llm_provider",
        "description": (
            "Switch which AI brain answers the user: 'claude' (Anthropic) or 'gemini' (Google "
            "AI Studio). Takes effect immediately, no restart. Use for 'switch to Gemini', "
            "'use Claude again', 'change your brain/model provider'. Tell the user the result "
            "(it includes a data-privacy note when switching to Gemini's free tier)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"provider": {"type": "string", "enum": ["claude", "gemini"]}},
            "required": ["provider"],
        },
    },
    {
        "name": "change_jarvis_code",
        "description": (
            "Add a feature to, fix, or otherwise change JARVIS'S OWN source code (this very "
            "assistant) by handing it to the background coding agent, pre-loaded with this "
            "project's rules (follow CLAUDE.md, never weaken the confirmation gate, add tests, "
            "commit locally but never push or restart). Use for any request like 'add a "
            "feature to yourself', 'make Jarvis able to X', 'change how you Y', 'fix your own "
            "bug'. Runs in the background and returns once *started*; refer to the agent as "
            f"{CODING_AGENT_NAME}. The running Jarvis keeps its old code until the user "
            "restarts it — say so when it reports back. Only one self-change runs at a time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "feature": {
                    "type": "string",
                    "description": "the feature or change to make, as a clear, complete instruction",
                }
            },
            "required": ["feature"],
        },
    },
    {
        "name": "delegate_to_claude_code",
        "description": (
            "Delegate a real software development task — writing code, fixing a bug, adding a "
            "feature, refactoring, running tests — to a full headless Claude Code agent, "
            "instead of doing it yourself with run_shell/write_file. Claude Code has a far "
            "larger toolset built for exactly this (repo-wide search, diff-aware editing, "
            "git/test awareness) and will do a better job on anything beyond a one-off command. "
            "This runs in the background and returns immediately once the task is *started*, "
            "not once it's finished. In your spoken reply, refer to this agent by name — "
            f"{CODING_AGENT_NAME} — instead of saying \"Claude Code\" or \"a background task\" "
            f"(e.g. \"I'll hand that off to {CODING_AGENT_NAME}, he'll let you know once it's "
            "done\"), then move on — the user can keep talking to you about other things while "
            f"{CODING_AGENT_NAME} works. It reports back on its own (toast plus a spoken "
            "summary) once it finishes; list_background_tasks shows what's still running if "
            "asked. Reach for this for actual coding/repo work; use run_shell/run_python "
            "directly for quick one-liners."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "what to build/fix/change, as a clear, complete instruction",
                },
                "repo_path": {
                    "type": "string",
                    "description": (
                        "absolute path to the OTHER project/repo to work in. To change "
                        "Jarvis itself use change_jarvis_code instead — never guess Jarvis's "
                        "path; omitting this defaults to Jarvis's own folder"
                    ),
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "delegate_research",
        "description": (
            "Run a websearch-and-summarize task in the background and save the findings to a "
            "file, without blocking — reach for this instead of web_search+write_file "
            "yourself when the task is substantial enough that the user wants to keep talking "
            "to you while it runs. Cheaper and faster than delegate_to_claude_code since it "
            "doesn't spin up a full Claude Code session; use delegate_to_claude_code instead "
            "for anything that needs actual repo/code work. Like delegate_to_claude_code, this "
            "returns immediately once started and reports back on its own when done."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "what to research and summarize, as a clear, complete instruction",
                },
                "output_path": {
                    "type": "string",
                    "description": (
                        "absolute path to save the summary to; omit to default to a "
                        "timestamped file under ~/Jarvis_Research/"
                    ),
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "list_background_tasks",
        "description": (
            "List background tasks started with delegate_to_claude_code, delegate_research, "
            "or set_plan — what's currently running (a plan shows \"step N/M\" progress) and "
            "(optionally) what already finished. Use this if the user asks \"is that done yet\" "
            "or \"what's still running\" instead of just waiting for the completion notification."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "include_finished": {
                    "type": "boolean",
                    "description": "true to also show recently finished/failed tasks, not just running ones",
                },
            },
        },
    },
    {
        "name": "set_plan",
        "description": (
            "For a compound instruction made of multiple distinct sub-tasks — e.g. \"check the "
            "attached file, summarize it, save it as a PDF, email it back, then delete the old "
            "email and send the update\" — break it into an ordered list of steps instead of "
            "working through them all inline in this conversation. Each step then runs in the "
            "background as its own small, focused request against a slim context (not the "
            "whole growing history), and progress is checkpointed after every step so a crash "
            "or a stuck request only loses the one in-flight step, not the whole task. Use "
            "depends_on to encode real ordering constraints (e.g. \"delete the old email\" has "
            "no prerequisite, but if the old one must be gone before the new one sends, give "
            "the send step a depends_on on the delete step) — don't just chain every step "
            "after the previous one by default; only add a dependency where the order actually "
            "matters. Only reach for this for genuinely multi-step requests (roughly 3+ "
            "distinct actions); a 1-2 step request should just be done directly with the "
            "normal tools instead. After calling this, tell the user you've started working "
            "through it in the background and will let them know when it's done — don't also "
            "try to perform the steps yourself in this same turn."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "description": "ordered list of sub-tasks that make up the full request",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {
                                "type": "string",
                                "description": "one concrete, self-contained sub-task",
                            },
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": (
                                    "0-based indices of steps in this same list that must "
                                    "complete before this one starts; omit or leave empty if "
                                    "this step has no prerequisites"
                                ),
                            },
                        },
                        "required": ["description"],
                    },
                },
            },
            "required": ["steps"],
        },
    },
    {
        "name": "get_workflow_status",
        "description": (
            "Report on the current development workspace: detected stack, git branch and "
            "uncommitted-change count, whether this is a context switch from the last "
            "workspace worked in, and concrete suggestions (e.g. commit before switching, "
            "pull before continuing). Use this when the user asks what they were working on "
            "technically, or before starting a coding task, to ground yourself in the repo's "
            "actual state instead of guessing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "project folder to inspect; omit to use the last-touched workspace",
                },
            },
        },
    },
    {
        "name": "check_project_health",
        "description": (
            "Proactively scan a project folder (or a single file) for concrete bug-risk, "
            "security, and performance red flags — bare excepts, swallowed exceptions, "
            "leftover merge-conflict markers, hardcoded secrets/keys, eval/exec on dynamic "
            "input, shell=True subprocess calls, string-built SQL, suspicious nested loops. "
            "Findings are tracked across scans so repeat calls show what's new, what's still "
            "open, and what got fixed. Use this before/after significant coding work, or "
            "whenever the user asks you to check a project for problems."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"root_path": {"type": "string", "description": "folder or file to scan"}},
            "required": ["root_path"],
        },
    },
    {
        "name": "list_watched_folders",
        "description": (
            "List the folders Jarvis is currently watching for new/changed files (Downloads "
            "by default). Use this when the user asks what's being watched."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "add_watched_folder",
        "description": "Start watching an additional folder for new/changed files.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "folder to watch"}},
            "required": ["path"],
        },
    },
    {
        "name": "remove_watched_folder",
        "description": "Stop watching a folder for new/changed files.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "folder to stop watching"}},
            "required": ["path"],
        },
    },
    {
        "name": "get_recent_file_events",
        "description": (
            "Report recent new/changed files seen in watched folders, most recent first, "
            "flagging anything large. Use this when the user asks what showed up in Downloads "
            "(or another watched folder) recently."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "max events to return, default 20"}},
        },
    },
    {
        "name": "list_open_windows",
        "description": "List titles of all visible open windows.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "control_window",
        "description": (
            "Minimize, maximize, restore, close, snap, or resize a single open window by a "
            "substring of its title. For snap, pass a side: left, right, top, bottom, "
            "top-left, top-right, bottom-left, bottom-right, maximize, or center (fixed preset "
            "zones). For resize, pass an arbitrary width/height in pixels, or width_percent/ "
            "height_percent (e.g. 50 for half the screen) — use this for a free-form size the "
            "user asks for, not one of the preset snap zones."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "window_title": {"type": "string", "description": "substring of the target window's title"},
                "action": {
                    "type": "string",
                    "enum": ["minimize", "maximize", "restore", "close", "snap", "resize"],
                },
                "side": {
                    "type": "string",
                    "enum": list(window_control.SNAP_SIDES),
                    "description": "required when action is snap",
                },
                "width": {"type": "integer", "description": "pixels; for action=resize"},
                "height": {"type": "integer", "description": "pixels; for action=resize"},
                "width_percent": {"type": "number", "description": "percent of screen width; for action=resize"},
                "height_percent": {"type": "number", "description": "percent of screen height; for action=resize"},
            },
            "required": ["window_title", "action"],
        },
    },
    {
        "name": "resize_all_windows",
        "description": (
            "Resize every visible open window to the same size at once — use this when the "
            "user asks to resize \"all my windows\" rather than one specific window. Pass "
            "width/height in pixels, or width_percent/height_percent for a percent of the "
            "screen. Minimized windows are left alone."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "width": {"type": "integer"},
                "height": {"type": "integer"},
                "width_percent": {"type": "number"},
                "height_percent": {"type": "number"},
            },
        },
    },
    {
        "name": "arrange_windows",
        "description": (
            "Arrange two or more open windows (matched by title substring) into a layout: "
            "side-by-side (columns), grid, or cascade."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "window_titles": {"type": "array", "items": {"type": "string"}},
                "layout": {"type": "string", "enum": list(window_control.ARRANGE_LAYOUTS)},
            },
            "required": ["window_titles"],
        },
    },
    {
        "name": "save_window_layout",
        "description": (
            "Save the position/size/state of currently open windows under a name, to restore "
            "later. Omit window_titles to snapshot every visible window."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "window_titles": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["name"],
        },
    },
    {
        "name": "restore_window_layout",
        "description": "Restore a previously saved window layout by name.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "list_window_layouts",
        "description": "List saved window layout names.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "analyze_error",
        "description": (
            "Parse a raw error message or traceback (Python, JavaScript/Node, or a bare HTTP "
            "status) into a structured explanation: error type, likely cause, a concrete "
            "suggested fix, and the failure location. Use this whenever the user pastes/reads "
            "an error back to you, instead of just repeating the raw text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"error_text": {"type": "string"}},
            "required": ["error_text"],
        },
    },
    {
        "name": "analyze_code",
        "description": (
            "Structural analysis of a single Python file via its AST: functions/classes "
            "found, and flags for long functions, high branch-complexity, and missing "
            "docstrings on public names. Use this when the user asks you to review or "
            "understand a specific Python file's structure."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "path to a .py file"}},
            "required": ["path"],
        },
    },
    {
        "name": "trace_dependencies",
        "description": (
            "Build the import graph for a Python project directory. Omit 'target' for an "
            "overview (module count, most-imported modules); pass 'target' (a module or file "
            "name) to see what it imports and, just as importantly, what else in the project "
            "imports it — use this before changing or removing something, to see the blast "
            "radius across files."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "root_path": {"type": "string", "description": "project root to walk"},
                "target": {"type": "string", "description": "optional module/file name to trace"},
            },
            "required": ["root_path"],
        },
    },
    {
        "name": "remember_decision",
        "description": (
            "Record a decision along with its rationale and the alternatives considered — "
            "richer than remember_fact, meant for choices worth revisiting later (an "
            "architecture call, a tool choice, a tradeoff). Call this when the user explains "
            "*why* they chose something, not just what they chose."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "decision": {"type": "string"},
                "rationale": {"type": "string", "description": "why this was chosen"},
                "alternatives": {"type": "string", "description": "what else was considered, if mentioned"},
                "project": {"type": "string", "description": "optional project this decision belongs to"},
            },
            "required": ["decision"],
        },
    },
    {
        "name": "remember_code_pattern",
        "description": (
            "Record a code style or convention the user prefers (e.g. \"uses early returns "
            "over nested if/else\", \"prefers dataclasses over plain dicts for config\"). Call "
            "this when the user states or demonstrates a coding preference worth applying "
            "consistently later."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "the preferred pattern/convention"},
                "language": {"type": "string", "description": "optional language/framework it applies to"},
                "example": {"type": "string", "description": "optional short code example"},
                "note": {"type": "string", "description": "optional extra context"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "semantic_recall",
        "description": (
            "Search remembered facts, decisions, and code patterns by meaning rather than "
            "exact keyword overlap (unlike recall_facts, which is a literal SQL LIKE match). "
            "Use this when the user asks to recall something related to a topic but the exact "
            "wording likely differs from how it was originally phrased."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]


CLAUDE_UNAVAILABLE_REPLY = "Sorry, I couldn't reach Claude just now."
CLAUDE_MAX_ATTEMPTS = 3
CLAUDE_RETRY_DELAY_S = 1.5


def _urlopen_hard_timeout(req: urllib.request.Request, timeout: int) -> bytes:
    """urlopen(timeout=...) is supposed to bound the whole call, but a wedged TLS connection
    has been observed in practice to hang well past its declared socket timeout (seen right
    after an SSLV3_ALERT_BAD_RECORD_MAC on this machine — the retry that followed never timed
    out or logged anything, silently hanging the agent loop for minutes). Enforce the cap from
    the outside with a watchdog thread instead of trusting urlopen alone. If the request thread
    is still alive after the deadline, it's abandoned (daemon, so it dies with the process) and
    this raises TimeoutError — leaking one stuck socket is a fine trade against hanging the
    caller forever."""
    outcome: dict = {}

    def _do() -> None:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                outcome["data"] = resp.read()
        except Exception as e:
            outcome["error"] = e

    t = threading.Thread(target=_do, daemon=True)
    t.start()
    t.join(timeout + 5)  # small grace period past urlopen's own timeout
    if t.is_alive():
        raise TimeoutError(f"Claude request wedged past {timeout}s (urlopen's own timeout didn't fire)")
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("data", b"")


_cache_ttl_1h_rejected = False


def _has_cache_ttl(obj) -> bool:
    if isinstance(obj, dict):
        return ("cache_control" in obj and "ttl" in (obj["cache_control"] or {})) or any(
            _has_cache_ttl(v) for v in obj.values()
        )
    return isinstance(obj, list) and any(_has_cache_ttl(v) for v in obj)


def _strip_cache_ttl(obj):
    if isinstance(obj, dict):
        return {
            k: ({kk: vv for kk, vv in v.items() if kk != "ttl"} if k == "cache_control" and isinstance(v, dict) else _strip_cache_ttl(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_strip_cache_ttl(v) for v in obj]
    return obj


# --- LLM provider switch: Claude (default) or Gemini (Google AI Studio) ------------------------
# Callers all build Anthropic-format requests; when the provider is gemini, _claude_request hands
# the body to jarvis_gemini.call, which translates it and returns an Anthropic-shaped response, so
# nothing above this layer knows or cares which brain answered. Precedence: llm_provider.json
# (written by the set_llm_provider tool / dashboard chip) > JARVIS_LLM_PROVIDER env > "claude".
LLM_SETTINGS_PATH = Path(__file__).resolve().parent / "llm_provider.json"


def _llm_provider() -> str:
    return gemini.get_provider(LLM_SETTINGS_PATH)


def _llm_configured() -> bool:
    if _llm_provider() == "gemini":
        return bool(gemini.api_key())
    return bool((os.environ.get("ANTHROPIC_API_KEY") or "").strip())


def _llm_unavailable_reply() -> str:
    return "Sorry, I couldn't reach Gemini just now." if _llm_provider() == "gemini" else CLAUDE_UNAVAILABLE_REPLY


def _llm_status() -> dict:
    return {
        "provider": _llm_provider(),
        "gemini_model": gemini.model_name(),
        "claude_model": CLAUDE_MODEL,
        "claude_configured": bool((os.environ.get("ANTHROPIC_API_KEY") or "").strip()),
        "gemini_configured": bool(gemini.api_key()),
    }


def set_llm_provider(provider: str) -> str:
    """Switches the brain for every following request (no restart). Refuses a provider whose
    key isn't configured, so a typo can't leave Jarvis with no working brain."""
    provider = (provider or "").strip().lower()
    if provider not in gemini.PROVIDERS:
        return f"Unknown brain {provider!r}; choose claude or gemini."
    if provider == "gemini" and not gemini.api_key():
        return "Gemini isn't set up: add GEMINI_API_KEY to the .env file and restart Jarvis."
    if provider == "claude" and not (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        return "Claude isn't set up: ANTHROPIC_API_KEY is missing."
    gemini.set_provider(LLM_SETTINGS_PATH, provider)
    _invalidate_read_caches()
    if provider == "gemini":
        return (
            f"Switched to Gemini ({gemini.model_name()}). Note: on Google's free tier, your "
            "prompts and Jarvis's tool results may be used by Google to improve its products."
        )
    return f"Switched to Claude ({CLAUDE_MODEL})."


def _record_api_usage(body: dict, result: dict) -> None:
    """Logs this response's token usage + estimated cost to the api_usage table (dashboard's
    Usage tab, api_spend tool). Runs on its own short-lived thread so a slow or locked SQLite
    write can never delay — or deadlock against a caller already holding the DB lock — the
    Claude call it records. Best-effort: record_usage swallows every error."""
    usage = (result or {}).get("usage") if isinstance(result, dict) else None
    if not usage:
        return
    threading.Thread(
        target=billing.record_usage,
        args=(
            _memory_db_connect, _memory_db_lock,
            (result or {}).get("model") or (body or {}).get("model") or CLAUDE_MODEL, usage,
        ),
        daemon=True,
    ).start()


def _claude_request(body: dict, timeout: int) -> dict | None:
    if _llm_provider() == "gemini":
        result = gemini.call(body, timeout, _urlopen_hard_timeout)
        if result is not None:
            _record_api_usage(body, result)
        return result
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        log.warning("Set ANTHROPIC_API_KEY in the environment to use Claude.")
        return None
    encoded = json.dumps(body).encode()
    for attempt in range(1, CLAUDE_MAX_ATTEMPTS + 1):
        req = urllib.request.Request(
            CLAUDE_API_URL,
            data=encoded,
            method="POST",
            headers={
                "x-api-key": api_key,
                "anthropic-version": CLAUDE_API_VERSION,
                "content-type": "application/json",
            },
        )
        try:
            result = json.loads(_urlopen_hard_timeout(req, timeout))
            _record_api_usage(body, result)
            return result
        except urllib.error.HTTPError as e:
            transient = e.code in (429, 500, 502, 503, 504, 529)
            try:
                detail = e.read().decode(errors="replace")[:1000]
            except Exception:
                detail = "(could not read response body)"
            log.warning("Claude request failed (attempt %d): HTTP %d: %s", attempt, e.code, detail)
            if e.code == 400 and "ttl" in detail.lower() and _has_cache_ttl(body):
                # The 1h cache TTL was rejected (unsupported on this account/API version):
                # drop to the plain 5-minute breakpoint for the rest of this run and retry now,
                # rather than failing every command over an optimization.
                global _cache_ttl_1h_rejected
                _cache_ttl_1h_rejected = True
                log.warning("Anthropic rejected the 1h cache TTL; falling back to 5-minute caching.")
                encoded = json.dumps(_strip_cache_ttl(body)).encode()
                continue
            if not transient or attempt == CLAUDE_MAX_ATTEMPTS:
                return None
            time.sleep(CLAUDE_RETRY_DELAY_S)
        except Exception as e:
            log.warning("Claude request failed (attempt %d): %s", attempt, e)
            if attempt == CLAUDE_MAX_ATTEMPTS:
                return None
            time.sleep(CLAUDE_RETRY_DELAY_S)
    return None


def _claude_text(data: dict) -> str:
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    return " ".join(p for p in parts if p).strip()


# --- speech shaping: the dashboard always shows the full reply; what Piper actually speaks ---
# --- out loud (voice/typed-hotkey only — phone and dashboard replies are read, not heard) ---
# --- gets shortened first, so a long tool-result dump doesn't turn into a rambling monologue. ---
SPEECH_SUMMARY_MIN_CHARS = 220  # below this, speaking the reply verbatim is already short
SPEECH_SUMMARY_TIMEOUT_S = 12

# Matches a Windows path (C:\...) or an absolute Unix-style path (/a/b/c) with at least two
# path segments. A lookbehind for ":" only stops this from matching the "//" directly after
# "https:" — it does nothing about the path segment *later* in a URL (https://example.com/a/b
# still has a bare "/a/b" with no ":" right before it) — so _collapse_paths_for_speech masks
# whole URLs out first and this regex never sees their insides at all.
_SPEECH_PATH_RE = re.compile(
    r'[A-Za-z]:[\\/](?:[^\s\\/:*?"<>|]+[\\/])+[^\s\\/:*?"<>|]*'
    r'|/(?:[^\s/]+/)+[^\s/]*'
)
_SPEECH_URL_RE = re.compile(r"https?://\S+", re.I)


def _humanize_path_for_speech(path_text: str) -> str:
    parts = [p for p in re.split(r"[\\/]+", path_text) if p]
    if parts and re.fullmatch(r"[A-Za-z]:", parts[0]):
        parts = parts[1:]
    if not parts:
        return "a folder"
    last = parts[-1]
    # A trailing name with a dot that isn't just a leading-dot dotfile reads as a file — say the
    # folder it's in, not the path leading to it; a bare directory name speaks for itself.
    if "." in last.lstrip(".") and not last.startswith("."):
        folder = parts[-2] if len(parts) >= 2 else last
        return f"the {folder} folder"
    return f"the {last} folder"


def _collapse_paths_for_speech(text: str) -> str:
    """Replaces any full file path in `text` with just its containing folder's name — Jarvis
    should say "saved it in the Research folder", never read a full path with every slash.
    URLs are masked out first and restored untouched afterward, so a link never gets mistaken
    for a filesystem path (its own "/segments" would otherwise match just as well)."""
    text = text or ""
    urls: list[str] = []

    def _stash_url(m: re.Match) -> str:
        urls.append(m.group(0))
        return f"\x00URL{len(urls) - 1}\x00"

    masked = _SPEECH_URL_RE.sub(_stash_url, text)
    collapsed = _SPEECH_PATH_RE.sub(lambda m: _humanize_path_for_speech(m.group(0)), masked)
    for i, url in enumerate(urls):
        collapsed = collapsed.replace(f"\x00URL{i}\x00", url)
    return collapsed


def _summarize_for_speech(text: str) -> str:
    """Shortens a reply for Piper to speak — the dashboard still shows `text` in full via
    action_audit/dashboard_sessions, this only affects what comes out of the speakers. Skipped
    (no Claude call, zero extra cost) for anything already short. Falls back to the original
    text on any failure — a summarization hiccup must never mean Jarvis goes silent."""
    text = text or ""
    if len(text) < SPEECH_SUMMARY_MIN_CHARS:
        return text
    # Same long reply -> same summary: skip the extra Claude call. Persisted in SQLite so it
    # survives restarts (JARVIS_SUMMARY_CACHE=0 disables).
    summary_key = None
    if cache.enabled("summary"):
        summary_key = cache.stable_hash(CLAUDE_MODEL, text[:4000])
        cached_summary = _speech_summary_kv().get(summary_key, SPEECH_SUMMARY_CACHE_MAX_AGE_S)
        cache.record("summary", cached_summary is not None)
        if cached_summary:
            return cached_summary
    body = {
        "model": CLAUDE_MODEL,
        "max_tokens": 120,
        "system": (
            "Rewrite the following assistant reply as one short, natural sentence (two at "
            "most) meant to be spoken aloud by a voice assistant. Keep the key facts and any "
            "direct answer; drop filler and repetition. Never read out a full file path — "
            "refer to a file or folder by name only, not its full location."
        ),
        "messages": [{"role": "user", "content": text[:4000]}],
    }
    data = _claude_request(body, timeout=SPEECH_SUMMARY_TIMEOUT_S)
    if data is None:
        return text
    summary = _claude_text(data).strip()
    if summary and summary_key:
        _speech_summary_kv().put(summary_key, summary)
    return summary or text


SPEECH_SUMMARY_CACHE_MAX_AGE_S = 7 * 24 * 3600
_speech_summary_kv_obj: cache.SqliteKV | None = None


def _speech_summary_kv() -> cache.SqliteKV:
    # Lazy: _memory_db_connect/_memory_db_lock are defined further down this module.
    global _speech_summary_kv_obj
    if _speech_summary_kv_obj is None:
        _speech_summary_kv_obj = cache.SqliteKV(
            "speech_summary_cache", _memory_db_connect, _memory_db_lock
        )
    return _speech_summary_kv_obj


# --- persistent memory: SQLite-backed chat history + user profile facts --------------
# Long-term storage across restarts, replacing the old RAM-only conversation_history list.
_memory_db_lock = threading.Lock()


def _memory_db_path() -> Path:
    override = (os.environ.get("JARVIS_MEMORY_DB_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent / "jarvis_memory.db"


def _create_memory_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS memory_turns ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "role TEXT NOT NULL, "
        "content TEXT NOT NULL, "
        "timestamp TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS user_profile ("
        "key TEXT PRIMARY KEY, "
        "value TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS action_audit ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "timestamp TEXT NOT NULL, "
        "transcript TEXT NOT NULL, "
        "tool_name TEXT NOT NULL, "
        "tool_input TEXT NOT NULL, "
        "result TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS memory_facts ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "category TEXT NOT NULL, "
        "key TEXT, "
        "content TEXT NOT NULL, "
        "created_at TEXT NOT NULL, "
        "superseded_at TEXT, "
        "superseded_by INTEGER)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS scheduled_skill_runs ("
        "skill_name TEXT PRIMARY KEY, "
        "last_run_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS reminders ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "text TEXT NOT NULL, "
        "due_at TEXT NOT NULL, "
        "repeat_every_minutes REAL, "
        "urgent INTEGER NOT NULL DEFAULT 0, "
        "created_at TEXT NOT NULL, "
        "delivered_at TEXT, "
        "cancelled_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS background_tasks ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "kind TEXT NOT NULL, "
        "task TEXT NOT NULL, "
        "target TEXT, "
        "status TEXT NOT NULL DEFAULT 'running', "
        "started_at TEXT NOT NULL, "
        "finished_at TEXT, "
        "result_summary TEXT)"
    )
    conn.execute(
        # One row per step of a background_tasks row with kind='plan' (see set_plan/_run_plan).
        # depends_on is a JSON list of step_index values that must be 'done' before this step
        # starts — kept as a plain column rather than a join table since a plan's step count is
        # small and the dependency set never needs its own query.
        "CREATE TABLE IF NOT EXISTS plan_steps ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "task_id INTEGER NOT NULL, "
        "step_index INTEGER NOT NULL, "
        "description TEXT NOT NULL, "
        "depends_on TEXT NOT NULL DEFAULT '[]', "
        "status TEXT NOT NULL DEFAULT 'pending', "
        "created_at TEXT NOT NULL, "
        "started_at TEXT, "
        "finished_at TEXT, "
        "result_summary TEXT)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS projects ("
        "name TEXT PRIMARY KEY, "
        "status TEXT NOT NULL, "
        "next_step TEXT, "
        "created_at TEXT NOT NULL, "
        "updated_at TEXT NOT NULL)"
    )


def _quarantine_corrupt_memory_db(db_path: Path) -> None:
    """Renames a corrupted memory DB aside (never deletes) so a fresh one can take its place.
    Corruption here is a real, observed failure mode — forcibly killing jarvis.py mid-write
    (e.g. taskkill /F, or a backgrounding harness killing the process) can corrupt SQLite's
    file — and without this, every future call would keep hitting the exact same
    'database disk image is malformed' error forever, silently killing every voice command."""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.corrupted-{ts}.bak")
    try:
        db_path.rename(backup_path)
        log.warning(
            "Memory DB at %s was corrupted; backed up to %s and starting fresh. "
            "Conversation history/facts before this point may be unrecoverable.",
            db_path,
            backup_path,
        )
    except OSError as e:
        log.warning("Memory DB at %s is corrupted and could not be backed up: %s", db_path, e)


def _memory_db_connect() -> sqlite3.Connection:
    db_path = _memory_db_path()
    conn = sqlite3.connect(db_path, timeout=10)
    _apply_memory_db_pragmas(conn)
    try:
        _create_memory_tables(conn)
    except sqlite3.DatabaseError:
        conn.close()
        _quarantine_corrupt_memory_db(db_path)
        conn = sqlite3.connect(db_path, timeout=10)  # fresh file, since the old one was just moved aside
        _apply_memory_db_pragmas(conn)
        _create_memory_tables(conn)
    return conn


def _apply_memory_db_pragmas(conn: sqlite3.Connection) -> None:
    """WAL mode lets readers proceed while a writer is mid-transaction instead of the default
    rollback-journal's whole-file exclusive lock — observed live: many jarvis_*.py modules each
    open their own connection to this same file, and a startup burst (session recovery, the
    scheduler's first tick, filewatcher, dashboard session pruning) can collide under the
    default mode. journal_mode is persisted in the file itself, so this only has real work to
    do the first time any connection ever sets it; busy_timeout (10s, above the 5s default) is
    a per-connection setting and always applied. Never fatal — a WAL-unsupported filesystem
    (rare, e.g. some network shares) just keeps the default mode."""
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
    except sqlite3.DatabaseError as e:
        log.debug("Could not set WAL/busy_timeout pragmas: %s", e)


def _history_snapshot() -> list[dict]:
    """Last CONVERSATION_HISTORY_MAX_TURNS messages from memory_turns, oldest first."""
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            rows = conn.execute(
                "SELECT role, content FROM memory_turns ORDER BY id DESC LIMIT ?",
                (CONVERSATION_HISTORY_MAX_TURNS,),
            ).fetchall()
        finally:
            conn.close()
    rows.reverse()
    return [{"role": role, "content": content} for role, content in rows]


def _append_history(user_text: str, assistant_text: str) -> None:
    """Permanently records a turn in memory_turns. The table is never trimmed — it's the
    long-term history; _history_snapshot() separately limits how much of it is sent to
    Claude per request."""
    if not user_text or not assistant_text:
        return  # keep strict user/assistant alternation; drop incomplete turns
    now = datetime.now().isoformat(timespec="seconds")
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            conn.execute(
                "INSERT INTO memory_turns (role, content, timestamp) VALUES (?, ?, ?)",
                ("user", user_text, now),
            )
            conn.execute(
                "INSERT INTO memory_turns (role, content, timestamp) VALUES (?, ?, ?)",
                ("assistant", assistant_text, now),
            )
            conn.commit()
        finally:
            conn.close()


def get_user_profile_context() -> str:
    """Formats all stored user_profile facts for embedding in the system prompt. Empty
    string if none are set — the table starts empty; populate it with set_user_profile_fact()."""
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            rows = conn.execute("SELECT key, value FROM user_profile ORDER BY key").fetchall()
        finally:
            conn.close()
    if not rows:
        return ""
    facts = "\n".join(f"- {key}: {value}" for key, value in rows)
    return f"\n\nKnown facts about the user, persisted across sessions:\n{facts}"


def set_user_profile_fact(key: str, value: str) -> None:
    """Permanently stores (or updates) one user-profile fact, e.g. set_user_profile_fact(
    "name", "Ayo"). Not wired to a voice action — populate it directly for now."""
    k = (key or "").strip()
    v = (value or "").strip()
    if not k or not v:
        return
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            conn.execute(
                "INSERT INTO user_profile (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (k, v),
            )
            conn.commit()
        finally:
            conn.close()


MAX_ACTIVE_FACTS_IN_PROMPT = 40


def remember_fact(category: str, content: str, key: str | None = None) -> str:
    """Stores a durable fact about the user. When `key` is given and an earlier active fact
    shares the same category+key, that earlier fact is marked superseded (not deleted) —
    so history of *why* something changed stays queryable via recall_facts, instead of being
    silently overwritten like the old flat user_profile table."""
    category = category if category in MEMORY_FACT_CATEGORIES else "fact"
    content = (content or "").strip()
    if not content:
        return "No content given."
    key = (key or "").strip() or None
    now = datetime.now().isoformat(timespec="seconds")
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            prior_ids: list[int] = []
            if key:
                prior_ids = [
                    row[0]
                    for row in conn.execute(
                        "SELECT id FROM memory_facts "
                        "WHERE category = ? AND key = ? AND superseded_at IS NULL",
                        (category, key),
                    ).fetchall()
                ]
            cur = conn.execute(
                "INSERT INTO memory_facts (category, key, content, created_at) VALUES (?, ?, ?, ?)",
                (category, key, content, now),
            )
            new_id = cur.lastrowid
            if prior_ids:
                conn.executemany(
                    "UPDATE memory_facts SET superseded_at = ?, superseded_by = ? WHERE id = ?",
                    [(now, new_id, pid) for pid in prior_ids],
                )
            conn.commit()
        finally:
            conn.close()
    if prior_ids:
        return f"Remembered: {content} (superseded {len(prior_ids)} earlier fact(s) under key {key!r})."
    return f"Remembered: {content}"


def recall_facts(query: str = "", include_superseded: bool = False, limit: int = 10) -> str:
    """Keyword search over remembered facts — not semantic search, just SQL LIKE, which is
    plenty for a personal fact store of this size. Used both by the recall_facts tool and
    available for future callers that need more than the auto-injected active-facts summary."""
    q = (query or "").strip()
    clauses: list[str] = []
    params: list = []
    if not include_superseded:
        clauses.append("superseded_at IS NULL")
    if q:
        clauses.append("(content LIKE ? OR key LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like])
    sql = "SELECT category, key, content, created_at, superseded_at FROM memory_facts"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(max(1, min(int(limit or 10), 50)))
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
    if not rows:
        return "No matching facts found."
    lines = []
    for cat, key, content, created_at, superseded_at in rows:
        tag = f"[{cat}]" + (f" ({key})" if key else "")
        status = " [superseded]" if superseded_at else ""
        lines.append(f"{tag} {created_at}: {content}{status}")
    return "\n".join(lines)


def get_active_facts_context() -> str:
    """Formats currently-active remembered facts for the system prompt — this is what makes
    remember_fact calls actually persist across restarts and future conversations, the same
    way get_user_profile_context() already does for manually-set profile facts."""
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            rows = conn.execute(
                "SELECT category, content FROM memory_facts "
                "WHERE superseded_at IS NULL ORDER BY created_at DESC LIMIT ?",
                (MAX_ACTIVE_FACTS_IN_PROMPT,),
            ).fetchall()
        finally:
            conn.close()
    if not rows:
        return ""
    lines = [f"- [{category}] {content}" for category, content in rows]
    return "\n\nThings you've learned and remembered about the user over time:\n" + "\n".join(lines)


# --- FEATURE 1: session context — "what is the user doing right now", persisted across restarts ---
# --- so the proactive systems below (scheduled skills, health-check suggestions) can decide ---
# --- whether to interrupt immediately or hold a notification until the user is actually free, ---
# --- instead of always talking over whatever the user is doing the moment something fires. ---
SESSION_STATE_PATH = Path(__file__).resolve().parent / "session_state.json"
RECENT_TASK_WINDOW_HOURS = 4.0
# The user's stated preference: an afternoon focus block where casual interruptions should be
# held back rather than spoken immediately.
PREFERRED_WORK_HOUR_START = 13  # 1pm
PREFERRED_WORK_HOUR_END = 17  # 5pm
# How recently the keyboard/mouse must have been touched (system-wide, via GetLastInputInfo) to
# count the user as "actively working" — a much more reliable signal than polling the foreground
# window, since someone can sit reading a window without touching anything.
ACTIVE_IDLE_THRESHOLD_S = 60.0

_session_context_lock = threading.Lock()


def _default_session_context() -> dict:
    return {
        "last_active_window": None,
        "last_active_project": None,
        "preferences": {
            "preferred_work_hour_start": PREFERRED_WORK_HOUR_START,
            "preferred_work_hour_end": PREFERRED_WORK_HOUR_END,
        },
        "recent_tasks": [],  # [{"task": str, "at": iso timestamp}, ...], pruned to the last
        # RECENT_TASK_WINDOW_HOURS on every refresh
        "scheduled_task_running": False,
        "pending_notifications": [],  # [{"text": str, "queued_at": iso timestamp}, ...]
        "updated_at": None,
    }


def _load_session_context() -> dict:
    """Reads session_state.json if present; a missing or corrupt file just means a fresh
    default context, not a crash — this is best-effort context, not durable memory."""
    if not SESSION_STATE_PATH.is_file():
        return _default_session_context()
    try:
        data = json.loads(SESSION_STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("session_state.json did not contain a JSON object")
    except (OSError, ValueError) as e:
        log.warning("Could not read session state %s (starting fresh): %s", SESSION_STATE_PATH, e)
        return _default_session_context()
    merged = _default_session_context()
    merged.update(data)
    merged["preferences"] = {**merged["preferences"], **(data.get("preferences") or {})}
    return merged


# Loaded once at import time and mutated in place under _session_context_lock thereafter.
_session_context: dict = _load_session_context()


def _save_session_context_locked() -> None:
    """Caller must already hold _session_context_lock. Writes to a temp file and replaces
    atomically, so a crash mid-write can never leave a half-written, unparseable
    session_state.json behind for the next load."""
    tmp = SESSION_STATE_PATH.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(_session_context, indent=2), encoding="utf-8")
        tmp.replace(SESSION_STATE_PATH)
    except OSError as e:
        log.warning("Could not save session state: %s", e)


def _safe_parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _get_idle_seconds() -> float | None:
    """Seconds since the last system-wide keyboard/mouse input, via GetLastInputInfo. None on
    non-Windows platforms or if the API call fails — callers treat "unknown" as "can't confirm
    the user is busy," so notifications don't end up silently stuck forever on a platform we
    can't measure idle time on."""
    if sys.platform != "win32":
        return None
    import ctypes

    class _LastInputInfo(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    lii = _LastInputInfo()
    lii.cbSize = ctypes.sizeof(_LastInputInfo)
    try:
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return None
        idle_ms = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return max(idle_ms, 0) / 1000.0
    except Exception as e:
        log.warning("Could not read system idle time: %s", e)
        return None


def _get_active_window_title() -> str | None:
    """Best-effort title of the current foreground window (Windows only) — used purely to
    infer what project/document the user was last looking at, not as the busy/idle signal."""
    if sys.platform != "win32":
        return None
    import ctypes

    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return None
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value.strip() or None
    except Exception as e:
        log.warning("Could not read active window title: %s", e)
        return None


def _guess_project_from_window_title(title: str | None) -> str | None:
    """Best-effort project/document name from a window title such as "jarvis.py -
    jarvis-main2-enhanced - Cursor" — just the first " - "-separated segment."""
    if not title:
        return None
    return title.split(" - ", 1)[0].strip() or None


def user_is_actively_working() -> bool:
    """True if the user touched the keyboard/mouse within ACTIVE_IDLE_THRESHOLD_S seconds.
    Unknown (non-Windows, or the API call failed) is treated as "not actively working," so a
    platform we can't measure never ends up queuing every notification forever."""
    idle = _get_idle_seconds()
    return idle is not None and idle < ACTIVE_IDLE_THRESHOLD_S


def _is_preferred_work_hours(now: datetime | None = None) -> bool:
    """Whether `now` (default: current time) falls in the user's stated afternoon focus
    window (default 1pm-5pm, overridable via session_state.json's "preferences")."""
    now = now or datetime.now()
    with _session_context_lock:
        prefs = _session_context.get("preferences") or {}
        start = int(prefs.get("preferred_work_hour_start", PREFERRED_WORK_HOUR_START))
        end = int(prefs.get("preferred_work_hour_end", PREFERRED_WORK_HOUR_END))
    return start <= now.hour < end


def refresh_session_context() -> None:
    """Updates last-active-window/project and prunes recent_tasks older than
    RECENT_TASK_WINDOW_HOURS, then persists. Cheap enough (two Windows API calls, no
    subprocess) to call right before every interrupt decision instead of needing a dedicated
    polling thread."""
    title = _get_active_window_title()
    now = datetime.now()
    cutoff = now - timedelta(hours=RECENT_TASK_WINDOW_HOURS)
    with _session_context_lock:
        if title:
            _session_context["last_active_window"] = title
            _session_context["last_active_project"] = _guess_project_from_window_title(title)
        _session_context["recent_tasks"] = [
            t
            for t in _session_context.get("recent_tasks", [])
            if (parsed := _safe_parse_iso(t.get("at"))) is not None and parsed >= cutoff
        ]
        _session_context["updated_at"] = now.isoformat(timespec="seconds")
        _save_session_context_locked()


def record_recent_task(task: str) -> None:
    """Appends a task (a voice/text command, or a scheduled skill run) to the rolling
    last-4-hours window — the "what has the user been doing lately" half of session context."""
    task = (task or "").strip()
    if not task:
        return
    with _session_context_lock:
        _session_context.setdefault("recent_tasks", []).append(
            {"task": task, "at": datetime.now().isoformat(timespec="seconds")}
        )
        _save_session_context_locked()


def _set_scheduled_task_running(running: bool) -> None:
    with _session_context_lock:
        _session_context["scheduled_task_running"] = running
        _save_session_context_locked()


def _speak_shaped(text: str) -> None:
    """speak_text with the same speech shaping a command reply gets: long text is summarized
    into a sentence or two and full file paths collapse to a folder name. Proactive messages
    (background-task completions, scheduled skills, reminders) used to call speak_text directly,
    so a finished coding task was read out word for word, exactly as it appears in the
    dashboard. Only the *spoken* copy is shortened — the dashboard, toast and phone push all
    keep the full text — and short messages (under SPEECH_SUMMARY_MIN_CHARS) cost no extra call."""
    speak_text(_collapse_paths_for_speech(_summarize_for_speech(text)))


def queue_or_deliver_notification(
    text: str, urgent: bool = False, force_phone: bool = False
) -> None:
    """The interrupt gate every proactive message (scheduled skills, health-check suggestions)
    goes through, instead of calling speak_text directly: speaks immediately unless the user
    looks actively busy (touched the keyboard/mouse in the last ACTIVE_IDLE_THRESHOLD_S
    seconds) during their stated afternoon focus hours, in which case it's queued and only
    delivered the next time they actually talk to Jarvis (see flush_pending_notifications,
    called from handle_text_command) — never interrupting mid-focus-block for something
    non-urgent, but never getting lost either."""
    text = (text or "").strip()
    if not text:
        return
    _notify_phone(text, force=force_phone)
    refresh_session_context()
    if urgent and sleep_mode.is_active():
        # Still spoken live below, but also remembered so the wake-up recap can report it first.
        with _session_context_lock:
            _session_context.setdefault("pending_notifications", []).append(
                {
                    "text": text,
                    "queued_at": datetime.now().isoformat(timespec="seconds"),
                    "during_sleep": True,
                    "important": True,
                }
            )
            _save_session_context_locked()
    if sleep_mode.should_suppress(urgent):
        with _session_context_lock:
            _session_context.setdefault("pending_notifications", []).append(
                {
                    "text": text,
                    "queued_at": datetime.now().isoformat(timespec="seconds"),
                    "during_sleep": True,
                }
            )
            _save_session_context_locked()
        log.info("Queued non-urgent notification (Sleep Mode active): %r", text)
        return
    if urgent or not (user_is_actively_working() and _is_preferred_work_hours()):
        _speak_shaped(text)
        return
    with _session_context_lock:
        _session_context.setdefault("pending_notifications", []).append(
            {"text": text, "queued_at": datetime.now().isoformat(timespec="seconds")}
        )
        _save_session_context_locked()
    log.info("Queued non-urgent notification (user busy in preferred work hours): %r", text)


def flush_pending_notifications() -> None:
    """Speaks any notifications queued while the user was busy. Called at the start of every
    real command (handle_text_command) — the user talking to Jarvis is itself proof they're
    available to listen right now."""
    with _session_context_lock:
        everything = _session_context.get("pending_notifications") or []
        # Items queued by Sleep Mode wait for the wake-up digest (_sleep_wake_digest) instead of
        # being read out one by one — even if the user talks to Jarvis while still in Sleep Mode.
        pending = [i for i in everything if not i.get("during_sleep")]
        _session_context["pending_notifications"] = [i for i in everything if i.get("during_sleep")]
        _save_session_context_locked()
    for item in pending:
        try:
            _speak_shaped(item.get("text", ""))
        except Exception as e:
            log.warning("Could not speak queued notification: %s", e)


USER_NAME = (os.environ.get("JARVIS_USER_NAME") or "Hero").strip() or "Hero"


def _sleep_wake_digest(started_at: str, ended_at: str) -> None:
    """Registered with jarvis_sleep_mode: when Sleep Mode ends, replaces the old flood of queued
    notifications with one spoken recap ("Hero, while you were asleep, ..."). Draining the queue
    is synchronous (so a command issued right after waking can't replay the items); summarizing
    and speaking happen on a thread. Urgent messages were already spoken live and aren't here."""
    with _session_context_lock:
        everything = _session_context.get("pending_notifications") or []
        items = [i for i in everything if i.get("during_sleep")]
        _session_context["pending_notifications"] = [
            i for i in everything if not i.get("during_sleep")
        ]
        _save_session_context_locked()

    def _run() -> None:
        try:
            digest = _build_sleep_digest(items)
            sleep_mode.save_digest(started_at, digest)
            speak_text(_collapse_paths_for_speech(digest))
        except Exception as e:
            log.warning("Could not deliver Sleep Mode wake digest: %s", e)

    threading.Thread(target=_run, daemon=True, name="sleep-wake-digest").start()


def _build_sleep_digest(items: list[dict]) -> str:
    """Two-part recap: what mattered first (urgent things that came through live while asleep),
    then "On a lighter note," the held-back reminders/notifications."""
    prefix = f"{USER_NAME}, while you were asleep, "
    if not items:
        return f"{USER_NAME}, nothing came in while you were asleep."
    important = [i for i in items if i.get("important")]
    lighter = [i for i in items if not i.get("important")]

    def _fmt(group: list[dict]) -> str:
        return "\n".join(f"-{(i.get('text') or '').strip()[:300]}" for i in group[:30]) or "(none)"

    body = {
        "model": CLAUDE_MODEL,
        "max_tokens": 300,
        "system": (
            f"You are a voice assistant. The user ({USER_NAME}) just woke up. You get two lists "
            "of what happened while they slept: IMPORTANT (urgent things that came through) and "
            "LIGHTER (reminders and notifications held back). Write a short spoken recap of at "
            f"most four sentences that starts exactly with: \"{prefix}\". First report the "
            "IMPORTANT items; if that list is empty say nothing important happened. Then, only "
            "if LIGHTER is not empty, continue with the exact words \"On a lighter note,\" and "
            "summarize those. Group related items, keep key facts, drop filler. Never read out "
            "a full file path or URL. Plain spoken prose: no lists, no markdown."
        ),
        "messages": [
            {"role": "user", "content": f"IMPORTANT:\n{_fmt(important)}\n\nLIGHTER:\n{_fmt(lighter)}"}
        ],
    }
    data = _claude_request(body, timeout=SPEECH_SUMMARY_TIMEOUT_S)
    text = _claude_text(data).strip() if data is not None else ""
    # Trust the model's wording only if it kept the requested structure.
    if text and (not lighter or "on a lighter note" in text.lower()):
        return text
    # Fallback: never go silent or drop items just because summarizing failed or ignored the format.
    def _heads(group: list[dict]) -> str:
        more = f", and {len(group) - 3} more" if len(group) > 3 else ""
        return "; ".join((i.get("text") or "").strip()[:80] for i in group[:3]) + more

    out = prefix + (
        f"this happened: {_heads(important)}." if important else "nothing important happened."
    )
    if lighter:
        out += f" On a lighter note, {_heads(lighter)}."
    return out


sleep_mode.set_wake_digest_handler(_sleep_wake_digest)


# --- Windows toast notifications: a real, visible Action Center banner for reminders, so one ---
# --- isn't missed just because nobody was in earshot of Piper's spoken announcement. Shells out ---
# --- to a static PowerShell script (WinRT's ToastNotificationManager) rather than a new pip ---
# --- dependency. Uses PowerShell's own registered AppUserModelID rather than an arbitrary ---
# --- string, since a toast fired under an unregistered AUMID can silently fail or raise ---
# --- "element not found" on stricter Windows builds. Title/message are passed as PowerShell ---
# --- -File arguments (never interpolated into the script text) so reminder text can never be ---
# --- read as PowerShell code, only as a string value. ---
_TOAST_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
_TOAST_PS_SCRIPT = r"""
param(
    [string]$Title = "Jarvis",
    [string]$Message = "",
    [string]$AppId
)
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null

$safeTitle = [System.Security.SecurityElement]::Escape($Title)
$safeMessage = [System.Security.SecurityElement]::Escape($Message)
$xmlText = "<toast><visual><binding template=`"ToastGeneric`"><text>$safeTitle</text><text>$safeMessage</text></binding></visual></toast>"

$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($xmlText)
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($AppId).Show($toast)
"""


def _toast_script_path() -> Path:
    base = Path(__file__).resolve().parent / ".cache"
    base.mkdir(parents=True, exist_ok=True)
    path = base / "show_toast.ps1"
    if not path.is_file():
        path.write_text(_TOAST_PS_SCRIPT, encoding="utf-8")
    return path


def send_windows_toast(title: str, message: str) -> bool:
    """Shows a native Windows Action Center toast. Best-effort — logs and returns False on
    any failure (non-Windows, PowerShell missing, WinRT unavailable) rather than raising,
    since a missed toast should never take down reminder delivery."""
    if sys.platform != "win32":
        return False
    message = (message or "").strip()
    if not message:
        return False
    title = (title or "Jarvis").strip() or "Jarvis"
    try:
        script_path = _toast_script_path()
        proc = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(script_path),
                "-Title", title, "-Message", message, "-AppId", _TOAST_APP_ID,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if proc.returncode != 0:
            log.warning("Windows toast script failed: %s", (proc.stderr or proc.stdout or "").strip()[:300])
            return False
        return True
    except Exception as e:
        log.warning("Could not show Windows toast: %s", e)
        return False


# --- FEATURE: phone integration — ntfy.sh and/or a Telegram bot, either or both, configured ---
# --- entirely via NTFY_TOPIC/TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID in .env (silently inert if ---
# --- unset). Outbound: _notify_phone fires from queue_or_deliver_notification so every ---
# --- existing proactive message (reminders, background-task completions, health suggestions) ---
# --- reaches the phone with no extra call sites to maintain. Inbound: two long-polling ---
# --- listener threads (started from main(), see _ntfy_listen_loop/_telegram_listen_loop) feed ---
# --- whatever you send from your phone into handle_text_command — the exact same command ---
# --- pipeline the text-hotkey box uses, full tool access included. ---
_NTFY_PRIORITIES = {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5}


def _ntfy_publish(message: str, title: str = "Jarvis", priority: str = "default") -> bool:
    """Best-effort push via ntfy's JSON publish endpoint (not the raw-body+headers form —
    headers can't safely carry arbitrary unicode, JSON can). Never raises.

    priority must be an int 1-5 on this endpoint — the string names ntfy's docs show (e.g.
    "default") are only accepted on the header-based publish form, not this JSON one; sending
    a string here gets a flat "request body must be valid JSON" 400 with no field named,
    confirmed against the live API."""
    if not NTFY_TOPIC:
        return False
    message = (message or "").strip()
    if not message:
        return False
    payload = json.dumps(
        {
            "topic": NTFY_TOPIC,
            "message": message[:4000],
            "title": title,
            "priority": _NTFY_PRIORITIES.get(priority, 3),
        }
    ).encode("utf-8")
    try:
        req = urllib.request.Request(
            f"{NTFY_SERVER}/",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except Exception as e:
        log.warning("ntfy publish failed: %s", e)
        return False


def _telegram_send(message: str) -> bool:
    """Best-effort push via Telegram's sendMessage. Never raises."""
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return False
    message = (message or "").strip()
    if not message:
        return False
    payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": message[:4000]}).encode("utf-8")
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        return True
    except Exception as e:
        log.warning("Telegram send failed: %s", e)
        return False


def _notify_phone(text: str, title: str = "Jarvis", force: bool = False) -> None:
    """Pushes to every configured phone channel — but only when
    JARVIS_PHONE_PROACTIVE_NOTIFICATIONS is explicitly enabled (off by default; see that
    constant's comment). Called from queue_or_deliver_notification for every *proactive*
    message (scheduled skills, health suggestions, reminders, background task completions);
    never affects a direct reply to something the user typed from ntfy/Telegram, which goes
    through reply_sink in _ntfy_listen_loop/_telegram_listen_loop instead."""
    # force=True bypasses the off-by-default toggle for the one case the user asked for it:
    # the result of a change to Jarvis's own code (so a phone-started self-change reports back
    # to the phone). Every other proactive message still respects the toggle.
    if not (JARVIS_PHONE_PROACTIVE_NOTIFICATIONS or force):
        return
    if NTFY_TOPIC:
        _ntfy_publish(text, title=title)
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        _telegram_send(text)


def _ntfy_listen_loop() -> None:
    """Long-polls a *separate* {NTFY_TOPIC}-cmd topic (never the outbound one, so Jarvis's own
    pushes can't loop back in as commands) and runs each message through handle_text_command.
    ntfy sends periodic keepalive events on this stream specifically so a stalled connection is
    detectable; any error (including a keepalive-free timeout) just reconnects after a short
    pause rather than giving up."""
    topic = f"{NTFY_TOPIC}-cmd"
    url = f"{NTFY_SERVER}/{topic}/json?poll=false"
    log.info("ntfy command listener watching topic %r", topic)
    while True:
        try:
            with urllib.request.urlopen(urllib.request.Request(url), timeout=90) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get("event") != "message":
                        continue
                    text = (event.get("message") or "").strip()
                    if text:
                        log.info("ntfy command received: %r", text)
                        # Reply goes to the main (notification) topic, not -cmd, so it lands
                        # wherever you're already subscribed to see it, not the inbound-only one.
                        handle_text_command(
                            text, reply_sink=lambda r: _ntfy_publish(r, title="Jarvis"), source="phone"
                        )
        except Exception as e:
            log.warning("ntfy listener error (reconnecting): %s", e)
            time.sleep(5)


def _telegram_listen_loop() -> None:
    """Long-polls Telegram's getUpdates and runs each message through handle_text_command —
    but only from TELEGRAM_CHAT_ID; a message from any other chat is logged and dropped, since
    a bot's username is discoverable and knowing it shouldn't be enough to run commands on this
    machine the way knowing an ntfy topic name is (see _ntfy_listen_loop's caveat)."""
    offset = 0
    base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    log.info("Telegram command listener running for chat %s", TELEGRAM_CHAT_ID)
    while True:
        try:
            url = f"{base}/getUpdates?timeout=50&offset={offset}"
            with urllib.request.urlopen(url, timeout=60) as resp:
                data = json.loads(resp.read())
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message") or {}
                chat_id = str((msg.get("chat") or {}).get("id") or "")
                text = (msg.get("text") or "").strip()
                if chat_id != TELEGRAM_CHAT_ID:
                    if chat_id:
                        log.warning("Ignoring Telegram message from unauthorized chat %s", chat_id)
                    continue
                if text:
                    log.info("Telegram command received: %r", text)
                    handle_text_command(text, reply_sink=lambda r: _telegram_send(r), source="phone")
        except Exception as e:
            log.warning("Telegram listener error (reconnecting): %s", e)
            time.sleep(5)


# --- FEATURE: reminders — one-off or repeating "tell me about this later", distinct from a ---
# --- skill (which re-derives what to do from instructions every run). A reminder is just a ---
# --- fixed piece of text and a due time, persisted in the same memory DB as everything else, ---
# --- checked once per scheduler tick, and delivered through the same interrupt-aware ---
# --- queue_or_deliver_notification gate scheduled skills already use. ---
def _parse_due_at(due_at: str) -> datetime | None:
    """Accepts the ISO-ish formats a model is likely to produce ("2026-09-16 15:00",
    "2026-09-16T15:00", with or without seconds) rather than requiring one exact format."""
    s = (due_at or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def create_reminder(
    text: str,
    due_at: str = "",
    due_in_minutes: float | None = None,
    repeat_every_minutes: float | None = None,
    urgent: bool = False,
) -> str:
    """Schedules a reminder for an absolute time (due_at) or a delay from now
    (due_in_minutes) — exactly one should be given; due_in_minutes wins if both are. An
    optional repeat_every_minutes re-arms the same reminder after each delivery instead of
    firing once."""
    text = (text or "").strip()
    if not text:
        return "No reminder text given."
    when: datetime | None = None
    if due_in_minutes is not None:
        try:
            when = datetime.now() + timedelta(minutes=float(due_in_minutes))
        except (TypeError, ValueError):
            when = None
    if when is None and due_at:
        when = _parse_due_at(due_at)
    if when is None:
        return "Couldn't understand when to remind you — give a specific time or a number of minutes from now."
    repeat: float | None = None
    if repeat_every_minutes:
        try:
            repeat = float(repeat_every_minutes)
        except (TypeError, ValueError):
            repeat = None
    now_iso = datetime.now().isoformat(timespec="seconds")
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            conn.execute(
                "INSERT INTO reminders (text, due_at, repeat_every_minutes, urgent, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (text, when.isoformat(timespec="seconds"), repeat, int(bool(urgent)), now_iso),
            )
            conn.commit()
        finally:
            conn.close()
    when_desc = (
        when.strftime("%A %H:%M") if when.date() != datetime.now().date() else when.strftime("%H:%M")
    )
    return f"Reminder set for {when_desc}: {text}."


def list_reminders(include_delivered: bool = False) -> str:
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            sql = (
                "SELECT id, text, due_at, repeat_every_minutes, delivered_at FROM reminders "
                "WHERE cancelled_at IS NULL"
            )
            if not include_delivered:
                sql += " AND delivered_at IS NULL"
            sql += " ORDER BY due_at"
            rows = conn.execute(sql).fetchall()
        finally:
            conn.close()
    if not rows:
        return "No upcoming reminders."
    lines = []
    for rid, text, due_at, repeat, delivered_at in rows:
        tag = " [delivered]" if delivered_at else ""
        repeat_note = f", repeating every {repeat:.0f} min" if repeat else ""
        lines.append(f"#{rid} at {due_at}{repeat_note}: {text}{tag}")
    return "\n".join(lines)


def cancel_reminder(reminder_id: int) -> str:
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            cur = conn.execute(
                "UPDATE reminders SET cancelled_at = ? WHERE id = ? AND cancelled_at IS NULL",
                (datetime.now().isoformat(timespec="seconds"), reminder_id),
            )
            conn.commit()
        finally:
            conn.close()
    return f"Cancelled reminder #{reminder_id}." if cur.rowcount else f"No active reminder #{reminder_id}."


def _check_due_reminders(now: datetime) -> None:
    """Called once per scheduler tick. A due, non-repeating reminder is marked delivered; a
    repeating one is re-armed for now + its interval instead, so it keeps firing."""
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            rows = conn.execute(
                "SELECT id, text, repeat_every_minutes, urgent FROM reminders "
                "WHERE cancelled_at IS NULL AND delivered_at IS NULL AND due_at <= ?",
                (now.isoformat(timespec="seconds"),),
            ).fetchall()
        finally:
            conn.close()
    for rid, text, repeat, urgent in rows:
        # The toast fires immediately and unconditionally — unlike the spoken announcement,
        # a silent visual banner doesn't talk over anything, so it doesn't need to wait out
        # queue_or_deliver_notification's busy-gate to avoid being missed.
        send_windows_toast("Jarvis Reminder", text)
        queue_or_deliver_notification(f"Reminder: {text}", urgent=bool(urgent))
        record_recent_task(f"reminder delivered: {text}")
        with _memory_db_lock:
            conn = _memory_db_connect()
            try:
                if repeat:
                    next_due = (now + timedelta(minutes=float(repeat))).isoformat(timespec="seconds")
                    conn.execute("UPDATE reminders SET due_at = ? WHERE id = ?", (next_due, rid))
                else:
                    conn.execute(
                        "UPDATE reminders SET delivered_at = ? WHERE id = ?",
                        (now.isoformat(timespec="seconds"), rid),
                    )
                conn.commit()
            finally:
                conn.close()


# --- FEATURE: project tracking + quick recall — "what am I working on and what's next", so a ---
# --- new session (or a context switch back after hours away) can pick up where things were ---
# --- left off instead of the user re-explaining. A project is deliberately just a name/status/ ---
# --- next-step triple, the same lightweight shape as the memory_facts table above, updated ---
# --- via update_project_status and surfaced both in every system prompt and via quick_recall. ---
def update_project_status(name: str, status: str, next_step: str = "") -> str:
    name = (name or "").strip()
    status = (status or "").strip()
    if not name or not status:
        return "Need both a project name and a status."
    next_step = (next_step or "").strip() or None
    now = datetime.now().isoformat(timespec="seconds")
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            conn.execute(
                "INSERT INTO projects (name, status, next_step, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET status = excluded.status, "
                "next_step = COALESCE(excluded.next_step, projects.next_step), "
                "updated_at = excluded.updated_at",
                (name, status, next_step, now, now),
            )
            conn.commit()
        finally:
            conn.close()
    suffix = f" — next: {next_step}" if next_step else ""
    return f"Updated project {name!r}: {status}{suffix}"


def _fetch_projects(limit: int = 20) -> list[tuple]:
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            return conn.execute(
                "SELECT name, status, next_step, updated_at FROM projects "
                "ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            conn.close()


def get_projects_context() -> str:
    """Formats tracked projects for the system prompt — same always-in-context pattern as
    get_active_facts_context(), so Claude knows what's ongoing without a tool call."""
    rows = _fetch_projects()
    if not rows:
        return ""
    lines = [
        f"- {name}: {status}" + (f" (next: {next_step})" if next_step else "")
        for name, status, next_step, _ in rows
    ]
    return "\n\nOngoing projects you're tracking for the user:\n" + "\n".join(lines)


def quick_recall() -> str:
    """Synthesizes 'where we left off': tracked projects and their next steps, recently run
    commands/skills, the last window/project the user was active in, and any upcoming
    reminders — everything needed to jump back into work without the user re-explaining
    context. Backing tool for the quick_recall action ("what were we doing", "catch me up")."""
    parts: list[str] = []

    projects = _fetch_projects(limit=10)
    if projects:
        proj_lines = [
            f"{name} ({status}" + (f", next step: {next_step})" if next_step else ")")
            for name, status, next_step, _ in projects
        ]
        parts.append("Ongoing projects: " + "; ".join(proj_lines) + ".")

    with _session_context_lock:
        recent_tasks = list(_session_context.get("recent_tasks", []))
        last_project = _session_context.get("last_active_project")
    if recent_tasks:
        recent_desc = "; ".join(t["task"] for t in recent_tasks[-5:])
        parts.append(f"Recently: {recent_desc}.")
    if last_project:
        parts.append(f"You were last active in {last_project}.")

    upcoming = list_reminders(include_delivered=False)
    if upcoming and upcoming != "No upcoming reminders.":
        parts.append("Upcoming reminders: " + upcoming.replace("\n", "; "))

    running_tasks = list_background_tasks(include_finished=False)
    if running_tasks and running_tasks != "No background tasks running.":
        parts.append("Background tasks in progress: " + running_tasks.replace("\n", "; "))

    if not parts:
        return "Nothing tracked yet — no ongoing projects, recent tasks, or reminders."
    return " ".join(parts)


# --- skills: user- or Claude-authored procedures dropped into skills/*.json, loaded fresh on ---
# --- every system prompt build (not cached) so a new file takes effect with no restart and no ---
# --- code edit — the "skill library" layer, distinct from the built-in tools above. ---
SKILLS_DIR_NAME = "skills"
MAX_SKILLS_CONTEXT_CHARS = 16000


def _skills_dir() -> Path:
    override = (os.environ.get("JARVIS_SKILLS_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent / SKILLS_DIR_NAME


_skills_cache: tuple[tuple, list[dict]] | None = None


def _load_skills() -> list[dict]:
    """Skills from disk, re-parsed only when a skills/*.json file was added, removed or
    modified (checked via a cheap name+mtime signature) instead of on every agent turn."""
    global _skills_cache
    directory = _skills_dir()
    try:
        sig = tuple((p.name, p.stat().st_mtime_ns) for p in sorted(directory.glob("*.json")))
    except OSError:
        return _read_skills_from_disk()
    cached = _skills_cache
    if cached is not None and cached[0] == sig:
        return [dict(s) for s in cached[1]]
    skills = _read_skills_from_disk()
    _skills_cache = (sig, skills)
    return [dict(s) for s in skills]


def _read_skills_from_disk() -> list[dict]:
    """Reads every *.json skill file from the skills directory. A malformed file is skipped
    with a warning instead of breaking the others or the whole system prompt."""
    directory = _skills_dir()
    if not directory.is_dir():
        return []
    skills = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            name = str(data.get("name") or path.stem).strip()
            description = str(data.get("description") or "").strip()
            instructions = str(data.get("instructions") or "").strip()
            schedule = data.get("schedule")
            if name and instructions:
                skill: dict = {"name": name, "description": description, "instructions": instructions}
                if isinstance(schedule, dict):
                    skill["schedule"] = schedule
                skills.append(skill)
            else:
                log.warning("Skipping skill file %s: missing name/instructions.", path)
        except Exception as e:
            log.warning("Skipping malformed skill file %s: %s", path, e)
    return skills


def get_skills_context() -> str:
    skills = _load_skills()
    if not skills:
        return ""
    parts: list[str] = []
    total = 0
    for s in skills:
        block = f"### Skill: {s['name']}\n{s['description']}\n{s['instructions']}".strip()
        if total + len(block) > MAX_SKILLS_CONTEXT_CHARS:
            log.warning("Skill context budget (%d chars) exceeded; dropping remaining skills.", MAX_SKILLS_CONTEXT_CHARS)
            break
        parts.append(block)
        total += len(block)
    if not parts:
        return ""
    return (
        "\n\nUser-defined skills — pre-written procedures to follow when they match what's "
        "being asked, carrying out the steps with your normal tools:\n\n" + "\n\n".join(parts)
    )


def save_skill(
    name: str, description: str, instructions: str, schedule: dict | None = None
) -> str:
    """Writes name/description/instructions (and optional schedule) as a new
    skills/<name>.json file, or overwrites an existing skill of the same name. Called via the
    save_skill tool, not directly by voice."""
    slug = re.sub(r"[^a-z0-9_\-]", "_", (name or "").strip().lower()).strip("_")
    if not slug:
        return "No valid skill name given."
    instructions = (instructions or "").strip()
    if not instructions:
        return "No instructions given."
    directory = _skills_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{slug}.json"
        payload = {
            "name": slug,
            "description": (description or "").strip(),
            "instructions": instructions,
        }
        if isinstance(schedule, dict) and (schedule.get("daily_at") or schedule.get("every_minutes")):
            payload["schedule"] = schedule
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as e:
        return f"Failed to save skill: {e}"
    if payload.get("schedule"):
        return f"Saved skill {slug!r} to {path} (scheduled: {payload['schedule']})."
    return f"Saved skill {slug!r} to {path}."


# --- proactive scheduler: a skill can carry an optional "schedule" so Jarvis acts on its own ---
# --- initiative (a morning briefing, a periodic check) instead of only ever reacting to voice. ---
# --- Runs independently of clap/PTT activation, in its own background thread. ---
SCHEDULER_TICK_S = 60


def _get_last_skill_run(skill_name: str) -> datetime | None:
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            row = conn.execute(
                "SELECT last_run_at FROM scheduled_skill_runs WHERE skill_name = ?",
                (skill_name,),
            ).fetchone()
        finally:
            conn.close()
    if not row:
        return None
    try:
        return datetime.fromisoformat(row[0])
    except ValueError:
        return None


def _set_last_skill_run(skill_name: str, when: datetime) -> None:
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            conn.execute(
                "INSERT INTO scheduled_skill_runs (skill_name, last_run_at) VALUES (?, ?) "
                "ON CONFLICT(skill_name) DO UPDATE SET last_run_at = excluded.last_run_at",
                (skill_name, when.isoformat(timespec="seconds")),
            )
            conn.commit()
        finally:
            conn.close()


def _skill_is_due(skill: dict, now: datetime) -> bool:
    schedule = skill.get("schedule")
    if not isinstance(schedule, dict):
        return False
    last_run = _get_last_skill_run(skill["name"])

    daily_at = schedule.get("daily_at")
    if daily_at:
        try:
            hour, minute = (int(p) for p in str(daily_at).split(":", 1))
            target_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except (TypeError, ValueError):
            return False
        if now < target_today:
            return False
        return last_run is None or last_run.date() != now.date()

    every_minutes = schedule.get("every_minutes")
    if every_minutes:
        try:
            interval = timedelta(minutes=float(every_minutes))
        except (TypeError, ValueError):
            return False
        return last_run is None or (now - last_run) >= interval

    return False


def _run_scheduled_skill(skill: dict) -> None:
    log.info("Running scheduled skill %r.", skill["name"])
    # Session context: mark a scheduled task as in-flight so anything checking
    # "is the user free right now" (e.g. queue_or_deliver_notification) can see it, and
    # record it as a recent task for the session_context history.
    _set_scheduled_task_running(True)
    record_recent_task(f"scheduled skill: {skill['name']}")
    synthetic_transcript = (
        f"(This is a scheduled, proactive run of your \"{skill['name']}\" skill — the user "
        f"didn't just ask for this out loud, act on the schedule instead.) {skill['instructions']}"
    )
    try:
        reply = run_agent_loop(synthetic_transcript)
        if reply:
            # Route through the interrupt gate instead of speaking immediately — a scheduled
            # skill is exactly the kind of unprompted interrupt session context exists for.
            queue_or_deliver_notification(reply)
    except Exception as e:
        log.warning("Scheduled skill %r failed: %s", skill["name"], e)
    finally:
        _set_scheduled_task_running(False)
        _set_last_skill_run(skill["name"], datetime.now())


def _run_queued_task(description: str, instructions: str) -> None:
    """task_scheduler's run_callback — same shape as _run_scheduled_skill above, so a queued
    task with instructions is executed exactly like a scheduled skill (full tool access,
    reply delivered through the interrupt gate)."""
    log.info("Running queued task %r.", description)
    _set_scheduled_task_running(True)
    record_recent_task(f"queued task: {description}")
    synthetic_transcript = (
        f"(This is a scheduled, proactive run of a queued task: \"{description}\" — the user "
        f"didn't just ask for this out loud, act on it now.) {instructions}"
    )
    try:
        reply = run_agent_loop(synthetic_transcript)
        if reply:
            queue_or_deliver_notification(reply)
    finally:
        _set_scheduled_task_running(False)


def _scheduler_loop() -> None:
    while True:
        try:
            now = datetime.now()
            for skill in _load_skills():
                if _skill_is_due(skill, now):
                    _run_scheduled_skill(skill)
            _check_due_reminders(now)
            _check_background_tasks(now)
            _retry_failed_mcp_servers(now)
            task_scheduler.tick(now, _run_queued_task, queue_or_deliver_notification)
            sleep_mode.check_wakeup(now, _run_system_action, speak_text)
        except Exception as e:
            log.warning("Scheduler tick failed: %s", e)
        time.sleep(SCHEDULER_TICK_S)


def _start_scheduler() -> None:
    _recover_interrupted_background_tasks()
    threading.Thread(target=_scheduler_loop, daemon=True, name="skill-scheduler").start()


# --- MCP client: connects to servers listed in mcp_servers.json (one-time, lazy) and merges ---
# --- their tools into the agent loop's tool list, namespaced "mcp_<server>_<tool>" — the same ---
# --- protocol/tool-discovery mechanism Claude Code itself uses for integrations, so adding one ---
# --- (Gmail, Calendar, Slack, ...) is a config entry, not a code change. A server that fails to ---
# --- connect (missing credentials, package not found, offline) is skipped with a warning; the ---
# --- built-in tools and the rest of Jarvis keep working regardless. ---
MCP_TOOL_CALL_TIMEOUT_S = 60
MCP_STARTUP_TIMEOUT_S = 60
MCP_RETRY_INTERVAL_S = 120  # a server that failed to connect gets one more try every 2 minutes

_mcp_lock = threading.Lock()
_mcp_loop: asyncio.AbstractEventLoop | None = None
_mcp_started = False
# Set once the *first* connection attempt (success or failure) finishes — every caller of
# ensure_mcp_started() waits on this instead of racing past a bare "already started" flag, so a
# scheduled skill's first run can't slip through before MCP tools actually exist. See
# ensure_mcp_started's docstring for the race this fixes.
_mcp_ready_event = threading.Event()
_mcp_handles: dict[str, "_McpServerHandle"] = {}  # server name -> _McpServerHandle
_mcp_tool_index: dict[str, tuple[str, str]] = {}  # exposed tool name -> (server name, real tool name)
_mcp_tool_schemas: list[dict] = []
_mcp_failed_servers: dict[str, dict] = {}  # server name -> {"cfg": {...}, "last_attempt": datetime}


def _mcp_servers_config_path() -> Path:
    override = (os.environ.get("JARVIS_MCP_CONFIG_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent / "mcp_servers.json"


def _load_mcp_server_configs() -> dict:
    """{"server_name": {"command": "...", "args": [...], "env": {...}}, ...} — see
    mcp_servers.example.json. Missing or malformed config just means no MCP servers; not fatal."""
    path = _mcp_servers_config_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        log.warning("Could not parse MCP server config %s: %s", path, e)
        return {}


def _ensure_mcp_loop() -> asyncio.AbstractEventLoop:
    """MCP's client SDK is asyncio-only; Jarvis is thread-based throughout. This runs one
    dedicated event loop forever in a background thread, and every MCP call is dispatched into
    it via asyncio.run_coroutine_threadsafe — the standard bridge pattern for using an async-only
    library from synchronous code."""
    global _mcp_loop
    with _mcp_lock:
        if _mcp_loop is None:
            _mcp_loop = asyncio.new_event_loop()

            def _run_forever() -> None:
                asyncio.set_event_loop(_mcp_loop)
                _mcp_loop.run_forever()

            threading.Thread(target=_run_forever, daemon=True, name="mcp-loop").start()
        return _mcp_loop


def _mcp_run_coro(coro, timeout: float):
    loop = _ensure_mcp_loop()
    return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=timeout)


class _McpServerHandle:
    """One MCP server's connection state. Tool-call requests are dispatched into `queue`
    rather than calling `session.call_tool` directly from other coroutines — see
    _mcp_server_supervisor for why."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue()
        self.ready = asyncio.Event()
        self.tools: list = []
        self.error: str | None = None


async def _mcp_server_supervisor(cfg: dict, handle: "_McpServerHandle") -> None:
    """Owns one MCP server's stdio connection for the entire process lifetime. The
    ClientSession/stdio transport must stay open in the *same* still-running coroutine/task
    that created it — anyio's cancel scopes are bound to the task that entered them, so once
    that task returns, the connection is torn down even if Python objects referencing the
    session are kept alive elsewhere. Tool calls are therefore dispatched into this
    long-running task via a queue instead of re-entering the session from a separate coroutine."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    try:
        params = StdioServerParameters(
            command=str(cfg.get("command") or ""),
            args=[str(a) for a in (cfg.get("args") or [])],
            env={**os.environ, **{k: str(v) for k, v in (cfg.get("env") or {}).items()}},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                handle.tools = list(tools_result.tools)
                handle.ready.set()
                while True:
                    tool_name, arguments, future = await handle.queue.get()
                    try:
                        result = await session.call_tool(tool_name, arguments)
                        if not future.done():
                            future.set_result(result)
                    except Exception as e:
                        if not future.done():
                            future.set_exception(e)
    except Exception as e:
        handle.error = str(e)
        handle.ready.set()  # unblock the connect-time waiter even on failure


async def _mcp_connect_one(server_name: str, cfg: dict) -> bool:
    """Connects a single MCP server and registers its tools on success. Returns whether it
    connected — the caller (initial connect or a later retry) decides what to do with that."""
    command = str(cfg.get("command") or "").strip()
    if not command:
        log.warning("MCP server %r has no \"command\"; skipping.", server_name)
        return False
    handle = _McpServerHandle()
    _mcp_handles[server_name] = handle
    asyncio.get_running_loop().create_task(_mcp_server_supervisor(cfg, handle))
    try:
        await asyncio.wait_for(handle.ready.wait(), timeout=MCP_STARTUP_TIMEOUT_S)
    except asyncio.TimeoutError:
        log.warning("MCP server %r timed out connecting.", server_name)
        return False
    if handle.error:
        log.warning("Failed to connect MCP server %r: %s", server_name, handle.error)
        return False
    for tool in handle.tools:
        exposed_name = f"mcp_{server_name}_{tool.name}"[:128]
        _mcp_tool_index[exposed_name] = (server_name, tool.name)
        _mcp_tool_schemas.append(
            {
                "name": exposed_name,
                "description": (tool.description or f"{server_name}.{tool.name}")[:1024],
                "input_schema": tool.input_schema or {"type": "object", "properties": {}},
            }
        )
    log.info("Connected MCP server %r (%d tools).", server_name, len(handle.tools))
    return True


async def _mcp_connect_all_async(configs: dict) -> None:
    for server_name, cfg in configs.items():
        # Top-level non-server keys (e.g. a "_comment" string in the example config) or any
        # other malformed entry must not abort every server after it in iteration order.
        try:
            if server_name.startswith("_") or not isinstance(cfg, dict):
                continue
            ok = await _mcp_connect_one(server_name, cfg)
            with _mcp_lock:
                if ok:
                    _mcp_failed_servers.pop(server_name, None)
                else:
                    _mcp_failed_servers[server_name] = {"cfg": cfg, "last_attempt": datetime.now()}
        except Exception as e:
            log.warning("Skipping malformed MCP server config %r: %s", server_name, e)


def _preload_mcp_async() -> None:
    """Connects to configured MCP servers in the background at startup — without this, the
    *first* voice command after launch blocks on ensure_mcp_started() inside run_agent_loop,
    and a slow/hung server (observed live: Gmail's stdio server timing out) means a real
    command sits in dead silence for the full MCP_STARTUP_TIMEOUT_S before Jarvis does
    anything at all, indistinguishable from a hang. Preloading here means that wait, if any,
    happens before the user ever speaks."""
    threading.Thread(target=ensure_mcp_started, daemon=True, name="mcp-preload").start()


def ensure_mcp_started() -> None:
    """Connects every configured MCP server exactly once, lazily, on first use.

    Every caller — including one racing in on another thread while the first connection
    attempt is still in flight — blocks here until that attempt actually finishes, success or
    failure. This matters because _preload_mcp_async() starts connecting in the background at
    the same moment _start_scheduler() starts the scheduler thread, and a skill due to run on
    the very first tick (observed live: gmail_watch) calls this too, from run_agent_loop's
    get_mcp_tool_schemas(). Without blocking here, that second caller would see "already
    started" and return immediately with the tool list still empty — the skill runs believing
    Gmail has no tools, not that it just isn't ready yet.

    If the `mcp` package isn't installed or no servers are configured, this is a silent no-op;
    MCP is additive, never required."""
    global _mcp_started
    with _mcp_lock:
        if _mcp_started:
            already_starting = True
        else:
            _mcp_started = True
            already_starting = False
    if already_starting:
        _mcp_ready_event.wait(timeout=MCP_STARTUP_TIMEOUT_S * 4)
        return
    try:
        configs = _load_mcp_server_configs()
        if not configs:
            return
        try:
            import mcp  # noqa: F401  (import check only — real usage is inside _mcp_connect_all_async)
        except ImportError:
            log.warning(
                "mcp_servers.json is configured but the `mcp` package isn't installed "
                "(pip install mcp)."
            )
            return
        try:
            # _mcp_connect_all_async connects servers one at a time, each with its own internal
            # MCP_STARTUP_TIMEOUT_S budget — this outer bound must cover the whole sequence, not
            # a single server's worth, or a later server (observed live: a first-time `npx`
            # package download) gets truncated before it's even reached once earlier servers eat
            # into the budget.
            _mcp_run_coro(
                _mcp_connect_all_async(configs), timeout=MCP_STARTUP_TIMEOUT_S * len(configs)
            )
        except Exception as e:
            log.warning("MCP startup failed: %s", e)
    finally:
        _mcp_ready_event.set()


def _retry_failed_mcp_servers(now: datetime) -> None:
    """Called from the scheduler tick (every SCHEDULER_TICK_S). A server that failed its
    initial connection attempt (npx cold-start, transient network hiccup, server briefly down)
    gets retried every MCP_RETRY_INTERVAL_S instead of being given up on for the rest of the
    process's life — the only way it came back before this was restarting Jarvis entirely."""
    if not _mcp_started:
        return  # nothing has attempted a first connection yet; nothing to retry
    with _mcp_lock:
        due = {
            name: info["cfg"]
            for name, info in _mcp_failed_servers.items()
            if (now - info["last_attempt"]) >= timedelta(seconds=MCP_RETRY_INTERVAL_S)
        }
        for name in due:
            _mcp_failed_servers[name]["last_attempt"] = now
    if not due:
        return
    log.info("Retrying %d previously-failed MCP server(s): %s", len(due), ", ".join(due))
    try:
        _mcp_run_coro(_mcp_connect_all_async(due), timeout=MCP_STARTUP_TIMEOUT_S * len(due))
    except Exception as e:
        log.warning("MCP retry failed: %s", e)


def _dashboard_get_services_status() -> list[dict]:
    """Read-only snapshot for the dashboard's Services dropdown: every configured MCP server
    plus the two phone channels, each with a status and a short human detail string."""
    with _mcp_lock:
        failed = {k: dict(v) for k, v in _mcp_failed_servers.items()}
        handles_snapshot = dict(_mcp_handles)
        started = _mcp_started
    configs = _load_mcp_server_configs()
    services: list[dict] = []
    for name, cfg in configs.items():
        if name.startswith("_") or not isinstance(cfg, dict):
            continue
        handle = handles_snapshot.get(name)
        if name in failed:
            last = failed[name]["last_attempt"]
            services.append({
                "name": name,
                "status": "failed",
                "detail": (
                    f"last tried {last.strftime('%H:%M:%S')}, "
                    f"retrying every {MCP_RETRY_INTERVAL_S // 60} min"
                ),
            })
        elif handle is not None and handle.error is None:
            services.append({
                "name": name, "status": "connected", "detail": f"{len(handle.tools)} tool(s)",
            })
        elif not started:
            services.append({"name": name, "status": "pending", "detail": "not started yet"})
        else:
            services.append({"name": name, "status": "connecting", "detail": "starting…"})
    services.append({
        "name": "phone — ntfy",
        "status": "connected" if NTFY_TOPIC else "not configured",
        "detail": "listening" if NTFY_TOPIC else "set NTFY_TOPIC in .env to enable",
    })
    services.append({
        "name": "phone — telegram",
        "status": "connected" if (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID) else "not configured",
        "detail": (
            "listening" if (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
            else "set TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID in .env to enable"
        ),
    })
    return services


def _dashboard_get_sleep() -> dict:
    return sleep_mode.stats_summary()


def _dashboard_get_usage() -> dict:
    return billing.local_summary(_memory_db_connect, _memory_db_lock)


def _dashboard_get_daily_items() -> list[dict]:
    """Read-only snapshot for the dashboard's own Daily section (recurring skills + recurring
    reminders) — deliberately separate from the Tasks panel, which is one-off/in-flight work,
    not standing routines."""
    items: list[dict] = []
    for skill in _load_skills():
        schedule = skill.get("schedule")
        if not isinstance(schedule, dict):
            continue
        if schedule.get("daily_at"):
            schedule_desc = f"daily at {schedule['daily_at']}"
        elif schedule.get("every_minutes"):
            schedule_desc = f"every {schedule['every_minutes']:g} minutes"
        else:
            schedule_desc = "recurring"
        last_run = _get_last_skill_run(skill["name"])
        items.append({
            "kind": "skill",
            "name": skill["name"],
            "description": skill.get("description") or "",
            "schedule": schedule_desc,
            "last_run_at": last_run.isoformat(timespec="seconds") if last_run else None,
        })

    try:
        with _memory_db_lock:
            conn = _memory_db_connect()
            try:
                rows = conn.execute(
                    "SELECT text, due_at, repeat_every_minutes FROM reminders "
                    "WHERE repeat_every_minutes IS NOT NULL AND cancelled_at IS NULL "
                    "ORDER BY due_at"
                ).fetchall()
            finally:
                conn.close()
    except sqlite3.DatabaseError as e:
        log.debug("Could not read recurring reminders for dashboard Daily section: %s", e)
        rows = []
    for text, due_at, repeat_every_minutes in rows:
        items.append({
            "kind": "reminder",
            "name": text,
            "description": "",
            "schedule": f"every {repeat_every_minutes:g} min",
            "last_run_at": None,
            "next_due": due_at,
        })
    return items


def get_mcp_tool_schemas() -> list[dict]:
    ensure_mcp_started()
    return list(_mcp_tool_schemas)


async def _mcp_call_tool_async(server_name: str, tool_name: str, arguments: dict):
    handle = _mcp_handles.get(server_name)
    if handle is None or handle.error:
        raise RuntimeError(f"MCP server {server_name!r} is not connected.")
    future = asyncio.get_running_loop().create_future()
    await handle.queue.put((tool_name, arguments, future))
    return await future


def execute_mcp_tool(exposed_name: str, tool_input: dict) -> str:
    entry = _mcp_tool_index.get(exposed_name)
    if not entry:
        return f"Unknown MCP tool: {exposed_name!r}"
    server_name, real_name = entry
    try:
        result = _mcp_run_coro(
            _mcp_call_tool_async(server_name, real_name, tool_input or {}),
            timeout=MCP_TOOL_CALL_TIMEOUT_S,
        )
    except Exception as e:
        return f"MCP tool call failed: {e}"
    parts = [b.text for b in (getattr(result, "content", None) or []) if getattr(b, "text", None)]
    text = " ".join(parts) or "(no output)"
    return f"MCP tool reported an error: {text}" if getattr(result, "is_error", False) else text


def _tts_engine_context_line() -> str:
    """Ground truth for "what voice/TTS engine are you using?" — without this, Claude has no
    way to actually know (the engine choice happens in speak_text(), entirely after Claude's
    reply is generated, invisible to it) and was observed live guessing "Piper" regardless of
    which engine was actually active, since Piper is the more famous open-source project."""
    if FISH_AUDIO_API_KEY:
        return (
            "\n\nYour spoken replies are synthesized by Fish Audio (cloud TTS), with the "
            "local Piper engine as an automatic fallback only if Fish Audio fails — say Fish "
            "Audio if asked what voice engine you use, not Piper, unless you know a fallback "
            "just happened."
        )
    return "\n\nYour spoken replies are synthesized by the local Piper TTS engine."


def build_system_prompt(tone_line: str = "") -> str:
    # Computed fresh on every call (every agent-loop iteration) rather than relying on a
    # get-current-time tool call staying in the 6-message history window — observed live:
    # a calendar event created several turns after the last such tool call landed on the
    # wrong year and the wrong day for "Friday", because that fact had already scrolled out
    # of history by then. Putting it directly in the system prompt makes it structurally
    # impossible to lose track of, for calendar events or anything else date-relative.
    now = datetime.now()
    current_time_line = f"\n\nRight now it is {now.strftime('%A, %Y-%m-%d %H:%M')} (local time)."
    return (
        AGENT_SYSTEM_PROMPT
        + current_time_line
        + _tts_engine_context_line()
        + tone_line
        + get_user_profile_context()
        + get_active_facts_context()
        + get_projects_context()
        + get_skills_context()
        + workflow.get_context_summary()
        + sleep_mode.system_prompt_context_line()
    )


def _own_code_context_line() -> str:
    """Ground truth for "where is your code / edit yourself". Without it Claude has no way to
    know and was observed searching the disk, finding an unrelated project whose folder name
    contained "jarvis" (OpenJarvis), and telling the user that was its source. The path is
    computed from this file's own location, so it stays right if the folder moves; it is
    constant per install, so it lives in the cached stable system block."""
    here = Path(__file__).resolve().parent
    return (
        f"\n\nYour own source code is in {here} (entry point jarvis.py, a git repository). You "
        "do not need to search the disk for it — that is the answer to \"where is your code\". "
        "Other folders with \"jarvis\" in the name, such as OpenJarvis, are different projects, "
        "not you. To change your own code, use change_jarvis_code (never guess a repo path)."
    )


def build_system_blocks(tone_line: str = "") -> list[dict]:
    """build_system_prompt split for Anthropic prompt caching: a stable block carrying the
    (large) fixed prompt, marked cacheable, then a small volatile block (clock minute, tone,
    sleep-mode line) after it. Cache matching is an exact-prefix match, so anything that
    changes per call must sit *after* the breakpoint or it invalidates the whole prefix."""
    stable = (
        AGENT_SYSTEM_PROMPT
        + _own_code_context_line()
        + _tts_engine_context_line()
        + get_user_profile_context()
        + get_active_facts_context()
        + get_projects_context()
        + get_skills_context()
    )
    now = datetime.now()
    volatile = (
        f"Right now it is {now.strftime('%A, %Y-%m-%d %H:%M')} (local time)."
        + tone_line
        + workflow.get_context_summary()
        + sleep_mode.system_prompt_context_line()
    )
    stable_block: dict = {"type": "text", "text": stable}
    if cache.enabled("prompt"):
        stable_block["cache_control"] = _long_cache_control()
    return [stable_block, {"type": "text", "text": volatile}]


def _long_cache_control() -> dict:
    """Breakpoint for the big, rarely-changing prefix (tools + stable system block). Defaults
    to the 1-hour TTL (JARVIS_PROMPT_CACHE_TTL=5m for the plain 5-minute one): a 1h write costs
    2x instead of 1.25x, but survives idle gaps between voice commands so far fewer commands
    pay a write at all. Anthropic requires longer-TTL breakpoints to come *before* shorter ones
    — tools, then system, then the (5-minute) message breakpoint — which is the order here."""
    if _cache_ttl_1h_rejected or (os.environ.get("JARVIS_PROMPT_CACHE_TTL") or "1h").strip().lower() == "5m":
        return {"type": "ephemeral"}
    return {"type": "ephemeral", "ttl": "1h"}


def _cached_tools(tools: list[dict]) -> list[dict]:
    """Copy of tools with a cache breakpoint on the last one (caches the whole tool list)."""
    if not tools or not cache.enabled("prompt"):
        return tools
    return tools[:-1] + [{**tools[-1], "cache_control": _long_cache_control()}]


def _messages_with_cache_breakpoint(messages: list[dict]) -> list[dict]:
    """Copy of messages with a cache breakpoint on the final content block, so each agent-loop
    round trip reads everything before it (history + earlier tool results) from cache instead
    of re-billing it. Never mutates the caller's list — the marker must not accumulate."""
    if not messages or not cache.enabled("prompt"):
        return messages
    last = messages[-1]
    content = last.get("content")
    if isinstance(content, str):
        blocks = [{"type": "text", "text": content}]
    elif isinstance(content, list) and content and isinstance(content[-1], dict):
        blocks = list(content)
    else:
        return messages
    blocks[-1] = {**blocks[-1], "cache_control": {"type": "ephemeral"}}
    return messages[:-1] + [{**last, "content": blocks}]


_last_claude_agent_call = 0.0


def _log_cache_usage(data: dict, label: str) -> None:
    global _last_claude_agent_call
    _last_claude_agent_call = time.time()
    usage = data.get("usage") or {}
    read = usage.get("cache_read_input_tokens", 0) or 0
    log.info(
        "%s tokens: %s uncached in, %s cache-read, %s cache-write, %s out",
        label,
        usage.get("input_tokens", 0),
        read,
        usage.get("cache_creation_input_tokens", 0),
        usage.get("output_tokens", 0),
    )
    if cache.enabled("prompt"):
        cache.record("prompt", hit=read > 0)


def _prompt_cache_warm_request() -> None:
    """One 1-token request carrying exactly the prefix run_agent_loop sends (same tools, same
    stable system block), so the first real command after startup already reads from cache.
    (max_tokens=0 is rejected by the Messages API — 1 is the minimum.) Never raises."""
    try:
        data = _claude_request(
            {
                "model": CLAUDE_MODEL,
                "max_tokens": 1,
                "system": build_system_blocks(),
                "messages": [{"role": "user", "content": "warmup"}],
                "tools": _cached_tools(AGENT_TOOLS + get_mcp_tool_schemas()),
            },
            timeout=30,
        )
        if data is not None:
            _log_cache_usage(data, "prompt-cache warmup")
    except Exception as e:
        log.debug("Prompt-cache warmup failed: %s", e)


def _prompt_cache_keepwarm_loop(interval_s: float) -> None:
    while True:
        time.sleep(interval_s)
        # Only re-warm when the prefix would otherwise expire unused — a real command in the
        # last interval already refreshed it for free.
        if time.time() - _last_claude_agent_call >= interval_s:
            _prompt_cache_warm_request()


def start_prompt_cache_warmup() -> None:
    """Startup pre-warm (background thread; get_mcp_tool_schemas blocks until MCP has
    connected, and the tool list must match what agent calls send or the prefix won't hit).
    Optional periodic keep-warm via JARVIS_PROMPT_CACHE_KEEPWARM_MIN (default 0 = off: with the
    1h TTL every real command refreshes the cache, and a keep-warm read of the ~22k-token prefix
    every few minutes around the clock would cost more than most idle gaps save)."""
    if not (cache.enabled("prompt") and _llm_provider() == "claude" and _llm_configured()):
        return  # Anthropic prompt caching only; Gemini caches implicitly, no pre-warm needed
    threading.Thread(target=_prompt_cache_warm_request, daemon=True).start()
    try:
        minutes = float(os.environ.get("JARVIS_PROMPT_CACHE_KEEPWARM_MIN") or 0)
    except ValueError:
        minutes = 0
    if minutes > 0:
        threading.Thread(
            target=_prompt_cache_keepwarm_loop, args=(minutes * 60,), daemon=True
        ).start()


def _launch_app_notepad() -> None:
    try:
        subprocess.Popen(["notepad.exe"])
    except OSError as e:
        log.warning("Could not open Notepad: %s", e)


def _launch_app_calculator() -> None:
    try:
        subprocess.Popen(["calc.exe"])
    except OSError as e:
        log.warning("Could not open Calculator: %s", e)


def _launch_app_explorer() -> None:
    try:
        subprocess.Popen(["explorer.exe"])
    except OSError as e:
        log.warning("Could not open File Explorer: %s", e)


def _launch_app_chrome() -> None:
    chrome = _chrome_executable()
    if not chrome:
        log.warning("Chrome not found; opening default browser instead.")
        webbrowser.open("about:blank")
        return
    popen_kw: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        subprocess.Popen([chrome], **popen_kw)
    except OSError as e:
        log.warning("Could not open Chrome: %s", e)


def _launch_app_spotify() -> None:
    try:
        if sys.platform == "win32":
            os.startfile("spotify:")
        else:
            webbrowser.open("https://open.spotify.com")
    except OSError as e:
        log.warning("Could not open Spotify (%s); falling back to web.", e)
        _open_uri("https://open.spotify.com")


def _launch_app(name: str) -> None:
    if name == "cursor":
        open_cursor_window()
    elif name == "notepad":
        _launch_app_notepad()
    elif name == "calculator":
        _launch_app_calculator()
    elif name == "explorer":
        _launch_app_explorer()
    elif name == "chrome":
        _launch_app_chrome()
    elif name == "spotify":
        _launch_app_spotify()
    else:
        log.warning("Unknown app: %r", name)


def _system_action_lock() -> None:
    if sys.platform != "win32":
        log.warning("Lock workstation is only implemented on Windows.")
        return
    import ctypes

    ctypes.windll.user32.LockWorkStation()


def _system_action_minimize_all() -> None:
    if sys.platform != "win32":
        log.warning("Minimize-all is only implemented on Windows.")
        return
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW("Shell_TrayWnd", None)
    if not hwnd:
        log.warning("Could not find the taskbar window to minimize all.")
        return
    WM_COMMAND = 0x0111
    MIN_ALL = 419
    user32.SendMessageW(hwnd, WM_COMMAND, MIN_ALL, 0)


def _system_action_minimize_active() -> None:
    if sys.platform != "win32":
        log.warning("Minimize-active is only implemented on Windows.")
        return
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        log.warning("No foreground window to minimize.")
        return
    SW_MINIMIZE = 6
    user32.ShowWindow(hwnd, SW_MINIMIZE)


# Virtual-key codes for hardware volume/media keys — sent via keybd_event, same as a real keypress.
_MEDIA_VK = {
    "volume_up": 0xAF,
    "volume_down": 0xAE,
    "volume_mute": 0xAD,
    "media_play_pause": 0xB3,
    "media_next": 0xB0,
    "media_previous": 0xB1,
    "media_stop": 0xB2,
}


def _send_vk_key(vk: int) -> None:
    if sys.platform != "win32":
        log.warning("Volume/media keys are only implemented on Windows.")
        return
    import ctypes

    user32 = ctypes.windll.user32
    KEYEVENTF_KEYUP = 0x0002
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _run_system_action(name: str) -> None:
    if name == "lock":
        _system_action_lock()
    elif name == "minimize_all":
        _system_action_minimize_all()
    elif name == "minimize_active":
        _system_action_minimize_active()
    elif name in _MEDIA_VK:
        _send_vk_key(_MEDIA_VK[name])
    else:
        log.warning("Unknown system action: %r", name)


# --- screen interaction: click / drag / scroll / window focus -------------------------
def click_at(x: int, y: int, button: str = "left", clicks: int = 1) -> None:
    try:
        import pyautogui
    except ImportError:
        log.warning("Install `pyautogui` (see requirements.txt) to click on screen.")
        return
    pyautogui.FAILSAFE = True
    btn = button if button in ALLOWED_MOUSE_BUTTONS else "left"
    n = 2 if clicks == 2 else 1
    try:
        pyautogui.click(x=x, y=y, clicks=n, button=btn)
    except Exception as e:
        log.warning("Could not click at (%d, %d): %s", x, y, e)


def drag_and_drop(x: int, y: int, end_x: int, end_y: int, button: str = "left") -> None:
    try:
        import pyautogui
    except ImportError:
        log.warning("Install `pyautogui` (see requirements.txt) to drag on screen.")
        return
    pyautogui.FAILSAFE = True
    btn = button if button in ALLOWED_MOUSE_BUTTONS else "left"
    try:
        pyautogui.moveTo(x, y)
        pyautogui.dragTo(end_x, end_y, duration=0.3, button=btn)
    except Exception as e:
        log.warning("Could not drag (%d, %d) -> (%d, %d): %s", x, y, end_x, end_y, e)


def scroll_screen(amount: int, x: int | None = None, y: int | None = None) -> None:
    try:
        import pyautogui
    except ImportError:
        log.warning("Install `pyautogui` (see requirements.txt) to scroll the screen.")
        return
    pyautogui.FAILSAFE = True
    try:
        if x is not None and y is not None:
            pyautogui.scroll(amount, x=x, y=y)
        else:
            pyautogui.scroll(amount)
    except Exception as e:
        log.warning("Could not scroll: %s", e)


def focus_window(title_substring: str) -> bool:
    try:
        import pygetwindow as gw
    except ImportError:
        log.warning("Install `PyGetWindow` (see requirements.txt) to focus windows.")
        return False
    needle = title_substring.strip().lower()
    if not needle:
        return False
    try:
        match = next(
            (w for w in gw.getAllWindows() if w.title and needle in w.title.lower()), None
        )
        if match is None:
            log.warning("No window found matching %r.", title_substring)
            return False
        if match.isMinimized:
            match.restore()
        match.activate()
        return True
    except Exception as e:
        log.warning("Could not focus window %r: %s", title_substring, e)
        return False


# --- WhatsApp messaging (UI automation via WhatsApp Desktop) --------------------------
# Launched via the Windows Start menu search (press Win, type "whatsapp", wait, Enter) rather
# than a direct AppUserModelID — simpler, and works the same way for any app without needing
# to look up an ID.
WHATSAPP_START_MENU_SEARCH_WAIT_S = 3.0
# Proportional (x, y) positions on a MAXIMIZED WhatsApp Desktop window, as a fraction of
# screen size — calibrated on a 1920x1080 display. Retune these if your layout differs
# (different resolution, sidebar width, etc.): the search box, the first search result in
# the chat list, and the message compose box.
WHATSAPP_SEARCH_POS = (0.132, 0.115)
WHATSAPP_FIRST_RESULT_POS = (0.132, 0.206)
WHATSAPP_MESSAGE_BOX_POS = (0.625, 0.965)
WHATSAPP_LAUNCH_WAIT_S = 6.0
WHATSAPP_SEARCH_WAIT_S = 2.5
WHATSAPP_STEP_PAUSE_S = 1.2  # pause between each click/type step, so the UI has time to settle


def _maximize_window_by_title(title_substring: str) -> bool:
    try:
        import pygetwindow as gw
    except ImportError:
        return False
    needle = title_substring.strip().lower()
    try:
        match = next(
            (w for w in gw.getAllWindows() if w.title and needle in w.title.lower()), None
        )
        if match is None:
            return False
        if match.isMinimized:
            match.restore()
        match.maximize()
        match.activate()
        return True
    except Exception as e:
        log.warning("Could not maximize window %r: %s", title_substring, e)
        return False


def _launch_whatsapp_via_start_menu(pyautogui) -> None:
    log.info("Opening Start menu and searching for WhatsApp...")
    pyautogui.press("win")
    time.sleep(WHATSAPP_STEP_PAUSE_S)
    pyautogui.typewrite("whatsapp", interval=0.05)
    log.info("Waiting %.0fs for search results...", WHATSAPP_START_MENU_SEARCH_WAIT_S)
    time.sleep(WHATSAPP_START_MENU_SEARCH_WAIT_S)
    pyautogui.press("enter")


def send_whatsapp_message(contact_name: str, message: str) -> None:
    """Opens WhatsApp Desktop, searches for a contact by name, and sends a message.

    This is fixed-coordinate UI automation (see the WHATSAPP_*_POS constants) with no
    confirmation step and no way to verify the search's top result is actually the intended
    contact — a wrong or stale search result sends the message to the wrong person. There is
    no "type but don't send" option for messaging, unlike type_text elsewhere in this file.
    """
    name = (contact_name or "").strip()
    text = (message or "").strip()
    if not name or not text:
        log.warning("send_whatsapp_message needs both a contact name and a message.")
        return
    try:
        import pyautogui
    except ImportError:
        log.warning("Install `pyautogui` (see requirements.txt) to send WhatsApp messages.")
        return
    pyautogui.FAILSAFE = True

    if not _maximize_window_by_title("WhatsApp"):
        try:
            _launch_whatsapp_via_start_menu(pyautogui)
        except Exception as e:
            log.warning("Could not launch WhatsApp via the Start menu: %s", e)
            return
        log.info("Waiting %.0fs for WhatsApp to open...", WHATSAPP_LAUNCH_WAIT_S)
        time.sleep(WHATSAPP_LAUNCH_WAIT_S)
        if not _maximize_window_by_title("WhatsApp"):
            log.warning("Could not find the WhatsApp window after launching it.")
            return

    w, h = _primary_screen_size()
    try:
        log.info("Clicking search box and typing contact name %r...", name)
        sx, sy = int(w * WHATSAPP_SEARCH_POS[0]), int(h * WHATSAPP_SEARCH_POS[1])
        pyautogui.click(sx, sy)
        time.sleep(WHATSAPP_STEP_PAUSE_S)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.3)
        pyautogui.typewrite(name, interval=0.04)
        log.info("Waiting %.1fs for search results to settle...", WHATSAPP_SEARCH_WAIT_S)
        time.sleep(WHATSAPP_SEARCH_WAIT_S)

        log.info("Clicking the top search result...")
        rx, ry = int(w * WHATSAPP_FIRST_RESULT_POS[0]), int(h * WHATSAPP_FIRST_RESULT_POS[1])
        pyautogui.click(rx, ry)
        time.sleep(WHATSAPP_STEP_PAUSE_S)

        log.info("Clicking the message box and typing the message...")
        mx, my = int(w * WHATSAPP_MESSAGE_BOX_POS[0]), int(h * WHATSAPP_MESSAGE_BOX_POS[1])
        pyautogui.click(mx, my)
        time.sleep(WHATSAPP_STEP_PAUSE_S)
        pyautogui.typewrite(text, interval=0.02)
        time.sleep(WHATSAPP_STEP_PAUSE_S)
        pyautogui.press("enter")
        log.info("Sent WhatsApp message to %r.", name)
    except Exception as e:
        log.warning("Could not send WhatsApp message: %s", e)


def _screenshot_jpeg_b64() -> str | None:
    try:
        from PIL import ImageGrab
    except ImportError:
        log.warning("Install `Pillow` (see requirements.txt) to read the screen.")
        return None
    try:
        img = ImageGrab.grab()
        img.thumbnail((1600, 1600))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=70)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as e:
        log.warning("Could not capture screenshot: %s", e)
        return None


def read_screen(transcript: str) -> tuple[str, str]:
    """Returns (spoken_reply, code_to_type_or_empty).

    The fix-typing half only fires when Claude judges the request explicitly asked for the
    error/bug to be corrected, written, or typed — not on a plain "what does this say"/"explain
    this" ask. That decision happens here (after actually seeing the screenshot), not at the
    routing step, since the routing call never sees the screen.
    """
    if not _llm_configured():
        return "I don't have an Anthropic API key set, so I can't read the screen.", ""
    b64 = _screenshot_jpeg_b64()
    if not b64:
        return "I couldn't capture the screen.", ""
    data = _claude_request(
        {
            "model": CLAUDE_MODEL,
            "max_tokens": 800,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Here is a screenshot of my screen. Briefly (2-4 sentences) "
                                f"answer this: {transcript}\n\n"
                                "If there's a visible compiler error, exception, stack trace, or "
                                "lint error AND the request explicitly asks you to fix, correct, "
                                "write, or type it (not just explain/describe it), work out the "
                                "correction, then add a line saying exactly ---CODE--- followed by "
                                "ONLY the corrected code/line to type, nothing else after it. "
                                "Otherwise omit the ---CODE--- part entirely."
                            ),
                        },
                    ],
                }
            ],
        },
        timeout=60,
    )
    if data is None:
        return "Sorry, I couldn't read the screen just now.", ""
    full = _claude_text(data)
    if not full:
        return "I couldn't make out anything useful on the screen.", ""
    if "---CODE---" in full:
        explanation, code = full.split("---CODE---", 1)
        return explanation.strip(), code.strip()
    return full, ""


def _bytes_to_gb(n: float) -> float:
    return n / (1024**3)


def _bytes_to_mb(n: float) -> float:
    return n / (1024**2)


def get_system_status_report() -> dict:
    """Full structured hardware/performance snapshot. Each section is gathered
    independently — one unsupported metric (e.g. temperature sensors on most Windows
    machines) never blocks the rest of the report; unavailable sections are just None."""
    import psutil

    report: dict = {}

    try:
        per_core = psutil.cpu_percent(interval=0.4, percpu=True)
        overall = sum(per_core) / len(per_core) if per_core else 0.0
        freq = psutil.cpu_freq()
        report["cpu"] = {
            "overall_percent": overall,
            "per_core_percent": per_core,
            "physical_cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
            "frequency_current_mhz": freq.current if freq else None,
            "frequency_max_mhz": freq.max if freq else None,
        }
    except Exception as e:
        log.warning("Could not read CPU metrics: %s", e)
        report["cpu"] = None

    try:
        mem = psutil.virtual_memory()
        report["memory"] = {
            "total_gb": _bytes_to_gb(mem.total),
            "used_gb": _bytes_to_gb(mem.used),
            "available_gb": _bytes_to_gb(mem.available),
            "percent": mem.percent,
        }
    except Exception as e:
        log.warning("Could not read memory metrics: %s", e)
        report["memory"] = None

    try:
        swap = psutil.swap_memory()
        report["swap"] = {
            "total_gb": _bytes_to_gb(swap.total),
            "used_gb": _bytes_to_gb(swap.used),
            "percent": swap.percent,
        }
    except Exception as e:
        log.warning("Could not read swap metrics: %s", e)
        report["swap"] = None

    try:
        disks = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue  # e.g. an empty CD/card reader
            disks.append(
                {
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "total_gb": _bytes_to_gb(usage.total),
                    "used_gb": _bytes_to_gb(usage.used),
                    "free_gb": _bytes_to_gb(usage.free),
                    "percent": usage.percent,
                }
            )
        report["disks"] = disks
    except Exception as e:
        log.warning("Could not read disk partitions: %s", e)
        report["disks"] = []

    try:
        io = psutil.disk_io_counters()
        report["disk_io"] = (
            {"read_mb": _bytes_to_mb(io.read_bytes), "write_mb": _bytes_to_mb(io.write_bytes)}
            if io
            else None
        )
    except Exception as e:
        log.warning("Could not read disk I/O counters: %s", e)
        report["disk_io"] = None

    try:
        net = psutil.net_io_counters()
        report["network"] = (
            {"sent_mb": _bytes_to_mb(net.bytes_sent), "recv_mb": _bytes_to_mb(net.bytes_recv)}
            if net
            else None
        )
    except Exception as e:
        log.warning("Could not read network counters: %s", e)
        report["network"] = None

    try:
        boot_ts = psutil.boot_time()
        uptime_hours = (time.time() - boot_ts) / 3600
        report["system"] = {
            "boot_time": datetime.fromtimestamp(boot_ts).isoformat(timespec="seconds"),
            "uptime_hours": uptime_hours,
            "process_count": len(psutil.pids()),
        }
    except Exception as e:
        log.warning("Could not read boot time/process count: %s", e)
        report["system"] = None

    try:
        battery = psutil.sensors_battery()
        if battery is not None:
            secs_left = battery.secsleft
            minutes_left = secs_left / 60 if secs_left and secs_left > 0 else None
            report["battery"] = {
                "percent": battery.percent,
                "power_plugged": battery.power_plugged,
                "minutes_left": minutes_left,
            }
        else:
            report["battery"] = None
    except Exception as e:
        log.warning("Could not read battery status: %s", e)
        report["battery"] = None

    try:
        # Not implemented on most Windows machines — psutil.sensors_temperatures may not
        # even exist as an attribute there, unlike on Linux.
        temps_raw = psutil.sensors_temperatures() if hasattr(psutil, "sensors_temperatures") else {}
        temps: dict = {}
        for name, entries in (temps_raw or {}).items():
            temps[name] = [
                {
                    "label": entry.label or name,
                    "current_c": entry.current,
                    "high_c": entry.high,
                    "critical_c": entry.critical,
                }
                for entry in entries
            ]
        report["temperatures"] = temps
    except Exception as e:
        log.warning("Could not read temperature sensors: %s", e)
        report["temperatures"] = {}

    return report


def _format_uptime(hours: float) -> str:
    days, rem_hours = divmod(hours, 24)
    days, rem_hours = int(days), int(rem_hours)
    if days > 0:
        return f"{days} day{'s' if days != 1 else ''} {rem_hours} hour{'s' if rem_hours != 1 else ''}"
    if rem_hours > 0:
        return f"{rem_hours} hour{'s' if rem_hours != 1 else ''}"
    return "less than an hour"


def _craft_system_status_summary(report: dict) -> str:
    """A short, spoken-friendly summary — the full detail lives in the report dict
    (also logged), since reading out every core/drive/sensor aloud would be unusable."""
    parts: list[str] = []

    cpu = report.get("cpu")
    if cpu:
        parts.append(
            f"CPU is at {cpu['overall_percent']:.0f} percent across "
            f"{cpu['logical_cores']} cores"
        )

    mem = report.get("memory")
    if mem:
        parts.append(
            f"RAM is at {mem['percent']:.0f} percent used, "
            f"{mem['available_gb']:.1f} gigabytes available"
        )

    swap = report.get("swap")
    if swap and swap["total_gb"] > 0.05:
        parts.append(f"swap is at {swap['percent']:.0f} percent")

    disks = report.get("disks") or []
    if disks:
        main = disks[0]
        extra_n = len(disks) - 1
        extra = f", plus {extra_n} more drive{'s' if extra_n != 1 else ''}" if extra_n else ""
        parts.append(f"drive {main['device']} has {main['free_gb']:.0f} gigabytes free{extra}")

    battery = report.get("battery")
    if battery:
        charging = " and charging" if battery["power_plugged"] else ""
        parts.append(f"battery is at {battery['percent']:.0f} percent{charging}")

    sysinfo = report.get("system")
    if sysinfo:
        parts.append(
            f"uptime is {_format_uptime(sysinfo['uptime_hours'])}, "
            f"with {sysinfo['process_count']} processes running"
        )

    temps = report.get("temperatures") or {}
    all_currents = [
        entry["current_c"]
        for entries in temps.values()
        for entry in entries
        if entry.get("current_c") is not None
    ]
    if all_currents:
        avg_temp = sum(all_currents) / len(all_currents)
        parts.append(f"average sensor temperature is {avg_temp:.0f} degrees Celsius")

    if not parts:
        return "I couldn't gather system stats just now."
    return ", ".join(parts) + "."


def system_status() -> str:
    try:
        import psutil  # noqa: F401  (imported here to fail fast with a clear message)
    except ImportError:
        return "I don't have the psutil library installed, so I can't check system stats."
    try:
        report = get_system_status_report()
    except Exception as e:
        log.warning("Could not gather system status: %s", e)
        return "Sorry, I couldn't gather system stats just now."
    log.info("Full system status report: %s", report)
    return _craft_system_status_summary(report)


# --- FEATURE 2: proactive system health monitoring — runs on its own in the background (no ---
# --- voice command needed) and speaks up when it spots something worth flagging, instead of ---
# --- only reporting stats when the user explicitly asks via the system_status tool. Builds on ---
# --- the same psutil metrics as system_status()/get_system_status_report(), and mirrors the ---
# --- free_up_ram skill's "top RAM processes" idea but acting on it proactively rather than ---
# --- waiting for the user to ask what's slowing the machine down. ---
HEALTH_CHECK_INTERVAL_S = 15 * 60  # run every 15 minutes
PROACTIVE_SUGGESTIONS_LOG_PATH = Path(__file__).resolve().parent / "proactive_suggestions.log"
DISK_USAGE_ALERT_PERCENT = 90.0  # a drive at/above this percent full is "approaching capacity"
CPU_LOAD_ALERT_PERCENT = 90.0

# Double-checked (2026-09-18, user request): RAM monitoring — the per-process "X is using N
# megabytes, want me to close it?" nag and the RAM-jump-since-last-check alert — was removed
# entirely, not just muted. Disk-capacity and CPU-load checks below are unaffected; the user
# only objected to the RAM ones. system_status() (on-demand, voice-asked) still reports RAM
# usage — this only removes the *unprompted* proactive nagging about it.


def _log_proactive_suggestion(text: str, timestamp: str) -> None:
    """Appends one line per suggestion to proactive_suggestions.log — a durable record of
    everything the health monitor has ever flagged, independent of whether it actually got
    spoken (see queue_or_deliver_notification, which may hold it back)."""
    try:
        with open(PROACTIVE_SUGGESTIONS_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{timestamp} {text}\n")
    except OSError as e:
        log.warning("Could not write to proactive suggestions log: %s", e)


def check_system_health() -> dict:
    """One health-check pass: gathers the top RAM-consuming processes, CPU load, and disk
    usage, compares against the previous pass to spot trends (e.g. a sudden RAM jump), and
    returns {"snapshot": ..., "suggestions": [...]}. Every metric is gathered independently
    so one failure (e.g. psutil missing, or a permission error on one drive) never blocks the
    rest — mirrors the defensive per-section pattern in get_system_status_report()."""
    try:
        import psutil
    except ImportError:
        log.warning("psutil not installed; skipping system health check.")
        return {"snapshot": None, "suggestions": []}

    now = datetime.now()
    timestamp = now.isoformat(timespec="seconds")
    suggestions: list[str] = []

    try:
        cpu_percent = psutil.cpu_percent(interval=0.5)
    except Exception as e:
        log.warning("Could not read CPU load: %s", e)
        cpu_percent = None

    disks_near_capacity: list[dict] = []
    try:
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (PermissionError, OSError):
                continue  # e.g. an empty CD/card reader
            if usage.percent >= DISK_USAGE_ALERT_PERCENT:
                disks_near_capacity.append(
                    {"device": part.device, "percent": usage.percent, "free_gb": _bytes_to_gb(usage.free)}
                )
    except Exception as e:
        log.warning("Could not read disk usage: %s", e)

    snapshot = {"timestamp": timestamp, "cpu_percent": cpu_percent}

    for disk in disks_near_capacity:
        suggestions.append(
            f"Drive {disk['device']} is at {disk['percent']:.0f} percent full, only "
            f"{disk['free_gb']:.1f} gigabytes free. Might want to clear some space soon."
        )

    if cpu_percent is not None and cpu_percent >= CPU_LOAD_ALERT_PERCENT:
        suggestions.append(f"CPU load is at {cpu_percent:.0f} percent right now.")

    for suggestion in suggestions:
        _log_proactive_suggestion(suggestion, timestamp)

    return {"snapshot": snapshot, "suggestions": suggestions}


def _health_monitor_loop() -> None:
    """Runs check_system_health() every HEALTH_CHECK_INTERVAL_S and speaks up (through the
    session-context interrupt gate, so it won't talk over a focused work session) whenever a
    pass produces suggestions — the proactive half of this feature; system_status()/
    check_system_health() itself stays available on-demand too."""
    while True:
        try:
            result = check_system_health()
            for suggestion in result.get("suggestions", []):
                queue_or_deliver_notification(suggestion)
        except Exception as e:
            log.warning("System health check failed: %s", e)
        time.sleep(HEALTH_CHECK_INTERVAL_S)


def _start_health_monitor() -> None:
    threading.Thread(target=_health_monitor_loop, daemon=True, name="health-monitor").start()


# --- disk usage: find large files and folders (read-only, never deletes anything) -----
def _resolve_scan_root(root_path: str) -> Path:
    rp = (root_path or "").strip()
    if not rp:
        return Path.home()
    if sys.platform == "win32" and re.fullmatch(r"[A-Za-z]:?", rp):
        return Path(rp.rstrip(":") + ":\\")
    return Path(rp).expanduser()


def _scan_dir_for_large_files(path: Path, min_bytes: int) -> tuple[int, list[tuple[str, int]]]:
    """Recursively sums file sizes under path, returning (total_bytes, large_files) where
    large_files lists every individual file >= min_bytes found anywhere in the tree.
    Symlinks are never followed (sidesteps symlink loops entirely); permission and
    not-found errors on restricted folders are swallowed so the scan keeps going."""
    total = 0
    large_files: list[tuple[str, int]] = []
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        sub_total, sub_large = _scan_dir_for_large_files(
                            Path(entry.path), min_bytes
                        )
                        total += sub_total
                        large_files.extend(sub_large)
                    elif entry.is_file(follow_symlinks=False):
                        size = entry.stat(follow_symlinks=False).st_size
                        total += size
                        if size >= min_bytes:
                            large_files.append((entry.path, size))
                except (PermissionError, FileNotFoundError, OSError):
                    continue
    except (PermissionError, FileNotFoundError, OSError):
        pass
    return total, large_files


def _fmt_gb(n: float) -> str:
    return f"{n / (1024 ** 3):.2f} GB"


def get_large_files_report(root_path: str = "", min_size_gb: float = 2.0) -> dict:
    """Scans root_path (default: home folder) for individual files and top-level
    directories at or above min_size_gb. Read-only — never deletes or modifies anything."""
    root = _resolve_scan_root(root_path)
    min_gb = min_size_gb if min_size_gb and min_size_gb > 0 else 2.0
    min_bytes = int(min_gb * 1024**3)

    report: dict = {
        "root": str(root),
        "min_size_gb": min_gb,
        "exists": root.exists(),
        "large_dirs": [],
        "large_files": [],
        "elapsed_s": 0.0,
        "error": None,
    }
    if not root.exists():
        report["error"] = f"{root} does not exist"
        return report

    start = time.monotonic()
    log.info("Scanning %s for files/folders >= %.2f GB (this may take a while)...", root, min_gb)

    large_dirs: list[tuple[str, int]] = []
    large_files: list[tuple[str, int]] = []
    try:
        with os.scandir(root) as it:
            top_entries = list(it)
    except (PermissionError, FileNotFoundError, OSError) as e:
        report["error"] = str(e)
        return report

    for entry in top_entries:
        try:
            if entry.is_symlink():
                continue
            if entry.is_dir(follow_symlinks=False):
                size, files_in = _scan_dir_for_large_files(Path(entry.path), min_bytes)
                if size >= min_bytes:
                    large_dirs.append((entry.path, size))
                large_files.extend(files_in)
            elif entry.is_file(follow_symlinks=False):
                size = entry.stat(follow_symlinks=False).st_size
                if size >= min_bytes:
                    large_files.append((entry.path, size))
        except (PermissionError, FileNotFoundError, OSError):
            continue

    large_dirs.sort(key=lambda t: t[1], reverse=True)
    large_files.sort(key=lambda t: t[1], reverse=True)
    report["large_dirs"] = large_dirs
    report["large_files"] = large_files
    report["elapsed_s"] = time.monotonic() - start
    return report


def _print_large_files_breakdown(report: dict) -> None:
    """The full breakdown, printed to the console — only the top few entries get spoken."""
    lines = [
        f"Large file/folder scan of {report['root']} (>= {report['min_size_gb']:g} GB), "
        f"completed in {report['elapsed_s']:.1f}s:",
        f"-- {len(report['large_dirs'])} large top-level folder(s) --",
    ]
    for path, size in report["large_dirs"]:
        lines.append(f"  {_fmt_gb(size):>10}  {path}")
    lines.append(f"-- {len(report['large_files'])} large individual file(s) --")
    for path, size in report["large_files"]:
        lines.append(f"  {_fmt_gb(size):>10}  {path}")
    log.info("\n".join(lines))


_scan_lock = threading.Lock()
_scan_in_progress = False


def scan_large_files(root_path: str = "", min_size_gb: float = 2.0) -> str:
    global _scan_in_progress
    with _scan_lock:
        if _scan_in_progress:
            return (
                "I'm already scanning for large files — I'll let you know when that's "
                "done, no need to ask again."
            )
        _scan_in_progress = True
    try:
        report = get_large_files_report(root_path, min_size_gb)
    except Exception as e:
        log.warning("Could not scan for large files: %s", e)
        return "Sorry, I couldn't scan for large files just now."
    finally:
        with _scan_lock:
            _scan_in_progress = False

    if report["error"]:
        return f"I couldn't scan {report['root']}: {report['error']}"

    _print_large_files_breakdown(report)

    large_dirs = report["large_dirs"]
    large_files = report["large_files"]
    min_gb = report["min_size_gb"]
    if not large_dirs and not large_files:
        return (
            f"I scanned {report['root']} in {report['elapsed_s']:.0f} seconds and didn't "
            f"find anything over {min_gb:g} gigabytes."
        )

    parts = [f"I scanned {report['root']} in {report['elapsed_s']:.0f} seconds."]
    if large_dirs:
        listing = ", ".join(
            f"{Path(p).name or p} at {_fmt_gb(s)}" for p, s in large_dirs[:3]
        )
        parts.append(f"Biggest folders: {listing}.")
    if large_files:
        listing = ", ".join(
            f"{Path(p).name} at {_fmt_gb(s)}" for p, s in large_files[:3]
        )
        parts.append(f"Biggest individual files: {listing}.")
    return " ".join(parts)


def _read_clipboard() -> str:
    try:
        import pyperclip
    except ImportError:
        log.warning("Install `pyperclip` (see requirements.txt) to use clipboard actions.")
        return ""
    try:
        return pyperclip.paste() or ""
    except Exception as e:
        log.warning("Could not read clipboard: %s", e)
        return ""


# Clipboard content can be large (whole files, long logs); cap what we send to Claude.
CLIPBOARD_CHARS_TO_CLAUDE = 6000


def read_clipboard_and_describe(transcript: str) -> str:
    text = _read_clipboard()
    if not text.strip():
        return "Your clipboard is empty."
    data = _claude_request(
        {
            "model": CLAUDE_MODEL,
            "max_tokens": 500,
            "system": (
                "The user copied this to their clipboard. Briefly (2-4 sentences) answer their "
                "question about it, or summarize/explain it if they didn't ask something specific."
            ),
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Question: {transcript}\n\nClipboard content:\n"
                        f"{text[:CLIPBOARD_CHARS_TO_CLAUDE]}"
                    ),
                }
            ],
        },
        timeout=30,
    )
    if data is None:
        return "Sorry, I couldn't process the clipboard content just now."
    return _claude_text(data) or "I couldn't make sense of the clipboard content."


def refactor_clipboard_code(transcript: str) -> tuple[str, str]:
    """Returns (spoken_explanation, refactored_code_or_empty)."""
    text = _read_clipboard()
    if not text.strip():
        return "Your clipboard is empty, so there's nothing to refactor.", ""
    data = _claude_request(
        {
            "model": CLAUDE_MODEL,
            "max_tokens": 1500,
            "system": (
                "The user copied a code snippet to their clipboard and wants it refactored or "
                "fixed. Reply with a short (1-2 sentence) spoken explanation of what you changed, "
                "then a line saying exactly ---CODE--- followed by ONLY the corrected/refactored "
                "code, nothing else after it."
            ),
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Request: {transcript}\n\nClipboard code:\n"
                        f"{text[:CLIPBOARD_CHARS_TO_CLAUDE]}"
                    ),
                }
            ],
        },
        timeout=45,
    )
    if data is None:
        return "Sorry, I couldn't reach Claude to refactor that.", ""
    full = _claude_text(data)
    if "---CODE---" in full:
        explanation, code = full.split("---CODE---", 1)
        return explanation.strip(), code.strip()
    return full or "I couldn't refactor that.", ""


class _DuckDuckGoResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[tuple[str, str]] = []
        self._pending_title: str | None = None
        self._in_title = False
        self._in_snippet = False
        self._buf = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        cls = dict(attrs).get("class") or ""
        if tag == "a" and cls == "result-link":
            self._in_title = True
            self._buf = ""
        elif tag == "td" and cls == "result-snippet":
            self._in_snippet = True
            self._buf = ""

    def handle_data(self, data: str) -> None:
        if self._in_title or self._in_snippet:
            self._buf += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_title:
            self._in_title = False
            self._pending_title = self._buf.strip()
        elif tag == "td" and self._in_snippet:
            self._in_snippet = False
            snippet = self._buf.strip()
            if self._pending_title:
                self.results.append((self._pending_title, snippet))
                self._pending_title = None


def _duckduckgo_search(query: str, max_results: int = 5) -> list[tuple[str, str]]:
    url = "https://lite.duckduckgo.com/lite/?" + urllib.parse.urlencode({"q": query})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Jarvis voice assistant)"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    parser = _DuckDuckGoResultParser()
    parser.feed(html)
    return parser.results[:max_results]


def web_search_and_summarize(transcript: str, query: str) -> str:
    q = (query or transcript).strip()
    if not q:
        return "I don't have anything to search for."
    try:
        results = _duckduckgo_search(q)
    except Exception as e:
        log.warning("Web search failed: %s", e)
        return "Sorry, I couldn't search the web just now."
    if not results:
        return f"I couldn't find anything for {q}."

    if not _llm_configured():
        title, snippet = results[0]
        return f"{title}. {snippet}"

    listing = "\n".join(f"- {title}: {snippet}" for title, snippet in results)
    data = _claude_request(
        {
            "model": CLAUDE_MODEL,
            "max_tokens": 600,
            "system": (
                "Summarize these web search results into a short spoken answer "
                "(2-4 sentences) for the user's question. Answer naturally; don't "
                "mention that these are search results."
            ),
            "messages": [
                {
                    "role": "user",
                    "content": f"Question: {transcript}\nSearch query: {q}\nResults:\n{listing}",
                }
            ],
        },
        timeout=30,
    )
    if data is None:
        title, snippet = results[0]
        return f"{title}. {snippet}"
    return _claude_text(data) or f"{results[0][0]}. {results[0][1]}"


def type_text(text: str) -> None:
    t = text or ""
    if not t:
        return
    try:
        import keyboard
    except ImportError:
        log.warning("Install `keyboard` (see requirements.txt) to type text.")
        return
    try:
        keyboard.write(t)
    except Exception as e:
        log.warning("Could not type text: %s", e)


SHELL_TIMEOUT_S = 60
MAX_TOOL_RESULT_CHARS = 4000

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[@-Z\\-_]")


def _strip_ansi(text: str) -> str:
    """Strips ANSI/VT100 escape sequences (color codes, cursor movement) that a subprocess
    (PowerShell, the `claude` CLI, anything meant for a terminal) writes to its output —
    raw control bytes have no business reaching Claude as tool_result content."""
    return _ANSI_ESCAPE_RE.sub("", text)


def _run_shell_command(command: str) -> str:
    try:
        popen_kw: dict = {}
        if os.name == "nt":
            popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=SHELL_TIMEOUT_S,
            **popen_kw,
        )
        out = _strip_ansi((proc.stdout or "").strip())[:MAX_TOOL_RESULT_CHARS]
        err = _strip_ansi((proc.stderr or "").strip())[:MAX_TOOL_RESULT_CHARS]
        result = f"exit_code={proc.returncode}"
        if out:
            result += f"\nstdout:\n{out}"
        if err:
            result += f"\nstderr:\n{err}"
        return result
    except subprocess.TimeoutExpired:
        return f"Command timed out after {SHELL_TIMEOUT_S} seconds."
    except Exception as e:
        return f"Failed to run command: {e}"


def _run_python_code(code: str) -> str:
    try:
        popen_kw: dict = {}
        if os.name == "nt":
            popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=SHELL_TIMEOUT_S,
            **popen_kw,
        )
        out = _strip_ansi((proc.stdout or "").strip())[:MAX_TOOL_RESULT_CHARS]
        err = _strip_ansi((proc.stderr or "").strip())[:MAX_TOOL_RESULT_CHARS]
        result = f"exit_code={proc.returncode}"
        if out:
            result += f"\nstdout:\n{out}"
        if err:
            result += f"\nstderr:\n{err}"
        return result
    except subprocess.TimeoutExpired:
        return f"Code timed out after {SHELL_TIMEOUT_S} seconds."
    except Exception as e:
        return f"Failed to run code: {e}"


def _read_file_tool(path: str) -> str:
    if not path:
        return "No path given."
    try:
        data = Path(path).expanduser().read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Failed to read {path}: {e}"
    if len(data) > MAX_TOOL_RESULT_CHARS * 2:
        return data[: MAX_TOOL_RESULT_CHARS * 2] + f"\n... [truncated, {len(data)} chars total]"
    return data or "(file is empty)"


def _write_file_tool(path: str, content: str, append: bool) -> str:
    if not path:
        return "No path given."
    try:
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a" if append else "w", encoding="utf-8") as f:
            f.write(content or "")
        return f"{'Appended' if append else 'Wrote'} {len(content or '')} chars to {p}."
    except Exception as e:
        return f"Failed to write {path}: {e}"


def _http_request_tool(url: str, method: str, headers: dict | None, body: str | None) -> str:
    if not url:
        return "No URL given."
    try:
        data = body.encode() if body else None
        req = urllib.request.Request(
            url, data=data, method=(method or "GET").upper(), headers=headers or {}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode(errors="replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace") if e.fp else str(e)
        status = e.code
    except Exception as e:
        return f"Request failed: {e}"
    if len(text) > MAX_TOOL_RESULT_CHARS:
        text = text[:MAX_TOOL_RESULT_CHARS] + f"... [truncated, {len(text)} chars total]"
    return f"status={status}\n{text}"


# --- Claude Code delegation: real development work (multi-file changes, repo-wide search, ---
# --- tests) goes to a full headless Claude Code agent instead of Jarvis's own run_shell/ ---
# --- write_file — a much larger toolset and a design built for exactly this. Runs with ---
# --- --dangerously-skip-permissions since no human is present to click "allow" from a voice ---
# --- session; the same catastrophic-command tripwire used for run_shell/run_python is applied ---
# --- to the task text as a first line of defense, though it can't see what the delegated agent ---
# --- decides to do autonomously partway through the task — that's a real, accepted gap, not an ---
# --- oversight, consistent with this whole tool being full-trust by design. ---
CLAUDE_CODE_TIMEOUT_S = 900


# --- FEATURE: background tasks — delegate_to_claude_code (real coding/debugging work, via a ---
# --- detached `claude -p` subprocess) and delegate_research (websearch-and-summarize, via a ---
# --- plain background thread running the same run_agent_loop a voice command uses) both let ---
# --- Jarvis keep taking new commands immediately instead of blocking on the task. Both are ---
# --- tracked in the background_tasks table and report back through the same ---
# --- queue_or_deliver_notification/toast pipeline reminders already use — see ---
# --- background_agents_plan.md for the design this implements. ---
_background_tasks_lock = threading.Lock()
# In-memory only: maps a background_tasks row id to (its live Popen handle, spawn time), for
# polling and stale-process detection by _check_background_tasks. Doesn't survive a restart —
# see _recover_interrupted_background_tasks.
_RUNNING_BACKGROUND_PROCS: dict[int, tuple[subprocess.Popen, float]] = {}
# Caps concurrent *coding* background tasks (each a full `claude -p` session) — these draw from
# the same shared Pro/Max usage pool as interactive Claude Code/app usage, unlike research tasks
# (cheap Haiku tool calls), so it's worth capping rather than letting requests pile up unbounded.
MAX_CONCURRENT_BACKGROUND_CODE_TASKS = 2
# Caps concurrent *plan* background tasks (set_plan) — each step is its own Claude request, so
# several plans running at once could otherwise stack up a lot of concurrent API traffic.
MAX_CONCURRENT_PLAN_TASKS = 2


def _background_tasks_dir(task_id: int) -> Path:
    d = Path(__file__).resolve().parent / ".jarvis_tasks" / str(task_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _insert_background_task(task: str, kind: str, target: str) -> int:
    now_iso = datetime.now().isoformat(timespec="seconds")
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            cur = conn.execute(
                "INSERT INTO background_tasks (kind, task, target, status, started_at) "
                "VALUES (?, ?, ?, 'running', ?)",
                (kind, task, target, now_iso),
            )
            conn.commit()
            task_id = int(cur.lastrowid)
        finally:
            conn.close()
    dashboard.notify({
        "type": "background_task_update",
        "data": {"id": task_id, "kind": kind, "task": task, "status": "running"},
    })
    return task_id


def _count_running_background_tasks(kind: str) -> int:
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM background_tasks WHERE kind = ? AND status = 'running'",
                (kind,),
            ).fetchone()
        finally:
            conn.close()
    return int(row[0]) if row else 0


def _finish_background_task(task_id: int, status: str, summary: str, kind: str = "") -> None:
    """Marks a background_tasks row done/failed and reports it: a Windows toast plus a spoken
    message. Reported urgent=True (bypasses the busy-quiet-hours gate other proactive messages
    go through) — unlike a scheduled skill or health-monitor suggestion, the user explicitly
    asked for this and is waiting on it, so it should never sit silently queued until they
    happen to say something else first. A 'code' task is reported in James's voice (the
    coding-agent persona) since that's who the user was told is doing it; other kinds
    (research) stay generic since no persona was named."""
    now_iso = datetime.now().isoformat(timespec="seconds")
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            conn.execute(
                "UPDATE background_tasks SET status = ?, finished_at = ?, result_summary = ? "
                "WHERE id = ?",
                (status, now_iso, summary, task_id),
            )
            conn.commit()
        finally:
            conn.close()
    dashboard.notify({
        "type": "background_task_update",
        "data": {"id": task_id, "status": status, "result_summary": summary},
    })
    ok = status == "done"
    if kind == "code":
        who = f"{CODING_AGENT_NAME} (background task #{task_id})"
        lead = f"{who} is done:" if ok else f"{who} ran into a problem:"
    else:
        lead = f"Background task #{task_id} finished:" if ok else f"Background task #{task_id} failed:"
    message = f"{lead} {summary}"
    send_windows_toast("Jarvis — background task done", message[:250])
    queue_or_deliver_notification(message, urgent=True, force_phone=task_id in _SELF_EDIT_TASK_IDS)
    record_recent_task(f"background task #{task_id} {'finished' if ok else 'failed'}")


def list_background_tasks(include_finished: bool = False) -> str:
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            sql = "SELECT id, kind, task, status, started_at, result_summary FROM background_tasks"
            if not include_finished:
                sql += " WHERE status = 'running'"
            sql += " ORDER BY id DESC LIMIT 20"
            rows = conn.execute(sql).fetchall()
            # For a running 'plan' task, "running" alone doesn't say how far along it is —
            # look up step completion so quick_recall/list_background_tasks can show "step 3/6"
            # instead of leaving the user guessing.
            plan_progress: dict[int, str] = {}
            for tid, kind, _task, status, _started_at, _summary in rows:
                if kind == "plan" and status == "running":
                    total = conn.execute(
                        "SELECT COUNT(*) FROM plan_steps WHERE task_id = ?", (tid,)
                    ).fetchone()[0]
                    done = conn.execute(
                        "SELECT COUNT(*) FROM plan_steps WHERE task_id = ? AND status = 'done'",
                        (tid,),
                    ).fetchone()[0]
                    plan_progress[tid] = f"step {done}/{total}"
        finally:
            conn.close()
    if not rows:
        return "No background tasks running." if not include_finished else "No background tasks recorded."
    lines = []
    for tid, kind, task, status, started_at, summary in rows:
        progress = f", {plan_progress[tid]}" if tid in plan_progress else ""
        detail = f" — {summary}" if status != "running" and summary else ""
        lines.append(f"#{tid} [{status}] ({kind}{progress}, started {started_at}): {task}{detail}")
    return "\n".join(lines)


def _recover_interrupted_background_tasks() -> None:
    """Called once at startup, before the scheduler starts. A row still 'running' from a
    previous process has no live Popen/thread behind it — that state is in-memory only and
    doesn't survive a restart, and a headless Claude Code session can't reliably be resumed
    mid-execution anyway (transcript continuity isn't the same as the original OS process
    still existing) — so mark it failed honestly instead of pretending it might still finish."""
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            now_iso = datetime.now().isoformat(timespec="seconds")
            cur = conn.execute(
                "UPDATE background_tasks SET status = 'failed', finished_at = ?, "
                "result_summary = 'interrupted by a Jarvis restart' WHERE status = 'running'",
                (now_iso,),
            )
            # A plan's steps have no live thread behind them either once the process
            # restarts — leave completed ones as a record of real progress, but stop any
            # step still 'pending'/'running' from looking like it's still in flight.
            conn.execute(
                "UPDATE plan_steps SET status = 'failed', finished_at = ?, "
                "result_summary = 'interrupted by a Jarvis restart' "
                "WHERE status IN ('pending', 'running')",
                (now_iso,),
            )
            conn.commit()
            if cur.rowcount:
                log.warning(
                    "Marked %d background task(s) failed (interrupted by restart).", cur.rowcount
                )
        finally:
            conn.close()


def _check_background_tasks(now: datetime) -> None:
    """Called once per scheduler tick. Polls the OS processes backing running 'code' tasks
    (started by _delegate_to_claude_code); 'research' tasks (path B, a plain background
    thread) report their own completion via _finish_background_task instead, since there's
    no subprocess here to poll for those."""
    with _background_tasks_lock:
        items = list(_RUNNING_BACKGROUND_PROCS.items())
    for task_id, (proc, started_at) in items:
        if proc.poll() is None:
            if time.monotonic() - started_at > CLAUDE_CODE_TIMEOUT_S:
                log.warning(
                    "Background task #%d exceeded %ds; killing it.", task_id, CLAUDE_CODE_TIMEOUT_S
                )
                proc.kill()
                with _background_tasks_lock:
                    _RUNNING_BACKGROUND_PROCS.pop(task_id, None)
                _finish_background_task(
                    task_id,
                    "failed",
                    f"timed out after {CLAUDE_CODE_TIMEOUT_S} seconds and was killed",
                    kind="code",
                )
            continue  # still running
        with _background_tasks_lock:
            _RUNNING_BACKGROUND_PROCS.pop(task_id, None)

        output_path = _background_tasks_dir(task_id) / "output.json"
        try:
            raw = output_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raw = ""
        raw = _strip_ansi(raw).strip()

        if proc.returncode != 0:
            summary = f"exited with an error (code {proc.returncode}): {raw[:MAX_TOOL_RESULT_CHARS] or 'no output'}"
            _finish_background_task(task_id, "failed", summary, kind="code")
            continue

        try:
            data = json.loads(raw)
            result = str(data.get("result") or "").strip()
        except (json.JSONDecodeError, TypeError):
            result = raw
        if len(result) > MAX_TOOL_RESULT_CHARS:
            result = result[:MAX_TOOL_RESULT_CHARS] + f"... [truncated, {len(result)} chars total]"
        _finish_background_task(task_id, "done", result or "finished with no result text", kind="code")


def _dashboard_kill_background_task(task_id: int) -> str:
    """Phase 2 Stop button. Only ever kills a process Jarvis itself spawned via
    _delegate_to_claude_code (already passed the catastrophic-reason check at delegation
    time) — never touches the confirmation gate. Mirrors the existing timeout-reaper kill
    path in _check_background_tasks rather than adding new process-control logic."""
    with _background_tasks_lock:
        entry = _RUNNING_BACKGROUND_PROCS.pop(task_id, None)
    if not entry:
        return (
            "That task isn't currently running as a killable background process "
            "(already finished, or a queued/reminder task with no live process to stop)."
        )
    proc, _started_at = entry
    try:
        proc.kill()
    except Exception as e:
        return f"Failed to stop task #{task_id}: {e}"
    _finish_background_task(task_id, "cancelled", "Cancelled from dashboard.", kind="code")
    return f"Stopped task #{task_id}."


# Prepended to every task that runs in Jarvis's *own* folder (whichever tool started it), so the
# self-editing path can't skip the project's standing rules. The agent is headless and cannot ask
# questions, so anything risky must be reported instead of done. The user accepted (2026-09-18)
# that this can be triggered from the phone channels too, and knows the risk; these rules are a
# guardrail for the model, not a hard technical barrier.
_SELF_EDIT_PREAMBLE = (
    "You are modifying the Jarvis voice assistant's OWN source code (this repository), at the "
    "user's request via Jarvis. Rules, in priority order:\n"
    "1. Read CLAUDE.md first and follow it. For dashboard features it requires a risk review "
    "(security, cost, data exposure, irreversibility, performance); you cannot ask questions "
    "here, so if any of those risks is non-zero and unmitigated, do NOT implement it — explain "
    "the risk in your final message instead.\n"
    "2. Never weaken or bypass the catastrophic confirmation gate (_CATASTROPHIC_PATTERNS / "
    "_pending_action), the phone-notification rules, or the dashboard's localhost-only binding "
    "(no 0.0.0.0, no tunnels), and never add a new way to run commands or actions that skips "
    "the existing gate.\n"
    "3. Never read out, print, or commit secrets (.env, tokens, PINs, API keys).\n"
    "4. Add or extend tests for what you change, and run `python -m pytest test_cache.py "
    "test_dashboard.py -q`; do not finish while tests fail (revert your change if you can't "
    "fix them).\n"
    "5. Commit locally with a clear message, but do NOT push and do NOT restart or kill "
    "Jarvis: the running instance keeps its old code until the user restarts it.\n"
    "6. Your final message is spoken aloud and sent to the user's phone: two to four plain "
    "sentences — what you added, whether tests passed, and that a restart is needed to use "
    "it.\n\n"
    "The requested change: "
)
_SELF_EDIT_TASK_IDS: set[int] = set()


def _delegate_to_claude_code(task: str, repo_path: str) -> str:
    task = (task or "").strip()
    if not task:
        return "No task given."
    reason = _catastrophic_reason(task)
    if reason:
        return (
            f"That task reads as though it would {reason} — refusing to delegate it "
            "automatically. Ask explicitly via run_shell/run_python if this is really wanted; "
            "that path still has its own confirmation step for this tier."
        )
    cwd = Path(repo_path).expanduser() if repo_path else Path(__file__).resolve().parent
    if not cwd.is_dir():
        return f"{cwd} is not a valid directory."
    self_edit = cwd.resolve() == Path(__file__).resolve().parent
    if self_edit:
        with _background_tasks_lock:
            self_edit_running = any(t in _RUNNING_BACKGROUND_PROCS for t in _SELF_EDIT_TASK_IDS)
        if self_edit_running:
            return (
                f"{CODING_AGENT_NAME} is already changing my code (one self-change at a time, so "
                "two edits can't collide) — ask again once that one finishes."
            )
    try:
        workflow.touch_workspace(str(cwd))
    except Exception as e:
        log.debug("workflow.touch_workspace failed for %s: %s", cwd, e)

    running = _count_running_background_tasks("code")
    if running >= MAX_CONCURRENT_BACKGROUND_CODE_TASKS:
        return (
            f"{CODING_AGENT_NAME} already has {running} background task(s) running (cap is "
            f"{MAX_CONCURRENT_BACKGROUND_CODE_TASKS}, to stay within the shared Pro/Max usage "
            "pool) — ask again once one finishes; list_background_tasks shows what's running."
        )

    task_id = _insert_background_task(task, "code", str(cwd))
    output_path = _background_tasks_dir(task_id) / "output.json"

    popen_kw: dict = {}
    if os.name == "nt":
        popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    # Strip API-key-style credentials before handing the subprocess its environment: the
    # `claude` CLI's own auth resolution tries ANTHROPIC_API_KEY/ANTHROPIC_AUTH_TOKEN before
    # ever falling back to a `claude login` OAuth session, so leaving Jarvis's own key in
    # this child's environment would silently bill the delegated task per-token against that
    # key instead of using a Pro/Max subscription login — even though Jarvis's own brain
    # legitimately needs that same env var for its own direct API calls.
    child_env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
    }
    try:
        # Opening the file only for the Popen call (not kept open in this process) is
        # deliberate: the child gets its own duplicated handle at spawn time, so closing our
        # copy when the `with` block exits doesn't touch the child's ability to keep writing.
        with open(output_path, "w", encoding="utf-8") as out_f:
            proc = subprocess.Popen(
                [
                    "claude", "-p", (_SELF_EDIT_PREAMBLE + task) if self_edit else task,
                    "--output-format", "json", "--dangerously-skip-permissions",
                ],
                cwd=str(cwd),
                stdout=out_f,
                stderr=subprocess.STDOUT,
                text=True,
                env=child_env,
                **popen_kw,
            )
    except FileNotFoundError:
        msg = "the `claude` CLI isn't installed or isn't on PATH"
        _finish_background_task(task_id, "failed", msg, kind="code")
        return f"Couldn't hand this to {CODING_AGENT_NAME} — {msg}."
    except Exception as e:
        _finish_background_task(task_id, "failed", f"failed to start: {e}", kind="code")
        return f"Couldn't hand this to {CODING_AGENT_NAME} — failed to start: {e}"

    with _background_tasks_lock:
        _RUNNING_BACKGROUND_PROCS[task_id] = (proc, time.monotonic())
        if self_edit:
            _SELF_EDIT_TASK_IDS.add(task_id)
    record_recent_task(f"started background coding task #{task_id}: {task}")
    return (
        f"Handed this off to {CODING_AGENT_NAME} (background task #{task_id}) in {cwd}: {task}. "
        f"I'll keep taking other commands — {CODING_AGENT_NAME} will let you know once it's done."
    )


def _delegate_research(task: str, output_path: str) -> str:
    task = (task or "").strip()
    if not task:
        return "No research task given."
    reason = _catastrophic_reason(task)
    if reason:
        return f"That task reads as though it would {reason} — refusing to run it automatically."

    output_path = (output_path or "").strip()
    if not output_path:
        default_dir = Path.home() / "Jarvis_Research"
        default_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_path = str(default_dir / f"research-{stamp}.md")

    task_id = _insert_background_task(task, "research", output_path)
    synthetic_transcript = (
        "(This is a background research task the user asked you to run while they do other "
        "things — they are not watching this. Research the following and write your findings "
        f"to the file {output_path!r} using write_file, then reply with a one-sentence summary "
        "of what you found and saved.) " + task
    )

    def _run() -> None:
        try:
            reply = run_agent_loop(synthetic_transcript)
        except Exception as e:
            _finish_background_task(task_id, "failed", f"research task raised an error: {e}")
            return
        _finish_background_task(task_id, "done", reply.strip() or f"finished, saved to {output_path}")

    threading.Thread(target=_run, daemon=True, name=f"research-task-{task_id}").start()
    record_recent_task(f"started background research task #{task_id}: {task}")
    return (
        f"Started background research task #{task_id}, saving to {output_path}. I'll keep "
        "taking other commands and let you know when it's done."
    )


# --- FEATURE: set_plan — an explicit, checkpointed step list for compound instructions, ---
# --- instead of working through every sub-task inline in one growing run_agent_loop ---
# --- conversation (see MULTITASKING_RESEARCH.md for why: cost grows with history length, ---
# --- a wedged request or a hit MAX_AGENT_ITERATIONS silently drops the whole task, and ---
# --- there's no way to express "this step must happen before that one"). A plan is just ---
# --- another background_tasks row (kind='plan'); its steps live in plan_steps, checkpointed ---
# --- one at a time, and it reports back through the same notification pipeline as everything ---
# --- else in this file. ---
def _mark_plan_step(task_id: int, step_index: int, status: str, summary: str = "") -> None:
    now_iso = datetime.now().isoformat(timespec="seconds")
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            if status == "running":
                conn.execute(
                    "UPDATE plan_steps SET status = ?, started_at = ? "
                    "WHERE task_id = ? AND step_index = ?",
                    (status, now_iso, task_id, step_index),
                )
            else:
                conn.execute(
                    "UPDATE plan_steps SET status = ?, finished_at = ?, result_summary = ? "
                    "WHERE task_id = ? AND step_index = ?",
                    (status, now_iso, summary, task_id, step_index),
                )
            conn.commit()
        finally:
            conn.close()


def _run_plan_step(step_description: str, prior_context: str) -> str:
    """Runs one plan step as its own small agent loop against a slim context — just this
    step's description plus a short summary of what its dependency step(s) produced, not the
    whole plan's running transcript. This (not just checkpointing) is what keeps a multi-step
    plan's per-step cost flat instead of compounding the way run_agent_loop's full-history
    resend does across a long chain. set_plan itself is excluded from the toolset here so a
    step can't recursively spawn its own sub-plan."""
    intro = (
        "(This is one step of a multi-step plan you created for the user's request. Do just "
        "this step, using tools as needed, then reply with a short one or two sentence summary "
        "of what you did or found — that summary is what the next dependent step sees, not "
        "this whole exchange, so make it self-contained.)"
    )
    if prior_context:
        intro += f" Relevant results from earlier steps this one depends on: {prior_context}"
    messages: list[dict] = [{"role": "user", "content": f"{intro}\n\nStep: {step_description}"}]
    reply_parts: list[str] = []
    tools = [t for t in AGENT_TOOLS if t["name"] != "set_plan"] + get_mcp_tool_schemas()
    system_blocks = build_system_blocks()
    cached_tools = _cached_tools(tools)

    for _ in range(MAX_STEP_ITERATIONS):
        data = _claude_request(
            {
                "model": CLAUDE_MODEL,
                "max_tokens": 1024,
                "system": system_blocks,
                "messages": _messages_with_cache_breakpoint(messages),
                "tools": cached_tools,
            },
            timeout=60,
        )
        if data is None:
            return " ".join(reply_parts).strip() or "step failed: could not reach Claude"
        _log_cache_usage(data, "plan step")

        content = data.get("content", [])
        messages.append({"role": "assistant", "content": content})
        reply_parts.extend(
            b.get("text", "") for b in content if b.get("type") == "text" and b.get("text")
        )

        tool_uses = [b for b in content if b.get("type") == "tool_use"]
        if not tool_uses or data.get("stop_reason") != "tool_use":
            break

        tool_results = []
        for i, tu in enumerate(tool_uses):
            if i < MAX_TOOL_CALLS_PER_TURN:
                result_text = _execute_tool(tu.get("name", ""), tu.get("input") or {}, step_description)
            else:
                result_text = "Skipped: too many tool calls requested in a single turn."
            tool_results.append(
                {"type": "tool_result", "tool_use_id": tu.get("id"), "content": result_text}
            )
        messages.append({"role": "user", "content": tool_results})

    return " ".join(p.strip() for p in reply_parts if p.strip()) or "step finished with no summary text"


def _run_plan(task_id: int) -> None:
    """Background-thread entry point (like _delegate_research's _run): works through a plan's
    steps in dependency order, one at a time, persisting each step's result before moving on
    so a crash or a hung request only loses the one in-flight step, not the whole plan.
    Fail-fast — one failed step stops the plan rather than running the rest against a
    dependency that never produced its result, since later steps' context would be wrong."""
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            rows = conn.execute(
                "SELECT step_index, description, depends_on FROM plan_steps "
                "WHERE task_id = ? ORDER BY step_index",
                (task_id,),
            ).fetchall()
        finally:
            conn.close()
    steps = {idx: (desc, json.loads(deps or "[]")) for idx, desc, deps in rows}
    results: dict[int, str] = {}
    done: set[int] = set()
    remaining = set(steps.keys())

    while remaining:
        ready = sorted(i for i in remaining if all(d in done for d in steps[i][1]))
        if not ready:
            stuck = sorted(remaining)
            _finish_background_task(
                task_id,
                "failed",
                f"stuck: step(s) {stuck} depend on a step that never completed (cycle or bad index)",
                kind="plan",
            )
            return

        step_idx = ready[0]
        description, deps = steps[step_idx]
        _mark_plan_step(task_id, step_idx, "running")
        prior_context = "; ".join(f"step {d}: {results[d]}" for d in deps if d in results)
        try:
            summary = _run_plan_step(description, prior_context)
        except Exception as e:
            summary = f"raised an error: {e}"
            _mark_plan_step(task_id, step_idx, "failed", summary)
            _finish_background_task(
                task_id, "failed", f"step {step_idx} ({description}) {summary}", kind="plan"
            )
            return

        _mark_plan_step(task_id, step_idx, "done", summary)
        results[step_idx] = summary
        done.add(step_idx)
        remaining.discard(step_idx)

    final_summary = " ".join(f"step {i}: {results[i]}" for i in sorted(results))
    if len(final_summary) > MAX_TOOL_RESULT_CHARS:
        final_summary = final_summary[:MAX_TOOL_RESULT_CHARS] + "... [truncated]"
    _finish_background_task(task_id, "done", final_summary or "all steps finished", kind="plan")


def _set_plan(transcript: str, steps: list) -> str:
    """Handles the set_plan tool call: validates and persists an ordered step list, then hands
    it to a background thread (_run_plan) instead of executing it inline — the calling
    run_agent_loop turn just confirms the plan started and moves on, exactly like
    delegate_to_claude_code/delegate_research already do for their own background work."""
    cleaned: list[dict] = []
    for i, s in enumerate(steps or []):
        desc = str((s or {}).get("description") or "").strip()
        if not desc:
            continue
        deps = sorted({int(d) for d in (s.get("depends_on") or []) if isinstance(d, (int, float))})
        cleaned.append({"step": i, "description": desc, "depends_on": deps})

    if len(cleaned) < 2:
        return "That's not really a multi-step plan — just do it directly instead of calling set_plan."
    valid_indices = {s["step"] for s in cleaned}
    for s in cleaned:
        s["depends_on"] = [d for d in s["depends_on"] if d in valid_indices and d != s["step"]]

    running = _count_running_background_tasks("plan")
    if running >= MAX_CONCURRENT_PLAN_TASKS:
        return (
            f"Already {running} plan(s) running (cap is {MAX_CONCURRENT_PLAN_TASKS}) — ask "
            "again once one finishes; list_background_tasks shows what's running."
        )

    task_id = _insert_background_task(transcript, "plan", json.dumps(cleaned))
    now_iso = datetime.now().isoformat(timespec="seconds")
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            for s in cleaned:
                conn.execute(
                    "INSERT INTO plan_steps (task_id, step_index, description, depends_on, "
                    "status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
                    (task_id, s["step"], s["description"], json.dumps(s["depends_on"]), now_iso),
                )
            conn.commit()
        finally:
            conn.close()

    threading.Thread(target=_run_plan, args=(task_id,), daemon=True, name=f"plan-task-{task_id}").start()
    record_recent_task(f"started background plan #{task_id} with {len(cleaned)} steps: {transcript}")
    return (
        f"Started background plan #{task_id} with {len(cleaned)} steps. I'll work through them "
        "in order and let you know when it's done — list_background_tasks shows progress if asked."
    )


def _log_action_audit(tool_name: str, tool_input: dict, transcript: str, result: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with _memory_db_lock:
        conn = _memory_db_connect()
        try:
            conn.execute(
                "INSERT INTO action_audit (timestamp, transcript, tool_name, tool_input, result) "
                "VALUES (?, ?, ?, ?, ?)",
                (now, transcript, tool_name, json.dumps(tool_input)[:2000], (result or "")[:2000]),
            )
            conn.commit()
        finally:
            conn.close()


# --- read-only tool result cache + reply cache ----------------------------------------------
# Tools that only *read* state, with how long (seconds) a result may be reused. Anything not in
# this table — every mutating tool, every mcp_* tool, anything unknown — is never cached, and
# running one clears both caches below, since it may have changed what a read would return.
READONLY_TOOL_TTLS: dict[str, float] = {
    "system_status": 20,
    "api_spend": 300,
    "list_reminders": 30,
    "list_task_queue": 30,
    "list_background_tasks": 30,
    "get_workflow_status": 30,
    "get_recent_file_events": 30,
    "list_open_windows": 15,
    "list_watched_folders": 60,
    "list_window_layouts": 60,
    "recall_facts": 60,
    "quick_recall": 60,
    "semantic_recall": 60,
    "web_search": 600,
}
# web_search's summary is written for the transcript that asked (web_search_and_summarize takes
# it), so that tool's cache key includes it; the others depend only on their arguments.
_TRANSCRIPT_KEYED_TOOLS = {"web_search"}
_tool_result_cache = cache.TTLCache(256)
_reply_cache = cache.TTLCache(128)
_FAILED_RESULT_PREFIXES = ("couldn't", "could not", "no results", "unrecognized", "error", "failed", "skipped")


def _looks_failed(result: str) -> bool:
    r = (result or "").strip().lower()
    return not r or r.startswith(_FAILED_RESULT_PREFIXES) or "unavailable" in r[:60]


def _invalidate_read_caches() -> None:
    _tool_result_cache.clear()
    _reply_cache.clear()


def _execute_tool(
    tool_name: str, tool_input: dict, transcript: str, skip_confirmation: bool = False
) -> str:
    """_execute_tool_impl behind the read-only result cache: identical read-only calls within
    their TTL reuse the earlier result (JARVIS_TOOL_CACHE=0 disables); any other tool runs
    normally and then clears the read caches."""
    ttl = READONLY_TOOL_TTLS.get(tool_name)
    if ttl is None:
        try:
            return _execute_tool_impl(tool_name, tool_input, transcript, skip_confirmation)
        finally:
            _invalidate_read_caches()
    if not cache.enabled("tool") or skip_confirmation:
        return _execute_tool_impl(tool_name, tool_input, transcript, skip_confirmation)
    key = cache.stable_hash(
        tool_name, tool_input or {}, cache.normalize_text(transcript) if tool_name in _TRANSCRIPT_KEYED_TOOLS else ""
    )
    hit = _tool_result_cache.get(key)
    if hit is not cache.MISS:
        cache.record("tool", True, tool_name)
        _log_action_audit(tool_name, tool_input or {}, transcript, f"(cached) {hit}")
        return hit
    cache.record("tool", False, tool_name)
    result = _execute_tool_impl(tool_name, tool_input, transcript, skip_confirmation)
    if not _looks_failed(result):
        _tool_result_cache.put(key, result, ttl)
    return result


def _execute_tool_impl(
    tool_name: str, tool_input: dict, transcript: str, skip_confirmation: bool = False
) -> str:
    """Runs one tool call and returns the text to feed back to Claude as its tool_result.
    Every call — successful, failed, or staged for confirmation — is recorded to the
    action_audit table."""
    inp = tool_input or {}
    result = f"Unrecognized tool: {tool_name!r}"
    try:
        if tool_name.startswith("mcp_"):
            result = execute_mcp_tool(tool_name, inp)
        elif tool_name == "open_url":
            url = str(inp.get("url") or "").strip()
            result = f"Opened {url}." if url else "No URL given."
            if url:
                _open_uri(url)
        elif tool_name == "play_media":
            url = str(inp.get("url") or "").strip()
            result = "Opened." if url else "No URL given."
            if url:
                _open_uri(url)
        elif tool_name == "open_app":
            app = str(inp.get("app") or "").strip()
            if app in ALLOWED_APPS:
                _launch_app(app)
                result = f"Opened {app}."
            else:
                result = f"{app!r} is not a known app."
        elif tool_name == "system_action":
            action = str(inp.get("system_action") or "").strip()
            if action in ALLOWED_SYSTEM_ACTIONS:
                _run_system_action(action)
                result = f"Ran system action {action}."
            else:
                result = f"{action!r} is not a known system action."
        elif tool_name == "read_screen":
            text, fix_code = read_screen(transcript)
            result = text or "Couldn't read the screen."
            if fix_code:
                type_text(fix_code)
                result += " (typed the correction at your cursor)"
        elif tool_name == "web_search":
            query = str(inp.get("query") or "").strip()
            result = web_search_and_summarize(transcript, query) or "No results."
        elif tool_name == "type_text":
            text = str(inp.get("text") or "")
            if text:
                type_text(text)
                result = f"Typed {len(text)} characters."
            else:
                result = "No text given."
        elif tool_name == "system_status":
            result = system_status() or "Couldn't read system status."
        elif tool_name == "api_spend":
            try:
                spend_days = int(inp.get("days") or 30)
            except (TypeError, ValueError):
                spend_days = 30
            admin_key = (os.environ.get("ANTHROPIC_ADMIN_API_KEY") or "").strip()
            if admin_key:
                result = billing.get_api_spend(admin_key, spend_days)
            else:
                # No Admin API key (individual accounts can't have one): use the local estimate
                # built from every call's logged token usage.
                result = billing.format_local_summary(
                    billing.local_summary(_memory_db_connect, _memory_db_lock)
                )
        elif tool_name == "read_clipboard":
            result = read_clipboard_and_describe(transcript) or "Clipboard is empty."
        elif tool_name == "refactor_clipboard_code":
            explanation, code = refactor_clipboard_code(transcript)
            result = explanation or "Nothing to refactor."
            if code:
                type_text(code)
                try:
                    import pyperclip

                    pyperclip.copy(code)
                except Exception as e:
                    log.warning("Could not copy refactored code to clipboard: %s", e)
                result += " (typed and copied the result)"
        elif tool_name == "click_at":
            x, y = inp.get("x"), inp.get("y")
            if x is not None and y is not None:
                button = str(inp.get("button") or "left").strip().lower()
                clicks = int(inp.get("clicks") or 1)
                click_at(int(x), int(y), button=button, clicks=clicks)
                result = f"Clicked at ({x}, {y})."
            else:
                result = "Missing x/y."
        elif tool_name == "drag_and_drop":
            x, y = inp.get("x"), inp.get("y")
            end_x, end_y = inp.get("end_x"), inp.get("end_y")
            if None not in (x, y, end_x, end_y):
                button = str(inp.get("button") or "left").strip().lower()
                drag_and_drop(int(x), int(y), int(end_x), int(end_y), button=button)
                result = f"Dragged ({x}, {y}) to ({end_x}, {end_y})."
            else:
                result = "Missing coordinates."
        elif tool_name == "scroll_screen":
            amount = inp.get("scroll_amount")
            if amount is not None:
                scroll_screen(int(amount), x=inp.get("x"), y=inp.get("y"))
                result = f"Scrolled {amount}."
            else:
                result = "Missing scroll_amount."
        elif tool_name == "focus_window":
            title = str(inp.get("window_title") or "").strip()
            if title:
                found = focus_window(title)
                result = (
                    f"Focused window matching {title!r}."
                    if found
                    else f"No window matching {title!r} found."
                )
            else:
                result = "Missing window_title."
        elif tool_name == "sleep_mode":
            action = str(inp.get("action") or "").strip().lower()
            if action == "on":
                result = sleep_mode.enable(_run_system_action, speak_text)
            elif action == "off":
                result = sleep_mode.disable()
            elif action == "toggle":
                result = sleep_mode.toggle(_run_system_action, speak_text)
            elif action == "status":
                result = sleep_mode.status()
            else:
                result = f"{action!r} is not a known sleep_mode action."
        elif tool_name == "schedule_sleep_wakeup":
            result = sleep_mode.schedule_wakeup(
                str(inp.get("wake_time") or ""), inp.get("ramp_minutes")
            )
        elif tool_name == "play_ambient_sound":
            result = sleep_mode.play_ambient(str(inp.get("kind") or "rain"))
        elif tool_name == "guided_breathing_exercise":
            for line, pause_s in sleep_mode.guided_breathing_steps():
                speak_text(line)
                if pause_s:
                    time.sleep(pause_s)
            result = "Guided breathing exercise complete."
        elif tool_name == "send_whatsapp_message":
            contact = str(inp.get("contact_name") or "").strip()
            message = str(inp.get("message") or "").strip()
            if contact and message:
                send_whatsapp_message(contact, message)
                result = f"Sent to {contact}."
            else:
                result = "Missing contact_name or message."
        elif tool_name == "scan_large_files":
            result = scan_large_files(
                str(inp.get("root_path") or ""), float(inp.get("min_size_gb") or 2.0)
            )
        elif tool_name == "run_shell":
            command = str(inp.get("command") or "").strip()
            if not command:
                result = "No command given."
            else:
                reason = None if skip_confirmation else _catastrophic_reason(command)
                if reason:
                    if _queue_pending_confirmation("run_shell", {"command": command}, reason):
                        result = (
                            f"That command would {reason} — staged, not run. "
                            'Say "yes" on your next turn to actually run it.'
                        )
                    else:
                        result = "Another confirmation is already pending; ignoring this one."
                else:
                    result = _run_shell_command(command)
        elif tool_name == "run_python":
            code = str(inp.get("code") or "").strip()
            if not code:
                result = "No code given."
            else:
                reason = None if skip_confirmation else _catastrophic_reason(code)
                if reason:
                    if _queue_pending_confirmation("run_python", {"code": code}, reason):
                        result = (
                            f"That code would {reason} — staged, not run. "
                            'Say "yes" on your next turn to actually run it.'
                        )
                    else:
                        result = "Another confirmation is already pending; ignoring this one."
                else:
                    result = _run_python_code(code)
        elif tool_name == "read_file":
            result = _read_file_tool(str(inp.get("path") or ""))
        elif tool_name == "write_file":
            result = _write_file_tool(
                str(inp.get("path") or ""), str(inp.get("content") or ""), bool(inp.get("append"))
            )
        elif tool_name == "http_request":
            result = _http_request_tool(
                str(inp.get("url") or ""),
                str(inp.get("method") or "GET"),
                inp.get("headers"),
                inp.get("body"),
            )
        elif tool_name == "remember_fact":
            result = remember_fact(
                str(inp.get("category") or "fact"),
                str(inp.get("content") or ""),
                inp.get("key"),
            )
        elif tool_name == "recall_facts":
            result = recall_facts(
                str(inp.get("query") or ""), bool(inp.get("include_superseded"))
            )
        elif tool_name == "save_skill":
            schedule = inp.get("schedule")
            result = save_skill(
                str(inp.get("name") or ""),
                str(inp.get("description") or ""),
                str(inp.get("instructions") or ""),
                schedule if isinstance(schedule, dict) else None,
            )
        elif tool_name == "create_reminder":
            result = create_reminder(
                str(inp.get("text") or ""),
                str(inp.get("due_at") or ""),
                inp.get("due_in_minutes"),
                inp.get("repeat_every_minutes"),
                bool(inp.get("urgent")),
            )
        elif tool_name == "list_reminders":
            result = list_reminders(bool(inp.get("include_delivered")))
        elif tool_name == "cancel_reminder":
            rid = inp.get("reminder_id")
            result = cancel_reminder(int(rid)) if rid is not None else "Missing reminder_id."
        elif tool_name == "queue_task":
            result = task_scheduler.queue_task(
                str(inp.get("description") or ""),
                estimate_minutes=inp.get("estimate_minutes"),
                priority=str(inp.get("priority") or "normal"),
                instructions=inp.get("instructions"),
                earliest_start=inp.get("earliest_start"),
                deadline=inp.get("deadline"),
            )
        elif tool_name == "plan_task_queue":
            result = task_scheduler.plan_task_queue(
                busy_intervals=inp.get("busy_intervals"),
                day_start=str(inp.get("day_start") or task_scheduler.DEFAULT_DAY_START),
                day_end=str(inp.get("day_end") or task_scheduler.DEFAULT_DAY_END),
            )
        elif tool_name == "list_task_queue":
            result = task_scheduler.list_task_queue(bool(inp.get("include_done")))
        elif tool_name == "cancel_queued_task":
            tid = inp.get("task_id")
            result = task_scheduler.cancel_task(int(tid)) if tid is not None else "Missing task_id."
        elif tool_name == "update_project_status":
            result = update_project_status(
                str(inp.get("name") or ""),
                str(inp.get("status") or ""),
                str(inp.get("next_step") or ""),
            )
        elif tool_name == "quick_recall":
            result = quick_recall()
        elif tool_name == "set_llm_provider":
            result = set_llm_provider(str(inp.get("provider") or ""))
        elif tool_name == "change_jarvis_code":
            result = _delegate_to_claude_code(str(inp.get("feature") or ""), "")
        elif tool_name == "delegate_to_claude_code":
            result = _delegate_to_claude_code(
                str(inp.get("task") or ""), str(inp.get("repo_path") or "")
            )
        elif tool_name == "delegate_research":
            result = _delegate_research(
                str(inp.get("task") or ""), str(inp.get("output_path") or "")
            )
        elif tool_name == "list_background_tasks":
            result = list_background_tasks(bool(inp.get("include_finished")))
        elif tool_name == "set_plan":
            result = _set_plan(transcript, inp.get("steps") or [])
        elif tool_name == "get_workflow_status":
            result = workflow.get_workflow_status(str(inp.get("path") or ""))
        elif tool_name == "check_project_health":
            result = proactive.check_project_health(str(inp.get("root_path") or ""))
        elif tool_name == "list_watched_folders":
            result = filewatcher.list_watched_folders()
        elif tool_name == "add_watched_folder":
            result = filewatcher.add_watched_folder(str(inp.get("path") or ""))
        elif tool_name == "remove_watched_folder":
            result = filewatcher.remove_watched_folder(str(inp.get("path") or ""))
        elif tool_name == "get_recent_file_events":
            limit = inp.get("limit")
            result = filewatcher.get_recent_file_events(int(limit) if limit else 20)
        elif tool_name == "list_open_windows":
            result = window_control.list_open_windows()
        elif tool_name == "control_window":
            title = str(inp.get("window_title") or "")
            action = str(inp.get("action") or "")
            if action == "minimize":
                result = window_control.minimize_window(title)
            elif action == "maximize":
                result = window_control.maximize_window(title)
            elif action == "restore":
                result = window_control.restore_window(title)
            elif action == "close":
                result = window_control.close_window(title)
            elif action == "snap":
                result = window_control.snap_window(title, str(inp.get("side") or ""))
            elif action == "resize":
                result = window_control.resize_window(
                    title,
                    width=inp.get("width"),
                    height=inp.get("height"),
                    width_percent=inp.get("width_percent"),
                    height_percent=inp.get("height_percent"),
                )
            else:
                result = f"{action!r} is not a known window action."
        elif tool_name == "resize_all_windows":
            result = window_control.resize_all_windows(
                width=inp.get("width"),
                height=inp.get("height"),
                width_percent=inp.get("width_percent"),
                height_percent=inp.get("height_percent"),
            )
        elif tool_name == "arrange_windows":
            result = window_control.arrange_windows(
                list(inp.get("window_titles") or []), str(inp.get("layout") or "side-by-side")
            )
        elif tool_name == "save_window_layout":
            result = window_control.save_layout(
                str(inp.get("name") or ""), inp.get("window_titles")
            )
        elif tool_name == "restore_window_layout":
            result = window_control.restore_layout(str(inp.get("name") or ""))
        elif tool_name == "list_window_layouts":
            result = window_control.list_layouts()
        elif tool_name == "analyze_error":
            result = tech_understanding.format_error_report(
                tech_understanding.parse_error(str(inp.get("error_text") or ""))
            )
        elif tool_name == "analyze_code":
            result = tech_understanding.format_analysis_report(
                tech_understanding.analyze_python_file(str(inp.get("path") or ""))
            )
        elif tool_name == "trace_dependencies":
            result = tech_understanding.trace_dependencies(
                str(inp.get("root_path") or ""), str(inp.get("target") or "")
            )
        elif tool_name == "remember_decision":
            result = memory_enhance.remember_decision(
                str(inp.get("decision") or ""),
                str(inp.get("rationale") or ""),
                str(inp.get("alternatives") or ""),
                str(inp.get("project") or ""),
            )
        elif tool_name == "remember_code_pattern":
            result = memory_enhance.remember_code_pattern(
                str(inp.get("pattern") or ""),
                str(inp.get("language") or ""),
                str(inp.get("example") or ""),
                str(inp.get("note") or ""),
            )
        elif tool_name == "semantic_recall":
            result = memory_enhance.semantic_recall(str(inp.get("query") or ""))
    except Exception as e:
        log.warning("Tool %r raised: %s", tool_name, e)
        result = f"Tool failed: {e}"

    log.info("Tool %s(%r) -> %s", tool_name, inp, (result or "")[:200])
    _log_action_audit(tool_name, inp, transcript, result)
    return result


def run_agent_loop(transcript: str, tone: dict | None = None) -> str:
    """Real observe-act-observe loop: Claude picks tools, sees each result, and decides
    what (if anything) to do next, up to MAX_AGENT_ITERATIONS round trips, before giving a
    final spoken reply. Replaces the old single forced perform_actions tool call.

    tone, if given (see jarvis_voice_tone.analyze_tone), is folded into the system prompt
    for every round trip of this call so the reply's tone/approach can adapt — e.g. terser
    when the user sounds frustrated, more explanatory when curious."""
    if not _llm_configured():
        log.warning("No API key for the active brain (%s) — set it in .env.", _llm_provider())
        return ""

    # Reply cache: only ever populated by turns that used read-only tools exclusively (see the
    # store below), so a hit can only replay an informational answer, never skip an action.
    reply_key = None
    if cache.enabled("reply") and cache.is_self_contained(transcript):
        reply_key = cache.stable_hash(
            cache.normalize_text(transcript), sleep_mode.system_prompt_context_line()
        )
        cached_reply = _reply_cache.get(reply_key)
        cache.record("reply", cached_reply is not cache.MISS, repr(transcript[:40]))
        if cached_reply is not cache.MISS:
            _append_history(transcript, cached_reply)
            return cached_reply

    messages: list[dict] = _history_snapshot() + [{"role": "user", "content": transcript}]
    reply_parts: list[str] = []
    last_tool_result_text = ""  # fallback if Claude ends a turn with only a tool call, no text
    used_tool_names: list[str] = []
    any_tool_failed = False
    tools = AGENT_TOOLS + get_mcp_tool_schemas()
    tone_line = voice_tone.tone_context_line(tone) if tone else ""
    # Built once per command, not per round trip: the volatile block (clock minute) sits
    # before the messages in the cached prefix, so recomputing it mid-loop across a minute
    # rollover would needlessly invalidate the message-level cache.
    system_blocks = build_system_blocks(tone_line)
    cached_tools = _cached_tools(tools)

    for _ in range(MAX_AGENT_ITERATIONS):
        data = _claude_request(
            {
                "model": CLAUDE_MODEL,
                "max_tokens": 1536,
                "system": system_blocks,
                "messages": _messages_with_cache_breakpoint(messages),
                "tools": cached_tools,
            },
            timeout=60,
        )
        if data is None:
            reply = " ".join(reply_parts).strip() or _llm_unavailable_reply()
            _append_history(transcript, reply)
            return reply
        _log_cache_usage(data, "agent loop")

        content = data.get("content", [])
        messages.append({"role": "assistant", "content": content})

        reply_parts.extend(
            b.get("text", "") for b in content if b.get("type") == "text" and b.get("text")
        )

        tool_uses = [b for b in content if b.get("type") == "tool_use"]
        if not tool_uses or data.get("stop_reason") != "tool_use":
            break

        # Every tool_use block above MUST get a matching tool_result, or Anthropic's API
        # rejects the next request with an HTTP 400 ("tool_use ids were found without
        # tool_result blocks") — so an over-the-cap request still gets a (skipped) result
        # rather than being silently dropped from this list.
        tool_results = []
        for i, tu in enumerate(tool_uses):
            if i < MAX_TOOL_CALLS_PER_TURN:
                result_text = _execute_tool(tu.get("name", ""), tu.get("input") or {}, transcript)
            else:
                result_text = "Skipped: too many tool calls requested in a single turn."
            tool_results.append(
                {"type": "tool_result", "tool_use_id": tu.get("id"), "content": result_text}
            )
            last_tool_result_text = result_text
            used_tool_names.append(tu.get("name", ""))
            any_tool_failed = any_tool_failed or _looks_failed(result_text)
        messages.append({"role": "user", "content": tool_results})

    reply = " ".join(p.strip() for p in reply_parts if p.strip())
    if (
        reply_key
        and reply
        and used_tool_names
        and not any_tool_failed
        and all(n in READONLY_TOOL_TTLS for n in used_tool_names)
    ):
        _reply_cache.put(reply_key, reply, min(READONLY_TOOL_TTLS[n] for n in used_tool_names))
    if not reply and last_tool_result_text:
        # Observed live: Claude sometimes ends a turn with only a tool call and no spoken text
        # at all — most consequentially for a staged catastrophic confirmation (run_shell/
        # run_python's "staged, not run, say yes" result) and a multi-tool task that exhausts
        # MAX_AGENT_ITERATIONS before ever narrating a summary. The system prompt already says
        # to always give a short spoken reply, but that's not 100% reliable model behavior —
        # silence is worse than just surfacing the last tool's own result text instead.
        reply = last_tool_result_text
    _append_history(transcript, reply)
    return reply


def handle_text_command(
    transcript: str, reply_sink=None, tone: dict | None = None, source: str = "text"
) -> None:
    """Runs one already-transcribed command (typed or spoken) through the confirmation
    gate and the Claude tool loop, then speaks the reply. Shared by handle_voice_command
    (after Whisper) and the typed-command hotkey (which skips transcription entirely).

    source labels this command for the dashboard's Sessions panel ("voice"/"text"/"phone"/
    "dashboard") — purely descriptive, never changes behavior.

    reply_sink, if given, marks this as a phone- or dashboard-originated command: instead of
    speaking the full reply locally, Jarvis sends the *actual* answer only to reply_sink — the
    room and the phone/dashboard get different things, on purpose, instead of reading the whole
    answer out loud into an empty room. Phone additionally gets a brief spoken "Message
    received." ack up front, since nobody's looking at a screen for it; the dashboard already
    shows the command arrive live, so it skips that ack.

    tone, if given, comes from handle_voice_command (text + raw audio, so it can factor in
    loudness/pace). Callers without audio (typed hotkey, phone) leave it unset and this
    falls back to a text-only read of the same transcript."""
    if not transcript:
        return

    # Session context: the user talking to Jarvis is itself proof they're available, so
    # deliver anything queued earlier right now instead of leaving it stuck until the next
    # health check or scheduled skill happens to notice.
    flush_pending_notifications()

    if reply_sink and source != "dashboard":
        speak_text("Message received.")

    with _pending_action_lock:
        pending = _pending_action
    if pending is not None:
        if _is_confirmation_yes(transcript):
            step = _take_pending_action()
            if step:
                _execute_confirmed_action(step, reply_sink)
            dashboard.notify({"type": "pending_action", "data": None})
            return
        _take_pending_action()
        dashboard.notify({"type": "pending_action", "data": None})
        log.info(
            "Dropped pending confirmation (%r); treating this as a new command.",
            pending.get("tool_name"),
        )

    if tone is None:
        tone = voice_tone.analyze_tone(transcript)

    record_recent_task(transcript)
    # Dashboard session bookkeeping: best-effort, never raises (see jarvis_dashboard.py) — a
    # failure here must never affect the actual command below.
    session_id = dashboard.start_session(source, transcript)
    dashboard.notify(
        {"type": "session_start", "data": {"id": session_id, "source": source, "transcript": transcript}}
    )
    try:
        reply = run_agent_loop(transcript, tone=tone)
    except Exception:
        dashboard.end_session(session_id, "failed", None)
        dashboard.notify({"type": "session_end", "data": {"id": session_id, "status": "failed"}})
        raise
    dashboard.end_session(session_id, "done", reply)
    dashboard.notify({"type": "session_end", "data": {"id": session_id, "status": "done", "reply": reply}})
    if reply:
        if reply_sink:
            reply_sink(reply)
        # Phone is remote — the room shouldn't hear the full answer read into an empty space,
        # so it gets reply_sink only (plus the "Message received." ack above). Dashboard is
        # different: the user is normally sitting right there, typing into a box they can see —
        # muting speech just because they used the dashboard instead of push-to-talk surprised
        # the user in practice ("it's not even talking anymore"), so dashboard gets *both* the
        # text (already in the dashboard via dashboard.end_session above) and spoken audio.
        if reply_sink is None or source == "dashboard":
            # Dashboard/audit trail always get the full `reply` above — only what actually
            # comes out of the speakers is shortened and stripped of full file paths.
            speak_text(_collapse_paths_for_speech(_summarize_for_speech(reply)))


def handle_voice_command(audio: np.ndarray, sample_rate: int) -> None:
    if audio.size == 0:
        return
    try:
        transcript = transcribe_pcm(audio, sample_rate)
    except Exception as e:
        log.warning("Transcription failed: %s", e)
        return
    if not transcript:
        log.info("Push-to-talk: heard nothing.")
        return
    tone = voice_tone.analyze_tone(transcript, audio, sample_rate)
    if tone.get("tone") != "neutral":
        log.info("Voice tone: %s (confidence %.0f%%).", tone["tone"], tone["confidence"] * 100)
    log.info("Heard: %r", transcript)
    handle_text_command(transcript, tone=tone, source="voice")


_text_hotkey_popup_open = threading.Event()


def _show_text_command_popup() -> None:
    """Small always-on-top Tkinter input box: Enter submits and runs the typed text through
    the same agent loop as a voice command, Escape/closing the window cancels. Runs its own
    Tk mainloop on this (dedicated, short-lived) thread — fine on Windows as long as no other
    Tk root is ever alive on another thread at the same time, which _text_hotkey_popup_open
    guarantees by refusing to open a second box while one is already up."""
    import tkinter as tk

    typed = {"text": None}

    def submit(_event=None) -> None:
        typed["text"] = entry.get()
        root.destroy()

    def cancel(_event=None) -> None:
        typed["text"] = None
        root.destroy()

    root = tk.Tk()
    root.title("Jarvis")
    root.attributes("-topmost", True)
    try:
        root.overrideredirect(True)  # borderless — just the input strip, no title bar
    except tk.TclError:
        pass
    width, height = 480, 44
    screen_w = root.winfo_screenwidth()
    root.geometry(f"{width}x{height}+{(screen_w - width) // 2}+80")

    entry = tk.Entry(root, font=("Segoe UI", 14))
    entry.insert(0, "")
    entry.pack(fill="both", expand=True, padx=8, pady=8)
    entry.bind("<Return>", submit)
    entry.bind("<Escape>", cancel)
    entry.bind("<FocusOut>", cancel)
    root.protocol("WM_DELETE_WINDOW", cancel)
    root.lift()
    root.focus_force()
    entry.focus_set()

    root.mainloop()

    _text_hotkey_popup_open.clear()
    text = (typed["text"] or "").strip()
    if not text:
        log.info("Text command box closed with no input.")
        return
    log.info("Typed command: %r", text)
    threading.Thread(target=handle_text_command, args=(text,), daemon=True).start()


def _text_hotkey_watch_loop() -> None:
    """Polls JARVIS_TEXT_HOTKEY_KEY; once it's been held continuously for
    JARVIS_TEXT_HOTKEY_HOLD_S seconds, opens the typed-command popup (once per hold — the
    key must be released and pressed again to reopen it)."""
    held_since: float | None = None
    fired_this_hold = False
    poll_s = 0.05
    while True:
        time.sleep(poll_s)
        pressed = _keyboard_is_pressed(JARVIS_TEXT_HOTKEY_KEY)
        if not pressed:
            held_since = None
            fired_this_hold = False
            continue
        if held_since is None:
            held_since = time.monotonic()
            continue
        if fired_this_hold:
            continue
        if (time.monotonic() - held_since) < JARVIS_TEXT_HOTKEY_HOLD_S:
            continue
        fired_this_hold = True
        if _text_hotkey_popup_open.is_set():
            continue
        _text_hotkey_popup_open.set()
        threading.Thread(target=_show_text_command_popup, daemon=True).start()


def _chrome_executable() -> str | None:
    if sys.platform == "win32":
        for base in (
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        ):
            if not base:
                continue
            p = os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")
            if os.path.isfile(p):
                return p
    return shutil.which("google-chrome") or shutil.which("chrome")


def _primary_screen_size() -> tuple[int, int]:
    if sys.platform == "win32":
        import ctypes

        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    return (1920, 1080)


def _cursor_executable() -> str | None:
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        for sub in ("Programs\\cursor\\Cursor.exe", "Programs\\Cursor\\Cursor.exe"):
            if local:
                p = os.path.join(local, *sub.split("\\"))
                if os.path.isfile(p):
                    return p
    return shutil.which("cursor")


def _cursor_largest_main_hwnd_win32() -> int | None:
    """Largest top-level Cursor.exe window (visible or minimized)."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    GW_OWNER = 4
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    candidates: list[tuple[int, wintypes.HWND]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd: wintypes.HWND, _lp: wintypes.LPARAM) -> bool:
        if user32.GetWindow(hwnd, GW_OWNER):
            return True
        if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        if not user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return True
        hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not hproc:
            return True
        try:
            buf = ctypes.create_unicode_buffer(4096)
            sz = wintypes.DWORD(len(buf))
            if not kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(sz)):
                return True
            exe_path = buf.value
        finally:
            kernel32.CloseHandle(hproc)
        if os.path.basename(exe_path).lower() != "cursor.exe":
            return True
        r = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return True
        w, h = r.right - r.left, r.bottom - r.top
        if w < 200 or h < 200:
            return True
        candidates.append((w * h, hwnd))
        return True

    user32.EnumWindows(_enum, 0)
    if not candidates:
        return None
    return int(max(candidates, key=lambda t: t[0])[1])


def _cursor_foreground_hwnd_win32(hwnd: int) -> None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    user32.ShowWindow(hwnd, SW_RESTORE)
    fg = user32.GetForegroundWindow()
    tid_tgt = user32.GetWindowThreadProcessId(hwnd, None)
    tid_fg = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    if tid_fg and tid_tgt:
        user32.AttachThreadInput(tid_fg, tid_tgt, True)
    user32.SetForegroundWindow(hwnd)
    if tid_fg and tid_tgt:
        user32.AttachThreadInput(tid_fg, tid_tgt, False)


def _cursor_send_f11_fullscreen_win32(hwnd: int) -> None:
    """F11 toggles Zen/fullscreen in Cursor (Electron)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    KEYEVENTF_KEYUP = 0x0002
    VK_F11 = 0x7A
    _cursor_foreground_hwnd_win32(hwnd)
    user32.keybd_event(VK_F11, 0, 0, 0)
    user32.keybd_event(VK_F11, 0, KEYEVENTF_KEYUP, 0)


def _focus_existing_cursor_window_win32() -> bool:
    """Bring an existing Cursor.exe main window to the foreground (no new process)."""
    if sys.platform != "win32":
        return False
    hwnd = _cursor_largest_main_hwnd_win32()
    if hwnd is None:
        return False
    _cursor_foreground_hwnd_win32(hwnd)
    return True


def open_cursor_window() -> None:
    if not FOCUS_EXISTING_CURSOR_WINDOW and not OPEN_NEW_CURSOR_WINDOW:
        return
    exe = _cursor_executable()
    if not exe:
        log.warning(
            "Could not find Cursor (install app or add the `cursor` command to PATH)."
        )
        return
    popen_kw: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        if FOCUS_EXISTING_CURSOR_WINDOW:
            focused = (
                sys.platform == "win32" and _focus_existing_cursor_window_win32()
            )
            if not focused:
                subprocess.Popen([exe], **popen_kw)
        if OPEN_NEW_CURSOR_WINDOW:
            subprocess.Popen([exe, "-n"], **popen_kw)
    except OSError as e:
        log.warning("Could not start or focus Cursor: %s", e)
        return
    if sys.platform == "win32" and CURSOR_OPEN_FULLSCREEN:
        time.sleep(0.5)
        hwnd = _cursor_largest_main_hwnd_win32()
        if hwnd is not None:
            _cursor_send_f11_fullscreen_win32(hwnd)
        else:
            log.warning("Cursor fullscreen: no Cursor window found to send F11.")


def main() -> int:
    blocksize = block_samples()
    ptt_active = False
    ptt_buffer: list[np.ndarray] = []

    if FOCUS_EXISTING_CURSOR_WINDOW:
        log.info(
            "Opening Cursor will foreground an existing instance (Windows API); "
            "falls back to launching it if none is running."
        )
    if OPEN_NEW_CURSOR_WINDOW:
        log.info("Opening Cursor will also open a new window (-n).")
    if CURSOR_OPEN_FULLSCREEN and sys.platform == "win32":
        log.info("Cursor will be sent F11 for fullscreen after focus/launch.")
    _preload_piper_async()
    if JARVIS_PTT_ENABLED:
        log.info(
            "Push-to-talk: hold '%s' and speak, release to run the command "
            "(Whisper=%s, Claude model=%s). Preloading Whisper in the background...",
            JARVIS_PTT_KEY,
            WHISPER_MODEL_SIZE,
            CLAUDE_MODEL,
        )
        _preload_whisper_async()

    if JARVIS_TEXT_HOTKEY_ENABLED:
        log.info(
            "Typed commands: hold '%s' for %.1fs to open a text box.",
            JARVIS_TEXT_HOTKEY_KEY,
            JARVIS_TEXT_HOTKEY_HOLD_S,
        )
        threading.Thread(target=_text_hotkey_watch_loop, daemon=True).start()

    if NTFY_TOPIC:
        log.info(
            "Phone (ntfy): pushing notifications to topic %r; commands read from %r.",
            NTFY_TOPIC, f"{NTFY_TOPIC}-cmd",
        )
        threading.Thread(target=_ntfy_listen_loop, daemon=True, name="ntfy-listener").start()
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        log.info("Phone (Telegram): pushing notifications and listening for chat %s.", TELEGRAM_CHAT_ID)
        threading.Thread(target=_telegram_listen_loop, daemon=True, name="telegram-listener").start()

    if JARVIS_DASHBOARD_ENABLED:
        # Double-checked (Phase 0/2): localhost-only, no auth (user-accepted for a single-user
        # local machine). Approve/Reject/Stop are wired starting Phase 2 — Approve calls the
        # *same* _execute_confirmed_action used by the spoken "yes" (see
        # _dashboard_approve_pending's docstring); the user explicitly accepted (2026-09-18,
        # recorded in CLAUDE.md) that this may one-click-confirm catastrophic-tier actions,
        # on condition that the click only happens from the frontend's mandatory review/detail
        # view. Stop only ever kills a process Jarvis itself spawned; never touches the gate.
        # A startup failure (e.g. fastapi/uvicorn not installed) must never take Jarvis's core
        # loop down with it, hence the broad except.
        try:
            # Warm the fastapi/uvicorn import *here*, synchronously, before the dashboard
            # thread exists — observed live: CPython's per-module import lock can spuriously
            # deadlock-detect when two threads do their first import of unrelated heavy
            # packages at nearly the same instant (here: dashboard-server's first `import
            # uvicorn` racing Whisper/Piper loading on other startup threads), permanently
            # crashing whichever thread loses. Importing once on the main thread means the
            # background thread's later `import uvicorn` just hits sys.modules — no lock, no
            # race, regardless of what else is importing at that moment.
            try:
                import fastapi  # noqa: F401
                import uvicorn  # noqa: F401
            except ImportError:
                pass  # dashboard.start() logs its own warning and no-ops if truly missing
            threading.Thread(
                target=dashboard.start,
                kwargs=dict(
                    port=JARVIS_DASHBOARD_PORT,
                    get_pending=_dashboard_get_pending,
                    approve_pending=_dashboard_approve_pending,
                    reject_pending=_dashboard_reject_pending,
                    kill_background_task=_dashboard_kill_background_task,
                    get_system_status=get_system_status_report,
                    get_services=_dashboard_get_services_status,
                    get_daily=_dashboard_get_daily_items,
                    get_usage=_dashboard_get_usage,
                    get_sleep=_dashboard_get_sleep,
                    get_llm=_llm_status,
                    set_llm=set_llm_provider,
                    # Phase 4: a dashboard-typed command is just a 4th input surface alongside
                    # voice/text-hotkey/phone — it goes through the exact same
                    # handle_text_command pipeline (run_agent_loop, _execute_tool, and the
                    # confirmation gate for run_shell/run_python), never skip_confirmation.
                    run_command=lambda text, sink: handle_text_command(
                        text, reply_sink=sink, source="dashboard"
                    ),
                ),
                daemon=True,
                name="dashboard-server",
            ).start()
            log.info(
                "Dashboard: starting on http://127.0.0.1:%d (localhost-only).", JARVIS_DASHBOARD_PORT
            )
            if JARVIS_DASHBOARD_AUTO_OPEN:
                threading.Timer(
                    1.5, lambda: webbrowser.open(f"http://127.0.0.1:{JARVIS_DASHBOARD_PORT}")
                ).start()
        except Exception as e:
            log.warning("Dashboard failed to start; Jarvis continues without it: %s", e)

    _preload_mcp_async()
    start_prompt_cache_warmup()
    _start_scheduler()
    _start_health_monitor()
    filewatcher.start_watching(
        notifier=lambda text, urgent: queue_or_deliver_notification(text, urgent=urgent)
    )
    log.info("File watcher running (%s, poll every %ds).",
              ", ".join(filewatcher.watcher.list_paths()), filewatcher.watcher.poll_interval)
    log.info(
        "Proactive system health monitor running every %d minutes (suggestions logged to %s).",
        HEALTH_CHECK_INTERVAL_S // 60,
        PROACTIVE_SUGGESTIONS_LOG_PATH,
    )

    input_idx = _choose_input_device(blocksize)

    try:
        with sd.InputStream(
            device=input_idx,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=blocksize,
        ) as stream:
            while True:
                data, overflowed = stream.read(blocksize)
                if overflowed:
                    log.warning("Input overflow; try a larger BLOCK_MS")

                if jarvis_speaking.is_set():
                    # Don't let the mic hear Jarvis's own voice and mistake it for a command.
                    continue

                if JARVIS_PTT_ENABLED:
                    pressed = _keyboard_is_pressed(JARVIS_PTT_KEY)
                    if pressed and not ptt_active:
                        ptt_active = True
                        ptt_buffer = []
                        log.info("Push-to-talk: listening...")
                    if ptt_active:
                        ptt_buffer.append(data.copy())
                        if not pressed:
                            ptt_active = False
                            audio = (
                                np.concatenate(ptt_buffer, axis=0)
                                if ptt_buffer
                                else np.empty((0, CHANNELS), dtype=np.float32)
                            )
                            ptt_buffer = []
                            log.info(
                                "Push-to-talk: released (%.2fs), transcribing...",
                                audio.shape[0] / SAMPLE_RATE,
                            )
                            threading.Thread(
                                target=handle_voice_command,
                                args=(audio, SAMPLE_RATE),
                                daemon=True,
                            ).start()

    except KeyboardInterrupt:
        log.info("Stopped.")
        return 0
    except sd.PortAudioError as e:
        log.error("Audio error: %s", e)
        log.error("If PortAudio fails, install/repair drivers or try another SAMPLE_RATE.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
