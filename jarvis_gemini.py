"""Gemini (Google AI Studio) backend for Jarvis's LLM calls.

Jarvis's callers all speak Anthropic's Messages format (system / messages / tools in, content
blocks + stop_reason + usage out). Rather than touching every caller, this module translates: it
takes an Anthropic-shaped request body, calls Gemini's generateContent, and returns an
Anthropic-shaped response, so `_claude_request` can hand back the same dict either way.

Also holds the persisted provider choice (llm_provider.json > JARVIS_LLM_PROVIDER > "claude").
Pure translation functions take/return plain dicts and never touch the network, so they are
unit-tested with fixtures; only `call` does I/O, and it takes the HTTP function as a parameter.
"""

from __future__ import annotations

import http.client
import io
import json
import logging
import os
import queue
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Callable

log = logging.getLogger("jarvis")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# 2026-09-22: bumped from gemini-3.1-flash-lite — confirmed live against
# generativelanguage.googleapis.com/v1beta/models that 3.1 is still listed but Google's error
# responses for nearby dated models point at 3.6+ as current; gemini-3.5-flash-lite was chosen
# over the newer 3.6/3.7/3.8 lines because it already has a jarvis_billing.PRICES entry (keeps
# local cost tracking exact instead of falling back to the "approximate" Haiku-rate guess) and
# is confirmed live (not 404) on this key. Update PRICES too if this is bumped again.
# 2026-09-24: 3.5-flash-lite's free tier is 500 requests/day and ran out, so Gemini went dead
# until the reset. Default is back to 3.1-flash-lite (confirmed working live). No automatic
# model fallback (removed 2026-09-25, user request): the user picks the model in Settings.
DEFAULT_MODEL = "gemini-3.1-flash-lite"
PROVIDERS = ("claude", "gemini", "ollama")  # ollama: local brain (jarvis_ollama)
MAX_RETRY_WAIT_S = 30.0  # longest 429 "retry after" Jarvis will sit through mid-command, for a per-MINUTE limit.
# (A per-DAY limit is never waited on: see quota_kind. Google's retryDelay is meaningless for it, often 2 s.)


# --- provider choice -----------------------------------------------------------------------
def get_provider(settings_path: Path) -> str:
    try:
        p = json.loads(Path(settings_path).read_text(encoding="utf-8")).get("provider")
        if p in PROVIDERS:
            return p
    except (OSError, ValueError, AttributeError):
        pass
    env = (os.environ.get("JARVIS_LLM_PROVIDER") or "").strip().lower()
    return env if env in PROVIDERS else "claude"


def set_provider(settings_path: Path, provider: str) -> None:
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}")
    Path(settings_path).write_text(json.dumps({"provider": provider}), encoding="utf-8")


def api_key() -> str:
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()


_models_cache: tuple[float, list[str]] = (0.0, [])
# Not usable as Jarvis's brain: speech, image, music, robotics and agent-only models.
_NOT_CHAT = re.compile(r"tts|image|banana|lyria|robotics|computer-use|deep-research|antigravity|transcribe|customtools")


def list_models() -> list[str]:
    """Chat models the key can list, cached 1 hour; [] on any failure. No test prompts:
    those spent one request per model of a free daily quota as small as 20."""
    global _models_cache
    if time.time() - _models_cache[0] < 3600 and _models_cache[1]:
        return _models_cache[1]
    if not api_key():
        return []
    try:
        req = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
            headers={"x-goog-api-key": api_key()})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
    except (OSError, ValueError) as e:
        log.warning("Couldn't list Gemini models: %s", e)
        return []
    names = sorted({m["name"].split("/", 1)[1] for m in data.get("models", [])
                    if "generateContent" in m.get("supportedGenerationMethods", [])
                    and not _NOT_CHAT.search(m["name"])})
    _models_cache = (time.time(), names)
    return names


def model_name() -> str:
    return (os.environ.get("JARVIS_GEMINI_MODEL") or "").strip() or DEFAULT_MODEL


# --- request translation -------------------------------------------------------------------
def _system_text(system) -> str:
    if isinstance(system, str):
        return system
    return "\n\n".join(b.get("text", "") for b in (system or []) if isinstance(b, dict) and b.get("text"))


def _result_text(content) -> str:
    if isinstance(content, str):
        return content
    return " ".join(b.get("text", "") for b in (content or []) if isinstance(b, dict))


def convert_messages(messages: list[dict]) -> list[dict]:
    """Anthropic messages -> Gemini contents. tool_use becomes a functionCall part and tool_result
    a functionResponse part (which needs the function *name*, so ids are mapped back to names
    from the assistant turns). Gemini 3 requires the thought signature it attached to a
    function call to be sent back verbatim; convert_response stashes it on the block."""
    id_to_name: dict[str, str] = {}
    contents: list[dict] = []
    for m in messages:
        role = "model" if m.get("role") == "assistant" else "user"
        raw = m.get("content")
        blocks = [{"type": "text", "text": raw}] if isinstance(raw, str) else (raw or [])
        parts: list[dict] = []
        for b in blocks:
            t = b.get("type")
            if t == "text":
                if b.get("text"):
                    part = {"text": b["text"]}
                    if b.get("_thought_signature"):
                        part["thoughtSignature"] = b["_thought_signature"]
                    parts.append(part)
            elif t == "tool_use":
                id_to_name[b.get("id", "")] = b.get("name", "")
                part = {"functionCall": {"name": b.get("name", ""), "args": b.get("input") or {}}}
                if b.get("_thought_signature"):
                    part["thoughtSignature"] = b["_thought_signature"]
                parts.append(part)
            elif t == "tool_result":
                parts.append({"functionResponse": {
                    "name": id_to_name.get(b.get("tool_use_id", ""), "tool"),
                    "response": {"result": _result_text(b.get("content"))},
                }})
            elif t in ("image", "document"):  # Gemini's inlineData takes images and PDFs alike
                src = b.get("source") or {}
                if src.get("type") == "base64":
                    parts.append({"inlineData": {"mimeType": src.get("media_type", "image/png"), "data": src.get("data", "")}})
        if not parts:
            parts = [{"text": " "}]  # Gemini rejects a content with no parts
        contents.append({"role": role, "parts": parts})
    return contents


