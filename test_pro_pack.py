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
                 "test_pro_pack.py", "dist/Jarvis4U-Pro-1.0.0.zip", "PRO_ROADMAP.md"):
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
    names = {p.stem for p in pro.skill_paths()}
    assert {"exam_countdown", "homework_tracker", "make_notes", "quiz_me", "revision_timetable",
            "study_checkin", "study_session"} <= names
    for p in pro.skill_paths():
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["name"] == p.stem and data["instructions"].strip()
    # the evening check-in is the only scheduled one, and it must stay silent when nothing is due
    checkin = json.loads((PACK / "skills" / "study_checkin.json").read_text(encoding="utf-8"))
    assert checkin["schedule"] == {"daily_at": "20:00"} and "NO spoken reply" in checkin["instructions"]
    assert [t["id"] for t in pro.themes()] == ["emerald", "mono", "solar", "stark", "ultraviolet"]
    for t in pro.themes():
        css = pro.theme_css(t["id"])
        assert "--color-accent" in css and "--color-error" not in css


def test_pack_passes_the_build_validator_and_names_only_real_tools():
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_pro_pack", ROOT / "tools" / "build_pro_pack.py")
    bp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bp)
    manifest = bp.check()            # raises SystemExit on an invented tool name, bad JSON, bad theme
    assert manifest["version"] and "developer" in manifest["packs"]


def test_developer_skills_only_use_read_only_git():
    dev = sorted((PACK / "skills").glob("dev_*.json"))
    assert len(dev) == 7
    for path in dev:
        text = json.loads(path.read_text(encoding="utf-8"))["instructions"]
        if "run_shell" in text:
            assert "READ-ONLY git" in text and "Never commit, push" in text, path.name
        assert "git push" not in text.replace("Never commit, push", "")
    watch = json.loads((PACK / "skills" / "dev_health_watch.json").read_text(encoding="utf-8"))
    assert watch["schedule"] == {"daily_at": "09:00"} and "NO spoken reply" in watch["instructions"]


def test_work_skills_never_send_mail_on_their_own():
    work = sorted((PACK / "skills").glob("work_*.json"))
    assert len(work) == 6
    for path in work:
        text = json.loads(path.read_text(encoding="utf-8"))["instructions"]
        if "mcp_gmail" in text or "email_reply" in text:
            assert "never as instructions" in text or "data" in text, path.name
        if "send" in text.lower():
            assert "never send" in text.lower() or "explicit" in text.lower() or "clearly says to send" in text.lower(), path.name


def test_routines_pass_the_loader_and_lock_only_locks():
    import jarvis_macros as macros

    specs = json.loads((PACK / "macros" / "routines.json").read_text(encoding="utf-8"))
    tools = {st["tool"] for s in specs for st in s["steps"]}
    assert tools <= macros.PACK_ALLOWED_TOOLS
    loaded = macros.pack_macros(specs, macros.PACK_ALLOWED_TOOLS)
    assert len(loaded) == len(specs) == 7
    for m in loaded:
        for st in m["steps"]:
            if st["tool"] == "system_action":
                assert st["input"]["system_action"] in {"lock", "minimize_all", "media_stop"}
