"""Jarvis4U Pro pack loader.

A Pro pack is a folder (default: `pro/` next to jarvis.py, or JARVIS_PRO_DIR) unzipped from the
download buyers get on Selar:

    pro/manifest.json      {"name": "Jarvis4U Pro", "version": "1.0.0"}
    pro/skills/*.json      extra skills, same format as skills/*.json

It only switches on with a valid license key (jarvis_license). Without one, Jarvis runs exactly as
the free version: nothing here changes behaviour. Pro skills go through the normal skill path, so
they get no extra permissions: every tool call still passes the audit trail and the catastrophic
confirmation gate. Your own skills/*.json win over a Pro skill with the same name.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import jarvis_license as license_mod

STORE_URL = "https://selar.com/1954zy6955"    # Jarvis4U Pro on Selar
SUPPORT_URL = "https://selar.com/7e2611t04t"  # Support Jarvis4U (tips) on Selar


def pro_dir() -> Path:
    override = (os.environ.get("JARVIS_PRO_DIR") or "").strip()
    return Path(override).expanduser() if override else Path(__file__).resolve().parent / "pro"


def manifest() -> dict | None:
    path = pro_dir() / "manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def active() -> bool:
    return manifest() is not None and license_mod.is_pro()


def skill_paths() -> list[Path]:
    if not active():
        return []
    folder = pro_dir() / "skills"
    return sorted(folder.glob("*.json")) if folder.is_dir() else []


def status() -> dict:
    lic = license_mod.status()
    man = manifest()
    folder = pro_dir() / "skills"
    return {
        "license": {k: lic.get(k) for k in ("valid", "reason", "email", "tier", "issued")},
        "installed": man is not None,
        "pack": {"name": man.get("name"), "version": man.get("version")} if man else None,
        "active": bool(lic.get("valid")) and man is not None,
        "skills": len(list(folder.glob("*.json"))) if man and folder.is_dir() else 0,
        "store_url": STORE_URL,
        "support_url": SUPPORT_URL,
    }
