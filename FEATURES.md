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
A command that normalises to a trigger phrase (lower case, punctuation and leading
"jarvis"/"please" removed; >= 0.9 similarity for small transcription slips; max 12 words) runs the
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
