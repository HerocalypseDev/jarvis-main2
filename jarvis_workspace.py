"""Jarvis_Workspace: the default home for every file Jarvis creates, saves or looks up.

Policy: a path that is empty, a bare filename or relative resolves *inside* the workspace, and a
new file is filed into one of the existing subfolders by its name/extension/content. An absolute
path the user spelled out is honored, unless JARVIS_WORKSPACE_STRICT=1, which refuses any write
outside the workspace. `..` can never climb out of the workspace.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

DEFAULT_ROOT = r"C:\Users\USER\OneDrive\Documents\01_Projects\Jarvis_Workspace"
SUBFOLDERS = ("Bugs", "Code_Projects", "Learning_Resources", "Notes", "Assets", "Roblox_Projects", "Temp")

_ASSET_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".avif", ".svg", ".ico", ".psd",
    ".mp3", ".wav", ".ogg", ".flac", ".mp4", ".mov", ".webm", ".mkv", ".ttf", ".otf", ".woff",
    ".woff2", ".fbx", ".obj", ".blend",
}
_ROBLOX_EXT = {".rbxl", ".rbxlx", ".rbxm", ".rbxmx", ".rbxp", ".luau"}
_CODE_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json", ".yaml", ".yml", ".toml",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".java", ".go", ".rs", ".rb", ".php", ".sh", ".bat",
    ".ps1", ".sql", ".lua", ".ipynb",
}
_TEMP_EXT = {".tmp", ".temp", ".bak", ".cache"}
_TEMP_RE = re.compile(r"(^|[^a-z])(temp|tmp|scratch|draft)([^a-z]|$)", re.I)
_BUG_RE = re.compile(r"(^|[^a-z])(bugs?|errors?|crash(es)?|traceback|stack_?trace|issues?|debug|exception)([^a-z]|$)", re.I)
_LEARN_RE = re.compile(
    r"(^|[^a-z])(tutorials?|lessons?|course|learn(ing)?|study|guide|cheat_?sheet|reference|notes_on|how_?to)([^a-z]|$)",
    re.I,
)
_ROBLOX_RE = re.compile(r"roblox|luau|robux|rojo|roact", re.I)
_TRACE_RE = re.compile(r"Traceback \(most recent call last\)|^\s*(Exception|Error):", re.M)


def root() -> Path:
    raw = os.environ.get("JARVIS_WORKSPACE_DIR", "").strip()
    return Path(raw).expanduser() if raw else Path(DEFAULT_ROOT)


def strict() -> bool:
    return os.environ.get("JARVIS_WORKSPACE_STRICT", "").strip().lower() in ("1", "true", "yes")


def classify(filename: str, content: str = "") -> str:
    """Pick the subfolder for a new file from its name, extension and (start of) content."""
    name = Path(filename.replace("\\", "/")).name
    stem, ext = os.path.splitext(name.lower())
    head = (content or "")[:2000]
    if ext in _ROBLOX_EXT or _ROBLOX_RE.search(name) or (ext not in _ASSET_EXT and _ROBLOX_RE.search(head)):
        return "Roblox_Projects"
    if ext in _ASSET_EXT:
        return "Assets"
    if ext in _TEMP_EXT or _TEMP_RE.search(stem):
        return "Temp"
    if ext == ".log" or _BUG_RE.search(stem) or (ext in ("", ".txt", ".md") and _TRACE_RE.search(head)):
        return "Bugs"
    if _LEARN_RE.search(stem):
        return "Learning_Resources"
    if ext in _CODE_EXT:
        return "Code_Projects"
    return "Notes"


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_write_path(path: str, content: str = "") -> tuple[Path | None, str]:
    """Where a file should be written. Returns (path, "") or (None, reason it was refused)."""
    base = root().resolve()
    raw = (path or "").strip()
    if not raw:
        return None, "No path given."
    p = Path(raw).expanduser()
    if p.is_absolute():
        if strict() and not _inside(p.resolve(), base):
            return None, f"Refused: writes must stay inside {base} (JARVIS_WORKSPACE_STRICT is on)."
        return p, ""
    parts = Path(raw.replace("\\", "/")).parts
    if parts and parts[0].lower() in {s.lower() for s in SUBFOLDERS}:
        sub = next(s for s in SUBFOLDERS if s.lower() == parts[0].lower())
        rel = Path(sub, *parts[1:])
    else:
        rel = Path(classify(raw, content), *parts)
    target = (base / rel).resolve()
    if not _inside(target, base):
        return None, f"Refused: {raw!r} would land outside {base}."
    return target, ""


def resolve_read_path(path: str) -> Path:
    """Absolute paths are used as given; a relative one is looked up in the workspace first."""
    p = Path((path or "").strip()).expanduser()
    if p.is_absolute() or not str(p).strip("."):
        return p
    base = root()
    candidates = [base / p] + [base / s / p for s in SUBFOLDERS]
    for c in candidates:
        try:
            if c.is_file() and _inside(c.resolve(), base.resolve()):
                return c
        except OSError:
            continue
    return p


def default_dir(subfolder: str) -> Path:
    """A workspace subfolder, created if missing (for tools that pick their own file name)."""
    d = root() / subfolder
    d.mkdir(parents=True, exist_ok=True)
    return d
