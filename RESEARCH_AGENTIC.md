# Making Jarvis more efficient, more agentic and more professional (research, 2026-09-30)

Private notes (excluded from the public export). Numbers about outside services come from third-party
summaries dated mid-2026; check each provider's own dashboard before relying on them.

## 1. Limits this plan respects

- Cloud only, nothing heavy on the PC (no local models, no GPU work).
- Free tiers only: Gemini free quota, Deepgram and Fish credits, no paid search or model API keys.
- One Windows PC, one owner, Claude Code as the developer (each session costs money and time).
- Payment options are limited from Nigeria, so anything that needs a card or a purchase is "maybe later".
- Gemini Live and other big rewrites were already declined.

## 2. Where Jarvis is today (measured)

- `jarvis.py` is 13,001 lines, plus 68 `jarvis_*.py` modules, 984 tests, 32 eval cases.
- 95 agent tools. Their schemas are about 55,000 characters (roughly 14k tokens) on every round if nothing is narrowed.
- Tool calls in one turn run one after another (`for i, tu in enumerate(tool_uses)` in `run_agent_loop`).
- Already built and working: tool narrowing, claim checker, model escalation, lessons memory, embeddings retrieval,
  autonomy, confirmation gate, dashboard, audit trail, evals, spoken lead-ins, Gemini streaming.

## 3. What the real failures say

Looking at every problem found live in the last two weeks, almost none were "the model is too weak":

| Failure | Real cause |
|---|---|
| "weird" file not found | Model sent `name_query`, tool read `query` (bad arguments) |
| `dir C:\ -s -b` failed | Wrong shell dialect (cmd vs PowerShell) |
| "I've typed it" but nothing typed | Claim with no proof of the result |
| "Couldn't reach Gemini" | Daily free quota used up, single provider |
| Gmail tool expired | Google login expiry (Testing-mode OAuth), no warning |
| Search never used Everything | Feature not set up, nothing told the owner |
| Form answers in wrong fields | Blind scripts instead of read-act-verify steps |

