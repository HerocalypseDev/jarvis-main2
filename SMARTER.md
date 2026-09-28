# Smarter + more autonomous batch (2026-09-28)

User request: "start on everything now including autonomous and smarter", after a research pass
(Anthropic's agent guidance, tool-search results, Reflexion-style self-improvement, agent memory
surveys). Built in phases; each is pushed to `main` on its own. The catastrophic confirmation gate is
untouched by every phase: nothing here calls `skip_confirmation`, and every tool a model picks still
runs through `_execute_tool`. Tests: `test_smarter.py`.

## Phase 1: tool narrowing (`jarvis_tool_router.py`)

- **Why:** ~130 built-in tools + every MCP tool went out on every request. Tool-picking accuracy falls
  past ~30-50 tools, worst on small models.
- **What:** BM25 over each tool's name (weighted x3), description, parameter names and enum values.
  `select()` returns the always-on `CORE_TOOLS`, any tool named outright in the command, the best
  matches (recent history text as low-weight context), up to `JARVIS_TOOL_NARROWING_LIMIT` (28), then
  a `find_tools` meta-tool. When the model calls `find_tools("keywords")`, the loop adds the matching
  schemas for the next round and returns their names. `find_tools` is handled inside `run_agent_loop`
  (no side effects, not audited: it only widens the choice; the tools it adds still go through
  `_execute_tool` and the gate).
- **Default:** `JARVIS_TOOL_NARROWING=auto` = Gemini only. Claude keeps the full list because its
  1-hour prompt cache is keyed on the exact tool prefix; narrowing there would re-write ~33k tokens of
  cache per distinct list. `on` = both brains, `off` = never. On the Settings page.
- **Not verified live:** ranking quality against the real MCP tool set (WhatsApp, Gmail, Calendar),
  which is not loaded in the cloud test environment.

## Phase 2: claim checker + escalate on failure

- **Claim checker** (`_ACTION_CLAIMS`, `_unbacked_claims` in jarvis.py): generalises the hand-off guard.
  A *final* reply that claims, in the past tense, that it set a reminder / sent a message / added a
  calendar event / saved a file / remembered something, when no tool whose name fits that action ran
  this turn, gets one extra round with a "[system check] ... did NOT happen" message. If the next reply
  still claims it, a "Correction: I didn't actually ..." line is appended. Questions and offers ("Shall
  I set a reminder?") are ignored. Matching is on tool *names* (e.g. any tool containing
  send/reply/mail/whatsapp backs "I sent"), so it is a tripwire, not proof the action succeeded.
- **Escalate on failure**: `_escalation_model()` = `JARVIS_SMART_MODEL` on Claude,
  `JARVIS_GEMINI_SMART_MODEL` on Gemini (empty by default, since the user picks Gemini models; e.g.
  `gemini-3.6-flash`, on the Settings page). A repeated command (voice_tone's `repeated` signal) starts on
  it; a failed tool result or an unbacked claim switches the rest of the command to it. A mid-command
  switch on Claude sends no `thinking` (earlier assistant turns have no thinking blocks to echo back).
  On Gemini, `jarvis_gemini.call` uses a `gemini-`/`gemma-` model named in the body, and if that model
  fails, retries the same request on the configured model.
- **Cost:** an escalated Claude command pays the smart model's rate for the rest of that command and its
  own prompt-cache write (~$0.08-0.13 the first time each hour).
- **Residual:** a streamed first-round reply is already spoken before the check runs; the correction then
  follows it. Only when the Claude brain streams a tool-less first reply (rare for action commands).

## Phase 3: lessons memory (`jarvis_lessons.py`)

- **Why:** the Reflexion pattern: agents improve fastest when each failure leaves a short written lesson
  that is read back next time. The weekly improvement report found failures but nothing fed them back.
- **When a lesson is written:** at the end of a real user command (`_current_command_source()` set, not
  autonomy/scheduled runs, not the reduced-tools fast path) where a tool result looked failed, or the
  user's words correct the previous answer (`CORRECTION_RE`: "no, ...", "I meant ...", "that didn't
  work", ...) or voice_tone flagged a repeated command. One small model call (`_sleep_mail_claude`, the
  normal model, 120 tokens) on its own thread, at most `LESSONS_PER_HOUR` (12).
- **Input framing:** the command, each tool call + result and the correction go in a `<<<DATA ... DATA>>>`
  block, sanitised; the stored lesson is sanitised again, one line, <= 200 chars.
- **Refused lessons:** anything mentioning confirmations/approvals/skipping/permissions/safety/gates/
  secrets/disabling checks (`_FORBIDDEN_RE`), or where the sanitiser found injection-like text. The prompt
  line also says lessons never override rules or confirmations.
- **Use:** the top 3 lessons by word match (lesson + the command that caused it) go in the *volatile*
  system block (`_lessons_line`), never the cached prefix. Near-duplicates (>= 70% word overlap) refresh
  the old row; 200 rows max, least-used pruned. Table `lessons` in `jarvis_memory.db`.
- **Control:** `lessons` tool (list / add / forget; add and forget are attended-only), `JARVIS_LESSONS=0`
  turns the whole thing off.
- **Cost:** one ~120-token call per failed or corrected command, capped at 12/hour.
- **Not verified live:** lesson quality from a real model.

## Phase 4: meaning-based memory retrieval (`jarvis_embeddings.py`)

- **Why:** TF-IDF matched filler words; that is how billing and sleep facts were read out as "Related:".
- **What:** Gemini `gemini-embedding-001` vectors (256 dims) for memory facts and the command, cached per
  text in a new `embeddings` table (sha256 key, float32 blob). `jarvis_memory_enhance.relevant_memory_line`
  takes an optional `semantic` ranker; jarvis passes `_semantic_ranker()` from both per-command retrieval
  and the deadline-nudge context. Hybrid: meaning matches first, plus strong word matches (TF-IDF >= 0.3,
  e.g. "open my browser" -> "Opera GX as the main browser", which the embedding ranked below its cut-off).
