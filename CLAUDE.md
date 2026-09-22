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
- **UI/UX overhaul (2026-09-22)**: replaced the three-column + bottom-tabs layout with a
  sidebar-navigated, hash-routed shell (Home/Sessions/Tasks/Autonomy/Identity/Sleep/Usage/
  Activity/Audit/Victory/Daily) plus a new Home "mission control" default view. Full write-up,
  route table, and parity notes in `DASHBOARD.md`. Frontend-only — `jarvis_dashboard.py` was not
  touched, so the Host/Origin guards, the localhost-only bind, and the confirmation gate's
  Review-then-Approve path are all exactly as before (`actOnPending()` still calls the same
  `POST /api/pending/approve|reject`, copied verbatim). No feature was dropped: every panel from
  the old bottom-tabs (Autonomy's suggestions/commitments/campaigns/rules/log/organising/skills/
  dynamic-tools, Identity's profiles/consent/pause/away/pictures/events, Sleep's charts/digests,
  Usage, Audit filters, Victory, Daily) kept its existing element IDs and was re-parented into a
  routed `<section>` rather than rewritten — `autonomy.js` needed exactly two line changes (its
  panel lookup id, and removing a now-nonexistent tab-button click listener since the router
  calls `window.refreshAutonomy()` directly on route activation). Home composes entirely from
  data the other routes already fetch (`GET /api/state` + the existing usage/llm chip polling) —
  confirmed during a Phase 0 inventory pass that no new backend endpoint was needed. This
  **supersedes** the "Post-launch round 2" resizable-column note above: the three-column
  `.layout`/`.col` grid no longer exists (Sessions and Tasks are now separate full-width routes),
  so there's nothing left to drag-resize there; the bottom panel's `resize: vertical` is likewise
  gone along with the bottom-tabs strip itself. Sidebar is collapsible (button in the top bar,
  state remembered per-browser in `localStorage`). Verified: `test_dashboard.py` (30/30) and the
  dashboard-relevant slice of `test_hardening.py` pass unchanged (one assertion updated for the
  renamed `tab-audit` → `view-audit` element id); every route's backing API responds 200 against
  a standalone preview instance (`jarvis_dashboard._build_app()`, see `DASHBOARD.md`); `node
  --check` on both JS files; and `renderHome()` was executed against real fetched API data in a
  headless Node harness (no jsdom, no browser automation tool available in this session) and
  confirmed to run without error, including the RAM-danger styling and alert banner firing
  correctly at 91%. **Not verified**: an actual rendered browser view (no claude-in-chrome/jsdom
  available this session) — the user should eyeball it live before treating this as fully done.
- **Post-overhaul UX pass (2026-09-22)**: full write-up in DASHBOARD.md's "Post-overhaul UX pass"
  section. Summary: (1/2) new voice/text/dashboard commands and Audit Trail row clicks now drive
  the context/detail panel automatically (a background update reveals the panel only if the
  current route already has one; a direct click still navigates — see DASHBOARD.md for the full
  navigation write-up); (3) Usage/Sleep/Identity/Home's shared `.usage-cards` strip is now a
  responsive grid instead of flex-wrap, taller charts, and a new Usage "tokens & cache savings by
  period" breakdown from fields `/api/usage` already returned; (4) Autonomy was restructured into
  Needs-you / Running-now / commitments / campaigns / rules / secondary "Automation details" /
  activity log, with every existing control kept, just regrouped; (5) Sleep gained a goal-hit-rate
  % card and a total-sleep-this-period card from fields already computed; (6) Home gained Recent
  sessions (clickable), Recent autonomy activity, a Presence card (face recognition, hidden when
  the feature is off), and an Open-tasks count — via two new light 30s polls of the existing
  `/api/autonomy`/`/api/faces` endpoints, no new backend route. Two real voice-playback bugs were
  also root-caused and fixed in `jarvis.py` (not dashboard code): `_play_pcm_stream`'s
  `sd.OutputStream` now passes `latency="high"` so uneven network chunk timing can't starve the
  output device into a crackle/dropout ("voice breaks a lot"); and a new
  `TTS_LIVE_STREAM_MIN_CHARS` (40, `JARVIS_TTS_LIVE_STREAM_MIN_CHARS`) keeps short text — the
  filler phrase and short replies like "Hi, how can I help?" — off the live Deepgram WebSocket
  entirely, since `_speak_streamed`'s existing "keep whatever already played, don't restart" rule
  on a mid-stream drop is the right call for a long reply but sounds like the whole thing got cut
  off on a short one, and a short phrase's REST round trip is already fast enough that streaming
  buys little there anyway. Residual, accepted: a genuine mid-utterance WebSocket drop on a
  *longer* reply (past the 40-char floor) still ends with whatever played before the drop, the
  same class of tradeoff as Phase C's documented LLM-stream retry behavior in SPEED.md. Tests:
  2 new in `test_deepgram_voice.py` (92 total in that file), one pre-existing test's fixture text
  lengthened to keep exercising the streaming path it tests. Full suite: 733 tests, same 4
  pre-existing unrelated failures (deleted urgent-email-monitor skill files, see "Audit hardening"
  below).

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

- **Proactive speech now shaped too (2026-09-18)**: a finished delegated coding task was read out
  word for word, because `_finish_background_task` -> `queue_or_deliver_notification` called
  `speak_text` directly — `_summarize_for_speech`/`_collapse_paths_for_speech` only ran inside
  `handle_text_command`. New `_speak_shaped()` applies both, and is used by
  `queue_or_deliver_notification`, `flush_pending_notifications`, and the spoken result of a
  confirmed/dashboard-approved action. Only the spoken copy is shortened; dashboard, toast and
  phone push keep the full text. Guided-breathing lines stay verbatim on purpose. Rule: any new
  code path that speaks model- or tool-generated text should use `_speak_shaped`, not
  `speak_text` directly.

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

## Text-to-speech: Fish Audio primary, Piper fallback (2026-09-18)

- Double-checked and locked in with the user: Fish Audio's free `s2.1-pro-free` tier (zero
  ongoing cost), the user's own `reference_id` voice, Piper kept installed as an automatic
  fallback rather than removed. Credentials live in `.env` only (`FISH_AUDIO_API_KEY`,
  `FISH_AUDIO_VOICE_ID`, gitignored, never in code or committed) — if you ever need to rotate
  them, that's the only place they live.
- `speak_text()` tries `_fish_audio_synthesize()` first when `FISH_AUDIO_API_KEY` is set (a
  plain `urllib.request` POST to `https://api.fish.audio/v1/tts`, no new pip dependency);
  requests `format: "wav"` specifically (not raw `pcm`) so the sample rate comes from the
  response's own header via stdlib `wave`, instead of being guessed/hardcoded. Any failure
  (missing key, network error, bad response) falls back to the existing local Piper path —
  never straight to silence. Verified live: a real API call end-to-end through `speak_text()`
  (including actual playback), and a simulated Fish Audio outage confirmed the Piper fallback
  actually plays audio rather than going quiet.
