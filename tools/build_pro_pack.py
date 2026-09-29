"""Build the Jarvis4U Pro download (seller only; never published).

    python tools/build_pro_pack.py

Checks every file in pro_pack/ (valid JSON, each skill has a name and instructions, the tools a skill
names really exist, themes survive the loader's colour-only rebuild), then writes
dist/Jarvis4U-Pro-<version>.zip. Upload that zip as the file of the "Jarvis4U Pro" product on Selar.

The zip contains a top-level `pro/` folder plus INSTALL.txt, so buyers unzip it straight into their
Jarvis4U folder.
"""
from __future__ import annotations

import json
import os
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "pro_pack"
DIST = ROOT / "dist"

INSTALL = """Jarvis4U Pro {version}
===================

Thank you for supporting Jarvis4U!

1. Unzip this file into your Jarvis4U folder (the one with jarvis.py in it).
   You should end up with a folder called "pro" next to jarvis.py.
2. Start Jarvis, open the dashboard (http://127.0.0.1:8765) -> Settings -> Jarvis4U Pro.
3. Paste the license key you received by email and press Activate.
4. Still in Settings -> Jarvis4U Pro, pick a Pro theme if you like.

Student pack - just ask Jarvis:
  "Start a study session on chemistry for 50 minutes"
  "My maths exam is on Friday at 9"          / "How many days until my exams?"
  "I have history homework due Thursday"       / "What homework do I have?"
  "Quiz me on photosynthesis"                  / "Quiz me from my biology notes"
  "Make me a revision timetable"
  "Make notes on the French revolution"
  (every evening at 8pm Jarvis quietly checks what's due and only speaks if something is close)

Developer pack - just ask Jarvis:
  "Brief me on this repo"                      / "Write my standup"
  "Explain this error" (copy the error first)  / "Why is CI failing?" (copy the log first)
  "Review my changes in <folder>"
  "Hand this to Claude Code properly: <task>"
  "Watch <folder> for code health" (then a quiet 9am check that only speaks if something risky shows up)
  Developer skills only ever run read-only git commands; they never commit, push or edit your code.

Updates: new packs are added to the same download on Selar; download it again and replace the
"pro" folder. Your license key keeps working.

Need help? Reply to your purchase email.
"""


IGNORE_WORDS: set[str] = set()


def _known_tools() -> tuple[set[str], set[str]]:
    """(tool names, parameter names across all tools)."""
    os.environ.setdefault("JARVIS_MEMORY_DB_PATH", str(DIST / "_build_check.db"))
    os.environ.setdefault("ANTHROPIC_API_KEY", "build-check")
    sys.path.insert(0, str(ROOT))
    import jarvis  # noqa: E402

    tools = {t["name"] for t in jarvis.AGENT_TOOLS}
    params = {k for t in jarvis.AGENT_TOOLS for k in ((t.get("input_schema") or {}).get("properties") or {})}
    return tools, params


def check() -> dict:
    manifest = json.loads((SRC / "manifest.json").read_text(encoding="utf-8"))
    for key in ("name", "version"):
        if not manifest.get(key):
            raise SystemExit(f"manifest.json needs a {key!r}")
    tools, params = _known_tools()
    skill_names = {p.stem for p in (SRC / "skills").glob("*.json")}
    names = set()
    for path in sorted((SRC / "skills").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        name = str(data.get("name") or "").strip()
        if not name or not str(data.get("instructions") or "").strip():
            raise SystemExit(f"{path.name}: needs name and instructions")
        if name.lower() in names:
            raise SystemExit(f"{path.name}: duplicate skill name {name!r}")
        names.add(name.lower())
        # Every snake_case word must be a real tool, a real tool parameter, or another pack skill, so a
        # typo'd or invented tool name can never ship.
        mentioned = set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", data["instructions"]))
        unknown = mentioned - tools - params - skill_names - IGNORE_WORDS
        if unknown:
            raise SystemExit(f"{path.name}: names tools Jarvis doesn't have: {sorted(unknown)}")
    import jarvis_pro

    real_active = jarvis_pro.active
    os.environ["JARVIS_PRO_DIR"] = str(SRC)
    jarvis_pro.active = lambda: True
    try:
        for path in sorted((SRC / "themes").glob("*.css")):
            if not jarvis_pro.theme_css(path.stem):
                raise SystemExit(f"{path.name}: no usable colour tokens after the loader's rebuild")
    finally:
        jarvis_pro.active = real_active
    return manifest


def build() -> Path:
    manifest = check()
    DIST.mkdir(exist_ok=True)
    out = DIST / f"Jarvis4U-Pro-{manifest['version']}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("INSTALL.txt", INSTALL.format(version=manifest["version"]))
        for path in sorted(SRC.rglob("*")):
            if path.is_file() and not path.name.startswith("."):
                z.write(path, "pro/" + path.relative_to(SRC).as_posix())
    return out


if __name__ == "__main__":
    path = build()
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    print(f"Built {path} ({path.stat().st_size // 1024} KB, {len(names)} files)")
    print("\n".join("  " + n for n in names))
    print("Upload this zip as the Jarvis4U Pro product file on Selar.")
