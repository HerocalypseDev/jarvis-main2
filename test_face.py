"""Tests for jarvis_face (Phase 1). No real camera, model or network is ever touched: the
detector/camera are faked, and all data goes to a temp dir. Real Windows DPAPI *is* exercised
(it only wraps a random test key in the temp dir). Run: python -m pytest test_face.py -v"""

import contextlib
import sqlite3
import threading

import numpy as np
import pytest

import jarvis_face as face


@pytest.fixture()
def fx(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_FACE_DIR", str(tmp_path / "facedata"))
    monkeypatch.setenv("JARVIS_FACE_ENABLED", "1")
    monkeypatch.setattr(face, "FRAME_INTERVAL_S", 0)
    monkeypatch.setattr(face, "SAMPLE_GAP_S", 0)
    monkeypatch.setattr(face, "download_models", lambda progress_fn=None: None)
    return tmp_path


BASE = np.random.RandomState(7).randn(512).astype("float32")
BASE /= np.linalg.norm(BASE)


def _obs(nose_dx=0.0, emb=None, score=0.95, n=1):
    """n fake detections whose nose sits nose_dx eye-distances off the eyes' midpoint."""
    kps = np.array([[100, 100], [140, 100], [120 + nose_dx * 40, 120], [105, 140], [135, 140]], dtype="float32")
    e = BASE if emb is None else emb
    return [face.Observation((80, 80, 160, 170), kps, score, e) for _ in range(n)]


class _Cap:
    def __init__(self):
        self.released = False

    def read(self):
        return True, object()

    def release(self):
        self.released = True


class _Engine:
    """Yields a scripted list of per-frame detections, then repeats the last one."""

    def __init__(self, frames):
        self.frames, self.i = frames, 0

    def analyze(self, frame):
        out = self.frames[min(self.i, len(self.frames) - 1)]
        self.i += 1
        return out


def _install(monkeypatch, frames):
    cap = _Cap()
    monkeypatch.setattr(face, "_get_engine", lambda: _Engine(frames))
    monkeypatch.setattr(face, "_open_camera", lambda idx: cap)
    return cap


def _turning_frames():
    noisy = lambda: (BASE + np.random.RandomState(1).randn(512).astype("float32") * 0.01)
    return [_obs(0.0, noisy()) for _ in range(8)] + [_obs(-0.25), _obs(0.25)] + [_obs(0.0, noisy())]


# --- policy gates ----------------------------------------------------------------------------
def test_refuse_reason_gates(monkeypatch):
    monkeypatch.setenv("JARVIS_FACE_ENABLED", "0")
    assert "switched off" in face.refuse_reason("voice")
    monkeypatch.setenv("JARVIS_FACE_ENABLED", "1")
    assert face.refuse_reason("voice") is None
    assert face.refuse_reason("text") is None
    assert face.refuse_reason("dashboard") is None
    assert "phone" in face.refuse_reason("phone")
    assert "scheduled" in face.refuse_reason(None)  # no user command on this thread


def test_face_data_under_onedrive_is_refused(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_FACE_DIR", str(tmp_path / "OneDrive" / "Documents" / "faces"))
    with pytest.raises(RuntimeError, match="OneDrive"):
        face._data_dir()


# --- storage / encryption ---------------------------------------------------------------------
def test_embeddings_roundtrip_and_are_not_stored_in_plaintext(fx):
    arr = np.vstack([BASE, BASE * 0.5]).astype("float32")
    blob = face._pack_embeddings(arr)
    assert BASE.astype("<f4").tobytes()[:64] not in blob
    assert np.allclose(face._unpack_embeddings(blob), arr)
    with pytest.raises(Exception):
        face._decrypt(blob, b"some other purpose")  # AAD binds the ciphertext to its column


def test_key_persists_and_is_wrapped_by_dpapi(fx):
    k1 = face._key()
    face._key_cache.clear()
    assert face._key() == k1  # reloaded through DPAPI from face.key
    raw = (face._data_dir() / "face.key").read_bytes()
    assert k1 not in raw  # the file holds the wrapped key, never the key itself


# --- enrollment ------------------------------------------------------------------------------
def test_enroll_happy_path_stores_encrypted_profile_and_releases_camera(fx, monkeypatch):
    cap = _install(monkeypatch, _turning_frames())
    spoken = []
    msg = face.enroll("Hero", "voice", spoken.append)
    assert msg.startswith("Done, Hero")
    assert cap.released
    assert spoken and "turn your head" in spoken[0]
    (p,) = face.list_profiles()
    assert p["name"] == "Hero" and p["role"] == "admin" and p["n_samples"] == face.SAMPLES_WANTED
    emb = face.load_embeddings(p["id"])
    assert emb.shape == (face.SAMPLES_WANTED + 1, 512)
    with contextlib.closing(sqlite3.connect(str(face._db_path()))) as conn:
        assert conn.execute("SELECT kind FROM face_events").fetchall() == [("enroll",)]
        (blob,) = conn.execute("SELECT embeddings FROM face_profiles").fetchone()
    assert BASE.astype("<f4").tobytes()[:64] not in blob


def test_enroll_rejects_a_still_photo_with_no_head_turn(fx, monkeypatch):
    _install(monkeypatch, [_obs(0.0)])
    monkeypatch.setattr(face, "ENROLL_TIMEOUT_S", 0.3)
    msg = face.enroll("Hero", "voice")
    assert "turn your head" in msg
    assert face.list_profiles() == []


def test_enroll_stops_when_two_faces_are_in_frame(fx, monkeypatch):
    _install(monkeypatch, [_obs(0.0, n=2)])
    assert "more than one face" in face.enroll("Hero", "voice")
    assert face.list_profiles() == []


def test_enroll_rejects_mixed_identities(fx, monkeypatch):
    other = np.random.RandomState(99).randn(512).astype("float32")
    other /= np.linalg.norm(other)
    frames = [_obs(0.0, BASE), _obs(0.0, other), _obs(-0.3, BASE), _obs(0.3, other), _obs(0.0, BASE), _obs(0.0, other)]
    _install(monkeypatch, frames)
    monkeypatch.setattr(face, "ENROLL_TIMEOUT_S", 1.0)
    assert "same face" in face.enroll("Hero", "voice")
    assert face.list_profiles() == []


def test_enroll_refused_from_phone_and_scheduled_and_does_not_touch_camera(fx, monkeypatch):
    opened = []
    monkeypatch.setattr(face, "_open_camera", lambda i: opened.append(i))
    assert "phone" in face.enroll("Hero", "phone")
    assert "scheduled" in face.enroll("Hero", None)
    assert opened == []


def test_only_one_person_can_ever_be_enrolled(fx, monkeypatch):
    _install(monkeypatch, _turning_frames())
    assert face.enroll("Hero", "voice").startswith("Done")
    _install(monkeypatch, _turning_frames())
    assert "already enrolled" in face.enroll("Deborah", "voice")
    assert [p["name"] for p in face.list_profiles()] == ["Hero"]


def test_enroll_validates_name_and_pause_and_camera_errors(fx, monkeypatch):
    assert "name" in face.enroll("Hero; DROP TABLE", "voice")
    face.set_setting("paused", "1")
    assert "paused" in face.enroll("Hero", "voice")
    face.set_setting("paused", "0")

    def no_cam(i):
        raise face.CameraUnavailable("Couldn't open the camera (index 0); another app may be using it.")

    monkeypatch.setattr(face, "_get_engine", lambda: _Engine([_obs()]))
    monkeypatch.setattr(face, "_open_camera", no_cam)
    assert "Couldn't open the camera" in face.enroll("Hero", "voice")
    assert face.list_profiles() == []


def test_camera_lock_blocks_concurrent_enrollment(fx, monkeypatch):
    _install(monkeypatch, _turning_frames())
    face._camera_lock.acquire()
    try:
        assert "busy" in face.enroll("Hero", "voice")
    finally:
        face._camera_lock.release()


# --- deletion --------------------------------------------------------------------------------
def test_delete_needs_confirmation_and_erases_embeddings_but_keeps_audit(fx, monkeypatch):
    _install(monkeypatch, _turning_frames())
    face.enroll("Hero", "voice")
    assert "confirm" in face.delete("Hero", False, "voice")
    assert len(face.list_profiles()) == 1
    assert "phone" in face.delete("Hero", True, "phone")
    assert len(face.list_profiles()) == 1
    assert face.delete("hero", True, "voice").startswith("Deleted")  # names are case-insensitive
    assert face.list_profiles() == []
    with contextlib.closing(sqlite3.connect(str(face._db_path()))) as conn:
        assert [r[0] for r in conn.execute("SELECT kind FROM face_events ORDER BY id")] == ["enroll", "delete"]
        assert conn.execute("SELECT COUNT(*) FROM face_profiles").fetchone() == (0,)
    assert "don't have" in face.delete("Hero", True, "voice")


# --- model download integrity ----------------------------------------------------------------
class _Resp:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n):
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk


def test_model_download_rejects_truncated_and_tampered_files(fx, monkeypatch):
    monkeypatch.undo()  # drop the download_models stub from the fixture
    monkeypatch.setenv("JARVIS_FACE_DIR", str(fx / "facedata"))
    monkeypatch.setattr(face, "MODEL_ZIP_SIZE", 10)
    monkeypatch.setattr(face.urllib.request, "urlopen", lambda url, timeout=0: _Resp(b"12345"))
    with pytest.raises(RuntimeError, match="cut short"):
        face.download_models()
    monkeypatch.setattr(face.urllib.request, "urlopen", lambda url, timeout=0: _Resp(b"0123456789"))
    with pytest.raises(RuntimeError, match="integrity"):
        face.download_models()
    assert not face.models_ready()
    assert not list((face._model_root()).glob("*.part"))  # bad downloads are cleaned up


# --- yaw + jarvis.py wiring ------------------------------------------------------------------
def test_yaw_ratio_is_signed_and_scale_free():
    assert face.yaw_ratio(_obs(0.0)[0].kps) == pytest.approx(0.0)
    assert face.yaw_ratio(_obs(0.25)[0].kps) == pytest.approx(0.25)
    assert face.yaw_ratio(_obs(-0.25)[0].kps) == pytest.approx(-0.25)


@pytest.fixture()
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    import jarvis as j

    monkeypatch.setattr(j, "flush_pending_notifications", lambda: None)
    monkeypatch.setattr(j, "speak_text", lambda *a, **k: None)
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    return j


def test_face_tools_are_hidden_unless_the_feature_is_enabled(jarvis):
    names = {t["name"] for t in jarvis.AGENT_TOOLS}
    assert {"enroll_face", "list_faces", "delete_face"} == {t["name"] for t in jarvis.FACE_TOOLS}
    assert not ({"enroll_face", "list_faces", "delete_face"} & names)  # default: off, no tokens spent


@pytest.mark.parametrize("source,refused", [("phone", True), ("voice", False), ("text", False), ("dashboard", False)])
def test_tool_sees_the_real_command_source(jarvis, monkeypatch, fx, source, refused):
    seen = {}

    def agent(transcript, tone=None, narrate=False):
        seen["reply"] = jarvis._execute_tool_impl("enroll_face", {"name": "Hero"}, transcript)
        return "ok"

    monkeypatch.setattr(jarvis, "run_agent_loop", agent)
    _install(monkeypatch, [_obs(0.0)])
    monkeypatch.setattr(face, "ENROLL_TIMEOUT_S", 0.2)
    jarvis.handle_text_command("enroll me", source=source, reply_sink=lambda r: None)
    assert ("phone" in seen["reply"]) is refused
    assert jarvis._current_command_source() is None  # restored afterwards


def test_scheduled_thread_has_no_source_and_is_refused(jarvis, monkeypatch, fx):
    out = {}
    t = threading.Thread(
        target=lambda: out.setdefault("r", jarvis._execute_tool_impl("enroll_face", {"name": "Hero"}, "sched"))
    )
    t.start()
    t.join()
    assert "scheduled" in out["r"]
