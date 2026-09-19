"""Local-only face recognition identity layer (Phase 1: enrollment, storage, liveness).

Everything stays on this machine: detection, embedding and matching run on CPU through
insightface's `buffalo_l` ONNX pack; nothing is sent to any cloud API. A face is only ever an
identity / personalization signal — it never confirms, approves or unlocks anything, and it has
no connection to the catastrophic confirmation gate (`_pending_action`) in jarvis.py.

Storage is deliberately *outside* the repo and OneDrive: `%LOCALAPPDATA%\\Jarvis\\face.db`
(override with JARVIS_FACE_DIR; a directory under OneDrive is refused, because a synced
biometric database would leave the machine). Embeddings are AES-GCM encrypted with a random
key that is itself wrapped by Windows DPAPI, so the database is unreadable from another
Windows account or another machine. No camera frame is ever written to disk.

Policy (user decisions, 2026-09-19): exactly one enrolled person (the owner, Admin) — nobody
else is ever enrolled; enroll/delete are refused unless the command came from voice, the typed
hotkey or the dashboard (never phone, never a scheduled task).

Liveness is a head-turn challenge from the detector's 5 landmarks. It stops a held-still photo,
not a determined replay attack: a plain RGB webcam cannot, which is exactly why a face match is
never allowed to gate anything.
"""

from __future__ import annotations

import contextlib
import ctypes
import hashlib
import logging
import os
import re
import shutil
import sqlite3
import sys
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

log = logging.getLogger("jarvis")

# --- model pack (pinned: trust-on-first-use hash recorded 2026-09-19) ------------------------
MODEL_PACK = "buffalo_l"
MODEL_URL = "https://github.com/deepinsight/insightface/releases/download/model-zoo/buffalo_l.zip"
MODEL_ZIP_SIZE = 288_621_354
MODEL_ZIP_SHA256 = "80ffe37d8a5940d59a7384c201a2a38d4741f2f3c51eef46ebb28218a7b0ca2f"
MODEL_FILES = ("det_10g.onnx", "w600k_r50.onnx")  # detector + ArcFace recognizer; rest unused

# --- tuning (env-overridable; defaults are strict: better "unknown" than a wrong match) -------
MIN_DET_SCORE = 0.60
SAMPLE_DET_SCORE = 0.70
SAMPLE_MAX_YAW = 0.18  # only near-frontal frames become enrollment samples
SAMPLES_WANTED = 5
SAMPLE_GAP_S = 0.5
FRAME_INTERVAL_S = 0.25
ENROLL_TIMEOUT_S = 30.0
SAMPLE_CONSISTENCY = 0.45  # lowest cosine between any two samples; different people sit near 0
WARMUP_MIN_FRAMES = 5
WARMUP_MAX_FRAMES = 45  # ~1.5s at 30fps: the most a poll will spend waiting for exposure
WARMUP_STABLE_DELTA = 1.5  # brightness change between frames that counts as "settled"
CAMERA_WAIT_S = 6.0  # how long enroll waits for an in-flight poll to release the camera
EVENT_KEEP_DAYS_DEFAULT = 180.0
HOUSEKEEPING_EVERY_S = 3600.0
ALLOWED_SOURCES = frozenset({"voice", "text", "dashboard"})  # never "phone", never scheduled
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z '\-]{0,39}$")


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def enabled() -> bool:
    return os.environ.get("JARVIS_FACE_ENABLED", "0").strip().lower() in ("1", "true", "yes")


def liveness_min_swing() -> float:
    """How far the nose must sweep across the eyes' midline (in eye-distances) during the head
    turn. ~0.3 is roughly a 15 degree turn each way. Tune with JARVIS_FACE_LIVENESS_SWING."""
    return _float_env("JARVIS_FACE_LIVENESS_SWING", 0.30)


# --- paths -----------------------------------------------------------------------------------
def _data_dir() -> Path:
    raw = os.environ.get("JARVIS_FACE_DIR")
    base = Path(raw) if raw else Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Jarvis"
    if any(part.lower().startswith("onedrive") for part in base.resolve().parts):
        raise RuntimeError(
            f"Refusing to keep face data under OneDrive ({base}): it would sync off this machine."
        )
    base.mkdir(parents=True, exist_ok=True)
    return base


def _db_path() -> Path:
    return _data_dir() / "face.db"


def _model_root() -> Path:
    return _data_dir() / "models"


_db_lock = threading.Lock()
_camera_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS face_profiles ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE COLLATE NOCASE, "
        "role TEXT NOT NULL DEFAULT 'admin', created_at TEXT NOT NULL, consent_at TEXT NOT NULL, "
        "n_samples INTEGER NOT NULL, embeddings BLOB NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS face_events ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, profile_id INTEGER, name TEXT, "
        "kind TEXT NOT NULL, confidence REAL, detail TEXT)"
    )
    conn.execute("CREATE TABLE IF NOT EXISTS face_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS face_snapshots ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, event_id INTEGER, "
        "confidence REAL, jpeg BLOB NOT NULL)"
    )
    return conn


@contextlib.contextmanager
def _db():
    """Connection that commits on success and is always closed (sqlite3's own `with` only
    commits, so connections would otherwise pile up and hold the file open)."""
    conn = _connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def log_event(kind: str, profile_id: int | None = None, name: str | None = None,
              confidence: float | None = None, detail: str | None = None) -> int | None:
    """Audit row (never contains an image or an embedding). Best-effort: never raises.
    Returns the new row id (None if the write failed)."""
    try:
        with _db_lock, _db() as conn:
            row_id = conn.execute(
                "INSERT INTO face_events (ts, profile_id, name, kind, confidence, detail) VALUES (?,?,?,?,?,?)",
                (_now(), profile_id, name, kind, confidence, detail),
            ).lastrowid
        _emit(kind, name, confidence)
        return row_id
    except Exception as e:
        log.warning("face event log failed: %s", e)
        return None


# --- key protection: random AES key wrapped by Windows DPAPI (tied to this Windows login) ----
class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


_DPAPI_ENTROPY = b"jarvis-face-v1"


