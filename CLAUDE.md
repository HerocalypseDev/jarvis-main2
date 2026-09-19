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
  (even if the user talks to Jarvis mid-sleep). When Sleep Mode ends by any route (tool, toggle,
  wake alarm) `disable()` calls the handler `jarvis._sleep_wake_digest`, which drains those items
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
  (afternoon start) and was replaced at the user's request. Not built: a nap alarm/timer (a nap has
  no wake time unless `schedule_sleep_wakeup` is used, and that alarm says "Good morning"), counting
  naps toward a 24-hour goal. Not exercised live (it toggles dark mode/volume/hosts); unit-tested
  with those faked.
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
| **Running total (final)** | | **~385 min** | **~$13.90–$19.65** |
