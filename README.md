# Jarvis desktop voice assistant

Python script offering **push-to-talk voice commands** (hold a key, speak, release) plus a typed-command hotkey, both running local Whisper transcription and a real Claude tool-use loop against this machine. Local Whisper transcribes, Claude decides what to do, **Fish Audio** (cloud TTS) speaks the reply, with **Piper** (local, offline, free) as an automatic fallback if Fish Audio ever fails. See constants at the top of `jarvis.py` for behavior and tuning.

## Setup

From this project directory:

```bash
python -m pip install -r requirements.txt
```

## Environment variables

The script loads a **`.env` file** in the same folder as `jarvis.py` (via `python-dotenv`). You can also set variables in the shell.

### Text-to-speech: Fish Audio (primary, cloud) with Piper (local, free) as fallback

Spoken output — voice-command replies — uses [Fish Audio](https://fish.audio)'s TTS API as the primary voice when `FISH_AUDIO_API_KEY` is set (the free `s2.1-pro-free` tier is unlimited under fair use). If Fish Audio ever fails for any reason — no key, no internet, rate limited, API error — it automatically falls back to [Piper](https://github.com/OHF-Voice/piper1-gpl), a local neural TTS engine that runs entirely on your CPU with no account/key/internet needed. Leave `FISH_AUDIO_API_KEY` unset to skip Fish Audio entirely and always use Piper.

### Required (push-to-talk voice commands)

| Variable | Purpose |
| -------- | ------- |
| `ANTHROPIC_API_KEY` | API key from [console.anthropic.com](https://console.anthropic.com) (starts with `sk-ant-`). Used to turn your transcribed speech into actions. |

Without this, holding the push-to-talk key still transcribes locally but no action is taken (a warning is logged).

### Optional

| Variable | Purpose |
| -------- | ------- |
| `FISH_AUDIO_API_KEY` | API key from [fish.audio](https://fish.audio) — makes Fish Audio the primary voice. Unset = Piper only. |
| `FISH_AUDIO_VOICE_ID` | A specific voice's `reference_id` from fish.audio (browse/clone voices there). Unset = the model's default voice. |
| `FISH_AUDIO_MODEL` | Fish Audio model id (default `s2.1-pro-free`, the free unlimited tier). Other options: `s1`, `s2-pro`, `s2.1-pro`, `drama-3-preview`. |
| `PIPER_VOICE` | Piper voice model name (default `en_US-lessac-medium`). Browse options at the [Piper voice samples page](https://rhasspy.github.io/piper-samples/). Downloaded automatically on first use. |
| `PIPER_VOICES_DIR` | Custom folder for downloaded Piper voice models (default: `.cache/piper_voices/` under the project). |
| `JARVIS_MEMORY_DB_PATH` | Custom path for the SQLite memory database (default: `jarvis_memory.db` in the project folder). |
| `JARVIS_PTT_KEY` | Push-to-talk key name, per the `keyboard` package (default `right shift`). Hold to record, release to send. |
| `WHISPER_MODEL_SIZE` | Local Whisper model size: `tiny`, `base`, `small`, `medium`, ... (default `base`). Bigger = more accurate, slower, more RAM. Downloaded once on first use. |
| `WHISPER_LANGUAGE` | Language code for transcription (default `en`). Set empty to let Whisper auto-detect (less reliable on short clips). |
| `CLAUDE_MODEL` | Claude model id for command interpretation and screen/search understanding (default `claude-haiku-4-5-20251001`). |
| `JARVIS_INPUT_DEVICE` | Optional mic override: **integer** index or **substring** of the device name. If unset, the script uses the Windows default; when that mic is silent, it auto-picks the loudest working input. List devices: `python -c "import sounddevice as sd; print(sd.query_devices())"`. |

Example `.env`:

```env
ANTHROPIC_API_KEY=your_key_here
```

## Run without VS Code

One-time: `powershell -ExecutionPolicy Bypass -File install_shortcuts.ps1` (add `-Autostart` to also start Jarvis at login; `-RemoveAutostart` undoes it). It puts **Jarvis** and **Stop Jarvis** shortcuts on the Desktop and records which `python.exe` to use in `jarvis_python.txt`. Double-click *Jarvis* to start it hidden (no console window); output goes to `jarvis_standalone.log` (trimmed at 5 MB). *Stop Jarvis* ends it. Only one instance can run at a time, so starting it twice is harmless.

## Run

```bash
python jarvis.py
```

Allow the microphone if Windows prompts you. Stop with **Ctrl+C**.

## Typing to Jarvis (text hotkey)

Don't want to talk out loud? Hold **Left Ctrl** (or your `JARVIS_TEXT_HOTKEY_KEY`) for 2 seconds and a small always-on-top text box pops up. Type your command and press **Enter** — it goes straight into the same Claude tool loop as a voice command (no Whisper, no mic) and Jarvis speaks the reply as usual. Press **Escape**, click away, or close the box to cancel without sending anything.

Unlike push-to-talk, there's no live mic involved, so there's no risk of a stray sound being misread as a command — it works as soon as Jarvis starts.

| Variable | Purpose |
| -------- | ------- |
| `JARVIS_TEXT_HOTKEY_KEY` | Hotkey name, per the `keyboard` package (default `left ctrl`). |
| `JARVIS_TEXT_HOTKEY_HOLD_S` | Seconds to hold before the box appears (default `2.0`). |

Set `JARVIS_TEXT_HOTKEY_ENABLED = False` at the top of `jarvis.py` to disable it.

## Talking to Jarvis (push-to-talk)

Hold **Right Shift** (or your `JARVIS_PTT_KEY`), say a command, then release. On release:

1. **Local Whisper** transcribes what you said (no cloud call, no cost).
2. The transcript goes to **Claude** running a real tool-use loop (`run_agent_loop` in `jarvis.py`): Claude picks a tool, sees the result, and decides what to do next — it can call several tools in a row before replying, up to `MAX_AGENT_ITERATIONS` round trips. This is **not** a fixed menu anymore.
3. Jarvis speaks Claude's final reply back once the loop finishes.

### ⚠️ Full system access, by design

Jarvis has **general-purpose tools with no sandbox**: `run_shell` (PowerShell) and `run_python` (a Python subprocess) can do anything your Windows user account can do, and `read_file`/`write_file`/`http_request` have no path or destination restriction. If a request doesn't match one of the named tools below, Claude reaches for these instead of saying it can't help — that's the point (see "Available tools"). Nearly everything executes **immediately, with no confirmation step** — that's a deliberate choice, made with awareness that local Whisper mishears short clips and that screen/clipboard content read back to Claude isn't guaranteed trustworthy (a manipulated web page or file could in principle plant text that gets fed back into a tool call).

The one thing that still requires a spoken **"yes" on your next push-to-talk press** is a narrow, pattern-matched tier of catastrophic, whole-machine actions: shutting down/restarting/signing out the machine, reformatting/repartitioning a disk, or recursively wiping an entire drive or your whole user profile (see `_CATASTROPHIC_PATTERNS` in `jarvis.py`). This is a text-pattern tripwire over the command Claude wants to run, not a sandbox — it can be evaded by a sufficiently different phrasing of the same command, and it's the *only* safety net in this codebase for that tier. Everything else — individual file deletes, sending WhatsApp messages, clicking, arbitrary shell/Python — fires with zero confirmation.

If a confirmation is pending and you say anything other than a "yes" word, it's silently dropped and your new utterance is treated as a fresh command (it doesn't queue or block).

### Available tools

Named tools (more reliable — Claude prefers these when one fits):

| You say | Jarvis does |
| --- | --- |
| "open github.com" | Opens the URL in your browser (`open_url`) |
| "play some lofi on youtube" | Opens a song/search on Spotify or YouTube (`play_media`) |
| "open cursor" / "open notepad" / "open calculator" / "open explorer" / "open chrome" / "open spotify" | Launches or focuses that app (`open_app`, allowlist in `ALLOWED_APPS`) |
| "lock my computer" / "minimize everything" / "minimize this window" / "turn the volume up/down" / "mute" / "skip this track" / "pause the music" | System-level actions and media keys (`system_action`) |
| "turn on sleep mode" / "turn off sleep mode" / "is sleep mode on?" | Quiets non-urgent notifications, dims to dark mode, lowers volume, and speaks more softly (`sleep_mode`) |
| "play some rain sounds" | Ambient/sleep sounds (`play_ambient_sound`) |
| "guide me through a breathing exercise" | Spoken guided breathing exercise (`guided_breathing_exercise`) |
| "what does this error say" / "summarize this page" / "fix this error" | Screenshot → Claude vision (`read_screen`); if you explicitly ask for a fix, it's typed at your cursor automatically. **The screenshot is sent to Anthropic's API.** |
| "search for X" / "look up X" | DuckDuckGo search, summarized (`web_search`) |
| "type ..." / dictating a message | Types exact text at your cursor via `type_text` — **only types, never presses Enter** |
| "how's the system doing?" | CPU/RAM/disk/battery summary (`system_status`) |
| "what's on my clipboard?" | Reads/explains the clipboard (`read_clipboard`). **Clipboard content is sent to Anthropic's API.** |
| "refactor this code" | Fixes clipboard code, types and copies back the result (`refactor_clipboard_code`) |
| "click at 500, 300" | Mouse click at explicit coordinates (`click_at`) — fires immediately, no confirmation |
| "drag from 100, 100 to 400, 400" | Drag-and-drop (`drag_and_drop`) — fires immediately, no confirmation |
| "scroll down" | Scroll at cursor or explicit coordinates (`scroll_screen`) |
| "focus the notepad window" | Brings a window forward by title substring (`focus_window`) |
| "send a whatsapp message to X saying Y" | WhatsApp Desktop UI automation (`send_whatsapp_message`) — **fires immediately, no confirmation.** See warning below. |
| "find large files" | Recursive, **read-only** disk scan (`scan_large_files`) |

General-purpose tools (the escape hatch for anything not covered above — **full system access, no sandbox, no confirmation except the catastrophic tier above**):

| Tool | Does |
| --- | --- |
| `run_shell` | Runs an arbitrary PowerShell command, returns stdout/stderr/exit code |
| `run_python` | Runs arbitrary Python in a subprocess, returns stdout/stderr/exit code |
| `read_file` | Reads any text file on disk |
| `write_file` | Writes/appends any text file on disk, creating folders as needed |
| `http_request` | Makes an arbitrary HTTP request to any URL |

**A note on `click_at`/`drag_and_drop`:** a click is not reversible or inert — it's the same as you clicking that spot yourself, so it can trigger anything under the cursor (a "Delete" button, a dialog, a link). Use with that in mind, especially with `MIN_RMS`/transcription accuracy in a noisy room.

**A stronger warning on `send_whatsapp_message`:** the riskiest named tool. It uses fixed-coordinate UI automation (`WHATSAPP_SEARCH_POS`/`WHATSAPP_FIRST_RESULT_POS`/`WHATSAPP_MESSAGE_BOX_POS` in `jarvis.py`, calibrated for a maximized window on a 1920x1080 display) to search WhatsApp Desktop's contact list by name and click the *first* search result — there's no way to verify that's actually the contact you meant, and unlike `type_text`, a sent message can't be un-sent. Only use it when you're confident about both the contact name and the exact message.

**Audit log:** every tool call — successful, failed, or staged for confirmation — is recorded to an `action_audit` table in `jarvis_memory.db` (timestamp, transcript, tool name, input, result). Nothing reads it back automatically yet; query it directly with `sqlite3 jarvis_memory.db "select * from action_audit order by id desc limit 20"` if you want to see what Jarvis has actually done.

**Conversation memory:** every exchange is permanently logged to a local SQLite database, `jarvis_memory.db` (in the project folder, gitignored — set `JARVIS_MEMORY_DB_PATH` to move it). Each request sends Claude only the most recent 3 exchanges (6 messages, `CONVERSATION_HISTORY_MAX_TURNS`) for context, but the full history is kept forever and **survives restarts**.

**User profile facts:** the same database has a `user_profile` table (`key`/`value` rows) included in *every* system prompt. Nothing populates this automatically — add facts yourself with `python -c "import jarvis; jarvis.set_user_profile_fact('name', 'Ayo')"`.

**Remembered facts (`remember_fact`/`recall_facts` tools):** unlike `user_profile`, this is automatic and categorized — Claude calls `remember_fact` on its own whenever you state a preference, decision, standing instruction, goal, or relationship worth recalling later ("I prefer dark mode," "my flight is Friday," "always CC my manager"), no "remember that..." phrasing required, though that works too. Facts are stored in a `memory_facts` table (category, optional grouping `key`, content, timestamps) and the current active set (most recent 40, `MAX_ACTIVE_FACTS_IN_PROMPT`) is injected into every system prompt automatically, the same way `user_profile` is. When a new fact is remembered under the same `key` as an earlier one, the old one is marked **superseded**, not deleted or overwritten — so "why did I change my mind about X" stays answerable. Claude can dig into that history (or search by keyword) with `recall_facts`, including superseded facts if asked. This is keyword search (SQL `LIKE`), not semantic/embedding-based search — fine at personal scale, but worth knowing if you ask it to "recall anything related to X" and the wording doesn't overlap.

Inspect it directly any time:
```
sqlite3 jarvis_memory.db "select category, key, content, created_at, superseded_at from memory_facts order by id desc limit 20;"
```

**Skills (`skills/*.json`, `save_skill` tool):** a skill is a named, reusable procedure — a description of *when* to use it plus step-by-step instructions — loaded automatically from every `.json` file in `skills/` and folded into the system prompt on every request (no restart needed to pick up a new one). This is separate from the built-in tools: a skill doesn't add a new capability, it codifies a known-good way of using the tools that already exist, so Claude doesn't have to reason it out from scratch each time (e.g. `skills/free_up_ram.json` — ships with the repo — tells it exactly how to list top RAM consumers and to never kill a process unless the user names it explicitly).

Add a skill by hand (drop a file in `skills/`):
```json
{
  "name": "my_skill",
  "description": "When Jarvis should use this",
  "instructions": "Step-by-step procedure, referencing tools by name where relevant."
}
```
Or just ask out loud — "turn this into a skill for next time" / "remember these steps as your morning briefing" — and Claude calls `save_skill` itself to write the file. A malformed skill file is skipped with a console warning rather than breaking the others. Override the directory with `JARVIS_SKILLS_DIR`.

**Proactive/scheduled skills:** add an optional `"schedule"` to any skill file and Jarvis runs it on its own — no push-to-talk needed — and speaks whatever it produces, unprompted:
```json
{ "schedule": { "daily_at": "08:00" } }
```
or
```json
{ "schedule": { "every_minutes": 30 } }
```
A background thread checks every 60 seconds (`SCHEDULER_TICK_S`) for a due skill, runs it through the same agent loop as a voice command (full tool access, memory, other skills), and speaks the result. Runs are tracked in a `scheduled_skill_runs` table so a `daily_at` skill fires once per day and an `every_minutes` skill respects its interval even across restarts. Ask out loud — "give me a briefing every morning at 8" — and Claude calls `save_skill` with a schedule itself. No skill is scheduled by default; you opt in per skill.

**Notification gate (`session_state.json`):** every proactive message — a scheduled skill's result, a reminder, a system-health suggestion — goes through `queue_or_deliver_notification` instead of speaking immediately. It checks system-wide idle time (`GetLastInputInfo`) against your stated afternoon focus window (`preferred_work_hour_start`/`_end` in `session_state.json`, default 1pm-5pm): if you're actively at the keyboard during that window, non-urgent notices are queued instead of interrupting, and get spoken the next time you actually talk to Jarvis (`flush_pending_notifications`, called at the start of every command). Pass `urgent: true` (e.g. on `create_reminder`) to bypass the gate and speak immediately regardless. State (last active window/project, recent tasks, queued notifications) persists in `session_state.json` in the project folder (gitignored) across restarts.

**Reminders (`create_reminder`/`list_reminders`/`cancel_reminder` tools):** a lighter-weight sibling of skills for a one-off or repeating nudge rather than a full procedure — "remind me in 20 minutes to stretch," "don't let me forget my 3pm call," "don't forget your afternoon work session." Give either an absolute time (`due_at`) or a delay (`due_in_minutes`); add `repeat_every_minutes` for a recurring reminder instead of a one-shot. Stored in a `reminders` table in `jarvis_memory.db`, checked once per scheduler tick (`SCHEDULER_TICK_S`, same 60-second loop as scheduled skills) and delivered through the notification gate above, so a reminder due mid-focus-block waits until you're free instead of interrupting. `list_reminders`/`cancel_reminder` manage what's pending; ask out loud and Claude calls these itself.

**Project tracking + quick recall (`update_project_status`/`quick_recall` tools):** Claude calls `update_project_status(name, status, next_step)` whenever you mention progress or what's next on something you're working on, storing it in a `projects` table in `jarvis_memory.db`. The current set (name, status, next step) is injected into every system prompt automatically, the same way remembered facts are — so a brand-new session already knows what's ongoing. Ask "what were we doing?" / "catch me up" / "where did we leave off?" and `quick_recall` combines tracked projects, recently run commands/skills, the last window you were active in, and any upcoming reminders into one spoken summary, instead of you re-explaining context.

### Workflow, proactive checks, technical understanding, and richer memory

Four modular components (`jarvis_workflow.py`, `jarvis_proactive.py`, `jarvis_tech_understanding.py`, `jarvis_memory_enhance.py`), each self-contained — no import-time dependency on `jarvis.py` internals, own SQLite tables in the same `jarvis_memory.db` file, own logger — wired into the same agent loop as every other tool. None of them poll the screen continuously; each only runs when called (a tool call, or the couple of call sites in `jarvis.py` noted below that touch them opportunistically after real work happens).

**Workflow integration (`get_workflow_status` tool):** tracks the development workspace(s) you actually work in — git branch, uncommitted-file count, ahead/behind upstream, detected stack (Python/Node/Rust/Go/... via marker files like `requirements.txt`/`package.json`) — and logs a "context switch" when the active workspace changes between calls. `delegate_to_claude_code` calls this automatically on its `repo_path` so real coding work always gets recorded; ask directly ("what's the state of this repo?") to pull it on demand. A short summary of the current workspace is injected into every system prompt, the same way projects/facts are.

**Proactive problem detection (`check_project_health` tool):** scans a file or directory for concrete, regex-detectable red flags — bare `except:`, silently-swallowed exceptions, leftover merge-conflict markers, hardcoded API keys/secrets/private keys, `eval`/`exec` on dynamic input, `subprocess(..., shell=True)`, string-built SQL, suspiciously-close nested loops. Findings are fingerprinted and persisted in a `proactive_findings` table so a repeat scan reports what's *new*, what's *still open*, and what's been *resolved* since the last pass, instead of repeating the same list every time.

**Deep technical understanding (`analyze_error`/`analyze_code`/`trace_dependencies` tools):** `analyze_error` classifies a raw error message or traceback (Python, JS/Node, or a bare HTTP status) into an error type, likely cause, and a concrete suggested fix, instead of Jarvis just reading the raw text back to you. `analyze_code` is an AST-based structural pass over a single Python file — functions/classes found, flags for overly-long functions, high branch-complexity, and missing docstrings on public names. `trace_dependencies` builds an import graph across a Python project and, given a target module, reports both what it imports and — just as importantly — what else in the project imports it, so you can see the blast radius before changing or removing something.

**Contextual memory enhancement (`remember_decision`/`remember_code_pattern`/`semantic_recall` tools):** `remember_decision` is a richer sibling of `remember_fact` for choices worth revisiting later — records the decision, the rationale, and the alternatives considered, in a `decision_history` table (`update_decision_outcome`, not yet exposed as a tool, lets you record how it played out). `remember_code_pattern` records a coding convention/style you prefer, taggable by language. `semantic_recall` searches `memory_facts` + `decision_history` + `code_patterns` together using a small pure-Python TF-IDF/cosine-similarity ranking — unlike `recall_facts` (exact SQL `LIKE` keyword matching), it can surface a relevant memory even when the query's wording doesn't literally overlap with how it was originally phrased.

### Integrations

**GitHub works right now, with no setup:** the `gh` CLI, if installed and logged in (`gh auth status`), is reachable via `run_shell` like any other command — Jarvis is told to prefer it for issues/PRs/repos over guessing at a raw API call. If `gh` isn't authenticated on your machine, run `gh auth login` once and it's available.

**Everything else (Gmail, Calendar, Slack, ...) goes through MCP** — the same protocol Claude Code itself uses for integrations. Copy `mcp_servers.example.json` to `mcp_servers.json` (gitignored — it'll hold real tokens) and fill in a server:
```json
{
  "slack": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-slack"],
    "env": { "SLACK_BOT_TOKEN": "xoxb-...", "SLACK_TEAM_ID": "T..." }
  }
}
```
Jarvis connects to every configured server once, lazily, on first voice command after startup, and merges each server's tools into the agent loop as `mcp_<server>_<tool>` — Claude calls them exactly like a built-in tool. **I can't obtain these credentials for you** — Gmail/Calendar need a Google Cloud OAuth app + consent flow, Slack needs a bot token from api.slack.com/apps, GitHub (if you want it via MCP instead of `gh`) needs a personal access token — each service's own MCP server README has the exact steps. A server that fails to connect (bad token, package not found, offline) is skipped with a console warning; it never breaks the rest of Jarvis. Override the config path with `JARVIS_MCP_CONFIG_PATH`.

Requires Node/npx for most published MCP servers (`node --version` to check) and the `mcp` Python package (`pip install mcp`, already in `requirements.txt`).

**Also connected:** Google Calendar via `@cocal/google-calendar-mcp` (reuses the same `gcp-oauth.keys.json` as Gmail — just enable the Calendar API in the same Google Cloud project and run its own `auth` command once); real browser automation via Microsoft's official `@playwright/mcp` (26 tools: navigate, click, type, fill forms, screenshots, page snapshots — no credentials needed, verified live against a real page). Browser snapshots/screenshots land in `.playwright-mcp/` (gitignored).

### Discord — a self-bot, not a normal integration (real ban risk)

`discord_selfbot_server.py` (in this repo, not a third-party package) lets Jarvis act as your actual Discord account — read your DMs and servers, send messages as you. **This is fundamentally different from every other integration here.** A legitimate Discord integration is a bot: it only sees servers it's invited to, via Discord's official Bot API, no ban risk. Making Jarvis act as *you* means automating your personal account outside that official API (a "self-bot"), which explicitly violates Discord's Terms of Service. Official client libraries (`discord.js` 11.4+, `discord.py`) deliberately dropped support for this specifically to stop it, and Discord has run enforcement waves terminating accounts caught doing it. `discord.py-self` is the unofficial fork that restores it — there's no maintained, ToS-compliant equivalent for "read my own DMs."

This was built anyway at explicit, twice-confirmed user request.

**Setup:**
1. Log into discord.com in a browser, open DevTools (F12) → Application → Local Storage → `https://discord.com` → copy the `token` value.
2. Put it in `mcp_servers.json`'s `discord` entry, `env.DISCORD_USER_TOKEN` — **never anywhere else.** Unlike an OAuth token, this is unscoped, unrevocable-without-changing-your-password access to your entire account.
3. That's it — `jarvis.py`'s MCP client launches `discord_selfbot_server.py` itself.

Exposes 5 tools: `list_servers`, `list_dm_channels`, `find_dm_with_user`, `read_messages`, `send_message`. Not self-tested end-to-end for the same reason `delegate_to_claude_code` wasn't — I don't have (and shouldn't ask for) a token to test with. Tool *registration* was verified directly; the actual Discord connection needs a live test from you.

### Phone integration — ntfy.sh and/or a Telegram bot

Two independent, optionally-both-enabled channels, configured entirely via `.env` (both blank = feature is silently off). Either one gets you two things: every proactive notification Jarvis already generates (reminders, `delegate_to_claude_code`/`delegate_research`/`set_plan` completions, health-check suggestions — anything that goes through `queue_or_deliver_notification`) reaches your phone immediately, and you can message back — that message runs through the exact same command pipeline as the text-hotkey box, full tool access, same confirmation gate for the catastrophic-action tier, nothing else held back.

Phone pushes bypass the busy/work-hours queueing gate that the in-room spoken announcement respects — a silent push doesn't interrupt anything the way audio would, so it always fires immediately regardless of whether you look "busy."

**ntfy.sh** — free, no account. `NTFY_TOPIC` in `.env` is really a shared secret on the free public server: anyone who learns the topic name can publish to `<topic>-cmd` and run commands on this machine, so it needs to be long and random, never something guessable, and never committed or shared — treat it like a password. Outbound notifications go to `{NTFY_TOPIC}`; inbound commands are read from a **separate** `{NTFY_TOPIC}-cmd` topic specifically so Jarvis's own outbound pushes can't loop back in and get treated as commands. Subscribe to the base topic name in the ntfy app (iOS/Android) to receive notifications; publish to `<topic>-cmd` from the app to send a command. Verified live against the real service: publish, the JSON stream's `event: message` payload, and the reconnect-on-keepalive-timeout behavior all confirmed working end-to-end.

**Telegram bot** — a bit more setup but a stronger security boundary, since it's authenticated by the bot token rather than a topic name, and only messages from `TELEGRAM_CHAT_ID` are ever accepted (anyone else messaging the bot is logged and dropped). Setup: message `@BotFather` in Telegram, `/newbot`, follow the prompts to get a token; message your new bot once (anything) so it has a chat open with you; then visit `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and read `message.chat.id` from the JSON to get `TELEGRAM_CHAT_ID`. Put both in `.env`. Registered and code-complete but **not live-tested** — I don't have a bot token to test with; the ntfy side's real-API testing gives reasonable confidence the same `urllib`-based request/long-poll pattern is sound, but confirm your own bot actually round-trips before relying on it.

### Background tasks: delegating real coding work and research (`delegate_to_claude_code`, `delegate_research`)

For actual development tasks — not a one-off shell command, but "add a feature," "fix this bug," "run the tests" — Jarvis hands off to a full headless Claude Code agent instead of doing it itself with `run_shell`/`write_file`. It runs `claude -p "<task>" --output-format json --dangerously-skip-permissions` in the target repo (`repo_path`, defaulting to this project's own folder) as a **detached background process** — the tool call returns immediately once the task is *started*, not once it's finished, so Jarvis stays free to take other voice/text commands while it runs. `--dangerously-skip-permissions` is necessary because nothing is present to click "allow" from a voice session; the same catastrophic-command tripwire used for `run_shell`/`run_python` is applied to the task text first, but it can't see what the delegated agent decides to do partway through — accept that as part of the same full-trust posture as everything else in this project, not an oversight.

For a substantial websearch-and-summarize task — "look into X and save a summary to a file" — `delegate_research` does the same thing without shelling out to Claude Code: it runs Jarvis's own tool loop (`run_agent_loop`, the same one voice commands use) on a background thread, has it search and `write_file` its findings, and is cheaper/faster since it skips spinning up a whole Claude Code session.

Both are tracked in a `background_tasks` table in `jarvis_memory.db` and polled/finished from the same 60-second scheduler tick reminders already use (`_check_background_tasks`); either the CLI process exiting (coding tasks) or the background thread finishing (research tasks) triggers a report — a Windows toast plus a spoken summary through the same busy-aware `queue_or_deliver_notification` gate reminders use, so it won't interrupt you mid-focus-block. Ask "what's still running?" (`list_background_tasks`) any time instead of waiting for the notification; `quick_recall` also surfaces anything currently running. Concurrent coding tasks are capped at `MAX_CONCURRENT_BACKGROUND_CODE_TASKS` (2) since each draws on the same shared Claude Pro/Max usage pool as interactive sessions; a coding task still running past `CLAUDE_CODE_TIMEOUT_S` (900s) is killed and reported as timed out. A task still marked "running" after a Jarvis restart (the in-memory process handle doesn't survive one) is marked failed on the next startup rather than silently forgotten.

**This one wasn't self-tested end-to-end** — Claude Code's own safety classifier blocks a running Claude Code session from spawning or even probing another `claude` CLI invocation ("create unsafe agents"), so I couldn't verify the actual subprocess call, its flags, or the JSON output shape (`{"result": "..."}`, per `claude --help`) against a real run. Test it yourself: say something like "delegate to Claude Code: add a docstring to X function" and confirm it actually starts, keeps Jarvis responsive to other commands, and reports back correctly when it finishes — if the JSON parsing or flags need adjusting, that'll show up as an error string in the completion report instead of a real result.

The first press after starting the script may be slow while the Whisper model finishes loading in the background (it starts loading at startup, and downloads once on first-ever run). Similarly, the first TTS reply may pause briefly while the Piper voice model downloads (also one-time, also automatic).

## Full Autonomy (optional, off by default)

Commitment tracking, proactive suggestions with Approve/Dismiss, multi-day campaigns and runtime tool creation. See [AUTONOMY.md](AUTONOMY.md). Turn on by voice ("turn on autonomy") or in the dashboard's Autonomy tab; `JARVIS_AUTONOMY_DISABLED=1` is the hard kill switch.

## Tuning

Edit the constants at the top of `jarvis.py`:

| Constant      | Effect                                                            |
| ------------- | ----------------------------------------------------------------- |
| `BLOCK_MS`    | Larger = slightly less CPU, a bit less precise timing.            |
| `SAMPLE_RATE` | Try `48000` if your device does not like `44100`.                 |

## Troubleshooting

- **Wrong or quiet mic:** On startup the script probes your default Windows input. If it is silent, it **auto-selects** the loudest working mic. To force a specific device, set `JARVIS_INPUT_DEVICE` in `.env` (index or name substring from `sounddevice.query_devices()`).
- **PortAudio / audio errors:** Update audio drivers or try another `SAMPLE_RATE`.
- **No speech / TTS errors:** Check the log for `Fish Audio TTS failed, falling back to Piper` (a Fish Audio problem, but should still speak via Piper) or a Piper download/load failure right after it (both TTS paths down) — confirm `FISH_AUDIO_API_KEY`/`FISH_AUDIO_VOICE_ID` are correct, and for Piper confirm `piper-tts` installed correctly (`pip show piper-tts`) and that `.cache/piper_voices/` has both the `.onnx` and `.onnx.json` files for `PIPER_VOICE`.
- **Push-to-talk key does nothing:** The `keyboard` package's global hook can be blocked by Windows permissions; try running the terminal as Administrator. Also confirm `JARVIS_PTT_KEY` matches a name `keyboard` recognizes (e.g. `f8`, `caps lock`, `right ctrl`).
- **Voice commands transcribe but nothing happens:** Set `ANTHROPIC_API_KEY` in `.env`.
- **First push-to-talk is slow:** The local Whisper model downloads once (~150 MB for `base`) and loads into memory on first use; subsequent presses are fast.
