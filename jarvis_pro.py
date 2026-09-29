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


# The free stylesheet's own values (dashboard_static/style.css :root) for the tokens the readability check uses.
_DEFAULT_TOKENS = {"--color-bg-primary": "#050b14", "--color-bg-secondary": "#0a1420",
                   "--color-text-primary": "#dcedf5", "--color-text-secondary": "#a9c4d3"}
MIN_TEXT_CONTRAST = 4.5
_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _luminance(hex_colour: str) -> float | None:
    m = _HEX_RE.match(hex_colour.strip())
    if not m:
        return None
    h = m.group(1)
    h = "".join(c * 2 for c in h) if len(h) == 3 else h
    ch = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255
        ch.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def _readable(tokens: dict) -> bool:
    """Body text (which is also the approval bar's text) must stay readable on the page and panel
    backgrounds: plain hex colours with >= 4.5:1 contrast. A theme that fails is refused whole."""
    for text in ("--color-text-primary", "--color-text-secondary"):
        for bg in ("--color-bg-primary", "--color-bg-secondary"):
            lt, lb = _luminance(tokens.get(text, _DEFAULT_TOKENS[text])), _luminance(tokens.get(bg, _DEFAULT_TOKENS[bg]))
            if lt is None or lb is None:
                return False
            hi, lo = max(lt, lb), min(lt, lb)
            if (hi + 0.05) / (lo + 0.05) < MIN_TEXT_CONTRAST:
                return False
    return True


def theme_css(theme_id: str) -> str | None:
    """A theme rebuilt from its colour-token declarations only: `--color-*` / `--shadow-glow` with
    plain colour values. Anything else in the file (url(), @import, selectors, other properties) is
    dropped, and the danger colours can't be changed. None if Pro isn't active or the id is unknown."""
    if not active() or not _THEME_ID_RE.match(theme_id or ""):
        return None
    path = pro_dir() / "themes" / f"{theme_id}.css"
    if not path.is_file():
        return None
    tokens: dict[str, str] = {}
    for name, value in _DECL_RE.findall(path.read_text(encoding="utf-8", errors="replace")):
        value = value.strip()
        if not (name.startswith("--color-") or name == "--shadow-glow"):
            continue
        if name.startswith(_LOCKED) or "url" in value.lower() or not _SAFE_VALUE_RE.match(value):
            continue
        tokens[name] = value
    if not tokens or not _readable(tokens):
        return None
    return ":root {\n" + "\n".join(f"  {k}: {v};" for k, v in tokens.items()) + "\n}\n"


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
