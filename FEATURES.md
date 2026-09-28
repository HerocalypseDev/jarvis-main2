# Feature batch 2026-09-27

A set of cheap, local-first features. Rules that apply to every feature here:

- No always-on heavy work. Anything continuous or costly is opt-in (meeting capture, code index).
- Every tool call goes through `_execute_tool`, so it is audited in `action_audit` and the
  catastrophic confirmation gate applies. Nothing here calls `skip_confirmation`.
- One agent tool per feature, with an `action` field, so the cached tool prefix grows as little as
  possible. Handlers live in `_BATCH_TOOL_HANDLERS` in jarvis.py.
- Dashboard: every feature uses the generic `GET /api/feature/{name}` and
  `POST /api/feature/{name}/{action}` routes (`providers["feature:<name>"]`, registered with the
  `@_feature(name)` decorator in jarvis.py). The dashboard's Host/Origin middleware covers them.
  UI lives on the **Toolbox** route (`dashboard_static/features.js`).
- Tests use a temp DB (`JARVIS_MEMORY_DB_PATH`) and never the real `jarvis_memory.db`.

## Phase A

| Feature | Code | Default | Settings |
|---|---|---|---|
| A1 Clipboard history | `jarvis_clipboard_history.py`, tool `clipboard_history` | on | `JARVIS_CLIPBOARD_HISTORY`, `JARVIS_CLIPBOARD_HISTORY_MAX` (50) |
| A2 Everything file search | `jarvis_everything.py`, tool `quick_search` | on when Everything is installed | `JARVIS_EVERYTHING_URL`, `JARVIS_EVERYTHING_ES` |
| A3 Device names | `jarvis_netscan.py`, tool `network_devices` | on | `JARVIS_NETSCAN_ANNOUNCE_NAMED` (1) |
| A4 Voice macros | `jarvis_macros.py`, tool `macros` | on (no macros until you make one) | - |
| A5 Battery saver | `jarvis_battery.py` | on | `JARVIS_BATTERY_SAVER`, `JARVIS_BATTERY_LOW_PCT` (20), `JARVIS_BATTERY_CRITICAL_PCT` (10) |
| A6 Deadline prep | `_deadline_context` (jarvis.py) + `_deadline_scan` (jarvis_autonomy.py) | on with autonomy | - |

**A1 Clipboard history.** A daemon thread reads Windows' clipboard sequence number once a second
(a counter, the clipboard is not opened) and reads the text only when it changes. Last 50 copies
in `clipboard_history`, deduplicated by SHA-256. Privacy: copies that password managers mark
private (`ExcludeClipboardContentFromMonitorProcessing`, `CanIncludeInClipboardHistory = 0`,
`Clipboard Viewer Ignore`) are never read. Secret-looking text (API keys, bearer tokens, JWTs,
private keys, `password:` lines, long key-like strings) is stored as hash + length only: no text,
no preview, `get` refuses it. The selection hotkey's own sentinel/restore copies are skipped.
Nothing reaches the model unless the tool is called. Clearing the history needs the PC (not phone).

**A2 Everything.** Tries Everything's HTTP server (loopback only, so the query never leaves the
PC), then `es.exe`. No disk-walk fallback on purpose: without Everything the tool says how to set
it up. Install: voidtools Everything, then Tools > Options > HTTP Server > enable, bind
127.0.0.1, set a port (default 80 conflicts with other servers, 8080 is common).

**A3 Device names.** `network_device_names` (keyed by MAC, so a name follows the device across
networks). New-device notices use the name. A **named** device that comes back after 30+ minutes
away is announced ("John's iPhone joined the network"); unnamed ones are not, so sleeping phones
don't cause chatter. Rename from the Home network card's "Name" button or by voice.

**A4 Voice macros.** `macros` table: name, trigger phrases (2+ words), steps `[{tool, input}]`.
A command that normalises to a trigger phrase (lower case, punctuation, apostrophes and leading
"jarvis"/"please" removed; exact match only, add extra phrases for variants; max 12 words) runs the
steps with **no LLM call**, before intent routing. Steps must be existing tools (built-in, dynamic,
or connected MCP); a macro cannot call the `macros` tool. Each step goes through `_execute_tool`
(audited, gated); a staged catastrophic step stops the macro and says so. Creating, changing or
deleting macros needs voice/typed/dashboard, not phone/autonomy. Dashboard: Toolbox > Voice macros
(form builder with tool dropdown + JSON input per step, this also covers D1).

