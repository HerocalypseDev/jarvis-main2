"""Automatic file organising for the autonomy layer. ON as soon as autonomy is on: no enable flag.

What it does: when the file watcher reports a NEW file directly inside an allowlisted folder, the first matching
rule files it into a tidy folder under the user profile. Built-in defaults work immediately:

  allowlisted folders (those that exist): ~/Downloads, ~/Desktop, ~/OneDrive/Desktop, ~/OneDrive/Downloads
  rules:  PDF/DOC/DOCX/PPTX/RTF/ODT/EPUB -> ~/Documents/Jarvis_Organised/Documents
          XLS/XLSX/CSV/ODS               -> ~/Documents/Jarvis_Organised/Spreadsheets
          PNG/JPG/JPEG/WEBP/GIF          -> ~/Pictures/Jarvis_Organised
          (destination folders are created when missing)

You can add or override rules, add or remove folders, and see what was filed, by voice (`autonomy_organise`
tool), in the dashboard's Autonomy tab, or with JARVIS_AUTONOMY_ORGANISE_ROOTS (extra folders, os.pathsep-
separated). A rule you write beats a default one; removing a default is remembered.

Safety (all enforced in code, all tested):
  * MOVE or COPY only. Never deletes. Never overwrites: a name clash gets a timestamp suffix. A cross-drive move
    is done as a copy and the original is left in place.
  * realpath checks: the file must resolve inside an allowlisted folder and sit directly in it (not in a
    sub-folder), so `..` traversal, symlinks and junctions that leave the folder are rejected; destinations must
    resolve inside the user profile.
  * Only regular files; temp/partial downloads (.crdownload, .part, ...), hidden files and Office lock files are
    skipped, and a file must be unchanged for JARVIS_AUTONOMY_ORGANISE_SETTLE_S (20 s) so a download in
    progress is never moved.
  * Every action goes to autonomy_decisions (category file:organise) and action_audit. In dry-run nothing on disk
    changes; the plan is logged and the file is organised after dry-run ends. The hard kill stops it.
  * Files no rule matches (or that could not be filed) still get a 'Review new file ...' notification from the
    core's file bridge, so nothing is silently ignored.

Self-contained like the other jarvis_*.py modules (own table, IF NOT EXISTS; uses the core module's DB helpers
and callbacks; never imports jarvis.py). Called through the `organise` callback from jarvis_autonomy._file_scan.
"""

from __future__ import annotations

import errno
import json
import logging
import os
import re
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

import jarvis_autonomy as core

log = logging.getLogger("jarvis.autonomy_organise")

SETTLE_S_DEFAULT = 20
MAX_RETRIES = 10
TEMP_EXTS = frozenset({".crdownload", ".part", ".tmp", ".download", ".partial", ".opdownload", ".temp"})
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
EXT_RE = re.compile(r"^\.[a-z0-9]{1,10}$")
DEFAULT_ROOT_NAMES = ("Downloads", "Desktop", "OneDrive/Desktop", "OneDrive/Downloads")
DEFAULT_RULES = (
    ("default_documents", (".pdf", ".doc", ".docx", ".pptx", ".rtf", ".odt", ".epub"), "~/Documents/Jarvis_Organised/Documents"),
    ("default_spreadsheets", (".xls", ".xlsx", ".csv", ".ods"), "~/Documents/Jarvis_Organised/Spreadsheets"),
    ("default_images", (".png", ".jpg", ".jpeg", ".webp", ".gif"), "~/Pictures/Jarvis_Organised"),
)

_DDL = ("CREATE TABLE IF NOT EXISTS autonomy_organise_rules ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, extensions TEXT NOT NULL, "
        "dest_dir TEXT NOT NULL, action TEXT NOT NULL DEFAULT 'move', is_enabled INTEGER NOT NULL DEFAULT 1, "
        "source TEXT NOT NULL DEFAULT 'default', created_at TEXT NOT NULL)")
_ready: set[str] = set()
_retries: dict[str, int] = {}


# ---------------------------------------------------------------------------------------- paths
def home() -> Path:
    """The user profile (JARVIS_AUTONOMY_HOME overrides it, which is what the tests use)."""
    return Path(os.environ.get("JARVIS_AUTONOMY_HOME") or Path.home())


def _norm(p: str | Path) -> str:
    return os.path.normcase(os.path.realpath(str(p)))


def _inside(path: str | Path, root: str | Path) -> bool:
    a, b = _norm(path), _norm(root)
    try:
        return os.path.commonpath([a, b]) == b
    except ValueError:  # different drives
        return False


def _json_setting(key: str) -> list:
    try:
        v = json.loads(core.get_setting(key, "[]") or "[]")
        return v if isinstance(v, list) else []
    except json.JSONDecodeError:
        return []


