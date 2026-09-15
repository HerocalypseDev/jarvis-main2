# Desktop clap → Jarvis-style assistant

Python script that listens to your default microphone for two clap patterns:

- **2 claps (double clap) → serious mode**: a different greeting, then an immediate live weather + time report for Ganmo, Ilorin, Kwara State.
- **3 claps (rapid) → normal mode**: "Hey boss, how can I help you today?" and focuses/launches Cursor.

Either pattern activates Jarvis and unlocks **push-to-talk voice commands** (hold a key, speak, release) — until then, push-to-talk is locked, so the first thing the script reacts to is a clap, not a stray command spoken beforehand. **Claps only matter for that initial activation** — once Jarvis is up, it stops listening for clap patterns entirely (so its own TTS playback can never be misheard as a later clap) and mode-switching happens by voice instead: say "switch to serious mode" or "switch to normal mode." Local Whisper transcribes, Claude Haiku decides what to do, **Piper** (local, offline, free — no account, no API key) speaks the reply. See constants at the top of `jarvis.py` for behavior and tuning.

## Setup

From this project directory:

```bash
python -m pip install -r requirements.txt
```

## Environment variables

The script loads a **`.env` file** in the same folder as `jarvis.py` (via `python-dotenv`). You can also set variables in the shell.

### Text-to-speech: Piper (local, free, no key needed)

