# Full Autonomy Stack

Jarvis can move from "answers when asked" to "notices what you have committed to and does something about
it": it extracts commitments and projects from conversation, mail and file activity, keeps them across
days, watches deadlines, creates the calendar events / reminders / background tasks they imply, retries
what fails, learns from what you dismiss, runs multi-day campaigns, and composes repeated work into skills.

> **Permission model (explicit user decision, 2026-09-20): FULL AUTO-ACT, except catastrophic actions.**
> Autonomy is **ON by default** (user decision 2026-09-20; set `JARVIS_AUTONOMY_ENABLED=0` or use the
> dashboard toggle to start/keep it off). While on, it does **not ask** before acting. The only things that still need a
> spoken "yes" or a dashboard Approve are the catastrophic tier already enforced in `jarvis.py`
> (`_CATASTROPHIC_PATTERNS` / `_pending_action`: shutdown, restart, sign-out, disk format/partition,
> recursive wipe of a drive or profile). That gate is untouched, and no autonomy module references it
> (an AST test pins this). Everything is logged, and you can switch autonomy off or into dry-run at any time.

Files: `jarvis_autonomy.py` (core), `jarvis_autonomy_skills.py`, `jarvis_dynamic_tools.py`,
`jarvis_memory_consolidation.py`, `dashboard_static/autonomy.js` (Autonomy tab), tests in `test_autonomy.py`.

## Turn it on / off (and the emergency stop)

| How | Effect |
|---|---|
| Default | **On** from the first start (mail polling every 10 min, file bridge, tick, skills all active; dry-run is off, so it acts for real). A choice saved in the DB beats the default. |
| Dashboard > Autonomy > *Turn autonomy on/off* | The only way to turn it back **on** at runtime after switching it off (`JARVIS_AUTONOMY_ENABLED=0` starts it off). Persisted in the DB. |
| Say "turn off autonomy" (the `autonomy` tool) or the dashboard button | Off from anywhere; also cancels the task-queue items autonomy had started. |
| **`JARVIS_AUTONOMY_DISABLED=1`** | Hard kill. Overrides everything; nothing autonomous runs, enabling is refused. |
| Dashboard *Dry run* / "autonomy dry run on" | Everything is decided and logged, nothing is executed (`outcome = dry_run`). |
| `JARVIS_DYNAMIC_TOOLS_DISABLED=1` | No dynamic tools created, advertised or run. |

Turning autonomy **on**, writing/loosening policy rules and leaving dry-run are *settings*, not actions
autonomy takes, so they are dashboard-only (`HUMAN_ONLY_ACTIONS`). Everything else, including approving
a recorded card, accepting a commitment and approving a campaign, the model may do by voice.

## The policy engine (what "default auto_act" means in code)

`evaluate_policy(category, sender, text, confidence, action_type, source_type)` in `jarvis_autonomy.py`:

* **No matching rule -> `auto_act`** for every non-catastrophic action type (`calendar`, `reminder`, `email`,
  `file_op`, `background_task`, `notification`), from **any** source: your own words, mail, Telegram,
  Discord, files, the classifier. There is no source-based and no action-type-based guard any more.
* The only gate is a confidence floor, `JARVIS_AUTONOMY_AUTO_MIN_CONF` (default **0.7**). Below it the item
  is **recorded** as a dashboard card ("Recorded for review") instead of acted on. That card is visibility,
  not a question: nothing blocks on it.
* Rules (`autonomy_policies`, most specific wins: sender > keyword > category, newest first):
  `auto_act` (optionally with its own `min_confidence`), `ignore` (silence a category), and `ask_once` /
  `always_ask` (only a user can write these; they make a card and wait, as an explicit override).
  A sender rule matches the **exact address** (or `@domain.com`), never a substring or display name.
* **Teach loop** (`record_feedback`): dismissing a category's cards twice in a row turns a *learned* rule
  into `ignore`; approvals reset the streak. A learned rule may auto-act on **any** action type. Nothing
  learned can make Jarvis ask more. A recently dismissed category is skipped for
  `JARVIS_AUTONOMY_DISMISS_COOLDOWN_MIN` (180).
* **Budgets are soft**: `JARVIS_AUTONOMY_MAX_ACTS_PER_DAY` (10) is logged, and going over it never turns an
  action into an ask; a 5x runaway breaker (50/day by default) is the only thing that stops. Concurrent
  background tasks (`..._MAX_BG_TASKS`, 2) is a real capacity limit: an extra step waits, planned.
