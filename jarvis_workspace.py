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

DEFAULT_ROOT = str(Path.home() / "OneDrive" / "Documents" / "01_Projects" / "Jarvis_Workspace")

# --- sensitive-path policy (audit H4): even a user-spelled absolute path may not read credentials or ---
# --- write over Jarvis's own code / persistence points, because a prompt-injected agent run can ask ---
# --- for exactly that (read .env, then http_request it out; or plant a Startup entry). -----------------
_CODE_DIR = Path(__file__).resolve().parent
_SENSITIVE_NAMES = {
    "face.key", "credentials.json", "gcp-oauth.keys.json", "mcp_servers.json", "id_rsa", "id_ed25519",
    "id_ecdsa", "known_hosts", "jarvis_memory.db", "session_state.json", "llm_provider.json", "ntuser.dat",
}
_SENSITIVE_SUFFIXES = (".pem", ".key", ".pfx", ".p12", ".kdbx", ".ppk")
_SENSITIVE_DIRS = {".ssh", ".gnupg", ".aws", ".gmail-mcp", "google-calendar-mcp", "jarvis"}  # last = %LOCALAPPDATA%\Jarvis
_WRITE_ONLY_DIRS = {".claude", ".git", "startup"}


def _sensitive_parts(p: Path) -> tuple[str, list[str]]:
    try:
        rp = p.expanduser().resolve()
    except (OSError, RuntimeError):
        rp = p.expanduser()
    return rp.name.lower(), [x.lower() for x in rp.parts[:-1]]


def sensitive_reason(path: str, write: bool = False) -> str | None:
    """Why Jarvis's file tools must not touch this path (None = fine). Reads are refused for
    credentials/keys/its own databases; writes are additionally refused inside its own code
    folder, .git/.claude and the Windows Startup folder."""
    raw = (path or "").strip()
    if not raw:
        return None
    p = Path(raw)
    name, parents = _sensitive_parts(p)
    if name.startswith(".env") or name in _SENSITIVE_NAMES or name.endswith(_SENSITIVE_SUFFIXES) \
            or name.startswith(("face.db", "jarvis_memory.db")):
        return "that looks like a credential or one of Jarvis's private data files"
    if any(part in _SENSITIVE_DIRS for part in parents if part != "jarvis" or "appdata" in parents):
        return "that folder holds credentials or Jarvis's private data"
    if write:
        if any(part in _WRITE_ONLY_DIRS for part in parents):
            return "writing there could plant code that runs later (.git, .claude or the Startup folder)"
        try:
            rp = p.expanduser().resolve()
            if rp == _CODE_DIR or _CODE_DIR in rp.parents:
                return "that is Jarvis's own code folder; use change_jarvis_code for source changes"
        except (OSError, RuntimeError):
            pass
    return None
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
    if p.is_absolute() or raw.lower().startswith(".env"):
        bad = sensitive_reason(raw, write=True)
        if bad:
            return None, f"Refused: {bad}."
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
    bad = sensitive_reason(str(target), write=True)
    if bad:
        return None, f"Refused: {bad}."
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