Spoken output — both clap greetings and voice-command replies — uses [Piper](https://github.com/OHF-Voice/piper1-gpl), a local neural TTS engine. It runs entirely on your CPU: no account, no API key, no internet needed after the one-time voice model download (~60MB, automatic on first use), and it can never bill you or rate-limit you. See `PIPER_VOICE` below to pick a different voice.

### Required (push-to-talk voice commands)

| Variable | Purpose |
| -------- | ------- |
| `ANTHROPIC_API_KEY` | API key from [console.anthropic.com](https://console.anthropic.com) (starts with `sk-ant-`). Used to turn your transcribed speech into actions. |

Without this, holding the push-to-talk key still transcribes locally but no action is taken (a warning is logged).

### Optional

| Variable | Purpose |
| -------- | ------- |
| `PIPER_VOICE` | Piper voice model name (default `en_US-lessac-medium`). Browse options at the [Piper voice samples page](https://rhasspy.github.io/piper-samples/). Downloaded automatically on first use. |
| `PIPER_VOICES_DIR` | Custom folder for downloaded Piper voice models (default: `.cache/piper_voices/` under the project). |
| `JARVIS_WELCOME_CACHE_DIR` | Custom folder for cached welcome WAV (default: `.cache/jarvis_welcome/` under the project). |
| `JARVIS_MEMORY_DB_PATH` | Custom path for the SQLite memory database (default: `jarvis_memory.db` in the project folder). |
| `JARVIS_PTT_KEY` | Push-to-talk key name, per the `keyboard` package (default `left shift`). Hold to record, release to send. |
| `WHISPER_MODEL_SIZE` | Local Whisper model size: `tiny`, `base`, `small`, `medium`, ... (default `base`). Bigger = more accurate, slower, more RAM. Downloaded once on first use. |
| `WHISPER_LANGUAGE` | Language code for transcription (default `en`). Set empty to let Whisper auto-detect (less reliable on short clips). |
| `CLAUDE_MODEL` | Claude model id for command interpretation and screen/search understanding (default `claude-haiku-4-5-20251001`). |
| `JARVIS_INPUT_DEVICE` | Optional mic override: **integer** index or **substring** of the device name. If unset, the script uses the Windows default; when that mic is silent, it auto-picks the loudest working input. List devices: `python -c "import sounddevice as sd; print(sd.query_devices())"`. |

Example `.env`:

```env
ANTHROPIC_API_KEY=your_key_here
```

## Run

```bash
python jarvis.py
```

Allow the microphone if Windows prompts you. Stop with **Ctrl+C**.

## Talking to Jarvis (push-to-talk)

Clap twice (serious mode) or three times rapidly (normal mode) first — push-to-talk is locked until Jarvis is activated by one of those patterns. Then hold **Left Shift** (or your `JARVIS_PTT_KEY`), say a command, then release. On release:

1. **Local Whisper** transcribes what you said (no cloud call, no cost).
2. The transcript goes to **Claude** running a real tool-use loop (`run_agent_loop` in `jarvis.py`): Claude picks a tool, sees the result, and decides what to do next — it can call several tools in a row before replying, up to `MAX_AGENT_ITERATIONS` round trips. This is **not** a fixed menu anymore.
3. Jarvis speaks Claude's final reply back via Piper once the loop finishes.

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
| "switch to serious mode" / "switch to normal mode" | Re-runs that mode's greeting (`switch_mode`) |
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

**Proactive/scheduled skills:** add an optional `"schedule"` to any skill file and Jarvis runs it on its own — no clap, no push-to-talk — and speaks whatever it produces, unprompted:
```json
{ "schedule": { "daily_at": "08:00" } }
```
or
```json
{ "schedule": { "every_minutes": 30 } }
```
A background thread checks every 60 seconds (`SCHEDULER_TICK_S`) for a due skill, runs it through the same agent loop as a voice command (full tool access, memory, other skills), and speaks the result via Piper. Runs are tracked in a `scheduled_skill_runs` table so a `daily_at` skill fires once per day and an `every_minutes` skill respects its interval even across restarts. Ask out loud — "give me a briefing every morning at 8" — and Claude calls `save_skill` with a schedule itself. No skill is scheduled by default; you opt in per skill.

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

**Also connected:** Google Calendar via `@cocal/google-calendar-mcp` (reuses the same `gcp-oauth.keys.json` as Gmail — just enable the Calendar API in the same Google Cloud project and run its own `auth` command once).

### Discord — a self-bot, not a normal integration (real ban risk)

`discord_selfbot_server.py` (in this repo, not a third-party package) lets Jarvis act as your actual Discord account — read your DMs and servers, send messages as you. **This is fundamentally different from every other integration here.** A legitimate Discord integration is a bot: it only sees servers it's invited to, via Discord's official Bot API, no ban risk. Making Jarvis act as *you* means automating your personal account outside that official API (a "self-bot"), which explicitly violates Discord's Terms of Service. Official client libraries (`discord.js` 11.4+, `discord.py`) deliberately dropped support for this specifically to stop it, and Discord has run enforcement waves terminating accounts caught doing it. `discord.py-self` is the unofficial fork that restores it — there's no maintained, ToS-compliant equivalent for "read my own DMs."

This was built anyway at explicit, twice-confirmed user request, the same posture as the WhatsApp Web reading feature in the sibling `jarvis_assistant` project.

**Setup:**
1. Log into discord.com in a browser, open DevTools (F12) → Application → Local Storage → `https://discord.com` → copy the `token` value.
2. Put it in `mcp_servers.json`'s `discord` entry, `env.DISCORD_USER_TOKEN` — **never anywhere else.** Unlike an OAuth token, this is unscoped, unrevocable-without-changing-your-password access to your entire account.
3. That's it — `jarvis.py`'s MCP client launches `discord_selfbot_server.py` itself.

Exposes 5 tools: `list_servers`, `list_dm_channels`, `find_dm_with_user`, `read_messages`, `send_message`. Not self-tested end-to-end for the same reason `delegate_to_claude_code` wasn't — I don't have (and shouldn't ask for) a token to test with. Tool *registration* was verified directly; the actual Discord connection needs a live test from you.

### Delegating real coding work (`delegate_to_claude_code`)

For actual development tasks — not a one-off shell command, but "add a feature," "fix this bug," "run the tests" — Jarvis hands off to a full headless Claude Code agent instead of doing it itself with `run_shell`/`write_file`. It runs `claude -p "<task>" --output-format json --dangerously-skip-permissions` in the target repo (`repo_path`, defaulting to this project's own folder) and speaks back the result. `--dangerously-skip-permissions` is necessary because nothing is present to click "allow" from a voice session; the same catastrophic-command tripwire used for `run_shell`/`run_python` is applied to the task text first, but it can't see what the delegated agent decides to do partway through — accept that as part of the same full-trust posture as everything else in this project, not an oversight.

**This one wasn't self-tested end-to-end** — Claude Code's own safety classifier blocks a running Claude Code session from spawning or even probing another `claude` CLI invocation ("create unsafe agents"), so I couldn't verify the actual subprocess call, its flags, or the JSON output shape (`{"result": "..."}`, per `claude --help`) against a real run. Test it yourself: say something like "delegate to Claude Code: add a docstring to X function" and confirm it actually runs and reports back correctly — if the JSON parsing or flags need adjusting, that'll show up immediately as an error string spoken back instead of a real result.

The first press after starting the script may be slow while the Whisper model finishes loading in the background (it starts loading at startup, and downloads once on first-ever run). Similarly, the very first clap/greeting may pause briefly while the Piper voice model downloads (also one-time, also automatic).

## Tuning

Edit the constants at the top of `jarvis.py`:

| Constant      | Effect                                                            |
| ------------- | ----------------------------------------------------------------- |
| `SPIKE_RATIO` | Increase if you get false triggers; decrease if claps are missed. |
| `COOLDOWN_S`  | Minimum time between two logged claps.                            |
| `BLOCK_MS`    | Larger = slightly less CPU, a bit less precise timing.            |
| `MIN_RMS`     | Floor on how loud a block must be (helps in very quiet rooms).  |
| `SAMPLE_RATE` | Try `48000` if your device does not like `44100`.                 |
| `JARVIS_WELCOME_PHRASE` | What the double clap says. |

## Troubleshooting

- **Wrong or quiet mic:** On startup the script probes your default Windows input. If it is silent, it **auto-selects** the loudest working mic. To force a specific device, set `JARVIS_INPUT_DEVICE` in `.env` (index or name substring from `sounddevice.query_devices()`).
- **PortAudio / audio errors:** Update audio drivers or try another `SAMPLE_RATE`.
- **No reaction to claps:** Lower `SPIKE_RATIO` slightly or speak/clap closer to the mic.
- **Spam logs:** Raise `SPIKE_RATIO` or `COOLDOWN_S`.
- **No welcome speech / TTS errors:** Check the log for a Piper download or load failure — confirm `piper-tts` installed correctly (`pip show piper-tts`) and that `.cache/piper_voices/` has both the `.onnx` and `.onnx.json` files for `PIPER_VOICE`.
- **Push-to-talk key does nothing:** The `keyboard` package's global hook can be blocked by Windows permissions; try running the terminal as Administrator. Also confirm `JARVIS_PTT_KEY` matches a name `keyboard` recognizes (e.g. `f8`, `caps lock`, `right ctrl`).
- **Voice commands transcribe but nothing happens:** Set `ANTHROPIC_API_KEY` in `.env`.
- **First push-to-talk is slow:** The local Whisper model downloads once (~150 MB for `base`) and loads into memory on first use; subsequent presses are fast.
