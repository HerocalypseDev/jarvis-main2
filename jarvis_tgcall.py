"""Two-way phone calls through a spare Telegram account (2026-10-17, owner choice after CallMeBot kept failing).

Jarvis logs into a SPARE Telegram user account (never the owner's main one) and rings the owner's main account.
On the line Jarvis speaks (the normal TTS voice) and hears the owner (the normal speech-to-text), so the owner can
talk to it and cut in while it speaks.

Layout (everything above `TelegramTransport` is pure and tested with a fake line):
- config + limits: api id/hash and the target from `.env`, the login session kept OUTSIDE the repo and OneDrive;
- `Listener`: energy VAD over the caller's 48 kHz audio -> "speech_start" / "utterance" events;
- `Talker`: paces TTS frames onto the line and stops at once when the caller starts talking (barge-in), reporting
  which sentences were heard and which were cut;
- `Conversation`: the loop (opening line, listen, answer, hang up on goodbye / silence / max length);
- `TelegramTransport`: Telethon + py-tgcalls (imported lazily, optional packages), run on its own asyncio thread.

Rules (owner's choices + the project's standing rules):
- The only person called is TGCALL_TARGET (falls back to CALLMEBOT_TELEGRAM_USER). Nothing here takes a recipient
  from a caller, so a call can never reach anyone else; at most JARVIS_CALLS_PER_DAY calls a day (default 5, shared
  with CallMeBot), the same opening at most once an hour, one call at a time, JARVIS_TGCALL_MAX_MIN minutes at most.
- What the caller says runs through the normal command pipeline as a hands-free phone command: the catastrophic
  confirmation gate is intact and a spoken "yes" on a call can NEVER confirm a staged action (energy VAD cannot tell
  the owner from someone else holding the phone). That wiring lives in jarvis.py; this module never imports it.
- Secrets: the api hash and the session file are credentials. The session lives under %LOCALAPPDATA%\\Jarvis\\tgcall
  (a folder jarvis_workspace.sensitive_reason already refuses) and a path under OneDrive is refused.
- Audio is the only thing that leaves the PC (to Telegram, and to the speech engines exactly as for a voice command).
Not verified on a real call: see CLAUDE.md. `python jarvis_tgcall.py test` checks the audio path end to end.
"""
from __future__ import annotations

import asyncio
import atexit
import collections
import logging
import os
import queue
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

log = logging.getLogger("jarvis")

RATE = 48000                        # Telegram call audio: 48 kHz mono 16-bit
FRAME_MS = 20                       # one Opus frame
FRAME_SAMPLES = RATE * FRAME_MS // 1000
FRAME_BYTES = FRAME_SAMPLES * 2
STT_RATE = 16000

RING_TIMEOUT_S = 45
SAME_TEXT_GAP_S = 3600
FILLER_AFTER_S = 4.0
INSTALL_HINT = "pip install telethon==1.45.0 py-tgcalls==3.0.0 ntgcalls==3.0.3"

_GOODBYE_RE = re.compile(
    r"\b(good ?bye|bye|hang up|end (the|this) call|that'?s all|that is all|talk later|speak later|i'?m done)\b", re.I)


class CallError(Exception):
    """A call that could not be placed or ended badly; the message is a plain-words reason."""


# --- configuration -------------------------------------------------------------------------------------------------
def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip().strip('"').strip("'")


def api_id() -> int | None:
    v = _env("TGCALL_API_ID")
    return int(v) if v.isdigit() and 0 < int(v) < 2 ** 31 else None


def api_hash() -> str:
    v = _env("TGCALL_API_HASH_SECRET").lower()
    return v if re.fullmatch(r"[0-9a-f]{32}", v) else ""


def target() -> str:
    """The owner's main Telegram @username or +phone number (the same person CallMeBot rings)."""
    value = _env("TGCALL_TARGET") or _env("CALLMEBOT_TELEGRAM_USER")
    if not value:
        return ""
    compact = value.replace(" ", "")
    if re.fullmatch(r"\+?\d{7,15}", compact):
        digits = compact.lstrip("+")
        if digits.startswith("0"):
            return ""  # local format (0801...), not international
        return "+" + digits
    if re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{3,31}", value):
        return value if value.startswith("@") else "@" + value
    return ""


def session_dir() -> Path:
    override = _env("JARVIS_TGCALL_DIR")
    base = Path(override) if override else (
        Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "share")) / "Jarvis" / "tgcall")
    if "onedrive" in str(base).lower():
        raise CallError("the Telegram login must not live in a synced OneDrive folder (set JARVIS_TGCALL_DIR elsewhere)")
    return base


def session_path() -> Path:
    return session_dir() / "jarvis_call"      # Telethon adds ".session"


def logged_in() -> bool:
    try:
        f = session_path().with_suffix(".session")
        return f.is_file() and f.stat().st_size > 0
    except (CallError, OSError):
        return False


_GUARD_NAME = "jarvis_call.owner"
_claimed = False