**A5 Battery saver.** Each scheduler tick: on battery only, `low` (<= 20%) runs autonomy every 5
min instead of every minute and the network scan every 5x its interval; `critical` (<= 10%) runs
autonomy every 15 min, pauses the network scan and holds non-urgent announcements until the user
next talks to Jarvis. One spoken notice per crossing (critical is urgent), one when power is back;
audited as `battery_mode`. Nothing is killed, nothing hibernates. Desktops are always normal.

**A6 Deadline prep.** When autonomy nudges a commitment at 24 h / 2 h / overdue, the nudge also
carries related memory facts (local TF-IDF, same as per-command retrieval) and, for the 24 h and
2 h nudges, up to 3 recent Gmail **subjects** (one search, `newer_than:30d`). Once per bucket, never
per tick. Calendar blocking is unchanged: autonomy's existing 24 h action path already does it.
Not added in dry-run.

Residual risks (Phase A): clipboard history keeps ordinary copied text (e.g. a pasted address) in
the local DB; turn off with `JARVIS_CLIPBOARD_HISTORY=0`. The secret detector is a heuristic and
can miss an unusual secret format. Everything's HTTP server, if bound to 0.0.0.0 by the user, would
expose file names to the LAN; that is Everything's setting, not Jarvis's.

## Phase B

| Feature | Code | Default | Settings |
|---|---|---|---|
| B1 Meeting notes | `jarvis_meeting_capture.py`, tool `meeting_notes` | **off** (starts only when asked) | `JARVIS_MEETING_AUTO` (0), `JARVIS_MEETING_MAX_MIN` (120), `JARVIS_MEETING_SILENCE_MIN` (10) |
| B2 File index + tags + duplicates | `jarvis_file_index.py`, tool `find_files` | on (watched folders only) | `JARVIS_FILE_TAG_LLM_PER_HOUR` (10) |
| B3 App shortcuts | `jarvis_app_shortcuts.py`, tool `app_shortcuts` | on (none until you add one) | - |
| B4 Email drafts + templates | `jarvis_email_templates.py`, tool `email_reply` | on | - |
| B5 Voice tone | `jarvis_voice_tone.adapt` | on | - |

**B1 Meeting notes.** Opt-in only. Start: "start meeting notes" (voice/typed/dashboard, not phone)
or the Toolbox button; with `JARVIS_MEETING_AUTO=1`, also when a Zoom/Teams/Meet/Webex/Skype/Jitsi
window is in front (once per window; never in safe mode or on a critical battery). Captures the
**speakers only** through WASAPI loopback (`soundcard`, new dependency, pinned), so it records the
other people, not the user's microphone. Audio is read in 2 s pieces (stop takes effect within 2 s)
and sent to STT in 30 s chunks through the normal `transcribe_pcm` (Deepgram, falling back to local
Whisper); silent chunks are never sent. Ends on "stop meeting notes", max duration, silence timeout,
or (auto sessions) the meeting window closing. On stop, ONE model call returns a summary + action
items (transcript framed as data); action items go through `autonomy.ingest_external(...,
"message", "meeting")`, i.e. the third-party commitment path with its 0.85 confidence bar. Tables
`meetings`, `meeting_segments`. Verified live: loopback capture on this PC's Realtek speakers.
**Not verified live**: a full meeting end to end (would send real call audio to Deepgram and the AI).

**B2 File index.** The file watcher now has `listeners`; the index queues each new/changed file and
one worker thread (ends itself after 60 s idle) stores size, extension, mtime, SHA-256 (<= 512 MB),
and tags: extension category, folder, name keywords, and keywords in the first 2000 characters of a
PDF/DOCX/TXT (invoice, receipt, statement, resume, contract, ticket, screenshot, tax, homework,
certificate). A document with no rule tag beyond its category gets one model call (first 1500
characters, framed as data), capped at `JARVIS_FILE_TAG_LLM_PER_HOUR`; tags are reused for identical
files by hash. Partial downloads (.crdownload/.part/.tmp) are skipped. Nothing is ever moved.
`find_files` answers from SQLite only; vanished files are pruned when read. "Index what's already
there" queues existing files in watched folders (top level + one level down, 2000 max).

**B3 App shortcuts.** `app_shortcuts` table: app (process name, or `title:<regex>`), phrase, and
`keys` (sent only if that app is still in front), `say` (the phrase is run as a normal Jarvis
command), or `macro`. A foreground tracker (one Win32 call every 1.5 s, skips any window titled
"Jarvis...", i.e. the dashboard tab) remembers the last real app. Matching runs before macros and
intent routing, and only for voice/typed commands (never from phone or dashboard, so keys are never
pressed remotely). Runs are audited as `app_shortcuts` tool calls. The Alt+K palette lists the
current app's shortcuts first.

