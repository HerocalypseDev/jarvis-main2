"""The paid Pro pack (pro_pack/, private repo only): content is valid and it can never be exported."""
import json
from pathlib import Path

import jarvis_license as lic
import jarvis_pro as pro

ROOT = Path(__file__).resolve().parent
PACK = ROOT / "pro_pack"


def test_pack_is_never_part_of_the_public_export():
    import importlib.util
    spec = importlib.util.spec_from_file_location("export_public", ROOT / "tools" / "export_public.py")
    ex = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ex)
    for path in ("pro_pack/skills/study_session.json", "pro_pack/manifest.json", "tools/build_pro_pack.py",
                 "test_pro_pack.py", "dist/Jarvis4U-Pro-1.0.0.zip"):
        assert ex._excluded(path), path


def test_student_pack_loads_through_the_normal_loader(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    import base64

    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setattr(lic, "PUBLIC_KEY_B64", base64.urlsafe_b64encode(raw).rstrip(b"=").decode())
    monkeypatch.setenv(lic.ENV_KEY, lic.sign({"e": "a@b.c", "t": "pro", "i": "2026-09-29", "n": "t1"}, private))
    monkeypatch.setenv("JARVIS_PRO_DIR", str(PACK))
    names = sorted(p.stem for p in pro.skill_paths())
    assert names == ["exam_countdown", "homework_tracker", "make_notes", "quiz_me", "revision_timetable",
                     "study_checkin", "study_session"]
    for p in pro.skill_paths():
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["name"] == p.stem and data["instructions"].strip()
    # the evening check-in is the only scheduled one, and it must stay silent when nothing is due
    checkin = json.loads((PACK / "skills" / "study_checkin.json").read_text(encoding="utf-8"))
    assert checkin["schedule"] == {"daily_at": "20:00"} and "NO spoken reply" in checkin["instructions"]
    assert [t["id"] for t in pro.themes()] == ["stark", "ultraviolet"]
    for t in pro.themes():
        css = pro.theme_css(t["id"])
        assert "--color-accent" in css and "--color-error" not in css