So the leverage is in the harness around the model: tool design, checking results, provider spread, health checks.
This matches Anthropic's published advice: start with simple workflows, add autonomy only where flexibility
is worth the cost, and put as much care into tool design as into prompts
([overview of the five workflow patterns](https://claude.com/blog/common-workflow-patterns-for-ai-agents-and-when-to-use-them)).

## 4. Recommendations, most valuable first

### A. Do first (high impact, small work, no new cost)

1. **One generic argument checker instead of per-tool alias hacks.** Before any tool runs, check the model's
   arguments against that tool's schema. Unknown key + missing required key + same type: map it automatically
   (`name_query` -> `query`). Otherwise return an error that teaches ("missing `query`; valid: query, ext,
   path_prefix"). Log every repair: the list shows which tool descriptions to fix. (~1 function in `_execute_tool`.)
2. **Verify after acting, and give a receipt.** After every action that changes something (type, send, save, create
   reminder/event), run a cheap read-back (screen snapshot, list the reminder, does the file exist) and end with one
   line of proof: what, where, evidence. The claim checker only proves a tool ran; this proves the outcome. This is
   the biggest "professional" signal, and it is what the form-filling failures needed.
3. **Doctor + expiry alerts.** `python jarvis_doctor.py` and a Home card: keys valid, model quota (via Google's free
   list endpoint), Everything HTTP server, MCP logins (Gmail/Calendar), mic, Deepgram, disk. Turn known error text
   ("invalid_grant", "token expired") into one notice with the exact fix command. Publishing the Google OAuth app
   ends the 7-day expiry.
4. **Turn every debug report into an eval case.** Extend `tools/collect_debug.py` to draft `evals/cases.json`
   entries from failed commands. A tiny nightly run (about 15 requests, hard cap) on the cheapest working model gives a
   pass-rate trend on the dashboard, so fixes stop regressing.

### B. Do next (medium work, fixes the quota and speed limits)

5. **More free brains behind one router.** Add an OpenAI-compatible adapter (about as big as `jarvis_gemini.py`)
   and a quota-aware picker that keeps daily counters per provider.
   - [Groq](https://eesel.ai/blog/groq-pricing): no card. `llama-3.3-70b-versatile` 30 RPM, 12k TPM, 1,000 requests/day;
     `llama-3.1-8b-instant` 14,400/day and 306k TPM (good for routing, summaries, shortening speech; weak for tool use);
     `gpt-oss-120b` 1,000/day, 8k TPM. Cached tokens don't count. **Catch:** 8-12k TPM is smaller than one Jarvis
     round today, so this only works together with item 6.
   - [OpenRouter free models](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/): 20 RPM and only 50 requests
     a day unless $10 of credit was ever bought (then 1,000). Models rotate. A weak main option, fine as a last resort.
   - [Mistral Experiment plan](https://help.mistral.ai/en/articles/455206-how-can-i-try-the-api-for-free-with-the-experiment-plan):
     no card, phone verification, about 2 RPM, huge token allowance, but requests may be used for training.
   - Not usable: Cerebras needs a payment method for its credit; [GitHub Models](https://letsdatascience.com/news/github-retires-free-github-models-playground-5cc61120)
     closed to new users in June 2026.
   - Free tiers may train on your prompts (already true for Gemini free): keep the existing warning for each.
6. **Put the prompt on a diet.** Free-tier TPM is now the real ceiling. Extend tool narrowing to every non-cached
   provider, shorten tool descriptions, move rarely used tools behind `find_tools`, keep moving rules from the prompt
   into code guards (as already done for hand-offs and file search). Target under 6k tokens per round, and show
   tokens per command in the Usage tab so progress is visible.
7. **Run independent read-only tools in parallel.** Both Claude and Gemini can return several calls in one turn
   ([Gemini docs summary](https://oneuptime.com/blog/post/2026-02-17-how-to-implement-function-calling-with-gemini-for-tool-augmented-ai-applications/markdown)),
   and the loop currently runs them in sequence. `READONLY_TOOL_TTLS` already names the safe ones: run those in a
   thread pool, keep anything that writes sequential, and don't rely on the order the model returns.
8. **Grow the no-LLM path.** The audit table already records command -> tool calls. Mine the frequent ones into instant
   macros/skills (the machinery exists) and answer them with zero model calls. Every command that skips the model is
   faster and costs no quota.

### C. Later (bigger, but makes it feel like a product)

9. **Workflows for the recurring big jobs, agent only inside steps.** Form filling, inbox triage, research, briefing:
   fixed step graphs (snapshot -> list fields -> fill one -> verify -> next) with a saved checklist in SQLite so a
   restart resumes. The model handles the fuzzy parts; code handles order and checking.
10. **Visible plans.** Dashboard shows the plan, each step's status and a Stop button; long tasks checkpoint.
11. **One place per tool.** Today a tool is spread over `AGENT_TOOLS`, a handler table, `READONLY_TOOL_TTLS`, the
    announcement table and the narrowing lists. A single `Tool` record (schema, handler, risk tier, cache TTL, spoken
    line, aliases) makes adding a tool one edit, and enables items 1, 5 and 7 cleanly. Split `jarvis.py` along that line.
12. **Ask one question when it is truly ambiguous** (three matching files, two contacts) instead of guessing, and stay
    quiet otherwise. Add a per-command timeline (rounds, tools, latency, tokens) next to the audit trail.

## 5. What not to do with these limits

- Local models, fine-tuning, a vector database service (TF-IDF plus Gemini embeddings is enough).
- Multi-agent swarms or framework rewrites (LangGraph, CrewAI): errors multiply, free quotas run out fast, and you
  already own a working loop.
- Paid search/model APIs, or anything that needs a card, until income from Jarvis4U Pro covers it.
- Rebuilding Gemini Live (already declined).

## 6. Suggested order

1. **Session 1 (reliability):** items 1, 2 (file, typing, reminders first), 3, 4.
2. **Session 2 (quota and speed):** items 6, 5 (Groq only), 7.
3. **Session 3 (product feel):** items 8, 9, 11.

Each session ends with the usual tests, full-suite comparison and publish to both repos.

## 7. Sources

- [Common workflow patterns for AI agents (Claude)](https://claude.com/blog/common-workflow-patterns-for-ai-agents-and-when-to-use-them)
- [Building effective agents, summary (Simon Willison)](https://simonwillison.net/2024/Dec/20/building-effective-agents)
- [Groq pricing and free tier](https://eesel.ai/blog/groq-pricing)
- [Free LLM APIs compared (OpenRouter)](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/)
- [Mistral Experiment plan](https://help.mistral.ai/en/articles/455206-how-can-i-try-the-api-for-free-with-the-experiment-plan)
- [Cerebras free plan](https://costbench.com/software/llm-api-providers/cerebras-inference/free-plan/)
- [GitHub Models retirement for new users](https://letsdatascience.com/news/github-retires-free-github-models-playground-5cc61120)
- [Gemini function calling guide](https://oneuptime.com/blog/post/2026-02-17-how-to-implement-function-calling-with-gemini-for-tool-augmented-ai-applications/markdown)
