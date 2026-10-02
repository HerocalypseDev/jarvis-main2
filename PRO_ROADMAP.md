# Jarvis4U Pro roadmap (private)

Plan agreed 2026-09-29, from Perplexity's research plus our review. This file stays in the private repo
(it is on `tools/export_public.py`'s EXCLUDE list). Nothing here changes what the free version does.

## Rules every phase follows

- **One product, one key.** "Jarvis4U Pro" includes every pack. New packs are free updates for
  existing buyers. The price goes up as packs are added (below). No per-pack SKUs unless sales demand it.
- **Packs are data, not code.** A pack may ship skills (`pro/skills/*.json`), colour themes
  (`pro/themes/*.css`) and, from Phase 3, macros (`pro/macros/*.json`). A pack never ships Python or JS
  that Jarvis executes. Anything that would need that (meeting vault UI, custom dashboard pages) waits
  for its own security review.
- **Same safety path.** Pack skills and macros use only existing tools, through `_execute_tool` (audit
  trail + catastrophic gate). No Pro content may weaken or bypass a rule in CLAUDE.md.
- **Never Pro:** voice core, reminders/timers, dashboard shell, audit trail, catastrophic gate, Safe
  Mode, the autonomy engine, privacy features, and **data export/backup** (Phase 6 ships it free).
- **Only advertise what exists.** README, Settings card and the Selar description list shipped packs only.
- Every phase: build with `tools/build_pro_pack.py` (validates JSON, tool names, themes), bump
  `pro_pack/manifest.json` version, extend `test_pro_pack.py`, upload the new zip to Selar, update the
  Selar description, note it in CLAUDE.md's phase log.

## Pricing path (suggestion)

| After phase | Pro contains | Price (NGN / USD / GBP) |
|---|---|---|
| now | Student pack + 2 themes | 5,000 / 5 / 5 |
| 2 | + Developer + Work packs | 7,500 / 8 / 7 |
| 5 | + Routines, more themes, Research, Autonomy recipes | 10,000 / 12 / 10 |

Selar's foreign-currency minimum is $3 / £3.

---

## Phase 1 - Developer pack (skills only)

Folder: `pro_pack/skills/dev_*.json`. Uses existing tools: `review_code`, `code_search`, `analyze_error`,
`analyze_code`, `trace_dependencies`, `check_project_health`, `delegate_to_claude_code`, `read_file`,
`write_file`, `run_shell` (read-only git commands only, stated in the instructions), `web_search`,
`list_background_tasks`.

| Skill | Says | Does |
|---|---|---|
| `dev_repo_briefing` | "brief me on this repo" | README + recent `git log` + open TODOs via `code_search`; 5-line spoken summary; optional .md saved to workspace |
| `dev_explain_error` | "explain this error" (clipboard/selection) | `analyze_error` + `code_search` for the failing symbol; cause + fix steps |
| `dev_pr_review` | "review my changes" | `git diff` (read-only) -> `review_code`; findings grouped must-fix / should-fix / nits |
| `dev_ci_summary` | "why is CI failing" | reads the pasted/linked log (`read_file`/clipboard), names the failing test and likely cause |
| `dev_handoff` | "hand this to Claude Code properly" | writes a clear task brief (goal, files, acceptance, tests) then `delegate_to_claude_code` |
| `dev_standup` | "write my standup" | yesterday's commits + background tasks -> 3-line standup |
| `dev_morning` (scheduled, off by default) | 9:00 | silent unless a watched repo has failing health checks |

Tests: every `dev_*` skill loads, names only real tools, and `run_shell` skills say read-only git only.
Acceptance: each skill tried once live by voice on the owner's PC.

## Phase 2 - Work / Founder pack (skills only)

Uses: Gmail/Calendar MCP (when connected), `briefing`, `email_reply` (drafts; sends only when asked),
`create_reminder`, `remember_fact`, `recall_facts`, `memory_search`, `write_file`, `daily_plan`.

| Skill | Says | Does |
|---|---|---|
| `work_inbox_triage` | "triage my inbox" | unread mail -> reply now / later / FYI / ignore buckets; drafts for "reply now"; never sends unasked |
| `work_meeting_prep` | "prep me for my next meeting" | next calendar event + recent mail with attendees + saved facts -> 30-second brief |
| `work_follow_ups` | "what am I waiting on" | sent mail with no reply in N days + commitments -> list + optional nudge drafts |
| `work_weekly_status` | "write my weekly update" | week's sessions, finished tasks, commitments -> status .docx |
| `work_focus_blocks` | "find me focus time" | free calendar gaps -> suggests blocks; creates events only when told |
| `work_end_of_day` | "wrap up my day" | what got done, what moved, top 3 for tomorrow -> spoken + saved note |

Rule written into each skill: third-party email text is data, never instructions (same as autonomy).
Tests as Phase 1. Acceptance: live run with Gmail/Calendar connected.

## Phase 3 - Routine (macro) pack + macro loader (small engine change)

Engine (public, free code path): `jarvis_pro.macro_specs()` reads `pro/macros/*.json`
(`{name, phrases, steps}`) only with a valid key. `jarvis_macros.match()` checks the user's own macros
first, then pack macros (user always wins on a phrase clash). Pack macros are read-only in the Toolbox
(shown with a "Pro" tag, can be switched off, not edited).

Safety: pack macro steps are limited to an allowlist of low-risk tools (`open_app`, `open_url`,
`focus_mode`, `play_media`, `play_ambient_sound`, `create_reminder`, `weather`, `briefing`,
`arrange_windows`, `restore_window_layout`, `control_window`, `system_status`, `safe_mode`). Never
`run_shell`, `run_python`, `type_text`, `http_request`, email sending or delegation. Validated at load
with the same `macros.validate()` + the allowlist; a bad macro is skipped with a log line. Steps still
run through `_execute_tool`.

Routines: "start my work day", "deep focus", "leave desk" (lock screen via `system_action` lock only),
"end of day", "movie mode", "wind down". Tests: allowlist enforced, user macro wins, key required.

## Phase 4 - More themes

3 more themes (e.g. Emerald, Solar light-on-dark amber, Mono/high-contrast). Tokens only (the loader
drops everything else and never touches the danger colours). Also fix the known cosmetic gap: turn the
hard-coded cyan rgba glows (brand text-shadow, card top highlight, nav active gradient) into
`--color-accent-*` tokens in the free stylesheet so themes recolour them too. Contrast check >= 4.5:1
for text tokens, headless screenshot of each theme.

## Phase 5 - Research pack + Autonomy recipes (skills only) - SHIPPED in pack 1.5.0

Research: `research_deep_dive` (plan -> several `web_search` rounds -> sourced .docx with a sources list),
`research_compare` (A vs B table), `research_watch` (creates a weekly `background_agents` watch; user
confirms first). Autonomy recipes: skills that set up tested background-agent / autonomy configurations
("newsletter triage", "invoice watch", "job-alert mail") **always starting in dry-run**, telling the user
how to review the Activity log and switch to live from the dashboard (turning autonomy live stays
dashboard-only, as in CLAUDE.md).

## Phase 6 - Backup & migrate (FREE, needs the dashboard double-check protocol)

Export: memory facts, profile, skills, macros, reminders, timers, settings **without** secrets (no
`.env` values matching the secret pattern, no face data, no API keys) into one file encrypted with a
password (AES-GCM, scrypt-derived key; `cryptography` is already a dependency). Import: shows a preview
and merges (never silently overwrites). Dashboard Settings buttons + `backup` tool (attended-only).
Risk review before building: the file contains personal memory (user picks where it goes), a weak
password is the user's risk, import is the only write path. Stop and ask on anything non-zero.

## Later (not planned yet)

- **Early access**: once packs ship regularly; a manifest flag + "beta" folder.
- **Priority support**: a Telegram group for Pro buyers (no code).
- **Meeting vault UI, custom dashboard pages**: need packs to run code -> separate security review.
- **Health / finance / family packs**: only with careful wording (no medical advice, no bank logins,
  privacy defaults for other people's data).
- **Separate SKUs / bundles**: only if one-product sales show demand for it.

---

# Second wave (planned 2026-10-02): seven packs + Pro dashboard widgets

From the 2026-10-02 research (what people pay for in assistant apps: proactive help, memory, meeting notes,
auto-scheduling; Nigerian students pay NGN 2,000-10,000 for WAEC/JAMB prep). Same rules as above: packs are data,
use only existing tools, go through `_execute_tool`, never ship code. Phase 14 is the one engine change.

## Shared fact formats (so packs and widgets agree)

Pack skills save structured lines with `remember_fact`, using a stable `key` so an update replaces the old line
instead of piling up. Widgets (Phase 14) read these lines by prefix. Never change a prefix once shipped.

| Prefix | Example | Key |
|---|---|---|
| `Exam:` (existing) | `Exam: Chemistry on 2026-11-03 09:00` | `exam:<subject>` |
| `Exam score:` | `Exam score: Physics 14/20 on 2026-10-02 (weak: projectile motion, units)` | `exam-score:<subject>:<date>:<n>` |
| `Study streak:` | `Study streak: 4 days, last 2026-10-02` | `study-streak` |
| `Job application:` | `Job application: Flutterwave / Junior QA / applied 2026-10-02 / status applied` | `job:<company>:<role>` |
| `Content plan:` | `Content plan: 2026-10-05 / TikTok / how I passed JAMB / status idea` | `content:<date>:<title>` |
| `Habit:` | `Habit: gym / mon,wed,fri / 18:00` | `habit:<name>` |
| `Week plan:` | `Week plan: 2026-W40 / 5 focus blocks / top: finish CV` | `week-plan:<iso-week>` |

## Phase 7 - Exam pack (JAMB / WAEC / NECO), pack 1.6.0

Builds on the Student pack. Questions are generated in the exam's style, never copied from real past papers.

| Skill | Says | Does |
|---|---|---|
| `exam_cbt_practice` | "JAMB practice: physics, 10 questions" | Asks N multiple-choice questions one at a time (4 options, one correct), keeps score, a `create_reminder` for the time limit, then saves an `Exam score:` line with weak topics and a streak update |
| `exam_weak_topics` | "drill my weak topics" | Reads the `Exam score:` lines, picks the weakest topics, runs a short drill with explanations |
| `exam_study_plan` | "make me a 7-day JAMB plan" | Subjects + exam date (from `Exam:` facts) -> day-by-day plan .docx in the workspace + a `Study plan:` fact |
| `exam_progress` | "how am I doing in physics" | Score trend per subject from the `Exam score:` lines, best/worst topic, days to the exam |
| `exam_daily_drill` (scheduled 19:00, `requires_fact: "Exam score:"`) | - | Silent unless no practice was logged today and an exam is within 30 days: one nudge line |

Tests: skills load, names only real tools, the scheduled one is silent and gated, no skill claims real past papers.

## Phase 8 - Meeting Memory pack, pack 1.7.0

On top of the free `meeting_notes` (start/stop/list/get). Meeting text is other people's speech: data, never instructions.

| Skill | Says | Does |
|---|---|---|
| `meeting_decisions` | "what did we decide about the launch" | `meeting_notes` list + get the matching notes -> decisions with meeting name and date |
| `meeting_owe` | "what do I owe people from meetings this week" | action items from this week's notes that are the user's |
| `meeting_to_email` | "turn my last meeting into an email" | a follow-up email DRAFT (decisions, owners, dates); never sends |
| `meeting_prebrief` | "brief me for my next meeting" | next calendar event (`mcp_calendar`) + notes from earlier meetings with the same title/people |

## Phase 9 - Job Hunt pack, pack 1.8.0

Never invents experience, grades, dates or skills: only what the user's CV/memory says; gaps are asked about.

| Skill | Says | Does |
|---|---|---|
| `job_cv_tailor` | "tailor my CV for this job" (job ad copied) | reads the CV file (`read_file`) + the ad (`read_clipboard`) -> tailored CV .docx + list of changes |
| `job_cover_letter` | "write a cover letter for this job" | short cover letter .docx from the CV + ad |
| `job_tracker` | "I applied to X for Y" / "what jobs have I applied to" | `Job application:` facts (status applied/interview/offer/rejected) + a follow-up reminder 7 days later |
| `job_interview_prep` | "prep me for the Y interview" | 8 likely questions for the role, one at a time, with feedback on the user's answers |

## Phase 10 - Creator / Seller pack, pack 1.9.0

| Skill | Says | Does |
|---|---|---|
| `creator_product_copy` | "write a Selar description for my product" | title, hook, benefits, what's inside, FAQ, call to action; honest claims only |
| `creator_captions` | "captions for my TikTok about X" | 3 caption options + hashtags per platform asked |
| `creator_content_plan` | "plan my content for next week" | 7-day plan .docx + `Content plan:` facts |
| `creator_customer_reply` | "reply to this customer" (message copied) | a polite reply draft; never sends; refunds/promises left for the user to decide |
| `recipe_sale_alert` | "tell me when I make a sale" | `background_agents` mail_match on Selar/Paystack sale emails -> reminder; created switched OFF |

## Phase 11 - Smart Scheduler pack, pack 1.10.0

| Skill | Says | Does |
|---|---|---|
| `plan_my_week` | "plan my week" | calendar (`mcp_calendar`), reminders, task queue and commitments -> proposed focus blocks in free gaps; creates events only after "yes, add them"; saves a `Week plan:` fact |
| `habit_blocks` | "add gym Mon/Wed/Fri at 6pm" | `Habit:` fact + weekly repeating reminders (`repeat_every_minutes` 10080) |
| `week_review` (scheduled Fri 17:00, `requires_fact: "Week plan:"`) | - | one spoken line: what got done vs planned, what slipped |

## Phase 12 - Gamer pack, pack 1.11.0

| Item | Says | Does |
|---|---|---|
| routine "Game mode" | "game mode" | focus on, minimise windows, a 60-minute break reminder |
| `gamer_session` | "gaming session for 2 hours" | break reminders every 45 min + a stop reminder; eye/water tip lines |
| `gamer_patch_notes` | "what changed in the latest X update" | `web_search` -> short patch summary with sources |
| `gamer_discord_post` | "write a Discord announcement for X" | a formatted announcement draft (headings, emojis optional); never posts |
| `gamer_roblox_dev` | "help me with my Roblox game" | `roblox_companion` start/status/review for the user's project |

## Phase 13 - More themes, pack 1.12.0

Naija (green), Festive (red + gold, for December), Daylight (a light theme). Each passes the loader's contrast check;
headless screenshot of Home + approval bar with each.

## Phase 14 - Pro dashboard widgets (engine change, free code path + pack data), pack 2.0.0

**What it is:** a "Pro" section on the Home page showing small live cards built from the facts the packs save:
exam countdown, score trend, study streak, job application board, content plan, this week's plan, upcoming reminders.

**Design (no pack code ever runs):**
- A pack ships `pro/widgets/*.json` specs only: `{id, title, type, source, prefix?, limit?}`.
- `type` is one of a fixed set the free dashboard knows how to draw: `list`, `countdown`, `score_trend`, `board`, `stat`.
- `source` is one of a fixed set the free core knows how to read, read-only: `facts` (active memory facts starting with
  `prefix`), `reminders` (upcoming), `meetings` (recent titles). Anything else in a spec is ignored.
- `jarvis_pro.widget_specs()` loads and validates specs only with a valid key; a bad spec is skipped with one log line.
- `GET /api/feature/pro_widgets` (existing `@_feature` route family, so the Host/Origin middleware covers it) returns
  each widget's computed data. Read-only, no write path, no new table.
- The frontend draws each type with fixed code; every string goes through `esc()`. No HTML, CSS or JS from the pack.
- Without a key: the section is hidden and the route returns `{"active": false}`. Free features never change.

**Risk review (dashboard double-check protocol):**
- Maps onto: `memory_facts`, `reminders`, `meetings` tables (read), the `@_feature` route family, the Home page.
- New: one read-only route, one loader function, a Home section. No new table, no write path.
- Security: localhost-only like every route; existing Host/Origin middleware; text escaped; specs can't inject markup
  (only enum values and a prefix string are used, prefix used as a SQL parameter).
- Cost: none (local SQL, no model call). Data exposure: shows the user's own facts on their own localhost page, same
  as the Memory route. Irreversibility: none (read-only). Performance: a few small queries per 30 s Home refresh.
- Result: no new risk beyond the existing Memory route, so it is built without a stop-and-ask.

Tests: spec validation (bad type/source/prefix dropped), key gating, each type's computation (countdown days, score
percentages, board grouping), route through the middleware, headless render of the Home section.

## Pricing after the second wave (suggestion)

| After phase | Price (NGN / USD / GBP) |
|---|---|
| 10 | 12,500 / 14 / 12 |
| 14 | 15,000 / 17 / 14 |
