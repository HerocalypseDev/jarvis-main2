"""Client for the homework app's Jarvis API (LearnAi: POST /api/jarvis). Stdlib only, never imports jarvis.py.

Configuration is read at call time (so a changed .env works after a restart without code changes):
  HOMEWORK_APP_URL     e.g. https://learn-ai-xxxx.vercel.app (no trailing slash needed)
  HOMEWORK_API_TOKEN   the same value as JARVIS_API_TOKEN in the app's Vercel settings

The token and the signed file links are credentials: they never appear in an exception message or a log line.
"""

from __future__ import annotations

import http.client
import json
import re
import os
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "Jarvis-Homework/1.0"  # the app shows this as the device in its Activity log
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
MAX_RESPONSE_BYTES = 8 * 1024 * 1024  # a CSV export is the largest answer the app sends


class HomeworkApiError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status


def _base_url() -> str:
    url = (os.environ.get("HOMEWORK_APP_URL") or "").strip().strip("\"'").rstrip("/")
    # "my-app.vercel.app" is what Vercel shows and what people paste: https is the only sensible reading.
    if url and "://" not in url:
        url = "https://" + url
    return url


def _token() -> str:
    return (os.environ.get("HOMEWORK_API_TOKEN") or "").strip()


def is_configured() -> bool:
    return bool(_base_url() and _token())


def _endpoint() -> str:
    base = _base_url()
    if not base or not _token():
        raise HomeworkApiError("The homework app isn't set up: add HOMEWORK_APP_URL and HOMEWORK_API_TOKEN to .env.")
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme == "http" and (parsed.hostname or "") not in _LOCAL_HOSTS:
        raise HomeworkApiError("HOMEWORK_APP_URL must start with https:// (the token is never sent over plain http).")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HomeworkApiError("HOMEWORK_APP_URL doesn't look like a web address.")
    return base + "/api/jarvis"


_FALLBACK = {
    400: "The homework app said the request wasn't valid.",
    401: "The homework app rejected Jarvis's token: HOMEWORK_API_TOKEN must equal JARVIS_API_TOKEN in Vercel.",
    403: "The homework app is in read-only mode for Jarvis (JARVIS_API_READ_ONLY=1).",
    404: "The homework app couldn't find that.",
    500: "The homework app had an error.",
    503: "The homework app has Jarvis access turned off (no JARVIS_API_TOKEN set in Vercel).",
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib re-sends the Authorization header on a redirect, to any host and even from https to http.
    The API never redirects, so a redirect is refused instead of followed."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HomeworkApiError("The homework app redirected the request; check HOMEWORK_APP_URL "
                               "(use the exact https address of the app, no path).", code)


_api_opener = urllib.request.build_opener(_NoRedirect)


def _request(method: str, body: dict | None, timeout: float):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(_endpoint(), data=data, method=method, headers={
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    })
    try:
        with _api_opener.open(req, timeout=timeout) as r:
            status, raw = r.status, r.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise HomeworkApiError("The homework app's answer was too large.")
    except HomeworkApiError:
        raise
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read() if hasattr(e, "read") else b""
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as e:
        # Debug report 2026-10-07: the bare message sent the model hunting for a local server. The app is hosted online;
        # say what failed (without the address or any token) so the owner is told the real reason.
        reason = e.reason if isinstance(e, urllib.error.URLError) else e
        text = f"{type(reason).__name__} {reason}".lower()
        why = ("this PC has no internet or can't look up the address (DNS)" if "getaddrinfo" in text or "11001" in text
               or "11002" in text or "name or service" in text else
               "the connection timed out" if "timed out" in text or isinstance(e, TimeoutError) else
               "the connection was blocked or reset (a firewall, VPN or proxy?)" if "10054" in text or "refused" in text
               or "reset" in text or "forcibly" in text else
               "a secure connection (SSL) problem" if "ssl" in text or "certificate" in text else
               f"{type(reason).__name__}")
        raise HomeworkApiError("Can't reach the homework app right now: " + why + ". The app is hosted online (not on this PC), "
                               "so don't look for a local server; tell the user this reason.") from None
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        payload = {}
    if status >= 400 or not payload.get("ok", status < 400):
        msg = str(payload.get("error") or "").strip() or _FALLBACK.get(status) or f"The homework app answered {status}."
        msg = re.sub(r"https?://\S+", "[link hidden]", msg)[:400]  # audit 2026-10-04: an error may quote a signed link
        raise HomeworkApiError(msg, status)
    return payload


def list_tools(timeout: float = 30) -> list[dict]:
    return list(_request("GET", None, timeout).get("tools") or [])


def call(tool: str, args: dict | None = None, timeout: float = 30) -> object:
    clean = {k: v for k, v in (args or {}).items() if v is not None}
    return _request("POST", {"tool": tool, "args": clean}, timeout).get("result")


def download(url: str, max_bytes: int = 21 * 1024 * 1024, timeout: float = 60) -> bytes:
    """GET a signed file link (the link itself is the credential: no auth header). Stops past max_bytes."""
    parsed = urllib.parse.urlparse(str(url or ""))
    if parsed.scheme != "https" and (parsed.hostname or "") not in _LOCAL_HOSTS:
        raise HomeworkApiError("A file link wasn't https, so it wasn't downloaded.")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            chunks, total = [], 0
            while True:
                block = r.read(256 * 1024)
                if not block:
                    break
                total += len(block)
                if total > max_bytes:
                    raise HomeworkApiError(f"A file is larger than {max_bytes // (1024 * 1024)} MB, so it wasn't downloaded.")
                chunks.append(block)
            return b"".join(chunks)
    except HomeworkApiError:
        raise
    except urllib.error.HTTPError as e:
        raise HomeworkApiError(f"A file couldn't be downloaded (HTTP {e.code}; the link may have expired).") from None
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
        raise HomeworkApiError("A file couldn't be downloaded right now.") from None
