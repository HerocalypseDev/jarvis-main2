"""Link between Jarvis and the Jarvis Tabs browser extension (2026-10-03, owner request: see and act on every tab).

The extension (browser_extension/, loaded unpacked in Opera GX now, Firefox later) connects to this small WebSocket server
on 127.0.0.1 and waits for commands. Commands only ever go Jarvis -> extension (list/read/close/reopen/switch/open tabs);
the extension never accepts anything from a web page.

Who can talk to whom:
- The server binds 127.0.0.1 only, and refuses any connection whose Origin isn't an extension (a web page can open a
  WebSocket to localhost, but its Origin is the website, which it can't fake).
- Both sides prove they know the pairing key (HMAC over each other's random nonce) before anything else is sent. The key
  lives in browser_extension/pairing.json (gitignored), written by Jarvis the first time it runs, which the unpacked
  extension reads from its own folder: no copy-paste. A program squatting on the port without the key gets nothing: the
  extension checks the server's proof before it answers any command.
- Any program running as the same Windows user can read pairing.json, but such a program could already read the browser's
  own profile; the key stops web pages and other machines, which is what matters here.
"""

import asyncio
import hashlib
import hmac
import itertools
import json
import logging
import os
import secrets
import threading
import time
from pathlib import Path

log = logging.getLogger("jarvis.browser_bridge")

DEFAULT_PORT = 8767
PAIRING_FILE = "pairing.json"
HANDSHAKE_TIMEOUT_S = 10
EXTENSION_ORIGINS = ("chrome-extension://", "moz-extension://", "extension://")
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "[::1]")


class BridgeError(Exception):
    pass


def _proof(key: str, msg: str) -> str:
    return hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest()


def ensure_pairing(ext_dir: Path, port: int) -> str:
    """Returns the pairing key, creating browser_extension/pairing.json if it is missing (or has another port)."""
    path = Path(ext_dir) / PAIRING_FILE
    data = {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    key = str(data.get("key") or "")
    if len(key) < 32 or not all(c in "0123456789abcdef" for c in key):
        key = secrets.token_hex(32)
    if data.get("key") != key or data.get("port") != port:
        Path(ext_dir).mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"port": port, "key": key}, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    return key


class _Conn:
    def __init__(self, ws, browser: str, version: str):
        self.ws, self.browser, self.version = ws, browser, version
        self.since = self.last_seen = time.time()
        self.pending: dict[int, asyncio.Future] = {}