- **Selection** (tuned on live scores): >= 0.70, >= 0.07 above the median of all facts, and within 0.05 of the
  best match. Live check on 9 sample facts: 8/8 queries right, including "wash clothes" no longer pulling in
  the PPM exam and "what's the weather" returning nothing.
- **Default:** `JARVIS_EMBEDDINGS=auto` = only while the Gemini brain is active (fact text then goes to the
  same vendor that already sees every prompt); `on` also with Claude (sends fact text to Google for
  embedding); `off`. Needs a Gemini key. `JARVIS_EMBED_MODEL` overrides the model.
- **Speed/failure:** facts are embedded once in the background at startup (`_warm_embeddings`); a command
  pays one small query request (2.5 s timeout). Any failure -> TF-IDF as before; 3 failures in a row pause
  embeddings for 5 minutes.
- **Data exposure:** on Gemini's free tier, fact text sent for embedding may be used by Google, same as the
  prompts themselves.

## Phase 5: eval set from real failures (`jarvis_eval.py`, `evals/cases.json`)

- 30 cases, most taken from real incidents in CLAUDE.md (shutdown never staged, fake James hand-off,
  "where is your code" -> OpenJarvis, deferred jobs, fake "I sent it"), plus everyday tool routing.
- `python jarvis_eval.py [--provider claude|gemini] [--model NAME] [--case ID] [--delay S] [--verbose]`.
  Uses the real model, but **no tool ever runs**: `_execute_tool_impl` is replaced by a recorder, MCP is
  never started, a throwaway DB is used, caches and lessons are off. Results go to `evals/results/`
  (gitignored). A case where the model was unreachable (quota/overload) is reported as ERR, not scored.
- Case checks: `expect_any` (one of these tool calls, optional `input_re`), `forbid`, `reply_not_re`,
  `reply_re`. A unit test checks every named tool exists, so a renamed tool can't silently make a case
  impossible.
- **First live run (2026-09-28, the user's Gemini key):** `gemini-3.6-flash` free tier allows only 5
  requests/minute (5/8 before the quota hit); `gemma-4-31b-it`: 6/6 scored cases passed, 24 not scored
  (free-tier rate limit), and each case took 30-180 s. So neither is a good full-time brain on the free
  tier; a real comparison needs Claude or a paid Gemini tier, or `--delay 15` and patience.

## Phase 6: autonomy upgrades

- **Duplicates stopped at the source:** `_insert_commitment` marks a commitment that is itself a reminder
  request (`_REMINDER_ABOUT_RE`) or that an existing reminder covers (`reminder_covers`) as
  `covered_by=reminder` + handled, so it is tracked but never actioned or nudged (the 2026-09-28 overdue
  burst, fixed earlier at nudge time, is now also prevented at creation).
- **Confidence that learns** (`autonomy_calibration` table, `record_outcome`, `learned_raise`): per action
  type, bad outcomes (a dismissed card, a cancelled reminder that autonomy created - tracked in
  `autonomy_created` via `_autonomy_create_reminder`, which appends the new id - or "undo" within 10 min
  of an autonomous action, `note_user_undo`) raise the auto-act bar by 0.05 each, capped at +0.2; two
  approvals cancel one bad. It is added to both the default floor and the third-party bar. **It can only
  raise the bar, never lower it below the configured default.** Cancelling your own reminder changes nothing.
- **Daily plan + evening review** (`jarvis_daily_plan.py` + glue in jarvis.py, table `daily_plans`):
  at `JARVIS_DAILY_PLAN_TIME` (07:45) one small model call orders today's candidates (open commitments
  due within 36 h or overdue up to 3 days, today's reminders, today's calendar events, yesterday's
  carried-over items) into <= 6 items; model down -> deterministic order. Only refs that really exist are
  accepted from the model. At `JARVIS_DAILY_REVIEW_TIME` (21:00) each item is checked (commitment
  completed, reminder delivered/cancelled, event time passed); unfinished items carry over and one short
  non-urgent line is announced (so sleep/focus/safe-mode/meeting holds apply). Home has a "Today's plan"
  card (`/api/feature/daily_plan`, Rebuild button); voice: `daily_plan` tool ("what's my plan today").
  `JARVIS_DAILY_PLAN=0` turns both off. Verified in headless Chromium against stubbed data.

## Phase 7: local brain via Ollama (`jarvis_ollama.py`)

- The private option: "switch to the local brain" / the brain chip -> `local`. Every model call goes to
  Ollama's `/api/chat` on `JARVIS_OLLAMA_URL` (default `http://127.0.0.1:11434`) with
  `JARVIS_OLLAMA_MODEL` (default `qwen3:8b`; `ollama pull qwen3:8b` first). Anthropic-shaped requests are
  translated like the Gemini adapter (tools -> function specs, tool_use/tool_result -> tool_calls/tool
  messages, `<think>` text stripped so reasoning is never spoken).
- **Privacy rules:** public hosts are refused (loopback/private/link-local only); it **never fails over to a
  cloud brain**; with it active, tool narrowing is on (small models need it) and embeddings stay off
  (auto = Gemini only), so memory text isn't sent to Google either. Speech still uses whatever STT/TTS is
  configured (Deepgram/Fish are cloud; local Whisper/Piper are the private options).
- `set_llm_provider("ollama")` checks the server answers and the model is pulled before switching.
- **Not verified live:** no Ollama server in the cloud test environment; translation is unit-tested against
  Ollama's documented request/response shapes.
