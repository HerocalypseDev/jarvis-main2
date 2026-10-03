Example skills. Copy any of these into the `skills/` folder to enable them, and edit freely.

- `morning_briefing.json`: daily 8:00 spoken briefing (weather, mail, calendar, news). Needs the
  Gmail/Calendar MCP servers for those parts.
- `gmail_watch.json`: checks Gmail every hour; only something urgent is said out loud, the rest waits for "what did I miss?".

A skill is `name`, `description`, `instructions` (what Jarvis should do, in plain English) and an
optional `schedule` (`{"daily_at": "HH:MM"}` or `{"every_minutes": N}`).

A scheduled run's reply is not read out by default: it goes to the "what did I miss?" list (and the dashboard
Home card), unless the reply starts with `URGENT:`. Add `"announce": true` to a skill whose scheduled report you
always want to hear (the morning briefing has it).
