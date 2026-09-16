# Background task delegation — plan (draft, not built yet)

## What you asked for

Give Jarvis a complex job (write code, debug code, websearch-and-summarize-to-a-file)
and keep talking to Jarvis about other things while it runs. The background job
reports back to Jarvis when done, and Jarvis gives you a quick spoken/toast rundown
instead of you having to go check on it.

## Answer up front: don't add n8n or Hermes — extend what's already in `jarvis.py`

You're most of the way there already:

- `delegate_to_claude_code` (`jarvis.py:3791`, `_delegate_to_claude_code`) already shells
  out to a full headless Claude Code agent (`claude -p ... --output-format json
  --dangerously-skip-permissions`), authenticated via your Pro/Max login, not a metered
  API key (see the comment at `jarvis.py:3809-3814` — this was deliberately switched off
  `ANTHROPIC_API_KEY` billing already). **Its only problem is that `subprocess.run(...)`
  blocks** — Jarvis can't do anything else until that one task finishes.
- Every voice/text command already dispatches on its own thread
  (`handle_voice_command`, per README) — Jarvis isn't single-threaded today, it just
  has no *tracked, reportable* background work yet.
- A scheduler thread already exists and ticks every 60s (`_scheduler_loop`,
  `jarvis.py:2264`, `SCHEDULER_TICK_S=60`) for scheduled skills and reminders — this is
  the natural place to also poll background tasks.
- Proactive reporting already exists end-to-end: `queue_or_deliver_notification`
  (`jarvis.py:1739`) checks whether you're mid-focus-block before interrupting, and
  Windows toast delivery was just added (per recent commit history). A finished
  background task is just another thing that flows through this same gate.
- `quick_recall` (`jarvis.py:2052`) already assembles "what's going on" from projects,
  reminders, and recent tasks — background tasks slot in as one more source.

So the fix is: **make delegation non-blocking, track it, poll it from the existing
scheduler loop, and report through the existing notification gate.** No new service,
no Docker container, no separate process to babysit.

## Why not n8n

n8n is a general workflow engine (visual canvas, webhooks, 400+ integrations). It's
free self-hosted and cheap to run ($5-10/mo VPS, or free on a machine that's already
on), but it buys you nothing here:

- Its main value is orchestrating *many external services* through triggers/webhooks.
  Jarvis's triggers are "you said something" or "a schedule tick fired" — both already
  exist.
- You'd end up with two orchestration layers doing the same job: Jarvis calling an n8n
  webhook, n8n calling back into Jarvis (or `claude -p` itself) to report status. That's
  more moving parts for identical behavior.
- It's a separate always-on process (Docker) on a machine that isn't a server — one
  more thing to keep alive, update, and debug when it's down.

