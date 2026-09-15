#!/usr/bin/env python3
"""
Desktop clap listener: reads the default microphone and logs when two loud transients
(a double clap) are detected within a short time window.

Run:
  python -m pip install -r requirements.txt
  python clap_listen.py

Tuning (constants below):
  SAMPLE_RATE   — usually 44100 or 48000; match your device if needed.
  BLOCK_MS      — analysis window size; smaller = snappier, noisier.
  SPIKE_RATIO   — how many times louder than the noise floor counts as a clap;
                    raise if false triggers; lower if claps are missed.
  COOLDOWN_S    — minimum seconds between double-clap logs (debounce).
  MIN_DOUBLE_GAP_S / MAX_DOUBLE_GAP_S — allowed time between the two claps.
  RETRIGGER_RATIO — audio must fall below threshold * this before another hit counts.
  NOISE_FLOOR_ALPHA — closer to 1 = slower baseline adaptation to room noise.
  MIN_RMS       — ignore spikes below this absolute level (float audio ~ [-1, 1]).
  FOCUS_EXISTING_CURSOR_ON_DOUBLE_CLAP — if True, launch Cursor without -n (reuse / focus existing instance).
  OPEN_NEW_CURSOR_ON_DOUBLE_CLAP — if True, also launch Cursor with -n (extra new window; runs after focus launch if both).
  CURSOR_OPEN_FULLSCREEN — Windows: after focus/launch, send F11 to enter Cursor/VS Code-style fullscreen (toggle off with F11).
  JARVIS_WELCOME_* — TTS on double clap (Piper, local/offline/free). Configure via PIPER_VOICE
    in the environment or a `.env` file next to this script (default en_US-lessac-medium).
    With JARVIS_WELCOME_CACHE_ENABLED, audio is saved under `.cache/jarvis_welcome/` (WAV) and
    replayed when phrase + voice + model + format match—no repeat API call. Delete that folder
    or set JARVIS_WELCOME_CACHE_ENABLED=False to force a fresh fetch.
  The welcome sequence runs only once per process. The assistant speaks in the background so Cursor
    opens without waiting for playback to finish (restart the script to run again).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
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
from zoneinfo import ZoneInfo
import webbrowser
from pathlib import Path

from dotenv import load_dotenv
import numpy as np
import sounddevice as sd

# --- tuning knobs -----------------------------------------------------------
SAMPLE_RATE = 44100
BLOCK_MS = 40
CHANNELS = 1

SPIKE_RATIO = 9.0
COOLDOWN_S = 0.45
MIN_DOUBLE_GAP_S = 0.05
MAX_DOUBLE_GAP_S = 0.35
RETRIGGER_RATIO = 0.55
NOISE_FLOOR_ALPHA = 0.992
MIN_RMS = 0.012
QUIET_GATE_MULT = 2.2  # update noise floor only when below floor * this
# Startup mic probe: if default input RMS stays below this, scan for a louder device.
INPUT_PROBE_S = 0.5
INPUT_SILENT_RMS = 0.001

# Cursor: focus existing instance (no -n). Set OPEN_NEW_CURSOR_ON_DOUBLE_CLAP for a new window as well.
FOCUS_EXISTING_CURSOR_ON_DOUBLE_CLAP = True
OPEN_NEW_CURSOR_ON_DOUBLE_CLAP = False
CURSOR_OPEN_FULLSCREEN = False

JARVIS_WELCOME_ENABLED = True
# Triple clap (3 in a row): normal mode.
JARVIS_WELCOME_PHRASE = "Hey boss, how can I help you today?"
# Double clap: serious mode — a different greeting, then an immediate weather + time report.
JARVIS_SERIOUS_MODE_PHRASE = "Serious mode activated. I'm in serious mode right now."
JARVIS_SERIOUS_MODE_LOCATION = "Ganmo, Ilorin, Kwara State, Nigeria"
# wttr.in doesn't have a "Ganmo" entry; Ilorin (the nearest city, a few km away) is the
# closest queryable location and shares the same weather/timezone.
JARVIS_SERIOUS_MODE_WEATHER_QUERY = "Ilorin,Nigeria"
JARVIS_SERIOUS_MODE_TIMEZONE = "Africa/Lagos"  # all of Nigeria uses this one timezone
# Serious mode also opens two Opera GX windows split-screen on the primary display.
JARVIS_SERIOUS_MODE_OPERA_LEFT_URL = "https://animeheaven.me"
JARVIS_SERIOUS_MODE_OPERA_RIGHT_URL = "https://www.youtube.com"
# Save Piper PCM as WAV under .cache/jarvis_welcome/; replay skips re-synthesis when unchanged.
JARVIS_WELCOME_CACHE_ENABLED = True

load_dotenv(Path(__file__).resolve().parent / ".env")

# Push-to-talk voice commands: hold JARVIS_PTT_KEY, speak, release. Local Whisper
# transcribes, Claude decides zero or more actions from a fixed safe set, Piper speaks the reply.
JARVIS_PTT_ENABLED = True
JARVIS_PTT_KEY = (os.environ.get("JARVIS_PTT_KEY") or "left shift").strip() or "left shift"
WHISPER_MODEL_SIZE = (os.environ.get("WHISPER_MODEL_SIZE") or "base").strip() or "base"
CLAUDE_MODEL = (
    os.environ.get("CLAUDE_MODEL") or "claude-haiku-4-5-20251001"
).strip() or "claude-haiku-4-5-20251001"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("clap_listen")

# Set while any Jarvis TTS audio is actually playing through the speakers. The main loop
# skips clap/PTT detection while this is set, so the mic can't hear Jarvis's own voice
# bleed through and misread it as a new clap or command (an audio feedback loop that would
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
    return True


def _take_pending_action() -> dict | None:
    global _pending_action
    with _pending_action_lock:
        step, _pending_action = _pending_action, None
    return step


def _execute_confirmed_action(step: dict) -> None:
    tool_name = str(step.get("tool_name") or "")
    tool_input = step.get("tool_input") or {}
    log.info("Confirmed by user: executing staged %s(%r)", tool_name, tool_input)
    result = _execute_tool(tool_name, tool_input, transcript="", skip_confirmation=True)
    speak_text(result or "Done.")


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


# --- text-to-speech: local, offline, free (Piper) --------------------------
PIPER_VOICE = (os.environ.get("PIPER_VOICE") or "en_US-lessac-medium").strip() or "en_US-lessac-medium"

_piper_voice_obj = None
_piper_lock = threading.Lock()


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


def _piper_synthesize(text: str) -> tuple[bytes, int]:
    voice = _get_piper_voice()
    chunks = list(voice.synthesize(text))
    if not chunks:
        return b"", voice.config.sample_rate
    raw = b"".join(ch.audio_int16_bytes for ch in chunks)
    return raw, chunks[0].sample_rate


def _jarvis_welcome_cache_dir() -> Path:
    base = Path(__file__).resolve().parent
    override = (os.environ.get("JARVIS_WELCOME_CACHE_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return base / ".cache" / "jarvis_welcome"


def _jarvis_welcome_cache_path(
    text: str, voice_id: str, model_id: str, sample_rate: int
) -> Path:
    key = f"{text}|{voice_id}|{model_id}|{sample_rate}".encode()
    digest = hashlib.sha256(key).hexdigest()[:24]
    return _jarvis_welcome_cache_dir() / f"{digest}.wav"


def _play_pcm_wav_file(path: Path) -> bool:
    try:
        with wave.open(str(path), "rb") as wf:
            ch = wf.getnchannels()
            sw = wf.getsampwidth()
            rate = wf.getframerate()
            if ch != 1 or sw != 2:
                log.warning("Unsupported cached WAV (channels=%s, width=%s).", ch, sw)
                return False
            raw = wf.readframes(wf.getnframes())
    except (OSError, wave.Error) as e:
        log.warning("Could not read cached welcome audio: %s", e)
        return False
    if not raw:
        return False
    pcm_i16 = np.frombuffer(raw, dtype=np.int16)
    pcm_f = pcm_i16.astype(np.float32) / 32768.0
    with _playback_lock:
        jarvis_speaking.set()
        try:
            sd.play(pcm_f, rate)
            sd.wait()
        except Exception as e:
            log.warning("Could not play cached welcome audio: %s", e)
            return False
        finally:
            jarvis_speaking.clear()
    return True


def _save_pcm_wav_file(path: Path, pcm_bytes: bytes, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with wave.open(str(tmp), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        tmp.replace(path)
    except OSError:
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
        raise


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
    """Speak arbitrary dynamic text (voice-command replies) — not cached, unlike the welcome line."""
    t = _sanitize_for_speech(text)
    if not t:
        return
    try:
        raw, sample_rate = _piper_synthesize(t)
    except Exception as e:
        log.warning("Piper TTS failed: %s", e)
        return
    if not raw:
        log.warning("Piper returned empty audio.")
        return
    _play_pcm_bytes(raw, sample_rate)


def speak_cached_phrase(phrase: str) -> None:
    """Speak a fixed phrase (a clap-triggered greeting), using the on-disk WAV cache — keyed
    on the phrase text itself — to skip repeat synthesis for phrases said more than once."""
    if not JARVIS_WELCOME_ENABLED or not phrase.strip():
        return
    text = phrase.strip()
    pcm_rate = _get_piper_voice().config.sample_rate

    cache_path = _jarvis_welcome_cache_path(text, PIPER_VOICE, "piper", pcm_rate)
    if JARVIS_WELCOME_CACHE_ENABLED and cache_path.is_file():
        log.info("Playing cached phrase: %s", cache_path)
        if _play_pcm_wav_file(cache_path):
            return
        log.warning("Cache miss after read failure; re-synthesizing with Piper.")

    try:
        raw, sample_rate = _piper_synthesize(text)
    except Exception as e:
        log.warning("Piper TTS failed: %s", e)
        return
    if not raw:
        log.warning("Piper returned empty audio.")
        return
    if JARVIS_WELCOME_CACHE_ENABLED:
        try:
            _save_pcm_wav_file(cache_path, raw, sample_rate)
            log.info("Saved phrase audio to cache: %s", cache_path)
        except OSError as e:
            log.warning("Could not save phrase cache: %s", e)
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
ALLOWED_MODES = ("serious", "normal")
MEMORY_FACT_CATEGORIES = ("preference", "decision", "directive", "goal", "relationship", "fact")
MAX_TOOL_CALLS_PER_TURN = 5  # cap on parallel tool calls Claude can request in one turn
MAX_AGENT_ITERATIONS = 6  # cap on observe-act-observe round trips per voice command
CONVERSATION_HISTORY_MAX_TURNS = 6  # 3 user+assistant exchanges

AGENT_SYSTEM_PROMPT = """You are Jarvis, a desktop voice assistant with real tool access to this \
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
spoken summary of the outcome; don't narrate tool mechanics.

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