* **The user is busy** (typing, speaking, mid-command, Focus/Sleep Mode): notifications and reminders
  still happen (delivery/speech timing belongs to `queue_or_deliver_notification`); an action that needs
  an agent-loop run (`calendar` without a direct path, `email`, `file_op`) goes on an *auto queue* and runs
  the moment the user is idle again. It is never asked about.
* A failed autonomous action is logged (`outcome = failed`) and you get a short notification.

Approved/auto `calendar`/`email`/`file_op` actions that need the agent run through the **normal agent loop**
(`run_agent_loop` -> `_execute_tool`), so if one of them ever reaches a catastrophic command, that command is
*staged* for your yes exactly like a user-initiated one, and nothing runs until you confirm it.

## Work package 1 - inbound perception

`process_inbound_message_for_events(subject, body, sender, source, message_id="")` is the single inbound hook
(`source` in `email` / `telegram` / `discord` / `message`). It always uses the real body when there is one;
with only a subject it still extracts but scales confidence by 0.85. Meetings become `event` commitments,
tasks become `task` commitments; confident ones act at once. Every attempt writes an `inbound` row to
`autonomy_decisions` (+ `action_audit`). `message_id` de-duplicates across call sites (`autonomy_seen_messages`).

Call sites:

| Path | Where | What it passes |
|---|---|---|
| Sleep-mail (while Sleep Mode is on) | `jarvis_sleep_mail.run_cycle` reads each non-family message and calls `on_inbound` -> `jarvis._autonomy_inbound` | subject + **full body** + sender + id |
| Normal Gmail inbox | `jarvis._autonomy_poll_mail` (the `poll_mail` callback) via the tick's `_inbox_poll`, every `JARVIS_AUTONOMY_MAIL_POLL_MIN` min (default 10, **0 = off**) | new inbox messages (not yours, not seen) with bodies, up to 5 per poll |
| Telegram / ntfy | messages **you** send are commands: they go through `handle_text_command` -> `autonomy.after_turn` (extraction) | your own words |
| Discord | there is no inbound Discord handler in Jarvis (only the optional MCP). Any code that gets a Discord message should call `jarvis._autonomy_inbound(subject, body, sender, "discord", id)` | n/a today |
| File watcher | `_file_scan` reads `filewatcher.watcher.recent_events`; a NEW document file (`.pdf .docx .doc .xlsx .pptx .csv .zip .epub`) in a watched folder becomes a "Review new file ..." commitment + a notification, once. It never moves or deletes files by itself | path |

**Data exposure:** mail bodies (and Gmail polling) go to the active brain. On Gemini's free tier that text may
be used to improve Google products. Set `JARVIS_AUTONOMY_MAIL_POLL_MIN=0` to stop the polling.

## Work package 2 - extraction

`after_turn` extracts when `_should_extract` says so: the cheap cue regex (fast path), **or** the user's message
is at least `JARVIS_AUTONOMY_EXTRACT_MIN_CHARS` (240) long, **or** it is >= 40 chars with future/obligation
phrasing ("will", "at 9am", "on Friday", "before", "due" ...). `JARVIS_AUTONOMY_EXTRACT_ALWAYS=1` skips the gate.
Extraction sees `semantic_recall` of the exchange ("Related memory: ..."). Quality rules in `add_commitment`:
near-duplicates (same words, Jaccard >= 0.75, same day when both have one) **update** the existing item
(higher confidence, missing deadline/quote filled) instead of inserting; confidence is clamped to 0..1; a
past or >3-year deadline is dropped (item kept); a source quote is always stored (falls back to the text).
A turn that read mail/web/files/screen is tagged `message`, and a **low-confidence** item from another
person's words is stored *quarantined* (kept out of prompts and nudges until you accept it); a confident one acts.

## Work package 3 - observability

* Voice/text: "show autonomy log", "what did autonomy do today", "why did you do X", "read out the autonomy
  log" (`autonomy` tool actions `log`, `why`, `speak_log`; the spoken copy goes through `_speak_shaped`).
