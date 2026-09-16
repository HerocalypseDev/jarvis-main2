# Mobile notification options for Jarvis

Not yet decided which one to build. Three candidates, no new pip dependency needed for any of them — Jarvis already has `http_request`/`run_shell`/`run_python` tools.

1. **ntfy.sh** — free, no account needed. Jarvis POSTs a message to a topic URL you pick (e.g. `https://ntfy.sh/your-topic-name`); you subscribe to that topic in the official ntfy app (iOS/Android) to get push notifications.

2. **Discord webhook** — if you already use Discord on your phone with notifications on. Create a webhook URL from a channel's Integrations settings (no bot, no login token, no ban risk — unlike the existing self-bot). Jarvis POSTs JSON `{"content": "..."}` to that URL.

3. **Telegram bot** — free. One-time setup: create a bot via @BotFather to get a bot token, message the bot once to get your chat ID, then Jarvis calls Telegram's `sendMessage` API to message you directly.

Pick one (or more) later and I'll wire it into `queue_or_deliver_notification`/reminders.
