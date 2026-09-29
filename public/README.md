# Jarvis4U

A voice-first desktop assistant for Windows. Hold a key, talk, and Jarvis does things on your PC:
opens apps, answers questions, reads and writes files, runs commands, manages reminders and
timers, checks your mail and calendar, and hands bigger coding jobs to Claude Code in the
background. A local dashboard in your browser shows everything it does.

It runs on your machine, with your own API keys, and keeps its memory in a local SQLite file.
Nothing is shared with anyone except the AI/voice services you choose to configure.

> **Read "Safety" below before running it.** Jarvis has real access to your computer by design.

## What it can do

- **Talk to it:** push-to-talk (default **Right Shift**), a typed-command box (hold **Left Ctrl** 2 s),
  the dashboard's command box, or your phone (ntfy / Telegram).
- **Brains:** Claude (default), Gemini (has a free tier), or a fully local model through Ollama.
  Switch any time from the dashboard's top bar.
- **Voice:** local Whisper speech-to-text and local Piper voice work with no account at all.
  Deepgram and Fish Audio are optional cloud upgrades (faster / nicer voice).
- **Memory:** remembers facts you tell it, learns from its mistakes, and you can view, edit or
  delete everything it knows on the dashboard's Memory page.
- **Daily life:** reminders, named timers, morning briefing, weather, "what's urgent?", sleep mode
  with a wake-up recap, media and volume control, window control.
- **Work:** delegate coding tasks to Claude Code, background research, code search and review,
  Word/PowerPoint output, clipboard history, file search.
- **Dashboard** (`http://127.0.0.1:8765`, this PC only): live sessions, tasks, a full audit trail
  of every action, usage and cost, settings, and the approval screen for dangerous actions.
- **Optional:** autonomy (acts on your mail/messages by itself), face recognition (local only),
  MCP servers (Gmail, Google Calendar, browser automation, GitHub, ...).

## Support Jarvis4U ❤

Jarvis4U is free and open source, and it stays that way. If it saves you time, you can
[**support the project**](https://selar.com/7e2611t04t) (pick any tier), or get **Jarvis4U Pro**.

### Jarvis4U Pro ⭐

[**Get Jarvis4U Pro**](https://selar.com/1954zy6955) for extras on top of the free version: the
**Student pack** (study sessions, exam countdowns, homework tracker, quizzes, revision timetables,
revision notes), the **Developer pack** (repo briefings, error explainer, change review, CI summaries,
Claude Code hand-offs, standups), the **Work pack** (inbox triage with drafts, meeting prep,
follow-ups, weekly updates, focus time, end-of-day wrap-up), **Routines** (say "start my work day",
"deep focus", "leave desk"... and they run instantly), the **Research pack** (sourced research reports,
side-by-side comparisons, weekly topic watch), **Autonomy recipes** (ready-made email watchers for invoices,
job alerts and deadlines that start switched off), five **Pro dashboard themes**, and new packs as they're released.
Nothing in the free version is taken away or locked.

After buying you get a download (the Pro pack) and a license key by email:
1. Unzip the Pro pack into a folder called `pro` next to `jarvis.py`.
2. Open the dashboard -> **Settings** -> **Jarvis4U Pro**, paste the key, press **Activate**.

The key is checked on your own PC (no account, no internet needed). Safety rules are identical
in Pro: Pro skills use the same tools, audit trail and confirmation gate as everything else.

## Requirements

- Windows 10 or 11 (it uses Windows APIs for hotkeys, audio, windows and notifications)
- Python 3.11 or newer
- A microphone, and at least one AI key (Anthropic or Gemini), or Ollama for a local model
- Optional: Node.js (for MCP servers), the Claude Code CLI (for coding hand-offs)

## Quick start

```powershell
git clone https://github.com/HerocalypseDev/Jarvis4U.git
cd Jarvis4U
python -m pip install -r requirements.txt
copy .env.example .env
notepad .env        # add at least one API key and your name
python jarvis.py
```

Then hold **Right Shift**, say "what time is it?", and let go. The first run downloads the local
Whisper and Piper models once, so the first answer is slow.

To start it without a console window, and get Desktop shortcuts:
`powershell -ExecutionPolicy Bypass -File install_shortcuts.ps1`

### Your data stays yours

Everything personal lives in files git ignores: `.env` (keys and settings), `jarvis_memory.db`
(memory, history, audit trail), `session_state.json`, `mcp_servers.json`, logs, and caches. A fresh
clone starts with an empty memory. Face data, if you turn that feature on, is encrypted and kept
outside the project folder.

### Optional add-ons

- **Gmail / Calendar / browser / GitHub:** copy `mcp_servers.example.json` to `mcp_servers.json`
  and follow the notes in it.
- **Scheduled routines ("skills"):** see `examples/skills/` and copy the ones you want into `skills/`.
- **Phone control:** set `NTFY_TOPIC` and/or `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` in `.env`.
- **Coding hand-offs:** install the Claude Code CLI and run `claude` then `/login` once.

## Safety

Jarvis is powerful on purpose. Please understand this before using it:

- It can run shell commands and Python, read and write files, and control apps **without asking**.
  A misheard command, or text planted in an email or web page it reads, can make it do something
  you didn't want. Use it on your own PC with your own account, not on shared or work machines.
- A small set of **catastrophic actions** (shutdown/restart, formatting a disk, wiping a drive or
  your user folder) is always held for an explicit "yes" or the dashboard's Review, then Approve.
  This is a text tripwire, not a sandbox.
- **Autonomy is off by default** in this repo. When on, it acts on your mail and messages without
  asking. Read [AUTONOMY.md](AUTONOMY.md) and try dry-run first.
- The dashboard only listens on `127.0.0.1` and has no login. Never expose it to the network.
- With a cloud brain or cloud voice turned on, what you say and what Jarvis reads (emails, screen
  text, files) is sent to that provider. Gemini's free tier may use it to improve Google products.
- Your phone topic/bot token is effectively a password for your PC. Keep it secret.

## Documentation

| File | What's in it |
|---|---|
| [DASHBOARD.md](DASHBOARD.md) | The dashboard: routes, approval flow, visual system |
| [AUTONOMY.md](AUTONOMY.md) | Autonomy: what it does, permission model, how to verify it safely |
| [FEATURES.md](FEATURES.md) | Clipboard, macros, background agents, meeting notes, file index, ... |
| [SMARTER.md](SMARTER.md) | Tool narrowing, lessons memory, embeddings, evals, local brain |
| [SPEED.md](SPEED.md) | The Deepgram voice pipeline and latency tuning |

Settings: every option is in `.env` and on the dashboard's Settings page.

## Tests

```powershell
python -m pytest -q
```

Tests use a temporary database and never touch your real memory. Some face-recognition tests need
the Windows camera stack and are skipped or fail elsewhere.

## License

MIT, see [LICENSE](LICENSE). No warranty: you run it at your own risk.
