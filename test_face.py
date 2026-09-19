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

    if not hasattr(j, "_real_flush_pending"):
        j._real_flush_pending = j.flush_pending_notifications
    monkeypatch.setattr(j, "flush_pending_notifications", lambda: None)
    monkeypatch.setattr(j, "speak_text", lambda *a, **k: None)
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    return j


def test_face_tools_are_hidden_unless_the_feature_is_enabled(jarvis):
    names = {t["name"] for t in jarvis.AGENT_TOOLS}
    face_names = {"enroll_face", "list_faces", "delete_face", "who_is_here", "face_privacy"}
    assert face_names == {t["name"] for t in jarvis.FACE_TOOLS}
    assert not (face_names & names)  # default: off, no tokens spent


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
