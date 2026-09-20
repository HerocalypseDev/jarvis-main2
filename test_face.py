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
    monkeypatch.setattr(face, "_st", face._Presence())
    monkeypatch.setattr(face, "_hooks", {"greet": face._noop, "notify": face._noop, "quiet": lambda: False, "release": face._noop})
    face._recent_unknowns.clear()
    face.invalidate_profile_cache()
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


OTHER_FACE = np.random.RandomState(99).randn(512).astype("float32")
OTHER_FACE /= np.linalg.norm(OTHER_FACE)
OTHER_FACE2 = np.random.RandomState(123).randn(512).astype("float32")
OTHER_FACE2 /= np.linalg.norm(OTHER_FACE2)


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


def _person_frames(emb):
    e = lambda: (emb + np.random.RandomState(2).randn(512).astype("float32") * 0.01)
    return [_obs(0.0, e()) for _ in range(8)] + [_obs(-0.25, emb), _obs(0.25, emb)] + [_obs(0.0, e())]


def test_multiple_people_can_be_enrolled_with_roles(fx, monkeypatch):
    _install(monkeypatch, _turning_frames())
    assert "as admin" in face.enroll("Hero", "voice")
    _install(monkeypatch, _person_frames(OTHER_FACE))
    assert "as user" in face.enroll("Deborah", "voice")
    _install(monkeypatch, _person_frames(OTHER_FACE2))
    assert "as guest" in face.enroll("Sam", "voice", role="guest")
    assert [(p["name"], p["role"]) for p in face.list_profiles()] == [("Hero", "admin"), ("Deborah", "user"), ("Sam", "guest")]
    assert face.identify(OTHER_FACE)[0]["name"] == "Deborah"  # profiles are told apart
    assert face.identify(OTHER_FACE2)[0]["name"] == "Sam"
    assert face.identify(BASE)[0]["name"] == "Hero"
    assert "Deborah is enrolled as user" in face.describe_profiles() and "Sam" in face.describe_profiles()


def test_second_admin_is_refused_and_bad_role_too(fx, monkeypatch):
    _install(monkeypatch, _turning_frames())
    face.enroll("Hero", "voice")
    _install(monkeypatch, _person_frames(OTHER_FACE))
    assert "already an Admin" in face.enroll("Deborah", "voice", role="admin")
    assert "user or guest" in face.enroll("Deborah", "voice", role="root")
    assert len(face.list_profiles()) == 1


def test_first_person_is_admin_whatever_role_was_asked(fx, monkeypatch):
    _install(monkeypatch, _turning_frames())
    assert "as admin" in face.enroll("Hero", "voice", role="guest")


def test_same_face_or_name_cannot_be_enrolled_twice(fx, monkeypatch):
    _install(monkeypatch, _turning_frames())
    face.enroll("Hero", "voice")
    _install(monkeypatch, _turning_frames())
    assert "already enrolled as Hero" in face.enroll("Deborah", "voice")  # same face, new name
    assert "already enrolled" in face.enroll("hero", "voice")  # same name (case-insensitive)
    assert [p["name"] for p in face.list_profiles()] == ["Hero"]


def test_admin_cannot_be_deleted_while_others_remain(fx, monkeypatch):
    _install(monkeypatch, _turning_frames())
    face.enroll("Hero", "voice")
    _install(monkeypatch, _person_frames(OTHER_FACE))
    face.enroll("Deborah", "voice")
    assert "is the Admin" in face.delete("Hero", True, "dashboard", ui_confirmed=True)
    assert len(face.list_profiles()) == 2
    assert "Deleted Deborah" in face.delete("Deborah", True, "dashboard", ui_confirmed=True)
    assert "Deleted Hero" in face.delete("Hero", True, "dashboard", ui_confirmed=True)
    assert face.list_profiles() == []


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
    monkeypatch.setattr(face, "CAMERA_WAIT_S", 0.05)
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

    if not hasattr(j, "_real_flush_pending"):
        j._real_flush_pending = j.flush_pending_notifications
    monkeypatch.setattr(j, "flush_pending_notifications", lambda: None)
    monkeypatch.setattr(j, "speak_text", lambda *a, **k: None)
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    return j