The `gh` CLI is installed and already authenticated on this machine — for GitHub issues, PRs, \
repos, or notifications, run `gh` commands via run_shell rather than guessing at a raw API call. \
Any tools named "mcp_<server>_..." below are live integrations (Gmail, Calendar, Slack, etc., \
depending on what's configured) reached the same way Claude Code reaches its own integrations — \
use them directly like any other tool.

For actual software development work — writing code, fixing a bug, adding a feature, running a \
test suite — use delegate_to_claude_code instead of doing it yourself with run_shell/write_file. \
It hands the task to a full Claude Code agent with a much larger, purpose-built toolset and will \
do a meaningfully better job on anything beyond a one-liner. It runs synchronously and can take \
several minutes; say so in your reply rather than leaving the user wondering about the pause.

One narrow tier of action stays gated: shutting down/restarting/signing out the machine, \
reformatting or repartitioning a disk, and recursively wiping an entire drive or the user's whole \
profile. If a run_shell or run_python call would do one of those, it gets staged instead of run — \
say what you're about to do and that the user needs to say "yes" on their next turn to actually run \
it. Every other action, including individual file deletes, sending messages, and clicking, \
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
        "name": "switch_mode",
        "description": "Switch Jarvis between serious mode and normal mode, replaying that mode's greeting.",
        "input_schema": {
            "type": "object",
            "properties": {"mode": {"type": "string", "enum": list(ALLOWED_MODES)}},
            "required": ["mode"],
        },
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
        "name": "delegate_to_claude_code",
        "description": (
            "Delegate a real software development task — writing code, fixing a bug, adding a "
            "feature, refactoring, running tests — to a full headless Claude Code agent, "
            "instead of doing it yourself with run_shell/write_file. Claude Code has a far "
            "larger toolset built for exactly this (repo-wide search, diff-aware editing, "
            "git/test awareness) and will do a better job on anything beyond a one-off command. "
            "This runs synchronously and can take several minutes for a real task — mention "
            "that in your reply so the user isn't left wondering about the pause. Reach for "
            "this for actual coding/repo work; use run_shell/run_python directly for quick "
            "one-liners."
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
                        "absolute path to the project/repo to work in; omit to default to "
                        "this Jarvis project's own folder"
                    ),
                },
            },
            "required": ["task"],
        },
    },
]


