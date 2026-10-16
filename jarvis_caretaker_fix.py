"""Caretaker fixes, storage family (2026-10-16): free disk space without ever making a mistake you can't take back.

Pure stdlib, never imports jarvis.py. Everything takes its folders as arguments, so tests run on temp dirs.

Three kinds of action, in the order they are tried (cheapest and safest first, stopping once enough is free):
1. CACHES / TEMP (green): files that rebuild themselves, older than CACHE_MIN_AGE_DAYS, deleted outright.
2. OLD RECYCLE BIN items (green): only those that have sat there RECYCLE_OLDER_DAYS.
3. OLD INSTALLERS in Downloads (yellow): big installer/archive files not touched for STALE_DAYS are MOVED to the
   holding folder (never deleted); they are really removed only after HOLDING_DAYS, and "undo" puts them back.
The user's own files are only ever moved by (3), and only through `hold`, which refuses protected places.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import jarvis_caretaker as ct
import jarvis_workspace as workspace

CACHE_MIN_AGE_DAYS = 2          # a cache file touched in the last 2 days may be in use
RECENT_USE_DAYS = 30            # anything the user touched this recently is never moved
STALE_DAYS = 30                 # an installer/archive this old in Downloads is a candidate
STALE_MIN_MB = 50
INSTALLER_EXT = {".exe", ".msi", ".msix", ".iso", ".zip", ".7z", ".rar", ".img", ".dmg", ".pkg", ".cab"}
# Folders directly under the home folder that are the user's own work: nothing in them is ever moved.
PROTECTED_HOME_DIRS = {"documents", "desktop", "pictures", "videos", "music", "source", "repos", "projects",
                       "code", "dev", "github", "saved games", "contacts", "favorites", "links", "3d objects"}
PROTECTED_ANYWHERE = {".git", ".ssh", ".gnupg", ".aws", ".config", "appdata"}
_SYSTEM_PREFIXES = ("c:\\windows", "c:\\program files", "c:\\programdata", "c:\\users\\default")
MANIFEST = "manifest.json"
MAX_WALK_FILES = 80000


def _now(now=None) -> datetime:
    return now or datetime.now()


def _old_enough(mtime: float, days: float, now: datetime) -> bool:
    return (now - datetime.fromtimestamp(mtime)) >= timedelta(days=days)


# --- 1. caches / temp ---------------------------------------------------------------------------
def clear_caches(roots: list[Path], *, min_age_days: float = CACHE_MIN_AGE_DAYS, now=None,
                 dry_run: bool = False) -> dict:
    """Delete cache files older than `min_age_days` under the given roots. Never follows symlinks, never leaves
    a root, skips anything in use (a locked file simply fails and is left). Returns {freed, files, skipped}."""
    now = _now(now)
    freed = files = skipped = 0
    for root in roots:
        try:
            root = Path(root).resolve()
        except OSError:
            continue
        if not root.is_dir() or workspace.too_broad(root) or workspace.sensitive_reason(str(root), write=True):
            skipped += 1
            continue
        seen = 0
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
            for name in filenames:
                seen += 1
                if seen > MAX_WALK_FILES:
                    break
                p = os.path.join(dirpath, name)
                try:
                    if os.path.islink(p):
                        continue
                    st = os.stat(p, follow_symlinks=False)
                    if not _old_enough(st.st_mtime, min_age_days, now):
                        continue
                    if not dry_run:
                        os.remove(p)
                    freed += st.st_size
                    files += 1
                except OSError:
                    skipped += 1   # in use / permission: leave it alone
            if seen > MAX_WALK_FILES:
                break
    return {"freed": freed, "files": files, "skipped": skipped}


# --- 2. old recycle-bin items -------------------------------------------------------------------
def recycle_bin_dirs() -> list[Path]:
    """<drive>:\\$Recycle.Bin\\<SID> folders on this PC (Windows); empty elsewhere."""
    out: list[Path] = []
    if os.name != "nt":
        return out
    for letter in "CDEFGH":
        base = Path(f"{letter}:\\$Recycle.Bin")
        try:
            if base.is_dir():
                out += [d for d in base.iterdir() if d.is_dir()]
        except OSError:
            continue
    return out


def purge_recycle(bin_dirs: list[Path], *, older_days: float = ct.RECYCLE_OLDER_DAYS, now=None,
                  dry_run: bool = False) -> dict:
    """Remove Recycle Bin items that were deleted at least `older_days` ago. The `$I<id>` metadata file is created
    at deletion time, so its mtime is the deletion time; the payload is the matching `$R<id>`."""
    now = _now(now)
    freed = items = 0
    for d in bin_dirs:
        try:
            entries = list(Path(d).iterdir())
        except OSError:
            continue
        for meta in entries:
            if not meta.name.startswith("$I"):
                continue
            try:
                if not _old_enough(meta.stat().st_mtime, older_days, now):
                    continue
            except OSError:
                continue
            payload = Path(d) / ("$R" + meta.name[2:])
            size = 0
            try:
                if payload.is_dir() and not payload.is_symlink():
                    size = sum(f.stat().st_size for f in payload.rglob("*") if f.is_file() and not f.is_symlink())
                    if not dry_run:
                        shutil.rmtree(payload, ignore_errors=True)
                elif payload.exists():
                    size = payload.stat().st_size
                    if not dry_run:
                        payload.unlink()
                if not dry_run:
                    meta.unlink()
                freed += size
                items += 1
            except OSError:
                continue
    return {"freed": freed, "items": items}


# --- 3. the holding folder ----------------------------------------------------------------------
def hold_problem(path: str | os.PathLike, *, home: Path, holding_root: Path, code_dir: Path | None = None,
                 now=None) -> str | None:
    """Why this path must NOT be moved to the holding folder (None = allowed)."""
    now = _now(now)
    p = Path(path)
    if p.is_symlink():
        return "it's a shortcut/link"
    try:
        rp = p.resolve()
    except OSError:
        return "can't read it"
    if not rp.is_file():
        return "it isn't a plain file"
    if workspace.too_broad(rp):
        return "too broad"
    if workspace.sensitive_reason(str(rp), write=True):
        return "it looks like a credential, a private file or code Jarvis protects"
    low = str(rp).lower().replace("/", "\\")
    if low.startswith(_SYSTEM_PREFIXES):
        return "it's part of Windows or an installed program"
    try:
        rel = rp.relative_to(Path(home).resolve())
        top = rel.parts[0].lower() if rel.parts else ""
        if top in PROTECTED_HOME_DIRS or top.startswith("onedrive"):
            return f"it's in your {rel.parts[0]} folder"
    except ValueError:
        pass   # outside the home folder: judged by the checks below
    if any(part.lower() in PROTECTED_ANYWHERE for part in rp.parts):
        return "it's in a protected folder"
    if Path(holding_root).resolve() in rp.parents:
        return "it's already in the holding folder"
    if code_dir and (Path(code_dir).resolve() == rp or Path(code_dir).resolve() in rp.parents):
        return "it's Jarvis's own code"
    for parent in rp.parents:
        if (parent / ".git").exists():
            return "it's inside a code project"
    try:
        if _old_enough(rp.stat().st_mtime, RECENT_USE_DAYS, now):
            return None
    except OSError:
        return "can't read it"
    return f"you changed it in the last {RECENT_USE_DAYS} days"


def find_stale_installers(downloads: Path, *, min_mb: float = STALE_MIN_MB, older_days: float = STALE_DAYS,
                          now=None) -> list[tuple[str, int]]:
    """Big installer/archive files in Downloads nobody has touched for a month, biggest first."""
    now = _now(now)
    out: list[tuple[str, int]] = []
    seen = 0
    try:
        base = Path(downloads).resolve()
    except OSError:
        return out
    if not base.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            seen += 1
            if seen > MAX_WALK_FILES:
                return sorted(out, key=lambda t: -t[1])
            if os.path.splitext(name)[1].lower() not in INSTALLER_EXT:
                continue
            p = os.path.join(dirpath, name)
            try:
                st = os.stat(p, follow_symlinks=False)
            except OSError:
                continue
            if st.st_size >= min_mb * 1024 * 1024 and _old_enough(st.st_mtime, older_days, now):
                out.append((p, st.st_size))
    return sorted(out, key=lambda t: -t[1])


def hold(paths: list[str], holding_root: Path, *, home: Path, issue_key: str = "", code_dir: Path | None = None,
         now=None) -> dict:
    """Move files into holding/<date>-<id>/ and write a manifest so `restore` can put them back. Refused files are
    reported, never moved. Returns {"manifest": path|None, "moved": [...], "refused": [(path, why)], "bytes": n}."""
    now = _now(now)
    holding_root = Path(holding_root)
    batch = holding_root / f"{now:%Y-%m-%d}-{uuid.uuid4().hex[:6]}"
    moved: list[dict] = []
    refused: list[tuple[str, str]] = []
    for src in paths:
        why = hold_problem(src, home=home, holding_root=holding_root, code_dir=code_dir, now=now)
        if why:
            refused.append((str(src), why))
            continue
        try:
            batch.mkdir(parents=True, exist_ok=True)
            size = Path(src).stat().st_size
            dest = batch / f"{len(moved):03d}__{Path(src).name}"
            shutil.move(str(src), str(dest))
            moved.append({"orig": str(src), "held": str(dest), "size": size})
        except OSError as e:
            refused.append((str(src), f"couldn't move it ({e.__class__.__name__})"))
    manifest = None
    if moved:
        manifest = batch / MANIFEST
        manifest.write_text(json.dumps({"ts": now.isoformat(timespec="seconds"), "issue": issue_key,
                                        "items": moved}, indent=1), encoding="utf-8")
    return {"manifest": str(manifest) if manifest else None, "moved": moved, "refused": refused,
            "bytes": sum(m["size"] for m in moved)}


def restore(manifest_path: str | os.PathLike) -> dict:
    """Undo a hold: put every file back where it came from. If something new sits at the old path the file comes
    back beside it as '<name> (restored)' - nothing is ever overwritten."""
    mp = Path(manifest_path)
    try:
        data = json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"restored": 0, "problems": ["the holding record is gone (already purged or undone)"]}
    restored, problems = 0, []
    for it in data.get("items", []):
        held, orig = Path(it["held"]), Path(it["orig"])
        if not held.exists():
            problems.append(f"{orig.name} is no longer in the holding folder")
            continue
        dest = orig
        if dest.exists():
            dest = orig.with_name(f"{orig.stem} (restored){orig.suffix}")
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(held), str(dest))
            restored += 1
        except OSError as e:
            problems.append(f"{orig.name}: {e.__class__.__name__}")
    if not problems:
        shutil.rmtree(mp.parent, ignore_errors=True)
    return {"restored": restored, "problems": problems}


def purge_holding(holding_root: Path, *, days: float = ct.HOLDING_DAYS, now=None) -> dict:
    """Really delete holding batches older than `days`. This is the one place the user's moved files are removed."""
    now = _now(now)
    freed = batches = 0
    root = Path(holding_root)
    if not root.is_dir():
        return {"freed": 0, "batches": 0}
    for batch in root.iterdir():
        if not batch.is_dir():
            continue
        try:
            ts = datetime.fromisoformat(json.loads((batch / MANIFEST).read_text(encoding="utf-8"))["ts"])
        except (OSError, ValueError, KeyError):
            ts = datetime.fromtimestamp(batch.stat().st_mtime)   # no manifest: age by the folder itself
        if now - ts < timedelta(days=days):
            continue
        size = sum(f.stat().st_size for f in batch.rglob("*") if f.is_file())
        shutil.rmtree(batch, ignore_errors=True)
        freed += size
        batches += 1
    return {"freed": freed, "batches": batches}