def _tool_names_with_feature(flag: str) -> set:
    """Import jarvis in a fresh process with JARVIS_FACE_ENABLED set explicitly, so the result never
    depends on the developer's own .env (dotenv does not override variables that are already set)."""
    import json
    import os
    import subprocess
    import sys

    env = {**os.environ, "JARVIS_FACE_ENABLED": flag, "JARVIS_DASHBOARD_ENABLED": "0"}
    out = subprocess.run(
        [sys.executable, "-c", "import json, jarvis; print(json.dumps([t['name'] for t in jarvis.AGENT_TOOLS]))"],
        capture_output=True, text=True, env=env, timeout=120, cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    assert out.returncode == 0, out.stderr[-500:]
    return set(json.loads(out.stdout.strip().splitlines()[-1]))


def test_face_tools_are_hidden_unless_the_feature_is_enabled(jarvis):
    face_names = {t["name"] for t in jarvis.FACE_TOOLS}
    assert {"enroll_face", "list_faces", "delete_face", "who_is_here", "face_privacy"} <= face_names
    assert not (face_names & _tool_names_with_feature("0"))  # default: off, no tokens spent
    assert face_names <= _tool_names_with_feature("1")  # on: all advertised


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


# ===============================================================================================
# Phase 2: recognition, presence, group-safe, snapshots
# ===============================================================================================
import time  # noqa: E402

OTHER = np.random.RandomState(99).randn(512).astype("float32")
OTHER /= np.linalg.norm(OTHER)
OTHER2 = np.random.RandomState(123).randn(512).astype("float32")
OTHER2 /= np.linalg.norm(OTHER2)
FRAME = (np.random.RandomState(5).rand(480, 640, 3) * 200 + 20).astype("uint8")


@pytest.fixture()
def enrolled(fx):
    with face._db_lock, face._db() as conn:
        conn.execute(
            "INSERT INTO face_profiles (name, role, created_at, consent_at, n_samples, embeddings) VALUES (?,?,?,?,?,?)",
            ("Hero", "admin", "2026-09-19T10:00:00", "2026-09-19T10:00:00", 5, face._pack_embeddings(np.vstack([BASE, BASE]))),
        )
    face.invalidate_profile_cache()
    return fx


def _look(monkeypatch, obs=(), mean=100.0, std=40.0):
    monkeypatch.setattr(face, "_capture_and_analyze", lambda: (list(obs), mean, std, FRAME))


def _kinds():
    with contextlib.closing(sqlite3.connect(str(face._db_path()))) as conn:
        return [r[0] for r in conn.execute("SELECT kind FROM face_events ORDER BY id")]


def test_identify_matches_owner_and_rejects_strangers(enrolled):
    prof, score = face.identify(BASE)
    assert prof["name"] == "Hero" and score == pytest.approx(1.0, abs=1e-3)
    assert face.identify(OTHER)[0] is None
    near = BASE * 0.6 + OTHER * 0.8  # cosine ~0.6 to the owner
    assert face.identify(near / np.linalg.norm(near))[0] is not None
    faint = BASE * 0.3 + OTHER * 0.95  # cosine ~0.3: below the strict threshold
    assert face.identify(faint / np.linalg.norm(faint))[0] is None


def test_owner_arrival_greets_once_then_cooldown(enrolled, monkeypatch):
    greetings = []
    face._hooks["greet"] = greetings.append
    _look(monkeypatch, _obs(0.0, BASE))
    t = 1_000_000.0
    assert face.poll_once(t) == "ok"
    assert len(greetings) == 1 and "Hero" in greetings[0]
    face.poll_once(t + 5)  # still there: no second greeting
    # leaves, comes back within the cooldown: logged as an arrival, not greeted again
    _look(monkeypatch, [])
    face.poll_once(t + 10 + face.owner_absent_after_s() + 1)
    _look(monkeypatch, _obs(0.0, BASE))
    face.poll_once(t + 400)
    assert len(greetings) == 1
    assert _kinds() == ["owner_arrived", "owner_left", "owner_arrived"]


def test_greeting_cooldown_survives_restart_via_settings(enrolled, monkeypatch):
    greetings = []
    face._hooks["greet"] = greetings.append
    _look(monkeypatch, _obs(0.0, BASE))
    face.poll_once(2_000_000.0)
    face._st = face._Presence()  # simulate a restart: in-memory state gone
    face.poll_once(2_000_060.0)
    assert len(greetings) == 1


def test_unknown_needs_two_polls_then_holds_and_logs(enrolled, monkeypatch):
    _look(monkeypatch, _obs(0.0, OTHER))
    t = 3_000_000.0
    face.poll_once(t)
    assert not face.group_safe(t)  # one sighting could be noise
    face.poll_once(t + 5)
    assert face.group_safe(t + 5)
    assert "unknown_seen" in _kinds()
    assert len(face.list_snapshots()) == 1


def test_unknown_picture_is_encrypted_face_crop_and_deduplicated(enrolled, monkeypatch):
    _look(monkeypatch, _obs(0.0, OTHER))
    t = 4_000_000.0
    for i in range(6):  # one stranger lingering: exactly one picture
        face.poll_once(t + i * 5)
    assert len(face.list_snapshots()) == 1
    snap = face.list_snapshots()[0]
    jpeg = face.get_snapshot(snap["id"])
    assert jpeg[:2] == b"\xff\xd8"  # decrypts to a real JPEG
    with contextlib.closing(sqlite3.connect(str(face._db_path()))) as conn:
        (raw,) = conn.execute("SELECT jpeg FROM face_snapshots").fetchone()
    assert raw[:2] != b"\xff\xd8" and jpeg not in raw  # ...but is never stored as one
    import cv2

    crop = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert crop.shape[0] < FRAME.shape[0] and crop.shape[1] < FRAME.shape[1]  # a crop, not the frame
    _look(monkeypatch, _obs(0.0, OTHER2))  # a *different* stranger: a second picture
    face.poll_once(t + 40)
    face.poll_once(t + 45)
    assert len(face.list_snapshots()) == 2
    # the first one comes back after a 10+ minute gap: a new visit
    _look(monkeypatch, _obs(0.0, OTHER))
    for i in range(2):
        face.poll_once(t + 5000 + i * 5)
    assert len(face.list_snapshots()) == 3


def test_no_picture_when_disabled_or_face_score_is_low(enrolled, monkeypatch):
    monkeypatch.setenv("JARVIS_FACE_SAVE_UNKNOWN", "0")
    _look(monkeypatch, _obs(0.0, OTHER))
    for i in range(3):
        face.poll_once(5_000_000.0 + i * 5)
    assert face.list_snapshots() == []
    monkeypatch.setenv("JARVIS_FACE_SAVE_UNKNOWN", "1")
    face._st = face._Presence()
    _look(monkeypatch, _obs(0.0, OTHER2, score=0.65))  # detected, but not a confident face
    for i in range(3):
        face.poll_once(5_100_000.0 + i * 5)
    assert face.list_snapshots() == []


def test_unknown_leaving_releases_held_messages(enrolled, monkeypatch):
    released = []
    face._hooks["release"] = lambda: released.append(1)
    _look(monkeypatch, _obs(0.0, OTHER))
    t = 6_000_000.0
    face.poll_once(t)
    face.poll_once(t + 5)
    _look(monkeypatch, [])
    face.poll_once(t + 30)
    assert not released  # not gone for long enough yet
    face.poll_once(t + 5 + face.UNKNOWN_CLEAR_S + 1)
    assert released == [1] and _kinds()[-1] == "unknown_left"
    assert not face.group_safe()


def test_stale_presence_is_never_trusted(enrolled, monkeypatch):
    _look(monkeypatch, _obs(0.0, OTHER))
    now = time.time()
    face.poll_once(now)
    face.poll_once(now + 1)
    assert face.group_safe(now + 2)
    assert not face.group_safe(now + face.STATE_STALE_S + 10)  # the poller died: fail open


def test_covered_camera_notifies_once_per_cover(enrolled, monkeypatch):
    notes = []
    face._hooks["notify"] = notes.append
    t = 7_000_000.0
    _look(monkeypatch, [], mean=1.0, std=0.5)
    assert face.poll_once(t) == "covered"
    face.poll_once(t + 5)
    face.poll_once(t + 10)
    assert len(notes) == 1 and "covered" in notes[0] and _kinds() == ["camera_covered"]
    _look(monkeypatch, _obs(0.0, BASE))
    face.poll_once(t + 15)
    assert _kinds()[1] == "camera_uncovered"
    _look(monkeypatch, [], mean=1.0, std=0.5)
    face.poll_once(t + 20)
    assert len(notes) == 2  # a second cover is a new event


def test_a_dark_room_is_not_a_covered_camera(enrolled, monkeypatch):
    notes = []
    face._hooks["notify"] = notes.append
    _look(monkeypatch, [], mean=4.0, std=9.0)  # dim but with detail (a night-time room)
    assert face.poll_once(8_000_000.0) == "ok" and notes == []


def test_unreachable_camera_notifies_after_repeated_failures_then_recovers(enrolled, monkeypatch):
    notes = []
    face._hooks["notify"] = notes.append

    def dead():
        raise face.CameraUnavailable("busy")

    monkeypatch.setattr(face, "_capture_and_analyze", dead)
    for i in range(face.CAMERA_FAILS_BEFORE_NOTICE - 1):
        assert face.poll_once(9_000_000.0 + i) == "camera-error"
    assert notes == []  # a brief blip (e.g. another app grabbing the camera) stays quiet
    face.poll_once(9_000_100.0)
    face.poll_once(9_000_105.0)
    assert len(notes) == 1 and "can't reach the camera" in notes[0]
    _look(monkeypatch, [])
    face.poll_once(9_000_200.0)
    assert _kinds() == ["camera_unreachable", "camera_restored"]


def test_poll_never_touches_the_camera_when_off_asleep_busy_or_unenrolled(enrolled, monkeypatch):
    used = []
    monkeypatch.setattr(face, "_capture_and_analyze", lambda: used.append(1) or ([], 100.0, 40.0, FRAME))
    face.set_paused(True, "voice")
    assert face.poll_once() == "off"
    face.set_paused(False, "voice")
    face._hooks["quiet"] = lambda: True  # Sleep Mode
    assert face.poll_once() == "quiet"
    face._hooks["quiet"] = lambda: False
    assert face._camera_lock.acquire(blocking=False)
    try:
        assert face.poll_once() == "busy"  # an enrollment is using it
    finally:
        face._camera_lock.release()
    assert used == []
    with face._db_lock, face._db() as conn:
        conn.execute("DELETE FROM face_profiles")
    face.invalidate_profile_cache()
    assert face.poll_once() == "no-profile" and used == []


def test_sleep_or_pause_clears_group_safe(enrolled, monkeypatch):
    _look(monkeypatch, _obs(0.0, OTHER))
    now = time.time()
    face.poll_once(now)
    face.poll_once(now + 1)
    assert face.group_safe()
    face._hooks["quiet"] = lambda: True
    face.poll_once(now + 2)
    assert not face.group_safe()


def test_snapshot_retention_and_cap_and_delete_all(enrolled, monkeypatch):
    from datetime import datetime, timedelta

    monkeypatch.setattr(face, "SNAPSHOT_MAX", 3)
    for i in range(5):
        face._save_snapshot(b"\xff\xd8jpeg%d" % i, 0.1, None)
    assert len(face.list_snapshots()) == 3  # capped, oldest dropped
    face.prune_snapshots(now=datetime.now() + timedelta(days=15))
    assert face.list_snapshots() == []  # older than 14 days
    face._save_snapshot(b"\xff\xd8x", 0.1, None)
    assert face.delete_all_snapshots() == 1 and face.list_snapshots() == []
    assert "snapshots_deleted" in _kinds()


def test_privacy_switch_pause_anywhere_resume_only_at_the_pc(fx):
    assert "paused" in face.set_paused(True, "phone")  # more private: always fine
    assert face.is_paused()
    assert "phone" in face.set_paused(False, "phone") and face.is_paused()
    assert "scheduled" in face.set_paused(False, None) and face.is_paused()
    assert "resumed" in face.set_paused(False, "voice") and not face.is_paused()
    assert _kinds() == ["paused", "resumed"]


def test_prompt_line_reflects_presence_and_is_empty_when_stale_or_off(enrolled, monkeypatch):
    assert face.system_prompt_context_line() == ""  # nothing observed yet
    now = time.time()
    _look(monkeypatch, _obs(0.0, BASE))
    face.poll_once(now)
    line = face.system_prompt_context_line()
    assert "Hero is at the computer" in line and "never a reason to skip a confirmation" in line
    _look(monkeypatch, _obs(0.0, BASE) + _obs(0.0, OTHER))
    face.poll_once(now + 1)
    face.poll_once(now + 2)
    assert "unrecognized person" in face.system_prompt_context_line()
    face._st.updated_at = time.time() - 1000
    assert face.system_prompt_context_line() == ""
    monkeypatch.setenv("JARVIS_FACE_ENABLED", "0")
    assert face.system_prompt_context_line() == ""


def test_who_is_here_wording(enrolled, monkeypatch):
    _look(monkeypatch, _obs(0.0, BASE))
    assert face.describe_presence().startswith("Hero is at the computer")
    _look(monkeypatch, _obs(0.0, BASE) + _obs(0.0, OTHER))
    face._st.updated_at = 0  # force a fresh look
    face.poll_once()
    face.poll_once()
    assert "someone I don't recognize" in face.describe_presence()
    face.set_paused(True, "voice")
    assert "paused" in face.describe_presence()


def test_polling_thread_starts_only_when_enabled_and_stops(fx, monkeypatch):
    monkeypatch.setenv("JARVIS_FACE_ENABLED", "0")
    assert face.start_polling() is False
    monkeypatch.setenv("JARVIS_FACE_ENABLED", "1")
    calls = []
    monkeypatch.setattr(face, "poll_once", lambda now=None: calls.append(1) or "ok")
    monkeypatch.setattr(face, "_poll_thread", None)
    assert face.start_polling() is True
    deadline = time.time() + 2
    while not calls and time.time() < deadline:
        time.sleep(0.02)
    face.stop_polling()
    assert calls


# --- jarvis.py integration ---------------------------------------------------------------------
@pytest.fixture()
def quiet_jarvis(jarvis, monkeypatch):
    spoken = []
    monkeypatch.setattr(jarvis, "flush_pending_notifications", jarvis._real_flush_pending)
    monkeypatch.setattr(jarvis, "_session_context", jarvis._default_session_context())
    monkeypatch.setattr(jarvis, "_save_session_context_locked", lambda: None)
    monkeypatch.setattr(jarvis, "refresh_session_context", lambda: None)
    monkeypatch.setattr(jarvis, "_notify_phone", lambda *a, **k: None)
    monkeypatch.setattr(jarvis, "_speak_shaped", spoken.append)
    monkeypatch.setattr(jarvis.focus_mode, "should_suppress", lambda urgent, *a: False)
    monkeypatch.setattr(jarvis.sleep_mode, "should_suppress", lambda urgent, *a, **k: False)
    monkeypatch.setattr(jarvis.sleep_mode, "is_active", lambda: False)
    monkeypatch.setattr(jarvis, "user_is_actively_working", lambda: False)
    return jarvis, spoken


def test_stranger_in_view_holds_proactive_speech_but_not_urgent(quiet_jarvis, monkeypatch):
    j, spoken = quiet_jarvis
    monkeypatch.setattr(face, "group_safe", lambda now=None: True)
    j.queue_or_deliver_notification("You have new mail from the bank.")
    assert spoken == []
    held = j._session_context["pending_notifications"]
    assert held and held[0]["group_safe"] is True
    j.queue_or_deliver_notification("Your build failed.", urgent=True)
    assert spoken == ["Your build failed."]  # urgent still comes through, as in Sleep/Focus Mode


def test_held_messages_wait_for_the_stranger_then_release(quiet_jarvis, monkeypatch):
    j, spoken = quiet_jarvis
    state = {"safe": True}
    monkeypatch.setattr(face, "group_safe", lambda now=None: state["safe"])
    j.queue_or_deliver_notification("Private thing.")
    j.flush_pending_notifications()  # the user gives a command while the guest is still there
    assert spoken == [] and len(j._session_context["pending_notifications"]) == 1
    state["safe"] = False  # guest leaves -> the face poller calls this
    j._face_release_held_notifications()
    assert spoken == ["Private thing."] and j._session_context["pending_notifications"] == []


def test_greeting_is_skipped_around_a_stranger_or_sleep(quiet_jarvis, monkeypatch):
    j, _ = quiet_jarvis
    said = []
    monkeypatch.setattr(j, "speak_text", said.append)
    monkeypatch.setattr(face, "group_safe", lambda now=None: False)
    j._face_greet("Good morning, Hero.")
    assert said == ["Good morning, Hero."]
    monkeypatch.setattr(face, "group_safe", lambda now=None: True)
    j._face_greet("Good morning, Hero.")
    monkeypatch.setattr(face, "group_safe", lambda now=None: False)
    monkeypatch.setattr(j.sleep_mode, "is_active", lambda: True)
    j._face_greet("Good morning, Hero.")
    assert said == ["Good morning, Hero."]  # not repeated; nothing queued for later either


def test_presence_line_lands_in_the_volatile_block_only(jarvis, monkeypatch, enrolled):
    now = time.time()
    _look(monkeypatch, _obs(0.0, BASE))
    face.poll_once(now)
    stable, volatile = jarvis.build_system_blocks("")
    assert "Hero is at the computer" in volatile["text"]
    assert "Hero is at the computer" not in stable["text"]  # keeps the cached prefix stable


def test_face_privacy_tool_pause_from_phone_works_resume_does_not(jarvis, monkeypatch, fx):
    def agent(source, action):
        out = {}

        def run(transcript, tone=None, narrate=False):
            out["r"] = jarvis._execute_tool_impl("face_privacy", {"action": action}, transcript)
            return "ok"

        monkeypatch.setattr(jarvis, "run_agent_loop", run)
        jarvis.handle_text_command("x", source=source, reply_sink=lambda r: None)
        return out["r"]

    assert "paused" in agent("phone", "pause")
    assert "phone" in agent("phone", "resume") and face.is_paused()
    assert "resumed" in agent("voice", "resume") and not face.is_paused()


def test_camera_warmup_waits_for_exposure_to_settle(monkeypatch):
    import cv2

    means = [100, 92, 80, 70, 62, 58, 58.2, 58.1, 58.3, 58.2, 58.0, 58.1]
    seq = iter(means)

    class FakeCap:
        reads = 0

        def isOpened(self):
            return True

        def read(self):
            FakeCap.reads += 1
            return True, np.full((4, 4, 3), next(seq, 58.0), dtype="float32")

        def release(self):
            pass

    monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: FakeCap())
    cap = face._open_camera(0)
    assert FakeCap.reads >= 8  # kept discarding while the image was still brightening/dimming
    assert FakeCap.reads < face.WARMUP_MAX_FRAMES  # ...but stopped once it settled
    ok, frame = cap.read()
    assert abs(float(frame.mean()) - 58.0) < 1.0  # the frame a poll analyzes is the settled one


