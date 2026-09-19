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
              confidence: float | None = None, detail: str | None = None) -> None:
    """Audit row (never contains an image or an embedding). Best-effort: never raises."""
    try:
        with _db_lock, _db() as conn:
            conn.execute(
                "INSERT INTO face_events (ts, profile_id, name, kind, confidence, detail) VALUES (?,?,?,?,?,?)",
                (_now(), profile_id, name, kind, confidence, detail),
            )
    except Exception as e:
        log.warning("face event log failed: %s", e)


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


def _key() -> bytes:
    path = _data_dir() / "face.key"
    cache_id = str(path)
    if cache_id in _key_cache:
        return _key_cache[cache_id]
    if path.exists():
        key = _dpapi(path.read_bytes(), protect=False)
    else:
        key = os.urandom(32)
        path.write_bytes(_dpapi(key, protect=True))
    _key_cache[cache_id] = key
    return key


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
    digest = hashlib.sha256(part.read_bytes()).hexdigest()
    if digest != MODEL_ZIP_SHA256:
        part.unlink(missing_ok=True)
        raise RuntimeError("Face model download failed its integrity check; refusing to use it.")
    dest = root / "models" / MODEL_PACK
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(part) as zf:
        for name in MODEL_FILES:
            with zf.open(name) as src, open(dest / name, "wb") as dst:
                dst.write(src.read())
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
        from insightface.app import FaceAnalysis

        self.app = FaceAnalysis(
            name=MODEL_PACK,
            root=str(_model_root()),
            allowed_modules=["detection", "recognition"],
            providers=["CPUExecutionProvider"],
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
    for _ in range(5):  # discard warm-up frames while auto-exposure settles
        cap.read()
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
        return (
            f"{existing[0]['name']} is already enrolled, and I only keep one profile. "
            "Say 'delete my face' first if you want to enroll again."
        )
    if is_paused():
        return "Face recognition is paused, so I won't turn the camera on. Say resume first."
    if not _camera_lock.acquire(blocking=False):
        return "The camera is busy right now. Try again in a moment."
    try:
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
        log_event("enroll_failed", name=name, detail=f"liveness: head turn {swing:.2f}", confidence=swing)
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
        cur = conn.execute(
            "INSERT INTO face_profiles (name, role, created_at, consent_at, n_samples, embeddings) "
            "VALUES (?,?,?,?,?,?)",
            (name, "admin", ts, ts, len(samples), _pack_embeddings(stored)),
        )
        pid = cur.lastrowid
    log_event("enroll", profile_id=pid, name=name, confidence=float(swing), detail="consent given by explicit enroll command")
    return f"Done, {name}. I've enrolled your face. It's stored only on this computer, encrypted, and you can delete it any time."


def delete(name: str, confirm: bool, source: str | None) -> str:
    """Remove a profile and its embeddings. The audit trail of events is kept (it holds no
    biometric data). Needs confirm=True, which the agent may only set after the user said yes."""
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
    if not confirm:
        return f"That will erase {row[1]}'s face profile. Ask the user to confirm, then call again with confirm set."
    with _db_lock, _db() as conn:
        conn.execute("DELETE FROM face_profiles WHERE id=?", (row[0],))
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