class Bridge:
    def __init__(self, key: str, port: int = DEFAULT_PORT, preferred=lambda: ""):
        self.key, self.port, self.preferred = key, port, preferred
        self._loop: asyncio.AbstractEventLoop | None = None
        self._conns: list[_Conn] = []
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._server = None
        self.started = False

    # ---------------------------------------------------------------- server
    def build_app(self):
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect

        app = FastAPI()

        @app.websocket("/tabs")
        async def tabs(ws: WebSocket):  # noqa: ANN202
            origin = ws.headers.get("origin", "")
            host = ws.headers.get("host", "").rsplit(":", 1)[0].lower()
            if not origin.startswith(EXTENSION_ORIGINS) or host not in LOOPBACK_HOSTS:
                await ws.close(code=1008)
                return
            await ws.accept()
            self._loop = asyncio.get_running_loop()
            conn = None
            try:
                conn = await self._handshake(ws)
                if conn is None:
                    await ws.close(code=1008)
                    return
                with self._lock:
                    self._conns.append(conn)
                log.info("Jarvis Tabs extension connected (%s %s).", conn.browser, conn.version)
                while True:
                    msg = json.loads(await ws.receive_text())
                    conn.last_seen = time.time()
                    if msg.get("type") == "result":
                        fut = conn.pending.get(msg.get("id"))
                        if fut and not fut.done():
                            fut.set_result(msg)
                    elif msg.get("type") == "ping":
                        await ws.send_text('{"type":"pong"}')
            except (WebSocketDisconnect, asyncio.TimeoutError, ValueError, RuntimeError):
                pass
            except Exception as e:  # never let one bad connection kill the server
                log.warning("Browser extension connection error: %s", e)
            finally:
                if conn:
                    with self._lock:
                        if conn in self._conns:
                            self._conns.remove(conn)
                    for fut in conn.pending.values():
                        if not fut.done():
                            fut.set_exception(BridgeError("the browser extension disconnected"))
                    log.info("Jarvis Tabs extension disconnected (%s).", conn.browser)

        return app

    async def _handshake(self, ws) -> _Conn | None:
        hello = json.loads(await asyncio.wait_for(ws.receive_text(), HANDSHAKE_TIMEOUT_S))
        their_nonce = str(hello.get("nonce") or "")
        if hello.get("type") != "hello" or not 16 <= len(their_nonce) <= 128:
            return None
        my_nonce = secrets.token_hex(16)
        await ws.send_text(json.dumps({"type": "challenge", "proof": _proof(self.key, "jarvis-server:" + their_nonce),
                                       "nonce": my_nonce}))
        auth = json.loads(await asyncio.wait_for(ws.receive_text(), HANDSHAKE_TIMEOUT_S))
        if auth.get("type") != "auth" or not hmac.compare_digest(
                str(auth.get("proof") or ""), _proof(self.key, "jarvis-extension:" + my_nonce)):
            log.warning("A browser extension connected with the wrong pairing key; refused.")
            return None
        await ws.send_text('{"type":"ready"}')
        return _Conn(ws, str(hello.get("browser") or "Browser")[:40], str(hello.get("version") or "")[:20])

    def start(self) -> bool:
        """Runs the server on its own daemon thread. False when FastAPI/uvicorn aren't installed."""
        try:
            import uvicorn
            app = self.build_app()
        except ImportError as e:
            log.info("Browser tabs bridge off: %s (pip install fastapi uvicorn[standard]).", e)
            return False
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning")
        self._server = uvicorn.Server(config)

        def _run():
            try:
                self._server.run()
            except BaseException as e:  # a port in use ends this thread, never Jarvis
                log.warning("Browser tabs bridge stopped: %s", e)

        threading.Thread(target=_run, daemon=True, name="browser-bridge").start()
        self.started = True
        return True

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True

    # ---------------------------------------------------------------- client side (any Jarvis thread)
    def status(self) -> list[dict]:
        with self._lock:
            return [{"browser": c.browser, "version": c.version, "since": c.since, "last_seen": c.last_seen}
                    for c in self._conns]

    def connected(self) -> bool:
        with self._lock:
            return bool(self._conns)

    def _pick(self) -> _Conn | None:
        with self._lock:
            conns = list(self._conns)
        if not conns:
            return None
        want = (self.preferred() or "").lower().replace(" ", "")
        for c in reversed(conns):
            if want and want in c.browser.lower().replace(" ", ""):
                return c
        return max(conns, key=lambda c: c.last_seen)

    def browser_name(self) -> str:
        c = self._pick()
        return c.browser if c else ""

    def request(self, action: str, args: dict | None = None, timeout: float = 10.0) -> dict:
        conn = self._pick()
        if conn is None or self._loop is None:
            raise BridgeError("not connected")
        fut = asyncio.run_coroutine_threadsafe(self._send(conn, action, args or {}, timeout), self._loop)
        try:
            return fut.result(timeout + 2)
        except BridgeError:
            raise
        except Exception as e:
            fut.cancel()
            raise BridgeError(f"the browser didn't answer ({type(e).__name__})") from e

    async def _send(self, conn: _Conn, action: str, args: dict, timeout: float):
        rid = next(self._ids)
        fut = asyncio.get_running_loop().create_future()
        conn.pending[rid] = fut
        try:
            await conn.ws.send_text(json.dumps({"type": "cmd", "id": rid, "action": action, "args": args}))
            msg = await asyncio.wait_for(fut, timeout)
        finally:
            conn.pending.pop(rid, None)
        if not msg.get("ok"):
            raise BridgeError(str(msg.get("error") or "the browser refused")[:300])
        return msg.get("data")
