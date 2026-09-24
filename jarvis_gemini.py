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

import json
import logging
import os
import re
import time
import urllib.error
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
# until the reset. Default is back to 3.1-flash-lite (confirmed working live), and a daily-quota
# 429 now moves on to the next model in FALLBACK_MODELS (free-tier quotas are per model).
DEFAULT_MODEL = "gemini-3.1-flash-lite"
FALLBACK_MODELS = ("gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-2.5-flash-lite")
_exhausted: dict[str, str] = {}  # model -> date its daily quota ran out (in memory, per run)
PROVIDERS = ("claude", "gemini")
MAX_RETRY_WAIT_S = 30.0  # longest 429 "retry after" Jarvis will sit through mid-command


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


def _next_model(current: str) -> str | None:
    """First model not out of daily quota today, after marking `current` exhausted."""
    today = time.strftime("%Y-%m-%d")
    _exhausted[current] = today
    for m in (model_name(),) + FALLBACK_MODELS:
        if _exhausted.get(m) != today:
            return m
    return None


def call(
    body: dict,
    timeout: int,
    http: Callable[[urllib.request.Request, int], bytes],
    max_attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> dict | None:
    """Runs one Anthropic-shaped body against Gemini; returns an Anthropic-shaped dict, or None
    on failure (the caller shows its own "couldn't reach" message). Handles free-tier 429s by
    waiting the server-advised delay (capped) instead of failing a multi-step command outright;
    drops thinkingConfig once if the model rejects it."""
    key, model = api_key(), model_name()
    today = time.strftime("%Y-%m-%d")
    if _exhausted.get(model) == today:
        model = next((m for m in FALLBACK_MODELS if _exhausted.get(m) != today), model)
    if not key:
        log.warning("Set GEMINI_API_KEY in .env to use Gemini.")
        return None
    think = True
    for attempt in range(1, max_attempts + 1):
        payload = json.dumps(to_request(body, model, think)).encode()
        req = urllib.request.Request(
            GEMINI_URL.format(model=model), data=payload, method="POST",
            headers={"x-goog-api-key": key, "content-type": "application/json"},
        )
        try:
            return from_response(json.loads(http(req, timeout)), model)
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode(errors="replace")
            except Exception:
                detail = ""
            log.warning("Gemini request failed (attempt %d): HTTP %d: %s", attempt, e.code, detail[:400])
            if e.code == 400 and think and "thinking" in detail.lower():
                think = False
                continue
            if e.code == 429 and "PerDay" in detail:
                nxt = _next_model(model)
                if nxt:
                    log.warning("Gemini %s daily quota used up, switching to %s.", model, nxt)
                    model = nxt
                    continue
            if e.code == 429 and attempt < max_attempts:
                wait = retry_delay_s(detail)
                if wait is not None and wait <= MAX_RETRY_WAIT_S:
                    sleep(wait + 0.5)
                    continue
                log.warning("Gemini quota exhausted (retry delay %s) — not waiting.", wait)
                return None
            if e.code in (500, 502, 503, 504) and attempt < max_attempts:
                sleep(1.5)
                continue
            return None
        except Exception as e:
            log.warning("Gemini request failed (attempt %d): %s", attempt, e)
            if attempt == max_attempts:
                return None
            sleep(1.5)
    return None