def convert_tools(tools: list[dict]) -> list[dict]:
    """Anthropic tools -> one Gemini tool with functionDeclarations. Uses parametersJsonSchema
    (standard JSON Schema) so MCP tools' schemas pass through untouched; a tool with no
    properties omits parameters entirely, since Gemini rejects an empty OBJECT schema."""
    decls = []
    for t in tools or []:
        decl: dict = {"name": t["name"], "description": (t.get("description") or t["name"])[:4000]}
        schema = t.get("input_schema") or {}
        if schema.get("properties"):
            decl["parametersJsonSchema"] = {k: v for k, v in schema.items() if k != "$schema"}
        decls.append(decl)
    return [{"functionDeclarations": decls}] if decls else []


def thinking_config(model: str) -> dict | None:
    """Keep Gemini's hidden 'thinking' minimal: those tokens bill (and count against free-tier
    limits) as output, and Jarvis's replies are short spoken answers. JARVIS_GEMINI_THINKING=
    default leaves the model's own default."""
    setting = (os.environ.get("JARVIS_GEMINI_THINKING") or "minimal").strip().lower()
    if setting == "default":
        return None
    if model.startswith("gemini-3"):
        return {"thinkingLevel": "minimal" if setting == "minimal" else setting}
    if model.startswith("gemini-2.5") and "pro" not in model:
        return {"thinkingBudget": 0}
    return None


def to_request(body: dict, model: str, think: bool = True) -> dict:
    req: dict = {"contents": convert_messages(body.get("messages") or [])}
    sys_text = _system_text(body.get("system"))
    if sys_text:
        req["systemInstruction"] = {"parts": [{"text": sys_text}]}
    tools = convert_tools(body.get("tools") or [])
    if tools:
        req["tools"] = tools
        if (body.get("tool_choice") or {}).get("type") == "none":  # answer in words only (agent step limit)
            req["toolConfig"] = {"functionCallingConfig": {"mode": "NONE"}}
    gen: dict = {"maxOutputTokens": int(body.get("max_tokens") or 1024)}
    tc = thinking_config(model) if think else None
    if tc:
        gen["thinkingConfig"] = tc
    req["generationConfig"] = gen
    return req


# --- response translation ------------------------------------------------------------------
def from_response(data: dict, model: str) -> dict:
    """Gemini response -> Anthropic-shaped {content, stop_reason, usage, model}."""
    cands = data.get("candidates") or []
    parts = ((cands[0].get("content") or {}).get("parts") or []) if cands else []
    content: list[dict] = []
    for p in parts:
        if p.get("thought"):
            continue  # a thought summary, not part of the answer
        sig = p.get("thoughtSignature")
        if "functionCall" in p:
            fc = p["functionCall"]
            block = {"type": "tool_use", "id": fc.get("id") or f"gemini_{uuid.uuid4().hex[:12]}",
                     "name": fc.get("name", ""), "input": fc.get("args") or {}}
        elif p.get("text"):
            block = {"type": "text", "text": p["text"]}
        else:
            continue
        if sig:
            block["_thought_signature"] = sig
        content.append(block)
    finish = (cands[0].get("finishReason") if cands else None) or ""
    if any(b["type"] == "tool_use" for b in content):
        stop = "tool_use"
    elif finish == "MAX_TOKENS":
        stop = "max_tokens"
    else:
        stop = "end_turn"
    u = data.get("usageMetadata") or {}
    cached = u.get("cachedContentTokenCount", 0) or 0
    return {
        "content": content,
        "stop_reason": stop,
        "model": model,
        "usage": {
            "input_tokens": max((u.get("promptTokenCount", 0) or 0) - cached, 0),
            "cache_read_input_tokens": cached,
            "cache_creation_input_tokens": 0,  # Gemini's implicit caching has no write charge
            "output_tokens": (u.get("candidatesTokenCount", 0) or 0) + (u.get("thoughtsTokenCount", 0) or 0),
        },
    }


# --- network -------------------------------------------------------------------------------
def retry_delay_s(error_body: str) -> float | None:
    """Seconds from a 429's google.rpc.RetryInfo ("retryDelay": "12s"), if present."""
    m = re.search(r'"retryDelay"\s*:\s*"([\d.]+)s"', error_body or "")
    return float(m.group(1)) if m else None


# --- why a call failed, in words a person can act on ------------------------------------------
# (2026-09-29) Every failure used to end in the same "couldn't reach Gemini". The real cause (quota,
# overload, a rejected key, a blocked connection) is now kept as `last_error_reason()` and spoken.
_last_error: dict = {"reason": "", "ts": 0.0}