* Dashboard > Autonomy > **Activity log**: filter by time range, type (act / inbound / queued / recorded /
  skipped / skill / error), outcome (ok / failed / dry run / skipped / info), category and free text; each row
  expands to *why* (policy reason), the source quote, what was done, the payload and the result. The budget
  usage line and the *Turn autonomy off* / *Dry run* buttons are on the same tab. API: `GET /api/autonomy/log`.
* Storage: `autonomy_decisions` now has `category`, `source_quote`, `payload_json`, `result`, `outcome`
  (auto-migrated), and every row is mirrored to `action_audit`.

## Work package 4 - deterministic calendar and reminders

`calendar` actions try `_direct_calendar` first: `jarvis._autonomy_create_event` finds the connected Calendar
MCP create-event tool and `build_calendar_args` maps title/start/end/location onto **that tool's own input
schema** (it never invites attendees). If there is no usable tool/schema, or the call reports an error, it
falls back to the normal agent loop. Reminders always use `create_reminder` directly. Direct calendar creation
is audited (`autonomy_direct_calendar`).

## Work package 5 - composable skills (`jarvis_autonomy_skills.py`)

A skill is a named, ordered list of `{tool, input}` steps that only names tools that **exist right now**
(checked at creation and on every run), cannot call itself, and runs each step through `_execute_tool`, so all
existing guards, the audit log and the catastrophic gate apply: it gains no new power. `{placeholder}` values in
inputs are filled from `params`. The model creates/runs them with the `autonomy_skill` tool; a sequence of 2-6
tools (shell/python steps excluded) that you run identically `JARVIS_AUTONOMY_PATTERN_MIN` (3) times becomes a
skill automatically (`auto_<hash>`). Dashboard: list / enable / disable / revoke. Dynamic *tools* (below) stay
pure computation; skills are the way to compose real side effects.

## Work package 6 - memory intervention and campaigns

* Deadline scan (no model): open commitments at **24 h / 2 h / overdue** get a nudge once per bucket; at the
  24 h bucket, if nothing was already done for the item, the action it implies (reminder / calendar event) is
  taken too, without asking.
* The classifier's memory context uses `semantic_recall` over the nearest open commitments.
* Campaign steps run a status machine: `planned -> running -> done | blocked | cancelled` (`simulated` for
  high-risk projects unless their metadata says `live`). A failed step (task failed/cancelled, never got a
  slot in 24 h, queue refused) is **retried up to 3 attempts, 10 minutes apart**, then `blocked` and you are
  told. Ordinary steps are never turned into an ask. Approved background tasks are actually planned into a slot.

## How the tick works

`jarvis.py`'s scheduler loop (`SCHEDULER_TICK_S`, 60 s) calls `autonomy.tick(now)`; when enabled the pass runs on
a worker thread. Free/deterministic steps: expire and prune, deadline scan, campaigns, planner, re-plan
pending tasks, run the auto queue, file scan, mail poll. Model steps (only when the user is not busy):
summarise idle conversation, memory consolidation, speak one recorded card, and the rate-limited classifier
(every 15 min, skipped when nothing changed). At most 6 autonomy worker threads exist at once.

## Dynamic tools

`create_tool(code_string, name, description, tests)` validates (scan + your tests) and registers `dyn_<name>`
straight away. It is **not a hard security boundary**: allow-listed modules can re-export `os`/`sys`, so the
runner strips sub-modules and underscore names from every allowed module, runs in a `python -I` process with a
10 s timeout, a Windows Job Object (256 MB, no child processes) and capped output. Treat every tool as if it could
run with your privileges. An existing name is never overwritten; 3 new tools per day.

## Safety that stays

Hard kill, dry run, the catastrophic gate, exact-sender matching, text sanitising (control characters, newlines,
lengths) before anything is stored/spoken/embedded in a prompt, the agent being told action data is data not
instructions, a runaway breaker, retention (decisions 90 days, closed commitments 180), and full logging.
A prompt-injection surface remains wherever mail/web text reaches the model; under this model a confident
injected instruction **can** cause a calendar event, a reminder, an email or a background task. The log and
the off switch are the mitigations.

## Audit-and-fix pass (2026-09-20, after the full-permission change)

Behaviour that changed because a real bug was found:

* **Dry-run no longer burns work.** Items extracted in dry-run were stored, so they became "duplicates" and were
  never acted on once dry-run ended, and the deadline scan used up the real 24 h / 2 h / overdue nudges.
  Now dry-run keeps separate bookkeeping (`dry_notified`, `dry_actioned`, commitment `dry_run` flag) and *leaving*
  dry-run replays what it only logged.