Worth reconsidering only if you later want non-Jarvis triggers (e.g. "when this email
arrives" without going through the Gmail MCP tool you already have) or a visual
editor for a much bigger workflow catalog.

## Why not Hermes / Ollama

Hermes Agent (NousResearch) isn't a component you plug into Jarvis — it's a *competing*
full agent runtime (its own persistent daemon, its own memory, its own scheduler, its
own skills). Adopting it means running two assistants side by side, not adding
background tasks to this one.

Using a *local model via Ollama* as the reasoning engine for background tasks (instead
of Claude) is a real lever for cost, but there's no dollar amount to save right now:

- Coding/debugging tasks already ride your Pro/Max subscription (fixed cost, already
  paid for) — a local model wouldn't make that cheaper, only lower quality.
- Websearch-and-summarize tasks are cheap enough on Haiku already (fractions of a cent
  each) that local inference wouldn't move the needle, and it adds a GPU/VRAM
  requirement plus weaker tool-calling reliability (per current Hermes-on-Ollama docs,
  you need ≥64K context and a tool-calling-tuned model like Hermes 4.3 or Qwen3, and
  Ollama's 4K default context has to be raised manually or it breaks).

Worth reconsidering only if background-task *volume* gets high enough that Haiku
tokens start actually costing something noticeable, or you specifically want tasks
that work with zero internet/API dependency.

## The actual constraint to design around: Pro/Max usage pool, not dollars

Headless `claude -p` runs draw from the **same 5-hour/weekly usage pool** as your
interactive Claude Code sessions and the Claude apps — there's no separate metering,
but there is a shared ceiling. So the plan below caps concurrent background coding
tasks rather than letting Jarvis fire off unlimited parallel `claude -p` processes.

## Two task kinds, two execution paths

**A. Coding / debugging** — needs real Claude Code (file edits, running tests, repo
awareness) → background **OS subprocess** wrapping the existing `claude -p` call.

**B. Websearch-and-summarize-to-a-file** — Jarvis already has `web_search` and
`write_file` tools and a working tool loop (`run_agent_loop`) → background **thread**
running `run_agent_loop` directly, no need to shell out to Claude Code at all. Cheaper
and simpler than path A for this kind of task.

Both report through the same tracking table and notification path.

## Concrete changes

1. **New table** `background_tasks` in `jarvis_memory.db`: `id, task, kind
   ('code'|'research'), repo_path_or_output_path, status ('running'|'done'|'failed'),
   pid (nullable, path A only), started_at, finished_at, result_summary`.

2. **Make `delegate_to_claude_code` non-blocking (path A).** Replace the blocking
   `subprocess.run` in `_delegate_to_claude_code` with `subprocess.Popen`, stdout
   redirected to a file under a new `.jarvis_tasks/<id>/output.json`. Insert a
   `background_tasks` row, return immediately: *"Started — I'll let you know when
   it's done."* Keep the existing catastrophic-command tripwire check before
   spawning (already there, keep as-is) and the existing `--dangerously-skip-permissions`
   posture (matches the rest of the codebase's full-trust design).

3. **New tool for path B**: `delegate_research(task, output_path)` — spawns a thread
   that runs `run_agent_loop` with a synthetic transcript telling it to search and
   write findings to `output_path` (default: a `Jarvis_Research/` folder), same
   tracking-row pattern as path A.

4. **Extend `_scheduler_loop`** with `_check_background_tasks(now)`: for path-A rows,
   poll the in-memory `Popen` handle (`proc.poll()`); for path-B rows, the thread
   itself updates the row on completion (no polling needed, but the row still exists
   for `list_background_tasks`/`quick_recall`). On completion, parse the result the
   same way `_delegate_to_claude_code` already does, mark the row `done`/`failed`,
   and call `queue_or_deliver_notification(f"Background task finished: {summary}")` —
   reusing the exact idle-gate + toast pipeline reminders already use.

5. **Concurrency cap**: `MAX_CONCURRENT_BACKGROUND_CODE_TASKS = 2` (tunable constant,
   path A only — path B threads are cheap enough not to cap as tightly). A new request
   past the cap gets queued with a spoken "already got 2 running, this'll start once
   one finishes" rather than silently piling up `claude -p` processes against the
   shared usage pool.

6. **New tools mirroring the reminders pattern**: `list_background_tasks` (like
   `list_reminders`) and folding running/recent background tasks into `quick_recall`'s
   summary, so "what's going on?" includes them without a separate ask.

7. **Crash recovery**: on Jarvis startup, any `background_tasks` row still `running`
   from a previous process (no live `Popen` handle, since those don't survive a
   restart) gets marked `failed` with a note — matches the existing honest-about-limits
   style rather than pretending to resume it (per current web research, Claude Code
   headless sessions don't reliably reconstruct execution continuity across a resume
   anyway, so no point trying to fake it).

## What you'd say once this is built

- *"Debug the crash in `foo.py`, I'll be doing other stuff"* → path A, Jarvis replies
  immediately, keeps taking commands, later interrupts (or waits for your next command,
  per the existing focus-window gate) with *"Finished debugging foo.py: the crash was
  X, fixed by Y."*
- *"Look into the best noise-cancelling headphones under $200 and save a summary to my
  desktop"* → path B, same pattern, cheaper and faster since it skips spinning up a
  full Claude Code session.

## Suggested build order

1. Path A (non-blocking `delegate_to_claude_code` + tracking table + scheduler poll +
   notification) — biggest win, reuses the most existing code.
2. `list_background_tasks` + `quick_recall` integration.
3. Path B (`delegate_research`) — smaller addition once path A's tracking
   infrastructure exists.
4. Concurrency cap + crash recovery — hardening once 1-3 work end to end.

Say the word and I'll start on step 1.