def _holder_alive(pid: int) -> bool:
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def claim_session(what: str) -> None:
    """One process at a time may open the spare account's session file: Telethon keeps it in sqlite, and a second
    program opening it gets "database is locked". The first opener writes its pid here; a second program is refused
    with a plain message. A file left by a process that has exited is taken over."""
    global _claimed
    if _claimed:
        return
    path = session_dir() / _GUARD_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
                pid, held_by = int(lines[0]), (lines[1] if len(lines) > 1 else "another program")
            except (OSError, ValueError, IndexError):
                pid, held_by = 0, ""
            if pid and pid != os.getpid() and _holder_alive(pid):
                raise CallError(f"the spare account is in use by {held_by} (process {pid}). Stop that program "
                                "first (Jarvis keeps the account while it runs), then try again")
            try:
                path.unlink()
            except OSError:
                pass
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"{os.getpid()}\n{what}\n")
        _claimed = True
        atexit.register(_release_session)
        return
    raise CallError("could not take the spare account's session (another program keeps it)")


def _release_session() -> None:
    global _claimed
    try:
        path = session_dir() / _GUARD_NAME
        if path.is_file() and path.read_text(encoding="utf-8").split("\n", 1)[0] == str(os.getpid()):
            path.unlink()
    except (OSError, ValueError, CallError):
        pass
    _claimed = False


def _who() -> str:
    """Plain label for this program, shown to another program that is refused."""
    name = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "python"
    if name.lower() == "jarvis.py":
        return "Jarvis"
    return " ".join([name] + sys.argv[1:2])


def missing() -> list[str]:
    """What is still to set up, in plain words (empty = ready)."""
    out = []
    if api_id() is None:
        out.append("TGCALL_API_ID (from my.telegram.org)")
    if not api_hash():
        out.append("TGCALL_API_HASH_SECRET (the api_hash from my.telegram.org)")
    if not target():
        out.append("your main Telegram @username (TGCALL_TARGET)")
    if not logged_in():
        out.append("the one-time login of the spare account: run `python jarvis_tgcall.py login` on the PC")
    return out


def configured() -> bool:
    return not missing()


def _int_env(name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(float(_env(name) or default))))
    except ValueError:
        return default


def per_day() -> int:
    return _int_env("JARVIS_CALLS_PER_DAY", 5, 0, 50)


def max_seconds() -> int:
    return _int_env("JARVIS_TGCALL_MAX_MIN", 15, 1, 60) * 60


def idle_seconds() -> int:
    return _int_env("JARVIS_TGCALL_IDLE_S", 45, 10, 300)


_lock = threading.Lock()
_calls: list[tuple[float, str]] = []
_line_busy = threading.Lock()
_yield_line = threading.Event()        # an outgoing call wants the Telegram session: the inbound listener steps aside
_inbound_listening = threading.Event()  # set while the inbound listener holds the Telegram session
_inbound_stop = threading.Event()
_inbound_thread: threading.Thread | None = None


def reserve(opening: str) -> str | None:
    """Counts a call against the daily cap. Returns a reason when it must not be placed, else None."""
    now = time.time()
    with _lock:
        _calls[:] = [c for c in _calls if now - c[0] < 86400]
        if len(_calls) >= per_day():
            return f"already made {per_day()} calls today (JARVIS_CALLS_PER_DAY); not calling again"
        if opening and any(t == opening and now - ts < SAME_TEXT_GAP_S for ts, t in _calls):
            return "already called you about this in the last hour"
        _calls.append((now, opening))
    return None


def refund(opening: str) -> None:
    """A call that never rang (setup problem, no answer) doesn't use up the day's allowance."""
    with _lock:
        for i in range(len(_calls) - 1, -1, -1):
            if _calls[i][1] == opening:
                del _calls[i]
                return


def reset_for_tests() -> None:
    with _lock:
        _calls.clear()


# --- audio helpers -------------------------------------------------------------------------------------------------
def to_rate(samples: np.ndarray, src: int, dst: int) -> np.ndarray:
    """Linear resample of mono float audio."""
    x = np.asarray(samples, dtype=np.float32)
    if src == dst or x.size == 0:
        return x
    n = max(1, int(round(x.size * dst / src)))
    return np.interp(np.linspace(0, x.size - 1, n), np.arange(x.size), x).astype(np.float32)


