# Multi-step task execution — research (draft, not built yet)

## What prompted this

Live-testing showed a single compound instruction — "check the attached file, summarize
it, save it as PDF, email it back, then delete the old email and send an updated
version" — takes 5-8+ tool-call round trips in one flat `run_agent_loop` (`jarvis.py:4406`)
conversation. Every round trip resends the *entire* message history, so cost and latency
both grow with how far into the task you already are, there's no record of which sub-step
is done vs. pending, and a request that wedges (as the Claude API call did — see the
`_urlopen_hard_timeout` fix) silently drops the whole multi-step task with no partial
progress saved anywhere.

`MAX_AGENT_ITERATIONS` was 6, just raised to 12 — that buys headroom but doesn't fix the
underlying shape: one growing ReAct-style loop with no explicit plan, no per-step state,
and no way to resume after a crash.

## What production agents actually do differently

**1. Explicit todo/plan list, not implicit planning in a growing transcript.**
Claude Code's own `TodoWrite` pattern (and Spring AI's port of it, Ona's "rethinking the
todo tool" writeup) replaced ad-hoc planning-in-prose with a single tool the model calls
to write out the *complete* current task list (pending/in-progress/completed) on every
update — no incremental diffs, no separate tools per state change. The win isn't
UX polish: with the plan sitting in message content instead of buried in scrollback,
"lost in the middle" failures where a mid-list step silently gets skipped mostly go away,
because the model re-reads and re-emits the whole list each time instead of relying on
attention across a long history. ([Spring AI: Why Your AI Agent Forgets Tasks](https://spring.io/blog/2026/01/20/spring-ai-agentic-patterns-3-todowrite/),
[Ona: rethinking the todo tool](https://ona.com/stories/rethinking-the-todo-tool))

**2. Plan-then-execute, not one continuous loop.**
LangGraph's Plan-and-Execute pattern splits into: a *planner* call that emits an ordered
step list once, an *executor* node that runs one step at a time against a slim per-step
context (not the full history), and a *re-planner* that only re-invokes the LLM to revise
the plan if a step's outcome diverges from expectations. State (the plan, `past_steps`,
results so far) is an explicit typed object, not "whatever's left in the message array."
([LangGraph workflows vs. agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents),
[Architecting Resilient LLM Agents: Plan-then-Execute](https://arxiv.org/pdf/2509.08646))

**3. Checkpointing state after every step, not just at the end.**
LangGraph's checkpointer persists state after each node runs, so a crash mid-task resumes
from the last completed step instead of restarting or silently dropping it entirely.
([LangGraph State: Checkpoints, Threads, and Recovery](https://eastondev.com/blog/en/posts/ai/20260424-langgraph-agent-architecture/))

**4. Orchestrator/worker for genuine parallelism, with explicit ordering constraints.**
Claude Code's Agent Teams (2026) give parallel subagents a *shared task list with
dependency tracking* plus file locking — the orchestrator decides which sub-tasks are
truly independent (can run concurrently) vs. which have a hard "must happen before"
relationship, and encodes that as a dependency edge rather than hoping ordering falls out
of prompt phrasing. This is the direct answer to "delete the old email must not race
sending the new one": that's not something you leave to the model's judgment mid-loop,
it's a dependency you declare in the plan before execution starts.
([Claude Code Multi-Agent Orchestration Patterns](https://thepromptshelf.dev/blog/claude-code-multi-agent-orchestration-patterns-2026/),
[Claude Code subagents and orchestration guide](https://hidekazu-konishi.com/entry/claude_code_subagents_and_orchestration_guide.html))

## Cost/latency tradeoff, specific to this codebase's pattern

Jarvis's loop resends full history every round trip (`run_agent_loop`, `jarvis.py:4414-4428`)
— cheap for a 2-3 step command, increasingly wasteful past ~5 steps since step *N* pays
for re-sending steps 1..N-1's tool results too. A plan-then-execute split only pays off
once tasks are *routinely* compound (which, per this session's test, they already are for
email/file workflows): one upfront planning call is slightly more expensive than the first
round of the current loop, but every subsequent step then runs against a short "here's
step 3 of the plan, here's what step 2 produced" context instead of the whole transcript —
net cheaper past roughly 4-5 steps, and the crossover only gets more favorable the longer
the task runs.

## Recommendation for `jarvis.py` — incremental, not a rewrite

Don't adopt LangGraph or rebuild `run_agent_loop` as a graph. The existing
`background_tasks` SQLite table (`jarvis.py`, added for `delegate_to_claude_code`/
`delegate_research`) already has almost the right shape for step-level checkpointing —
extend it instead of adding new infrastructure:

1. **Add a `plan_steps` table** (or a JSON column on `background_tasks`): for any command
   Claude's first response to identifies as multi-step (it can just say so, or you detect
   `tool_uses` count trending toward the cap), have it emit an explicit ordered step list
   up front — same idea as `TodoWrite`, scoped down to what this assistant needs: `{step,
   description, depends_on, status}`.
2. **Execute one step per `run_agent_loop` iteration**, passing only that step's
   description + the prior step's result as context, not the full running transcript —
   this is the actual fix for both the cost-scaling problem and the iteration-cap problem,
   since each step becomes a fresh, small request instead of one more link in a growing
   chain.
3. **Persist status after each step** (reuse `_finish_background_task`'s pattern, but per
   step, not per whole task) — a crash or hang on step 4 of 6 leaves steps 1-3's results on
   disk instead of losing the whole thing, and `list_background_tasks` can show "step 3/6"
   instead of just "running."
4. **Ordering, not concurrency, first.** Don't reach for parallel execution yet — the
   `depends_on` field on each step is what prevents the "delete-then-send" race the user
   hit; that's a correctness fix, independent of whether steps ever run concurrently. Only
   consider actual parallel sub-tasks (separate threads/background rows, like `delegate_research`
   already does) once there's a concrete case where two steps have no dependency edge
   between them and waiting for one before starting the other is genuinely wasted time.

This reuses `background_tasks`' existing polling (`_check_background_tasks`,
`jarvis.py:4005`) and notification pipeline as-is — a multi-step foreground command just
becomes a background_tasks row with a plan attached, checkpointed step-by-step, instead of
a special case.

## Suggested build order

1. Detect "this command needs a plan" (cheap heuristic: let Claude emit a `set_plan` tool
   call when it recognizes a compound instruction; don't try to pre-classify with regex).
2. Step-scoped execution loop: run one step against slim context, persist result, move to
   next `depends_on`-satisfied step.
3. Per-step status in `list_background_tasks` / `quick_recall`.
4. Only then: revisit whether any step class (independent, no shared side effects) is
   worth actually parallelizing.

Say the word and I'll start on step 1.