def roots() -> list[str]:
    """Allowlisted folders that exist right now: the built-in defaults + extras (env / added), minus removed ones."""
    cands = [str(home() / rel) for rel in DEFAULT_ROOT_NAMES]
    cands += [p for p in (os.environ.get("JARVIS_AUTONOMY_ORGANISE_ROOTS") or "").split(os.pathsep) if p.strip()]
    cands += [str(p) for p in _json_setting("organise_extra_roots")]
    removed = {_norm(p) for p in _json_setting("organise_removed_roots")}
    out: list[str] = []
    for c in cands:
        if os.path.isdir(c) and _norm(c) not in removed and _norm(c) not in {_norm(o) for o in out}:
            out.append(os.path.realpath(c))
    return out


def add_root(path: str) -> str:
    p = os.path.realpath(os.path.expanduser(str(path or "").strip()))
    if not os.path.isdir(p):
        return f"{path!r} is not a folder that exists."
    if not _inside(p, home()) or _norm(p) == _norm(home()):
        return "Organised folders must be inside your user profile (and not the whole profile)."
    extra = _json_setting("organise_extra_roots")
    if _norm(p) not in {_norm(e) for e in extra}:
        core.set_setting("organise_extra_roots", json.dumps(extra + [p]))
    removed = [r for r in _json_setting("organise_removed_roots") if _norm(r) != _norm(p)]
    core.set_setting("organise_removed_roots", json.dumps(removed))
    core._call("watch_path", p)  # make sure the file watcher reports new files there
    return f"Now organising new files in {p}."


def remove_root(path: str) -> str:
    p = os.path.realpath(os.path.expanduser(str(path or "").strip()))
    core.set_setting("organise_extra_roots", json.dumps([e for e in _json_setting("organise_extra_roots") if _norm(e) != _norm(p)]))
    removed = _json_setting("organise_removed_roots")
    if _norm(p) not in {_norm(r) for r in removed}:
        core.set_setting("organise_removed_roots", json.dumps(removed + [p]))
    return f"No longer organising new files in {p}."


def start() -> list[str]:
    """Called once at startup: make sure the file watcher covers every organised folder (Desktop is not
    watched by default; adding it is baselined, so existing files are not treated as new)."""
    rs = roots()
    for r in rs:
        core._call("watch_path", r)
    return rs


# ---------------------------------------------------------------------------------------- rules
def _init() -> None:
    key = str(core._db_path())
    if key in _ready:
        return
    with core._db_lock:
        conn = core._raw_connect()
        try:
            conn.execute(_DDL)
            conn.commit()
        finally:
            conn.close()
    _ready.add(key)
    _seed()


def _q(sql: str, params: tuple = ()) -> list[dict]:
    _init()
    return core._rows(sql, params)


def _x(sql: str, params: tuple = ()) -> int:
    _init()
    return core._exec_rc(sql, params)


def _seed() -> None:
    """Built-in rules, inserted once and never resurrected after the user removes one."""
    removed = set(_json_setting("organise_removed_defaults"))
    now = core._iso()
    for name, exts, dest in DEFAULT_RULES:
        if name in removed:
            continue
        core._exec_rc("INSERT OR IGNORE INTO autonomy_organise_rules (name, extensions, dest_dir, action, source, "
                      "created_at) VALUES (?, ?, ?, 'move', 'default', ?)", (name, json.dumps(list(exts)), dest, now))


def list_rules() -> list[dict]:
    rows = _q("SELECT id, name, extensions, dest_dir, action, is_enabled, source, created_at FROM autonomy_organise_rules "
              "ORDER BY (source='user') DESC, id DESC")
    for r in rows:
        try:
            r["extensions"] = json.loads(r["extensions"])
        except json.JSONDecodeError:
            r["extensions"] = []
    return rows


def resolve_dest(dest: str) -> tuple[str | None, str | None]:
    """(absolute folder, None) or (None, reason). The folder must resolve inside the user profile."""
    raw = str(dest or "").strip()
    if not raw:
        return None, "no destination folder"
    p = home() / raw[2:] if raw.startswith(("~/", "~\\")) else Path(raw).expanduser()
    if not p.is_absolute():
        return None, "destination must be an absolute path (or start with ~/)"
    real = os.path.realpath(str(p))
    if not _inside(real, home()) or _norm(real) == _norm(home()):
        return None, "destination must be a folder inside your user profile"
    for r in roots():
        if _norm(real) == _norm(r):
            return None, "destination cannot be one of the organised folders itself"
    return real, None