def pcm16_to_float(data: bytes) -> np.ndarray:
    return np.frombuffer(data[: len(data) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0


def float_to_pcm16(x: np.ndarray) -> bytes:
    return (np.clip(np.asarray(x, dtype=np.float32), -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


def tts_to_frames(raw: bytes, rate: int) -> list[bytes]:
    """16-bit mono TTS audio at any rate -> 20 ms frames at 48 kHz (last one padded with silence)."""
    if not raw or not rate:
        return []
    pcm = float_to_pcm16(to_rate(pcm16_to_float(raw), rate, RATE))
    pcm += b"\x00" * (-len(pcm) % FRAME_BYTES)
    return [pcm[i:i + FRAME_BYTES] for i in range(0, len(pcm), FRAME_BYTES)]


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", text or "") if p and p.strip()]
    out: list[str] = []
    for p in parts:
        while len(p) > 300:  # a run-on line: cut at a comma/space so no single synth call is huge
            cut = max(p.rfind(", ", 0, 300), p.rfind(" ", 0, 300))
            cut = cut if cut > 60 else 300
            out.append(p[:cut].strip())
            p = p[cut:].strip(" ,")
        if p:
            out.append(p)
    return out


def is_goodbye(text: str) -> bool:
    words = re.findall(r"[a-z']+", (text or "").lower())
    return 0 < len(words) <= 5 and bool(_GOODBYE_RE.search(" ".join(words)))


# --- hearing the caller --------------------------------------------------------------------------------------------
class Listener:
    """Energy VAD over the caller's audio (48 kHz mono 16-bit, any chunk size).

    feed() returns events: ("speech_start",) once the caller has been voiced for START_S (BARGE_S while Jarvis is
    speaking, so a cough or "mhm" doesn't cut it off), and ("utterance", float32 audio at 16 kHz) after END_SILENCE_S
    of quiet. The background level is learned from the quiet frames, so a steady hiss raises the bar."""
    START_S = 0.25
    BARGE_S = 0.5
    END_SILENCE_S = 0.8
    MIN_VOICED_S = 0.3
    MAX_UTT_S = 20.0
    PREROLL_S = 0.5
    MIN_RMS = 0.01

    def __init__(self, speaking: Callable[[], bool] = lambda: False):
        self.speaking = speaking
        self.floor = 0.004
        self._carry = b""
        self._pre: collections.deque = collections.deque(maxlen=int((self.PREROLL_S + self.BARGE_S) * 1000 / FRAME_MS) + 2)
        self._reset()

    def _reset(self) -> None:
        self._utt: list[np.ndarray] = []
        self._in_speech = False
        self._voiced_run = 0.0
        self._voiced_total = 0.0
        self._silence = 0.0

    def feed(self, data: bytes) -> list[tuple]:
        events: list[tuple] = []
        buf = self._carry + data
        n = len(buf) // FRAME_BYTES * FRAME_BYTES
        self._carry = buf[n:]
        step = FRAME_MS / 1000.0
        for i in range(0, n, FRAME_BYTES):
            frame = pcm16_to_float(buf[i:i + FRAME_BYTES])
            rms = float(np.sqrt(np.mean(frame * frame))) if frame.size else 0.0
            voiced = rms > max(self.MIN_RMS, self.floor * 3)
            if not self._in_speech:
                self._pre.append(frame)
                if not voiced:
                    self._voiced_run = 0.0
                    self.floor = min(0.05, max(0.001, 0.95 * self.floor + 0.05 * rms))
                    continue
                self._voiced_run += step
                if self._voiced_run >= (self.BARGE_S if self.speaking() else self.START_S):
                    self._in_speech = True
                    self._utt = list(self._pre)
                    self._voiced_total = self._voiced_run
                    self._silence = 0.0
                    events.append(("speech_start",))
                continue
            self._utt.append(frame)
            if voiced:
                self._voiced_total += step
                self._silence = 0.0
            else:
                self._silence += step
            if self._silence >= self.END_SILENCE_S or len(self._utt) * step >= self.MAX_UTT_S:
                if self._voiced_total >= self.MIN_VOICED_S:
                    events.append(("utterance", to_rate(np.concatenate(self._utt), RATE, STT_RATE)))
                self._pre.clear()
                self._reset()
        return events


# --- speaking to the caller ----------------------------------------------------------------------------------------
class Talker:
    """Sends 20 ms frames to the line in real time. `cancel` (set when the caller talks over Jarvis) stops it within
    one frame. Only one thing speaks at a time (`_say_lock`)."""

    def __init__(self, send: Callable[[bytes], None], cancel: threading.Event,
                 clock=time.monotonic, sleep=time.sleep):
        self.send = send
        self.cancel = cancel
        self.speaking = threading.Event()
        self._clock = clock
        self._sleep = sleep
        self._say_lock = threading.Lock()

    def say(self, parts: list[tuple[str, Callable[[], list[bytes]]]]) -> tuple[str, str, bool]:
        """parts = [(sentence, make_frames)]. Returns (heard, cut, interrupted): the sentences played in full, and the
        rest of the reply (the sentence being played when it was cut, plus everything after it)."""
        with self._say_lock:
            self.cancel.clear()
            self.speaking.set()
            heard: list[str] = []
            try:
                prefetched: dict[int, list[bytes]] = {}

                def fetch(i: int) -> None:
                    try:
                        prefetched[i] = parts[i][1]()
                    except Exception as e:  # one sentence failing to synthesise only loses that sentence
                        log.warning("Call speech: synthesis failed (%s)", e)
                        prefetched[i] = []

                worker: threading.Thread | None = None
                for i, (sentence, _make) in enumerate(parts):
                    if worker is not None:
                        worker.join(timeout=30)
                    if i not in prefetched:
                        fetch(i)
                    frames = prefetched.pop(i, [])
                    worker = None
                    if i + 1 < len(parts):
                        worker = threading.Thread(target=fetch, args=(i + 1,), daemon=True)
                        worker.start()
                    t0, sent = self._clock(), 0
                    for fr in frames:
                        if self.cancel.is_set():
                            return " ".join(heard), " ".join(p[0] for p in parts[i:]), True
                        self.send(fr)
                        sent += 1
                        delay = t0 + sent * FRAME_MS / 1000.0 - self._clock()
                        if delay > 0:
                            self._sleep(delay)
                    heard.append(sentence)
                return " ".join(heard), "", False
            finally:
                self.speaking.clear()


# --- the call itself -----------------------------------------------------------------------------------------------
@dataclass
class Hooks:
    """What the call needs from Jarvis (supplied by jarvis.py, so this module never imports it)."""
    transcribe: Callable[[np.ndarray], str]              # 16 kHz float32 mono audio -> text
    synth: Callable[[str], tuple[bytes, int]]            # text -> (16-bit mono PCM, sample rate)
    run_command: Callable[[str, str], str]               # (what the caller said, note) -> Jarvis's reply text
    shape: Callable[[str], str] = lambda t: t            # reply -> what is fit to say aloud (summary, paths, symbols)


@dataclass
class CallResult:
    ok: bool
    reason: str = ""
    seconds: float = 0.0
    turns: int = 0


class Conversation:
    def __init__(self, transport, hooks: Hooks, opening: str = "", clock=time.monotonic):
        self.transport = transport
        self.hooks = hooks
        self.opening = opening
        self.clock = clock
        self.cancel = threading.Event()
        self.talker = Talker(transport.send, self.cancel)
        self.listener = Listener(speaking=self.talker.speaking.is_set)
        self.utterances: queue.Queue = queue.Queue()
        self.turns = 0
        self._note = ""
        self._last_activity = clock()
        self._stop = threading.Event()

    # -- hearing (own thread): barge-in is decided here, the moment the caller has talked long enough
    def _reader(self) -> None:
        while not self._stop.is_set() and not self.transport.closed.is_set():
            try:
                data = self.transport.frames.get(timeout=0.2)
            except queue.Empty:
                continue
            for ev in self.listener.feed(data):
                self._last_activity = self.clock()
                if ev[0] == "speech_start" and self.talker.speaking.is_set():
                    self.cancel.set()
                elif ev[0] == "utterance":
                    self.utterances.put(ev[1])

    # -- speaking
    def _parts(self, text: str) -> list[tuple[str, Callable[[], list[bytes]]]]:
        shaped = self.hooks.shape(text) or text
        out = []
        for s in split_sentences(shaped):
            out.append((s, (lambda s=s: tts_to_frames(*self.hooks.synth(s)))))
        return out

    def say(self, text: str) -> bool:
        """Speaks `text`; if the caller cut in, remembers where, for the next command. Returns interrupted."""
        parts = self._parts(text)
        if not parts:
            return False
        heard, cut, interrupted = self.talker.say(parts)
        if interrupted:
            self._note = ("[Call: the caller talked over your last reply. They heard: '%s'. They did NOT hear: '%s'. "
                          "Answer what they say now; offer the rest only if it still matters.]"
                          % (heard[-200:], cut[:300]))
        self._last_activity = self.clock()
        return interrupted

    def _answer(self, said: str) -> None:
        note, self._note = self._note, ""
        done = threading.Event()

        def filler() -> None:
            if not done.wait(FILLER_AFTER_S):
                self.say("One moment.")

        th = threading.Thread(target=filler, daemon=True)
        th.start()
        try:
            reply = self.hooks.run_command(said, note)
        finally:
            done.set()
            th.join(timeout=15)
        self.turns += 1
        if reply and not self.transport.closed.is_set():
            self.say(reply)

    def run(self) -> CallResult:
        t0 = self.clock()
        reader = threading.Thread(target=self._reader, daemon=True)
        try:
            self.transport.start()                                    # rings and waits for the answer
        except CallError as e:
            self.transport.stop()
            return CallResult(False, str(e), self.clock() - t0)
        reason = ""
        try:
            reader.start()
            if self.opening:
                self.say(self.opening)
            while not self.transport.closed.is_set():
                now = self.clock()
                if now - t0 > max_seconds():
                    self.say("I have to let you go now; call me back if you need me.")
                    reason = "reached the longest call allowed"
                    break
                if now - self._last_activity > idle_seconds() and not self.talker.speaking.is_set():
                    self.say("I'll let you go. Call me whenever you need me.")
                    reason = "nobody spoke for a while"
                    break
                try:
                    audio = self.utterances.get(timeout=0.3)
                except queue.Empty:
                    continue
                said = (self.hooks.transcribe(audio) or "").strip()
                if len(said) < 2:
                    continue
                if is_goodbye(said):
                    self.say("Goodbye.")
                    reason = "you said goodbye"
                    break
                self._answer(said)
                self._last_activity = self.clock()
            else:
                reason = getattr(self.transport, "end_reason", "") or "the call ended"
        except Exception as e:  # a bug here must never leave a live call hanging
            log.warning("Call loop failed: %s", e, exc_info=True)
            reason = f"stopped by an error ({type(e).__name__})"
        finally:
            self._stop.set()
            self.transport.stop()
        return CallResult(True, reason, self.clock() - t0, self.turns)


# --- the real line: Telethon + py-tgcalls (lazy imports; optional packages) ------------------------------------------
def explain(e: BaseException) -> str:
    """A plain-words reason for a Telegram/call failure (matched by name: the packages are optional)."""
    name, text = type(e).__name__, str(e)
    low = (name + " " + text).lower()
    if "importerror" in low or "modulenotfound" in low:
        return f"the call packages aren't installed ({INSTALL_HINT})"
    if "authkey" in low or "sessionrevoked" in low or "sessionexpired" in low or "unauthorized" in low:
        return "the spare account's login ended: run `python jarvis_tgcall.py login` again"
    if "privacy" in low:
        return ("your main Telegram doesn't let the spare account call you: Settings, Privacy and Security, Calls, "
                "add the spare account to 'Always allow'")
    if "floodwait" in low or "flood" in low:
        return "Telegram asked this account to slow down; try again later"
    if "timeout" in low or "timed out" in low:
        return "no answer (the call rang out)"
    if "declin" in low or "busy" in low or "discard" in low:
        return "the call was declined or you were busy"
    if "usernamenotoccupied" in low or "cannot find any entity" in low or "no user" in low:
        return "Telegram doesn't know that @username (check TGCALL_TARGET)"
    return f"{name}: {text[:120]}".strip()


class TelegramTransport:
    """One outgoing call. start() connects, rings, and returns once the owner answered (or raises CallError)."""

    def __init__(self, to: str, ring_timeout: int = RING_TIMEOUT_S):
        self.to = to
        self.ring_timeout = ring_timeout
        self.frames: queue.Queue = queue.Queue(maxsize=400)
        self.closed = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._app = None
        self._client = None
        self._uid: int | None = None
        self._device = None
        self._error: str | None = None
        self.trace = ""
        self._ready = threading.Event()
        self.frames_in = 0
        self.frame_sizes: collections.Counter = collections.Counter()
        self.end_reason = ""                 # why the line dropped, in plain words (empty while it is up)
        self._answered_at: float | None = None

    def _since_answer(self) -> str:
        if self._answered_at is None:
            return "before it was answered"
        return f"{time.monotonic() - self._answered_at:.1f} s after it was answered"

    def _end(self, reason: str) -> None:
        if not self.end_reason:
            self.end_reason = reason
            log.warning("Telegram call ended: %s", reason)
        self.closed.set()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="jarvis-tgcall", daemon=True)
        self._thread.start()
        if not self._ready.wait(self.ring_timeout + 45):
            self.stop()
            raise CallError("Telegram took too long to connect")
        if self._error:
            self.stop()
            raise CallError(self._error)

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._connect())
        except BaseException as e:  # noqa: BLE001 - every failure becomes a reason
            self._error = explain(e)
            if os.environ.get("JARVIS_TGCALL_DEBUG"):
                import traceback
                self.trace = "".join(traceback.format_exception(e))
            log.info("Telegram call failed: %s: %s", type(e).__name__, e)
        finally:
            self._ready.set()
        if not self._error:
            try:
                loop.run_forever()
            finally:
                try:
                    loop.run_until_complete(self._shutdown())
                except Exception:
                    pass
        else:
            try:
                loop.run_until_complete(self._shutdown())
            except Exception:
                pass
        self.closed.set()

    async def _connect(self) -> None:
        try:
            from telethon import TelegramClient
            from pytgcalls import PyTgCalls, filters
            from pytgcalls.types import (AudioQuality, CallConfig, ChatUpdate, Device, Direction, ExternalMedia,
                                         MediaStream, RecordStream)
        except ImportError as e:
            raise CallError(f"the call packages aren't installed ({INSTALL_HINT})") from e
        self._device = Device
        claim_session(_who())
        client = TelegramClient(str(session_path()), api_id(), api_hash())
        self._client = client
        await client.connect()
        if not await client.is_user_authorized():
            raise CallError("the spare account isn't logged in: run `python jarvis_tgcall.py login` on the PC")
        entity = await client.get_entity(self.to)
        if type(entity).__name__ != "User":
            raise CallError(f"{self.to} is not a person's account (it resolved to a {type(entity).__name__}); "
                            "use the @username of your MAIN account, not a channel or group")
        me = await client.get_me()
        if me is not None and int(entity.id) == int(me.id):
            raise CallError(f"{self.to} is the spare account itself: Telegram can't call yourself. Set TGCALL_TARGET "
                            "to the @username of your MAIN account (the one you answer calls on), not the spare one")
        await client.get_input_entity(entity)       # puts the access hash in the session so the call layer can find the user
        self._uid = int(entity.id)
        app = PyTgCalls(client)
        self._app = app

        @app.on_update(filters.stream_frame(Direction.INCOMING))
        async def _incoming(_, update):
            for fr in update.frames:
                if getattr(fr.info, "width", 0):       # a video frame
                    continue
                self.frames_in += 1
                self.frame_sizes[len(fr.frame)] += 1
                try:
                    self.frames.put_nowait(bytes(fr.frame))
                except queue.Full:
                    pass                               # the listener is behind: drop, never block the call thread

        @app.on_update(filters.chat_update(ChatUpdate.Status.LEFT_CALL))
        async def _left(_, update):
            self._end(f"Telegram reported that the call left the line ({self._since_answer()})")

        await app.start()
        stream = MediaStream(ExternalMedia.AUDIO, audio_parameters=AudioQuality.HIGH,
                             video_flags=MediaStream.Flags.IGNORE)
        await app.play(self._uid, stream, CallConfig(timeout=self.ring_timeout))   # blocks until answered
        self._answered_at = time.monotonic()
        await app.record(self._uid, RecordStream(audio=True, audio_parameters=AudioQuality.HIGH))

    def send(self, frame: bytes) -> None:
        if self.closed.is_set() or self._loop is None or self._app is None:
            return
        fut = asyncio.run_coroutine_threadsafe(
            self._app.send_frame(self._uid, self._device.MICROPHONE, frame), self._loop)
        try:
            fut.result(timeout=3)
        except Exception as e:
            self._end(f"sending audio failed {self._since_answer()} ({type(e).__name__}: {str(e)[:120]})")

    async def _shutdown(self) -> None:
        try:
            if self._app is not None and self._uid is not None:
                await self._app.leave_call(self._uid)
        except Exception:
            pass
        try:
            if self._client is not None:
                await self._client.disconnect()
        except Exception:
            pass

    def stop(self) -> None:
        self.closed.set()
        loop, th = self._loop, self._thread
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if th is not None and th is not threading.current_thread():
            th.join(timeout=10)


# --- calls TO Jarvis: the spare account answers, but only for the owner's main account ---------------------------------
def inbound_enabled() -> bool:
    return configured() and os.environ.get("JARVIS_TGCALL_INBOUND", "1").strip().lower() not in ("0", "false", "off", "no")


class InboundTransport(TelegramTransport):
    """Waits (connected, nothing ringing) for a call from the owner's main account, answers it, then behaves like the
    outgoing transport. Calls from any other account are never answered (they just ring out)."""

    def __init__(self, to: str, should_stop: Callable[[], bool] = lambda: False):
        super().__init__(to)
        self.should_stop = should_stop
        self._incoming = threading.Event()
        self._answered = threading.Event()
        self._holds_line = False

    async def _connect(self) -> None:
        try:
            from telethon import TelegramClient
            from pytgcalls import PyTgCalls, filters
            from pytgcalls.types import (AudioQuality, CallConfig, ChatUpdate, Device, Direction, ExternalMedia,
                                         MediaStream, RecordStream)
        except ImportError as e:
            raise CallError(f"the call packages aren't installed ({INSTALL_HINT})") from e
        incoming_status = getattr(ChatUpdate.Status, "INCOMING_CALL", None)
        if incoming_status is None:
            raise CallError("this py-tgcalls version can't answer incoming calls")
        self._device = Device
        claim_session(_who())
        client = TelegramClient(str(session_path()), api_id(), api_hash())
        self._client = client
        await client.connect()
        if not await client.is_user_authorized():
            raise CallError("the spare account isn't logged in: run `python jarvis_tgcall.py login` on the PC")
        entity = await client.get_entity(self.to)
        if type(entity).__name__ != "User":
            raise CallError(f"{self.to} is not a person's account (it resolved to a {type(entity).__name__})")
        me = await client.get_me()
        if me is not None and int(entity.id) == int(me.id):
            raise CallError(f"{self.to} is the spare account itself: set TGCALL_TARGET to your MAIN account")
        await client.get_input_entity(entity)
        self._uid = int(entity.id)
        app = PyTgCalls(client)
        self._app = app

        @app.on_update(filters.stream_frame(Direction.INCOMING))
        async def _incoming_frames(_, update):
            for fr in update.frames:
                if getattr(fr.info, "width", 0):
                    continue
                self.frames_in += 1
                try:
                    self.frames.put_nowait(bytes(fr.frame))
                except queue.Full:
                    pass

        @app.on_update(filters.chat_update(ChatUpdate.Status.LEFT_CALL))
        async def _left(_, update):
            self._end(f"Telegram reported that the call left the line ({self._since_answer()})")

        @app.on_update(filters.chat_update(incoming_status))
        async def _ring(_, update):
            if int(getattr(update, "chat_id", 0) or 0) != self._uid or self._incoming.is_set():
                return                                      # not the owner: never answered
            if not _line_busy.acquire(blocking=False):
                return                                      # already on a call
            self._holds_line = True
            self._incoming.set()
            try:
                stream = MediaStream(ExternalMedia.AUDIO, audio_parameters=AudioQuality.HIGH,
                                     video_flags=MediaStream.Flags.IGNORE)
                await app.play(self._uid, stream, CallConfig(timeout=RING_TIMEOUT_S))   # answers the ringing call
                self._answered_at = time.monotonic()
                await app.record(self._uid, RecordStream(audio=True, audio_parameters=AudioQuality.HIGH))
                self._answered.set()
            except Exception as e:  # noqa: BLE001
                self._error = explain(e)
                log.info("Could not answer the incoming call: %s: %s", type(e).__name__, e)
                self._end(f"could not answer the incoming call ({type(e).__name__}: {str(e)[:120]})")

        await app.start()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="jarvis-tgcall-in", daemon=True)
        _inbound_listening.set()                 # from the first moment: the session file is ours while we connect
        self._thread.start()
        for _ in range(300):                     # up to 60 s, but an outgoing call can cut the wait short
            if self._ready.wait(0.2):
                break
            if self.should_stop():
                self.stop()
                raise CallError("listening stopped")
        else:
            self.stop()
            raise CallError("Telegram took too long to connect")
        if self._error:
            self.stop()
            raise CallError(self._error)
        while not self._incoming.is_set():
            if self.should_stop() or self.closed.is_set():
                self.stop()
                raise CallError("listening stopped")
            time.sleep(0.3)
        for _ in range(int((RING_TIMEOUT_S + 15) / 0.2)):
            if self._answered.is_set():
                return
            if self.closed.is_set() or self._error:
                break
            time.sleep(0.2)
        self.stop()
        raise CallError(self._error or "the call ended before it could be answered")

    def stop(self) -> None:
        super().stop()
        _inbound_listening.clear()
        if self._holds_line:
            self._holds_line = False
            try:
                _line_busy.release()
            except RuntimeError:
                pass


def start_inbound(hooks_factory: Callable[[], "Hooks"], on_done: Callable[[CallResult], None] | None = None,
                  transport_factory=None) -> bool:
    """Starts the background listener (once). Returns whether it started. A call from the owner is answered with a short
    greeting and then handled exactly like an outgoing one; the listener steps aside while an outgoing call is placed."""
    global _inbound_thread
    if not inbound_enabled() or (_inbound_thread is not None and _inbound_thread.is_alive()):
        return False
    _inbound_stop.clear()

    def _loop() -> None:
        failures = 0
        while not _inbound_stop.is_set():
            if not inbound_enabled() or _yield_line.is_set() or _line_busy.locked():
                _inbound_stop.wait(2)
                continue
            tr = (transport_factory or (lambda: InboundTransport(
                target(), lambda: _yield_line.is_set() or _inbound_stop.is_set())))()
            try:
                res = Conversation(tr, hooks_factory(), "Hi, it's Jarvis. Go ahead.").run()
            except Exception as e:  # noqa: BLE001
                res = CallResult(False, explain(e))
            if res.turns or res.ok:
                failures = 0
                log.info("Incoming Telegram call: %s (%.0fs, %d turns)", res.reason, res.seconds, res.turns)
                if on_done:
                    try:
                        on_done(res)
                    except Exception as e:  # noqa: BLE001
                        log.warning("Call follow-up failed: %s", e)
            elif res.reason != "listening stopped":
                failures += 1
                if failures in (1, 5):
                    log.info("Incoming-call listener could not start: %s", res.reason)
                _inbound_stop.wait(min(300, 20 * failures))   # back off: never hammer Telegram's login
            _inbound_stop.wait(1)

    _inbound_thread = threading.Thread(target=_loop, name="jarvis-tgcall-listener", daemon=True)
    _inbound_thread.start()
    return True


def stop_inbound() -> None:
    _inbound_stop.set()


# --- placing a call from Jarvis ------------------------------------------------------------------------------------
def call_owner(opening: str, hooks: Hooks, transport_factory=None) -> CallResult:
    """Blocking: rings the owner and talks until the call ends. Never raises."""
    todo = missing()
    if todo:
        return CallResult(False, "calls aren't set up yet: " + "; ".join(todo))
    if _inbound_listening.is_set():
        _yield_line.set()                                    # the listener holds the session file; ask it to let go
        for _ in range(120):                                 # it may still be connecting or shutting down: wait it out
            if not _inbound_listening.is_set():
                break
            time.sleep(0.25)
    if not _line_busy.acquire(blocking=False):
        _yield_line.clear()
        return CallResult(False, "already on a call")
    opening = (opening or "").strip()
    try:
        why = reserve(opening)
        if why:
            return CallResult(False, why)
        factory = transport_factory or (lambda: TelegramTransport(target()))
        result = CallResult(False, "not started")
        for attempt in range(2):
            try:
                result = Conversation(factory(), hooks, opening).run()
            except Exception as e:  # noqa: BLE001
                result = CallResult(False, explain(e))
            if attempt == 0 and result.turns == 0 and not result.ok and "database is locked" in (result.reason or "").lower():
                time.sleep(3)                    # the session file was still being released: one more try
                continue
            break
        if result.turns == 0 and not result.ok:
            refund(opening)                      # it never rang or wasn't answered: not a call that counts
        return result
    finally:
        _line_busy.release()
        _yield_line.clear()


def start_in_background(opening: str, hooks: Hooks, on_done: Callable[[CallResult], None] | None = None,
                        transport_factory=None) -> tuple[bool, str]:
    """Starts the call on its own thread and returns at once: (started, what to tell the user)."""
    todo = missing()
    if todo:
        return False, "calls aren't set up yet: " + "; ".join(todo)
    if _line_busy.locked():
        return False, "already on a call"

    def _go() -> None:
        res = call_owner(opening, hooks, transport_factory)
        log.info("Telegram call: %s (%s, %.0fs, %d turns)", "ok" if res.ok else "not completed", res.reason,
                 res.seconds, res.turns)
        if on_done:
            try:
                on_done(res)
            except Exception as e:  # noqa: BLE001
                log.warning("Call follow-up failed: %s", e)

    threading.Thread(target=_go, name="jarvis-call", daemon=True).start()
    return True, "ringing your Telegram now: pick up and talk, and you can cut in whenever you want"


# --- command line: login and a test call ---------------------------------------------------------------------------
def _cli_login() -> int:
    import getpass
    todo = [m for m in missing() if not m.startswith("the one-time login")]
    if todo:
        print("Set these in Jarvis's .env (or the Settings page) first: " + "; ".join(todo))
        return 1
    try:
        from telethon import TelegramClient
    except ImportError:
        print(f"Install the packages first: {INSTALL_HINT}")
        return 1
    session_dir().mkdir(parents=True, exist_ok=True)
    try:
        claim_session(_who())
    except CallError as e:
        print(str(e))
        return 1
    print("Log in the SPARE Telegram account (not your main one). Telegram sends a code to that account.")
    phone = input("Spare account's phone number, with country code (e.g. +234...): ").strip()

    async def go() -> None:
        client = TelegramClient(str(session_path()), api_id(), api_hash())
        await client.start(phone=lambda: phone,
                           code_callback=lambda: input("Code Telegram sent you: ").strip(),
                           password=lambda: getpass.getpass("Two-step password (Enter if none): "))
        me = await client.get_me()
        print(f"Logged in as {getattr(me, 'first_name', '') or 'the spare account'} "
              f"(@{getattr(me, 'username', None) or 'no username'}).")
        await client.disconnect()

    asyncio.run(go())
    try:
        session_path().with_suffix(".session").chmod(0o600)
    except OSError:
        pass
    print(f"The login is stored in {session_dir()} (keep it private: anyone with that file can use the account).")
    return 0


def _cli_test() -> int:
    """Rings you, plays a few beeps and reports what came back from your side. Checks the audio path without Jarvis."""
    todo = missing()
    if todo:
        print("Not ready: " + "; ".join(todo))
        return 1
    tr = TelegramTransport(target())
    print(f"Calling {target()} ... answer on your main Telegram.")
    try:
        tr.start()
    except CallError as e:
        print(f"Call failed: {e}")
        if getattr(tr, "trace", ""):
            print(tr.trace[-1800:])
        return 1
    cancel = threading.Event()
    talker = Talker(tr.send, cancel)
    t = np.arange(int(RATE * 0.5)) / RATE
    beep = float_to_pcm16(0.3 * np.sin(2 * np.pi * 660 * t))
    frames = [beep[i:i + FRAME_BYTES].ljust(FRAME_BYTES, b"\x00") for i in range(0, len(beep), FRAME_BYTES)]
    print("Connected. Playing 3 beeps; say something afterwards (8 seconds) ...")
    talker.say([(f"beep {i}", lambda: frames) for i in range(3)])
    lis = Listener()
    end = time.monotonic() + 8
    heard = 0
    while time.monotonic() < end and not tr.closed.is_set():
        try:
            for ev in lis.feed(tr.frames.get(timeout=0.2)):
                if ev[0] == "utterance":
                    heard += 1
        except queue.Empty:
            pass
    tr.stop()
    if tr.end_reason:
        print(f"The line dropped early: {tr.end_reason}.")
    print(f"Audio frames received: {tr.frames_in}; frame sizes seen: {dict(tr.frame_sizes) or 'none'}; "
          f"separate things you said: {heard}.")
    print("If you heard the beeps and the frame count is above zero, the call path works.")
    return 0


def load_dotenv(path=None) -> int:
    """For the standalone CLI only (Jarvis loads .env itself): copies KEY=VALUE lines from the project's .env into
    os.environ without overriding anything already set. Values are never printed. Returns how many were added."""
    path = path or (Path(__file__).resolve().parent / ".env")
    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return 0
    added = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        key, _, value = line.partition("=")
        key = key.strip()
        if key and not os.environ.get(key):
            os.environ[key] = value.strip().strip('"').strip("'")
            added += 1
    return added


def main(argv: list[str]) -> int:
    load_dotenv()
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "login":
        return _cli_login()
    if cmd == "test":
        return _cli_test()
    todo = missing()
    print("Telegram calls: ready." if not todo else "Telegram calls: not ready yet. Still to set up: " + "; ".join(todo))
    return 0 if not todo else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