def _note_error(reason: str) -> None:
    _last_error["reason"] = reason
    _last_error["ts"] = time.time()


def _clear_error() -> None:
    _last_error["reason"] = ""


def last_error_reason(max_age_s: float = 120.0) -> str:
    """The most recent failure's plain-language reason, or "" if the last call worked / it is stale."""
    if _last_error["reason"] and time.time() - _last_error["ts"] <= max_age_s:
        return _last_error["reason"]
    return ""


def quota_violations(detail: str) -> list[tuple[str, str]]:
    """[(quotaId, quotaValue)] from a 429's google.rpc.QuotaFailure, e.g. ("GenerateRequestsPerDayPerProjectPerModel-FreeTier", "500")."""
    ids = re.findall(r'"quotaId"\s*:\s*"([^"]+)"', detail or "")
    vals = re.findall(r'"quotaValue"\s*:\s*"?(\d+)"?', detail or "")
    return [(q, vals[i] if i < len(vals) else "") for i, q in enumerate(ids)]


def quota_kind(detail: str) -> tuple[str, str]:
    """("day" | "minute" | "", limit) for a 429. A daily limit does not come back by waiting a few seconds."""
    for q, v in quota_violations(detail):
        if "PerDay" in q:
            return "day", v
    for q, v in quota_violations(detail):
        if "PerMinute" in q:
            return "minute", v
    return "", ""


def reason_from_http(code: int, detail: str, model: str) -> str:
    low = (detail or "").lower()
    if code == 429:
        kind, limit = quota_kind(detail)
        if kind == "day":
            return (f"{model} has used up its free daily limit{f' of {limit} requests' if limit else ''}, "
                    "it resets at midnight Pacific time; pick another model or enable billing")
        wait = retry_delay_s(detail)
        if wait is not None and wait <= 120:
            return f"{model} is rate limited, try again in about {int(wait) + 1} seconds"
        return f"the quota for {model} is used up, pick another model in Settings"
    if code in (500, 502, 503, 504):
        return f"Google says {model} is overloaded right now"
    if code == 404:
        return f"{model} isn't available to this API key, pick another model in Settings"
    if code == 401 or (code == 400 and ("api key" in low or "api_key_invalid" in low)):
        return "Google rejected the API key"
    if code == 403:
        return "Google denied access with this API key (permissions, billing or country)"
    if code == 400:
        return f"Google refused the request ({(detail or '').strip()[:80] or 'HTTP 400'})"
    return f"Google returned HTTP {code}"


def reason_from_exception(e: BaseException) -> str:
    text = str(e)
    if "CERTIFICATE_VERIFY_FAILED" in text or "certificate" in text.lower():
        return "the secure connection to Google failed its certificate check (antivirus or a proxy?)"
    if _is_timeout(e):
        return "the request to Google timed out"
    reason = getattr(e, "reason", None)
    name = type(reason if reason is not None else e).__name__
    if isinstance(e, (ConnectionError, socket.gaierror)) or "getaddrinfo" in text or name == "gaierror":
        return "couldn't connect to Google (no internet, DNS or a firewall?)"
    return f"couldn't connect to Google ({name})"


# --- transport: one reusable HTTPS connection instead of a new TLS handshake per round --------
# (2026-09-29, speed pass) urllib opens a fresh connection for every request, which costs a TCP+TLS
# handshake (several round trips) on every one of the up to 12 rounds of a command. A small idle pool
# keeps connections to generativelanguage.googleapis.com open between calls. It is skipped when an
# HTTPS proxy is configured (http.client does not use proxies) or JARVIS_GEMINI_KEEPALIVE=0, in which
# case plain urlopen is used exactly as before.
POOL_IDLE_S = 45.0  # Google closes idle connections after about a minute; stay well under it
_STALE_ERRORS = (ConnectionError, http.client.HTTPException, socket.timeout, TimeoutError, OSError)


def keepalive_enabled() -> bool:
    return (os.environ.get("JARVIS_GEMINI_KEEPALIVE") or "1").strip().lower() not in ("0", "false", "no", "off")


def _proxied(url: str) -> bool:
    try:
        parts = urllib.parse.urlsplit(url)
        proxies = urllib.request.getproxies()
        return bool(proxies.get(parts.scheme)) and not urllib.request.proxy_bypass(parts.hostname or "")
    except Exception:
        return True  # unsure: take the plain urllib path


