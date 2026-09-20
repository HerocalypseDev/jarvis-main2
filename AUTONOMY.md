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
| Say "turn on autonomy" / "turn off autonomy" (the `autonomy` tool) | Persisted in the DB. Enabling is refused from the phone; disabling works anywhere. |
| Dashboard > Autonomy > *Turn autonomy on/off* | Same switch. |
| `JARVIS_AUTONOMY_ENABLED=1` | Default when the DB has no stored choice. |
| **`JARVIS_AUTONOMY_DISABLED=1`** | Hard kill. Overrides everything; nothing autonomous runs, enabling is refused. |
| Dashboard *Dry run* / "autonomy dry run on" | Everything is logged, nothing is executed. |
| `JARVIS_DYNAMIC_TOOLS_DISABLED=1` | No dynamic tools created, advertised or run. |

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
* Content someone else wrote (email/Telegram/Discord) can **never** auto-act through a category-wide rule,
  only through a rule naming that sender or keyword.
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

`create_tool(code_string, name, description, tests=None, dry_run=False)` — becomes `dyn_<name>`.

* Deliberately **pure computation only**: imports limited to a stdlib allow-list (json, re, math,
  datetime, statistics, collections, ...); no `eval/exec/open/getattr/...`, no underscore attributes, no
  file/network/shell/subprocess access. Needs shell/files/network? The model uses the existing tools.
* One entry function named `name`, tests are run first, then the tool runs in a separate `python -I`
  process (10 s timeout, restricted builtins/imports).
* Stored in `dynamic_tools` (hash + code); on every load the hash and scan are re-checked, so a tampered
  row is not run. Dashboard: enable / disable / revoke. Creation is refused from the phone and unattended
  runs. Deleting a tool does not refund the daily budget.

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

## Limits worth knowing

* The classifier and extraction use the active brain (`CLAUDE_MODEL` or Gemini). On Gemini's free tier that
  text (conversation, mail subjects, calendar) may be used to improve Google products.
* Extraction of mail is subject-only via sleep-mail; other mail handlers must call the hook.
* Calendar context is best-effort: it uses whatever Calendar MCP `list_events` tool is connected.
* Approved calendar events depend on the agent picking the right Calendar tool; not verified live.