* **Old learned "ask" rules are migrated.** Rules learned before the permission change (`always_ask`/`ask_once`,
  source `learned`) still forced an ask; they are converted to `auto_act` on startup. Rules you wrote are kept.
  A user-written `ask_once` really is "once": the first approval turns it into `auto_act`.
* **Teach loop is recoverable.** A learned `ignore` lapses after `JARVIS_AUTONOMY_LEARNED_IGNORE_DAYS` (30) and
  is never learned for `deadline:*` categories. Dismissing a *card* only suppresses further cards for that
  category; it no longer silences confident autonomous actions there.
* **The tick is never held up.** Agent-loop actions decided on the tick thread go to the auto queue, and the
  queue drain and the mail poll run on bounded workers (6 at most, one queue drain at a time), so a slow model
  call cannot starve the deadline scan. Campaign steps and the classifier retry after failures (a failed
  classifier call no longer makes the "unchanged context" shortcut skip its own retry).
* **Capacity is a wait, not a failure.** "Too many background tasks" puts the action on the auto queue instead
  of failing and notifying. The kill switch is also checked inside `_run_action`, so a worker that had already
  decided cannot act after autonomy is turned off. An agent reply that admits failure ("Sorry, I couldn't ...")
  or is empty counts as a failure, not a success.
* **Campaigns.** Steps run **without an approval step** (`approve_campaign(project, false)` *pauses* a project,
  `true` resumes it). A step whose task is stuck `running` for 6 h (Jarvis restarted mid-run) or whose queue row
  disappeared is recovered like any other failure.
* **Inbound.** A failed extraction releases the message so the next poll retries it (3 tries, then dropped); an
  unreachable Gmail retries in ~2 min instead of a full interval; one bad item no longer loses the rest of a batch;
  duplicate check + insert is one atomic step (two workers no longer double-insert). The sleep-mail hook reads a
  message body only while autonomy is enabled.
* **Housekeeping.** `autonomy_seen_messages` (60 days) and `autonomy_patterns` (60 days) are pruned.
  Consolidation writes a "learned rule" memory fact only for 3 approvals / 2 dismissals in a row (it used to write
  "repeatedly approved" after one) and retires facts for rules that no longer exist.
* **Skills.** Patterns are never mined from tools that type/click, send messages, write files, call HTTP, or change
  Jarvis (they can carry passwords/PINs/auth headers), nor from inputs over 1500 characters; the daily creation
  budget is enforced atomically.

Intentional and unchanged: high-risk projects are still *simulated* unless their metadata says `live`; a
user-written `ask_once`/`always_ask`/`ignore` rule is honoured; the confidence floor records (not acts on)
low-confidence items.

## How to verify (do this before trusting it)

1. **Dry run first.** Dashboard > Autonomy > *Dry run (log only)*, then *Turn autonomy on*. Nothing executes.
2. **Inbound mail.** Email yourself from another address: "Lunch with Sam next Thursday at 1pm in Room 4".
   Within `JARVIS_AUTONOMY_MAIL_POLL_MIN` minutes the Activity log shows an `inbound email` row
   ("N new item(s) from the body"), then an `act` row for the calendar event. Test the fallback: a subject-only
   message is logged as "from the subject only" at lower confidence (may be *recorded* instead of acted on).
3. **Calendar.** Leave dry run and repeat. In the log expand the `act` row: `Result` starts "Calendar event
   created directly" (direct MCP path) or shows the agent-loop reply (fallback). Confirm the event in Google
   Calendar. Say "why did you add that?" to hear the reasoning.
4. **Reminders.** Say "I need to send the report by tomorrow 5pm": a reminder appears in `list_reminders`.
5. **Files.** Drop a PDF into a watched folder (Downloads): a "New file ..." notification and a commitment.
6. **Catastrophic still asks.** Say "shut down my computer": it is staged, the dashboard shows the pending
   action, nothing runs until you say yes / Approve.
7. **Off switch.** *Turn autonomy off*: queued tasks it started are cancelled; `JARVIS_AUTONOMY_DISABLED=1` blocks
   it entirely.

Not verified live (unit-tested with fakes and the real task scheduler only): a real model extraction, the
Gmail poll against a real inbox, the Calendar MCP's actual create-event schema, and the new dashboard sections
in a real browser.
