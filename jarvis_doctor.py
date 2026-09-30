"""Jarvis doctor (2026-09-30): the quiet failures, found before the owner runs into them.

    python jarvis_doctor.py            # prints every check with the exact fix

Local and fast: no model call, no network except when a check says so. `run_checks()` returns
[{"name", "status": "ok"|"warn"|"fail", "detail", "fix"}] and is also used by the self-check voice report and the
dashboard's Home health card, so the same problems show up wherever the owner looks.

What it adds over the live self-check: Google sign-ins that are about to expire, Everything not set up,
missing packages for switched-on features, brain keys, the last eval result, and which tools keep needing
argument repairs.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "doctor_state.json"
GOOGLE_LOGIN_WARN_DAYS = 6  # a Google Cloud app in "Testing" status ends a sign-in about 7 days after consent
EVAL_RESULTS = ROOT / "evals" / "results"


def _check(name: str, status: str, detail: str, fix: str = "") -> dict:
    return {"name": name, "status": status, "detail": detail, "fix": fix}


def _load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    try:
        STATE_PATH.write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


def _google_token_paths(server: str) -> list[Path]:
    home = Path.home()
    if server == "gmail":
        return [Path(os.environ["GMAIL_CREDENTIALS_PATH"])] if os.environ.get("GMAIL_CREDENTIALS_PATH") else \
            [home / ".gmail-mcp" / "credentials.json"]
    env = (os.environ.get("GOOGLE_CALENDAR_MCP_TOKEN_PATH") or "").strip()
    return ([Path(env)] if env else []) + [home / ".config" / "google-calendar-mcp" / "tokens.json"]


def _refresh_token(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if isinstance(data, dict):
        if data.get("refresh_token"):
            return str(data["refresh_token"])
        for v in data.values():  # newer calendar server: {"normal": {"refresh_token": ...}}
            if isinstance(v, dict) and v.get("refresh_token"):
                return str(v["refresh_token"])
    return ""


REAUTH = {"gmail": "npx.cmd @gongrzhe/server-gmail-autoauth-mcp auth",
          "calendar": "npx.cmd @cocal/google-calendar-mcp auth"}


def google_login_checks(now: float | None = None, state: dict | None = None) -> list[dict]:
    """Warns before a Google sign-in expires. The refresh token itself never changes until the owner signs in
    again, so the day its fingerprint was first seen is the day of the last sign-in (only a hash is kept)."""
    now = now if now is not None else time.time()
    st = state if state is not None else _load_state()
    before = json.dumps(st, sort_keys=True)
    seen = st.setdefault("google_login", {})
    out = []
    for server in ("gmail", "calendar"):
        token = next((t for p in _google_token_paths(server) if (t := _refresh_token(p))), "")
        if not token:
            continue  # not set up on this PC: nothing to warn about
        fp = hashlib.sha256(token.encode()).hexdigest()[:16]
        rec = seen.get(server)
        if not rec or rec.get("fp") != fp:
            rec = {"fp": fp, "first_seen": now}
            seen[server] = rec
        age_days = (now - rec["first_seen"]) / 86400
        if age_days >= GOOGLE_LOGIN_WARN_DAYS:
            out.append(_check(f"{server.title()} sign-in", "warn",
                              f"signed in {age_days:.0f} days ago; if your Google Cloud app is still in 'Testing' "
                              "status, Google ends the sign-in after about 7 days",
                              f"Run `{REAUTH[server]}`, and publish the app (OAuth consent screen > Publish app) "
                              "so it stops expiring"))
        else:
            out.append(_check(f"{server.title()} sign-in", "ok", f"signed in {age_days:.0f} days ago"))
    if state is None and json.dumps(st, sort_keys=True) != before:
        _save_state(st)
    return out


def _has(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _last_eval() -> dict | None:
    try:
        files = sorted(EVAL_RESULTS.glob("*.json"))
        if not files:
            return None
        data = json.loads(files[-1].read_text(encoding="utf-8"))
        data["_age_days"] = (time.time() - files[-1].stat().st_mtime) / 86400
        return data
    except (OSError, ValueError):
        return None


def run_checks(env: dict | None = None) -> list[dict]:
    env = os.environ if env is None else env
    out: list[dict] = []

    # brain keys
    provider = (env.get("JARVIS_LLM_PROVIDER") or "").strip().lower()
    try:
        saved = json.loads((ROOT / "llm_provider.json").read_text(encoding="utf-8")).get("provider")
        provider = provider or str(saved or "").lower()
    except (OSError, ValueError, AttributeError):
        pass
    provider = provider or "claude"
    has_gemini = bool((env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY") or "").strip())
    has_claude = bool((env.get("ANTHROPIC_API_KEY") or "").strip())
    if provider == "gemini" and not has_gemini:
        out.append(_check("Brain key", "fail", "Gemini is the brain but GEMINI_API_KEY is not set",
                          "Put GEMINI_API_KEY=... in .env (Settings) and restart"))
    elif provider == "claude" and not has_claude:
        out.append(_check("Brain key", "fail", "Claude is the brain but ANTHROPIC_API_KEY is not set",
                          "Set ANTHROPIC_API_KEY, or switch the brain to Gemini in the dashboard"))
    else:
        out.append(_check("Brain key", "ok", f"{provider} key is set"))

    if not (ROOT / ".env").exists():
        out.append(_check(".env file", "warn", "no .env next to jarvis.py, so no settings or keys are saved",
                          "Create it from .env.example"))

    # Everything (file search)
    try:
        import jarvis_everything
        if jarvis_everything.reachable():
            out.append(_check("File search (Everything)", "ok", "answering"))
        else:
            out.append(_check("File search (Everything)", "warn",
                              "the Everything app isn't answering, so 'find a file' falls back to a slow folder scan",
                              "Start Everything, then Tools > Options > HTTP Server > Enable, port 80, "
                              "bind 127.0.0.1"))
    except Exception:
        pass

    # packages for switched-on features
    need = [("numpy", "voice"), ("sounddevice", "microphone and speakers"), ("websocket", "streaming speech")]
    if (env.get("JARVIS_WAKE_WORD") or "").strip().lower() in ("1", "true", "yes", "on"):
        need.append(("openwakeword", "the 'Hey Jarvis' wake word"))
    missing = [f"{mod} ({why})" for mod, why in need if not _has(mod)]
    if missing:
        out.append(_check("Python packages", "fail" if any("wake" not in m for m in missing) else "warn",
                          "missing: " + ", ".join(missing), "pip install -r requirements.txt"))
    else:
        out.append(_check("Python packages", "ok", "all present"))

    out += google_login_checks()

    ev = _last_eval()
    if ev:
        total = len(ev.get("cases", [])) - ev.get("errors", 0)
        passed = ev.get("passed", 0)
        status = "ok" if passed == total else "warn"
        out.append(_check("Regression evals", status, f"{passed}/{total} passed, {ev['_age_days']:.0f} day(s) ago "
                          f"on {ev.get('model', '?')}",
                          "" if status == "ok" else "python jarvis_eval.py --verbose (see which cases fail)"))
    try:
        import jarvis_toolargs
        line = jarvis_toolargs.summary()
        if not line.startswith("no "):
            out.append(_check("Tool arguments", "warn", line,
                              "The model keeps sending these tools wrong parameter names: sharpen their descriptions"))
    except Exception:
        pass
    return out


def problems(checks: list[dict] | None = None) -> list[dict]:
    return [c for c in (checks if checks is not None else run_checks()) if c["status"] != "ok"]


def speech(checks: list[dict] | None = None) -> str:
    """One or two spoken sentences for the self-check, empty when nothing needs attention."""
    bad = problems(checks)
    if not bad:
        return ""
    return " ".join(f"{c['name']}: {c['detail']}." + (f" Fix: {c['fix']}." if c["fix"] else "") for c in bad[:3])


def main() -> int:
    checks = run_checks()
    width = max(len(c["name"]) for c in checks)
    mark = {"ok": "OK  ", "warn": "WARN", "fail": "FAIL"}
    for c in checks:
        print(f"{mark[c['status']]}  {c['name']:<{width}}  {c['detail']}")
        if c["fix"] and c["status"] != "ok":
            print(f"      fix: {c['fix']}")
    bad = problems(checks)
    print(f"\n{len(checks) - len(bad)} of {len(checks)} checks fine." + (" Fix the lines above." if bad else ""))
    return 1 if any(c["status"] == "fail" for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
