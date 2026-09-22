# Dashboard UI/UX overhaul (2026-09-22)

The supervision dashboard moved from a dense three-column + bottom-tabs layout to a
sidebar-navigated, route-based shell. This is a frontend-only reorganization — no backend
route, response shape, or permission model changed. Files touched: `dashboard_static/index.html`,
`style.css`, `app.js`, `autonomy.js`, and one test assertion in `test_dashboard.py` (an old
`id="tab-audit"` string check updated to `id="view-audit"`). `jarvis_dashboard.py` was not
touched at all.

## Layout

```
┌──────────────────────────────────────────────────────────────┐
│ TOP BAR: sidebar toggle · brand · pending confirmations ·    │
│          input mode · brain · $ today · services · live      │
├────────────────────────────────────────────────────────────────┤
│ METRICS STRIP: CPU / RAM / disk / per-core heatmap / uptime   │
├────────────┬─────────────────────────────────┬───────────────┤
│ SIDEBAR    │ MAIN #view (hash-routed)        │ #context      │
│ Home       │  one <section class="view"> is  │ (Home/        │
│ Sessions   │  .active at a time; router in   │  Sessions/    │
│ Tasks      │  app.js toggles it on hashchange│  Tasks only)  │
│ Autonomy   │                                  │  detail-panel │
│ Identity   │                                  │               │
│ Sleep      │                                  │               │
│ Usage      │                                  │               │
│ Activity   │                                  │               │
│ Audit      │                                  │               │
│ Victory    │                                  │               │
│ Daily      │                                  │               │
└────────────┴─────────────────────────────────┴───────────────┘
```

## Routes

Hash-based, one active `<section class="view" id="view-NAME">` at a time (`app.js`'s
`ROUTES`/`renderRoute()`/`onRouteActivated()`):

| Route | Content | Fetched on activation |
|---|---|---|
| `#/home` (default) | Mission control — see below | `renderHome()` (no new fetch — composed from already-fetched `state.data` + `lastUsage`) |
| `#/sessions` | Session list, compose box, Clear finished | (part of the 15s `/api/state` poll) |
| `#/tasks` | Task list, Stop | (part of `/api/state` poll) |
| `#/autonomy` | autonomy.js's whole panel (suggestions, commitments, projects/campaigns, rules, activity log, file organising, skills, dynamic tools) | `window.refreshAutonomy()` → `GET /api/autonomy` |
| `#/identity` | Presence, profiles/consent, pause/away, unknown-visitor pictures, recognition events | `fetchIdentity()` → `GET /api/faces*` |
| `#/sleep` | Week/Month KPIs, charts, wake-up digests | `fetchSleep()` → `GET /api/sleep` |
| `#/usage` | Spend cards, daily chart, per-model breakdown | `fetchUsage()` → `GET /api/usage` |
| `#/activity` | Recent audit (compact) | (part of `/api/state` poll) |
| `#/audit` | Filterable full audit trail | `fetchAuditResults()` → `GET /api/audit` |
| `#/victory` | Completed-task counts + log | (part of `/api/state` poll) |
| `#/daily` | Recurring skills + reminders | `fetchDailyItems()` → `GET /api/daily` |

No `#/` fallback needed beyond the default — any unrecognized hash falls back to `home`
(`currentRoute()`). Sessions and Tasks kept their own full-width list (no more forced 3-column
split); the right-hand **context panel** (`#context`, hosting the existing `#detail-panel`) opens
only on Home/Sessions/Tasks — the routes where clicking something meaningfully has "more detail"
to show — and stays hidden elsewhere so a content-heavy route like Autonomy or Identity gets the
full window width. `showDetail()` (unchanged logic) also flips the route: clicking a session in
the Home "Now" block, for example, jumps to `#/sessions` and populates the context panel there.

## Home (mission control)

Answers "healthy? need me? what just happened?" in one glance, entirely from data other routes
already fetch — **no new backend endpoint was added**, confirmed unnecessary during Phase 0
inventory (`GET /api/state` already returns `pending_action`, `sessions`, `tasks`, `audit`,
`victory_log`, `counts`, and `metrics` in one call; `currentLlm`/`lastUsage` are already cached
from the top-bar chips' own polling).

- **Alerts**: a pending confirmation banner (links to Sessions), RAM ≥ 90%.
- **Health**: CPU/RAM/disk/uptime cards, RAM/CPU/disk styled `usage-card-danger` at ≥ 90%.
- **Needs you**: the pending confirmation (if any) + up to 5 recently failed tasks.
- **Now**: the latest session (click → Sessions + detail) and any currently-running task.
- **Today**: spend today (from the Usage chip's cached data), tasks done today, session count.
- **Send a command**: a second `#api/command` form (same endpoint, same code path, see below),
  so you don't have to leave Home to talk to Jarvis.

`renderHome()` runs on every `/api/state` poll while Home is the active route, plus once on
route activation. Verified against real seeded data in a headless Node harness (no browser
automation tool was available in this session) — confirmed it runs without error and produces
correct output, e.g. the RAM-danger styling and alert banner both fired correctly at 91%.

## Confirmation / approval path — unchanged

`actOnPending()` still calls exactly `POST /api/pending/approve` and `POST /api/pending/reject`,
copied verbatim from the pre-overhaul code. The pending-confirmation banner is still only reached
through the mandatory "Review" detail view (`showPendingDetail()`, unchanged) before Approve is
even clickable — the standing rule from CLAUDE.md's Dashboard section ("Approve may
one-click-confirm even catastrophic-tier actions, on condition it only happens from this detail
view") is untouched. `jarvis_dashboard.py`'s Host/Origin guard middleware, the WebSocket Origin
check, and the localhost-only bind are all in the backend file, which this overhaul never edited.
`test_hardening.py`'s dashboard-guard tests and `test_dashboard.py`'s full suite both pass
unchanged (one assertion updated for the renamed `tab-audit` → `view-audit` id, not a behavior
change).

## Sidebar collapse

Click the &#9776; button at the left of the top bar, or press it again to expand. State persists
per-browser via `localStorage` (`jarvis-sidebar-collapsed`) — a viewer convenience, not shared
state; wrapped in `try/catch` so a private window or blocked storage degrades to "always
expanded" instead of breaking navigation.

## Keyboard

- `/` focuses the nearest command box (Home's or Sessions') unless you're already typing in an
  input/textarea/select.

## What was deliberately not built (Phase 7 polish, scoped down)

- **A sidebar "needs attention" badge** for Autonomy. Would need a periodic background fetch of
  `/api/autonomy` even while that route isn't open, purely to keep a count fresh — the plan
  explicitly marked this optional, and it wasn't worth the extra polling for a first pass.
- **Per-fetch loading spinners.** Every fetch here is against `127.0.0.1` and typically resolves
  in single-digit milliseconds; a loading-state UI for that would be more visual noise than
  signal. The existing pattern (leave the last good render in place until the next successful
  fetch) already avoids layout jump for free.

## How to preview without running full Jarvis

`jarvis_dashboard._build_app(...)` builds the FastAPI app standalone (same helper `test_dashboard.py`
uses) — every callback kwarg is optional and defaults to an empty/"not configured" response, so
you can serve just the static shell against a scratch DB without spinning up voice capture, MCP
servers, or real API keys:

```python
import os
os.environ["JARVIS_MEMORY_DB_PATH"] = "/tmp/preview.db"
import jarvis_dashboard as dashboard
app = dashboard._build_app(port=8766)  # pick a port your real Jarvis (if running) isn't using
import uvicorn
uvicorn.run(app, host="127.0.0.1", port=8766)
```
