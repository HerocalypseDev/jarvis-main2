"""Local brain through Ollama (smarter batch, 2026-09-28): the private option.

With `set_llm_provider("ollama")` (or JARVIS_LLM_PROVIDER=ollama) every model call goes to an Ollama server
on this PC or the home network instead of Anthropic/Google, so commands, mail, screen text and memory never
leave the network. Like jarvis_gemini, the rest of Jarvis still builds Anthropic-shaped requests;
`call()` translates them to Ollama's /api/chat (tools = OpenAI-style function specs) and the reply back.

- Server: JARVIS_OLLAMA_URL (default http://127.0.0.1:11434). Only loopback or private-network hosts are
  accepted: a public host would defeat the point (data would leave the network), so it is refused.
- Model: JARVIS_OLLAMA_MODEL (default qwen3:8b, a small model with reliable tool calling). It must be pulled
  first: `ollama pull qwen3:8b`. Bigger = smarter and slower; the Settings page lets you change it.
- Never fails over to a cloud brain: if the local model is down the command fails, by design.
- No prompt caching and no image support on most local models (images are dropped with a note).
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import socket
import urllib.parse
import urllib.request
import uuid
from typing import Callable

log = logging.getLogger("jarvis.ollama")

DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:8b"


def base_url() -> str:
    return (os.environ.get("JARVIS_OLLAMA_URL") or DEFAULT_URL).strip().rstrip("/")


def model_name() -> str:
    return (os.environ.get("JARVIS_OLLAMA_MODEL") or DEFAULT_MODEL).strip()


def host_problem(url: str | None = None) -> str | None:
    """Why this server URL is not acceptable (None = fine): must be http(s) on a loopback/private host."""
    parsed = urllib.parse.urlparse(url or base_url())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "JARVIS_OLLAMA_URL must look like http://127.0.0.1:11434"
    try:
        addrs = {ai[4][0] for ai in socket.getaddrinfo(parsed.hostname, parsed.port or 80)}
    except OSError:
        return f"can't resolve {parsed.hostname}"
    for a in addrs:
        ip = ipaddress.ip_address(a.split("%")[0])
        if not (ip.is_loopback or ip.is_private or ip.is_link_local):
            return f"{parsed.hostname} is a public address; the local brain must stay on this PC or the home network"
    return None


def _default_http(req: urllib.request.Request, timeout: float) -> bytes:
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def available(http=None) -> str | None:
    """None if the server answers and the model is pulled, else a plain-language problem."""
    problem = host_problem()
    if problem:
        return problem
    http = http or _default_http
    try:
        tags = json.loads(http(urllib.request.Request(base_url() + "/api/tags"), 5))
    except Exception as e:
        return f"Ollama isn't running at {base_url()} ({type(e).__name__}). Install it from ollama.com and start it."
    names = {m.get("name", "") for m in tags.get("models", [])} | {m.get("model", "") for m in tags.get("models", [])}
    want = model_name()
    if want not in names and f"{want}:latest" not in names:
        return f"the model {want} isn't downloaded yet: run `ollama pull {want}`"
    return None


# --- translation ----------------------------------------------------------------------------------
def _system_text(system) -> str:
    if isinstance(system, str):
        return system
    return "\n\n".join(b.get("text", "") for b in (system or []) if isinstance(b, dict) and b.get("text"))


def to_request(body: dict, model: str) -> dict:
    msgs: list[dict] = []
    sys_text = _system_text(body.get("system"))
    if sys_text:
        msgs.append({"role": "system", "content": sys_text})
    id_to_name: dict[str, str] = {}
    for m in body.get("messages", []):
        role, content = m.get("role"), m.get("content")
        if isinstance(content, str):
            msgs.append({"role": role, "content": content})
            continue
        texts, calls, images = [], [], []
        for b in content or []:
            t = b.get("type")
            if t == "text":
                texts.append(b.get("text", ""))
            elif t == "image":
                images.append((b.get("source") or {}).get("data", ""))
            elif t == "tool_use":
                id_to_name[b.get("id", "")] = b.get("name", "")
                calls.append({"function": {"name": b.get("name", ""), "arguments": b.get("input") or {}}})
            elif t == "tool_result":
                res = b.get("content")
                if isinstance(res, list):
                    res = " ".join(x.get("text", "") for x in res if isinstance(x, dict))
                msgs.append({"role": "tool", "content": str(res or ""), "tool_name": id_to_name.get(b.get("tool_use_id", ""), "")})
        if texts or calls or images:
            msg: dict = {"role": role, "content": "\n".join(texts)}
            if calls:
                msg["tool_calls"] = calls
            if images:
                msg["images"] = [i for i in images if i]
            msgs.append(msg)
    req: dict = {"model": model, "messages": msgs, "stream": False,
                 "options": {"num_predict": int(body.get("max_tokens") or 1024)}}
    tools = [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                               "parameters": t.get("input_schema") or {"type": "object", "properties": {}}}}
             for t in body.get("tools") or [] if t.get("name")]
    if tools:
        req["tools"] = tools
    return req


def from_response(data: dict, model: str) -> dict:
    msg = data.get("message") or {}
    content: list[dict] = []
    text = (msg.get("content") or "").strip()
    # Reasoning models (qwen3 etc.) may wrap their thinking in <think> tags; never speak it.
    if "<think>" in text:
        text = text.split("</think>")[-1].strip()
    if text:
        content.append({"type": "text", "text": text})
    for n, call in enumerate(msg.get("tool_calls") or []):
        fn = call.get("function") or {}
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        content.append({"type": "tool_use", "id": f"ollama_{n}_{uuid.uuid4().hex[:10]}",
                        "name": fn.get("name", ""), "input": args or {}})
    stop = "tool_use" if any(b["type"] == "tool_use" for b in content) else (
        "max_tokens" if data.get("done_reason") == "length" else "end_turn")
    return {"model": model, "content": content, "stop_reason": stop,
            "usage": {"input_tokens": int(data.get("prompt_eval_count") or 0),
                      "output_tokens": int(data.get("eval_count") or 0)}}


def call(body: dict, timeout: int, http: Callable | None = None) -> dict | None:
    """One Anthropic-shaped request against the local model; None on failure (never a cloud fallback)."""
    problem = host_problem()
    if problem:
        log.warning("Local brain refused: %s", problem)
        return None
    http = http or _default_http
    model = model_name()
    payload = json.dumps(to_request(body, model)).encode()
    req = urllib.request.Request(base_url() + "/api/chat", data=payload, method="POST",
                                 headers={"content-type": "application/json"})
    try:
        # Local models are slower than cloud ones; give them at least 2 minutes per round trip.
        return from_response(json.loads(http(req, max(timeout, 120))), model)
    except Exception as e:
        log.warning("Local brain (Ollama %s) request failed: %s", model, e)
        return None