def test_camera_warmup_is_bounded_when_exposure_never_settles(monkeypatch):
    import cv2

    class FlickerCap:
        reads = 0

        def isOpened(self):
            return True

        def read(self):
            FlickerCap.reads += 1
            return True, np.full((4, 4, 3), 50.0 + (FlickerCap.reads % 2) * 40, dtype="float32")

        def release(self):
            pass

    monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: FlickerCap())
    face._open_camera(0)
    assert FlickerCap.reads == face.WARMUP_MAX_FRAMES


# ===============================================================================================
# Phase 3: dashboard Identity endpoints
# ===============================================================================================
@pytest.fixture()
def dash(enrolled):
    from fastapi.testclient import TestClient

    import jarvis_dashboard as dashboard

    app = dashboard._build_app(face=face)
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


def _snap(n=1):
    for i in range(n):
        face._save_snapshot(b"\xff\xd8\xff\xe0fakejpeg%d" % i, 0.12, None)


def test_identity_off_returns_disabled_and_never_touches_disk(fx, monkeypatch):
    from fastapi.testclient import TestClient

    import jarvis_dashboard as dashboard

    monkeypatch.setenv("JARVIS_FACE_ENABLED", "0")
    with TestClient(dashboard._build_app(face=face), base_url="http://127.0.0.1:8765") as c:
        assert c.get("/api/faces").json() == {"enabled": False}
        assert c.get("/api/faces/events").json() == {"rows": []}
        assert c.get("/api/faces/snapshots").json() == {"rows": []}
        assert c.delete("/api/faces/1?confirm=true").status_code == 404
        assert c.post("/api/faces/pause", json={"paused": True}).status_code == 404
    assert not (fx / "facedata" / "face.db").exists()  # a machine without the feature gets no DB