- Sleep Mode's calmer-at-night TTS tuning now has two parallel functions in
  `jarvis_sleep_mode.py`: `tts_overrides()` (Piper's `length_scale`/linear `volume`, unchanged)
  and the new `fish_audio_prosody_overrides()` (Fish's `speed` 0.5–2.0 / `volume` in dB) — same
  "slower and quieter" intent, not an exact unit conversion between the two engines' different
  parameter shapes.

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

## Prompt caching (2026-09-18)

- `run_agent_loop` and the plan-step loop send Anthropic `cache_control` breakpoints on (1) the
  last tool, (2) the stable system block, (3) the final message block, so each of the up-to-12
  round trips per command re-reads the ~22k-token prefix (system prompt + 105 tool schemas +
  earlier tool results) at ~10% price instead of re-billing it. Helpers: `build_system_blocks`,
  `_cached_tools`, `_messages_with_cache_breakpoint` (copies — never mutates `messages`), and
  `_log_cache_usage` (logs uncached/cache-read/cache-write/out tokens per round trip).
- Cache matching is exact-prefix: anything that changes per call (clock minute, tone line,
  sleep-mode line) must stay in the *volatile* second system block, after the breakpoint, and is
  built once per command, not per round trip. Don't move it back into the stable block.
  `build_system_prompt` is now unused by the loops (kept for reference).
- Verified live: call 1 wrote 22,039 tokens to cache, an identical call 2 read all 22,039.

- **Caching, round 2 (2026-09-18)** — helpers in `jarvis_cache.py`, tests in `test_cache.py`
  (`python -m pytest test_cache.py -v`). Every layer is on by default and individually switchable
  with `JARVIS_<LAYER>_CACHE=0`:
  - `PROMPT` — the layer above, now with a **1-hour TTL** on tools + stable system block
    (`JARVIS_PROMPT_CACHE_TTL=5m` for 5-minute; auto-falls back to 5m for the run if the API
    rejects `ttl`), a startup pre-warm (`start_prompt_cache_warmup`, 1-token request — the API
    rejects `max_tokens=0`), and optional `JARVIS_PROMPT_CACHE_KEEPWARM_MIN` (default off: a
    read of the ~22k prefix every few minutes around the clock costs more than it saves).
    Workflow summary moved to the volatile block. **Verified live** (2026-09-18): 1h TTL accepted
    (write then full read), startup pre-warm ran after MCP connected, agent-loop round trips read
    the 33k-token prefix from cache. Note: a startup pre-warm racing a scheduled skill's first
    call (both fire when MCP connects) can double-write once — harmless, one-time.
  - `TTS` — `.cache/tts/*.wav`, phrases ≤200 chars, 200 entries/100MB LRU. Keyed per engine
    (Fish vs Piper), so Piper fallback audio is never served in place of the real voice.
  - `REPLY` — in-memory; only turns whose tools were *all* in `READONLY_TOOL_TTLS`, none failed,
    and whose transcript has no pronoun/"and…"-style context dependence. Zero-tool turns are
    never cached (they may depend on history or the clock). TTL = shortest tool TTL used.
  - `TOOL` — in-memory results for `READONLY_TOOL_TTLS` tools (15–60s; web_search 10 min).
    Running any other tool (mutating, mcp_*, unknown) clears both this and the reply cache.
  - `SUMMARY` — (live: repeat long reply skipped its Claude call) `speech_summary_cache` table in `jarvis_memory.db`, 7-day max age, 500 rows.
  - Skills are re-parsed only when a `skills/*.json` name/mtime signature changes.
  - Hit/miss logging: `cache[layer] HIT|miss ... (h/n hits, pct)` and per-call
    `agent loop tokens: ... cache-read ...` lines in the Jarvis log.

## Confirmation gate follow-up (2026-09-18)

- **Shutdown never staged (2026-09-18, found live)**: "shut down my computer" via the dashboard
  produced a text-only reply ("I'm about to shut down… say yes") with *no* run_shell call, so
  nothing was staged, the dashboard approval bar stayed empty, and a later "yes" did nothing —
  Claude imitated the staged-action wording from the system prompt without making the call that
  triggers the gate. Nothing ran (audit table had no run_shell row). Fixed in the system prompt
  (must make the run_shell/run_python call; never announce/ask "yes" without it) and pinned with
  tests: the gate stages `shutdown /s /t 0` without executing it, and the prompt carries the rule.
  Prompt-level, so not 100% deterministic — if it recurs, add a code-level guard.

## Self-modification: `change_jarvis_code` (2026-09-18)

- New `change_jarvis_code(feature)` tool hands a change to Jarvis's *own* source to the background
  coding agent (James, headless `claude -p --dangerously-skip-permissions`). **Any** delegation
  whose working directory is this repo — the new tool, or `delegate_to_claude_code` with no/this
  `repo_path` — gets `_SELF_EDIT_PREAMBLE` prepended, so no route skips the rules: follow
  CLAUDE.md (incl. the dashboard risk review; headless, so risky = report, don't build), never
  weaken the confirmation gate / phone rules / localhost-only binding, never touch secrets, add
  tests and run them, **commit locally but never push or restart** (the running instance keeps
  its old code until the user restarts it), and give a 2–4 sentence spoken summary.
- Only one self-change runs at a time (`_SELF_EDIT_TASK_IDS` vs `_RUNNING_BACKGROUND_PROCS`).
- **Phone can trigger it, by explicit user choice (2026-09-18, "I am aware of the risk").** It is
  not source-gated: a Telegram/ntfy message can start a self-change. Anyone who can message the
  ntfy `-cmd` topic or the Telegram chat can therefore ask for code changes — the preamble is a
  guardrail for the model, not a technical barrier. The result of a self-change is pushed to the
  phone even with `JARVIS_PHONE_PROACTIVE_NOTIFICATIONS` off (`_notify_phone(force=True)`); every
  other proactive message still respects that toggle. If the phone exposure ever worries the
  user, the safe tightening is refusing `change_jarvis_code` when the command came from phone.
- Unit-tested with `subprocess.Popen` faked (prompt/cwd, self-edit lock, phone forcing); **not
  run live** against a real `claude` process — a live test would make real edits to this repo.

## Gemini brain option (2026-09-18)

- Jarvis can run on **Gemini (Google AI Studio)** instead of Claude, switchable live. All eight LLM
  call sites still build Anthropic-format requests; `_claude_request` checks `_llm_provider()` and,
  for gemini, hands the body to `jarvis_gemini.call`, which translates request -> Gemini
  `generateContent` and response -> Anthropic shape (tool_use/tool_result <-> functionCall/
  functionResponse, images -> inlineData, `cache_control` keys ignored, usage mapped incl. cached
  tokens). Nothing above `_claude_request` knows which brain answered.
- **Switching**: `llm_provider.json` (gitignored; written by the switch) > `JARVIS_LLM_PROVIDER`
  env > `claude`. Ways to flip it at runtime, no restart: the `set_llm_provider` tool ("switch to
  Gemini"), or the **"brain: claude/gemini" chip** in the dashboard top bar (`GET/POST /api/llm`;
  clicking to Gemini asks for confirmation). `set_llm_provider` refuses a provider whose key isn't
  set, so a typo can't strand Jarvis. Keys: `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) in `.env` only;
  `JARVIS_GEMINI_MODEL` (default `gemini-3.1-flash-lite`); `JARVIS_GEMINI_THINKING` (default
  `minimal` — thinking tokens bill as output and count toward free-tier limits; `default` leaves
  the model's own).
- Gemini 3 needs each function call's `thoughtSignature` echoed back: `from_response` stores it on
  the tool_use block as `_thought_signature` and `convert_messages` sends it back. Tool schemas go
  via `parametersJsonSchema` (MCP schemas pass through untouched); empty-property tools omit it.
- 429s: waits the server's `retryDelay` if <= 30s, but fails fast on a long (daily) quota reset
  rather than hanging a command. A 400 mentioning "thinking" retries once without thinkingConfig.
- **Data-exposure risk (double-check protocol)**: on Google's *free* tier, prompts and tool
  results (emails, screen contents, shell output) may be used to improve Google products; the paid
  tier does not. `set_llm_provider` and the dashboard confirm both say so. Claude stays the default.
- Free-tier limits are per *project*, not per key, and exact numbers are only visible in the AI
  Studio dashboard (third-party blogs disagree). A full agent turn sends ~13k tokens of fixed prefix
  (system ~4.8k + built-in tools ~8.3k, more with MCP tools) per round trip; Gemini's implicit
  caching reduces billing but it is unverified whether cached tokens count toward TPM.
- Usage tracking covers both providers (`api_usage` records the model that actually answered;
  Gemini prices are paid-tier equivalents, real free-tier cost is $0; the Usage tab now also
  shows tokens per model). The Anthropic prompt-cache pre-warm is skipped on Gemini.
- Verified live against the real Gemini API: 62-tool request accepted, tool call -> result ->
  reply round trip, implicit cache hits, and the "where is your code" question answered correctly.
  Not verified: the dashboard chip in a real browser, the voice/phone paths on Gemini, and how
  well a lite model handles the 58 extra MCP tools.

## Own-code location fix (2026-09-18)

- **Wrong "where is your code" (found live)**: asked where its source lives, Jarvis had no ground
  truth, searched the disk with run_shell, found the unrelated OpenJarvis project under the user
  profile and named it as its own code — a self-edit sent there would have changed the wrong repo.
  Fixed with `_own_code_context_line()` in the stable system block (the real path from
  `Path(__file__)`, "don't search the disk", "OpenJarvis etc. are different projects, use
  change_jarvis_code") and a clearer `delegate_to_claude_code` repo_path description. Pinned by
  tests in `test_cache.py`. Prompt-level, so not deterministic; if it recurs, add a code-level
  path check. **Not yet re-verified live** — the API credit balance ran out before the check.

## API spend lookup (2026-09-18)

- `api_spend` tool (`jarvis_billing.py`) reads Anthropic's Usage & Cost Admin API
  (`GET /v1/organizations/cost_report`, daily buckets, paginated) so Jarvis can answer "how much
  have I spent on Claude?". Needs `ANTHROPIC_ADMIN_API_KEY` (an `sk-ant-admin…` key, org accounts
  only) in `.env` — never in code; the normal `ANTHROPIC_API_KEY` cannot read billing. Read-only,
  cached 5 min via `READONLY_TOOL_TTLS`. Amounts arrive in cents as decimal strings.
  Unit-tested against the documented response shape; **not yet verified live** (the `.env` key
  line was blank when built) — confirm the real response once a key is set.
- **Local spend estimate (2026-09-18)** — for accounts with no Admin key (individual accounts
  can't have one). Every response's `usage` block goes through `_record_api_usage` (called from
  `_claude_request`, on its own thread so a locked DB can never delay or deadlock a Claude call)
  into the `api_usage` table in `jarvis_memory.db`: tokens + `cost_usd` + `saved_usd` (what
  caching saved vs. uncached input). Prices are the `PRICES` table in `jarvis_billing.py`
  (Haiku 4.5 / Sonnet 4 / Opus 4.5 list rates; unknown models fall back to Haiku rates and are
  flagged "approximate" — **update `PRICES` when prices change or the default model changes**).
  Covers Jarvis's own calls only, not other apps on the same key. `api_spend` uses the Admin API
  when `ANTHROPIC_ADMIN_API_KEY` is set, else this local estimate. Dashboard: `GET /api/usage`
  (read-only, no network call), a "Usage" tab (cards, 14-day bars, per-model list) and a
  "$X today" chip in the top bar. Verified live (real calls recorded; tab rendered in headless
  Chromium with no console errors). Rows older than 400 days are pruned on write.
  Cost note: the startup prompt-cache pre-warm is a ~32k-token 1h write, ~$0.065 per restart.

## Sleep trends + wake-up digest (2026-09-19)

- **Sleep tab** in the dashboard (`GET /api/sleep`, `jarvis_sleep_mode.stats_summary()`), built only
  from the existing `sleep_log` table: Week/Month toggle, cards (last night, average with delta vs
  the prior period, best/worst, avg bedtime -> wake + bedtime variability, goal hits + streak, sleep
  debt), and three SVG charts (hours per night with goal line, bedtime/wake times, weekday averages).
  Read-only. It measures time in Sleep Mode, not actual sleep; sessions under
  `JARVIS_SLEEP_MIN_SESSION_MINUTES` (20) are ignored, sessions are grouped by the day they ended
  on, goal is `JARVIS_SLEEP_GOAL_HOURS` (8). Only schema change: `sleep_log.digest TEXT` (auto-migrated).
- **Wake-up digest**: notifications queued during Sleep Mode are flagged `during_sleep` in
  `session_state.json`'s `pending_notifications`. `flush_pending_notifications` leaves them alone
  (even if the user talks to Jarvis mid-sleep). When Sleep Mode ends by either route (the tool or the
  toggle) `disable()` calls the handler `jarvis._sleep_wake_digest`, which drains those items
  synchronously and, on a thread, has one Claude call write a <=3-sentence recap starting "Hero,
  while you were asleep, ...", speaks it, and saves it to `sleep_log.digest` (shown in the tab).
  The recap is two-part: first the *important* items (urgent messages that came through live during sleep — `queue_or_deliver_notification` still speaks them, and also records them with `important: True`), or "nothing important happened"; then, only if there are held-back items, the exact words "On a lighter note," and those. If the model drops that structure, or the call fails, a deterministic fallback builds the same two parts from the raw items; says "nothing came in" if empty.
  Name comes from `JARVIS_USER_NAME` (default Hero). Urgent messages still speak live and are not
  in the digest. Cost: one small extra model call per wake-up. Same data exposure as the existing
  speech summarizer (queued text goes to the active brain). Tests: `test_sleep.py`.

- **Naps (2026-09-19):** the user starts one themselves — say "nap mode" / "I'm taking a nap"
  (`sleep_mode` tool, action `nap` -> `enable(kind="nap")`); `off` ends it. It is *exactly* Sleep
  Mode (quiet notifications, dark mode, volume, media auto-pause, the 15/2-min Gmail monitoring and
  family replies, the wake-up recap — worded "while you were napping") except the session is logged
  with `kind='nap'` (new `kind` column on `sleep_log`/`sleep_state`; NULL = a normal sleep) and never
  counts toward night averages, bedtime/wake, sleep debt or the goal streak. Dashboard: a Naps card
  (count, average, total), a violet nap segment stacked on the day's night bar, "(nap)" in the
  header, and a separate line in the voice `status()`. Naps under `JARVIS_NAP_MIN_MINUTES` (10) are
  ignored. Deliberately explicit: an earlier same-day version guessed naps from the clock
  (afternoon start) and was replaced at the user's request. Not built: a nap timer/alarm (the wake alarm was
  removed), counting
  naps toward a 24-hour goal. Not exercised live (it toggles dark mode/volume/hosts); unit-tested
  with those faked.
- **"Nothing changed" investigation (2026-09-19):** the 01:13-05:02 Sleep Mode run *did* work
  (reminders held, media auto-paused at 01:43) but looked like nothing: the PC was already in dark
  mode (the prior state is restored, so no visible change); volume key presses are only ~2% each;
  site blocking failed on the hosts file (no admin rights); and `disable()` never put the volume
  back. Fixes, in order: `enable()` now returns what really happened ("dark mode was already on",
  "volume set to 0% (it was 44%...)"); the volume is now set to an **exact level** through
  Windows Core Audio (`pycaw`, `JARVIS_SLEEP_VOLUME_PERCENT`, default **0** = silent, by explicit
  user request) *after* the spoken confirmation, the exact previous level is stored in
  `sleep_state.volume_level`, and `disable()` restores it. If pycaw/audio control is unavailable it
  falls back to 8 relative key presses (`volume_steps`), and a state left by the older version
  (steps only) still restores that way. pycaw is a no-op under pytest (`PYTEST_CURRENT_TEST`) so
  tests can never change the real machine volume. Consequence to remember: at 0% even urgent
  spoken alerts are silent until Sleep Mode ends (they still reach the recap).
- **Dark mode not visibly switching (2026-09-19, user report):** the registry write always succeeded
  (verified live: a fresh WinRT `UISettings` reports the app background flipping light->dark on the
  write alone, and the taskbar/Start follow), but running apps (Explorer, browsers, editors) only
  re-read the theme on `WM_SETTINGCHANGE("ImmersiveColorSet")`, which Windows Settings sends and
  Jarvis did not. `_set_dark_mode` now broadcasts it (`_broadcast_theme_change`, a no-op under
  pytest). Not confirmable without eyes on the screen: if apps still don't switch, the next suspect
  is the app itself ignoring the OS theme.
- **Removed at the user's request (2026-09-19): the wake-up alarm and distraction-site blocking.**
  Gone: `schedule_sleep_wakeup` tool, `check_wakeup`, the volume ramp, the hosts-file redirect
  (`JARVIS_SLEEP_BLOCK_DOMAINS`), and the scheduler tick call. Site blocking was the only reason
  Jarvis would need admin rights, so it keeps running as a normal user; no Sleep Mode step needs
  elevation now. Legacy columns (`wake_time`, `hosts_blocked`, ...) remain in `sleep_state`,
  unused. Sleep Mode/nap mode now ends only when the user says so.
- **Hotkeys (2026-09-19):** push-to-talk defaults to **Right Shift**, the typed-command hotkey to
  **Left Ctrl** (hold 2s). Left Ctrl is also used for shortcuts; a 2s hold is unlikely but possible
  while dragging with Ctrl held — change `JARVIS_TEXT_HOTKEY_KEY` if it misfires.

## Sleep Mode mail take-over (2026-09-19)

- `jarvis_sleep_mail.py`, ticked from the scheduler (`_sleep_mail_tick`): **only while Sleep Mode is
  on**, every 15 min (`JARVIS_SLEEP_MAIL_INTERVAL_MIN`; first check 15 min after it starts; as of
  2026-09-19 — was 30). Once a check finds a real inbound message it speeds up to every 2 min
  (`JARVIS_SLEEP_MAIL_ACTIVE_INTERVAL_MIN`) until 20 min pass with nothing new
  (`JARVIS_SLEEP_MAIL_ACTIVE_WINDOW_MIN`); any non-self sender triggers it, family or not. It
  searches the Gmail inbox (via the existing Gmail MCP) for mail that arrived since Sleep Mode
  began. **Family** senders get a reply sent *as Jarvis* ("I'm Jarvis, <name>'s assistant, they're
  asleep"), continuing the conversation across cycles; everything goes in the wake-up recap's
  important section. Non-family senders get one classification call over sender+subject only;
  critical ones (security/payment/deadline/emergency) are reported, never answered.
- **Explicit user decisions (2026-09-19):** reply scope is "open conversation" (highest-risk
  option, chosen knowingly over acknowledge-only); the family list is read from Jarvis's own memory
  (non-superseded `memory_facts` rows with category `relationship` that contain an email address);
  failed sends retry every 1 min, up to 5 retries (6 attempts) — implemented for these replies only
  (`send_with_retry`); an agent finishing during sleep is held for the recap instead of spoken at night.
- **Guardrails that stay regardless:** exact-address match only; the user's own addresses (from
  `user_profile`/`user_email` facts/`JARVIS_OWN_EMAILS`) are never replied to; `JARVIS_SLEEP_FAMILY_EXCLUDE`
  removes addresses; 6 replies per sender per night (`JARVIS_SLEEP_MAIL_MAX_REPLIES`); every reply
  carries a disclosure signature; the prompt forbids commitments, private info and claiming actions,
  and avoids gendered pronouns for the user. Messages are marked handled in `sleep_mail_handled`
  (no double replies across restarts); replies logged in `sleep_mail_replies`. Both tables are new.
- **Attachments (family replies only):** up to 3 per email, each <= 8 MB, downloaded via the Gmail
  MCP into `.cache/sleep_mail_att/<id>/` and deleted right after. Text/md/csv/json and .docx are read
  as text; PDFs via `pypdf` text, and scanned/handwritten PDFs (no text layer) plus png/jpg/gif/webp
  are sent to the model as `document`/`image` blocks (`jarvis_gemini` maps both to `inlineData`).
  Anything else (e.g. .exe) is never opened and is reported as unreadable. Verified live on a real
  5-page scanned PDF (summarised correctly, no send). **Data exposure:** attachment content goes to
  the active brain; if that is Gemini's free tier it may be used to improve Google products.
- **Open items:** Dad Jacob's address (`ayojacobgo@gmail.com`, same as the Claude account email) was
  confirmed by the user as his on 2026-09-19 and is on the family list; Racheal's old address was
  superseded in memory the same day (`rachealpower25@gmail.com` is the true one). An "error" that
  actually delivered would send a duplicate. Real emergencies are recorded and the sender is told to
  call directly, but Jarvis does not wake the user. Live-verified read-only (search, parse, read,
  send_email schema) against the real Gmail MCP; **no real send was made** — the first real send is
  untested. Tests: `test_sleep_mail.py`. Push-to-talk default moved to Right Shift the same day.

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

## Image download (2026-09-19)

- `download_image(url, filename?, referer?)` (`jarvis_image_download.py`, tests in
  `test_image_download.py`) saves ONE image to `JARVIS_IMAGE_DIR` (default `~/Pictures/Jarvis`).
  Flow: the Playwright `browser` MCP finds the image URL on the page (Pinterest etc.), this tool
  fetches it — deliberately not via run_shell/run_python. Guardrails: http(s) only, private/
  loopback hosts refused (re-checked on every redirect), must be a real raster image by
  content-type AND magic bytes (SVG refused), 25 MB cap, caller picks a name never a path, never
  overwrites. `i.pinimg.com/236x|736x/` URLs are upgraded to `/originals/` with fallback to the
  given size. Verified live against a real public PNG; **not verified against a real Pinterest
  session** (login wall / bot checks are the likely failure; the Playwright profile needs a
  one-time manual sign-in). Pinterest's ToS restricts automated scraping — keep to one image per
  request, personal use.

## Standalone launch (2026-09-19)

- `Jarvis.vbs` starts `python -u jarvis.py` hidden via `cmd /c` (a hidden *console* rather than
  `pythonw`, because pythonw has no valid stdio handles and breaks `subprocess` calls that pipe
  only some streams), logging to `jarvis_standalone.log`. `stop_jarvis.ps1` kills python/cmd
  processes whose command line has `jarvis.py`. `install_shortcuts.ps1` writes `jarvis_python.txt`
  (PATH's `python` may be the Store stub), makes Desktop shortcuts, and `-Autostart` adds a
  Startup-folder shortcut (opt-in; not enabled). VBScript gotcha: `log` is reserved.
- Verified live: launch, single hidden process, log output, stop script, relaunch. Not verified:
  the Autostart shortcut across a real sign-in, or push-to-talk/hotkeys from the hidden process
  over a long session.

## Voice restart (2026-09-19)

- `restart_jarvis(force?)` (`jarvis_restart.py`, `test_restart.py`): "restart yourself" reloads new
  code. Order: refuse if `_RUNNING_BACKGROUND_PROCS` is non-empty (unless `force`) -> `compile()` every
  `jarvis*.py` and abort on a syntax error, before stopping anything -> spawn a hidden PowerShell
  helper that waits for this PID then runs `Jarvis.vbs` -> after `MIN_DELAY_S` (8s, so the spoken
  goodbye happens) and once `jarvis_speaking` clears, kill MCP/npx children and `os._exit`.
  The new copy is always the standalone hidden one, even if the old one was started from VS Code.
- **Live-found bug:** the helper must NOT use `DETACHED_PROCESS` — with it PowerShell never
  launches the new Jarvis (verified by comparing flag variants); `CREATE_NO_WINDOW` alone works and
  still outlives the parent. Also `py_compile` to `NUL` fails on Windows; use `compile()`.
- Verified live end to end (dashboard command -> new PID, MCP servers reconnected). Known soft
  spot: the model passed `force: true` unprompted once (harmless with no tasks running); the
  guard is prompt-level (description says leave false), not code-enforced.

## Face recognition (2026-09-19)

- `jarvis_face.py` + `test_face.py`: a **local-only** identity/context layer (insightface 2.0
  `buffalo_l`, CPU/ONNX; ~0.3-0.5 s per frame, so it is polled, never streamed). Additive: it does
  not touch the agent loop, the catastrophic gate, Sleep Mode or any input path. Off by default:
  `JARVIS_FACE_ENABLED=1` (only then are the `enroll_face`/`list_faces`/`delete_face` tools even
  advertised to the model, so the cached tool prefix is unchanged otherwise).
- **A face is a personalization signal only.** It never confirms, approves or unlocks anything and
  has no path into `_pending_action`/`_execute_confirmed_action`. Keep it that way in later phases.
- **Storage is outside the repo and OneDrive**: `%LOCALAPPDATA%\Jarvis\face.db` (+ `face.key`,
  `models/`); `JARVIS_FACE_DIR` overrides, but a path under OneDrive is refused (a synced biometric
  DB would leave the machine). Embeddings are AES-GCM encrypted (AAD-bound to the column) with a
  random key wrapped by **Windows DPAPI** (tied to this Windows login; ctypes, no new dependency).
  No camera frame is ever written to disk. Tables: `face_profiles`, `face_events` (audit; never
  holds an image or embedding, survives profile deletion), `face_settings` (e.g. `paused`).
- **User decisions (2026-09-19)**: low-duty polling (5 s) paused during Sleep Mode; higher-accuracy
  library (insightface, `buffalo_l`); Integrated Webcam (index 0, `JARVIS_FACE_CAMERA_INDEX`);
  exactly **one** enrolled person, the owner/Admin - nobody else is ever enrolled (a second
  `enroll_face` is refused; delete first to re-enroll); roles Admin/User/Guest as proposed
  (Guest/unknown = quiet mode only, never a refused command); unknown faces get an event row
  **and a saved picture** (see limits below); enroll/delete refused from phone.
- **Command source**: `handle_text_command` is now a thin wrapper that records the source in a
  thread-local (`_current_command_source()`); only `voice`/`text`/`dashboard` may enroll/delete.
  Phone, and any thread with no user command (scheduled skills, background tasks) are refused.
- **Model download** (`download_models`): one-time 288 MB fetch from insightface's GitHub release,
  size + SHA-256 pinned in code (trust-on-first-use, recorded 2026-09-19); extracts only the
  detector + ArcFace files. insightface's own downloader does no integrity check and a dropped
  connection left a silently truncated file (seen live) - don't switch back to it.
- **Liveness is a speed bump, not a guarantee**: head-turn swing from the detector's 5 landmarks
  (`JARVIS_FACE_LIVENESS_SWING`, default 0.30, **not yet tuned on a real head turn**). It stops a
  held-still photo; a replayed video defeats it, which is why a match never gates anything.
- Enrollment consistency check uses the *minimum pairwise* cosine between samples (>= 0.45);
  comparing to the centroid let a 2-vs-3 mix of different people through (caught by a test).
- **Phase 2 (recognition + policy), shipped**: a daemon thread (`start_polling`, started from
  `main()` only when enabled) opens the camera, grabs ONE frame, releases it - every
  `JARVIS_FACE_POLL_S` (5s), or `JARVIS_FACE_SETTLED_POLL_S` (15s) once the owner has been steadily
  in view with nobody else. Each look is ~1.5s (camera LED on) and ~0.4s CPU. Match = cosine to the
  owner's stored embeddings >= `JARVIS_FACE_MATCH_THRESHOLD` (0.50, strict; live match was 0.83).
  It never polls while paused, in Sleep Mode, with no one enrolled, or while an enrollment holds the
  camera. State changes (not every poll) go to `face_events`: owner_arrived/left, unknown_seen/
  left, camera_covered/uncovered/unreachable/restored, paused/resumed.
- **Group-safe mode**: an unrecognized face seen on 2 consecutive polls holds *non-urgent spoken
  proactive messages* (queued with `group_safe: True`; `flush_pending_notifications` leaves them
  while the stranger is still there, and `_face_release_held_notifications` reads them out ~60s
  after they leave). Urgent messages still speak (same rule as Sleep/Focus Mode). It **never**
  refuses or alters a user command. Presence older than 90s is ignored (fail open).
- **Prompt line** (`system_prompt_context_line`, volatile block only, and part of the reply-cache
  key): who is present, and "keep replies discreet" when a stranger is in view. It says explicitly
  that it is never a reason to skip a confirmation.
- **Greeting**: "Good morning/afternoon/evening, <name>." on arrival, at most once per 30 min (cooldown
  persisted in `face_settings`, so a restart doesn't re-greet). Skipped - not queued - during
  Sleep/Focus Mode or with a stranger present.
- **Unknown-face pictures (built as approved)**: face crop only (max 256px JPEG), AES-GCM
  encrypted in `face_snapshots`, one per person per 10 min (dedupe by embedding, held in RAM only,
  never persisted), only for confident detections (score >= 0.70), auto-delete after 14 days
  (`JARVIS_FACE_SNAPSHOT_DAYS`), cap 200, `JARVIS_FACE_SAVE_UNKNOWN=0` disables. Never sent to a
  model. API only so far: `list_snapshots`/`get_snapshot`/`delete_all_snapshots` (dashboard is Phase 3).
- **Camera covered** = near-black AND flat frame (a dark room has detail, so it doesn't count);
  one notice per cover. **Unreachable** = 5 consecutive failed opens (another app such as Zoom may
  hold it); one notice per outage, then it backs off to one try a minute.
- Tools added: `who_is_here`, `face_privacy` (pause/resume/status; pause works from any source since
  it only increases privacy, resume is refused from phone and unattended tasks).
- **Live-found bug (2026-09-19)**: a camera opened cold returns a washed-out first frame (brightness
  ~100 vs ~58 settled) and no face was found in it - and every poll is a cold open, so polling would
  have missed the owner every time. `_open_camera` now discards frames until brightness settles
  (max 45 frames). Unit tests alone could not have caught this; keep a live check when touching it.
- **Known gap**: deleting the only profile re-opens the bootstrap window - anyone at the PC could
  then enroll themselves as Admin. Harmless while face grants no power; revisit if that changes.
- **Phase 3 (dashboard Identity tab), shipped**: bottom-panel "Identity" tab (`dashboard_static/`,
  `/api/faces*` in `jarvis_dashboard.py`, `face` module injected like the other providers). Shows
  who the camera sees, the enrolled profile with a plain-language consent summary (what is stored,
  never stored, who can read it, how consent was given), unknown-visitor pictures, the recognition
  event stream with a kind filter, a Pause/Resume camera button, "Export my data", "Erase profile"
  and "Delete all pictures" (each behind a browser `confirm()`; the API also needs `?confirm=true`,
  so a bare DELETE erases nothing). Live-refreshes on a `face_event` WebSocket message
  (`face.set_event_hook`, labels only) and every 10s while open.
- **Identity API rules**: every `/api/faces*` route rejects a non-loopback `Host` header (403) as a
  DNS-rebinding defence - pictures and erase are the most sensitive things this dashboard serves.
  Responses are `Cache-Control: no-store`; images add `nosniff`; **no route ever returns a face
  vector**. Pictures are only put in the page while the Identity tab is open (an `<img>` loads the
  moment it is in the DOM). With the feature off, `/api/faces` returns `{"enabled": false}` and
  touches no disk (no `face.db` on a machine that doesn't use it).
- **Export excludes** the face vectors (biometric, useless to the person) and every unknown-visitor
  picture (those are other people's). Exporting is itself logged as an `export` event. Erasing a
  profile keeps the audit events (no biometric data in them). Recognition events live in their own
  stream on this tab, not in the general Audit Trail.
- **Phase 4 (hardening), shipped** - a self-audit of Phases 1-3 found and fixed real defects:
  1. *Retention wasn't enforced*: unknown pictures were only pruned when a **new** one was saved,
     so an expired picture could sit indefinitely. `housekeeping()` now runs hourly from the poll
     thread (pictures 14 days, events `JARVIS_FACE_EVENT_DAYS` = 180).
  2. *Enroll failed spuriously* whenever a poll held the camera (~30% of tries): it now waits up to
     `CAMERA_WAIT_S` (6s).
  3. *A missing `face.key` silently minted a new key*, permanently orphaning every stored vector
     and picture. `_key()` now refuses if encrypted rows exist; `health_problem()` surfaces it in
     the Identity tab (red note) instead of failing quietly.
  4. *Erasing the profile left "Hero is at the computer"* in the prompt for up to 90s; `delete`
     now resets live presence.
  5. Polls are serialized (`_poll_lock`): the poll thread and a voice `who_is_here` no longer
     interleave state updates.
  6. Dashboard state-changing `/api/faces*` calls also require a loopback `Origin` when one is sent
     (a valid-Host request from another site is otherwise possible from a browser).
- **Gate isolation is now enforced by a test** (`test_face_code_cannot_reach_the_confirmation_gate`,
  AST-based): `jarvis_face` may not reference `_pending_action`/`_execute_confirmed_action`/
  `skip_confirmation`/`_CATASTROPHIC_PATTERNS` or import `jarvis`, and `jarvis.py` may reference
  `face` only from an allowlist of reviewed functions (tool dispatch, notification hold, greeting,
  prompt line, startup). Adding face to any other function fails the test - review it first.
  Another test pins that no image/frame file is ever written to the data dir (only `face.db*` and
  `face.key`).
- **Deliberately NOT built: PIN / voice as a second factor.** It only matters if face ever gates an
  action, and nothing does (face is personalization only). If that ever changes it is a new
  feature needing its own review (and a secret store), not an extension of this one.
- **Tuning tool**: `python jarvis_face.py calibrate [--seconds N]` - a dry run of the enrollment
  liveness check that stores NOTHING (no profile, event or image); prints the head-turn swing and
  says how to tune `JARVIS_FACE_LIVENESS_SWING`. **Live finding (2026-09-19)**: sitting roughly
  still produced a swing of 0.21 vs the 0.30 default, so natural head sway alone is most of the
  way to the threshold - a hand-held photo would jitter similarly. Liveness here is a speed bump
  against a *static* photo only; do not raise its trust. Consider a higher default (~0.40) once the
  owner's real head-turn swing has been measured.
- **Code review of the whole feature (2026-09-19)** - a line-by-line second pass found 11 more
  defects, all fixed and each pinned by a test:
  1. *Model-integrity bypass*: `FaceAnalysis` silently downloads a missing pack itself, with no
     hash check (e.g. polling after the model dir was deleted). `_InsightEngine` now refuses if
     `models_ready()` is false; `health_problem()` reports missing files.
  2. *Two racing enrollments could create two profiles* (the one-person rule was checked before
     waiting for the camera lock). Now re-checked under the lock and the INSERT is atomic
     (`... WHERE NOT EXISTS`).
  3. *`delete_face(confirm=true)` was prompt-only* (a model has passed `force=true` unprompted
     before). The code now requires an earlier unconfirmed call within 120s in a **different user
     message** (`turn_id` = the message text); the dashboard's click-through uses `ui_confirmed`.
  4. *WebSocket `/ws` had no Origin check* while now carrying presence events (`face_event`); a web
     page could listen in. A non-loopback Origin is refused (no Origin = non-browser, allowed).
  5. Camera stayed open if a warm-up read raised; now released.
  6. Poll thread gave up for good after 3 failures; now backs off 5 min and keeps trying.
  7. A slow greeting/notice held `_poll_lock`, freezing `who_is_here` and the dashboard's
     pause/erase; hooks now run after the lock is released, and pause/erase wait for an in-flight
     poll so it cannot write stale presence back over the reset.
  8. First-time key creation was not locked (two callers could each mint a key, orphaning data).
  9. ONNX inference burst across every core and could stutter the voice loop/Whisper: capped at
     `JARVIS_FACE_THREADS` (2; measured 292ms vs 302ms at 4 threads, so it costs nothing) and the
     poll thread runs below normal priority.
  10. Model extraction was non-atomic (a killed extract left a truncated `.onnx` that
      `models_ready()` accepted) and hashing read ~290MB into RAM; now write-aside + rename, chunked.
  11. The greeting could talk over a reply already playing; skipped while `jarvis_speaking`.
- **Held for the owner's decision (not applied - it loosens matching)**: when the owner looks down or
  turns away the match can dip under 0.50, and two polls in a row (~10s) then declares an "unknown
  person": group-safe mode holds non-urgent speech (including reminders) and a picture of the owner
  is saved. A "recently seen owner" hysteresis (accept >=0.35 when exactly one face is in frame and
  the owner was seen in the last 2 min) would fix it at the cost of a looser match. Untested on real
  data - tune `JARVIS_FACE_MATCH_THRESHOLD` from real `unknown_seen` confidences first.
- Also open: reminders are held by group-safe mode like other proactive speech (the owner's decision
  was "hold proactive messages"); whether time-critical reminders should bypass it is a policy call.
- **Stranger -> Telegram "disable reminders?" (2026-09-19, `jarvis_guest_reminders.py`,
  `test_guest_reminders.py`)**. When the face poll declares a stranger (the new `stranger` hook,
  once per visit) Jarvis texts the owner on **Telegram only** (never the ntfy topic, whose name is
  a shared secret) "...Should I disable reminders while they're here? Reply yes or no." This is a
  deliberate, user-requested exception to "no unsolicited phone pushes"; nothing else changed and
  `JARVIS_PHONE_PROACTIVE_NOTIFICATIONS` still gates everything else. No picture or face data is
  sent, only that text. Owner's decisions: **held until they answer**; "yes" = disabled (reminders
  are **held, never dropped, and each is also texted** to Telegram); "no" = held ones are read out
  and reminders speak normally for that visit; when the stranger leaves after a "yes" Jarvis asks
  "They've left. Turn reminders back on?" (yes -> back on and the held ones are read out; no -> stay
  off; the tool `reminders_mode` on/off/status works from any channel). State machine in the module
  docstring; state is in memory only, so a restart returns to normal (never silently off forever).
  One question per visit and at most one per 10 min (flapping visitor -> no Telegram spam).
- **Reminder specifics**: a held reminder also gets **no Windows toast** (the banner would show its
  text on screen in front of the visitor - `_check_due_reminders` now checks `_reminders_held_now`).
  Default (no answer/policy, e.g. Telegram down): a visitor holds non-urgent reminders like other
  proactive speech; urgent ones still speak. Once the owner says "disable", urgent ones are held too.
- **Phone-reply safety**: the yes/no is intercepted at the top of `_handle_text_command_impl`,
  phone source only, whole-message match only ("yes", "no thanks", "keep them on"; "no problem,
  open notepad" is NOT an answer - strict parser, unlike the gate's substring `_is_confirmation_yes`).
  It runs **before** the catastrophic gate on purpose: a "yes" meant for this question must never
  approve a staged shutdown/format. If one is staged it is **cancelled** (never run) and the reply
  says so. Pinned by a test. Only Telegram-configured setups get the question.
- **Away mode (2026-09-19)**: `away_mode` tool (on/off/status, also a dashboard button/card). Off by
  default and persisted (`face_settings.away_mode`). While ON, if the camera CAN see and the owner is
  not recognized for **2 min** (`JARVIS_FACE_AWAY_GRACE_S`, floor 10s) the computer is locked via the
  existing `_system_action_lock` (LockWorkStation), after a spoken warning **15s** before
  (`JARVIS_FACE_AWAY_WARN_S`, 0 disables) that is cancelled if the owner is recognized again.
  **Face only ever locks; nothing in the face module can unlock** (AST test, no identifier
  containing "unlock"; the injected action is checked to be LockWorkStation).
- **Away mode never fires blind** (owner's decision): covered lens, unreachable/busy camera (a
  Zoom/Teams call), pause, Sleep Mode, no enrollment, or an already-locked session all reset the
  clock and never lock. While the lock screen is up polling stops (`_session_locked()` via
  OpenInputDesktop; **not verified against a real locked session** - only that it returns False
  when unlocked). Polling runs at the fast 5s cadence while the clock is running (a 15s cadence
  would delay the lock). `on` needs an enrolled face; `off` (and re-enabling the camera) must come
  from the PC, not the phone; erasing the profile turns it off.
- **Known limitation of away mode**: it locks when the owner is *not recognized*, so a poor
  recognition (looking down, glare) for 2 min while working would lock the PC - the 15s warning
  is the mitigation. The same false-negative weakness as the held "false unknown" item above. A
  faster lock for "stranger present + owner absent" was deliberately NOT added: a false "unknown"
  on the owner would then lock in seconds. Using keyboard/mouse activity to veto a lock was
  considered and not built (a stranger typing would veto it too) - an open policy question.
- Status: Phases 0-4 + review + stranger/reminders + away mode shipped (face tests 107, +45 in
  `test_guest_reminders.py`; 345 total). Verified live: real model + camera + the full poll pipeline
  against a throwaway temp profile (re-run after the review fixes); the Identity tab in headless
  Chromium against synthetic data; `calibrate` on the real webcam. **Not verified live**: the real
  Telegram question/answer round trip, a real away-mode lock (would lock the owner's PC), the lock
  probe on a locked session. **Not verified live**: a real `enroll_face` by
  voice (writes a real biometric profile - the owner should do it), the head-turn threshold on a
  deliberate turn, an actual stranger (group-safe/picture path is unit-tested only), greeting
  audio, covered-lens detection on the real webcam, the tab against real data.

## Full Autonomy stack (2026-09-20)

- Full write-up: `AUTONOMY.md` (incl. a "How to verify" section). Code: `jarvis_autonomy.py` (commitments/projects,
  policy engine, tick, campaigns, planner, inbound hook, file/mail bridges, log/why), `jarvis_autonomy_skills.py`
  (composable skills), `jarvis_dynamic_tools.py`, `jarvis_memory_consolidation.py`, the dashboard "Autonomy" tab
  (`dashboard_static/autonomy.js`, `/api/autonomy*`, `/api/dynamic_tools*`). Tests: `test_autonomy.py` (137; whole
  suite 483).
- **PERMISSION MODEL — explicit user decision (2026-09-20): FULL AUTO-ACT, except catastrophic actions.** The
  user accepted the risks of full system access and autonomous decision-making. Once autonomy is ON it does not
  ask: `evaluate_policy` returns `auto_act` by default for every non-catastrophic action type (calendar, reminder,
  email, file_op, background_task, notification) from **any** source (own words, mail, Telegram, Discord, files),
  gated only by a confidence floor (`JARVIS_AUTONOMY_AUTO_MIN_CONF`, 0.7; below it the item is only *recorded* as a
  card). Learned rules may auto-act on any type; budgets are soft (5x runaway breaker only). **Do not re-introduce
  ask/confirm steps for non-catastrophic actions.** Only the existing catastrophic gate (`_CATASTROPHIC_PATTERNS`/
  `_pending_action`, restored to its original form in `_queue_pending_confirmation`) still needs a yes/Approve; an
  autonomous run that reaches a catastrophic command STAGES it like any other (pinned by tests, and the AST test
  still forbids the autonomy modules from referencing the gate or importing `jarvis`).
- Still kept: `JARVIS_AUTONOMY_DISABLED=1` hard kill, dry-run, and **ON by default** (user decision 2026-09-20: `enabled()` defaults to on, `JARVIS_AUTONOMY_ENABLED=0` starts it off; the first start therefore acts for real on mail/files/commitments, so use dry-run first if unsure), and
  three settings that stay **dashboard-only** because they are configuration, not actions: turn autonomy ON, write/
  loosen policy rules, leave dry-run (`HUMAN_ONLY_ACTIONS`). Also kept from the security audit: exact-sender rule
  matching, text sanitising, the dynamic-tool sandbox hardening (defence in depth, **not a security boundary**),
  CAS approve/dismiss, kill-switch cancelling queued work, retention pruning, bounded workers, `record_history=False`
  for autonomous agent runs. Known consequence: a confident prompt-injected instruction in an email CAN now cause
  a calendar event / reminder / email / background task; the Activity log and the off switch are the mitigation.
  Another: a stray spoken "yes" could confirm a catastrophic action an autonomous run staged (the dashboard shows it).
- **Work packages shipped** (details in `AUTONOMY.md`): (1) full inbound perception — one hook
  `process_inbound_message_for_events(subject, body, sender, source, message_id)`; call sites: sleep-mail now passes
  the **full body** (it reads each non-family message), a Gmail inbox poll (`_autonomy_poll_mail` -> `_inbox_poll`,
  `JARVIS_AUTONOMY_MAIL_POLL_MIN`, default 10, 0=off), Telegram/ntfy messages from the user go through
  `after_turn`, Discord has no inbound handler (hook is ready), file-watcher bridge (`_file_scan`); (2) smarter
  extraction gate + fuzzy dedupe/merge + quality rules + semantic recall; (3) observability: `log`/`why`/`speak_log`
  tool actions, `GET /api/autonomy/log`, filterable Activity log UI, richer `autonomy_decisions` columns; (4)
  direct Calendar MCP create-event (`build_calendar_args` maps onto the tool's own schema) with agent-loop fallback;
  (5) composable skills (`autonomy_skill` tool, `autonomy_skills` table, auto-mined from 3 identical repeats, only
  existing tools, re-validated every run); (6) deadline intervention at 24 h/2 h/overdue + campaign state machine
  `planned -> running -> done | blocked | cancelled` with 3-attempt recovery.
- **Injection hardening + file organising (2026-09-20, ALWAYS ON with autonomy — no feature flags, by user
  request)**: untrusted text is framed (`<<<UNTRUSTED_INBOUND ...>>>`), sanitised (`neutralize_injection`) and
  length-capped; third-party (`email`/`message`) calendar/email/file_op/background_task need confidence >= 0.85
  (`JARVIS_AUTONOMY_INBOUND_AUTO_MIN_CONF`) unless a clear datetime+title meeting, and *every* action from a
  message with injection-like text does; optional `JARVIS_AUTONOMY_EMAIL_AUTO_ALLOW` (empty = unrestricted).
  `jarvis_autonomy_organise.py` files new files from Downloads/Desktop by built-in rules (move/copy only, never
  delete/overwrite, realpath + top-level + settle checks, logged, dry-run-safe); the watcher baselines a newly
  added folder (`add_path(..., baseline=True)`). Do not add enable flags for these. Residual injection risk is
  real and documented in `AUTONOMY.md`. Suite: 538 tests (1 skipped: symlinks need privileges on Windows).
- **Audit pass 2 (injection + organise)** — details in `AUTONOMY.md`. Rules to keep: the sanitiser lives in
  `jarvis_untrusted.py` (NFKC + invisible-char strip + mixed-script look-alike folding) and is used by the core and
  sleep-mail; anything third parties control (mail, file names, project names) is neutralised at creation AND at
  render into any prompt; recorded inbound items are quarantined so the deadline path cannot act on them; the file
  scan covers every event on a worker (25/tick, single-flight); failure notices are throttled
  (`_notify_throttled`); organise skips files Jarvis just saved. Suite: 554 tests.
- **Audit-and-fix pass (2026-09-20, after the permission change)** — details in `AUTONOMY.md`. Rules to keep:
  dry-run must never consume real work (own `dry_*` bookkeeping + replay on leaving dry-run); old learned ask
  rules are migrated to auto_act; learned `ignore` lapses (30 d) and never applies to `deadline:*`; a dismissed card
  never silences a confident action; slow work (agent-loop actions, mail poll) is never run inline on the tick
  thread (auto queue + bounded workers, 6 max); capacity limits wait rather than fail; the kill switch is enforced
  inside `_run_action`; campaign steps run without approval (approve_campaign = un-pause); skills never mine
  secret-bearing tools. Suite: 507 tests green (test_autonomy.py 160).
- **Data exposure:** the mail poll and inbound hook send message bodies to the active brain (Gemini free tier may use
  it for Google product improvement). Turn the poll off with `JARVIS_AUTONOMY_MAIL_POLL_MIN=0`.
- **Deviations from the spec, on purpose:** tables are `autonomy_projects` / `autonomy_project_actions` (jarvis.py
  already owns a `projects` table); extra `autonomy_suggestions` (cards + auto queue), `autonomy_seen_messages`,
  `autonomy_skills`, `autonomy_patterns`; dynamic tools are pure computation only, real side effects go through
  skills; the tick rides the existing 60 s scheduler loop.
- **Not verified live:** a real model extraction, the Gmail poll against a real inbox, the Calendar MCP's actual
  create-event schema (`build_calendar_args` is schema-driven and falls back to the agent loop), the new dashboard
  sections in a real browser, and a real end-to-end auto-acted calendar event. Follow "How to verify" in
  `AUTONOMY.md` (dry run first).

## Speed Upgrade: Deepgram voice pipeline (2026-09-22)

Full write-up: `SPEED.md` (env vars, backend order, how to measure a before/after). Off by default —
no `DEEPGRAM_API_KEY` in `.env` means voice behaves exactly as before (local Whisper + Fish -> Piper).

- **New modules**: `jarvis_stt_deepgram.py` (Nova-3, `POST /v1/listen`), `jarvis_tts_deepgram.py`
  (Aura 2, `POST /v1/speak`), `jarvis_latency.py` (per-voice-command latency tracker + a small
  deterministic intent classifier). Both Deepgram modules use stdlib `urllib` directly — same
  pattern as jarvis.py's existing `_fish_audio_synthesize` — not the `deepgram-sdk` package, because
  the installed/latest SDK (7.x) doesn't match the API the task's snippets assumed (3.x) and the
  REST endpoints are simple enough not to need it. `requirements.txt` is unchanged.
- **STT**: `jarvis.transcribe_pcm()` tries Deepgram first when `JARVIS_STT_BACKEND` allows it and a
  key is set, falling back to local Whisper on any failure, exception, or a transcript below
  `JARVIS_DEEPGRAM_STT_MIN_CONFIDENCE` (0.6). The push-to-talk capture path is untouched — the whole
  hold-to-release buffer is still captured first, then sent to Deepgram's *pre-recorded* endpoint in
  one shot (not a live WebSocket); true streaming STT would mean rewriting audio capture, which the
  task said to preserve.
- **TTS**: `jarvis.speak_text()` now cascades Deepgram Aura 2 -> Fish Audio -> Piper (was Fish ->
  Piper). Each engine's audio is cached under its own key in the existing on-disk TTS cache, same as
  before. A `jarvis_cache.CircuitBreaker` (new, shared helper) trips each backend after 3 consecutive
  failures and cools down 120s, so an outage is skipped fast instead of a timeout on every command.
- **Sentence-level TTS pipelining**: a reply over `JARVIS_TTS_SENTENCE_STREAM_MIN_CHARS` (120 chars)
  is split into sentences (`jarvis._split_sentences`) and spoken one at a time; the *next* sentence
  is synthesized on a background thread while the current one plays, so time-to-first-audio is
  bounded by one sentence instead of the whole reply. No real token-level streaming from Claude was
  added (`run_agent_loop` still returns the full reply text) — see SPEED.md for why that specific
  piece was left out.
- **Filler phrase**: if a voice/dashboard command hasn't spoken anything within
  `JARVIS_TTS_FILLER_DELAY_S` (2.5s default), Jarvis says "One moment." once
  (`jarvis._speak_filler_if_slow`); no cancellation logic needed since the phrase is short and gets
  TTS-cached after first use.
- **Latency logging**: every voice command logs one grep-able `latency stt=.. ttft=.. tts=.. e2e=..
  stt_backend=.. tts_backend=.. intent=..` line (`jarvis_latency.py`); `latency.current()` is `None`
  for text/dashboard/phone commands (no capture-end to measure from), and every call site handles
  that. `jarvis_latency.classify_intent()` logs a cheap regex-based intent
  (time/date/volume/open_app/timer_reminder/complex) but does **not** route to a different model —
  `CLAUDE_MODEL` already defaults to Haiku 4.5, so there's no cheaper model left to route simple
  intents to; this was a deliberate scope cut, not an oversight.
- **Privacy**: with Deepgram enabled, microphone audio and spoken-reply text leave the machine for
  Deepgram's API — same category of exposure as Fish Audio (already documented above), just a second
  cloud vendor. Confidence gating and the circuit breaker are latency/quality safeguards only; they
  never touch the confirmation gate or any tool permission.
- Tests: `test_deepgram_voice.py` (41, no real network — every `urlopen` call is monkeypatched).
  `test_cache.py`'s existing Fish/Piper tests were unaffected; its shared `jarvis` fixture now also
  zeroes both Deepgram modules' `DEEPGRAM_API_KEY` so a real key in the dev machine's `.env` can't
  change those pre-Deepgram tests' behavior.
- **Not verified live** (needs a real `DEEPGRAM_API_KEY` + microphone): actual Nova-3 transcription
  accuracy/latency, actual Aura 2 audio quality, real end-to-end voice-in -> first-audio-out timing.
- **Audit-and-fix pass (2026-09-22)**, full write-up in SPEED.md — an adversarial re-read found and
  fixed 5 real issues, all pinned by new tests: (1) Whisper was preloaded eagerly at startup even
  when Deepgram was configured and healthy (`main()` now skips it whenever `_use_deepgram_stt()` is
  true — the same lazy-load-on-actual-fallback path as before, just no longer paid unconditionally
  at every restart); (2) `speak_text()`'s latency-log `tts_backend` latched to the *first* engine
  used instead of the *last* — a narrated line on Deepgram followed by a final reply that fell back
  to Piper mid-command used to log `tts_backend=deepgram`, a latency-lie, now fixed to update on
  every successful sentence; (3) the filler phrase ("One moment.") could fire after a mid-task
  narration had already spoken real content, since it only watched "command finished" — it now also
  backs off the moment `speak_text()` itself plays any audio, via a shared `threading.Event` reached
  through a per-thread signal (`jarvis._current_speak_signal()`); (4) the sentence-pipelining
  background thread's `next_thread.join()` had no timeout — now bounded by `PIPELINE_JOIN_TIMEOUT_S`
  (90s) as a defense-in-depth backstop; hitting it costs only that sentence's pipelining overlap,
  never the content (it's re-synthesized synchronously on the next loop iteration); (5) test gaps —
  STT circuit-breaker tripping/recovery and a real `TimeoutError` path weren't covered, now are.
  No catastrophic-gate, autonomy-permission, or fallback-removal changes were made.

## Cloud-latency pass (2026-09-22)

Full write-up in SPEED.md (env vars, protocol details, what was verified live, accepted edge
cases). Builds on the Deepgram REST work above; explicitly cloud-only per user instruction — no
new local/heavy models. New dependency: `websocket-client==1.9.0` (pinned in `requirements.txt`,
a small widely-used *synchronous* client chosen because it fits this codebase's threaded
architecture better than an async one). All four phases default **on** (explicit user decision,
"everything should be on by default, aware of the risk") and each independently falls back to the
exact proven non-streaming/full-tool path on any failure.

- **Phase A — streaming STT** (`jarvis_stt_deepgram.StreamingSession`): a live
  `wss://.../v1/listen` session opens at push-to-talk press (on its own thread so the capture
  loop is never blocked on the connect) and is fed every captured block while held; `feed()`
  only enqueues bytes so a slow connection can't stall audio capture. On release,
  `transcribe_pcm(stream_session=...)` finalizes it and uses the result if valid, else falls
  through to the existing REST-on-full-buffer path, then Whisper, exactly as before. Two races
  were found and fixed while building it: `feed()` calls before the connect resolves must be
  queued, not dropped; `finish()` must wait for an in-flight `start()` rather than racing ahead
  on a very short hold. `JARVIS_DEEPGRAM_STT_STREAM=1` (default). Verified live against the real
  API (a synthesized-audio round trip through the exact class, and the press-before-connect race
  against a real connection).
- **Phase B — streaming TTS playback** (`jarvis_tts_deepgram.StreamingSynthesis`, a *separate*
  Deepgram endpoint from the STT one): `speak_text()` tries this first for the sentence about to
  play right now, via a new `_play_pcm_stream` (`sd.OutputStream.write()` per chunk instead of
  `sd.play()` on a complete buffer) — first-chunk latency was ~0.3s into a ~1.3s utterance on a
  live test. Deliberately **never** used by the existing sentence-pipelining pre-fetch thread —
  that thread only fetches bytes, since if it also played audio it would fight the main thread's
  playback over the same device/lock and turn "synthesize ahead while this one plays" into
  waiting twice. `JARVIS_DEEPGRAM_TTS_STREAM=1` (default). Verified live: real audio played
  through actual speakers end-to-end.
- **Phase D — simple-intent fast path**: `time`/`date` skip the LLM call entirely (pure local
  clock read, `_deterministic_intent_reply`); `volume` and a *confidently named* `open_app`
  (re-checked against `ALLOWED_APPS` — `classify_intent`'s broad "open ..." regex is deliberately
  not trusted alone, so "open my email" still gets the full tool list) get a small reduced tool
  schema instead of the full ~100+ (`run_agent_loop(tools_override=...)`). The catastrophic gate
  is unaffected either way — it's enforced in `_execute_tool`, not by which tools were offered.
  `latency.path` logs which of `deterministic`/`reduced_tools`/`full` a command took.
- **Phase C — LLM token streaming to speech** (`jarvis._claude_stream_first_round`), the
  highest-risk piece, scoped narrowly: only the agent loop's first round trip, only when the
  reply will actually be spoken here (`narrate=True`, same condition as existing narration).
  Parses Claude's own SSE stream (`stream: true` on the same endpoint, no WebSocket needed) on a
  background thread, reconstructing the *exact* non-streamed response shape so every later round
  trip and all tool-result handling is completely untouched. Speaks each complete sentence as it
  arrives (composes with Phase B for free — a live sentence's audio can itself stream); stops
  speaking once a `tool_use` block starts (matches existing narrate semantics, just progressive)
  and flushes any held-back short fragment at that block's own end rather than the whole message's
  end — a real bug caught by testing (a short narration line right before a tool call was being
  silently dropped). On any failure (network, malformed SSE, Gemini as the active provider —
  Claude-only, checked and no-op'd rather than guessed at) it returns `None` and the same round
  trip is retried via the proven non-streaming call. `reply_already_spoken_via_stream()` (a
  per-thread flag, reset at the *start* of every command, not just read-and-reset at the end, so
  an unrelated exception can't leak it into the next command) stops the caller from speaking an
  already-streamed reply again; a streamed reply also skips `_summarize_for_speech`, which exists
  to soften a wait-then-shorten cost a live stream never had. `JARVIS_LLM_TTS_STREAM=1` (default).
  **Accepted rough edge**: a connection drop *after* some sentences already played will repeat the
  whole reply on retry — rare and bounded (a stutter, not silence/corruption), not worth more
  bookkeeping to avoid. **Test-safety note**: a fake `ANTHROPIC_API_KEY` + unguarded `narrate=True`
  would otherwise make a real network call — both shared `jarvis` test fixtures now default
  `JARVIS_LLM_TTS_STREAM=0`. Not verified live end-to-end (this session's Anthropic key has no
  credit balance, pre-existing and unrelated to this work) — confirmed instead that a real HTTP
  error from the API is handled identically by both paths, and the SSE parsing itself is covered
  by mocked tests built from Anthropic's documented event shapes.
- **Phase E**: nothing further needed — the filler-vs-narration fix and honest `stream`-vs-`rest`
  backend labels from the earlier audit pass already satisfy it.
- Tests: `test_deepgram_voice.py` grew from 41 to 90 (protocol tests for both new WebSocket
  classes, the streaming-vs-prefetch safety property, intent-routing, SSE parsing including the
  tool_use-interruption edge case, and the already-spoken-flag not leaking between commands).
  Full suite: 726 passed (the 4 pre-existing unrelated urgent-email-monitor failures untouched).
- **Audit-and-fix pass (2026-09-22, second pass)**, full write-up in SPEED.md — found one real
  High-severity bug: a multi-round command (streamed narration ending in a `tool_use`, then a
  normal final round) spoke the narration **twice** — once live during the stream, once again
  as part of the final reply, because the streamed text was folded into `reply_parts` regardless
  of whether the round continued into a tool call. Fixed to match the existing non-streamed
  narrate branch exactly: excluded from `reply_parts` whenever the round continues, only
  included (and only then marked already-spoken) on the round that actually ends the turn.
  Caught by a new test running a genuine two-round scenario — every existing test only exercised
  single-round streaming. Also fixed a stale comment in `main()`'s push-to-talk loop claiming
  `feed()` drops audio fed before the WebSocket connects, which was true of an earlier draft but
  not the shipped code (the queue-based design holds those bytes instead). Everything else
  audited clean with code-level evidence: chunks really do send during the hold, not only after
  release; no double `run_agent_loop` call from interim-vs-final transcripts; every streaming
  path (STT, TTS, Claude) has a bounded timeout with no infinite-wait path; the catastrophic gate
  is unreachable any differently through a reduced tool list or a streamed response than through
  the full non-streamed path (enforced in `_execute_tool`, not by which tools were offered or
  whether the round streamed); no `run_agent_loop` caller outside the direct
  `_handle_text_command_impl` path (scheduled skills, queued tasks, autonomous actions,
  background research) ever passes `narrate=True`, so streaming can never run on the scheduler
  or autonomy tick thread; no API key or secret appears in any new log line. No catastrophic-gate,
  autonomy-permission, or fallback-removal changes were made. Full suite green afterward.

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
| 7 (prompt caching for agent loop + plan steps) | Sonnet 5 | ~15 min | ~$0.50–$0.70 |
| 8 (multi-layer caching: TTS/reply/tool/summary/skills + 1h prompt TTL) | Sonnet 5 | ~40 min | ~$1.60–$2.20 |
| 9 (api_spend billing tool) | Sonnet 5 | ~10 min | ~$0.20–$0.30 |
| 10 (local spend tracking + dashboard Usage tab) | Sonnet 5 | ~25 min | ~$0.90–$1.30 |
| 11 (shutdown staging fix, proactive speech shaping, change_jarvis_code + phone) | Sonnet 5 | ~35 min | ~$1.40–$2.00 |
| 12 (Gemini brain option + runtime switch + research) | Sonnet 5 | ~50 min | ~$2.00–$2.80 |
| 13 (sleep trends tab + wake-up digest) | Sonnet 5 | ~30 min | ~$1.20–$1.70 |
| 14 (wake-up recap split, hotkey move, sleep-mode mail take-over + retry) | Sonnet 5 | ~45 min | ~$2.10–$2.90 |
| 15 (download_image tool for Pinterest-style image saves) | Sonnet 5 | ~10 min | ~$0.40–$0.60 |
| 16 (standalone launcher: hidden start, stop, shortcuts, autostart option) | Sonnet 5 | ~10 min | ~$0.35–$0.50 |
| 17 (voice-triggered self-restart + live debugging of the helper) | Sonnet 5 | ~25 min | ~$1.10–$1.50 |
| 18 (spoken progress lines during multi-step tasks) | Sonnet 5 | ~10 min | ~$0.35–$0.50 |
| 19 (face recognition Phase 0: analysis + risk review, no code) | Sonnet 5 | ~8 min | ~$0.25–$0.35 |
| 20 (face recognition Phase 1: module, DPAPI storage, enroll/delete, liveness) | Sonnet 5 | ~40 min | ~$2.20–$3.00 |
| 21 (face recognition Phase 2: polling, recognition, group-safe mode, unknown pictures, privacy switch) | Sonnet 5 | ~45 min | ~$2.50–$3.40 |
| 22 (face recognition Phase 3: dashboard Identity tab, consent view, export/erase, event stream, Host-header guard) | Sonnet 5 | ~35 min | ~$2.00–$2.80 |
| 23 (face recognition Phase 4: self-audit fixes, gate-isolation test, calibrate tool, Origin guard) | Sonnet 5 | ~30 min | ~$1.60–$2.30 |
| 24 (face recognition code review: 11 defects fixed, 17 new tests) | Sonnet 5 | ~40 min | ~$2.20–$3.00 |
| 25 (stranger -> Telegram reminders question with held+forwarded reminders, away mode auto-lock, dashboard toggle) | Sonnet 5 | ~60 min | ~$3.00–$4.20 |
| 26 (full autonomy: commitments/projects, policy engine + teach loop, tick, campaigns, dynamic tools, consolidation, dashboard tab) | Sonnet 5 | ~75 min | ~$3.60–$5.00 |
| 27 (autonomy security audit: 20 findings fixed, human-only approvals, quarantine, sandbox hardening, 54 new tests) | Sonnet 5 | ~40 min | ~$2.20–$3.00 |
| 28 (full-permission model + inbound perception, extraction, observability, direct calendar, skills, memory intervention; 40 new tests) | Sonnet 5 | ~75 min | ~$4.00–$5.50 |
| 29 (audit fixes: confirmation semantics + TTL, wider gate, dashboard-wide Host/Origin guard, sensitive-path/http policy, delegation env allowlist, attended-only autonomy approvals; 70 new tests) | Sonnet 5 | ~45 min | ~$3.00–$4.20 |
| 30 (Deepgram speed upgrade: Nova-3 STT + Aura 2 TTS backends with circuit breakers, sentence-pipelined TTS, filler phrase, latency logging + intent classifier; 31 new tests) | Sonnet 5 | ~60 min | ~$3.20–$4.50 |
| 31 (Deepgram speed-upgrade audit-and-fix pass: lazy Whisper preload, honest tts_backend logging, filler-vs-narration fix, bounded pipeline join timeout, breaker-recovery + timeout test coverage; 10 new tests) | Sonnet 5 | ~35 min | ~$1.60–$2.30 |
| 32 (cloud-latency pass: streaming STT + TTS WebSockets, simple-intent fast path, Claude SSE token streaming to speech, all default-on; websocket-client dependency; 48 new tests) | Sonnet 5 | ~110 min | ~$4.50–$6.20 |
| 33 (cloud-latency audit-and-fix pass: found and fixed a real double-speak bug in multi-round streamed narration, plus a stale comment; 1 new test) | Sonnet 5 | ~30 min | ~$1.30–$1.90 |
| 34 (dashboard UI/UX overhaul: sidebar + hash-routed shell, Home mission-control view, full feature parity lift-and-shift, verified via headless harness + standalone preview server) | Sonnet 5 | ~85 min | ~$3.60–$5.00 |
| 35 (post-overhaul UX pass: detail-panel auto-open + audit click-through, denser Usage/Sleep/Home/Autonomy layouts, Usage token breakdown, Autonomy restructure, Home enrichment, 2 root-caused voice playback bugs; 2 new tests) | Sonnet 5 | ~70 min | ~$3.00–$4.20 |
| **Running total (final)** | | **~1323 min** | **~$59.85–$83.60** |

- **Multi-user enrollment (2026-09-20, user request via Jarvis) — supersedes the "exactly one enrolled person" decision above.**
  Roles Admin/User/Guest in `face_profiles.role`. First enrollee is always the single Admin (owner); later ones are
  `user` (default) or `guest` via `enroll_face(name, role)`; a second Admin is refused (atomic INSERT guards), a face
  already enrolled under another name is refused, and the Admin cannot be deleted while others remain. Only the Admin
  counts as "owner present" (greeting, away-mode lock clock); users are named in the prompt line but never a stranger;
  guests are named but hold non-urgent speech/keep replies discreet like a stranger (no picture, no Telegram question).
  Roles are personalization only, never gate anything. Same source limits (no phone/scheduled). Tests in `test_face.py`.

## Audit hardening (2026-09-21)

Result of a read-only audit, then fixed; tests in `test_hardening.py` (70). Rules to keep:
- **Confirmation** (`_is_confirmation_yes`): whole-word, <= 8 words, and any negation ("no", "don't",
  "not sure", "cancel", "stop"...) vetoes it. It used to be a substring match, so "no, don't do it"
  approved a staged shutdown. A staged action expires after `PENDING_ACTION_TTL_S` (120 s) for the
  spoken-yes path and records its `source`/`queued_at`. Never go back to substring matching.
- **Gate coverage** (`_catastrophic_reason`): text is normalised (backticks, carets, `sh""utdown`),
  then the original patterns, extra shutdown/disk/boot patterns (`shutdown /p /h /l -r`, WMI,
  `Format-Volume`, `bcdedit`, `cipher /w`, `reg delete HKLM`), and a *combination* check: any
  recursive-delete verb + any drive-root / user-profile / top-level personal folder target, in any
  order. Still a tripwire over text, not a sandbox; extend the matrix in `test_hardening.py` when adding.
- **Dashboard**: a middleware rejects a non-loopback `Host` on EVERY `/api/*` route and a non-loopback
  `Origin` on every state-changing one (before this only `/api/faces*` and `/api/autonomy*` did, so DNS
  rebinding could reach `/api/command` and `/api/pending/approve`). New routes are covered automatically.
  Tests must build their client with `base_url="http://127.0.0.1:8765"`.
- **File/network tools** (`jarvis_workspace.sensitive_reason`): reads refuse `.env*`, keys, Jarvis's own
  DBs and credential folders; writes additionally refuse Jarvis's code folder, `.git`, `.claude` and the
  Startup folder. `http_request` refuses private/loopback hosts (also on redirects) and any request
  carrying the value of a secret-looking env var. Absolute paths elsewhere are still honoured.
- **Delegation** (`delegate_to_claude_code`/`change_jarvis_code`): refused when there is no command
  source (autonomy, scheduled skills, background threads), and the permissions-skipped child gets an
  allowlisted environment (`_DELEGATE_ENV_ALLOW`) - none of Jarvis's API keys or tokens.
- **Autonomy tool**: `ATTENDED_ONLY_ACTIONS` (approve, dismiss, never, add_action, approve_campaign,
  add_project, accept/complete/cancel_commitment) need voice/typed/dashboard; an unattended agent run
  can no longer promote its own review cards. Organise `add/remove_root|rule` likewise.
- Logs are untracked and ignored (`*.log`), `requirements.txt` is pinned to the tested versions, the
  workspace default root derives from the home directory.
- **Deliberately NOT changed** (standing user decisions): autonomy stays on by default with no default
  email-recipient allowlist (`JARVIS_AUTONOMY_EMAIL_AUTO_ALLOW` remains opt-in) - full auto-act was an
  explicit 2026-09-20 decision; `graphify-out/` stays tracked; git history was not rewritten (old logs
  remain in past commits). The urgent-email auto-reply skills are still deleted in the working tree
  (4 tests in `test_cache.py` fail until they are restored or those tests are removed); if restored,
  add a deterministic handled-ID table and per-sender cap first (memory-search dedupe is fuzzy).
- MCP servers still run through `npx ...@latest` in the local `mcp_servers.json` (gitignored); pin
  versions there yourself.
