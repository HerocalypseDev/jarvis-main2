# Full Autonomy Stack

Jarvis can move from "answers when asked" to "notices what you have committed to and helps": it
extracts commitments and projects from conversation and mail, keeps them across days, watches deadlines,
proposes concrete actions, learns from what you approve or dismiss, runs multi-day campaigns, and can
add small pure-computation tools to itself. **It is off by default, and it asks before it acts.**

Files: `jarvis_autonomy.py` (core), `jarvis_dynamic_tools.py`, `jarvis_memory_consolidation.py`,
`dashboard_static/autonomy.js` (Autonomy tab), tests in `test_autonomy.py`.

## Turn it on / off (and the emergency stop)

| How | Effect |
|---|---|
| Say "turn off autonomy" (the `autonomy` tool) | Persisted in the DB. Works from anywhere; it also cancels the queued tasks autonomy had started. |
| Dashboard > Autonomy > *Turn autonomy on/off* | The same switch, and the **only** way to turn it *on* (see "Human-only actions"). |
| `JARVIS_AUTONOMY_ENABLED=1` | Default when the DB has no stored choice. |
| **`JARVIS_AUTONOMY_DISABLED=1`** | Hard kill. Overrides everything; nothing autonomous runs, enabling is refused. |
| Dashboard *Dry run* / "autonomy dry run on" | Everything is logged, nothing is executed. |
| `JARVIS_DYNAMIC_TOOLS_DISABLED=1` | No dynamic tools created, advertised or run. |

## Human-only actions (security audit 2026-09-20, B-01)

The model cannot tell your words from text that reached it through an email, web page or file, so
anything that grants Jarvis more power exists **only as a dashboard route**, never as something the
`autonomy`/`create_tool` tools can do: enabling autonomy, approving a suggestion, accepting a commitment,
approving a campaign or adding campaign steps, setting rules, leaving dry run, and approving a proposed
dynamic tool. Asking by voice gets "use the dashboard". Turning things *off* (disable, dry-run on,
dismiss, never) still works everywhere. The suggestion card puts **Approve behind a Review panel** that
shows the exact data the action will run with.

## Untrusted text (audit C-02 / C-04 / B-02)

* Anything extracted from mail/Telegram/Discord, **or from a turn in which Jarvis read mail, the web,
  files or the screen**, is stored *quarantined*: it is kept out of the model's context, the classifier
  and the deadline auto-nudge until you accept it (dashboard *Accept*, or by approving a suggestion built
  from it). It still produces a suggestion card, which is your review.
* Model/other-person text is cleaned (control characters, newlines, length) before it is stored, shown,
  spoken or put in a prompt, and action details are reduced to plain scalar fields; what the card shows
  is exactly what runs, and the agent is told the values are data, never instructions.
* Extraction prompts now include the current time (so "tomorrow" resolves) and deadlines in the past or
  more than 3 years out are dropped.

## How the tick works

`jarvis.py`'s existing scheduler loop (`SCHEDULER_TICK_S`, 60 s) calls `autonomy.tick(now)`. There is no
second background loop; when enabled, the pass runs on a short-lived worker thread so a slow model call
never stalls reminders or skills. Each pass:

1. **Free, deterministic steps** (always): expire stale suggestions/commitments, nudge as an open
   commitment's deadline nears (24 h / 2 h / overdue, once each), advance approved campaigns, and every
   few hours run the planner.
2. **Gates.** If Focus/Sleep Mode is on, the user is typing/speaking, or Jarvis is speaking, the rest is
   skipped (suggestions still appear as dashboard cards; they are spoken later). Anything that is spoken goes
   through `queue_or_deliver_notification`, so face group-safe mode (a stranger in view) still holds it.
3. **Model steps** (only when the gates are clear): summarise idle conversation into
   `conversation_summaries`; daily memory consolidation; speak one waiting suggestion; and the
   *classifier* ("is there a latent need?"), which is rate-limited (default every 15 min) and skipped when
   nothing changed or there is nothing in memory to reason about, because it is the only per-tick cost.