def test_identity_without_a_face_provider_is_disabled(monkeypatch):
    from fastapi.testclient import TestClient

    import jarvis_dashboard as dashboard

    with TestClient(dashboard._build_app(), base_url="http://127.0.0.1:8765") as c:
        assert c.get("/api/faces").json() == {"enabled": False}


def test_identity_state_has_profile_consent_and_no_face_vectors(dash):
    r = dash.get("/api/faces")
    body = r.json()
    assert r.headers["cache-control"] == "no-store"
    assert body["enabled"] is True and body["paused"] is False
    (p,) = body["profiles"]
    assert p["name"] == "Hero" and p["consent"]["consent_given_at"]
    assert any("never" in x or "camera frames" in x for x in p["consent"]["never_stored"])
    assert body["settings"]["match_threshold"] == 0.5 and body["settings"]["save_unknown_pictures"] is True
    assert "embeddings" not in r.text  # the column name / vectors never leave the server


ROUTES = [
    ("get", "/api/faces"),
    ("get", "/api/faces/events"),
    ("get", "/api/faces/snapshots"),
    ("get", "/api/faces/snapshots/1/image"),
    ("get", "/api/faces/1/export"),
    ("delete", "/api/faces/snapshots"),
    ("delete", "/api/faces/1?confirm=true"),
]


@pytest.mark.parametrize("method,path", ROUTES)
def test_face_routes_reject_a_non_loopback_host_header(dash, method, path):
    """DNS-rebinding defence: a hostile page re-pointing its domain at 127.0.0.1 sends its own Host."""
    _snap()
    r = getattr(dash, method)(path, headers={"host": "evil.example.com:8765"})
    assert r.status_code == 403
    r = dash.post("/api/faces/pause", json={"paused": True}, headers={"host": "evil.example.com"})
    assert r.status_code == 403 and not face.is_paused()
    assert getattr(dash, method)(path, headers={"host": "localhost:8765"}).status_code != 403


def test_events_endpoint_filters_orders_and_clamps(dash):
    for k in ("owner_arrived", "unknown_seen", "owner_left"):
        face.log_event(k, name="Hero", confidence=0.8, detail="x")
    rows = dash.get("/api/faces/events").json()["rows"]
    assert [r["kind"] for r in rows] == ["owner_left", "unknown_seen", "owner_arrived"]  # newest first
    assert [r["kind"] for r in dash.get("/api/faces/events?kind=unknown_seen").json()["rows"]] == ["unknown_seen"]
    assert len(dash.get("/api/faces/events?limit=1").json()["rows"]) == 1
    assert len(dash.get("/api/faces/events?limit=99999").json()["rows"]) == 3  # clamped, not an error
    assert set(dash.get("/api/faces").json()["event_kinds"]) == {"owner_arrived", "unknown_seen", "owner_left"}


def test_snapshot_endpoints_list_serve_and_delete(dash):
    _snap(2)
    rows = dash.get("/api/faces/snapshots").json()["rows"]
    assert len(rows) == 2 and set(rows[0]) == {"id", "ts", "event_id", "confidence"}  # no image bytes in the list
    img = dash.get(f"/api/faces/snapshots/{rows[0]['id']}/image")
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert img.headers["cache-control"] == "no-store" and img.headers["x-content-type-options"] == "nosniff"
    assert img.content.startswith(b"\xff\xd8")
    assert dash.get("/api/faces/snapshots/9999/image").status_code == 404
    assert dash.delete("/api/faces/snapshots").json() == {"ok": True, "removed": 2}
    assert dash.get("/api/faces/snapshots").json()["rows"] == []


def test_export_contains_own_data_but_no_vectors_or_visitor_pictures(dash):
    _snap()
    face.log_event("owner_arrived", 1, "Hero", 0.8)
    r = dash.get("/api/faces/1/export")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    data = r.json()
    assert data["profile"]["name"] == "Hero" and data["consent"]["how_to_remove"]
    assert any(e["kind"] == "owner_arrived" for e in data["events"])
    assert "embeddings" not in r.text and "jpeg" not in r.text.lower() and "fakejpeg" not in r.text
    assert "export" in [e["kind"] for e in face.recent_events()]  # exporting is itself audited
    assert dash.get("/api/faces/999/export").status_code == 404


def test_delete_profile_needs_confirm_and_uses_dashboard_source(dash):
    assert dash.delete("/api/faces/1").status_code == 400  # a bare DELETE erases nothing
    assert len(face.list_profiles()) == 1
    r = dash.delete("/api/faces/1?confirm=true")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert face.list_profiles() == []
    assert dash.delete("/api/faces/1?confirm=true").status_code == 404
    assert face.recent_events(kind="delete")[0]["name"] == "Hero"  # audit row survives the erase


def test_pause_and_resume_from_the_dashboard(dash):
    r = dash.post("/api/faces/pause", json={"paused": True}).json()
    assert r["ok"] and r["paused"] is True and face.is_paused()
    assert dash.get("/api/faces").json()["paused"] is True
    r = dash.post("/api/faces/pause", json={"paused": False}).json()
    assert r["paused"] is False and not face.is_paused()


def test_event_hook_gets_labels_only_and_a_broken_hook_is_harmless(enrolled):
    seen = []
    face.set_event_hook(seen.append)
    try:
        face.log_event("unknown_seen", None, None, 0.31, "best match 0.31")
        assert seen and set(seen[0]) == {"kind", "name", "confidence", "ts"}  # no image/vector fields

        def boom(_ev):
            raise RuntimeError("dashboard down")

        face.set_event_hook(boom)
        assert face.log_event("owner_left", 1, "Hero") is not None  # still logged
    finally:
        face.set_event_hook(None)


def test_frontend_has_the_identity_tab_wired_to_the_api():
    import pathlib

    root = pathlib.Path(__file__).parent / "dashboard_static"
    html, js = (root / "index.html").read_text(encoding="utf-8"), (root / "app.js").read_text(encoding="utf-8")
    assert 'data-tab="identity"' in html and 'id="tab-identity"' in html
    for path in ("/api/faces", "/api/faces/events", "/api/faces/snapshots", "/api/faces/pause", "?confirm=true"):
        assert path in js
    assert 'event.type === "face_event"' in js  # live refresh
    assert "confirm(" in js  # erase / delete-all ask first


