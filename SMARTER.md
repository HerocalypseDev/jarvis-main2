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