**B4 Email drafts.** `email_reply action=suggest` makes one model call for up to 3 drafts (email
framed as data; instructed not to promise or leak). No send path exists in the module (pinned by a
test); sending stays a separate, explicit Gmail tool call. Templates (`email_templates`) with
`{placeholder}` filling are offered to the model as starting points; saved only when the user asks.

**B5 Voice tone.** Local text heuristics only (no audio emotion API, no model). New frustration cues
("for the last time", "I already said"...), a **repeated** signal (same command again within 2 min:
the reply prompt says the last answer missed and to try another approach) and a **brief** signal
(<= 5 words, not a question: "reply in one short sentence"). Goes into the volatile system block only.

Residual risks (Phase B): meeting transcripts and summaries go to Deepgram and the active AI (on
Gemini's free tier Google may use them); a meeting participant could try prompt injection through
speech (framed as data, action items use the third-party bar). The AI file tagger sends the start of
new documents to the active AI; set `JARVIS_FILE_TAG_LLM_PER_HOUR=0` for rules only. App shortcut
`keys` can be any key combination the user saves (e.g. alt+f4); they only fire for the saved app.

## Phase C

| Feature | Code | Default | Settings |
|---|---|---|---|
| C1 Background agents | `jarvis_agents.py`, tool `background_agents` | on (none until you make one) | - |
| C2 Code review | `jarvis_code_tools.review`, tool `review_code` | on demand | uses `JARVIS_SMART_MODEL` on Claude |
| C3 Code search | `jarvis_code_tools.search`, tool `code_search` | on demand | `JARVIS_RG_PATH`, `JARVIS_CODE_ROOTS` |
| C4 Memory full-text search | `jarvis_memory_search.py`, tool `memory_search` | on | - |
| C5 Lite knowledge graph | `jarvis_kg.py`, tool `knowledge_graph` | on (syncs every 30 min) | - |
| C6 Announcement priority | `jarvis_notify_priority.py` | on | `JARVIS_NOTIFY_SMART` (1), `JARVIS_NOTIFY_DIGEST_MIN` (60) |

**C1 Background agents.** `agents` table. Triggers: `interval` (>= 5 min), `daily` (HH:MM, optional
weekdays; runs once if the PC is on within 6 h after the slot), `mail_match` (a Gmail search every 10
min; the first check is a silent baseline; each new message runs the steps once with sanitised
`{subject}`/`{sender}`), `file_event` (fed by the file watcher; `{path}`), `manual`. `{subject}`/`{sender}`/`{path}` are only allowed (and only filled) in reminder/search-type
steps (`jarvis_agents.FILL_TOOLS`), never in anything that runs code, types, sends or writes. Steps are
existing tools only (not `background_agents`/`macros`), each through `_execute_tool` (audited with
transcript `(background agent NAME)`, catastrophic gate intact; a staged step stops the run), plus an
`agent_run` audit row. Runs on worker threads from the 60 s scheduler tick, single flight per agent,
never a process per agent. `max_runs_per_day` (default 24, max 288). A failure is announced once
until a run succeeds; hitting the budget is announced. Paused in safe mode and on a critical battery.
Creating/changing agents needs voice/typed/dashboard.

**C2 review_code.** A file (<= 60k chars, line-numbered, refused for `.env`/keys/Jarvis DBs via
`sensitive_reason`) or a repo folder's `git diff HEAD`. ONE model call (the smart model on Claude),
code framed as data, JSON findings (severity, line, issue, fix). Never edits anything.

**C3 code_search.** ripgrep (`rg` on PATH / `JARVIS_RG_PATH`, skips `.env*`, `*.pem`, `*.key`), else
`git grep` in a repo, else a bounded scan (5000 files, vendor folders skipped). Needs a folder (or
`JARVIS_CODE_ROOTS`); never the whole disk. Hits in files `sensitive_reason` refuses are dropped.
`JARVIS_CODE_INDEX` (embeddings) is **not built**; see Later.md.

**C4 memory_search.** FTS5 table `memory_fts` over active facts, conversation turns and summaries,
filled incrementally at search time (no triggers in the owning modules). BM25 + a fact bonus + a
recency bonus. Rows deleted or replaced at the source are filtered out and purged from the index.
Falls back to the existing TF-IDF `semantic_recall` when no fact matched. No re-ranker API.
Measured on a copy of the real DB: first search (indexing ~3k rows) 0.17 s, later ones ~0.04 s.

**C5 knowledge graph.** `kg_nodes`/`kg_edges`, derived every 30 min (0.05 s on the real DB) from
relationship facts with an email (person), autonomy projects, commitments (task, `part_of` project,
`asked_for` from the sending person) and meetings; derived nodes whose source is gone are removed.
User-stated links via `knowledge_graph action=relate` (attended only). `query` walks up to 2 hops.

**C6 Announcement priority.** Each proactive announcement gets a kind (inferred from its text:
network, deadline, autonomy, battery, meeting, agent, file, health, other; reminders are `reminder`).
Cutting it off (push-to-talk barge-in or "stop") counts as dismissed; talking to Jarvis within 2 min
without cutting it off counts as acted. After 5 outcomes, a kind with an act rate under 0.35 goes to
a digest spoken once every `JARVIS_NOTIFY_DIGEST_MIN` minutes. Urgent messages, reminders, battery
and meeting notices, and anything with `bypass_busy_gate` are never batched. Table
`notification_stats`; Toolbox shows the counts and has a reset.

Residual risks (Phase C): a `mail_match` agent acts on third-party mail (subjects/senders are
sanitised, the catastrophic gate still applies, but an agent that e.g. writes files with `{subject}`
in the name takes attacker-chosen text); keep agent steps simple. `review_code` sends the file or diff
to the active AI. The digest learns from a weak signal (barge-in) and can batch a kind the user
actually wanted; reset it in the Toolbox.

## Phase D (optional items)

| Item | Status |
|---|---|
| D1 Macro/skill form builder | **Shipped** as the Toolbox > Voice macros form (tool dropdown + JSON input per step). Agents use the same step builder. |
| D2 Wake word | **Not built** (see Later.md): an always-on detector costs CPU all day and adds a model dependency. |
| D3 create_presentation | **Shipped** as `write_file` with a `.pptx` name (`jarvis_pptx.py`, python-pptx already installed): `# Title` per slide, `-` bullets, `Notes:` lines. No new tool. |
| D3 translate / generate_image | **Not built** (see Later.md): the agent already translates in conversation; image generation needs a paid image API and model choice. |
| D4 test helper | **Not built**: "write tests for X" already goes to the coding agent through `delegate_to_claude_code`, on request only. |
| D5 Weekly improvement suggestions | **Shipped**: `jarvis_improvement_report.py`, tool `improvement_report`, Toolbox > Suggestions this week. Plain SQL, no model call, never changes anything. |

**D5 report** looks at the last 7 days: tools failing 2+ times, commands said the same way 3+ times
(macro candidates), announcement kinds cut off more than followed up, failing background agents,
voice replies over 6 s.

## Verification (all phases)

- Tests: `test_feature_batch_a.py` (22), `_b.py` (12), `_c.py` (12), `_d.py` (3); full suite green.
- Toolbox route rendered in headless Chromium at 1440 and 390 px against a seeded temp DB: every panel
  loads, no console errors, no horizontal scroll, the seeded fake secret never appears in the page.
- Live on this PC: WASAPI loopback capture (B1); FTS search and graph sync on a copy of the real DB
  (C4/C5). **Not verified live**: a real meeting end to end, a real Everything install, a real
  mail_match agent against Gmail, app-shortcut keys into a real app, battery thresholds on a laptop.
- Tool prefix grew by 14 tools (~2.5k tokens of the cached prefix); one-time cache re-write per restart.

## Toolbox trimmed (2026-09-28)

At the user's request the App shortcuts, Meeting notes and Email replies panels were removed from the
Toolbox page (HTML + features.js only) because it looked cluttered. The features still work by voice/typed
command and through their agent tools (`app_shortcuts`, `meeting_notes`, `email_reply`); their
`/api/feature/{shortcuts,meetings,email}` routes still exist, just with no panel. App shortcuts still show
first in the Alt+K palette.

## Audit (2026-09-27)

17 bugs found and fixed in this batch; details and the rules they imply are in CLAUDE.md ("Feature batch
audit"), regression tests in `test_feature_batch_audit.py`. Most important: mail-triggered agents crashed
on every check (missing module import); agent placeholders could carry a mail subject into a shell/send
step; fuzzy macro matching could run the opposite command; meeting notes dropped short remarks in quiet
chunks; a critical battery held reminders; every named device was announced after the PC woke up.