def holding_summary(holding_root: Path, *, now=None) -> list[dict]:
    """What is waiting in the holding folder: one row per batch with its size and the days left before it is removed."""
    now = _now(now)
    out: list[dict] = []
    root = Path(holding_root)
    if not root.is_dir():
        return out
    for batch in sorted(root.iterdir()):
        if not batch.is_dir():
            continue
        try:
            ts = datetime.fromisoformat(json.loads((batch / MANIFEST).read_text(encoding="utf-8"))["ts"])
        except (OSError, ValueError, KeyError):
            ts = datetime.fromtimestamp(batch.stat().st_mtime)
        files = [f for f in batch.rglob("*") if f.is_file() and f.name != MANIFEST]
        left = ct.HOLDING_DAYS - (now - ts).total_seconds() / 86400
        out.append({"batch": batch.name, "files": len(files), "bytes": sum(f.stat().st_size for f in files),
                    "days_left": max(0, round(left, 1)), "names": [f.name.split("__", 1)[-1] for f in files[:5]]})
    return out


def undo(undo_info: dict | None) -> str:
    """Run the undo recorded with an action. Returns one plain sentence."""
    if not undo_info or undo_info.get("kind") != "hold":
        return "That action can't be undone."
    r = restore(undo_info.get("manifest", ""))
    if r["restored"] and not r["problems"]:
        return f"Put {r['restored']} file(s) back where they were."
    if r["restored"]:
        return f"Put {r['restored']} file(s) back; {len(r['problems'])} couldn't be restored: {r['problems'][0]}."
    return "Nothing restored: " + (r["problems"][0] if r["problems"] else "no files found.")