def add_rule(name: str, extensions: object, dest_dir: str, action: str = "move") -> str:
    """Adds (or replaces, by name) a rule of your own. It beats the built-in ones for the same extension."""
    name = str(name or "").strip().lower()
    if not NAME_RE.match(name):
        return "Rule name must be lowercase letters, digits and underscores, 2-40 chars, starting with a letter."
    exts = [e.strip().lower() for e in (extensions.split(",") if isinstance(extensions, str) else (extensions or []))]
    exts = [e if e.startswith(".") else "." + e for e in exts if e]
    if not exts or any(not EXT_RE.match(e) or e in TEMP_EXTS for e in exts):
        return "Give one or more plain file extensions such as .pdf, .png (not temporary download types)."
    action = str(action or "move").lower()
    if action not in ("move", "copy"):
        return "Action must be move or copy (organising never deletes)."
    real, err = resolve_dest(dest_dir)
    if err:
        return f"Rule not saved: {err}."
    stored = str(dest_dir).strip()
    _x("INSERT INTO autonomy_organise_rules (name, extensions, dest_dir, action, source, created_at) VALUES (?,?,?,?, 'user', ?) "
       "ON CONFLICT(name) DO UPDATE SET extensions=excluded.extensions, dest_dir=excluded.dest_dir, action=excluded.action, "
       "source='user', is_enabled=1", (name, json.dumps(exts), stored, action, core._iso()))
    core._publish()
    return f"Rule {name!r} saved: {', '.join(exts)} -> {real} ({action})."


def remove_rule(name: str) -> str:
    name = str(name or "").strip().lower()
    n = _x("DELETE FROM autonomy_organise_rules WHERE name=? OR id=?", (name, int(name) if name.isdigit() else -1))
    if name in {d[0] for d in DEFAULT_RULES}:
        removed = _json_setting("organise_removed_defaults")
        if name not in removed:
            core.set_setting("organise_removed_defaults", json.dumps(removed + [name]))
    core._publish()
    return f"Rule {name!r} removed." if n or name in {d[0] for d in DEFAULT_RULES} else f"No rule named {name!r}."


def _match_rule(ext: str) -> dict | None:
    for r in list_rules():
        if r["is_enabled"] and ext in r["extensions"]:
            return r
    return None


# ---------------------------------------------------------------------------------------- filing
def _made_by_jarvis(name: str) -> bool:
    """A file Jarvis itself wrote or downloaded into a watched folder in the last 15 minutes ("save this to my
    Desktop") is where the user asked for it: do not whisk it away."""
    cut = (datetime.now() - timedelta(minutes=15)).isoformat(timespec="seconds")
    try:
        return bool(core._rows("SELECT 1 FROM action_audit WHERE tool_name IN ('write_file','download_image') "
                               "AND timestamp>=? AND instr(tool_input, ?)>0 LIMIT 1", (cut, name)))
    except Exception:
        return False


def _unique(dest_dir: str, name: str) -> str:
    cand = os.path.join(dest_dir, name)
    if not os.path.lexists(cand):
        return cand
    stem, ext = os.path.splitext(name)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    cand = os.path.join(dest_dir, f"{stem}_{stamp}{ext}")
    n = 1
    while os.path.lexists(cand) and n < 1000:
        cand = os.path.join(dest_dir, f"{stem}_{stamp}_{n}{ext}")
        n += 1
    return cand


def _copy_no_clobber(src: str, dst: str) -> None:
    with open(src, "rb") as fi, open(dst, "xb") as fo:  # 'x' fails if dst appeared meanwhile: never overwrite
        shutil.copyfileobj(fi, fo)
    shutil.copystat(src, dst)


def _record(rule: dict | None, src: str, dst: str, outcome: str, result: str, action: str = "move") -> None:
    name = os.path.basename(src)
    core._log_decision(f"organise {name}", {"rule": (rule or {}).get("name")}, "act" if outcome != "skipped" else "silent",
                       f"{action} {src} -> {dst}" if dst else result,
                       f"organise rule '{(rule or {}).get('name', 'none')}' ({(rule or {}).get('source', 'n/a')})",
                       category="file:organise", quote=src,
                       payload={"source": src, "dest": dst, "action": action, "rule": (rule or {}).get("name")},
                       result=result, outcome=outcome)
    core._audit("organise", {"src": src, "dst": dst, "action": action, "outcome": outcome}, result[:200])


