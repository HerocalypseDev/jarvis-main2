## Git

This repo is pushed to https://github.com/HerocalypseDev/jarvis-main2 (private). Push changes
after every phase of work (each meaningful chunk — a feature, a fix, a batch of related
changes), not only when explicitly asked: commit with a clear message and `git push`. Review
`git status`/`git diff` before staging, and never commit anything that looks like a real
credential, token, or PIN (check new files under `skills/` in particular — a skill can contain
things like typed passcodes).

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Dashboard (supervision UI)

- Code: `jarvis_dashboard.py` (FastAPI/WebSocket backend + own `dashboard_sessions` table in
  `jarvis_memory.db`) and `dashboard_static/` (vanilla HTML/CSS/JS frontend). It runs as a
  daemon thread started from `jarvis.py`'s `main()`, in-process — not a sibling process —
  because it needs direct access to in-memory state (`_pending_action`,
  `_RUNNING_BACKGROUND_PROCS`) that is never persisted to SQLite.
- Local-first, localhost-only by default: binds `127.0.0.1:${JARVIS_DASHBOARD_PORT:-8765}`
  only. No auth layer (accepted by the user 2026-09-18: single-user local machine). Never bind
  `0.0.0.0` and never add a tunnel (ngrok/Cloudflare/etc.) without a fresh, explicit
  confirmation in-session — this is a standing rule, not a one-time ask.
- The dashboard must never weaken or duplicate the catastrophic confirmation gate
  (`_CATASTROPHIC_PATTERNS`/`_pending_action` in jarvis.py). Any "Approve" action must call the
  *existing* `_execute_confirmed_action`/`_execute_tool(..., skip_confirmation=True)` path,
  never a reimplementation. The user explicitly accepted (2026-09-18) that the dashboard's
  Approve button may one-click-confirm catastrophic-tier actions (shutdown/format/recursive
  wipe) once that endpoint ships — this is a deliberately reviewed exception to the general
  "no silent bypass" instinct, not an oversight; keep it behind the mandatory detail view the
  original feature spec calls for, not a bare list-row button.
- New dashboard features still require the double-check protocol (map onto existing
  tables/functions, list new tables/APIs, risk review across security/cost/data-exposure/
  irreversibility/performance, stop-and-ask on non-zero risk) before implementation.
- Off by default. Start: set `JARVIS_DASHBOARD_ENABLED=1` before running `python jarvis.py`;
  it opens `http://127.0.0.1:8765` in a browser automatically (`JARVIS_DASHBOARD_AUTO_OPEN=0`
  to disable that). `JARVIS_DASHBOARD_PORT` overrides the port. No desktop shell (Tauri) yet —
  MVP is a plain browser tab; Tauri packaging is deferred until Phases 1-3 are solid.
- Visual style: dark background with cyan/electric-blue glow accents (mood reference only).
  Layout is the functional top-approval-bar + a horizontal system-metrics strip + three-column
  (Sessions/Tasks/Detail) + bottom Activity/Audit-Trail/Victory-log tabs — never the circular
  HUD composition of any reference image. The metrics strip is this build's take on the spec's
  "optional sidebar," horizontal rather than vertical so it doesn't crowd the three columns.
