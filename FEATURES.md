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