def handle_new_file(path: str) -> dict:
    """The `organise` callback. Returns {"status": moved|copied|dry_run|unsettled|no_rule|outside|rejected|skipped|
    missing|failed|off, ...}. Only moved/copied/dry_run/unsettled stop the core from also making a review item."""
    if core.hard_disabled() or not core.enabled():
        return {"status": "off"}
    _init()
    raw = str(path or "")
    real = os.path.realpath(raw)
    rs = roots()
    root = next((r for r in rs if _inside(real, r)), None)
    if root is None:
        # Looked like it was inside an organised folder but resolves elsewhere (.. traversal, symlink, junction):
        # that is worth a log line. A file in some other watched folder is simply not ours: stay quiet.
        if any(os.path.normcase(raw).startswith(os.path.normcase(r)) for r in rs):
            _record(None, raw, "", "skipped", "rejected: the path resolves outside the organised folders")
            return {"status": "rejected"}
        return {"status": "outside"}
    if os.path.islink(raw) or not os.path.isfile(real):
        return {"status": "missing"}
    if _norm(os.path.dirname(real)) != _norm(root):
        return {"status": "skipped", "reason": "not directly inside the organised folder"}
    name = os.path.basename(real)
    ext = os.path.splitext(name)[1].lower()
    if name.startswith((".", "~$")) or ext in TEMP_EXTS:
        return {"status": "skipped", "reason": "temporary or hidden file"}
    rule = _match_rule(ext)
    if rule is None:
        return {"status": "no_rule"}
    if _made_by_jarvis(name):
        return {"status": "skipped", "reason": "Jarvis just saved this file on request"}
    dest, err = resolve_dest(rule["dest_dir"])
    if err:
        _record(rule, real, "", "failed", f"rule destination rejected: {err}")
        return {"status": "failed", "reason": err}
    if any(_inside(real, d) for d in (resolve_dest(x["dest_dir"])[0] for x in list_rules()) if d):
        return {"status": "skipped", "reason": "already organised"}
    settle = core._env_int("JARVIS_AUTONOMY_ORGANISE_SETTLE_S", SETTLE_S_DEFAULT)
    try:
        if time.time() - os.path.getmtime(real) < settle:
            return {"status": "unsettled"}
    except OSError:
        return {"status": "missing"}
    action = rule["action"]
    if core.dry_run():
        dst = _unique(dest, name)
        _record(rule, real, dst, "dry_run", f"(dry run) would {action} to {dst}", action)
        return {"status": "dry_run", "dest": dst}
    try:
        os.makedirs(dest, exist_ok=True)
        dst = _unique(dest, name)
        note = ""
        if action == "copy":
            _copy_no_clobber(real, dst)
            status = "copied"
        else:
            try:
                if os.path.lexists(dst):  # never overwrite (os.rename would on POSIX)
                    raise FileExistsError(dst)
                os.rename(real, dst)
                status = "moved"
            except FileExistsError:
                dst = _unique(dest, name)
                os.rename(real, dst)
                status = "moved"
            except OSError as e:
                if isinstance(e, PermissionError):
                    raise
                if e.errno == errno.EXDEV or getattr(e, "winerror", None) == 17:  # another drive
                    _copy_no_clobber(real, dst)
                    status, note = "copied", " (other drive: copied, original left in place)"
                else:
                    raise
        _retries.pop(real, None)
        _record(rule, real, dst, "ok", f"{status} to {dst}{note}", action)
        return {"status": status, "dest": dst}
    except PermissionError:
        _retries[real] = _retries.get(real, 0) + 1
        if _retries[real] < MAX_RETRIES:  # in use by another program: try again on a later tick
            return {"status": "unsettled"}
        _record(rule, real, "", "failed", "the file stayed locked by another program", action)
        core._notify_throttled("organise-fail", f"I couldn't file {name}: it stayed in use by another program.")
        return {"status": "failed", "reason": "locked"}
    except Exception as e:
        _record(rule, real, "", "failed", f"{type(e).__name__}: {e}"[:300], action)
        core._notify_throttled("organise-fail", f"I couldn't file {name}: {e}"[:160])
        return {"status": "failed", "reason": str(e)}


# ------------------------------------------------------------------------------ views / tool API
def recent(limit: int = 20) -> list[dict]:
    return core.log_entries(24 * 30, category="file:organise", limit=limit)


def overview() -> dict:
    return {"roots": roots(), "rules": list_rules(), "recent": recent(15)}


def handle_tool(inp: dict, source: str | None = None) -> str:
    action = str(inp.get("action") or "list_rules").lower()
    if action == "add_rule":
        return add_rule(str(inp.get("name") or ""), inp.get("extensions"), str(inp.get("dest_dir") or ""),
                        str(inp.get("rule_action") or "move"))
    if action == "remove_rule":
        return remove_rule(str(inp.get("name") or ""))
    if action == "add_root":
        return add_root(str(inp.get("path") or ""))
    if action == "remove_root":
        return remove_root(str(inp.get("path") or ""))
    if action == "list_roots":
        return "\n".join(roots()) or "No organised folders exist on this machine."
    if action == "recent":
        rows = recent(15)
        return "\n".join(f"{r['created_at'][:16].replace('T', ' ')} {r['action_taken'][:300]} [{r['outcome']}]" for r in rows) \
            or "Nothing organised yet."
    return "\n".join(f"{r['name']} ({r['source']}{'' if r['is_enabled'] else ', off'}): {', '.join(r['extensions'])} -> "
                     f"{r['dest_dir']} ({r['action']})" for r in list_rules()) or "No rules."
