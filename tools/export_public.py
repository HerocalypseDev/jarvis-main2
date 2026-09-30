"""Build the public Jarvis4U copy of this (private) repo.

    python tools/export_public.py <target_dir> [--check-only]

What it does, in order:
  1. Takes ONLY files git tracks here (`git ls-files`), so nothing gitignored (.env, jarvis_memory.db,
     session_state.json, mcp_servers.json, logs, caches) can ever be copied, even by mistake.
  2. Drops everything on EXCLUDE (personal notes, your own skills, generated/junk folders, the
     Discord self-bot).
  3. Rewrites personal values into generic ones (REPLACE: names, city; DEFAULTS: code defaults
     that only suit this machine). The private repo itself is never modified, so your own Jarvis
     keeps behaving exactly as before.
  4. Lays the public-only files from `public/` on top (README, LICENSE, .env.example, CLAUDE.md,
     example skills).
  5. Scans every output file for anything personal or secret (DENY words, real-looking email
     addresses, key/token shapes, Windows user paths). Any hit = exit code 1, and the target is
     left as a work area you should not publish.

The target dir may be an existing clone of the public repo: its .git is kept and every other file
is replaced, so `git -C <target> add -A && git -C <target> commit` then shows exactly what changed.
Nothing is ever committed or pushed by this script.

Extra private words to block (a name, a street, a project) go in `public_export_denylist.txt`
next to this repo's root, one per line. That file is gitignored, so the list itself stays private.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OVERLAY = ROOT / "public"
LOCAL_DENYLIST = ROOT / "public_export_denylist.txt"

# Tracked paths (prefix match on the posix path) that never go public.
EXCLUDE = (
    "CLAUDE.md",                 # private working notes (family, decisions, history)
    "README.md",                 # replaced by public/README.md
    "Later.md",
    "discord_selfbot_server.py", # self-bot against Discord's ToS: not something to hand out
    "skills/",                   # your own routines; public gets examples/skills instead
    "graphify-out/",
    "brag-output",
    "snake_",
    ".claude/",
    "public/",                   # overlay source, copied separately
    "tools/export_public.py",
    "pro_pack/",                 # the PAID Pro pack source: must never reach the public repo
    "tools/build_pro_pack.py",
    "test_pro_pack.py",
    "PRO_ROADMAP.md",            # private business plan
    "RESEARCH_AGENTIC.md",       # private research notes (owner's limits and plans)
    "dist/",
    "session_state.json",
    "jarvis_memory.db",
)

# Whole-word replacements applied to every text file (case-sensitive; order matters for emails).
REPLACE = (
    ("rachealpower25@gmail.com", "riley@example.com"),
    ("Racheal", "Riley"), ("racheal", "riley"),
    ("Jacob", "Morgan"),
    ("Ayo", "Alex"),
    ("HERO", "FRIEND"), ("Hero", "Friend"), ("hero", "friend"),
    ("Lagos", "Leeds"), ("Nigeria", "England"),
    ("PPM", "Chemistry"), ("ppm", "chemistry"),
)

# Exact code-default swaps: (file, old, new, expected count). A count mismatch aborts the export,
# so a refactor can't silently leave a personal default in place.
DEFAULTS = (
    ("jarvis_workspace.py",
     'Path.home() / "OneDrive" / "Documents" / "01_Projects" / "Jarvis_Workspace"',
     'Path.home() / "Documents" / "Jarvis_Workspace"', 1),
    ("jarvis_audio_duck.py", '"JARVIS_DUCK_PAUSE_APPS", "OperaGX"', '"JARVIS_DUCK_PAUSE_APPS", ""', 1),
    ("jarvis_audio_duck.py", '"JARVIS_MEDIA_APP", "Opera"', '"JARVIS_MEDIA_APP", ""', 1),
    ("jarvis_autonomy_organise.py", 'home() / "Documents" / "01_Projects" / "Jarvis_Workspace"',
     'home() / "Documents" / "Jarvis_Workspace"', 1),
    ("jarvis_autonomy_organise.py", "C:\\\\Users\\\\<you>\\\\OneDrive\\\\Documents\\\\01_Projects\\\\Jarvis_Workspace here",
     "~\\\\Documents\\\\Jarvis_Workspace by default", 1),
    ("AUTONOMY.md", "here `C:\\Users\\USER\\OneDrive\\Documents\\01_Projects\\Jarvis_Workspace`",
     "by default `~\\Documents\\Jarvis_Workspace`", 1),
    # Strangers get autonomy OFF unless they turn it on (your install keeps its own default).
    ("jarvis_autonomy.py", 'os.environ.get("JARVIS_AUTONOMY_ENABLED", "1")',
     'os.environ.get("JARVIS_AUTONOMY_ENABLED", "0")', 1),
    ("test_autonomy.py", "def test_autonomy_is_on_by_default_and_can_be_switched_off(",
     "def test_autonomy_is_off_by_default_and_can_be_switched_on(", 1),
    ("test_autonomy.py",
     "    assert a.enabled() is True and a.dry_run() is False           # on, and live (not dry-run)\n"
     "    a.set_enabled(False)\n",
     "    assert a.enabled() is False                                   # public default: off\n"
     "    a.set_enabled(True)\n    assert a.enabled() is True and a.dry_run() is False  # a stored choice beats the default\n"
     "    a.set_enabled(False)\n", 1),
    ("test_cache.py", '(Path(__file__).parent / "skills" / "gmail_watch.json")',
     '(Path(__file__).parent / "examples" / "skills" / "gmail_watch.json")', 1),
)

# Lines appended to the copied .gitignore.
GITIGNORE_EXTRA = (
    "",
    "# public repo extras",
    "skills/*.json",
    "public_export_denylist.txt",
)

# --- privacy scan ----------------------------------------------------------------------------
DENY_WORDS = (
    "Hero", "Racheal", "Jacob", "Ayo", "Lagos", "Nigeria", "PPM", "ayojacobgo", "rachealpower",
    "01_Projects", "Jarvis_Workspace\\Notes",
)
DENY_ALLOWED_FILES = {"LICENSE"}  # the copyright line names the GitHub account on purpose
PERSONAL_MAIL_DOMAINS = ("gmail.com", "googlemail.com", "yahoo.", "hotmail.", "outlook.", "live.com",
                         "icloud.com", "proton.me", "protonmail.", "aol.com", "gmx.")
SECRET_PATTERNS = (
    ("Anthropic key", r"sk-ant-[A-Za-z0-9_-]{16,}"),
    ("Google key", r"AIza[0-9A-Za-z_-]{30,}"),
    ("Google OAuth token", r"\bAQ\.[A-Za-z0-9_-]{20,}"),
    ("GitHub token", r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    ("Slack token", r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    ("Telegram bot token", r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"),
    ("private key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    # test fixtures use the placeholder users "x" and "USER"
    ("Windows user path", r"[A-Za-z]:[\\/]{1,2}Users[\\/]{1,2}(?!(?:you|YOU|x|USER|USERNAME)(?![A-Za-z0-9._-])|<you>|<user>|\.\.\.)[A-Za-z0-9._-]+"),
)
FAKE_SECRET_MARKERS = ("abcdefghijklmnop", "supersecret", "xxxxxxxx", "EXAMPLE")  # obvious test fixtures
BINARY_OK = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".wav", ".onnx"}


def _git_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
    return [p for p in out.stdout.decode("utf-8").split("\0") if p]


def _excluded(path: str) -> bool:
    return any(path == e or path.startswith(e) for e in EXCLUDE)


def _is_text(data: bytes) -> bool:
    if b"\0" in data[:8192]:
        return False
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _scrub(text: str) -> str:
    for old, new in REPLACE:
        if "@" in old:
            text = text.replace(old, new)
        else:
            text = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(old)}(?![A-Za-z0-9_])", new, text)
    return text


def _denylist() -> list[str]:
    words = list(DENY_WORDS)
    if LOCAL_DENYLIST.exists():
        words += [w.strip() for w in LOCAL_DENYLIST.read_text(encoding="utf-8").splitlines()
                  if w.strip() and not w.startswith("#")]
    return words


def scan(target: Path) -> list[str]:
    """Every privacy/secret hit in the built tree, as 'path:line: reason'."""
    words = _denylist()
    word_re = re.compile("|".join(rf"(?<![A-Za-z0-9_]){re.escape(w)}(?![A-Za-z0-9_])" for w in words))
    mail_re = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
    secret_res = [(name, re.compile(p)) for name, p in SECRET_PATTERNS]
    hits: list[str] = []
    for path in sorted(target.rglob("*")):
        if ".git" in path.relative_to(target).parts or not path.is_file():
            continue
        rel = path.relative_to(target).as_posix()
        data = path.read_bytes()
        if not _is_text(data):
            if path.suffix.lower() not in BINARY_OK:
                hits.append(f"{rel}: unexpected binary file")
            continue
        for n, line in enumerate(data.decode("utf-8").splitlines(), 1):
            if rel not in DENY_ALLOWED_FILES and (m := word_re.search(line)):
                hits.append(f"{rel}:{n}: private word {m.group(0)!r}")
            for m in mail_re.finditer(line):
                if any(m.group(1).lower().startswith(d) or m.group(1).lower().endswith(d)
                       for d in PERSONAL_MAIL_DOMAINS):
                    hits.append(f"{rel}:{n}: personal email address {m.group(0)!r}")
            for name, rx in secret_res:
                m = rx.search(line)
                if m and not any(fake in m.group(0) for fake in FAKE_SECRET_MARKERS):
                    hits.append(f"{rel}:{n}: looks like a {name}")
    return hits


def build(target: Path) -> list[str]:
    target.mkdir(parents=True, exist_ok=True)
    for child in target.iterdir():  # keep an existing public clone's .git, replace everything else
        if child.name == ".git":
            continue
        shutil.rmtree(child) if child.is_dir() else child.unlink()

    written: list[str] = []
    defaults_seen = {i: 0 for i in range(len(DEFAULTS))}
    for rel in _git_files():
        if _excluded(rel):
            continue
        src = ROOT / rel
        if not src.is_file():  # deleted in the working tree but not yet committed
            continue
        data = src.read_bytes()
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not _is_text(data):
            dst.write_bytes(data)
            written.append(rel)
            continue
        text = data.decode("utf-8")
        for i, (fname, old, new, _count) in enumerate(DEFAULTS):
            if rel == fname:
                defaults_seen[i] += text.count(old)
                text = text.replace(old, new)
        if rel == "mcp_servers.example.json":
            cfg = json.loads(text)
            cfg.pop("discord", None)
            text = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
        if rel == ".gitignore":
            text = text.rstrip("\n") + "\n" + "\n".join(GITIGNORE_EXTRA) + "\n"
        text = _scrub(text)
        dst.write_text(text, encoding="utf-8", newline="")
        written.append(rel)

    bad = [DEFAULTS[i][:2] for i, seen in defaults_seen.items() if seen != DEFAULTS[i][3]]
    if bad:
        raise SystemExit(f"Default swap no longer matches the code, fix DEFAULTS first: {bad}")

    for src in sorted(OVERLAY.rglob("*")):
        if src.is_file():
            rel = src.relative_to(OVERLAY).as_posix()
            dst = target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            if rel not in written:
                written.append(rel)
    return sorted(written)


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    target = Path(argv[0]).resolve()
    if target == ROOT or ROOT in target.parents:
        print("Refusing: the target must be outside this repo.")
        return 2
    if "--check-only" not in argv:
        files = build(target)
        (target.parent / f"{target.name}.manifest.txt").write_text("\n".join(files) + "\n", encoding="utf-8")
        print(f"Built {len(files)} files into {target}")
    hits = scan(target)
    if hits:
        print(f"PRIVACY SCAN FAILED ({len(hits)} hits). Do not publish this copy:")
        print("\n".join("  " + h for h in hits[:200]))
        return 1
    print("Privacy scan: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