class _Pool:
    """Idle connections keyed by (scheme, host, port). acquire() hands out one exclusively; release()
    puts a still-healthy one back. Nothing is shared between two requests at the same time."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._idle: dict[tuple, list] = {}
        self.opened = 0  # connections created (tests + diagnostics)
        self.reused = 0

    def acquire(self, scheme: str, host: str, port: int, timeout: float):
        key = (scheme, host, port)
        now = time.monotonic()
        with self._lock:
            lst = self._idle.get(key, [])
            while lst:
                conn, stamp = lst.pop()
                if now - stamp <= POOL_IDLE_S:
                    self.reused += 1
                    return key, conn, True
                try:
                    conn.close()
                except Exception:
                    pass
            self.opened += 1
        cls = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
        return key, cls(host, port, timeout=timeout), False

    def release(self, key: tuple, conn) -> None:
        with self._lock:
            self._idle.setdefault(key, []).append((conn, time.monotonic()))

    def clear(self) -> None:
        with self._lock:
            for lst in self._idle.values():
                for conn, _ in lst:
                    try:
                        conn.close()
                    except Exception:
                        pass
            self._idle.clear()


_pool = _Pool()


def _split(url: str):
    p = urllib.parse.urlsplit(url)
    scheme = p.scheme or "https"
    port = p.port or (443 if scheme == "https" else 80)
    path = (p.path or "/") + (("?" + p.query) if p.query else "")
    return scheme, p.hostname or "", port, path


def _open(req: urllib.request.Request, timeout: float):
    """Sends `req` on a pooled connection; returns (key, conn, response). A reused connection the server
    already closed is replaced once by a fresh one. Raises urllib.error.HTTPError for a non-2xx status."""
    scheme, host, port, path = _split(req.full_url)
    headers = {k: v for k, v in req.header_items()}
    body = req.data
    method = req.get_method()
    last_exc: Exception | None = None
    for attempt in (1, 2):
        key, conn, reused = _pool.acquire(scheme, host, port, timeout)
        try:
            conn.timeout = timeout
            if conn.sock is not None:
                conn.sock.settimeout(timeout)
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
        except _STALE_ERRORS as e:
            try:
                conn.close()
            except Exception:
                pass
            last_exc = e
            if isinstance(e, (socket.timeout, TimeoutError)):
                raise  # slow, not stale: retrying here would only double the wait
            if reused and attempt == 1:
                continue  # a stale idle connection: retry once on a brand-new one
            raise
        if resp.status >= 400:
            data = resp.read()
            try:
                conn.close()
            except Exception:
                pass
            raise urllib.error.HTTPError(req.full_url, resp.status, resp.reason, resp.msg, io.BytesIO(data))
        return key, conn, resp
    raise last_exc or OSError("connection failed")


def _finish(key: tuple, conn, resp) -> None:
    """Return the connection to the pool only if the response was fully read and the server keeps it open."""
    try:
        if resp.isclosed() and not resp.will_close:
            _pool.release(key, conn)
            return
    except Exception:
        pass
    try:
        conn.close()
    except Exception:
        pass


def http_post(req: urllib.request.Request, timeout: float) -> bytes:
    """Drop-in for `urlopen(req).read()` with connection reuse; raises urllib.error.HTTPError like it."""
    if not keepalive_enabled() or _proxied(req.full_url) or not req.full_url.startswith("https:"):
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    key, conn, resp = _open(req, timeout)
    try:
        data = resp.read()
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        raise
    _finish(key, conn, resp)
    return data


def warm() -> bool:
    """Open (and pool) a connection ahead of the first command with a free metadata GET; never raises."""
    key_ = api_key()
    if not key_ or not keepalive_enabled():
        return False
    try:
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_name()}",
            headers={"x-goog-api-key": key_}, method="GET")
        http_post(req, 10)
        return True
    except Exception as e:
        log.debug("Gemini connection warm-up skipped: %s", e)
        return False


# --- timing knobs ---------------------------------------------------------------------------
def _env_float(name: str, default: float) -> float:
    try:
        return float((os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default


def attempt_timeout_s() -> float:
    """Longest one Gemini attempt may take (JARVIS_GEMINI_ATTEMPT_TIMEOUT_S, default 60). The agent loop's
    180 s round cap was written for long Claude documents; a stalled Gemini call used to hold a command for
    that long, up to four times over."""
    return max(5.0, _env_float("JARVIS_GEMINI_ATTEMPT_TIMEOUT_S", 60.0))


def hedge_after_s() -> float:
    """After this many seconds without an answer, the same request is also sent to the backup model
    (JARVIS_GEMINI_FALLBACK_MODEL) and whichever answers first wins. 0 = never race (default 8)."""
    return max(0.0, _env_float("JARVIS_GEMINI_HEDGE_S", 8.0))


def first_token_timeout_s() -> float:
    """Streaming: give up (and fall back to a normal call) if nothing arrives within this long."""
    return max(3.0, _env_float("JARVIS_GEMINI_FIRST_TOKEN_S", 8.0))


def stream_enabled() -> bool:
    return (os.environ.get("JARVIS_GEMINI_STREAM") or "1").strip().lower() not in ("0", "false", "no", "off")


# --- calls ----------------------------------------------------------------------------------
def call(
    body: dict,
    timeout: int,
    http: Callable[[urllib.request.Request, int], bytes],
    max_attempts: int = 4,
    sleep: Callable[[float], None] = time.sleep,
) -> dict | None:
    """Runs one Anthropic-shaped body against Gemini; returns an Anthropic-shaped dict, or None
    on failure (the caller shows its own "couldn't reach" message). Handles free-tier 429s by
    waiting the server-advised delay (capped) instead of failing a multi-step command outright;
    drops thinkingConfig once if the model rejects it.

    Speed (2026-09-29): a stalled call no longer holds the command for minutes. Each attempt is capped
    (attempt_timeout_s), timeouts are retried once rather than four times, and when a backup model is
    configured the same request is raced on it after hedge_after_s seconds - a model call has no side
    effects, so asking twice is safe; the first answer wins."""
    key, model = api_key(), model_name()
    # Escalation (smarter batch): the loop may ask for a stronger Gemini/Gemma model by name. If that
    # model fails, the same request is retried once on the configured model.
    override = str(body.get("model") or "")
    if override.startswith(("gemini-", "gemma-")) and override != model and key:
        result = _call_model(body, timeout, http, key, override, max_attempts=2, sleep=sleep)
        if result is not None:
            return result
        log.warning("Escalation model %s failed; retrying on %s", override, model)
    if not key:
        log.warning("Set GEMINI_API_KEY in .env to use Gemini.")
        _note_error("no Gemini API key is set")
        return None
    backup = fallback_model_name()
    if backup == model:
        backup = ""
    hedge = hedge_after_s()
    backup_tried = False
    swap_on_429 = bool(backup) and backup_on_rate_limit()  # opt-in: a 429 hands over instead of waiting
    if backup and hedge > 0:
        result, code, backup_tried = _hedged(body, timeout, http, key, model, backup, hedge, max_attempts, sleep,
                                             wait_on_429=not swap_on_429)
        _last_fail.code = code
    else:
        result = _call_model(body, timeout, http, key, model, max_attempts=max_attempts, sleep=sleep,
                             wait_on_429=not swap_on_429)
        code = getattr(_last_fail, "code", None)
    if result is None and code == 429 and swap_on_429 and not backup_tried:
        log.warning("Gemini %s is rate limited; trying the backup model %s.", model, backup)
        return _call_model(body, timeout, http, key, backup, max_attempts=2, sleep=sleep)
    if result is None and code in OVERLOAD_CODES and backup and not backup_tried:
        # Opt-in backup for OVERLOAD only (503 "high demand" and other 5xx), never for quota (429): the
        # user chose (2026-09-25) to change models themselves when a daily quota runs out.
        log.warning("Gemini %s is overloaded; trying the backup model %s once", model, backup)
        result = _call_model(body, timeout, http, key, backup, max_attempts=2, sleep=sleep)
    return result


def _hedged(body, timeout, http, key, model, backup, hedge_s, max_attempts, sleep, wait_on_429=True):
    """Primary model now; the backup joins after hedge_s seconds if the primary has not answered.
    Returns (result, last_fail_code, backup_was_started). The slower call is abandoned (daemon thread)."""
    results: queue.Queue = queue.Queue()

    def _run(name: str, mdl: str, attempts: int) -> None:
        r = _call_model(body, timeout, http, key, mdl, max_attempts=attempts, sleep=sleep,
                        wait_on_429=wait_on_429 if name == "primary" else True)
        results.put((name, r, getattr(_last_fail, "code", None)))

    threading.Thread(target=_run, args=("primary", model, max_attempts), daemon=True).start()
    running, started_backup, primary_code = 1, False, None
    while running:
        try:
            name, r, code = results.get(timeout=None if started_backup else hedge_s)
        except queue.Empty:
            log.warning("Gemini %s hasn't answered in %.0fs; racing the backup model %s", model, hedge_s, backup)
            threading.Thread(target=_run, args=("backup", backup, 2), daemon=True).start()
            running += 1
            started_backup = True
            continue
        running -= 1
        if name == "primary":
            primary_code = code
        if r is not None:
            if name == "backup":
                log.info("Gemini backup model %s answered first.", backup)
            return r, code, started_backup
        if name == "primary" and not started_backup:
            # The primary failed outright before the hedge timer: the normal overload fallback handles it.
            return None, primary_code, False
    return None, primary_code, started_backup


OVERLOAD_CODES = (500, 502, 503, 504)
# Waits between tries when Google is overloaded (2026-09-28, found live: 3 tries 1.5 s apart all hit the
# same short 503 spell on gemini-3.1-flash-lite, and the command failed while the next one worked).
OVERLOAD_BACKOFF_S = (2.0, 4.0, 8.0)
_last_fail = threading.local()
MAX_TIMEOUT_ATTEMPTS = 2  # a timed-out call is retried once, not max_attempts times


def backup_on_rate_limit() -> bool:
    """JARVIS_GEMINI_BACKUP_ON_RATE_LIMIT (default off): when the model answers 429 (its own per-minute or daily
    limit) ask the backup model at once instead of waiting or failing. Each model has its own quota (free tier, per
    project: e.g. 500 requests/day on 3.5-flash-lite, 20 on 3.5-flash), so two models add up. Off by default: on 2026-09-25 the user chose to change models
    themselves rather than have quota fall back automatically; this is the explicit opt-in."""
    return (os.environ.get("JARVIS_GEMINI_BACKUP_ON_RATE_LIMIT") or "0").strip().lower() in ("1", "true", "yes", "on")


def fallback_model_name() -> str:
    """JARVIS_GEMINI_FALLBACK_MODEL: tried once when the main model is overloaded (and raced against it
    when it is slow). Empty (default) = off."""
    return (os.environ.get("JARVIS_GEMINI_FALLBACK_MODEL") or "").strip()


def _is_timeout(e: BaseException) -> bool:
    if isinstance(e, (TimeoutError, socket.timeout)):
        return True
    reason = getattr(e, "reason", None)
    return isinstance(e, urllib.error.URLError) and isinstance(reason, (TimeoutError, socket.timeout))


def _call_model(body: dict, timeout: int, http, key: str, model: str, max_attempts: int = 4,
                sleep: Callable[[float], None] = time.sleep, wait_on_429: bool = True) -> dict | None:
    think = True
    _last_fail.code = None
    timeouts = 0
    per_attempt = min(float(timeout), attempt_timeout_s())
    for attempt in range(1, max_attempts + 1):
        payload = json.dumps(to_request(body, model, think)).encode()
        req = urllib.request.Request(
            GEMINI_URL.format(model=model), data=payload, method="POST",
            headers={"x-goog-api-key": key, "content-type": "application/json"},
        )
        try:
            result = from_response(json.loads(http(req, per_attempt)), model)
            _clear_error()
            return result
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode(errors="replace")
            except Exception:
                detail = ""
            log.warning("Gemini request failed (attempt %d): HTTP %d: %s", attempt, e.code, detail[:400])
            _note_error(reason_from_http(e.code, detail, model))
            _last_fail.code = e.code
            if e.code == 400 and think and "thinking" in detail.lower():
                think = False
                continue
            if e.code == 429 and quota_kind(detail)[0] == "day":
                log.warning("Gemini %s has used up its free daily quota (%s); waiting would not help.", model,
                            quota_kind(detail)[1] or "?")
                return None
            if e.code == 429 and not wait_on_429:
                log.warning("Gemini %s hit its rate limit; handing over to the backup model instead of waiting.", model)
                return None
            if e.code == 429 and attempt < max_attempts:
                wait = retry_delay_s(detail)
                if wait is not None and wait <= MAX_RETRY_WAIT_S:
                    sleep(wait + 0.5)
                    continue
                log.warning("Gemini quota exhausted (retry delay %s) — not waiting.", wait)
                return None
            if e.code in OVERLOAD_CODES and attempt < max_attempts:
                sleep(OVERLOAD_BACKOFF_S[min(attempt - 1, len(OVERLOAD_BACKOFF_S) - 1)])
                continue
            return None
        except Exception as e:
            log.warning("Gemini request failed (attempt %d): %s", attempt, e)
            _note_error(reason_from_exception(e))
            if _is_timeout(e):
                timeouts += 1
                if timeouts >= MAX_TIMEOUT_ATTEMPTS:
                    return None
            if attempt == max_attempts:
                return None
            sleep(1.5)
    return None


# --- streaming ------------------------------------------------------------------------------
def _merge_chunks(chunks: list[dict]) -> dict:
    """Streamed GenerateContentResponse chunks -> one response that from_response() understands: parts
    concatenated in order (adjacent plain-text parts joined), last finishReason and usage kept."""
    parts: list[dict] = []
    finish = None
    usage: dict = {}
    for ch in chunks:
        cands = ch.get("candidates") or []
        if cands:
            for p in (cands[0].get("content") or {}).get("parts") or []:
                plain = ("text" in p and not p.get("thought") and not p.get("thoughtSignature")
                         and "functionCall" not in p)
                last = parts[-1] if parts else None
                if plain and last is not None and "text" in last and not last.get("thought") \
                        and not last.get("thoughtSignature") and "functionCall" not in last:
                    last["text"] += p.get("text", "")
                else:
                    parts.append(dict(p))
            finish = cands[0].get("finishReason") or finish
        if ch.get("usageMetadata"):
            usage = ch["usageMetadata"]
    return {"candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": finish}],
            "usageMetadata": usage}


class _HttpFail(Exception):
    def __init__(self, code: int, detail: str) -> None:
        super().__init__(f"HTTP {code}: {detail[:200]}")
        self.code, self.detail = code, detail


def stream_round(body: dict, timeout: float, on_text=None, on_text_done=None, on_first_token=None,
                 opener=None, _retry: bool = True) -> dict | None:
    """One Gemini round trip over streamGenerateContent (SSE). on_text(delta) is called for every piece
    of answer text that arrives BEFORE the first function call of the message (the same rule the Claude
    stream follows: text next to a tool call is narration, spoken as it comes); on_text_done() fires once
    when that leading text ends (a function call appears, or the stream finishes) so a caller can flush a
    held-back fragment; on_first_token() fires when the first part of any kind arrives.

    Returns the same Anthropic-shaped dict `call` returns, or None on any failure so the caller can run
    the ordinary non-streaming call for this round. If the stream breaks AFTER something was already
    handed to on_text, what arrived is returned as the answer instead of None: retrying would speak it
    twice, and a truncated sentence beats repeating the whole reply. Never raises."""
    key = api_key()
    if not key or not stream_enabled():
        return None
    model = model_name()
    override = str(body.get("model") or "")
    if override.startswith(("gemini-", "gemma-")):
        model = override
    url = (GEMINI_URL.format(model=model).replace(":generateContent", ":streamGenerateContent")) + "?alt=sse"
    req = urllib.request.Request(
        url, data=json.dumps(to_request(body, model, True)).encode(), method="POST",
        headers={"x-goog-api-key": key, "content-type": "application/json", "accept": "text/event-stream"})
    lines: queue.Queue = queue.Queue()
    stop = threading.Event()

    def _reader() -> None:
        conn = resp = pkey = None
        clean = False
        try:
            if opener is not None:
                resp = opener(req, timeout)
                for raw in resp:
                    if stop.is_set():
                        break
                    lines.put(raw)
                clean = not stop.is_set()
            elif keepalive_enabled() and not _proxied(url):
                pkey, conn, resp = _open(req, timeout)
                while not stop.is_set():
                    raw = resp.readline()
                    if not raw:
                        break
                    lines.put(raw)
                clean = not stop.is_set()
            else:
                resp = urllib.request.urlopen(req, timeout=timeout)
                for raw in resp:
                    if stop.is_set():
                        break
                    lines.put(raw)
                clean = not stop.is_set()
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode(errors="replace")[:2000]
            except Exception:
                detail = ""
            lines.put(_HttpFail(e.code, detail))
        except Exception as e:
            lines.put(e)
        finally:
            try:
                if conn is not None and clean:
                    _finish(pkey, conn, resp)
                elif conn is not None:
                    conn.close()
                elif resp is not None and hasattr(resp, "close"):
                    resp.close()
            except Exception:
                pass
            lines.put(None)

    threading.Thread(target=_reader, daemon=True).start()

    deadline = time.monotonic() + timeout
    first_wait = first_token_timeout_s()
    chunks: list[dict] = []
    saw_call = False
    text_done = False
    handed_text = False
    first_fired = False
    started = time.monotonic()
    first_at = 0.0

    def _finish_leading_text() -> None:
        nonlocal text_done
        if text_done:
            return
        text_done = True
        if on_text_done is not None:
            try:
                on_text_done()
            except Exception as e:
                log.warning("Gemini stream text-done hook failed: %s", e)

    def _partial_or_none(reason: str):
        stop.set()
        if handed_text and chunks:
            log.warning("Gemini stream broke after speech had started (%s); using what arrived.", reason)
            _finish_leading_text()
            return from_response(_merge_chunks(chunks), model)
        log.warning("Gemini stream failed (%s); falling back to a normal call.", reason)
        return None

    try:
        while True:
            budget = deadline - time.monotonic()
            if budget <= 0:
                return _partial_or_none("timed out")
            wait = min(budget, first_wait if not first_fired else max(first_wait, 15.0))
            try:
                item = lines.get(timeout=wait)
            except queue.Empty:
                return _partial_or_none("no data for %.0fs" % wait)
            if item is None:
                break
            if (isinstance(item, _HttpFail) and item.code == 429 and _retry and not handed_text
                    and quota_kind(item.detail)[0] != "day"  # a daily limit does not clear in seconds
                    and not (backup_on_rate_limit() and fallback_model_name())):  # opted in: hand over, don't wait
                # A per-minute limit: Google says how long. Wait it out and try the stream once more instead of
                # spending a second request on the fallback path.
                delay = retry_delay_s(item.detail)
                if delay is not None and delay <= MAX_RETRY_WAIT_S and delay + 0.5 < budget:
                    stop.set()
                    _note_error(reason_from_http(429, item.detail, model))
                    log.warning("Gemini rate limit on the stream; waiting %.0fs and retrying once.", delay)
                    time.sleep(delay + 0.5)
                    return stream_round(body, max(5.0, budget - delay - 0.5), on_text, on_text_done, on_first_token,
                                        opener, _retry=False)
            if isinstance(item, Exception):
                if isinstance(item, _HttpFail):
                    _note_error(reason_from_http(item.code, item.detail, model))
                return _partial_or_none(str(item)[:200])
            line = item.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            try:
                chunk = json.loads(line[5:].strip())
            except ValueError:
                continue
            if chunk.get("error"):
                return _partial_or_none("error event " + str(chunk["error"])[:150])
            chunks.append(chunk)
            parts = ((chunk.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
            if parts and not first_fired:
                first_fired = True
                first_at = time.monotonic() - started
                if on_first_token is not None:
                    try:
                        on_first_token()
                    except Exception as e:
                        log.debug("on_first_token failed (harmless): %s", e)
            for p in parts:
                if "functionCall" in p:
                    saw_call = True
                    _finish_leading_text()
                elif p.get("text") and not p.get("thought") and not saw_call and not text_done:
                    handed_text = True
                    if on_text is not None:
                        try:
                            on_text(p["text"])
                        except Exception as e:
                            log.warning("Gemini stream text hook failed: %s", e)
    except Exception as e:  # defensive: never let a hook bug escape into the agent loop
        return _partial_or_none(repr(e)[:200])
    finally:
        stop.set()
    _finish_leading_text()
    if not chunks:
        log.warning("Gemini stream returned no data; falling back to a normal call.")
        return None
    result = from_response(_merge_chunks(chunks), model)
    log.debug("Gemini stream: first data after %.2fs, complete in %.2fs.", first_at, time.monotonic() - started)
    return result


# --- "why can't Jarvis reach Gemini?" ---------------------------------------------------------
def _env_file_values(path: Path) -> dict[str, str]:
    """KEY=value lines of a .env file (no quotes handling beyond stripping); never raises."""
    out: dict[str, str] = {}
    try:
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip().removeprefix("export ").strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    return out


def _mask(value: str) -> str:
    return f"{value[:4]}...{value[-4:]} ({len(value)} characters)" if len(value) > 8 else "(too short to be a key)"


def diagnose(env_path: Path | None = None, out=print) -> list[str]:
    """Checks, step by step, everything between Jarvis and Gemini and prints what it finds. Sends two tiny
    requests to the configured model, one over Jarvis's own transport and one over plain urllib, so a
    problem in either shows up. Never prints the full key. Returns the list of problems found."""
    problems: list[str] = []
    env_path = Path(env_path) if env_path else Path(__file__).resolve().parent / ".env"
    file_vals = _env_file_values(env_path)
    out(f"Jarvis Gemini check  (folder: {env_path.parent})")

    # 1. the key
    out("\n1. API key")
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        proc = (os.environ.get(name) or "").strip()
        filev = (file_vals.get(name) or "").strip()
        if proc or filev:
            out(f"   {name}: environment={_mask(proc) if proc else 'not set'} | .env file={_mask(filev) if filev else 'not set'}")
            if proc and filev and proc != filev:
                problems.append(f"{name} in the Windows environment differs from the one in .env; Jarvis keeps the "
                                "Windows one. Remove that Windows environment variable (or make them match).")
    key = api_key()
    if not key:
        key = (file_vals.get("GEMINI_API_KEY") or file_vals.get("GOOGLE_API_KEY") or "").strip()
        if key:
            os.environ["GEMINI_API_KEY"] = key  # what Jarvis's own startup does with .env
    if not key:
        problems.append("No Gemini key found (environment or .env). Add GEMINI_API_KEY=... to .env and restart Jarvis.")
        out("   NO KEY FOUND")
        for pr in problems:
            out("\nPROBLEM: " + pr)
        return problems
    out(f"   using: {_mask(key)}" + ("" if key.startswith(("AIza", "AQ.")) else "   <- unusual key shape"))

    # 2. the model
    out("\n2. Model")
    env_model = (os.environ.get("JARVIS_GEMINI_MODEL") or "").strip()
    file_model = (file_vals.get("JARVIS_GEMINI_MODEL") or "").strip()
    model = env_model or file_model or DEFAULT_MODEL
    if not env_model and file_model:
        os.environ["JARVIS_GEMINI_MODEL"] = file_model
    out(f"   using: {model}   (environment={env_model or 'not set'} | .env={file_model or 'not set'})")
    if env_model and file_model and env_model != file_model:
        problems.append(f"JARVIS_GEMINI_MODEL is {env_model} in the environment but {file_model} in .env; "
                        "the environment one wins until Jarvis restarts.")
    backup = fallback_model_name() or (file_vals.get("JARVIS_GEMINI_FALLBACK_MODEL") or "")
    out(f"   backup model: {backup or 'none set'}")

    # 3. connection settings
    out("\n3. Connection")
    proxies = {k: v for k, v in os.environ.items() if k.lower() in ("https_proxy", "http_proxy", "all_proxy")}
    out(f"   proxy variables: {', '.join(proxies) or 'none'}   |   connection reuse: "
        + ("off (proxy or switched off)" if (not keepalive_enabled() or _proxied('https://generativelanguage.googleapis.com/')) else "on"))

    # 4. can the key list models?
    out("\n4. Key check (lists the models this key can use)")
    listed: list[str] = []
    try:
        req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                                     headers={"x-goog-api-key": key})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
        listed = [m["name"].split("/", 1)[1] for m in data.get("models", [])
                  if "generateContent" in m.get("supportedGenerationMethods", [])]
        out(f"   OK in {time.time() - t0:.1f}s: {len(listed)} usable models")
        if model not in listed:
            problems.append(f"{model} is not in this key's model list; pick one from Settings.")
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode(errors="replace")
        except Exception:
            detail = ""
        reason = reason_from_http(e.code, detail, model)
        out(f"   FAILED: HTTP {e.code}: {reason}")
        problems.append(reason)
    except Exception as e:
        reason = reason_from_exception(e)
        out(f"   FAILED: {reason}  [{type(e).__name__}: {str(e)[:120]}]")
        problems.append(reason)

    # 5. a real request, two ways
    out(f"\n5. Test request to {model}")
    body = {"max_tokens": 60, "system": "Be brief.", "messages": [{"role": "user", "content": "Say hi in three words."}]}
    url = GEMINI_URL.format(model=model)
    payload = json.dumps(to_request(body, model, True)).encode()

    def _try(label: str, fn) -> None:
        req = urllib.request.Request(url, data=payload, method="POST",
                                     headers={"x-goog-api-key": key, "content-type": "application/json"})
        t0 = time.time()
        try:
            data = json.loads(fn(req, 30))
            text = "".join(p.get("text", "") for p in (data.get("candidates") or [{}])[0].get("content", {}).get("parts", []))
            out(f"   {label}: OK in {time.time() - t0:.2f}s -> {text.strip()[:40]!r}")
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode(errors="replace")
            except Exception:
                detail = ""
            reason = reason_from_http(e.code, detail, model)
            out(f"   {label}: FAILED HTTP {e.code}: {reason}")
            for q, v in quota_violations(detail):
                out(f"      limit hit: {q}" + (f" (allows {v})" if v else ""))
            out(f"      Google said: {detail.strip()[:220]}")
            problems.append(f"{label}: {reason}")
        except Exception as e:
            reason = reason_from_exception(e)
            out(f"   {label}: FAILED: {reason}  [{type(e).__name__}: {str(e)[:120]}]")
            problems.append(f"{label}: {reason}")

    def _plain(req, timeout):
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()

    _try("plain urllib   ", _plain)
    _try("Jarvis transport", http_post)
    started, first = time.time(), []
    res = stream_round(body, 30, on_text=lambda d: first.append(time.time() - started))
    out("   streaming      : " + (f"OK, first words after {first[0]:.2f}s" if res is not None and first
                                  else "did not stream (Jarvis then falls back to a normal request)"))

    out("\nRESULT")
    if problems:
        for pr in dict.fromkeys(problems):
            out("   PROBLEM: " + pr)
    else:
        out("   Everything works from here. If Jarvis still says it can't reach Gemini, restart Jarvis (so it "
            "reloads this code and .env) and read jarvis_standalone.log for the line starting 'Gemini request failed'.")
    return problems


if __name__ == "__main__":
    diagnose()