CLAUDE_UNAVAILABLE_REPLY = "Sorry, I couldn't reach Claude just now."
CLAUDE_MAX_ATTEMPTS = 3
CLAUDE_RETRY_DELAY_S = 1.5


def _claude_request(body: dict, timeout: int) -> dict | None:
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
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            transient = e.code in (429, 500, 502, 503, 504, 529)
            try:
                detail = e.read().decode(errors="replace")[:1000]
            except Exception:
                detail = "(could not read response body)"
            log.warning("Claude request failed (attempt %d): HTTP %d: %s", attempt, e.code, detail)
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


# --- persistent memory: SQLite-backed chat history + user profile facts --------------
# Long-term storage across restarts, replacing the old RAM-only conversation_history list.
_memory_db_lock = threading.Lock()


def _memory_db_path() -> Path:
    override = (os.environ.get("JARVIS_MEMORY_DB_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent / "jarvis_memory.db"


def _memory_db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_memory_db_path())
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
    return conn


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


# --- skills: user- or Claude-authored procedures dropped into skills/*.json, loaded fresh on ---
# --- every system prompt build (not cached) so a new file takes effect with no restart and no ---
# --- code edit — the "skill library" layer, distinct from the built-in tools above. ---
SKILLS_DIR_NAME = "skills"
MAX_SKILLS_CONTEXT_CHARS = 6000


def _skills_dir() -> Path:
    override = (os.environ.get("JARVIS_SKILLS_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent / SKILLS_DIR_NAME


def _load_skills() -> list[dict]:
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
    synthetic_transcript = (
        f"(This is a scheduled, proactive run of your \"{skill['name']}\" skill — the user "
        f"didn't just ask for this out loud, act on the schedule instead.) {skill['instructions']}"
    )
    try:
        reply = run_agent_loop(synthetic_transcript)
        if reply:
            speak_text(reply)
    except Exception as e:
        log.warning("Scheduled skill %r failed: %s", skill["name"], e)
    finally:
        _set_last_skill_run(skill["name"], datetime.now())


def _scheduler_loop() -> None:
    while True:
        try:
            now = datetime.now()
            for skill in _load_skills():
                if _skill_is_due(skill, now):
                    _run_scheduled_skill(skill)
        except Exception as e:
            log.warning("Scheduler tick failed: %s", e)
        time.sleep(SCHEDULER_TICK_S)


def _start_scheduler() -> None:
    threading.Thread(target=_scheduler_loop, daemon=True, name="skill-scheduler").start()


# --- MCP client: connects to servers listed in mcp_servers.json (one-time, lazy) and merges ---
# --- their tools into the agent loop's tool list, namespaced "mcp_<server>_<tool>" — the same ---
# --- protocol/tool-discovery mechanism Claude Code itself uses for integrations, so adding one ---
# --- (Gmail, Calendar, Slack, ...) is a config entry, not a code change. A server that fails to ---
# --- connect (missing credentials, package not found, offline) is skipped with a warning; the ---
# --- built-in tools and the rest of Jarvis keep working regardless. ---
MCP_TOOL_CALL_TIMEOUT_S = 60
MCP_STARTUP_TIMEOUT_S = 60

_mcp_lock = threading.Lock()
_mcp_loop: asyncio.AbstractEventLoop | None = None
_mcp_started = False
_mcp_handles: dict[str, "_McpServerHandle"] = {}  # server name -> _McpServerHandle
_mcp_tool_index: dict[str, tuple[str, str]] = {}  # exposed tool name -> (server name, real tool name)
_mcp_tool_schemas: list[dict] = []


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


async def _mcp_connect_all_async(configs: dict) -> None:
    for server_name, cfg in configs.items():
        # Top-level non-server keys (e.g. a "_comment" string in the example config) or any
        # other malformed entry must not abort every server after it in iteration order.
        try:
            if server_name.startswith("_") or not isinstance(cfg, dict):
                continue
            command = str(cfg.get("command") or "").strip()
            if not command:
                log.warning("MCP server %r has no \"command\"; skipping.", server_name)
                continue
            handle = _McpServerHandle()
            _mcp_handles[server_name] = handle
            asyncio.get_running_loop().create_task(_mcp_server_supervisor(cfg, handle))
            try:
                await asyncio.wait_for(handle.ready.wait(), timeout=MCP_STARTUP_TIMEOUT_S)
            except asyncio.TimeoutError:
                log.warning("MCP server %r timed out connecting.", server_name)
                continue
            if handle.error:
                log.warning("Failed to connect MCP server %r: %s", server_name, handle.error)
                continue
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
    """Connects every configured MCP server exactly once, lazily, on first use — safe to call
    on every request. If the `mcp` package isn't installed or no servers are configured, this
    is a silent no-op; MCP is additive, never required."""
    global _mcp_started
    with _mcp_lock:
        if _mcp_started:
            return
        _mcp_started = True
    configs = _load_mcp_server_configs()
    if not configs:
        return
    try:
        import mcp  # noqa: F401  (import check only — real usage is inside _mcp_connect_all_async)
    except ImportError:
        log.warning("mcp_servers.json is configured but the `mcp` package isn't installed (pip install mcp).")
        return
    try:
        _mcp_run_coro(_mcp_connect_all_async(configs), timeout=MCP_STARTUP_TIMEOUT_S)
    except Exception as e:
        log.warning("MCP startup failed: %s", e)


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


def build_system_prompt() -> str:
    return (
        AGENT_SYSTEM_PROMPT
        + get_user_profile_context()
        + get_active_facts_context()
        + get_skills_context()
    )


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
    if not (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
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

    if not (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
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
    try:
        popen_kw: dict = {}
        if os.name == "nt":
            popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.run(
            ["claude", "-p", task, "--output-format", "json", "--dangerously-skip-permissions"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=CLAUDE_CODE_TIMEOUT_S,
            **popen_kw,
        )
    except subprocess.TimeoutExpired:
        return f"Claude Code timed out after {CLAUDE_CODE_TIMEOUT_S} seconds."
    except FileNotFoundError:
        return "The `claude` CLI isn't installed or isn't on PATH."
    except Exception as e:
        return f"Failed to run Claude Code: {e}"

    if proc.returncode != 0:
        err = _strip_ansi((proc.stderr or proc.stdout or "").strip())[:MAX_TOOL_RESULT_CHARS]
        return f"Claude Code exited with an error (code {proc.returncode}): {err or 'no output'}"

    try:
        data = json.loads(proc.stdout)
        result = str(data.get("result") or "").strip()
    except (json.JSONDecodeError, TypeError):
        result = (proc.stdout or "").strip()
    result = _strip_ansi(result)
    if len(result) > MAX_TOOL_RESULT_CHARS:
        result = result[:MAX_TOOL_RESULT_CHARS] + f"... [truncated, {len(result)} chars total]"
    return result or "Claude Code finished with no result text."


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


def _execute_tool(
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
        elif tool_name == "switch_mode":
            mode = str(inp.get("mode") or "").strip()
            if mode in ALLOWED_MODES:
                if mode == "serious":
                    run_serious_mode_actions()
                else:
                    run_normal_mode_actions()
                result = f"Switched to {mode} mode."
            else:
                result = f"{mode!r} is not a known mode."
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
        elif tool_name == "delegate_to_claude_code":
            result = _delegate_to_claude_code(
                str(inp.get("task") or ""), str(inp.get("repo_path") or "")
            )
    except Exception as e:
        log.warning("Tool %r raised: %s", tool_name, e)
        result = f"Tool failed: {e}"

    log.info("Tool %s(%r) -> %s", tool_name, inp, (result or "")[:200])
    _log_action_audit(tool_name, inp, transcript, result)
    return result


def run_agent_loop(transcript: str) -> str:
    """Real observe-act-observe loop: Claude picks tools, sees each result, and decides
    what (if anything) to do next, up to MAX_AGENT_ITERATIONS round trips, before giving a
    final spoken reply. Replaces the old single forced perform_actions tool call."""
    if not (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        log.warning("Set ANTHROPIC_API_KEY in the environment for voice command interpretation.")
        return ""

    messages: list[dict] = _history_snapshot() + [{"role": "user", "content": transcript}]
    reply_parts: list[str] = []
    tools = AGENT_TOOLS + get_mcp_tool_schemas()

    for _ in range(MAX_AGENT_ITERATIONS):
        data = _claude_request(
            {
                "model": CLAUDE_MODEL,
                "max_tokens": 1536,
                "system": build_system_prompt(),
                "messages": messages,
                "tools": tools,
            },
            timeout=60,
        )
        if data is None:
            reply = " ".join(reply_parts).strip() or CLAUDE_UNAVAILABLE_REPLY
            _append_history(transcript, reply)
            return reply

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
        messages.append({"role": "user", "content": tool_results})

    reply = " ".join(p.strip() for p in reply_parts if p.strip())
    _append_history(transcript, reply)
    return reply


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
    log.info("Heard: %r", transcript)

    with _pending_action_lock:
        pending = _pending_action
    if pending is not None:
        if _is_confirmation_yes(transcript):
            step = _take_pending_action()
            if step:
                _execute_confirmed_action(step)
            return
        _take_pending_action()
        log.info(
            "Dropped pending confirmation (%r); treating this utterance as a new command.",
            pending.get("tool_name"),
        )

    reply = run_agent_loop(transcript)
    if reply:
        speak_text(reply)


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


def _opera_gx_executable() -> str | None:
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            p = os.path.join(local, "Programs", "Opera GX", "opera.exe")
            if os.path.isfile(p):
                return p
    return shutil.which("opera")


def _primary_screen_size() -> tuple[int, int]:
    if sys.platform == "win32":
        import ctypes

        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    return (1920, 1080)


def open_opera_gx_split_screen(url_left: str, url_right: str) -> None:
    """Two Opera GX windows, side by side, each covering half the primary screen."""
    exe = _opera_gx_executable()
    if not exe:
        log.warning("Could not find Opera GX (install it or add it to PATH).")
        return
    w, h = _primary_screen_size()
    half_w = w // 2
    popen_kw: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    for x, url in ((0, url_left), (half_w, url_right)):
        try:
            subprocess.Popen(
                [
                    exe,
                    "--new-window",
                    f"--window-position={x},0",
                    f"--window-size={half_w},{h}",
                    url,
                ],
                **popen_kw,
            )
        except OSError as e:
            log.warning("Could not open Opera GX for %s: %s", url, e)


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


def run_normal_mode_actions() -> None:
    """Triple clap: normal greeting + open Cursor. Runs outside the mic loop so it never
    stalls capture; the greeting is spoken first so it doesn't overlap other audio."""
    speak_cached_phrase(JARVIS_WELCOME_PHRASE)
    open_cursor_window()


def _fetch_live_weather(location_query: str) -> str:
    """Live current conditions via wttr.in (free, no key). A web search's static result
    snippets never contain the actual live reading, so that path can't give a real answer."""
    url = "https://wttr.in/" + urllib.parse.quote(location_query) + "?format=j1"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        cur = data["current_condition"][0]
        desc = cur["weatherDesc"][0]["value"]
        temp_c = cur["temp_C"]
        feels_c = cur["FeelsLikeC"]
        humidity = cur["humidity"]
        return f"{desc}, {temp_c} degrees Celsius, feels like {feels_c}, {humidity} percent humidity"
    except Exception as e:
        log.warning("Could not fetch weather: %s", e)
        return ""


def _current_local_time_str(tz_name: str) -> str:
    try:
        now_local = datetime.now(ZoneInfo(tz_name))
        return now_local.strftime("%I:%M %p").lstrip("0")
    except Exception as e:
        log.warning("Could not compute local time for %s: %s", tz_name, e)
        return ""


def run_serious_mode_actions() -> None:
    """Double clap: serious-mode greeting, two split-screen Opera GX windows, then an
    immediate weather + time report for JARVIS_SERIOUS_MODE_LOCATION. Runs outside the mic
    loop so it never stalls capture."""
    speak_cached_phrase(JARVIS_SERIOUS_MODE_PHRASE)
    open_opera_gx_split_screen(
        JARVIS_SERIOUS_MODE_OPERA_LEFT_URL, JARVIS_SERIOUS_MODE_OPERA_RIGHT_URL
    )
    weather = _fetch_live_weather(JARVIS_SERIOUS_MODE_WEATHER_QUERY)
    time_str = _current_local_time_str(JARVIS_SERIOUS_MODE_TIMEZONE)
    parts = []
    if weather:
        parts.append(f"The weather in {JARVIS_SERIOUS_MODE_LOCATION} is {weather}.")
    if time_str:
        parts.append(f"The local time there is {time_str}.")
    report = " ".join(parts)
    speak_text(report or "Sorry, I couldn't get the weather or time just now.")


def open_cursor_window() -> None:
    if not FOCUS_EXISTING_CURSOR_ON_DOUBLE_CLAP and not OPEN_NEW_CURSOR_ON_DOUBLE_CLAP:
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
        if FOCUS_EXISTING_CURSOR_ON_DOUBLE_CLAP:
            focused = (
                sys.platform == "win32" and _focus_existing_cursor_window_win32()
            )
            if not focused:
                subprocess.Popen([exe], **popen_kw)
        if OPEN_NEW_CURSOR_ON_DOUBLE_CLAP:
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
    noise_floor = 1e-4
    spike_armed = True
    # Claps are counted as a burst: each clap within MAX_DOUBLE_GAP_S of the previous one
    # extends the current burst; the burst is only "finished" once that much silence has
    # passed, at which point the total count decides what happens (2 = serious mode,
    # 3 = normal mode, anything else is ignored).
    clap_count = 0
    last_clap_time: float | None = None
    last_mode_trigger_time = 0.0
    # Push-to-talk stays locked until the first recognized clap pattern activates Jarvis,
    # so the very first thing the script reacts to is a clap — not a stray command spoken
    # beforehand.
    jarvis_activated = False
    ptt_locked_notice_shown = False
    ptt_active = False
    ptt_buffer: list[np.ndarray] = []

    log.info(
        "Listening (2 claps = serious mode, 3 claps = normal mode, %.2f–%.2fs apart, "
        "rate=%d, block=%d ms, spike_ratio=%.1f, cooldown=%.2fs). Ctrl+C to stop.",
        MIN_DOUBLE_GAP_S,
        MAX_DOUBLE_GAP_S,
        SAMPLE_RATE,
        BLOCK_MS,
        SPIKE_RATIO,
        COOLDOWN_S,
    )
    if FOCUS_EXISTING_CURSOR_ON_DOUBLE_CLAP:
        log.info(
            "Normal mode (triple clap) will foreground an existing Cursor window "
            "(Windows API); falls back to launching Cursor if none is running."
        )
    if OPEN_NEW_CURSOR_ON_DOUBLE_CLAP:
        log.info("Normal mode (triple clap) will also open a new Cursor window (-n).")
    if CURSOR_OPEN_FULLSCREEN and sys.platform == "win32":
        log.info("Cursor will be sent F11 for fullscreen after focus/launch.")
    if JARVIS_WELCOME_ENABLED:
        log.info(
            "Triple clap (normal mode) says: %r (Piper voice=%s)",
            JARVIS_WELCOME_PHRASE.strip(),
            PIPER_VOICE,
        )
        log.info(
            "Double clap (serious mode) says: %r, then reports weather + time for %s",
            JARVIS_SERIOUS_MODE_PHRASE,
            JARVIS_SERIOUS_MODE_LOCATION,
        )
        _preload_piper_async()
    if JARVIS_PTT_ENABLED:
        log.info(
            "Push-to-talk: hold '%s' and speak, release to run the command "
            "(Whisper=%s, Claude model=%s). Locked until the first recognized clap pattern. "
            "Preloading Whisper in the background...",
            JARVIS_PTT_KEY,
            WHISPER_MODEL_SIZE,
            CLAUDE_MODEL,
        )
        _preload_whisper_async()

    _preload_mcp_async()
    _start_scheduler()

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
                    # Don't let the mic hear Jarvis's own voice and mistake it for a clap
                    # or a command.
                    continue

                if JARVIS_PTT_ENABLED:
                    pressed = _keyboard_is_pressed(JARVIS_PTT_KEY)
                    if not jarvis_activated:
                        if pressed and not ptt_locked_notice_shown:
                            ptt_locked_notice_shown = True
                            log.info(
                                "Push-to-talk is locked until a clap (2 = serious mode, "
                                "3 = normal mode) activates Jarvis — ignoring for now."
                            )
                    else:
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
                            continue

                if jarvis_activated:
                    # Claps only matter for the initial activation. Once Jarvis is up, mode
                    # switching happens by voice ("switch to serious/normal mode") instead —
                    # this also means Jarvis's own TTS can never be misheard as a later clap.
                    continue

                level = rms_mono(data)

                quiet_gate = noise_floor * QUIET_GATE_MULT
                if level < quiet_gate:
                    noise_floor = NOISE_FLOOR_ALPHA * noise_floor + (
                        1.0 - NOISE_FLOOR_ALPHA
                    ) * level
                    noise_floor = max(noise_floor, 1e-7)

                threshold = max(noise_floor * SPIKE_RATIO, MIN_RMS)
                now = time.monotonic()
                retrigger_level = threshold * RETRIGGER_RATIO

                if level < retrigger_level:
                    spike_armed = True

                if (
                    spike_armed
                    and level >= threshold
                    and (now - last_mode_trigger_time) >= COOLDOWN_S
                ):
                    spike_armed = False
                    if last_clap_time is None or (now - last_clap_time) > MAX_DOUBLE_GAP_S:
                        clap_count = 1
                        last_clap_time = now
                    else:
                        gap = now - last_clap_time
                        if gap < MIN_DOUBLE_GAP_S:
                            pass  # bounce/chatter from the same clap; don't count it
                        else:
                            clap_count += 1
                            last_clap_time = now

                # A burst is "finished" once enough silence has passed since the last clap
                # in it — only then do we know the final count and can act on it.
                if (
                    clap_count > 0
                    and last_clap_time is not None
                    and (now - last_clap_time) > MAX_DOUBLE_GAP_S
                ):
                    finished_count = clap_count
                    clap_count = 0
                    last_clap_time = None
                    last_mode_trigger_time = now
                    if finished_count == 2:
                        jarvis_activated = True
                        log.info(
                            "Double clap detected (rms=%.5f, noise_floor=%.5f, threshold=%.5f) "
                            "— activating serious mode (push-to-talk unlocked). Claps are now "
                            "ignored; say \"switch to normal mode\" to change modes.",
                            level,
                            noise_floor,
                            threshold,
                        )
                        threading.Thread(target=run_serious_mode_actions, daemon=True).start()
                    elif finished_count == 3:
                        jarvis_activated = True
                        log.info(
                            "Triple clap detected (rms=%.5f, noise_floor=%.5f, threshold=%.5f) "
                            "— activating normal mode (push-to-talk unlocked). Claps are now "
                            "ignored; say \"switch to serious mode\" to change modes.",
                            level,
                            noise_floor,
                            threshold,
                        )
                        threading.Thread(target=run_normal_mode_actions, daemon=True).start()
                    else:
                        log.info(
                            "Clap burst of %d ignored (recognized: 2 = serious mode, "
                            "3 = normal mode).",
                            finished_count,
                        )

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
