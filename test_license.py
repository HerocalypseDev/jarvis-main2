"""Jarvis4U Pro: offline signed license keys, the Pro pack loader and the Settings route."""
import base64
import importlib
import json
import sys

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import jarvis_cache as cache
import jarvis_license as lic
import jarvis_pro as pro


def _pub(private) -> str:
    raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.fixture()
def signer(monkeypatch):
    private = Ed25519PrivateKey.generate()
    monkeypatch.setattr(lic, "PUBLIC_KEY_B64", _pub(private))
    monkeypatch.setattr(lic, "REVOKED_IDS", frozenset())
    return private


def _key(private, **over):
    payload = {"e": "buyer@example.com", "t": "pro", "i": "2026-09-29", "n": "ab12cd34", **over}
    return lic.sign(payload, private)


def test_genuine_key_verifies_and_survives_email_line_breaks(signer):
    key = _key(signer)
    ok = lic.verify(key)
    assert ok["valid"] and ok["email"] == "buyer@example.com" and ok["tier"] == "pro"
    wrapped = key[:40] + "\n  " + key[40:100] + " \r\n" + key[100:]
    assert lic.verify(wrapped)["valid"]


def test_forged_tampered_and_foreign_keys_are_rejected(signer):
    key = _key(signer)
    prefix, payload, sig = key.split(".")
    # Change the email inside the payload but keep the old signature.
    forged = json.dumps({"e": "thief@example.com", "t": "pro", "i": "2026-09-29", "n": "ab12cd34"},
                        separators=(",", ":"), sort_keys=True).encode()
    tampered = f"{prefix}.{base64.urlsafe_b64encode(forged).rstrip(b'=').decode()}.{sig}"
    assert not lic.verify(tampered)["valid"]
    # A key signed by someone else's private key (e.g. a keygen) is rejected.
    other = _key(Ed25519PrivateKey.generate())
    assert "isn't genuine" in lic.verify(other)["reason"]
    assert not lic.verify("J4U1.garbage.garbage")["valid"]
    assert not lic.verify("hello")["valid"]
    assert not lic.verify("")["valid"]


def test_wrong_tier_and_revoked_keys(signer, monkeypatch):
    assert "different product" in lic.verify(_key(signer, t="enterprise"))["reason"]
    monkeypatch.setattr(lic, "REVOKED_IDS", frozenset({"ab12cd34"}))
    out = lic.verify(_key(signer))
    assert not out["valid"] and "cancelled" in out["reason"]


def test_build_without_public_key_accepts_nothing(monkeypatch):
    monkeypatch.setattr(lic, "PUBLIC_KEY_B64", "")
    key = _key(Ed25519PrivateKey.generate())
    out = lic.verify(key)
    assert not out["valid"] and "aren't available" in out["reason"]


def test_pro_pack_only_loads_with_license_and_manifest(signer, monkeypatch, tmp_path):
    pack = tmp_path / "pro"
    (pack / "skills").mkdir(parents=True)
    (pack / "skills" / "study_timer.json").write_text(json.dumps({"name": "study_timer", "instructions": "x"}))
    monkeypatch.setenv("JARVIS_PRO_DIR", str(pack))
    monkeypatch.setenv(lic.ENV_KEY, _key(signer))
    assert not pro.active() and pro.skill_paths() == []            # no manifest yet
    (pack / "manifest.json").write_text(json.dumps({"name": "Jarvis4U Pro", "version": "1.0.0"}))
    assert pro.active() and [p.name for p in pro.skill_paths()] == ["study_timer.json"]
    key = _key(signer)
    assert key.split(".")[2] not in json.dumps(pro.status())       # status never carries the key
    monkeypatch.setenv(lic.ENV_KEY, "")
    assert not pro.active() and pro.skill_paths() == []            # no license
    st = pro.status()
    assert st["installed"] and not st["active"]


@pytest.fixture()
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("JARVIS_LLM_TTS_STREAM", "0")
    import jarvis as j

    monkeypatch.setattr(j, "get_mcp_tool_schemas", lambda: [])
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    j._reply_cache.clear()
    j._tool_result_cache.clear()
    cache.reset_stats()
    return j


def test_pro_skills_join_the_normal_skill_list_and_own_skills_win(jarvis, signer, monkeypatch, tmp_path):
    own = tmp_path / "skills"
    own.mkdir()
    (own / "morning.json").write_text(json.dumps({"name": "morning", "instructions": "mine"}))
    pack = tmp_path / "pro"
    (pack / "skills").mkdir(parents=True)
    (pack / "manifest.json").write_text(json.dumps({"name": "Jarvis4U Pro", "version": "1.0.0"}))
    (pack / "skills" / "morning.json").write_text(json.dumps({"name": "Morning", "instructions": "pro"}))
    (pack / "skills" / "exam_countdown.json").write_text(json.dumps({"name": "exam_countdown", "instructions": "pro2"}))
    monkeypatch.setenv("JARVIS_SKILLS_DIR", str(own))
    monkeypatch.setenv("JARVIS_PRO_DIR", str(pack))
    monkeypatch.setattr(jarvis, "_skills_cache", None)
    monkeypatch.setenv(lic.ENV_KEY, "")
    assert [s["name"] for s in jarvis._load_skills()] == ["morning"]
    monkeypatch.setenv(lic.ENV_KEY, _key(signer))
    skills = {s["name"]: s["instructions"] for s in jarvis._load_skills()}   # signature change -> reload
    assert skills == {"morning": "mine", "exam_countdown": "pro2"}


def test_dashboard_activate_verifies_first_and_never_echoes_the_key(jarvis, signer, monkeypatch):
    saved = {}
    monkeypatch.setattr(jarvis.settings, "set_setting",
                        lambda k, v: saved.update({k: v}) or {"ok": True})
    handler = jarvis._FEATURE_PROVIDERS["license"]
    bad = handler("activate", {"key": "J4U1.nope.nope"})
    assert not bad["ok"] and saved == {}
    key = _key(signer)
    monkeypatch.setenv(lic.ENV_KEY, key)          # what set_setting would do
    good = handler("activate", {"key": " " + key + "\n"})
    assert good["ok"] and saved == {lic.ENV_KEY: key}
    assert key not in json.dumps(good) and key not in json.dumps(handler("get", {}))
    assert good["license"]["email"] == "buyer@example.com"


def test_make_license_tool_round_trip(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("JARVIS4U_SELLER_DIR", str(tmp_path / "seller"))
    monkeypatch.syspath_prepend("tools")
    sys.modules.pop("make_license", None)
    ml = importlib.import_module("make_license")
    ml.init()
    pub = capsys.readouterr().out.strip().splitlines()[-1]
    assert (tmp_path / "seller" / "license_signing_key.pem").exists()
    key = ml.make("buyer@example.com")
    monkeypatch.setattr(lic, "PUBLIC_KEY_B64", pub)
    assert lic.verify(key)["valid"]
    assert "buyer@example.com" in (tmp_path / "seller" / "issued_keys.csv").read_text()
    ml.init()   # a second init must never replace the signing key
    assert lic.verify(ml.make("b2@example.com"))["valid"]
