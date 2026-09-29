"""Jarvis4U Pro pack loader.

A Pro pack is a folder (default: `pro/` next to jarvis.py, or JARVIS_PRO_DIR) unzipped from the
download buyers get on Selar:

    pro/manifest.json      {"name": "Jarvis4U Pro", "version": "1.0.0"}
    pro/skills/*.json      extra skills, same format as skills/*.json
    pro/themes/*.css       dashboard colour themes (only :root colour tokens are used, see theme_css)
    pro/macros/*.json      routines: voice macros limited to low-risk tools (jarvis_macros.PACK_ALLOWED_TOOLS)

It only switches on with a valid license key (jarvis_license). Without one, Jarvis runs exactly as
the free version: nothing here changes behaviour. Pro skills go through the normal skill path, so
they get no extra permissions: every tool call still passes the audit trail and the catastrophic
confirmation gate. Your own skills/*.json win over a Pro skill with the same name.
"""
from __future__ import annotations

import json
import os
import re
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


def macro_specs() -> list[dict]:
    """Raw routine specs from pro/macros/*.json (validated by jarvis_macros.pack_macros)."""
    if not active():
        return []
    folder = pro_dir() / "macros"
    out = []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.extend(d for d in (data if isinstance(data, list) else [data]) if isinstance(d, dict))
    return out


_THEME_ID_RE = re.compile(r"^[a-z0-9_-]{1,40}$")
_DECL_RE = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;{}]+);")
_SAFE_VALUE_RE = re.compile(r"^[#a-zA-Z0-9(),.\s%-]{1,120}$")
# Never themeable: the red of the pending-confirmation bar and error text must always read as danger.
_LOCKED = ("--color-error", "--color-on-error", "--color-warning")


def themes() -> list[dict]:
    if not active():
        return []
    folder = pro_dir() / "themes"
    out = []
    for path in sorted(folder.glob("*.css")) if folder.is_dir() else []:
        if not _THEME_ID_RE.match(path.stem):
            continue
        m = re.search(r"/\*\s*name:\s*([^*]{1,40})\*/", path.read_text(encoding="utf-8", errors="replace"))
        out.append({"id": path.stem, "name": (m.group(1).strip() if m else path.stem.title())})
    return out


def theme_css(theme_id: str) -> str | None:
    """A theme rebuilt from its colour-token declarations only: `--color-*` / `--shadow-glow` with
    plain colour values. Anything else in the file (url(), @import, selectors, other properties) is
    dropped, and the danger colours can't be changed. None if Pro isn't active or the id is unknown."""
    if not active() or not _THEME_ID_RE.match(theme_id or ""):
        return None
    path = pro_dir() / "themes" / f"{theme_id}.css"
    if not path.is_file():
        return None
    decls = []
    for name, value in _DECL_RE.findall(path.read_text(encoding="utf-8", errors="replace")):
        value = value.strip()
        if not (name.startswith("--color-") or name == "--shadow-glow"):
            continue
        if name.startswith(_LOCKED) or "url" in value.lower() or not _SAFE_VALUE_RE.match(value):
            continue
        decls.append(f"  {name}: {value};")
    return ":root {\n" + "\n".join(decls) + "\n}\n" if decls else None


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
        "themes": themes(),
        "store_url": STORE_URL,
        "support_url": SUPPORT_URL,
    }