def _dpapi(data: bytes, protect: bool) -> bytes:
    if sys.platform != "win32":
        raise RuntimeError("Face storage needs Windows DPAPI; not available on this platform.")
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    blob_p = ctypes.POINTER(_DataBlob)
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    fn.argtypes = [blob_p, ctypes.c_void_p, blob_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, blob_p]
    fn.restype = ctypes.c_int
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    def blob(b: bytes):
        buf = ctypes.create_string_buffer(b, len(b))
        return _DataBlob(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    b_in, keep_in = blob(data)
    b_ent, keep_ent = blob(_DPAPI_ENTROPY)
    b_out = _DataBlob()
    if not fn(ctypes.byref(b_in), None, ctypes.byref(b_ent), None, None, 0, ctypes.byref(b_out)):
        raise OSError(f"DPAPI {'protect' if protect else 'unprotect'} failed (error {ctypes.GetLastError()})")
    try:
        return ctypes.string_at(b_out.pbData, b_out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(b_out.pbData, ctypes.c_void_p))
        del keep_in, keep_ent


_key_cache: dict[str, bytes] = {}
_key_lock = threading.Lock()


def _key() -> bytes:
    with _key_lock:  # two first-time callers must not each mint a key (the loser's data is lost)
        return _key_locked()


def _key_locked() -> bytes:
    path = _data_dir() / "face.key"
    cache_id = str(path)
    if cache_id in _key_cache:
        return _key_cache[cache_id]
    if path.exists():
        key = _dpapi(path.read_bytes(), protect=False)
    else:
        if _has_encrypted_data():
            # A fresh key would silently orphan every stored vector and picture. Stop instead.
            raise RuntimeError(
                "The face encryption key is missing, so the stored face data can't be read. "
                "Erase the face profile and enroll again."
            )
        key = os.urandom(32)
        path.write_bytes(_dpapi(key, protect=True))
    _key_cache[cache_id] = key
    return key


def _has_encrypted_data() -> bool:
    """Any encrypted rows on disk? (Read directly: must not need the key it is about to check.)"""
    db = _data_dir() / "face.db"
    if not db.exists():
        return False
    try:
        conn = sqlite3.connect(str(db), timeout=10)
        try:
            n = conn.execute(
                "SELECT (SELECT COUNT(*) FROM face_profiles) + (SELECT COUNT(*) FROM face_snapshots)"
            ).fetchone()[0]
        finally:
            conn.close()
        return n > 0
    except sqlite3.Error:
        return False


def health_problem() -> str | None:
    """A human-readable reason stored face data can't be used (key missing / unreadable), or None."""
    try:
        if _has_encrypted_data():
            _key()
            if not models_ready():
                return "The face model files are missing, so I can't recognize anyone until they are downloaded again."
    except Exception as e:
        return str(e)
    return None


def _encrypt(plain: bytes, aad: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    return nonce + AESGCM(_key()).encrypt(nonce, plain, aad)


def _decrypt(blob: bytes, aad: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    return AESGCM(_key()).decrypt(blob[:12], blob[12:], aad)


_EMB_AAD = b"face_profiles.embeddings"


def _pack_embeddings(arr: np.ndarray) -> bytes:
    return _encrypt(np.ascontiguousarray(arr, dtype="<f4").tobytes(), _EMB_AAD)


def _unpack_embeddings(blob: bytes) -> np.ndarray:
    return np.frombuffer(_decrypt(blob, _EMB_AAD), dtype="<f4").reshape(-1, 512)


# --- profiles --------------------------------------------------------------------------------
def list_profiles() -> list[dict]:
    with _db_lock, _db() as conn:
        rows = conn.execute(
            "SELECT id, name, role, created_at, consent_at, n_samples FROM face_profiles ORDER BY id"
        ).fetchall()
    return [
        {"id": r[0], "name": r[1], "role": r[2], "created_at": r[3], "consent_at": r[4], "n_samples": r[5]}
        for r in rows
    ]


def load_embeddings(profile_id: int) -> np.ndarray | None:
    with _db_lock, _db() as conn:
        row = conn.execute("SELECT embeddings FROM face_profiles WHERE id=?", (profile_id,)).fetchone()
    return _unpack_embeddings(row[0]) if row else None


def get_setting(key: str, default: str = "") -> str:
    with _db_lock, _db() as conn:
        row = conn.execute("SELECT value FROM face_settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key: str, value: str) -> None:
    with _db_lock, _db() as conn:
        conn.execute("INSERT OR REPLACE INTO face_settings (key, value) VALUES (?,?)", (key, value))


def is_paused() -> bool:
    return get_setting("paused", "0") == "1"


# --- model download (pinned size + SHA-256; extracts only the two files we use) ---------------
def models_ready() -> bool:
    d = _model_root() / "models" / MODEL_PACK
    return all((d / f).exists() for f in MODEL_FILES)


def download_models(progress_fn=None) -> None:
    """One-time fetch of the buffalo_l pack from insightface's GitHub release. insightface's own
    downloader does no integrity check (and a dropped connection leaves a silently truncated file
    — seen live), so this verifies exact size and SHA-256 before extracting anything."""
    if models_ready():
        return
    root = _model_root()
    root.mkdir(parents=True, exist_ok=True)
    part = root / f"{MODEL_PACK}.zip.part"
    if progress_fn:
        progress_fn("Downloading the face model once, this can take a minute.")
    log.info("Downloading face model pack %s (%d bytes)...", MODEL_PACK, MODEL_ZIP_SIZE)
    with urllib.request.urlopen(MODEL_URL, timeout=60) as resp, open(part, "wb") as out:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
    if part.stat().st_size != MODEL_ZIP_SIZE:
        size = part.stat().st_size
        part.unlink(missing_ok=True)
        raise RuntimeError(f"Face model download was cut short ({size} of {MODEL_ZIP_SIZE} bytes).")
    h = hashlib.sha256()
    with open(part, "rb") as f:  # chunked: the pack is ~290MB, don't hold it in memory
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != MODEL_ZIP_SHA256:
        part.unlink(missing_ok=True)
        raise RuntimeError("Face model download failed its integrity check; refusing to use it.")
    dest = root / "models" / MODEL_PACK
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(part) as zf:
        for name in MODEL_FILES:
            tmp = dest / (name + ".tmp")  # write aside, then rename: a killed extract must not
            with zf.open(name) as src, open(tmp, "wb") as dst:  # leave a truncated file that
                shutil.copyfileobj(src, dst)  # models_ready() would then accept
            os.replace(tmp, dest / name)
    part.unlink(missing_ok=True)


# --- detection + embedding engine (lazy; replaced in tests) -----------------------------------
@dataclass
class Observation:
    bbox: tuple[float, float, float, float]
    kps: np.ndarray  # 5x2: left eye, right eye, nose, left mouth, right mouth (image coordinates)
    det_score: float
    embedding: np.ndarray  # L2-normalised, 512-d


_engine = None
_engine_lock = threading.Lock()


class _InsightEngine:
    def __init__(self) -> None:
        # insightface silently downloads a missing model pack itself, with no size or hash check,
        # which would bypass the pinned download above. Refuse instead; enrolling (or
        # `python jarvis_face.py calibrate`) fetches and verifies it.
        if not models_ready():
            raise RuntimeError(
                "The face model files are missing. Enroll once, or run 'python jarvis_face.py "
                "calibrate', to download and verify them."
            )
        import onnxruntime as ort
        from insightface.app import FaceAnalysis

        # Cap ONNX Runtime's threads: by default one inference bursts across every core, which
        # can stutter the voice loop / Whisper that share this process.
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, int(_float_env("JARVIS_FACE_THREADS", 2)))
        opts.inter_op_num_threads = 1
        self.app = FaceAnalysis(
            name=MODEL_PACK,
            root=str(_model_root()),
            allowed_modules=["detection", "recognition"],
            providers=["CPUExecutionProvider"],
            sess_options=opts,
        )
        self.app.prepare(ctx_id=-1, det_size=(320, 320))

    def analyze(self, frame) -> list[Observation]:
        return [
            Observation(tuple(float(v) for v in f.bbox), np.asarray(f.kps), float(f.det_score),
                        np.asarray(f.normed_embedding, dtype="float32"))
            for f in self.app.get(frame)
        ]


def _get_engine():
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = _InsightEngine()
        return _engine


# --- camera ----------------------------------------------------------------------------------
class CameraUnavailable(RuntimeError):
    pass


def camera_index() -> int:
    try:
        return int(os.environ.get("JARVIS_FACE_CAMERA_INDEX", "0"))
    except ValueError:
        return 0


def _open_camera(index: int):
    import cv2

    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap.release()
        raise CameraUnavailable(f"Couldn't open the camera (index {index}); another app may be using it.")
    # A camera opened cold hands back washed-out frames while auto-exposure settles (seen live:
    # brightness ~100 then ~58, and no face found in the first frame). Discard frames until the
    # brightness stops moving, so every poll - each one a cold open - sees a usable image.
    last, stable = None, 0
    try:
        for i in range(WARMUP_MAX_FRAMES):
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            mean = float(frame.mean())
            stable = stable + 1 if last is not None and abs(mean - last) < WARMUP_STABLE_DELTA else 0
            last = mean
            if i >= WARMUP_MIN_FRAMES and stable >= 3:
                break
    except Exception:
        cap.release()  # never leave the camera (and its LED) on because a read blew up
        raise
    return cap


def yaw_ratio(kps: np.ndarray) -> float:
    """Signed head-turn proxy: nose offset from the eyes' midpoint, in eye-distances. ~0 facing
    the camera; grows in magnitude as the head turns."""
    eye_l, eye_r, nose = kps[0], kps[1], kps[2]
    dist = abs(float(eye_r[0] - eye_l[0])) or 1e-6
    return float((nose[0] - (eye_l[0] + eye_r[0]) / 2.0) / dist)


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v)) or 1e-9
    return v / n


# --- policy gates ----------------------------------------------------------------------------
def refuse_reason(source: str | None) -> str | None:
    """Why enroll/delete must not run for this command source, or None if it may."""
    if not enabled():
        return "Face recognition is switched off. Set JARVIS_FACE_ENABLED to 1 and restart me."
    if source not in ALLOWED_SOURCES:
        where = "the phone" if source == "phone" else "a background or scheduled task"
        return (
            f"I won't enroll or delete faces from {where}. Ask me at this computer, "
            "by voice, keyboard or the dashboard."
        )
    return None


def _clean_name(name: str) -> str | None:
    name = re.sub(r"\s+", " ", (name or "").strip())
    return name if NAME_RE.match(name) else None


# --- enrollment / deletion -------------------------------------------------------------------
def enroll(name: str, source: str | None, speak_fn=None) -> str:
    """Enroll the (single) owner. Refused unless no one is enrolled yet, so a second person can
    never be added; to re-enroll, delete the existing profile first."""
    why = refuse_reason(source)
    if why:
        return why
    clean = _clean_name(name)
    if not clean:
        return "I need a name of letters only, up to forty characters, to enroll a face."
    existing = list_profiles()
    if existing:
        return _already_enrolled(existing[0]["name"])
    if is_paused():
        return "Face recognition is paused, so I won't turn the camera on. Say resume first."
    if not _camera_lock.acquire(timeout=CAMERA_WAIT_S):  # a poll may be mid-look (~1.5s)
        return "The camera is busy right now. Try again in a moment."
    try:
        existing = list_profiles()  # another enroll may have finished while we waited for the lock
        if existing:
            return _already_enrolled(existing[0]["name"])
        try:
            download_models(speak_fn)
        except Exception as e:
            log.warning("Face model setup failed: %s", e)
            log_event("enroll_failed", name=clean, detail=f"model setup: {e}"[:200])
            return f"I couldn't set up the face model: {e}"
        try:
            engine = _get_engine()
            cap = _open_camera(camera_index())
        except CameraUnavailable as e:
            log_event("enroll_failed", name=clean, detail=str(e)[:200])
            return str(e)
        except Exception as e:
            log.warning("Face engine failed to start: %s", e)
            log_event("enroll_failed", name=clean, detail=f"engine: {e}"[:200])
            return f"The face engine wouldn't start: {e}"
        try:
            if speak_fn:
                speak_fn("Look at the camera, then slowly turn your head left and right.")
            return _run_enrollment(clean, engine, cap)
        finally:
            cap.release()
    finally:
        _camera_lock.release()


def _already_enrolled(name: str) -> str:
    return (
        f"{name} is already enrolled, and I only keep one profile. "
        "Say 'delete my face' first if you want to enroll again."
    )


def _run_enrollment(name: str, engine, cap) -> str:
    samples: list[np.ndarray] = []
    yaws: list[float] = []
    last_sample_t = -1e9
    started = time.monotonic()
    while time.monotonic() - started < ENROLL_TIMEOUT_S:
        ok, frame = cap.read()
        if not ok or frame is None:
            time.sleep(FRAME_INTERVAL_S)
            continue
        seen = [o for o in engine.analyze(frame) if o.det_score >= MIN_DET_SCORE]
        if len(seen) > 1:
            log_event("enroll_failed", name=name, detail="more than one face in frame")
            return "I can see more than one face. Enrollment has to be just you, so I stopped."
        if seen:
            obs = seen[0]
            y = yaw_ratio(obs.kps)
            yaws.append(y)
            now = time.monotonic()
            if (
                len(samples) < SAMPLES_WANTED
                and obs.det_score >= SAMPLE_DET_SCORE
                and abs(y) <= SAMPLE_MAX_YAW
                and now - last_sample_t >= SAMPLE_GAP_S
            ):
                samples.append(obs.embedding)
                last_sample_t = now
        if len(samples) >= SAMPLES_WANTED and yaws and (max(yaws) - min(yaws)) >= liveness_min_swing():
            break
        time.sleep(FRAME_INTERVAL_S)

    if len(samples) < SAMPLES_WANTED:
        log_event("enroll_failed", name=name, detail=f"only {len(samples)} usable frames")
        return "I couldn't get a clear look at your face. Face the camera in decent light and try again."
    swing = (max(yaws) - min(yaws)) if yaws else 0.0
    if swing < liveness_min_swing():
        log_event("enroll_failed", name=name, detail=f"liveness: head turn {swing:.2f} (needs {liveness_min_swing():.2f})")
        return "I didn't see you turn your head, so I can't confirm it's really you. Please try again and turn slowly."
    arr = np.stack(samples)
    centroid = _unit(arr.mean(axis=0))
    units = np.stack([_unit(s) for s in arr])
    lowest_pair = float((units @ units.T).min())  # comparing to the centroid is too forgiving:
    if lowest_pair < SAMPLE_CONSISTENCY:  # a 2-vs-3 mix of different people still scores ~0.55
        log_event("enroll_failed", name=name, detail=f"inconsistent samples min pair={lowest_pair:.2f}")
        return "The frames didn't look like the same face, so I stopped. Please try again on your own."

    stored = np.vstack([centroid[None, :], arr])  # row 0 = centroid, then the raw samples
    ts = _now()
    with _db_lock, _db() as conn:
        # Atomic "only if nobody is enrolled": the one-person rule must hold even if two enrolls race.
        cur = conn.execute(
            "INSERT INTO face_profiles (name, role, created_at, consent_at, n_samples, embeddings) "
            "SELECT ?,?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM face_profiles)",
            (name, "admin", ts, ts, len(samples), _pack_embeddings(stored)),
        )
        pid = cur.lastrowid if cur.rowcount == 1 else None
    if pid is None:
        log_event("enroll_failed", name=name, detail="someone was enrolled while this was in progress")
        return "Someone was enrolled while I was working, so I didn't add a second profile."
    invalidate_profile_cache()
    log_event("enroll", profile_id=pid, name=name, detail=f"consent given by explicit enroll command; head-turn swing {swing:.2f}")
    return f"Done, {name}. I've enrolled your face. It's stored only on this computer, encrypted, and you can delete it any time."


STAGE_TTL_S = 120.0
_staged_deletes: dict[str, tuple[float, str | None]] = {}
_stage_lock = threading.Lock()


def delete(name: str, confirm: bool, source: str | None, turn_id: str | None = None,
           ui_confirmed: bool = False) -> str:
    """Remove a profile and its embeddings. The audit trail of events is kept (it holds no
    biometric data).

    `confirm=True` is model-supplied, and "only set it after the user said yes" is just a prompt
    (a model has passed force=true unprompted before). So the code enforces it: a confirming call
    only counts if an earlier, unconfirmed call for the same profile was made within STAGE_TTL_S
    *in a different user message* (`turn_id` = that message's text), so the model cannot stage and
    confirm inside one turn. The dashboard, where a person just clicked through a browser
    confirm(), passes ui_confirmed=True."""
    why = refuse_reason(source)
    if why:
        return why
    clean = _clean_name(name)
    if not clean:
        return "Which enrolled name should I delete?"
    with _db_lock, _db() as conn:
        row = conn.execute("SELECT id, name FROM face_profiles WHERE name=?", (clean,)).fetchone()
    if not row:
        return f"I don't have a face enrolled as {clean}."
    if not ui_confirmed:
        key, now = row[1].lower(), time.time()
        with _stage_lock:
            staged = _staged_deletes.get(key)
            ok = bool(
                confirm and staged and now - staged[0] <= STAGE_TTL_S
                and (turn_id is None or staged[1] is None or staged[1] != turn_id)
            )
            if not ok:
                _staged_deletes[key] = (now, turn_id)
            else:
                _staged_deletes.pop(key, None)
        if not ok:
            if confirm:
                return (
                    "I need the user's yes in a separate message first. Ask them whether to erase "
                    f"{row[1]}'s face profile, then call again once they've said yes."
                )
            return f"That will erase {row[1]}'s face profile. Ask the user to confirm, then call again with confirm set."
    with _db_lock, _db() as conn:
        conn.execute("DELETE FROM face_profiles WHERE id=?", (row[0],))
    invalidate_profile_cache()
    _reset_presence_serialized()  # otherwise "Hero is at the computer" lingers in the prompt for ~90s
    set_setting("away_mode", "0")  # with no face enrolled, away mode could only misfire
    log_event("delete", profile_id=row[0], name=row[1], detail="profile and embeddings erased")
    return f"Deleted {row[1]}'s face profile. Nothing biometric is left on this computer."


def describe_profiles() -> str:
    if not enabled():
        return "Face recognition is switched off."
    profiles = list_profiles()
    if not profiles:
        return "No faces are enrolled."
    p = profiles[0]
    return f"{p['name']} is enrolled as {p['role']}, since {p['created_at'][:10]}, with {p['n_samples']} samples."


# ===============================================================================================
# Phase 2: recognition, presence, group-safe mode, unknown-face pictures
# ===============================================================================================
COVER_MEAN, COVER_STD = 6.0, 3.0  # a covered lens is near-black AND flat; a dark room isn't flat
UNKNOWN_CONFIRM_POLLS = 2  # an unknown face must be seen on 2 polls in a row (drops one-frame noise)
UNKNOWN_CLEAR_S = 60.0
STATE_STALE_S = 90.0  # presence older than this is not trusted (thread stalled / paused / asleep)
GREETING_COOLDOWN_S = 1800.0
CAMERA_FAILS_BEFORE_NOTICE = 5
FAIL_BACKOFF_S = 60.0
SNAPSHOT_DEDUPE_S = 600.0
SNAPSHOT_MAX = 200
SNAPSHOT_MAX_SIDE = 256


def match_threshold() -> float:
    """Cosine similarity needed to call a face "the owner". Strict on purpose: a false unknown
    is only a quiet-mode blip, a false match is the worse error. Tune from the confidences in
    face_events (unknown rows record how close the best match was)."""
    return _float_env("JARVIS_FACE_MATCH_THRESHOLD", 0.50)


def poll_interval() -> float:
    return max(2.0, _float_env("JARVIS_FACE_POLL_S", 5.0))


def settled_poll_interval() -> float:
    """Once the owner has been steadily in view with nobody else, look less often (each look is
    ~0.4s of CPU and lights the camera LED), so the steady state is even lower duty."""
    return max(poll_interval(), _float_env("JARVIS_FACE_SETTLED_POLL_S", 15.0))


def owner_absent_after_s() -> float:
    return _float_env("JARVIS_FACE_ABSENT_S", 120.0)


def save_unknown_enabled() -> bool:
    return os.environ.get("JARVIS_FACE_SAVE_UNKNOWN", "1").strip().lower() in ("1", "true", "yes")


def snapshot_keep_days() -> float:
    return _float_env("JARVIS_FACE_SNAPSHOT_DAYS", 14.0)


# --- matching --------------------------------------------------------------------------------
_profile_cache: list[tuple[dict, np.ndarray]] | None = None
_profile_cache_lock = threading.Lock()


def invalidate_profile_cache() -> None:
    global _profile_cache
    with _profile_cache_lock:
        _profile_cache = None


def _profiles_for_matching() -> list[tuple[dict, np.ndarray]]:
    global _profile_cache
    with _profile_cache_lock:
        if _profile_cache is None:
            loaded = []
            for prof in list_profiles():
                emb = load_embeddings(prof["id"])
                if emb is not None and len(emb):
                    loaded.append((prof, np.stack([_unit(e) for e in emb])))
            _profile_cache = loaded
        return _profile_cache


def identify(embedding: np.ndarray) -> tuple[dict | None, float]:
    """(profile, score) if the embedding matches an enrolled face at or above the threshold,
    else (None, best_score_seen)."""
    e = _unit(np.asarray(embedding, dtype="float32"))
    best_prof, best = None, -1.0
    for prof, embs in _profiles_for_matching():
        score = float((embs @ e).max())
        if score > best:
            best_prof, best = prof, score
    if best_prof is not None and best >= match_threshold():
        return best_prof, best
    return None, best


# --- presence state --------------------------------------------------------------------------
@dataclass
class _Presence:
    owner_present: bool = False
    owner_name: str | None = None
    owner_conf: float | None = None
    owner_last_seen: float = 0.0
    unknown_present: bool = False
    unknown_streak: int = 0
    unknown_last_seen: float = 0.0
    covered: bool = False
    camera_fails: int = 0
    camera_alert_sent: bool = False
    updated_at: float = 0.0
    absent_since: float = 0.0  # away mode: when the owner was first NOT seen (0 = not absent)
    away_warned: bool = False


_st = _Presence()
_st_lock = threading.Lock()
_recent_unknowns: list[list] = []  # [embedding, last_seen]; RAM only, never persisted


def _noop(*a, **k):
    return None


_hooks = {
    "greet": _noop, "notify": _noop, "quiet": lambda: False, "release": _noop,
    "stranger": _noop, "stranger_left": _noop, "lock": _noop, "away_warn": _noop,
    "locked": None,  # filled below with the real session-lock probe
}


def _reset_transient() -> None:
    """Forget live presence (feature paused / asleep / nothing enrolled): stale "someone is
    there" state must never keep group-safe mode on with nobody looking."""
    with _st_lock:
        _st.owner_present = False
        _st.unknown_present = False
        _st.unknown_streak = 0
        _st.covered = False
        _st.updated_at = 0.0
        _st.absent_since = 0.0
        _st.away_warned = False
    _recent_unknowns.clear()


# --- away mode --------------------------------------------------------------------------------
# A mode the owner switches on. While it is on, and the camera can see, and the owner has not been
# recognized for AWAY_GRACE seconds, the workstation is LOCKED (after a spoken warning). Face only
# ever locks - nothing here can unlock anything - and a camera that can't see (covered, busy in a
# call, unreachable, paused) never counts as "owner not shown", so those cases never lock.
AWAY_GRACE_DEFAULT = 120.0
AWAY_WARN_DEFAULT = 15.0


def away_grace_s() -> float:
    return max(10.0, _float_env("JARVIS_FACE_AWAY_GRACE_S", AWAY_GRACE_DEFAULT))


def away_warn_s() -> float:
    return max(0.0, min(_float_env("JARVIS_FACE_AWAY_WARN_S", AWAY_WARN_DEFAULT), away_grace_s() - 5.0))


def away_enabled() -> bool:
    return get_setting("away_mode", "0") == "1"


def _session_locked() -> bool:
    """True while the Windows lock screen (secure desktop) is up: the camera is off-limits then,
    and there is nothing left to lock."""
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        user32.OpenInputDesktop.restype = ctypes.c_void_p
        user32.CloseDesktop.argtypes = [ctypes.c_void_p]
        handle = user32.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_SWITCHDESKTOP
        if not handle:
            return True  # can't open the input desktop -> the secure (lock) desktop is showing
        user32.CloseDesktop(handle)
        return False
    except Exception:
        return False


_hooks["locked"] = _session_locked


def _away_reset() -> None:
    with _st_lock:
        _st.absent_since = 0.0
        _st.away_warned = False


def _away_step(now: float, owner_seen: bool, out: list) -> None:
    """Advance the away timer after a poll in which the camera could see. Warn once shortly
    before the grace period ends, then lock."""
    if not away_enabled() or owner_seen:
        _away_reset()
        return
    grace, warn = away_grace_s(), away_warn_s()
    action = None
    with _st_lock:
        if _st.absent_since == 0.0:
            _st.absent_since = now  # the first poll that couldn't find the owner starts the clock
            return
        absent = now - _st.absent_since
        if absent >= grace:
            action, _st.absent_since, _st.away_warned = "lock", 0.0, False
        elif warn > 0 and absent >= grace - warn and not _st.away_warned:
            action, _st.away_warned = "warn", True
    if action == "lock":
        log_event("away_lock", detail=f"owner not seen for {int(absent)}s; locking the computer")
        out.append(("lock",))
    elif action == "warn":
        log_event("away_warning", detail=f"owner not seen for {int(absent)}s; locking in ~{int(warn)}s")
        out.append(("away_warn", f"I can't see you. Locking the computer in {int(warn)} seconds."))


def set_away(on: bool, source: str | None) -> str:
    """Away-mode switch. Turning it ON is always fine (it only adds protection) but needs an
    enrolled face, otherwise nobody could ever be "shown" and it would lock constantly. Turning it
    OFF removes protection, so it must come from this computer, like re-enabling the camera."""
    if not enabled():
        return "Face recognition is switched off, so away mode isn't available."
    if on:
        if not list_profiles():
            return "Enroll your face first; without it I couldn't tell you're here and would lock you out."
        set_setting("away_mode", "1")
        _away_reset()
        log_event("away_on", detail=f"source={source}")
        note = " Face recognition is paused, so it won't lock until you resume it." if is_paused() else ""
        return (
            f"Away mode is on. If I can't see you for {int(away_grace_s() // 60) or 1} "
            f"minute{'s' if away_grace_s() >= 120 else ''}, I'll lock the computer, with a warning first." + note
        )
    why = refuse_reason(source)
    if why:
        return why.replace("enroll or delete faces", "turn away mode off")
    set_setting("away_mode", "0")
    _away_reset()
    log_event("away_off", detail=f"source={source}")
    return "Away mode is off."


def away_status() -> str:
    if not enabled():
        return "Face recognition is switched off."
    if not away_enabled():
        return "Away mode is off."
    return f"Away mode is on: I lock the computer after {int(away_grace_s())} seconds without seeing you."


def state_snapshot() -> dict:
    with _st_lock:
        return {
            "owner_present": _st.owner_present,
            "owner_name": _st.owner_name,
            "owner_confidence": _st.owner_conf,
            "unknown_present": _st.unknown_present,
            "camera_covered": _st.covered,
            "camera_unreachable": _st.camera_alert_sent,
            "updated_at": _st.updated_at,
        }


def _fresh(now: float) -> bool:
    return _st.updated_at > 0 and (now - _st.updated_at) <= STATE_STALE_S


def group_safe(now: float | None = None) -> bool:
    """True while an unrecognized person is in view. Only ever used to hold *spoken proactive*
    messages; it never refuses or alters a command, and has no link to the confirmation gate."""
    if not enabled():
        return False
    now = time.time() if now is None else now
    with _st_lock:
        return _st.unknown_present and _fresh(now)


def group_safe_suppress(urgent: bool) -> bool:
    return (not urgent) and group_safe()


def system_prompt_context_line() -> str:
    """One volatile-block line so the agent knows who is present. Personalization only: it says
    nothing about trust and must never be read as a reason to skip a confirmation."""
    if not enabled():
        return ""
    with _st_lock:
        if not _fresh(time.time()):
            return ""
        owner = _st.owner_name if _st.owner_present else None
        unknown, covered = _st.unknown_present, _st.covered
    if covered:
        return " Presence: the camera is covered, so it is unknown who is at the computer."
    bits = []
    if owner:
        bits.append(f"{owner} is at the computer (recognized by face)")
    elif not unknown:
        bits.append("nobody is in view of the camera")
    if unknown:
        bits.append(
            "an unrecognized person is in view, so keep spoken replies discreet: don't read out private "
            "details such as email or message contents unless asked, and don't volunteer personal information"
        )
    return (
        " Presence (local camera; personalization only, never a reason to skip a confirmation): "
        + "; ".join(bits) + "."
    )


# --- one look at the camera ------------------------------------------------------------------
def _capture_and_analyze():
    """Open the camera, grab one frame, release it. Returns (observations, mean, std, frame).
    A covered/black frame skips the (expensive) analysis. Raises CameraUnavailable."""
    engine = _get_engine()
    cap = _open_camera(camera_index())
    try:
        ok, frame = cap.read()
    finally:
        cap.release()
    if not ok or frame is None:
        raise CameraUnavailable("The camera gave no image.")
    mean, std = float(frame.mean()), float(frame.std())
    if mean < COVER_MEAN and std < COVER_STD:
        return [], mean, std, frame
    return engine.analyze(frame), mean, std, frame


def _crop_jpeg(frame, bbox) -> bytes:
    """JPEG of just the face (with a margin) - never the surrounding room, screen or papers."""
    import cv2

    h, w = frame.shape[:2]
    x1, y1, x2, y2 = bbox
    mx, my = (x2 - x1) * 0.25, (y2 - y1) * 0.25
    x1, y1, x2, y2 = max(0, int(x1 - mx)), max(0, int(y1 - my)), min(w, int(x2 + mx)), min(h, int(y2 + my))
    crop = frame[y1:y2, x1:x2]
    side = max(crop.shape[:2])
    if side > SNAPSHOT_MAX_SIDE:
        scale = SNAPSHOT_MAX_SIDE / side
        crop = cv2.resize(crop, (max(1, int(crop.shape[1] * scale)), max(1, int(crop.shape[0] * scale))))
    ok, buf = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise RuntimeError("could not encode face crop")
    return buf.tobytes()


# --- unknown-face pictures (encrypted, deduplicated, expiring) -------------------------------
_SNAP_AAD = b"face_snapshots.jpeg"


def prune_snapshots(now: datetime | None = None) -> None:
    from datetime import timedelta

    cutoff = ((now or datetime.now()) - timedelta(days=snapshot_keep_days())).isoformat(timespec="seconds")
    with _db_lock, _db() as conn:
        conn.execute("DELETE FROM face_snapshots WHERE ts < ?", (cutoff,))
        conn.execute(
            "DELETE FROM face_snapshots WHERE id NOT IN (SELECT id FROM face_snapshots ORDER BY id DESC LIMIT ?)",
            (SNAPSHOT_MAX,),
        )


def event_keep_days() -> float:
    return _float_env("JARVIS_FACE_EVENT_DAYS", EVENT_KEEP_DAYS_DEFAULT)


def prune_events(now: datetime | None = None) -> None:
    from datetime import timedelta

    cutoff = ((now or datetime.now()) - timedelta(days=event_keep_days())).isoformat(timespec="seconds")
    with _db_lock, _db() as conn:
        conn.execute("DELETE FROM face_events WHERE ts < ?", (cutoff,))


_last_housekeeping = 0.0


def housekeeping(now: float | None = None, force: bool = False) -> bool:
    """Enforce the retention promises (unknown pictures 14 days, events 180 days) on a timer.
    Before this, pictures were only pruned when a *new* one was saved, so an old picture could
    sit past its expiry indefinitely. Returns True if it ran."""
    global _last_housekeeping
    now = time.time() if now is None else now
    if not force and now - _last_housekeeping < HOUSEKEEPING_EVERY_S:
        return False
    _last_housekeeping = now
    try:
        prune_snapshots()
        prune_events()
    except Exception as e:
        log.warning("face housekeeping failed: %s", e)
    return True


def _save_snapshot(jpeg: bytes, confidence: float, event_id: int | None) -> None:
    with _db_lock, _db() as conn:
        conn.execute(
            "INSERT INTO face_snapshots (ts, event_id, confidence, jpeg) VALUES (?,?,?,?)",
            (_now(), event_id, confidence, _encrypt(jpeg, _SNAP_AAD)),
        )
    prune_snapshots()


def list_snapshots(limit: int = 50) -> list[dict]:
    with _db_lock, _db() as conn:
        rows = conn.execute(
            "SELECT id, ts, event_id, confidence FROM face_snapshots ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [{"id": r[0], "ts": r[1], "event_id": r[2], "confidence": r[3]} for r in rows]


def get_snapshot(snapshot_id: int) -> bytes | None:
    with _db_lock, _db() as conn:
        row = conn.execute("SELECT jpeg FROM face_snapshots WHERE id=?", (snapshot_id,)).fetchone()
    return _decrypt(row[0], _SNAP_AAD) if row else None


def delete_all_snapshots() -> int:
    with _db_lock, _db() as conn:
        n = conn.execute("SELECT COUNT(*) FROM face_snapshots").fetchone()[0]
        conn.execute("DELETE FROM face_snapshots")
    if n:
        log_event("snapshots_deleted", detail=f"{n} unknown-face pictures erased")
    return n


def _already_seen_recently(embedding: np.ndarray, now: float) -> bool:
    """Same unknown person as one photographed in the last 10 minutes? Kept in RAM only (a
    stranger's embedding is never written to disk); a continuous stay counts as one visit."""
    _recent_unknowns[:] = [r for r in _recent_unknowns if now - r[1] <= SNAPSHOT_DEDUPE_S]
    e = _unit(embedding)
    for rec in _recent_unknowns:
        if float(np.dot(_unit(rec[0]), e)) >= match_threshold():
            rec[1] = now
            return True
    _recent_unknowns.append([e, now])
    return False


# --- the poll ---------------------------------------------------------------------------------
def _greeting_text(name: str) -> str:
    h = datetime.now().hour
    return f"Good {'morning' if h < 12 else 'afternoon' if h < 18 else 'evening'}, {name}."


def _camera_failed(err: Exception, out: list) -> None:
    with _st_lock:
        _st.camera_fails += 1
        alert = _st.camera_fails >= CAMERA_FAILS_BEFORE_NOTICE and not _st.camera_alert_sent
        if alert:
            _st.camera_alert_sent = True
    if alert:
        log_event("camera_unreachable", detail=str(err)[:200])
        out.append(("notify", "I can't reach the camera right now; another app may be using it, or it's unplugged."))


def _camera_ok() -> None:
    with _st_lock:
        restored = _st.camera_alert_sent
        _st.camera_fails = 0
        _st.camera_alert_sent = False
    if restored:
        log_event("camera_restored")


_poll_lock = threading.Lock()


def poll_once(now: float | None = None) -> str:
    """One recognition cycle. Returns a short status word (used by tests and who_is_here).
    Serialized: the poll thread and a voice-triggered who_is_here must not interleave state
    updates (each would otherwise see the other's half-finished presence)."""
    out: list = []
    with _poll_lock:
        status = _poll_once_locked(now, out)
    # Speaking / notifying can take many seconds (TTS, a summarizer call); doing it while holding
    # the poll lock would freeze who_is_here and the dashboard's pause/erase behind it.
    for hook, *args in out:
        fn = _hooks.get(hook)
        if fn is None:
            continue
        try:
            fn(*args)
        except Exception as e:
            log.warning("face %s hook failed: %s", hook, e)
    return status


def _reset_presence_serialized() -> None:
    """Reset live presence *after* any in-flight poll finishes, so that poll cannot write a
    stale "owner present"/"stranger present" back over the reset (pause / erase)."""
    with _poll_lock:
        _reset_transient()


def _poll_once_locked(now: float | None, out: list) -> str:
    now = time.time() if now is None else now
    if not enabled() or is_paused():
        _reset_transient()
        return "off"
    if _hooks["quiet"]():  # Sleep Mode: no camera, no polling
        _reset_transient()
        return "quiet"
    if (_hooks.get("locked") or (lambda: False))():  # already locked: the camera is off-limits, nothing left to lock
        _reset_transient()
        return "locked"
    profiles = list_profiles()
    if not profiles:
        _away_reset()
        return "no-profile"
    if not _camera_lock.acquire(blocking=False):  # an enrollment owns the camera right now
        _away_reset()
        return "busy"
    try:
        try:
            obs, mean, std, frame = _capture_and_analyze()
        except CameraUnavailable as e:
            _away_reset()  # can't see = can't tell whether they're gone: never lock on a blind camera
            _camera_failed(e, out)
            return "camera-error"
    finally:
        _camera_lock.release()
    _camera_ok()

    with _st_lock:
        _st.updated_at = now
    owner = profiles[0]

    covered_now = mean < COVER_MEAN and std < COVER_STD
    with _st_lock:
        was_covered, _st.covered = _st.covered, covered_now
    if covered_now:
        _away_reset()
        if not was_covered:
            log_event("camera_covered", detail=f"mean brightness {mean:.1f}")
            out.append(("notify", f"{owner['name']}, the camera looks covered, so I can't see the room."))
        return "covered"
    if was_covered:
        log_event("camera_uncovered")

    known, unknown = [], []
    for o in obs:
        if o.det_score < MIN_DET_SCORE:
            continue
        prof, score = identify(o.embedding)
        (known if prof else unknown).append((o, prof, score))

    # --- owner
    arrived = left = False
    if known:
        _o, prof, score = max(known, key=lambda k: k[2])
        with _st_lock:
            _st.owner_last_seen, _st.owner_conf, _st.owner_name = now, score, prof["name"]
            arrived, _st.owner_present = (not _st.owner_present), True
        if arrived:
            log_event("owner_arrived", prof["id"], prof["name"], score)
            _maybe_greet(prof["name"], now, out)
    else:
        with _st_lock:
            if _st.owner_present and now - _st.owner_last_seen > owner_absent_after_s():
                _st.owner_present, left = False, True
        if left:
            log_event("owner_left", owner["id"], owner["name"])

    _away_step(now, bool(known), out)

    # --- unknown people
    released = False
    if unknown:
        with _st_lock:
            _st.unknown_streak += 1
            _st.unknown_last_seen = now
            declared = _st.unknown_streak >= UNKNOWN_CONFIRM_POLLS
            newly = declared and not _st.unknown_present
            if declared:
                _st.unknown_present = True
        if declared:
            for o, _p, score in unknown:
                event_id = None
                if newly:
                    event_id = log_event(
                        "unknown_seen", confidence=score,
                        detail=f"best match {score:.2f} < threshold {match_threshold():.2f}",
                    )
                    newly = False
                    out.append(("stranger",))
                _maybe_snapshot(frame, o, score, event_id, now)
    else:
        with _st_lock:
            _st.unknown_streak = 0
            if _st.unknown_present and now - _st.unknown_last_seen > UNKNOWN_CLEAR_S:
                _st.unknown_present, released = False, True
        if released:
            log_event("unknown_left")
            out.append(("stranger_left",))  # before "release": state must update before held items flush
            out.append(("release",))
    return "ok"


def _maybe_greet(name: str, now: float, out: list) -> None:
    try:
        last = float(get_setting("last_greeting", "0") or 0)
    except ValueError:
        last = 0.0
    if now - last < GREETING_COOLDOWN_S:
        return
    set_setting("last_greeting", str(now))
    out.append(("greet", _greeting_text(name)))


def _maybe_snapshot(frame, obs: Observation, score: float, event_id: int | None, now: float) -> None:
    """Picture of an unknown face: only if enabled, only a real face (high detector score), and
    only once per person per visit."""
    if not save_unknown_enabled() or obs.det_score < SAMPLE_DET_SCORE:
        return
    if _already_seen_recently(obs.embedding, now):
        return
    try:
        _save_snapshot(_crop_jpeg(frame, obs.bbox), score, event_id)
    except Exception as e:
        log.warning("Could not save unknown-face picture: %s", e)


# --- polling thread ---------------------------------------------------------------------------
_poll_thread: threading.Thread | None = None
_poll_stop = threading.Event()
POLL_ERROR_BACKOFF_S = 300.0


def _lower_thread_priority() -> None:
    """Run the poll below normal priority so an inference burst yields to the voice loop."""
    if sys.platform != "win32":
        return
    try:
        k32 = ctypes.windll.kernel32
        k32.GetCurrentThread.restype = ctypes.c_void_p
        k32.SetThreadPriority.argtypes = [ctypes.c_void_p, ctypes.c_int]
        k32.SetThreadPriority(k32.GetCurrentThread(), -1)  # THREAD_PRIORITY_BELOW_NORMAL
    except Exception as e:
        log.debug("could not lower face poll priority: %s", e)


def start_polling(greet_fn=None, notify_fn=None, quiet_fn=None, release_fn=None,
                  stranger_fn=None, stranger_left_fn=None, lock_fn=None, away_warn_fn=None,
                  locked_fn=None) -> bool:
    """Start the low-duty background poll (no-op unless JARVIS_FACE_ENABLED=1). The callbacks
    keep this module free of any import of jarvis.py: greet_fn speaks the greeting, notify_fn
    delivers a proactive notice, quiet_fn says Sleep Mode is on, release_fn runs when an
    unrecognized person leaves. stranger_fn / stranger_left_fn fire when one is first declared /
    has gone; lock_fn locks the workstation (away mode) and away_warn_fn speaks the warning before
    it; locked_fn overrides the session-lock probe."""
    global _poll_thread
    if not enabled():
        return False
    _hooks.update(
        greet=greet_fn or _noop, notify=notify_fn or _noop,
        quiet=quiet_fn or (lambda: False), release=release_fn or _noop,
        stranger=stranger_fn or _noop, stranger_left=stranger_left_fn or _noop,
        lock=lock_fn or _noop, away_warn=away_warn_fn or _noop,
        locked=locked_fn or _session_locked,
    )
    if _poll_thread and _poll_thread.is_alive():
        return True
    _poll_stop.clear()

    def loop() -> None:
        _lower_thread_priority()
        errors = 0
        while not _poll_stop.is_set():
            failed = False
            try:
                housekeeping()
                poll_once()
                errors = 0
            except Exception as e:
                errors += 1
                failed = True
                log.warning("Face poll failed (%d): %s", errors, e)
            if failed and errors >= 3:
                # Was: give up for good (a fixed model / restored camera was never noticed until a
                # restart). Now: back off and keep trying; the dashboard's health note says why.
                _poll_stop.wait(POLL_ERROR_BACKOFF_S)
                continue
            with _st_lock:
                fails = _st.camera_fails
                settled = _st.owner_present and not _st.unknown_present and _st.absent_since == 0.0
            wait = FAIL_BACKOFF_S if fails >= CAMERA_FAILS_BEFORE_NOTICE else (
                settled_poll_interval() if settled else poll_interval())
            _poll_stop.wait(wait)

    _poll_thread = threading.Thread(target=loop, daemon=True, name="face-poll")
    _poll_thread.start()
    log.info("Face recognition polling started (every %ds, %ds once settled).", poll_interval(), settled_poll_interval())
    return True


def stop_polling() -> None:
    _poll_stop.set()


# --- voice-facing helpers ---------------------------------------------------------------------
def describe_presence(refresh: bool = True) -> str:
    if not enabled():
        return "Face recognition is switched off."
    if is_paused():
        return "Face recognition is paused, so I'm not looking through the camera."
    if not list_profiles():
        return "No one is enrolled yet, so I can't recognize anyone."
    if refresh:
        with _st_lock:
            fresh = _fresh(time.time())
        if not fresh:
            status = poll_once()
            if status == "quiet":
                return "Sleep Mode is on, so I'm not watching the camera."
            if status == "camera-error":
                return "I can't reach the camera right now."
    snap = state_snapshot()
    if snap["camera_covered"]:
        return "The camera is covered, so I can't tell who's there."
    parts = []
    if snap["owner_present"]:
        conf = snap["owner_confidence"]
        parts.append(f"{snap['owner_name']} is at the computer" + (f", with {int(conf * 100)} percent confidence" if conf else ""))
    if snap["unknown_present"]:
        parts.append("there's also someone I don't recognize")
    if not parts:
        return "I can't see anyone right now."
    text = ", and ".join(parts) + "."
    return text[0].upper() + text[1:]


def set_paused(paused: bool, source: str | None) -> str:
    """Camera privacy switch. Pausing is always allowed (it can only make things more private);
    resuming turns a camera on, so it is refused from phone and unattended tasks."""
    if not paused:
        why = refuse_reason(source)
        if why:
            return why.replace("enroll or delete faces", "turn the camera back on")
    was = is_paused()
    set_setting("paused", "1" if paused else "0")
    if paused:
        _reset_presence_serialized()
    if was != paused:
        log_event("paused" if paused else "resumed", detail=f"source={source}")
    return "Face recognition paused. The camera stays off." if paused else "Face recognition resumed."


# ===============================================================================================
# Phase 3: dashboard-facing helpers (read models, export, delete-by-id). Nothing here ever
# returns an embedding; pictures are only ever returned by get_snapshot() one at a time.
# ===============================================================================================
_event_hook = None


def set_event_hook(fn) -> None:
    """fn(event_dict) is called after every audit row (kind/name/confidence/ts only) so the
    dashboard can refresh live. Best-effort; a failing hook never affects recognition."""
    global _event_hook
    _event_hook = fn


def _emit(kind: str, name: str | None, confidence: float | None) -> None:
    hook = _event_hook
    if hook is None:
        return
    try:
        hook({"kind": kind, "name": name, "confidence": confidence, "ts": _now()})
    except Exception as e:
        log.debug("face event hook failed: %s", e)


def recent_events(limit: int = 100, offset: int = 0, kind: str | None = None) -> list[dict]:
    limit, offset = max(1, min(int(limit), 500)), max(0, int(offset))
    sql = "SELECT id, ts, profile_id, name, kind, confidence, detail FROM face_events"
    args: list = []
    if kind:
        sql += " WHERE kind = ?"
        args.append(kind)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    with _db_lock, _db() as conn:
        rows = conn.execute(sql, (*args, limit, offset)).fetchall()
    return [
        {"id": r[0], "ts": r[1], "profile_id": r[2], "name": r[3], "kind": r[4], "confidence": r[5], "detail": r[6]}
        for r in rows
    ]


def event_kinds() -> list[str]:
    with _db_lock, _db() as conn:
        return [r[0] for r in conn.execute("SELECT DISTINCT kind FROM face_events ORDER BY kind")]


def snapshot_count() -> int:
    with _db_lock, _db() as conn:
        return conn.execute("SELECT COUNT(*) FROM face_snapshots").fetchone()[0]


def _consent_summary(profile: dict) -> dict:
    return {
        "consent_given_at": profile["consent_at"],
        "how": "explicit enroll command, with a head-turn check, at this computer",
        "stored": [
            f"{profile['n_samples'] + 1} encrypted face vectors (numbers, not images)",
            "audit events: when you were recognized, confidence, and enroll/delete actions",
        ],
        "never_stored": [
            "camera frames or video of you",
            "your face vectors in plain form, in OneDrive, or on any server",
        ],
        "who_can_read_it": "only this Windows account on this computer (key protected by Windows DPAPI)",
        "how_to_remove": "the Erase button here, or say 'delete my face'",
    }


def dashboard_state() -> dict:
    """Everything the Identity tab shows in one call. Touches no disk when the feature is off."""
    if not enabled():
        return {"enabled": False}
    profiles = list_profiles()
    return {
        "enabled": True,
        "paused": is_paused(),
        "polling": bool(_poll_thread and _poll_thread.is_alive()),
        "presence": state_snapshot(),
        "profiles": [{**p, "consent": _consent_summary(p)} for p in profiles],
        "snapshot_count": snapshot_count(),
        "settings": {
            "poll_seconds": poll_interval(),
            "settled_poll_seconds": settled_poll_interval(),
            "match_threshold": match_threshold(),
            "save_unknown_pictures": save_unknown_enabled(),
            "picture_keep_days": snapshot_keep_days(),
            "camera_index": camera_index(),
            "absent_after_seconds": owner_absent_after_s(),
        },
        "event_kinds": event_kinds(),
        "away": {
            "enabled": away_enabled(),
            "grace_seconds": away_grace_s(),
            "warn_seconds": away_warn_s(),
            "absent_seconds": (max(0, int(time.time() - _st.absent_since)) if _st.absent_since else 0),
        },
        "problem": health_problem(),
    }


def export_profile(profile_id: int) -> dict | None:
    """A person's own data, as JSON: profile record, consent summary and their audit events.
    Deliberately excludes the face vectors (biometric, and useless to the person) and every
    unknown-visitor picture (those belong to other people)."""
    prof = next((p for p in list_profiles() if p["id"] == profile_id), None)
    if prof is None:
        return None
    with _db_lock, _db() as conn:
        rows = conn.execute(
            "SELECT id, ts, kind, confidence, detail FROM face_events WHERE profile_id = ? OR name = ? ORDER BY id",
            (profile_id, prof["name"]),
        ).fetchall()
    log_event("export", profile_id, prof["name"], detail="profile exported from the dashboard")
    return {
        "exported_at": _now(),
        "profile": {k: prof[k] for k in ("name", "role", "created_at", "consent_at", "n_samples")},
        "consent": _consent_summary(prof),
        "events": [{"id": r[0], "ts": r[1], "kind": r[2], "confidence": r[3], "detail": r[4]} for r in rows],
        "note": "Face vectors and unknown-visitor pictures are intentionally not included.",
    }


def delete_by_id(profile_id: int, source: str | None) -> str:
    prof = next((p for p in list_profiles() if p["id"] == profile_id), None)
    if prof is None:
        return "No such face profile."
    return delete(prof["name"], True, source, ui_confirmed=True)


def calibrate(seconds: float = 10.0, out=print) -> dict:
    """Dry run of the enrollment liveness check that stores NOTHING (no profile, no image, no
    event): reports the head-turn swing and detector scores it sees, so JARVIS_FACE_LIVENESS_SWING
    can be tuned on a real head turn before enrolling."""
    download_models(out)
    engine, cap = _get_engine(), _open_camera(camera_index())
    yaws, scores, frames, faces = [], [], 0, 0
    try:
        out(f"Look at the camera, then slowly turn your head left and right ({seconds:.0f}s)...")
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            frames += 1
            seen = [o for o in engine.analyze(frame) if o.det_score >= MIN_DET_SCORE]
            if len(seen) == 1:
                faces += 1
                yaws.append(yaw_ratio(seen[0].kps))
                scores.append(seen[0].det_score)
            time.sleep(FRAME_INTERVAL_S)
    finally:
        cap.release()
    swing = (max(yaws) - min(yaws)) if yaws else 0.0
    result = {
        "frames": frames, "single_face_frames": faces, "swing": round(swing, 3),
        "min_yaw": round(min(yaws), 3) if yaws else None, "max_yaw": round(max(yaws), 3) if yaws else None,
        "best_det_score": round(max(scores), 3) if scores else None,
        "needed_swing": liveness_min_swing(), "would_pass": swing >= liveness_min_swing() and faces >= SAMPLES_WANTED,
    }
    out(f"Result: {result}")
    if not faces:
        out("No single face was seen: face the camera in decent light with nobody else in frame.")
    elif swing < liveness_min_swing():
        out(f"Head turn {swing:.2f} is below the {liveness_min_swing():.2f} needed. Turn further, or lower "
            f"JARVIS_FACE_LIVENESS_SWING to about {max(0.10, swing * 0.7):.2f}.")
    else:
        out("That head turn would pass. Nothing was saved.")
    return result


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Jarvis face recognition helpers")
    ap.add_argument("command", choices=["calibrate"], help="calibrate: non-storing head-turn test")
    ap.add_argument("--seconds", type=float, default=10.0)
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    calibrate(args.seconds)
