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