# ===============================================================================================
# Phase 4: hardening
# ===============================================================================================
def test_face_code_cannot_reach_the_confirmation_gate():
    """Structural guard for the core rule: a face is personalization only. jarvis_face must not
    touch the gate, and jarvis.py may reference `face` only in the (reviewed) places below."""
    import ast
    import pathlib

    root = pathlib.Path(__file__).parent
    face_tree = ast.parse((root / "jarvis_face.py").read_text(encoding="utf-8"))
    used = set()
    for n in ast.walk(face_tree):  # code only: the module docstring may discuss the gate in prose
        if isinstance(n, ast.Name):
            used.add(n.id)
        elif isinstance(n, ast.Attribute):
            used.add(n.attr)
        elif isinstance(n, ast.arg):
            used.add(n.arg)
        elif isinstance(n, ast.keyword) and n.arg:
            used.add(n.arg)
        elif isinstance(n, ast.Import):
            used.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            used.add(n.module or "")
    for forbidden in ("_pending_action", "_execute_confirmed_action", "skip_confirmation", "_CATASTROPHIC_PATTERNS", "jarvis"):
        assert forbidden not in used, forbidden

    tree = ast.parse((root / "jarvis.py").read_text(encoding="utf-8"))
    users = set()
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(isinstance(n, ast.Name) and n.id == "face" for n in ast.walk(fn)):
                users.add(fn.name)
    allowed = {
        "_execute_tool_impl",  # the face tools' own dispatch branches
        "_face_greet", "queue_or_deliver_notification", "flush_pending_notifications",  # speech hold/greeting
        "build_system_blocks", "run_agent_loop",  # presence line (+ reply-cache key)
        "_reminders_held_now",  # visitor present -> hold a due reminder (speech + toast)
        "main",  # start polling / event hook
    }
    assert users <= allowed, f"face is referenced from unreviewed code: {sorted(users - allowed)}"
    for gate in ("_take_pending_action", "_execute_confirmed_action", "_dashboard_approve_pending", "_dashboard_reject_pending"):
        assert gate not in users

    # Away mode is the first time a face event acts on the machine. It may only LOCK: no unlock
    # anywhere in the face module, and the injected action is jarvis's lock helper (LockWorkStation).
    assert not any("unlock" in name.lower() for name in used), [n for n in used if "unlock" in n.lower()]
    jarvis_src = (root / "jarvis.py").read_text(encoding="utf-8")
    assert "lock_fn=_system_action_lock" in jarvis_src
    lock_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_system_action_lock")
    assert {n.attr for n in ast.walk(lock_fn) if isinstance(n, ast.Attribute)} >= {"LockWorkStation"}

    # The reminder-policy module (driven by face events) must not touch the gate either.
    gr_tree = ast.parse((root / "jarvis_guest_reminders.py").read_text(encoding="utf-8"))
    gr_used = {n.id for n in ast.walk(gr_tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(gr_tree) if isinstance(n, ast.Attribute)}
    for forbidden in ("_pending_action", "_execute_confirmed_action", "skip_confirmation", "_take_pending_action", "jarvis", "face"):
        assert forbidden not in gr_used, forbidden


def test_no_image_or_frame_is_ever_written_to_disk(enrolled, monkeypatch):
    import cv2

    monkeypatch.setattr(cv2, "imwrite", lambda *a, **k: (_ for _ in ()).throw(AssertionError("frame written")))
    _look(monkeypatch, _obs(0.0, OTHER))
    t = 11_000_000.0
    for i in range(4):  # an unknown visitor: the one path that keeps a (crop) picture, in the DB
        face.poll_once(t + i * 5)
    _install(monkeypatch, _turning_frames())
    with face._db_lock, face._db() as conn:
        conn.execute("DELETE FROM face_profiles")
    face.invalidate_profile_cache()
    assert face.enroll("Hero", "voice").startswith("Done")
    files = sorted(p.name for p in face._data_dir().rglob("*") if p.is_file())
    assert all(f.startswith("face.db") or f == "face.key" for f in files), files  # no .jpg/.png/.mp4 anywhere
    assert face.snapshot_count() == 1  # the crop lives encrypted inside face.db only


def test_housekeeping_expires_pictures_without_needing_a_new_one(enrolled, monkeypatch):
    face._save_snapshot(b"\xff\xd8old", 0.1, None)
    with face._db_lock, face._db() as conn:
        conn.execute("UPDATE face_snapshots SET ts = ?", ("2000-01-01T00:00:00",))
        conn.execute("INSERT INTO face_events (ts, kind) VALUES (?, ?)", ("2000-01-01T00:00:00", "owner_arrived"))
    face.log_event("owner_left")  # a recent event must survive
    assert face.snapshot_count() == 1  # the old bug: nothing prunes it until another picture is saved
    assert face.housekeeping(now=1e9, force=True) is True
    assert face.snapshot_count() == 0
    assert [e["kind"] for e in face.recent_events()] == ["owner_left"]
    assert face.housekeeping(now=1e9 + 60) is False  # throttled to once an hour
    assert face.housekeeping(now=1e9 + face.HOUSEKEEPING_EVERY_S + 1) is True


def test_a_missing_key_never_silently_orphans_existing_data(enrolled):
    (face._data_dir() / "face.key").unlink()
    face._key_cache.clear()
    with pytest.raises(RuntimeError, match="key is missing"):
        face._key()
    assert not (face._data_dir() / "face.key").exists()  # it did NOT mint a replacement
    assert "key is missing" in face.health_problem()
    assert "key is missing" in face.dashboard_state()["problem"]


def test_a_fresh_install_still_creates_its_key_and_reports_healthy(fx):
    assert face.health_problem() is None
    face._key()
    assert (face._data_dir() / "face.key").exists() and face.health_problem() is None


def test_enroll_waits_for_an_inflight_poll_but_not_forever(fx, monkeypatch):
    _install(monkeypatch, _turning_frames())
    face._camera_lock.acquire()
    threading.Timer(0.3, face._camera_lock.release).start()  # a poll finishing its ~1.5s look
    assert face.enroll("Hero", "voice").startswith("Done")
    monkeypatch.setattr(face, "CAMERA_WAIT_S", 0.05)
    face.delete("Hero", True, "voice", ui_confirmed=True)
    face._camera_lock.acquire()
    try:
        assert "busy" in face.enroll("Hero", "voice")
    finally:
        face._camera_lock.release()


def test_erasing_the_profile_clears_presence_immediately(enrolled, monkeypatch):
    _look(monkeypatch, _obs(0.0, BASE))
    face.poll_once(time.time())
    assert "Hero is at the computer" in face.system_prompt_context_line()
    assert face.delete("Hero", True, "voice", ui_confirmed=True).startswith("Deleted")
    assert face.system_prompt_context_line() == ""  # not "still here" for another ~90s
    assert not face.state_snapshot()["owner_present"]


def test_concurrent_polls_never_overlap(enrolled, monkeypatch):
    active, worst = [0], [0]
    lock = threading.Lock()

    def slow():
        with lock:
            active[0] += 1
            worst[0] = max(worst[0], active[0])
        time.sleep(0.05)
        with lock:
            active[0] -= 1
        return [], 100.0, 40.0, FRAME

    monkeypatch.setattr(face, "_capture_and_analyze", slow)
    threads = [threading.Thread(target=face.poll_once) for _ in range(5)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert worst[0] == 1


def test_state_changing_routes_reject_a_cross_site_origin(dash):
    good = {"origin": "http://127.0.0.1:8765"}
    evil = {"origin": "https://evil.example"}
    r = dash.post("/api/faces/pause", json={"paused": True}, headers=evil)
    assert r.status_code == 403 and not face.is_paused()  # valid loopback Host, hostile Origin
    assert dash.delete("/api/faces/1?confirm=true", headers=evil).status_code == 403
    assert len(face.list_profiles()) == 1
    assert dash.delete("/api/faces/snapshots", headers=evil).status_code == 403
    assert dash.post("/api/faces/pause", json={"paused": True}, headers=good).status_code == 200
    assert dash.post("/api/faces/pause", json={"paused": False}, headers={"origin": "http://localhost:8765"}).status_code == 200
    assert dash.get("/api/faces", headers=evil).status_code == 200  # reads stay simple; images aren't readable cross-site


def test_calibrate_reports_the_head_turn_and_stores_nothing(fx, monkeypatch):
    monkeypatch.setattr(face, "FRAME_INTERVAL_S", 0)
    _install(monkeypatch, _turning_frames())
    out = []
    res = face.calibrate(seconds=0.4, out=out.append)
    assert res["swing"] >= 0.5 and res["would_pass"] is True  # the scripted -0.25 -> +0.25 turn
    assert "Nothing was saved" in out[-1]
    assert face.list_profiles() == [] and face.recent_events() == [] and face.snapshot_count() == 0
    # a turn that is too small says how to tune it
    _install(monkeypatch, [_obs(0.0), _obs(0.05), _obs(-0.05)])
    out.clear()
    res = face.calibrate(seconds=0.3, out=out.append)
    assert res["would_pass"] is False and any("JARVIS_FACE_LIVENESS_SWING" in line for line in out)
    _install(monkeypatch, [[]])  # nobody in front of the camera
    out.clear()
    assert face.calibrate(seconds=0.2, out=out.append)["single_face_frames"] == 0
    assert any("No single face" in line for line in out)


# ===============================================================================================
# Code-review fixes (2026-09-19): each test pins one defect found in the review
# ===============================================================================================
_REAL_DOWNLOAD_MODELS = face.download_models  # captured before any fixture stubs it


def test_engine_refuses_when_models_are_missing_instead_of_letting_insightface_download(fx, monkeypatch):
    """insightface would silently fetch the pack itself with no size/hash check, bypassing the pin."""
    import insightface.app as iapp

    def boom(*a, **k):
        raise AssertionError("FaceAnalysis must not be constructed without verified model files")

    monkeypatch.setattr(iapp, "FaceAnalysis", boom)
    assert not face.models_ready()
    with pytest.raises(RuntimeError, match="model files are missing"):
        face._InsightEngine()


def test_engine_caps_onnx_threads_so_it_cannot_stall_the_voice_loop(fx, monkeypatch):
    import insightface.app as iapp

    seen = {}

    class FakeApp:
        def __init__(self, **kw):
            seen.update(kw)

        def prepare(self, **kw):
            pass

    monkeypatch.setattr(iapp, "FaceAnalysis", FakeApp)
    monkeypatch.setattr(face, "models_ready", lambda: True)
    face._InsightEngine()
    assert seen["sess_options"].intra_op_num_threads == 2 and seen["sess_options"].inter_op_num_threads == 1
    assert seen["providers"] == ["CPUExecutionProvider"]
    monkeypatch.setenv("JARVIS_FACE_THREADS", "1")
    face._InsightEngine()
    assert seen["sess_options"].intra_op_num_threads == 1


def test_health_problem_flags_missing_model_files_when_a_profile_exists(enrolled):
    assert "model files are missing" in face.health_problem()
    assert "model files are missing" in face.dashboard_state()["problem"]


def test_model_download_success_extracts_atomically_and_cleans_up(fx, monkeypatch):
    import hashlib
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("det_10g.onnx", b"detector-bytes")
        zf.writestr("w600k_r50.onnx", b"recognizer-bytes")
        zf.writestr("unused.onnx", b"never extracted")
    data = buf.getvalue()
    monkeypatch.setattr(face, "download_models", _REAL_DOWNLOAD_MODELS)
    monkeypatch.setattr(face, "MODEL_ZIP_SIZE", len(data))
    monkeypatch.setattr(face, "MODEL_ZIP_SHA256", hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(face.urllib.request, "urlopen", lambda url, timeout=0: _Resp(data))
    msgs = []
    face.download_models(msgs.append)
    d = face._model_root() / "models" / face.MODEL_PACK
    assert sorted(p.name for p in d.iterdir()) == ["det_10g.onnx", "w600k_r50.onnx"]  # only the two we use
    assert (d / "det_10g.onnx").read_bytes() == b"detector-bytes"
    assert not list(face._model_root().rglob("*.tmp")) and not list(face._model_root().rglob("*.part"))
    assert face.models_ready() and msgs and "Downloading" in msgs[0]


# --- one-person rule under a race ------------------------------------------------------------------
def test_admin_cannot_be_inserted_twice_even_if_enrollments_race(fx, monkeypatch):
    frames = _person_frames(OTHER_FACE)
    assert face._run_enrollment("Hero", _Engine(_turning_frames()), _Cap()).startswith("Done")
    msg = face._run_enrollment("Deborah", _Engine(frames), _Cap(), role="admin")  # bypasses enroll()'s pre-checks
    assert "didn't save this one" in msg
    assert [p["name"] for p in face.list_profiles()] == ["Hero"]
    assert "enroll_failed" in _kinds()


def test_concurrent_enroll_calls_of_the_same_person_leave_one_profile(fx, monkeypatch):
    _install(monkeypatch, _turning_frames())
    results = {}

    def go(n):
        results[n] = face.enroll(n, "voice")

    threads = [threading.Thread(target=go, args=(n,)) for n in ("Hero", "Deborah")]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(face.list_profiles()) == 1  # the same face can only be enrolled once
    assert sorted(r.startswith("Done") for r in results.values()) == [False, True]


# --- delete must be confirmed in a separate user message -------------------------------------------
def test_delete_confirm_in_the_same_turn_is_refused(enrolled):
    """A model that stages and confirms inside one turn (hallucination / prompt injection) gets nowhere."""
    assert "confirm" in face.delete("Hero", False, "voice", turn_id="erase my face")
    r = face.delete("Hero", True, "voice", turn_id="erase my face")
    assert "separate message" in r and len(face.list_profiles()) == 1
    assert face.delete("Hero", True, "voice", turn_id="yes").startswith("Deleted")  # the user's next message


def test_delete_confirm_without_staging_or_after_expiry_is_refused(enrolled, monkeypatch):
    assert "separate message" in face.delete("Hero", True, "voice", turn_id="yes")  # nothing was staged
    monkeypatch.setattr(face, "STAGE_TTL_S", 0.0)
    face.delete("Hero", False, "voice", turn_id="erase my face")
    assert "separate message" in face.delete("Hero", True, "voice", turn_id="yes")  # too late
    assert len(face.list_profiles()) == 1
    assert face.delete("Hero", True, "voice", ui_confirmed=True).startswith("Deleted")  # a dashboard click


def test_delete_via_the_real_tool_path_needs_two_user_messages(jarvis, monkeypatch, enrolled):
    """Goes through handle_text_command -> _execute_tool (not _execute_impl): also proves the command
    source survives the real dispatch wrapper, which the earlier tests skipped."""
    replies = []

    def agent_turn(script):
        def run(transcript, tone=None, narrate=False):
            for conf in script:
                replies.append(jarvis._execute_tool("delete_face", {"name": "Hero", "confirm": conf}, transcript))
            return "ok"

        monkeypatch.setattr(jarvis, "run_agent_loop", run)

    agent_turn([False, True])  # stage + confirm inside ONE user message
    jarvis.handle_text_command("erase my face", source="voice", reply_sink=lambda r: None)
    assert "separate message" in replies[-1] and len(face.list_profiles()) == 1
    agent_turn([True])  # the user's next message: "yes"
    jarvis.handle_text_command("yes", source="voice", reply_sink=lambda r: None)
    assert replies[-1].startswith("Deleted") and face.list_profiles() == []


# --- camera / thread hygiene -----------------------------------------------------------------------
def test_camera_is_released_if_warmup_raises(monkeypatch):
    import cv2

    state = {"released": False, "reads": 0}

    class FlakyCap:
        def isOpened(self):
            return True

        def read(self):
            state["reads"] += 1
            if state["reads"] > 2:
                raise RuntimeError("driver fault")
            return True, np.full((4, 4, 3), 50.0, dtype="float32")

        def release(self):
            state["released"] = True

    monkeypatch.setattr(cv2, "VideoCapture", lambda *a, **k: FlakyCap())
    with pytest.raises(RuntimeError, match="driver fault"):
        face._open_camera(0)
    assert state["released"]  # the camera light must not stay on


def test_poll_thread_keeps_trying_after_repeated_failures(fx, monkeypatch):
    calls = []

    def bad(now=None):
        calls.append(1)
        raise RuntimeError("model missing")

    monkeypatch.setattr(face, "poll_once", bad)
    monkeypatch.setattr(face, "POLL_ERROR_BACKOFF_S", 0.01)
    monkeypatch.setattr(face, "poll_interval", lambda: 0.01)
    monkeypatch.setattr(face, "settled_poll_interval", lambda: 0.01)
    monkeypatch.setattr(face, "_poll_thread", None)
    assert face.start_polling()
    deadline = time.time() + 3
    while len(calls) < 6 and time.time() < deadline:
        time.sleep(0.01)
    alive = face._poll_thread.is_alive()
    face.stop_polling()
    assert len(calls) >= 6 and alive  # it used to return for good after 3 failures


def test_lowering_poll_priority_is_safe_and_does_not_touch_the_calling_thread(monkeypatch):
    errors = []

    def run():
        try:
            face._lower_thread_priority()  # runs on its own thread: must never lower pytest's
        except Exception as e:
            errors.append(e)

    t = threading.Thread(target=run)
    t.start()
    t.join()
    assert not errors and not t.is_alive()


def test_hooks_run_after_the_poll_lock_is_released(enrolled, monkeypatch):
    """A slow greeting/notification must not freeze who_is_here or the dashboard's pause/erase."""
    _look(monkeypatch, _obs(0.0, BASE))
    in_hook, let_go = threading.Event(), threading.Event()
    lock_was_free = []

    def slow_greet(_text):
        lock_was_free.append(face._poll_lock.acquire(blocking=False))
        if lock_was_free[-1]:
            face._poll_lock.release()
        in_hook.set()
        let_go.wait(3)

    face._hooks["greet"] = slow_greet
    t = threading.Thread(target=face.poll_once, args=(time.time(),))
    t.start()
    assert in_hook.wait(3)
    started = time.time()
    assert "paused" in face.set_paused(True, "voice")  # returns while the greeting is still "speaking"
    assert time.time() - started < 1.0
    let_go.set()
    t.join(3)
    assert lock_was_free == [True]


def test_pause_during_an_inflight_poll_is_not_overwritten_by_it(enrolled, monkeypatch):
    """The in-flight poll must finish first, THEN the reset lands; otherwise the poll writes
    "owner present" back over a pause/erase and the prompt keeps saying so for ~90s."""
    entered, proceed = threading.Event(), threading.Event()

    def blocked_capture():
        entered.set()
        proceed.wait(3)
        return list(_obs(0.0, BASE)), 100.0, 40.0, FRAME

    monkeypatch.setattr(face, "_capture_and_analyze", blocked_capture)
    poller = threading.Thread(target=face.poll_once, args=(time.time(),))
    poller.start()
    assert entered.wait(3)
    pauser = threading.Thread(target=face.set_paused, args=(True, "voice"))
    pauser.start()
    time.sleep(0.1)
    assert pauser.is_alive()  # waiting for the poll, not racing it
    proceed.set()
    poller.join(3)
    pauser.join(3)
    snap = face.state_snapshot()
    assert not snap["owner_present"] and snap["updated_at"] == 0.0 and not face.group_safe()


def test_first_time_key_creation_is_race_free(fx, monkeypatch):
    import time as _t

    def slow_dpapi(data, protect):
        if protect:
            _t.sleep(0.05)  # widen the window in which a second caller could mint its own key
        return data

    monkeypatch.setattr(face, "_dpapi", slow_dpapi)
    face._key_cache.clear()
    keys = []
    threads = [threading.Thread(target=lambda: keys.append(face._key())) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(set(keys)) == 1 and (face._data_dir() / "face.key").read_bytes() == keys[0]


# --- dashboard WebSocket origin --------------------------------------------------------------------
def test_websocket_rejects_a_cross_site_origin_but_accepts_the_dashboard(fx):
    from fastapi.testclient import TestClient

    import jarvis_dashboard as dashboard

    with TestClient(dashboard._build_app(), base_url="http://127.0.0.1:8765") as c:
        for evil in ("https://evil.example", "null", "http://localhost.evil.example:8765"):
            with pytest.raises(Exception):
                with c.websocket_connect("/ws", headers={"origin": evil}):
                    pass
        with c.websocket_connect("/ws", headers={"origin": "http://127.0.0.1:8765"}):
            pass
        with c.websocket_connect("/ws", headers={"origin": "http://localhost:8765"}):
            pass
        with c.websocket_connect("/ws"):  # non-browser client: no Origin header
            pass


def test_greeting_does_not_talk_over_a_reply_already_playing(quiet_jarvis, monkeypatch):
    j, _ = quiet_jarvis
    said = []
    monkeypatch.setattr(j, "speak_text", said.append)
    monkeypatch.setattr(face, "group_safe", lambda now=None: False)
    j.jarvis_speaking.set()
    try:
        j._face_greet("Good evening, Hero.")
    finally:
        j.jarvis_speaking.clear()
    assert said == []


# ===============================================================================================
# Away mode (locks the computer when the owner has not been shown) + stranger hooks
# ===============================================================================================
class _Rec:
    """Records lock / warning / stranger hook calls in order."""

    def __init__(self):
        self.calls = []

    def hook(self, name):
        return lambda *a: self.calls.append((name, *a))


@pytest.fixture()
def away(enrolled, monkeypatch):
    rec = _Rec()
    for name in ("lock", "away_warn", "stranger", "stranger_left", "release"):
        face._hooks[name] = rec.hook(name)
    face._hooks["locked"] = lambda: False
    assert "Away mode is on" in face.set_away(True, "voice")
    _look(monkeypatch, [])  # the camera works, but the owner is not in view
    return rec


A0 = 5_000_000.0


def test_away_mode_warns_once_then_locks_after_the_grace_period(away):
    for t in (0, 20, 30):
        face.poll_once(A0 + t)
    assert away.calls == []  # 30s unseen: still inside the grace period, before the warning window
    face.poll_once(A0 + 36)  # >= 50 - 15
    assert [c[0] for c in away.calls] == ["away_warn"] and "15 seconds" in away.calls[0][1]
    face.poll_once(A0 + 42)
    assert [c[0] for c in away.calls] == ["away_warn"]  # warned only once
    face.poll_once(A0 + 51)
    assert [c[0] for c in away.calls] == ["away_warn", "lock"]
    assert _kinds()[-2:] == ["away_warning", "away_lock"]
    face.poll_once(A0 + 55)  # the clock restarts after a lock (no lock storm)
    assert [c[0] for c in away.calls].count("lock") == 1


def test_owner_coming_back_before_the_lock_cancels_it(away, monkeypatch):
    for t in (0, 20, 36):
        face.poll_once(A0 + t)  # warned
    _look(monkeypatch, _obs(0.0, BASE))  # ...and the owner is recognized again
    face.poll_once(A0 + 42)
    _look(monkeypatch, [])
    face.poll_once(A0 + 60)  # would have been past the old deadline
    face.poll_once(A0 + 70)
    assert "lock" not in [c[0] for c in away.calls]
    # The new absence clock started at t=60. It warns again at 60+35, and only locks at 60+50.
    for t in (80, 96, 104):
        face.poll_once(A0 + t)
    assert [c[0] for c in away.calls] == ["away_warn", "away_warn"]
    face.poll_once(A0 + 111)
    assert [c[0] for c in away.calls] == ["away_warn", "away_warn", "lock"]


def test_away_mode_is_off_by_default_and_never_locks_when_off(enrolled, monkeypatch):
    rec = _Rec()
    face._hooks["lock"], face._hooks["away_warn"], face._hooks["locked"] = rec.hook("lock"), rec.hook("warn"), (lambda: False)
    _look(monkeypatch, [])
    assert not face.away_enabled()
    for t in (0, 60, 120, 600, 6000):
        face.poll_once(A0 + t)
    assert rec.calls == []


@pytest.mark.parametrize("blind", ["covered", "camera-error", "busy"])
def test_a_blind_camera_never_locks_and_resets_the_clock(away, monkeypatch, blind):
    """Decision: if the camera can't see (covered, unreachable, busy in a call) it can't tell the
    owner is gone, so it must never lock - and it must not let earlier absence keep counting."""
    face.poll_once(A0)
    face.poll_once(A0 + 40)  # 40s of genuine absence so far
    if blind == "covered":
        _look(monkeypatch, [], mean=1.0, std=0.5)
    elif blind == "camera-error":
        monkeypatch.setattr(face, "_capture_and_analyze", lambda: (_ for _ in ()).throw(face.CameraUnavailable("in a call")))
    if blind == "busy":
        assert face._camera_lock.acquire(blocking=False)
    try:
        for t in (45, 400, 4000):
            face.poll_once(A0 + t)
    finally:
        if blind == "busy":
            face._camera_lock.release()
    _look(monkeypatch, [])
    face.poll_once(A0 + 4001)  # sight is back: a brand-new clock starts
    face.poll_once(A0 + 4030)
    assert "lock" not in [c[0] for c in away.calls]


def test_no_lock_when_paused_asleep_locked_already_or_nobody_enrolled(away, monkeypatch):
    face.poll_once(A0)
    face.set_paused(True, "voice")
    face.poll_once(A0 + 500)
    face.set_paused(False, "voice")
    face._hooks["quiet"] = lambda: True  # Sleep Mode
    face.poll_once(A0 + 1000)
    face._hooks["quiet"] = lambda: False
    used = []
    monkeypatch.setattr(face, "_capture_and_analyze", lambda: used.append(1) or ([], 100.0, 40.0, FRAME))
    face._hooks["locked"] = lambda: True  # the lock screen is already up
    assert face.poll_once(A0 + 2000) == "locked" and used == []  # camera untouched while locked
    face._hooks["locked"] = lambda: False
    with face._db_lock, face._db() as conn:
        conn.execute("DELETE FROM face_profiles")
    face.invalidate_profile_cache()
    face.poll_once(A0 + 3000)
    assert "lock" not in [c[0] for c in away.calls]


def test_warning_can_be_disabled_and_grace_has_a_floor(away, monkeypatch):
    monkeypatch.setenv("JARVIS_FACE_AWAY_WARN_S", "0")
    for t in (0, 36, 49):
        face.poll_once(A0 + t)
    assert away.calls == []  # no warning configured
    face.poll_once(A0 + 51)
    assert [c[0] for c in away.calls] == ["lock"]
    monkeypatch.setenv("JARVIS_FACE_AWAY_GRACE_S", "1")
    assert face.away_grace_s() == 10.0  # can't be configured into locking on every missed frame


def test_a_failing_lock_hook_does_not_break_polling(away):
    def boom(*a):
        raise OSError("LockWorkStation failed")

    face._hooks["lock"] = boom
    face.poll_once(A0)
    face.poll_once(A0 + 51)
    assert face.poll_once(A0 + 60) == "ok"


def test_set_away_rules(fx, monkeypatch):
    assert "Enroll your face first" in face.set_away(True, "voice")  # nobody enrolled: would lock constantly
    with face._db_lock, face._db() as conn:
        conn.execute(
            "INSERT INTO face_profiles (name, role, created_at, consent_at, n_samples, embeddings) VALUES (?,?,?,?,?,?)",
            ("Hero", "admin", "x", "x", 5, face._pack_embeddings(np.vstack([BASE, BASE]))),
        )
    face.invalidate_profile_cache()
    assert "Away mode is on" in face.set_away(True, "phone")  # turning it ON adds protection: any source
    assert face.away_enabled()
    assert "phone" in face.set_away(False, "phone") and face.away_enabled()  # OFF removes it: at the PC only
    assert "scheduled" in face.set_away(False, None) and face.away_enabled()
    assert "off" in face.set_away(False, "voice") and not face.away_enabled()
    assert _kinds()[-3:] == ["away_on", "away_off"][-2:] or "away_on" in _kinds()
    face.set_paused(True, "voice")
    assert "paused" in face.set_away(True, "voice")  # tells the owner it won't lock until resumed
    monkeypatch.setenv("JARVIS_FACE_ENABLED", "0")
    assert "switched off" in face.set_away(True, "voice")
    assert "switched off" in face.away_status()


def test_erasing_the_profile_turns_away_mode_off(away):
    assert face.away_enabled()
    assert face.delete("Hero", True, "voice", ui_confirmed=True).startswith("Deleted")
    assert not face.away_enabled()


def test_away_mode_persists_in_the_database(away):
    assert face.get_setting("away_mode") == "1"
    assert "Away mode is on" in face.away_status() and "50" in face.away_status()


def test_polling_runs_at_the_fast_interval_while_the_away_clock_is_running(enrolled, monkeypatch):
    waits = []

    class FakeEvent:
        def __init__(self):
            self.n = 0

        def is_set(self):
            return self.n >= 2

        def clear(self):
            pass

        def set(self):
            self.n = 99

        def wait(self, seconds):
            waits.append(seconds)
            self.n += 1

    monkeypatch.setattr(face, "_poll_stop", FakeEvent())
    monkeypatch.setattr(face, "poll_once", lambda now=None: "ok")
    monkeypatch.setattr(face, "housekeeping", lambda *a, **k: False)
    monkeypatch.setattr(face, "_poll_thread", None)
    face._st.owner_present = True  # owner steadily present -> the slow "settled" interval
    assert face.start_polling()
    face._poll_thread.join(3)
    assert waits[0] == face.settled_poll_interval()
    waits.clear()
    face._st.owner_present, face._st.absent_since = True, time.time()  # ...but the away clock is running
    face._poll_stop.n = 0
    monkeypatch.setattr(face, "_poll_thread", None)
    assert face.start_polling()
    face._poll_thread.join(3)
    assert waits[0] == face.poll_interval()  # watch closely: a 15s cadence would delay the lock


def test_stranger_hooks_fire_once_and_leave_fires_before_release(enrolled, monkeypatch):
    rec = _Rec()
    for name in ("stranger", "stranger_left", "release"):
        face._hooks[name] = rec.hook(name)
    _look(monkeypatch, _obs(0.0, OTHER))
    t = 9_000_000.0
    for i in range(4):
        face.poll_once(t + i * 5)
    assert rec.calls == [("stranger",)]  # once per visit, not per poll
    _look(monkeypatch, [])
    face.poll_once(t + 30)
    face.poll_once(t + 5 + face.UNKNOWN_CLEAR_S + 60)
    assert [c[0] for c in rec.calls] == ["stranger", "stranger_left", "release"]  # state before flush


def test_real_session_lock_probe_returns_a_bool_and_never_raises():
    assert face._session_locked() in (True, False)


# --- dashboard + tool -------------------------------------------------------------------------------------
def test_dashboard_away_toggle_and_state(dash):
    r = dash.post("/api/faces/away", json={"enabled": True}, headers={"origin": "http://127.0.0.1:8765"}).json()
    assert r["ok"] and r["away"] is True and "Away mode is on" in r["message"]
    st = dash.get("/api/faces").json()["away"]
    assert st["enabled"] is True and st["grace_seconds"] == 50.0 and st["warn_seconds"] == 15.0
    assert dash.post("/api/faces/away", json={"enabled": False}).json()["away"] is False
    assert dash.post("/api/faces/away", json={"enabled": True}, headers={"origin": "https://evil.example"}).status_code == 403
    assert dash.post("/api/faces/away", json={"enabled": True}, headers={"host": "evil.example"}).status_code == 403
    assert not face.away_enabled()  # neither hostile request changed anything


def test_away_mode_tool_respects_the_source(jarvis, monkeypatch, enrolled):
    out = []

    def turn(source, action):
        def agent(transcript, tone=None, narrate=False):
            out.append(jarvis._execute_tool("away_mode", {"action": action}, transcript))
            return "ok"

        monkeypatch.setattr(jarvis, "run_agent_loop", agent)
        jarvis.handle_text_command("x", source=source, reply_sink=lambda r: None)
        return out[-1]

    assert "Away mode is on" in turn("phone", "on")
    assert "phone" in turn("phone", "off") and face.away_enabled()  # can't be switched off remotely
    assert "on:" in turn("voice", "status")
    assert "Away mode is off" in turn("voice", "off") and not face.away_enabled()


# --- roles in presence ---------------------------------------------------------------------------
def _add_profile(name, role, emb):
    with face._db_lock, face._db() as conn:
        conn.execute(
            "INSERT INTO face_profiles (name, role, created_at, consent_at, n_samples, embeddings) VALUES (?,?,?,?,?,?)",
            (name, role, "2026-09-20T10:00:00", "2026-09-20T10:00:00", 5, face._pack_embeddings(np.vstack([emb, emb]))),
        )
    face.invalidate_profile_cache()


def test_user_is_recognized_but_is_not_the_owner_and_not_a_stranger(enrolled, monkeypatch):
    _add_profile("Deborah", "user", OTHER)
    _look(monkeypatch, _obs(0.0, OTHER))
    t = time.time()
    face.poll_once(t)
    face.poll_once(t + 5)
    snap = face.state_snapshot()
    assert not snap["owner_present"] and not snap["unknown_present"] and not face.group_safe()
    assert snap["others_present"] == [{"name": "Deborah", "role": "user"}]
    assert "Deborah (user) is in view" in face.system_prompt_context_line()
    assert "unknown_seen" not in _kinds()


def test_user_in_view_does_not_stop_away_mode_counting_the_owner_as_gone(enrolled, monkeypatch):
    _add_profile("Deborah", "user", OTHER)
    face.set_setting("away_mode", "1")
    _look(monkeypatch, _obs(0.0, OTHER))
    t = time.time()
    face.poll_once(t)
    assert face._st.absent_since > 0  # the Admin is still unseen


def test_guest_holds_proactive_speech_like_a_stranger_but_takes_no_picture(enrolled, monkeypatch):
    _add_profile("Sam", "guest", OTHER)
    _look(monkeypatch, _obs(0.0, OTHER))
    t = time.time()
    face.poll_once(t)
    assert face.group_safe(t + 1) and face.group_safe_suppress(urgent=False) and not face.group_safe_suppress(urgent=True)
    assert face.snapshot_count() == 0 and "unknown_seen" not in _kinds()
    assert face.state_snapshot()["unknown_present"] is False
    _look(monkeypatch, [])
    face.poll_once(t + 5 + face.UNKNOWN_CLEAR_S + 1)
    assert not face.state_snapshot()["guest_present"]


def test_owner_still_greeted_when_a_user_is_also_present(enrolled, monkeypatch):
    _add_profile("Deborah", "user", OTHER)
    _look(monkeypatch, _obs(0.0, BASE) + _obs(0.0, OTHER))
    face.poll_once(time.time())
    snap = face.state_snapshot()
    assert snap["owner_present"] and snap["owner_name"] == "Hero"
    assert snap["others_present"] == [{"name": "Deborah", "role": "user"}]
