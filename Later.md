# Later

## Google Maps location sharing -> "where is <person>?" (2026-09-19)

**Goal:** say "where is <person>" and Jarvis answers using a person's shared location.

Google has no official API for Maps location sharing, so there are three routes.

### 1. Unofficial library (closest to the goal)
- Python package `locationsharinglib` logs in with Google cookies and reads the people who share with you.
- Wrap it in a `where_is(name)` tool returning address, and optionally battery level and last-updated time.
- Downsides:
  - Unofficial, can break whenever Google changes something.
  - Stores a Google session cookie in `.env` (sensitive credential).
  - May violate Google's ToS.
  - Google sometimes forces a re-login.
- Data exposure: their location passes through the active brain (Claude, or Gemini free tier if switched). The people sharing should be told.

### 2. Telegram live location (official, stable)
- Jarvis already has a Telegram channel. The person shares a Live Location with the bot chat (15 min up to 8 h). Jarvis stores the latest coordinates and reverse-geocodes them.
- Downsides: not always-on (they must start a share each time); not Google Maps.

### 3. Dedicated tracker (official, always-on)
- OwnTracks or Home Assistant on their phone posts location to a small endpoint Jarvis reads.
- Reliable and private, but they must install an app.

### Recommendation
Option 1 if staying on Google Maps sharing and accepting fragility; option 3 if it should keep working.
Build read-only, with a name allowlist and no location history stored.

### Before building
Run the project's double-check protocol: map onto existing tables/functions, list new tables/APIs, risk review (security, cost, data exposure, irreversibility, performance), and stop and ask on non-zero risk.
