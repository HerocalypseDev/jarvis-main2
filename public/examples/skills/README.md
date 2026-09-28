Example skills. Copy any of these into the `skills/` folder to enable them, and edit freely.

- `morning_briefing.json`: daily 8:00 spoken briefing (weather, mail, calendar, news). Needs the
  Gmail/Calendar MCP servers for those parts.
- `gmail_watch.json`: checks Gmail every hour and only speaks up when something is important.

A skill is `name`, `description`, `instructions` (what Jarvis should do, in plain English) and an
optional `schedule` (`{"daily_at": "HH:MM"}` or `{"every_minutes": N}`).
