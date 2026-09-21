"""Local supervision dashboard for Jarvis: a read-mostly FastAPI + WebSocket UI over the
existing jarvis_memory.db tables, plus a small self-owned `dashboard_sessions` table (there is
no existing concept of a "session" spanning one voice/text/phone command, so this module adds
the minimum one).

Self-contained like the other jarvis_*.py modules: owns its own sqlite table, no import-time
dependency back on jarvis.py. jarvis.py calls the plain functions here (start_session,
end_session, notify) unconditionally and defensively — every one of them swallows its own
exceptions, because a dashboard bookkeeping failure must never break a real voice/text/phone
command. The actual web server (start()) is heavier (FastAPI/uvicorn) and is only imported
lazily inside start(), so importing this module at all — which jarvis.py now always does, to
get the lightweight bookkeeping functions — never requires those packages to be installed.

Double-checked (Phase 0, see CLAUDE.md's "Dashboard" section): binds 127.0.0.1 only, no auth
(user-accepted — single-user local machine). Approve/reject/kill/run-command endpoints for the
higher-risk features are added in later phases, not this module's Phase 1 (sessions, tasks,
victory log, read-only pending-action display).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

log = logging.getLogger("jarvis.dashboard")

DEFAULT_PORT = 8765
STATIC_DIR = Path(__file__).resolve().parent / "dashboard_static"

_db_lock = threading.Lock()


def _db_path() -> Path:
    override = (os.environ.get("JARVIS_MEMORY_DB_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent / "jarvis_memory.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=10)
    # WAL mode + a longer busy timeout: observed live, jarvis.py's many independent sqlite
    # connections to this same file can collide under the default rollback-journal mode
    # during a startup burst. journal_mode is persisted in the file itself, so this is only
    # ever real work the first time any connection sets it.
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
    except sqlite3.DatabaseError as e:
        log.debug("Could not set WAL/busy_timeout pragmas: %s", e)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS dashboard_sessions ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "source TEXT NOT NULL, "
        "transcript TEXT NOT NULL, "
        "status TEXT NOT NULL DEFAULT 'active', "
        "reply TEXT, "
        "started_at TEXT NOT NULL, "
        "ended_at TEXT)"
    )
    return conn


# --- session bookkeeping -----------------------------------------------------------------
# Called from jarvis.py's handle_text_command for every voice/text/phone/dashboard command.
# Never raises.
MAX_SESSION_ROWS = 300  # every command writes a row here — prune so the table never grows unbounded


def start_session(source: str, transcript: str) -> int | None:
    try:
        now_iso = datetime.now().isoformat(timespec="seconds")
        with _db_lock:
            conn = _connect()
            try:
                cur = conn.execute(
                    "INSERT INTO dashboard_sessions (source, transcript, status, started_at) "
                    "VALUES (?, ?, 'active', ?)",
                    (source, transcript, now_iso),
                )
                new_id = int(cur.lastrowid)
                # Cheap enough to run on every write (an indexed rowid range delete); keeps the
                # table from piling up forever while every command a user gives still gets a row.
                conn.execute(
                    "DELETE FROM dashboard_sessions WHERE id NOT IN "
                    "(SELECT id FROM dashboard_sessions ORDER BY id DESC LIMIT ?)",
                    (MAX_SESSION_ROWS,),
                )
                conn.commit()
                return new_id
            finally:
                conn.close()
    except Exception as e:
        log.debug("start_session failed (non-fatal): %s", e)
        return None


def clear_finished_sessions() -> int:
    """Deletes every session that isn't currently 'active' — the dashboard's "Clear finished"
    button. Returns how many rows were removed."""
    try:
        with _db_lock:
            conn = _connect()
            try:
                cur = conn.execute("DELETE FROM dashboard_sessions WHERE status != 'active'")
                conn.commit()
                return cur.rowcount
            finally:
                conn.close()
    except Exception as e:
        log.debug("clear_finished_sessions failed (non-fatal): %s", e)
        return 0


def end_session(session_id: int | None, status: str, reply: str | None) -> None:
    if session_id is None:
        return
    try:
        now_iso = datetime.now().isoformat(timespec="seconds")
        with _db_lock:
            conn = _connect()
            try:
                conn.execute(
                    "UPDATE dashboard_sessions SET status = ?, reply = ?, ended_at = ? "
                    "WHERE id = ?",
                    (status, reply, now_iso, session_id),
                )
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        log.debug("end_session failed (non-fatal): %s", e)


# --- best-effort live push ----------------------------------------------------------------
# notify() is safe to call whether or not the web server is running: _broadcast_fn is only
# set once start()'s FastAPI app finishes its startup handler.
_broadcast_fn: Callable[[dict], None] | None = None


def notify(event: dict) -> None:
    fn = _broadcast_fn
    if fn:
        try:
            fn(event)
        except Exception as e:
            log.debug("notify failed (non-fatal): %s", e)


class _ConnectionManager:
    def __init__(self) -> None:
        self._clients: dict = {}  # websocket -> asyncio.Lock (serializes sends per-connection)
        self._lock = threading.Lock()

    def add(self, ws) -> None:
        with self._lock:
            self._clients[ws] = asyncio.Lock()

    def remove(self, ws) -> None:
        with self._lock:
            self._clients.pop(ws, None)

    def snapshot(self) -> list:
        with self._lock:
            return list(self._clients.items())


def _set_broadcast(loop: "asyncio.AbstractEventLoop", manager: "_ConnectionManager") -> None:
    global _broadcast_fn

    def _broadcast(event: dict) -> None:
        asyncio.run_coroutine_threadsafe(_do_broadcast(manager, event), loop)

    _broadcast_fn = _broadcast


async def _do_broadcast(manager: "_ConnectionManager", event: dict) -> None:
    payload = json.dumps(event, default=str)
    for ws, lock in manager.snapshot():
        try:
            async with lock:
                await ws.send_text(payload)
        except Exception:
            manager.remove(ws)


# --- read models ---------------------------------------------------------------------------
def _fetch_sessions(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    rows = conn.execute(
        "SELECT id, source, transcript, status, reply, started_at, ended_at "
        "FROM dashboard_sessions ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "id": r[0], "source": r[1], "transcript": r[2], "status": r[3],
            "reply": r[4], "started_at": r[5], "ended_at": r[6],
        }
        for r in rows
    ]


def _fetch_tasks(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    items: list[dict] = []
    try:
        for row in conn.execute(
            "SELECT id, kind, task, status, started_at, finished_at, result_summary "
            "FROM background_tasks ORDER BY id DESC LIMIT ?",
            (limit,),
        ):
            tid, kind, task, status, started_at, finished_at, result_summary = row
            progress = None
            if kind == "plan" and status == "running":
                try:
                    total = conn.execute(
                        "SELECT COUNT(*) FROM plan_steps WHERE task_id = ?", (tid,)
                    ).fetchone()[0]
                    done = conn.execute(
                        "SELECT COUNT(*) FROM plan_steps WHERE task_id = ? AND status = 'done'",
                        (tid,),
                    ).fetchone()[0]
                    if total:
                        progress = f"{done}/{total}"
                except sqlite3.OperationalError:
                    pass
            items.append({
                "id": f"bg-{tid}", "kind": kind, "description": task, "status": status,
                "started_at": started_at, "finished_at": finished_at,
                "result_summary": result_summary, "source": "background_tasks",
                "progress": progress, "stoppable": status == "running",
            })
    except sqlite3.OperationalError:
        pass
    try:
        for row in conn.execute(
            "SELECT id, description, status, scheduled_start, scheduled_end, priority "
            "FROM task_queue ORDER BY id DESC LIMIT ?",
            (limit,),
        ):
            items.append({
                "id": f"tq-{row[0]}", "kind": f"queued ({row[5]})", "description": row[1],
                "status": row[2], "started_at": row[3], "finished_at": row[4],
                "result_summary": None, "source": "task_queue",
                "progress": None, "stoppable": False,
            })
    except sqlite3.OperationalError:
        pass
    try:
        for row in conn.execute(
            "SELECT id, text, due_at, delivered_at, cancelled_at FROM reminders "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ):
            status = "cancelled" if row[4] else ("done" if row[3] else "pending")
            items.append({
                "id": f"rem-{row[0]}", "kind": "reminder", "description": row[1],
                "status": status, "started_at": row[2], "finished_at": row[3] or row[4],
                "result_summary": None, "source": "reminders",
                "progress": None, "stoppable": False,
            })
    except sqlite3.OperationalError:
        pass
    items.sort(key=lambda t: t.get("started_at") or "", reverse=True)
    return items[:limit]


def _fetch_audit(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    try:
        rows = conn.execute(
            "SELECT id, timestamp, tool_name, tool_input, result FROM action_audit "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    out = []
    for r in rows:
        tool_input = r[3] or ""
        result = r[4] or ""
        out.append({
            "id": r[0], "timestamp": r[1], "tool_name": r[2],
            "tool_input": tool_input, "result": result,
            "result_preview": result[:200],
        })
    return out


def _fetch_tool_names(conn: sqlite3.Connection) -> list[str]:
    try:
        rows = conn.execute(
            "SELECT DISTINCT tool_name FROM action_audit ORDER BY tool_name"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [r[0] for r in rows if r[0]]


def _fetch_audit_filtered(
    conn: sqlite3.Connection,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    tool_name: str | None = None,
    transcript: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """The dedicated Audit Trail tab's query — full filtering on top of action_audit, the same
    table Phase 1's compact Activity stream already reads, just with real WHERE clauses instead
    of a flat "last N". `transcript` (exact match) is how a session row links to "its" audit
    rows: handle_text_command passes the identical transcript string into both
    dashboard.start_session and (via run_agent_loop/_execute_tool) every _log_action_audit call
    for that turn, so there's no need for a new session_id column to join them."""
    clauses: list[str] = []
    params: list = []
    if date_from:
        clauses.append("timestamp >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("timestamp <= ?")
        params.append(date_to)
    if tool_name:
        clauses.append("tool_name = ?")
        params.append(tool_name)
    if transcript:
        clauses.append("transcript = ?")
        params.append(transcript)
    if q:
        clauses.append("(tool_input LIKE ? OR result LIKE ? OR transcript LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    try:
        rows = conn.execute(
            f"SELECT id, timestamp, transcript, tool_name, tool_input, result FROM action_audit "
            f"{where} ORDER BY id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    out = []
    for r in rows:
        result = r[5] or ""
        out.append({
            "id": r[0], "timestamp": r[1], "transcript": r[2], "tool_name": r[3],
            "tool_input": r[4] or "", "result": result, "result_preview": result[:200],
        })
    return out


def _fetch_victory(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    out: list[dict] = []
    try:
        for row in conn.execute(
            "SELECT id, task, finished_at, result_summary FROM background_tasks "
            "WHERE status = 'done' ORDER BY id DESC LIMIT ?",
            (limit,),
        ):
            summary = f" — {row[3][:140]}" if row[3] else ""
            out.append({
                "id": f"bg-{row[0]}", "timestamp": row[2],
                "text": f"✅ {row[1]}{summary}",
            })
    except sqlite3.OperationalError:
        pass
    out.sort(key=lambda v: v.get("timestamp") or "", reverse=True)
    return out[:limit]


def _fetch_counts(conn: sqlite3.Connection) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    week_start = (datetime.now() - timedelta(days=7)).isoformat(timespec="seconds")
    counts = {"tasks_done_today": 0, "tasks_done_week": 0, "tasks_failed_today": 0}
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM background_tasks WHERE status='done' AND finished_at >= ?",
            (today,),
        ).fetchone()
        counts["tasks_done_today"] = int(row[0]) if row else 0
        row = conn.execute(
            "SELECT COUNT(*) FROM background_tasks WHERE status='done' AND finished_at >= ?",
            (week_start,),
        ).fetchone()
        counts["tasks_done_week"] = int(row[0]) if row else 0
        row = conn.execute(
            "SELECT COUNT(*) FROM background_tasks WHERE status='failed' AND finished_at >= ?",
            (today,),
        ).fetchone()
        counts["tasks_failed_today"] = int(row[0]) if row else 0
    except sqlite3.OperationalError:
        pass
    return counts


def _build_state(
    get_pending: Callable[[], dict | None] | None,
    get_system_status: Callable[[], dict] | None,
) -> dict:
    pending = None
    if get_pending:
        try:
            pending = get_pending()
        except Exception as e:
            log.debug("get_pending failed: %s", e)

    sessions: list[dict] = []
    tasks: list[dict] = []
    audit: list[dict] = []
    victory: list[dict] = []
    tool_names: list[str] = []
    counts = {"tasks_done_today": 0, "tasks_done_week": 0, "tasks_failed_today": 0}
    try:
        with _db_lock:
            conn = _connect()
            try:
                sessions = _fetch_sessions(conn)
                tasks = _fetch_tasks(conn)
                audit = _fetch_audit(conn)
                victory = _fetch_victory(conn)
                counts = _fetch_counts(conn)
                tool_names = _fetch_tool_names(conn)
            finally:
                conn.close()
    except Exception as e:
        log.warning("Dashboard state query failed: %s", e)

    metrics = None
    if get_system_status:
        try:
            metrics = get_system_status()
        except Exception as e:
            log.debug("get_system_status failed: %s", e)

    return {
        "pending_action": pending,
        "sessions": sessions,
        "tasks": tasks,
        "audit": audit,
        "victory_log": victory,
        "counts": counts,
        "metrics": metrics,
        "tool_names": tool_names,
    }


_LOOPBACK_NAMES = ("127.0.0.1", "localhost", "::1")


def _origin_is_loopback(origin: str) -> bool:
    """True if an Origin header names this machine. "null" (sandboxed iframes, file://) and any
    other site are not loopback."""
    from urllib.parse import urlsplit

    try:
        host = (urlsplit(origin or "").hostname or "").lower()
    except ValueError:
        return False
    return host in _LOOPBACK_NAMES


def _host_is_loopback(host_header: str) -> bool:
    from urllib.parse import urlsplit

    try:
        return (urlsplit("//" + (host_header or "")).hostname or "").lower() in _LOOPBACK_NAMES
    except ValueError:
        return False


# --- web server (heavy imports live here, not at module load) ------------------------------
def _build_app(
    *,
    get_pending: Callable[[], dict | None] | None = None,
    get_system_status: Callable[[], dict] | None = None,
    approve_pending: Callable[[], str | None] | None = None,
    reject_pending: Callable[[], bool] | None = None,
    kill_background_task: Callable[[int], str] | None = None,
    run_command: Callable[[str, Callable[[str], None]], None] | None = None,
    get_services: Callable[[], list[dict]] | None = None,
    get_daily: Callable[[], list[dict]] | None = None,
    get_usage: Callable[[], dict] | None = None,
    get_sleep: Callable[[], dict] | None = None,
    get_llm: Callable[[], dict] | None = None,
    set_llm: Callable[[str], str] | None = None,
    face=None,
    autonomy=None,
    autonomy_skills=None,
    autonomy_organise=None,
    dyn_tools=None,
    port: int = DEFAULT_PORT,
):
    """Builds the FastAPI app (import-guarded, testable without binding a socket). Returns
    None if fastapi/uvicorn aren't installed."""
    try:
        from fastapi import Body, FastAPI, Request, WebSocket, WebSocketDisconnect
        from fastapi.responses import JSONResponse, Response
        from fastapi.staticfiles import StaticFiles
    except ImportError as e:
        log.warning(
            "Dashboard disabled: %s. Install with `pip install fastapi uvicorn[standard]`, "
            "or set JARVIS_DASHBOARD_ENABLED=0 to silence this.", e,
        )
        return None

    # This module has `from __future__ import annotations`, so every annotation below (e.g.
    # `websocket: WebSocket` on ws_endpoint) is a lazy string. FastAPI resolves those strings
    # via the endpoint function's __globals__ — which is this *module's* global dict, not
    # _build_app's local scope — to tell a WebSocket-typed parameter apart from a query/body
    # one. Since the import above is deliberately local (so importing jarvis_dashboard never
    # requires fastapi to be installed), these names must be promoted into the module globals
    # or that resolution fails silently and the websocket route just refuses every connection.
    globals().update(
        Body=Body, FastAPI=FastAPI, Request=Request, WebSocket=WebSocket,
        WebSocketDisconnect=WebSocketDisconnect, JSONResponse=JSONResponse, Response=Response,
        StaticFiles=StaticFiles,
    )

    manager = _ConnectionManager()

    @asynccontextmanager
    async def _lifespan(_app):
        _set_broadcast(asyncio.get_running_loop(), manager)
        log.info("Dashboard: ready on http://127.0.0.1:%d", port)
        yield

    app = FastAPI(title="Jarvis Dashboard", docs_url=None, redoc_url=None, lifespan=_lifespan)

    # Every /api/* route (not just Identity/Autonomy) refuses a non-loopback Host header (DNS
    # rebinding: an attacker's domain re-pointed at 127.0.0.1 sends its own Host) and a state-changing
    # call whose Origin is not this machine (cross-site form/fetch). /api/command and
    # /api/pending/approve reach run_shell and the catastrophic-action approval, so they matter most.
    @app.middleware("http")
    async def _loopback_only(request, call_next):
        if request.url.path.startswith("/api/"):
            if not _host_is_loopback(request.headers.get("host") or ""):
                return JSONResponse({"error": "forbidden host"}, status_code=403)
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                origin = request.headers.get("origin")
                if origin and not _origin_is_loopback(origin):
                    return JSONResponse({"error": "forbidden origin"}, status_code=403)
        return await call_next(request)

    @app.get("/api/state")
    def api_state() -> dict:
        return _build_state(get_pending, get_system_status)

    @app.get("/api/audit")
    def api_audit(
        date_from: str | None = None,
        date_to: str | None = None,
        tool_name: str | None = None,
        transcript: str | None = None,
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        try:
            with _db_lock:
                conn = _connect()
                try:
                    rows = _fetch_audit_filtered(
                        conn, date_from=date_from, date_to=date_to, tool_name=tool_name,
                        transcript=transcript, q=q, limit=limit, offset=offset,
                    )
                finally:
                    conn.close()
        except Exception as e:
            log.warning("Audit query failed: %s", e)
            rows = []
        return {"rows": rows, "limit": limit, "offset": offset}

    @app.get("/api/services")
    def api_services() -> dict:
        if not get_services:
            return {"services": []}
        try:
            return {"services": get_services()}
        except Exception as e:
            log.warning("get_services failed: %s", e)
            return {"services": []}

    @app.get("/api/daily")
    def api_daily() -> dict:
        if not get_daily:
            return {"items": []}
        try:
            return {"items": get_daily()}
        except Exception as e:
            log.warning("get_daily failed: %s", e)
            return {"items": []}

    @app.get("/api/usage")
    def api_usage() -> dict:
        # Read-only local spend estimate (see jarvis_billing.local_summary) — no admin key, no
        # network call, nothing written.
        if not get_usage:
            return {"usage": None}
        try:
            return {"usage": get_usage()}
        except Exception as e:
            log.warning("get_usage failed: %s", e)
            return {"usage": None}

    @app.get("/api/sleep")
    def api_sleep() -> dict:
        # Read-only sleep trends from sleep_log (see jarvis_sleep_mode.stats_summary).
        if not get_sleep:
            return {"sleep": None}
        try:
            return {"sleep": get_sleep()}
        except Exception as e:
            log.warning("get_sleep failed: %s", e)
            return {"sleep": None}

    @app.get("/api/llm")
    def api_llm() -> dict:
        if not get_llm:
            return {"llm": None}
        try:
            return {"llm": get_llm()}
        except Exception as e:
            log.warning("get_llm failed: %s", e)
            return {"llm": None}

    @app.post("/api/llm")
    def api_set_llm(payload: dict = Body(...)):
        # Switches which AI brain (Claude/Gemini) answers. Goes through jarvis.set_llm_provider,
        # which refuses a provider with no key configured. Same localhost-only trust level as the
        # command box; the frontend asks for confirmation before switching to Gemini's free tier.
        if not set_llm or not get_llm:
            return JSONResponse({"error": "not available yet"}, status_code=501)
        message = set_llm(str((payload or {}).get("provider") or ""))
        ok = message.startswith("Switched")
        return JSONResponse({"ok": ok, "message": message, "llm": get_llm()}, status_code=200 if ok else 400)

    @app.delete("/api/sessions/finished")
    def api_clear_finished_sessions() -> dict:
        return {"ok": True, "removed": clear_finished_sessions()}

    @app.post("/api/pending/approve")
    def api_approve():
        if not approve_pending:
            return JSONResponse({"error": "not available yet"}, status_code=501)
        reply = approve_pending()
        return {"ok": True, "reply": reply}

    @app.post("/api/pending/reject")
    def api_reject():
        if not reject_pending:
            return JSONResponse({"error": "not available yet"}, status_code=501)
        return {"ok": reject_pending()}

    @app.post("/api/tasks/{task_id}/stop")
    def api_stop_task(task_id: str):
        if not kill_background_task:
            return JSONResponse({"error": "not available yet"}, status_code=501)
        # Only background_tasks rows (id "bg-<n>") have a live OS process to kill — task_queue
        # and reminders entries have no such process, so stopping them isn't offered.
        if not task_id.startswith("bg-"):
            return JSONResponse(
                {"error": "only background (code/research) tasks can be stopped"}, status_code=400
            )
        try:
            numeric_id = int(task_id[len("bg-"):])
        except ValueError:
            return JSONResponse({"error": "invalid task id"}, status_code=400)
        return {"ok": True, "result": kill_background_task(numeric_id)}

    @app.post("/api/command")
    def api_command(payload: dict = Body(...)):
        if not run_command:
            return JSONResponse({"error": "not available yet"}, status_code=501)
        text = str((payload or {}).get("text") or "").strip()
        if not text:
            return JSONResponse({"error": "empty command"}, status_code=400)

        def _sink(reply: str) -> None:
            notify({"type": "command_reply", "data": {"text": text, "reply": reply}})

        threading.Thread(target=run_command, args=(text, _sink), daemon=True).start()
        return {"ok": True}

    # --- Identity tab (face recognition; see jarvis_face.py) ---------------------------------------
    # `face` is the jarvis_face module (injected, like every other provider here). These are the
    # most sensitive routes on the dashboard - pictures of visitors, profile export/erase - so
    # every one rejects a request whose Host header isn't a loopback name. That defeats DNS
    # rebinding (a hostile web page re-pointing its own domain at 127.0.0.1 to read same-origin).
    # Nothing here ever returns a face vector; pictures are served one at a time, never cached.
    _NO_STORE = {"Cache-Control": "no-store"}

    def _face_guard(request):
        if not _host_is_loopback(request.headers.get("host") or ""):
            return JSONResponse({"error": "forbidden host"}, status_code=403)
        # A page on another site can still fire a "simple" cross-origin request at 127.0.0.1 with a
        # perfectly valid Host, so a state-changing call must also come from this dashboard's own
        # origin (browsers always send Origin on cross-origin POST/DELETE).
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and not _origin_is_loopback(origin):
                return JSONResponse({"error": "forbidden origin"}, status_code=403)
        return None

    def _face_unavailable():
        return face is None or not face.enabled()

    @app.get("/api/faces")
    def api_faces(request: Request):
        bad = _face_guard(request)
        if bad:
            return bad
        if face is None:
            return JSONResponse({"enabled": False}, headers=_NO_STORE)
        try:
            return JSONResponse(face.dashboard_state(), headers=_NO_STORE)
        except Exception as e:
            log.warning("face dashboard_state failed: %s", e)
            return JSONResponse({"enabled": False, "error": "unavailable"}, headers=_NO_STORE)

    @app.get("/api/faces/events")
    def api_face_events(request: Request, limit: int = 100, offset: int = 0, kind: str | None = None):
        bad = _face_guard(request)
        if bad:
            return bad
        if _face_unavailable():
            return JSONResponse({"rows": []}, headers=_NO_STORE)
        try:
            rows = face.recent_events(limit=limit, offset=offset, kind=kind or None)
        except Exception as e:
            log.warning("face events failed: %s", e)
            rows = []
        return JSONResponse({"rows": rows}, headers=_NO_STORE)

    @app.get("/api/faces/snapshots")
    def api_face_snapshots(request: Request):
        bad = _face_guard(request)
        if bad:
            return bad
        if _face_unavailable():
            return JSONResponse({"rows": []}, headers=_NO_STORE)
        return JSONResponse({"rows": face.list_snapshots(limit=200)}, headers=_NO_STORE)

    @app.get("/api/faces/snapshots/{snapshot_id}/image")
    def api_face_snapshot_image(snapshot_id: int, request: Request):
        bad = _face_guard(request)
        if bad:
            return bad
        if _face_unavailable():
            return JSONResponse({"error": "face recognition is off"}, status_code=404)
        data = face.get_snapshot(snapshot_id)
        if data is None:
            return JSONResponse({"error": "no such picture"}, status_code=404)
        return Response(
            content=data, media_type="image/jpeg",
            headers={**_NO_STORE, "X-Content-Type-Options": "nosniff"},
        )

    @app.delete("/api/faces/snapshots")
    def api_face_delete_snapshots(request: Request):
        bad = _face_guard(request)
        if bad:
            return bad
        if _face_unavailable():
            return JSONResponse({"ok": False, "error": "face recognition is off"}, status_code=404)
        return JSONResponse({"ok": True, "removed": face.delete_all_snapshots()}, headers=_NO_STORE)

    @app.get("/api/faces/{profile_id}/export")
    def api_face_export(profile_id: int, request: Request):
        bad = _face_guard(request)
        if bad:
            return bad
        if _face_unavailable():
            return JSONResponse({"error": "face recognition is off"}, status_code=404)
        data = face.export_profile(profile_id)
        if data is None:
            return JSONResponse({"error": "no such profile"}, status_code=404)
        return JSONResponse(
            data,
            headers={**_NO_STORE, "Content-Disposition": f'attachment; filename="face-profile-{profile_id}.json"'},
        )

    @app.delete("/api/faces/{profile_id}")
    def api_face_delete(profile_id: int, request: Request, confirm: bool = False):
        bad = _face_guard(request)
        if bad:
            return bad
        if _face_unavailable():
            return JSONResponse({"ok": False, "error": "face recognition is off"}, status_code=404)
        if not confirm:  # the UI asks the user first; a bare DELETE never erases anything
            return JSONResponse({"ok": False, "error": "confirm=true required"}, status_code=400)
        message = face.delete_by_id(profile_id, "dashboard")
        ok = message.startswith("Deleted")
        return JSONResponse({"ok": ok, "message": message}, status_code=200 if ok else 404, headers=_NO_STORE)

    @app.post("/api/faces/away")
    def api_face_away(request: Request, payload: dict = Body(...)):
        bad = _face_guard(request)
        if bad:
            return bad
        if _face_unavailable():
            return JSONResponse({"ok": False, "error": "face recognition is off"}, status_code=404)
        message = face.set_away(bool((payload or {}).get("enabled")), "dashboard")
        return JSONResponse({"ok": True, "message": message, "away": face.away_enabled()}, headers=_NO_STORE)

    @app.post("/api/faces/pause")
    def api_face_pause(request: Request, payload: dict = Body(...)):
        bad = _face_guard(request)
        if bad:
            return bad
        if _face_unavailable():
            return JSONResponse({"ok": False, "error": "face recognition is off"}, status_code=404)
        message = face.set_paused(bool((payload or {}).get("paused")), "dashboard")
        return JSONResponse({"ok": True, "message": message, "paused": face.is_paused()}, headers=_NO_STORE)

    # --- Autonomy tab (jarvis_autonomy.py / jarvis_dynamic_tools.py) --------------------------------
    # Same trust level and the same Host/Origin guard as the Identity routes: approving a suggestion
    # makes Jarvis act, so a cross-site request must never be able to do it. Approve/Dismiss/"Never"
    # are the teach loop; none of these routes touch the catastrophic confirmation gate (an approved
    # action runs through the normal agent loop, gate included).
    def _auto_unavailable():
        return autonomy is None

    @app.get("/api/autonomy")
    def api_autonomy(request: Request):
        bad = _face_guard(request)
        if bad:
            return bad
        if _auto_unavailable():
            return JSONResponse({"available": False}, headers=_NO_STORE)
        try:
            data = autonomy.status()
            data["available"] = True
            if autonomy_skills is not None:
                data["skills"] = autonomy_skills.list_skills()
            if autonomy_organise is not None:
                data["organise"] = autonomy_organise.overview()
            if dyn_tools is not None:
                data["dynamic_tools"] = dyn_tools.list_tools()
                data["dynamic_tool_proposals"] = dyn_tools.list_proposals()
                data["dynamic_tools_disabled"] = dyn_tools.disabled()
            return JSONResponse(data, headers=_NO_STORE)
        except Exception as e:
            log.warning("autonomy status failed: %s", e)
            return JSONResponse({"available": False, "error": "unavailable"}, headers=_NO_STORE)

    @app.post("/api/autonomy/enabled")
    def api_autonomy_enabled(request: Request, payload: dict = Body(...)):
        bad = _face_guard(request)
        if bad:
            return bad
        if _auto_unavailable():
            return JSONResponse({"ok": False}, status_code=501)
        msg = autonomy.set_enabled(bool((payload or {}).get("enabled")))
        return JSONResponse({"ok": True, "message": msg, "enabled": autonomy.enabled()}, headers=_NO_STORE)

    @app.post("/api/autonomy/dry_run")
    def api_autonomy_dry_run(request: Request, payload: dict = Body(...)):
        bad = _face_guard(request)
        if bad:
            return bad
        if _auto_unavailable():
            return JSONResponse({"ok": False}, status_code=501)
        msg = autonomy.set_dry_run(bool((payload or {}).get("enabled")))
        return JSONResponse({"ok": True, "message": msg, "dry_run": autonomy.dry_run()}, headers=_NO_STORE)

    @app.post("/api/autonomy/suggestions/{sid}/{verb}")
    def api_autonomy_suggestion(sid: int, verb: str, request: Request):
        bad = _face_guard(request)
        if bad:
            return bad
        if _auto_unavailable():
            return JSONResponse({"ok": False}, status_code=501)
        if verb == "approve":
            msg = autonomy.approve_suggestion(sid)
        elif verb in ("dismiss", "never"):
            msg = autonomy.dismiss_suggestion(sid, never=verb == "never")
        else:
            return JSONResponse({"ok": False, "error": "unknown action"}, status_code=400)
        return JSONResponse({"ok": True, "message": msg}, headers=_NO_STORE)

    @app.post("/api/autonomy/policies")
    def api_autonomy_policy(request: Request, payload: dict = Body(...)):
        bad = _face_guard(request)
        if bad:
            return bad
        if _auto_unavailable():
            return JSONResponse({"ok": False}, status_code=501)
        p = payload or {}
        conf = p.get("min_confidence")
        try:
            conf = float(conf) if conf not in (None, "") else None
        except (TypeError, ValueError):
            conf = None
        msg = autonomy.set_policy(str(p.get("category") or ""), str(p.get("verdict") or ""),
                                  str(p.get("match_kind") or "category"), str(p.get("match_value") or ""), conf)
        return JSONResponse({"ok": msg.startswith("Rule saved"), "message": msg}, headers=_NO_STORE)

    @app.delete("/api/autonomy/policies/{pid}")
    def api_autonomy_policy_delete(pid: int, request: Request):
        bad = _face_guard(request)
        if bad:
            return bad
        if _auto_unavailable():
            return JSONResponse({"ok": False}, status_code=501)
        return JSONResponse({"ok": True, "message": autonomy.delete_policy(pid)}, headers=_NO_STORE)

    @app.post("/api/autonomy/commitments/{cid}/status")
    def api_autonomy_commitment(cid: int, request: Request, payload: dict = Body(...)):
        bad = _face_guard(request)
        if bad:
            return bad
        if _auto_unavailable():
            return JSONResponse({"ok": False}, status_code=501)
        msg = autonomy.set_commitment_status(cid, str((payload or {}).get("status") or ""))
        return JSONResponse({"ok": msg.startswith("Commitment"), "message": msg}, headers=_NO_STORE)

    # Human-only decisions (audit B-01): the model's `autonomy`/`create_tool` tools cannot approve,
    # accept or enable anything - these routes, behind the Host/Origin guard, are the only way.
    @app.get("/api/autonomy/log")
    def api_autonomy_log(request: Request, hours: float = 24, decision: str = "", category: str = "",
                         outcome: str = "", q: str = "", limit: int = 100):
        """Filterable decision/action log: time range, type, category, outcome, free text."""
        bad = _face_guard(request)
        if bad:
            return bad
        if _auto_unavailable():
            return JSONResponse({"available": False}, headers=_NO_STORE)
        return JSONResponse({
            "available": True, "enabled": autonomy.enabled(), "dry_run": autonomy.dry_run(),
            "budgets": autonomy.budgets(),
            "entries": autonomy.log_entries(hours, decision, category, outcome, q, limit),
        }, headers=_NO_STORE)

    @app.post("/api/autonomy/organise/rules")
    def api_organise_add_rule(request: Request, payload: dict = Body(...)):
        bad = _face_guard(request)
        if bad:
            return bad
        if autonomy_organise is None:
            return JSONResponse({"ok": False}, status_code=501)
        p = payload or {}
        msg = autonomy_organise.add_rule(str(p.get("name") or ""), p.get("extensions"), str(p.get("dest_dir") or ""),
                                         str(p.get("action") or "move"))
        return JSONResponse({"ok": msg.startswith("Rule ") and "not saved" not in msg, "message": msg},
                            headers=_NO_STORE)

    @app.delete("/api/autonomy/organise/rules/{name}")
    def api_organise_remove_rule(name: str, request: Request):
        bad = _face_guard(request)
        if bad:
            return bad
        if autonomy_organise is None:
            return JSONResponse({"ok": False}, status_code=501)
        return JSONResponse({"ok": True, "message": autonomy_organise.remove_rule(name)}, headers=_NO_STORE)

    @app.post("/api/autonomy/organise/roots")
    def api_organise_add_root(request: Request, payload: dict = Body(...)):
        bad = _face_guard(request)
        if bad:
            return bad
        if autonomy_organise is None:
            return JSONResponse({"ok": False}, status_code=501)
        msg = autonomy_organise.add_root(str((payload or {}).get("path") or ""))
        return JSONResponse({"ok": msg.startswith("Now"), "message": msg}, headers=_NO_STORE)

    @app.post("/api/autonomy/organise/roots/remove")
    def api_organise_remove_root(request: Request, payload: dict = Body(...)):
        bad = _face_guard(request)
        if bad:
            return bad
        if autonomy_organise is None:
            return JSONResponse({"ok": False}, status_code=501)
        return JSONResponse({"ok": True, "message": autonomy_organise.remove_root(str((payload or {}).get("path") or ""))},
                            headers=_NO_STORE)

    @app.post("/api/autonomy/skills/{name}/{verb}")
    def api_autonomy_skill(name: str, verb: str, request: Request):
        bad = _face_guard(request)
        if bad:
            return bad
        if autonomy_skills is None:
            return JSONResponse({"ok": False}, status_code=501)
        if verb not in ("enable", "disable", "revoke"):
            return JSONResponse({"ok": False, "error": "unknown action"}, status_code=400)
        msg = (autonomy_skills.set_enabled(name, verb == "enable") if verb != "revoke"
               else autonomy_skills.revoke(name))
        return JSONResponse({"ok": not msg.startswith("No skill"), "message": msg}, headers=_NO_STORE)

    @app.post("/api/autonomy/commitments/{cid}/accept")
    def api_autonomy_commitment_accept(cid: int, request: Request):
        bad = _face_guard(request)
        if bad:
            return bad
        if _auto_unavailable():
            return JSONResponse({"ok": False}, status_code=501)
        msg = autonomy.accept_commitment(cid)
        return JSONResponse({"ok": msg.startswith("Commitment"), "message": msg}, headers=_NO_STORE)

    @app.post("/api/autonomy/campaigns/approve")
    def api_autonomy_campaign_approve(request: Request, payload: dict = Body(...)):
        bad = _face_guard(request)
        if bad:
            return bad
        if _auto_unavailable():
            return JSONResponse({"ok": False}, status_code=501)
        p = payload or {}
        msg = autonomy.approve_campaign(str(p.get("project") or ""), p.get("approved", True) is not False)
        return JSONResponse({"ok": msg.startswith("Campaign"), "message": msg}, headers=_NO_STORE)

    @app.post("/api/autonomy/campaigns/action")
    def api_autonomy_campaign_action(request: Request, payload: dict = Body(...)):
        bad = _face_guard(request)
        if bad:
            return bad
        if _auto_unavailable():
            return JSONResponse({"ok": False}, status_code=501)
        p = payload or {}
        msg = autonomy.add_project_action(str(p.get("project") or ""), str(p.get("description") or ""),
                                          str(p.get("scheduled_for") or ""),
                                          str(p.get("action_type") or "background_task"))
        return JSONResponse({"ok": msg.startswith("Added"), "message": msg}, headers=_NO_STORE)

    @app.post("/api/dynamic_tools/proposals/{pid}/{verb}")
    def api_dynamic_tool_proposal(pid: int, verb: str, request: Request):
        bad = _face_guard(request)
        if bad:
            return bad
        if dyn_tools is None:
            return JSONResponse({"ok": False}, status_code=501)
        if verb not in ("approve", "reject"):
            return JSONResponse({"ok": False, "error": "unknown action"}, status_code=400)
        msg = dyn_tools.decide_proposal(pid, verb == "approve")
        return JSONResponse({"ok": msg.startswith(("Created", "Rejected")), "message": msg}, headers=_NO_STORE)

    @app.post("/api/dynamic_tools/{name}/{verb}")
    def api_dynamic_tool(name: str, verb: str, request: Request):
        bad = _face_guard(request)
        if bad:
            return bad
        if dyn_tools is None:
            return JSONResponse({"ok": False}, status_code=501)
        if verb not in ("enable", "disable"):
            return JSONResponse({"ok": False, "error": "unknown action"}, status_code=400)
        return JSONResponse({"ok": True, "message": dyn_tools.set_enabled(name, verb == "enable")}, headers=_NO_STORE)

    @app.delete("/api/dynamic_tools/{name}")
    def api_dynamic_tool_revoke(name: str, request: Request):
        bad = _face_guard(request)
        if bad:
            return bad
        if dyn_tools is None:
            return JSONResponse({"ok": False}, status_code=501)
        return JSONResponse({"ok": True, "message": dyn_tools.revoke(name)}, headers=_NO_STORE)

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        # Cross-site WebSocket hijacking: any web page can open ws://127.0.0.1:port/ws, and this
        # socket now carries presence events (face_event) as well as session/task updates. Browsers
        # always send Origin on a WebSocket handshake, so refuse one that isn't this machine.
        origin = websocket.headers.get("origin")
        if origin and not _origin_is_loopback(origin):
            await websocket.close(code=1008)
            return
        await websocket.accept()
        manager.add(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            manager.remove(websocket)

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    else:
        log.warning("Dashboard static dir %s not found; serving API only.", STATIC_DIR)

    return app


def start(
    *,
    port: int = DEFAULT_PORT,
    get_pending: Callable[[], dict | None] | None = None,
    get_system_status: Callable[[], dict] | None = None,
    approve_pending: Callable[[], str | None] | None = None,
    reject_pending: Callable[[], bool] | None = None,
    kill_background_task: Callable[[int], str] | None = None,
    run_command: Callable[[str, Callable[[str], None]], None] | None = None,
    get_services: Callable[[], list[dict]] | None = None,
    get_daily: Callable[[], list[dict]] | None = None,
    get_usage: Callable[[], dict] | None = None,
    get_sleep: Callable[[], dict] | None = None,
    get_llm: Callable[[], dict] | None = None,
    set_llm: Callable[[str], str] | None = None,
    face=None,
    autonomy=None,
    autonomy_skills=None,
    autonomy_organise=None,
    dyn_tools=None,
) -> None:
    """Blocking call — run this in its own daemon thread from jarvis.py's main(). Binds
    127.0.0.1 only, by design: this server is a second surface that can (in later phases)
    trigger commands and approve the catastrophic confirmation gate, so it must never be
    reachable off-machine. approve_pending/reject_pending/kill_background_task/run_command are
    optional and phased in later (Phase 2/4) — omitted here, the corresponding endpoints
    respond 501."""
    app = _build_app(
        get_pending=get_pending,
        get_system_status=get_system_status,
        approve_pending=approve_pending,
        reject_pending=reject_pending,
        kill_background_task=kill_background_task,
        run_command=run_command,
        get_services=get_services,
        get_daily=get_daily,
        get_usage=get_usage,
        get_sleep=get_sleep,
        get_llm=get_llm,
        set_llm=set_llm,
        face=face,
        autonomy=autonomy,
        autonomy_skills=autonomy_skills,
        autonomy_organise=autonomy_organise,
        dyn_tools=dyn_tools,
        port=port,
    )
    if app is None:
        return

    if get_system_status:
        # Sample once here (server-side, on a single timer) and just ping connected clients to
        # refetch /api/state — cheaper than each browser tab independently polling a call that
        # blocks ~0.4s (psutil.cpu_percent's sampling window).
        def _metrics_loop() -> None:
            while True:
                time.sleep(5)
                notify({"type": "metrics_tick"})

        threading.Thread(target=_metrics_loop, daemon=True, name="dashboard-metrics-tick").start()

    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    uvicorn.Server(config).run()