- Status: Phase 1 shipped (Sessions, Tasks, Victory log, read-only pending-action display,
  basic WebSocket live updates). Phase 2 shipped (Approve/Reject wired to
  `_execute_confirmed_action`/`_take_pending_action`, reachable only via the frontend's
  mandatory "Review" detail view; Stop wired to a task's own subprocess via
  `_dashboard_kill_background_task`, which only ever kills processes Jarvis itself spawned).
  Phase 3 shipped: a filterable Audit Trail tab (`GET /api/audit`, filters on date range,
  tool name, and a free-text search over tool_input/result/transcript — session correlation
  is an exact match on `action_audit.transcript`, since handle_text_command passes the same
  transcript string into both `dashboard_sessions` and every `_log_action_audit` call for that
  turn, so no new session_id column was needed) and the metrics strip (CPU/RAM/disk/uptime from
  the existing `get_system_status_report()`/psutil, sampled once server-side on a 5s timer and
  pushed to clients — not polled per-browser-tab). Phase 4 shipped: an input-mode chip in the
  top bar (reflects the most recent session's source), a compose box in the Detail column that
  posts to `POST /api/command` — a 4th input surface alongside voice/text-hotkey/phone, running
  through the *exact same* `handle_text_command` pipeline including the confirmation gate, never
  `skip_confirmation=True` — and an auto-focus behavior where a new voice-originated session
  opens in the Detail panel live. Tauri packaging remains deferred (user chose "browser tab for
  MVP" 2026-09-18); revisit only if asked.
- Post-launch fixes/additions (2026-09-18, from real usage): a Services dropdown
  (`GET /api/services`, `_dashboard_get_services_status()` in jarvis.py) lists every configured
  MCP server plus both phone channels with a live status dot; a per-core CPU heatmap in the
  metrics strip (`metrics.cpu.per_core_percent`, already returned by
  `get_system_status_report()` — no backend change needed for that part); `dashboard_sessions`
  is now pruned to `MAX_SESSION_ROWS` (300) on every write, the Sessions panel groups rows by
  day, and has a "Clear finished" button (`DELETE /api/sessions/finished`, active sessions are
  never touched); the Detail panel's audit/session/task views were rebuilt as syntax-highlighted
  cards instead of raw `<pre>` dumps of JSON.
- **Test suite**: `test_dashboard.py` (pytest + FastAPI TestClient, isolated temp DB via
  `JARVIS_MEMORY_DB_PATH`, never touches the real `jarvis_memory.db`) covers every dashboard
  endpoint. Run: `python -m pytest test_dashboard.py -v`. Extend it when adding endpoints rather
  than only ad-hoc-testing by hand.
- Post-launch round 2 (2026-09-18, from more real usage): columns and the bottom panel are now
  drag-resizable via plain CSS `resize: horizontal`/`resize: vertical` (`.layout` switched from
  grid to flex so a resized column reflows the others instead of overflowing a fixed grid
  track) — verified the computed style applies correctly, but pixel-perfect synthetic
  mouse-drag verification of the actual grip hit-zone was unreliable in headless Chromium
  (known automation flakiness for native resize handles); this needs a real hands-on check, not
  just automated coverage. A new "Daily" tab (`GET /api/daily`, `_dashboard_get_daily_items()`
  in jarvis.py) lists recurring skills (from `_load_skills()`'s `schedule` field, with last-run
  time from `scheduled_skill_runs`) and recurring reminders (`repeat_every_minutes` set) — kept
  as its own tab per explicit request, not folded into the Tasks column, since these are
  standing routines, not one-off/in-flight work.

## Speech shaping (2026-09-18)

- `_finish_background_task` now reports completion with `urgent=True` — a background
  code/research task the user explicitly asked for must never sit silently queued behind the
  busy-quiet-hours gate (`queue_or_deliver_notification`'s `user_is_actively_working() and
  _is_preferred_work_hours()` check) the way an unprompted proactive suggestion does. That gate
  still applies as before to scheduled skills and health-monitor suggestions — only
  user-requested background task completions bypass it.
- **Design intent, clarified by the user after an initial misread (2026-09-18): the dashboard
  is always the full, complete record (session reply, audit trail — never trimmed); what comes
  out of the speakers is a separate, always-summarized pass over that same reply
  (`_summarize_for_speech`), and that spoken summary happens for every input source — voice,
  typed-hotkey, AND dashboard — never just silently written to the dashboard instead of spoken.**
  ("dashboard shouldn't talk" from earlier the same day meant "don't parrot the dashboard's full
  text verbatim out loud," not "stay silent when commands come from the dashboard" — an initial
  fix over-corrected to full silence for dashboard-sourced replies, confirmed broken live ("it's
  not even talking anymore"), then corrected to speak the *summary* for dashboard same as voice.)
  Phone is the one exception that stays text-only (no spoken summary, just the "Message
  received." ack) since nobody's in the room for a remote phone command — that part was never in
  question. What Jarvis speaks is shortened for anything over `SPEECH_SUMMARY_MIN_CHARS` (220
  chars) via one extra Claude call (`_summarize_for_speech`, same `CLAUDE_MODEL` already used
  everywhere — Haiku by default, so this doesn't add a more expensive tier) before `speak_text`.
  The dashboard/audit trail/session
  history always keep the full, unsummarized `reply` — only the TTS output is shortened. Falls
  back to the original text on any failure; never goes silent.
- `_collapse_paths_for_speech` replaces any full file path in the spoken text with just its
  containing folder's name ("the Research folder", never a path with every backslash read
  aloud). URLs are masked out before this runs and restored untouched after — the naive version
  of this regex will also match a URL's `/path/segments` and mangle the link; don't remove that
  masking step when touching this code.
- Dashboard-originated commands (`source="dashboard"`) no longer get the spoken "Message
  received." ack — that's for phone commands only, where nobody's looking at a screen for it.
  The dashboard already shows a command land live.

## MCP startup (2026-09-18)

- `ensure_mcp_started()` previously had a real race: it set `_mcp_started = True` *before* the
  connection attempt finished, so a second caller (observed live: the scheduler's first tick
  running a due skill like `gmail_watch`, racing against `_preload_mcp_async()`'s background
  connect) would see "already started" and return immediately with an empty tool list, instead
  of waiting for the connection that was still in flight. Fixed: every caller now blocks on
  `_mcp_ready_event` until the in-flight attempt (started by whoever got there first) actually
  finishes. Verified with a threaded repro (`ensure_mcp_started` called concurrently from two
  threads against a slow fake connect) before/after the fix.
- A server that fails to connect is retried automatically every `MCP_RETRY_INTERVAL_S` (2 min)
  from the scheduler tick (`_retry_failed_mcp_servers`, tracked in `_mcp_failed_servers`) instead
  of being given up on for the rest of the process's life — previously the only way to recover
  from a transient failure (npx cold-start, brief network hiccup) was restarting Jarvis.

## Reliability fixes from real usage (2026-09-18)

- **Silent replies, root-caused**: `run_agent_loop` could return an empty string when Claude
  ended its turn with only a tool call and no text at all — most consequentially, right after
  staging a catastrophic confirmation (run_shell/run_python's "staged, not run, say yes" tool
  result), where Claude sometimes considered the tool result self-explanatory and added no
  spoken commentary, and for a multi-tool task (e.g. "summarize my email") that exhausted
  `MAX_AGENT_ITERATIONS` before ever narrating a summary. The system prompt already said to
  always give a spoken reply, but that's not 100%-reliable model behavior. Fixed at the code
  level: if the loop ends with no text but at least one tool was called, `reply` falls back to
  that last tool's own result text instead of empty — silence is worse than surfacing something.
  Verified with a simulated Claude response containing only tool_use blocks across the whole
  loop (the worst case) before/after the fix.
- **RAM monitoring removed entirely** (`check_system_health`'s per-process "X is using N
  megabytes, want me to close it?" nag and the RAM-jump-since-last-check alert), per explicit
  user request. CPU-load and disk-capacity checks are untouched — only asked to remove RAM.
  `system_status()` (on-demand, voice-asked) still reports RAM usage; this only removed the
  *unprompted* nagging about it.
- **Phone push notifications are off by default now**: `JARVIS_PHONE_PROACTIVE_NOTIFICATIONS`
  (env var, default false) gates `_notify_phone`, called from `queue_or_deliver_notification`
  for every proactive message (scheduled skills, reminders, background task completions,
  health-monitor suggestions). Per explicit user request: "I don't want notifications sent to
  my telegram and ntfy all the time unless I type a message there." This never affects a direct
  reply to something the user typed *from* ntfy/Telegram — that goes through `reply_sink` in
  `_ntfy_listen_loop`/`_telegram_listen_loop`, a completely separate path, unaffected by this
  toggle. Set the env var to `1`/`true` to restore proactive phone pushes.

## Window control

- `resize_window(title, width=, height=, width_percent=, height_percent=)` and
  `resize_all_windows(...)` (jarvis_window_control.py) added for arbitrary free-form resize —
  `snap_window` remains for the fixed preset zones (left/right/quarters/etc.), this is for "make
  this window 500x400" or "resize all my windows to half the screen." Exposed to the agent via
  `control_window`'s `action=resize` and the standalone `resize_all_windows` tool.
- `resize_all_windows` resizes *every visible window on the desktop* — tested once for real
  during QA and it visibly resized 15 live windows (Discord, Chrome, VS Code, etc.), not just a
  throwaway test window. Test this one against a single spawned process in the future, not the
  live desktop.

### Cost reporting

After every implementation phase, report a table with exactly these rows — Model, Work,
Estimated tokens, Estimated cost, Time, and a **Running total** row that states *both* the
running cost and the running time across all phases so far (not cost alone):

| | |
|---|---|
| Model | e.g. Sonnet 5 |
| Work | one line: what changed and how it was verified |
| Estimated tokens | e.g. ~95k in / ~9k out |
| Estimated cost | e.g. ~$0.55–$0.75 |
| Time | e.g. ~15 min |
| Running total (Phases 0–N) | e.g. ~$1.55–$2.15, ~45 min |

This exact table goes in every phase report in chat (user confirmed 2026-09-18) — not just a
prose summary. Keep the running totals in the phase-log table below up to date too; add a new
row there each phase rather than only stating the total in chat.

| Phase | Model | Time | Est. cost |
|---|---|---|---|
| 0 (analysis + risk review) | Sonnet 5 | ~5 min | ~$0.20–$0.30 |
| 1 (Sessions/Tasks/Victory log MVP) | Sonnet 5 | ~25 min | ~$0.75–$1.10 |
| 2 (Approve/Reject/Stop) | Sonnet 5 | ~15 min | ~$0.55–$0.75 |
| 3 (Audit Trail filters + System Metrics) | Sonnet 5 | ~20 min | ~$0.60–$0.85 |
| 4 (input-mode chip, dashboard commands, voice auto-focus) | Sonnet 5 | ~15 min | ~$0.45–$0.65 |
| 5 (import deadlock + SQLite WAL/lock fixes, found on live restart) | Sonnet 5 | ~10 min | ~$0.30–$0.40 |
| 6 (RAM removal, silent-reply fix, phone-notif toggle, resizable panels, Daily tab) | Sonnet 5 | ~35 min | ~$1.00–$1.40 |
| **Running total (final)** | | **~125 min** | **~$3.85–$5.45** |