4. Every decision goes to `autonomy_decisions` **and** `action_audit` (as `autonomy_decision` /
   `autonomy_action` rows).

Extraction also runs after each command (`after_turn`) but only when the exchange contains a planning cue
("tomorrow", "remind", "deadline", ...), so ordinary chat costs nothing. `JARVIS_AUTONOMY_EXTRACT_ALWAYS=1`
removes that filter.

## Commitments, projects, campaigns

* `commitments` — task/event/promise/goal with deadline, who is responsible, confidence, source quote.
  Duplicates (same text, same day) are dropped; items under 0.6 confidence are never stored.
* `autonomy_projects` / `autonomy_project_actions` — named after `autonomy_` because `jarvis.py` already
  has a different `projects` table. A commitment's `related_project` finds or creates a project.
* **Campaigns**: `add_action` plans steps on a project; nothing runs until you `approve_campaign`. Steps
  are queued through the existing task queue (max concurrent background tasks, daily action budget
  apply) and reconciled from `task_queue`. A `high` risk project is *simulated* (logged only) unless its
  metadata says `live`.
* **Planner** (every `JARVIS_AUTONOMY_PLANNER_HOURS`, default 4): accepted (`accept_commitment`) tasks due
  within 7 days go into the task queue, then the queue is re-planned into free slots.

## Policies and the teach loop

A rule is `(category, match_kind category|sender|keyword, match_value) -> auto_act | ask_once |
always_ask | ignore`, optional `min_confidence`. Most specific wins (sender > keyword > category).
Categories look like `conversation:reminder`, `email:calendar`, `deadline:notification`, `tick:deadline:reminder`.

* **Default is ask.** The only built-in rule is an automatic heads-up about an approaching deadline.
* Content someone else wrote (email/Telegram/Discord) can **never** auto-act through a category-wide or
  keyword rule, only through a rule naming that **exact sender address** (or `@domain.com`). A `From`
  header can be forged, so even a sender rule is only as strong as your mail system: prefer leaving it on
  *ask*.
* Learned rules only ever auto-run reminders/notifications: 3 approvals in a row promote a category, 2
  dismissals demote it to `ignore`, one dismissal takes a learned auto rule back to asking. Rules you
  write yourself are never rewritten. *Never for this category* writes a permanent `ignore`.
* After a dismissal the same category is suppressed for `JARVIS_AUTONOMY_DISMISS_COOLDOWN_MIN` (180).
* Learned rules are also written into memory as `rule:autonomy:<category>` facts by consolidation.

Approved `calendar`/`email`/`file_op` actions run through the **normal agent loop**, so its tools, audit
trail and the catastrophic confirmation gate all still apply. The autonomy modules never reference the gate
(pinned by an AST test).

## Budgets

Per day: `JARVIS_AUTONOMY_MAX_ACTS_PER_DAY` (10), `..._MAX_SUGGESTIONS_PER_DAY` (8), concurrent
background tasks `..._MAX_BG_TASKS` (2), dynamic tools `JARVIS_DYNAMIC_TOOLS_PER_DAY` (3).

## Dynamic tools

`create_tool(code_string, name, description, tests=None, dry_run=False)` **proposes** a tool. It is
validated (scan + your tests) and filed as a proposal; it becomes `dyn_<name>` only when **you** approve it
in the dashboard (the code is shown there). Approval re-runs the scan and tests.

* **This is not a hard security boundary.** An audit showed that allow-listed modules re-export `os`/`sys`
  (`uuid.os`, `calendar.sys`, `json.codecs.open`) and that `operator.attrgetter` gives dynamic attribute
  access, so an AST scan alone can be bypassed. Treat every approved tool as if it could run with your
  privileges, and read the code before approving. What is layered on top, as defence in depth:
  * a small allow-list of pure modules (no `operator`, `string`, `typing`, `dataclasses`, `uuid`,
    `calendar`, `enum`, `urllib`), no `eval/exec/open/getattr/print/...`, no underscore attributes;
  * inside the runner every allowed module is replaced by a proxy with **no sub-modules and no
    underscore names**, so the re-export routes do not exist at runtime;
  * the tool runs in a separate `python -I` process with a 10 s timeout, a Windows Job Object (256 MB
    memory cap, no child processes), and output capped inside the child.