# --- the storage playbook -----------------------------------------------------------------------
class StorageEnv:
    """Everything the playbook needs from the machine, so tests can run it on temp folders."""

    def __init__(self, *, cache_roots, bin_dirs, downloads: Path, holding_root: Path, home: Path,
                 free_fraction, code_dir: Path | None = None, now=None):
        self.cache_roots, self.bin_dirs = cache_roots, bin_dirs
        self.downloads, self.holding_root, self.home = Path(downloads), Path(holding_root), Path(home)
        self.free_fraction, self.code_dir, self.now = free_fraction, code_dir, now


def fix_storage(store: ct.Store, issue_key: str, env: StorageEnv, *, target: float = ct.DISK_FREE_TARGET) -> dict:
    """Free space in the safest order, stopping once `target` of the drive is free. Every step is logged with its
    tier and, where it can be undone, how. Returns {"freed", "held", "steps", "reached", "free_after", "blocked"}."""
    steps: list[str] = []
    total = held_bytes = 0
    blocked = None

    def result() -> dict:
        return {"freed": total, "held": held_bytes, "steps": steps, "reached": env.free_fraction() >= target,
                "free_after": env.free_fraction(), "blocked": blocked}

    def reached() -> bool:
        return env.free_fraction() >= target

    if reached():
        return result()

    # 1. caches / temp
    blocked = ct.budget_blocked(store)
    if not blocked:
        r = clear_caches(env.cache_roots, now=env.now)
        if r["files"]:
            total += r["freed"]
            store.log_action(issue_key, ct.GREEN, "clear_caches", f"{r['files']} old cache/temp files",
                             "deleted (they rebuild themselves)", freed_bytes=r["freed"])
            steps.append(f"cleared {ct.human_bytes(r['freed'])} of caches and temp files")

    # 2. old Recycle Bin items
    if not reached():
        blocked = ct.budget_blocked(store)
        if not blocked:
            r = purge_recycle(env.bin_dirs, now=env.now)
            if r["items"]:
                total += r["freed"]
                store.log_action(issue_key, ct.GREEN, "purge_recycle",
                                 f"{r['items']} items older than {ct.RECYCLE_OLDER_DAYS} days",
                                 "emptied from the Recycle Bin", freed_bytes=r["freed"])
                steps.append(f"emptied {ct.human_bytes(r['freed'])} of old Recycle Bin items")

    # 3. old installers: moved to the holding folder, undoable (frees space only after HOLDING_DAYS)
    if not reached():
        blocked = ct.budget_blocked(store)
        cands = [] if blocked else find_stale_installers(env.downloads, now=env.now)
        room = ct.MAX_MOVE_GB_PER_DAY * 1024 ** 3 - store.bytes_moved_today()
        fit, acc = [], 0
        for p, s in cands:
            if acc + s <= room:
                fit.append(p)
                acc += s
        if cands and not fit:
            blocked = f"would move more than {ct.MAX_MOVE_GB_PER_DAY:.0f} GB of your files today"
        if fit:
            r = hold(fit, env.holding_root, home=env.home, issue_key=issue_key, code_dir=env.code_dir, now=env.now)
            if r["moved"]:
                held_bytes += r["bytes"]
                store.log_action(issue_key, ct.YELLOW, "hold_files",
                                 f"{len(r['moved'])} old installer/archive file(s) from Downloads",
                                 f"moved to the holding folder for {ct.HOLDING_DAYS} days",
                                 freed_bytes=r["bytes"], undo={"kind": "hold", "manifest": r["manifest"]})
                steps.append(f"moved {len(r['moved'])} old installer(s) ({ct.human_bytes(r['bytes'])}) to the "
                             f"holding folder; they free space after {ct.HOLDING_DAYS} days")
    return result()
