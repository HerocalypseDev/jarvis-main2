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