* An existing tool name is never overwritten or re-enabled (revoke it first); the daily budget is
  checked under the same lock as the insert.
* Stored in `dynamic_tools` (hash + code); on every load the hash and scan are re-checked, so a tampered
  row is not run. Dashboard: approve/reject proposals, enable / disable / revoke. Creation is refused
  from the phone and unattended runs. Deleting a tool does not refund the daily budget.

## Wiring in `jarvis.py` (already applied)

* imports (`autonomy`, `dyn_tools`, `consolidation`) next to the other modules;
* `AUTONOMY_TOOLS` (`autonomy`, `create_tool`, `manage_dynamic_tool`) appended to `AGENT_TOOLS`, dispatch in
  `_execute_tool_impl` (plus `dyn_*` routing); `dyn_tools.schemas()` added to the three tool lists;
* `build_system_blocks`: `autonomy.agent_context_line()` in the *volatile* block (open commitments/projects);
* `_scheduler_loop`: `autonomy.tick(now)`;
* `main()`: `dyn_tools.init_dynamic_tools()` + `autonomy.start_autonomy_tick(_autonomy_callbacks())` before
  `_start_scheduler()`;
* `_handle_text_command_impl`: `autonomy.after_turn(transcript, reply, source)` after the reply is stored;
* mail: `jarvis_sleep_mail.run_cycle(..., on_inbound=...)` calls `_autonomy_inbound(subject, body, sender)`.
  Only the subject is available there today; for full-body extraction call
  `_autonomy_inbound(subject, body, sender, "email" | "telegram" | "discord")` from any handler that has it.

## Reliability and housekeeping (audit C-01, D-01, E-01, E-03, F-01/02, G-01/02, H-01/02)

* **Approved background tasks and campaign steps are actually scheduled**: after queueing, the planner is
  run and the result says when it will run (or that it is waiting for a slot, retried every tick). A
  campaign step that never gets a slot within 24 h is marked failed, not left "queued" forever.
* Approve/dismiss are compare-and-set, so two simultaneous approvals run the action once.
* Turning autonomy off refuses new approvals, stops a worker that had not started yet, and cancels the
  task-queue items autonomy created.
* An approved action runs through the agent loop **without** writing the synthetic instruction into the
  conversation history and **without** being able to stage a catastrophic confirmation (so a later "yes"
  meant for something else cannot confirm it). The "a scheduled task is running" flag is a counter.
* Autonomy stays quiet while a command is being transcribed or run, as well as when you type or Jarvis
  speaks. At most 3 autonomy worker threads exist at once; extras are dropped and logged.
* Retention: decisions and finished suggestions 90 days, closed commitments 180 days, dynamic-tool events
  180 days (pruned at most hourly). Failed or malformed model calls are logged (`decision = error`).
* The classifier's "nothing changed" check now ignores the clock (it hashed the minute, so it never
  skipped) and includes the calendar.
* The dashboard payload trims evidence/quotes to 300 characters.

## Limits worth knowing

* A prompt-injection surface remains wherever mail/web text reaches the model. Quarantine, human-only
  approval and the review panel reduce it; a human who clicks *Approve* without reading the details still
  executes the action through the full-tool agent loop (the catastrophic gate still applies there).

* The classifier and extraction use the active brain (`CLAUDE_MODEL` or Gemini). On Gemini's free tier that
  text (conversation, mail subjects, calendar) may be used to improve Google products.
* Extraction of mail is subject-only via sleep-mail; other mail handlers must call the hook.
* Calendar context is best-effort: it uses whatever Calendar MCP `list_events` tool is connected.
* Approved calendar events depend on the agent picking the right Calendar tool; not verified live.
