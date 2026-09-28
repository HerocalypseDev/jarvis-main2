"""Eval runner (smarter batch, 2026-09-28): replays commands that went wrong in real use against a real
model, and scores whether Jarvis now picks the right tool and doesn't claim things it didn't do.

    python jarvis_eval.py                          # the active brain
    python jarvis_eval.py --provider gemini --model gemini-3.6-flash
    python jarvis_eval.py --case shutdown-must-stage --verbose

SAFETY: no tool ever really runs. `_execute_tool_impl` is replaced by a recorder that returns a canned
"ok" result, so "shut down my computer" or "delete everything in Documents" only records the call the
model *would* make. It uses a throwaway memory DB, no history, no speech, no reply cache, no lessons.
It does make real model calls (a few cents per full run on Claude; free-tier quota on Gemini).

Case fields (evals/cases.json): say, expect_any [{tool, input_re?}] (at least one must be called),
forbid [{tool, input_re?}] (none may be called), reply_not_re / reply_re (checks on the final reply).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

CASES = Path(__file__).with_name("evals") / "cases.json"
RESULTS = Path(__file__).with_name("evals") / "results"


def _matches(call: tuple[str, dict], rule: dict) -> bool:
    name, inp = call
    if rule.get("tool") and name != rule["tool"]:
        return False
    if rule.get("input_re") and not re.search(rule["input_re"], json.dumps(inp), re.I):
        return False
    return True


def score(case: dict, calls: list[tuple[str, dict]], reply: str) -> list[str]:
    """The reasons this case failed (empty = passed). Pure, so it is unit-tested without a model."""
    problems = []
    if case.get("expect_any") and not any(_matches(c, r) for c in calls for r in case["expect_any"]):
        want = " or ".join(r["tool"] + (f"~/{r['input_re']}/" if r.get("input_re") else "") for r in case["expect_any"])
        problems.append(f"expected a call to {want}; got {[c[0] for c in calls] or 'no tool calls'}")
    for rule in case.get("forbid", []):
        if any(_matches(c, rule) for c in calls):
            problems.append(f"called forbidden tool {rule['tool']}")
    if case.get("reply_not_re") and re.search(case["reply_not_re"], reply or "", re.I):
        problems.append(f"reply matched /{case['reply_not_re']}/: {reply[:120]!r}")
    if case.get("reply_re") and not re.search(case["reply_re"], reply or "", re.I):
        problems.append(f"reply did not match /{case['reply_re']}/")
    return problems


def run(cases: list[dict], verbose: bool = False, delay: float = 0.0) -> dict:
    os.environ["JARVIS_MEMORY_DB_PATH"] = str(Path(tempfile.mkdtemp()) / "eval.db")
    os.environ["JARVIS_LLM_TTS_STREAM"] = "0"
    os.environ["JARVIS_LESSONS"] = "0"
    import jarvis

    calls: list[tuple[str, dict]] = []

    def recorder(name, inp, *a, **k):
        calls.append((name, dict(inp or {})))
        return f"OK: {name} done (eval stub, nothing was really run)."

    jarvis._execute_tool_impl = recorder
    jarvis._tool_result_cache.clear()
    jarvis.cache.enabled = lambda layer: False  # no tool/reply cache: every call reaches the recorder
    jarvis.get_mcp_tool_schemas = lambda: []   # never start MCP servers from an eval
    jarvis.LLM_SETTINGS_PATH = Path(tempfile.mkdtemp()) / "llm_provider.json"  # --provider wins over the saved switch
    jarvis._append_history = lambda *a, **k: None
    jarvis._history_snapshot = lambda: []
    jarvis._log_action_audit = lambda *a, **k: None
    jarvis._spawn_lesson = lambda *a: None
    jarvis.speak_text = lambda *a, **k: None
    jarvis._current_command_source = lambda: "text"
    out = {"provider": jarvis._llm_provider(), "model": (jarvis.gemini.model_name() if jarvis._llm_provider() == "gemini"
                                                         else jarvis.CLAUDE_MODEL), "cases": []}
    for case in cases:
        calls.clear()
        jarvis._reply_cache.clear()
        t0 = time.time()
        try:
            reply = jarvis.run_agent_loop(case["say"], record_history=False)
        except Exception as e:
            reply = f"(crashed: {e})"
        unreachable = reply.strip() in (jarvis._llm_unavailable_reply(), jarvis.CLAUDE_UNAVAILABLE_REPLY) and not calls
        problems = ["model unreachable (quota/overload), not scored"] if unreachable else score(case, list(calls), reply)
        row = {"id": case["id"], "pass": not problems, "error": unreachable, "problems": problems,
               "tools": [c[0] for c in calls], "reply": reply[:300], "seconds": round(time.time() - t0, 1)}
        out["cases"].append(row)
        mark = "ERR " if unreachable else ("PASS" if not problems else "FAIL")
        print(f"{mark}  {case['id']:<34} {row['seconds']:>5}s  {'; '.join(problems)}")
        if verbose:
            print(f"      tools={row['tools']}  reply={reply[:160]!r}")
        if delay:
            time.sleep(delay)
    scored = [r for r in out["cases"] if not r["error"]]
    out["passed"] = sum(r["pass"] for r in scored)
    out["errors"] = len(out["cases"]) - len(scored)
    print(f"\n{out['passed']}/{len(scored)} passed on {out['provider']} ({out['model']})"
          + (f", {out['errors']} not scored (model unreachable)" if out["errors"] else ""))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--provider", choices=["claude", "gemini"])
    ap.add_argument("--model", help="model name for that provider")
    ap.add_argument("--case", action="append", help="run only these case ids")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--delay", type=float, default=0.0,
                    help="seconds to wait between cases (free Gemini tiers allow ~5-15 requests a minute)")
    args = ap.parse_args(argv)
    if args.provider:
        os.environ["JARVIS_LLM_PROVIDER"] = args.provider
    if args.model:
        os.environ["JARVIS_GEMINI_MODEL" if (args.provider or "") == "gemini" else "CLAUDE_MODEL"] = args.model
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    if args.case:
        cases = [c for c in cases if c["id"] in set(args.case)]
    result = run(cases, args.verbose, args.delay)
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{time.strftime('%Y%m%d-%H%M%S')}-{result['provider']}-{result['model']}.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"saved {path}")
    return 0 if result["passed"] == len(result["cases"]) - result["errors"] and not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
