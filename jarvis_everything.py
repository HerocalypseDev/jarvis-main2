"""Instant file search through voidtools Everything (2026-09-27, feature batch A2).

Everything keeps its own NTFS index, so a name search over the whole disk answers in milliseconds
and Jarvis never walks the disk itself. Two ways in, tried in order:
  1. Everything's HTTP server (Tools > Options > HTTP Server > enable, bind to 127.0.0.1).
     JARVIS_EVERYTHING_URL (default: try http://127.0.0.1:80 then :8080). Loopback only: the query
     would otherwise leave the machine.
  2. es.exe, Everything's command-line client (IPC, needs Everything running), on PATH or at
     JARVIS_EVERYTHING_ES.
Neither available = a clear "install Everything" message; there is deliberately no disk-walk fallback.
"""

from __future__ import annotations

import ipaddress
import json
import os
import shlex
import shutil
import subprocess
import time
import urllib.parse
import urllib.request

TIMEOUT_S = 2.0
MAX_RESULTS = 25
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_working_url: dict = {"url": None, "checked": 0.0}
SETUP_HINT = ("Everything isn't reachable. Install voidtools Everything, then either enable its HTTP "
              "server (Tools > Options > HTTP Server, bind to 127.0.0.1) or put es.exe on the PATH. Until "
              "then, to find a file use run_shell, which is PowerShell (not cmd.exe, so no `dir /s /b`): "
              "Get-ChildItem -Path $env:USERPROFILE -Recurse -Filter '*name*' -ErrorAction SilentlyContinue "
              "| Select-Object -First 20 -ExpandProperty FullName. Search the user's folders (Desktop, "
              "Documents, Downloads, OneDrive), never a whole drive like C:\\.")


def _candidate_urls() -> list[str]:
    env = (os.environ.get("JARVIS_EVERYTHING_URL") or "").strip().rstrip("/")
    return [env] if env else ["http://127.0.0.1:80", "http://127.0.0.1:8080"]


def _is_loopback(url: str) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def build_query(query: str, ext: str = "", path_prefix: str = "") -> str:
    q = (query or "").strip()
    if ext:
        exts = ";".join(e.strip().lstrip(".") for e in str(ext).replace(",", ";").split(";") if e.strip())
        q += f" ext:{exts}"
    if path_prefix:
        q = f'"{path_prefix.rstrip(chr(92))}\\" ' + q
    return q.strip()


def _http(url: str, q: str, count: int) -> list[dict]:
    params = urllib.parse.urlencode({"search": q, "json": 1, "path_column": 1, "size_column": 1,
                                     "date_modified_column": 1, "count": count, "sort": "date_modified",
                                     "ascending": 0})
    with urllib.request.urlopen(f"{url}/?{params}", timeout=TIMEOUT_S) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    out = []
    for it in data.get("results") or []:
        out.append({"path": os.path.join(it.get("path") or "", it.get("name") or ""),
                    "type": it.get("type") or "file", "size": it.get("size")})
    return out


def _es(q: str, count: int) -> list[dict] | None:
    exe = (os.environ.get("JARVIS_EVERYTHING_ES") or "").strip() or shutil.which("es") or shutil.which("es.exe")
    if not exe:
        return None
    p = subprocess.run([exe, "-n", str(count), "-sort", "date-modified-descending", *shlex.split(q, posix=True)],
                       capture_output=True, text=True, timeout=TIMEOUT_S + 3, creationflags=_NO_WINDOW,
                       errors="replace")
    if p.returncode != 0:
        return None
    return [{"path": line.strip(), "type": "file"} for line in p.stdout.splitlines() if line.strip()]


def search(query: str, ext: str = "", path_prefix: str = "", count: int = MAX_RESULTS) -> dict:
    """{"ok", "backend", "results": [{path, type, size?}], "ms", "error"?}."""
    q = build_query(query, ext, path_prefix)
    if not q:
        return {"ok": False, "error": "Say what to search for.", "results": []}
    count = max(1, min(int(count or MAX_RESULTS), 100))
    t0 = time.perf_counter()
    urls = _candidate_urls()
    if _working_url["url"] in urls:
        urls.remove(_working_url["url"])
        urls.insert(0, _working_url["url"])
    for url in urls:
        if not _is_loopback(url):
            continue
        try:
            res = _http(url, q, count)
            _working_url["url"] = url
            return {"ok": True, "backend": "http", "results": res, "ms": round((time.perf_counter() - t0) * 1000)}
        except Exception:
            continue
    try:
        res = _es(q, count)
    except Exception:
        res = None
    if res is not None:
        return {"ok": True, "backend": "es", "results": res, "ms": round((time.perf_counter() - t0) * 1000)}
    return {"ok": False, "error": SETUP_HINT, "results": []}


def format_results(r: dict, limit: int = 15) -> str:
    if not r.get("ok"):
        return r.get("error") or SETUP_HINT
    rows = r["results"]
    if not rows:
        return "No files match that."
    lines = [f"- {x['path']}" + (" (folder)" if x.get("type") == "folder" else "") for x in rows[:limit]]
    more = f"\n...and {len(rows) - limit} more." if len(rows) > limit else ""
    return f"{len(rows)} match(es), newest first:\n" + "\n".join(lines) + more
