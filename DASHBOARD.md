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
only on Home/Sessions/Tasks/Activity/Audit (`ROUTES_WITH_CONTEXT`) — the routes where clicking
something meaningfully has "more detail" to show — and stays hidden elsewhere so a content-heavy
route like Autonomy or Identity gets the full window width. `showDetail()` also flips the route on
a direct click: clicking a session in the Home "Now" block, for example, jumps to `#/sessions` and
populates the context panel there; see "Post-overhaul UX pass" below for the fuller navigation
write-up (including the `navigate: false` background-update case).

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

## Post-overhaul UX pass (2026-09-22)

Follow-up fixes after real use of the sidebar shell above — still frontend-only except where
noted; `jarvis_dashboard.py`'s Host/Origin guards, localhost bind, and the confirmation gate were
not touched.

**1. New commands open the detail panel automatically.** Every `render()` pass (the 15s
`/api/state` poll, plus any WebSocket-driven `handleLiveEvent`) now re-syncs the followed
session's detail into the panel if one is being followed (`state.followedSessionId`), not just on
the two explicit `session_start`/`session_end` events — so a reply landing between polls still
shows up promptly. Design decision: a **background** update (`navigate: false`) only refreshes the
panel's content and reveals it if the *current* route already has a context panel
(`ROUTES_WITH_CONTEXT`); it never yanks you to a different route just because a new command
started elsewhere. A **direct click** on a session/task (`navigate: true`, the default) still jumps
to the owning route, since a deliberate click means "take me there." On Home, a new voice/text/
dashboard command therefore updates the Sessions panel silently in the background if you're on
Sessions, but doesn't jump you off Home to show it — clicking it from Home's "Now"/"Recent
sessions" cards does navigate, same as before. `handleLiveEvent`'s source filter covers
`voice`/`text`/`dashboard` (not `phone` — nobody's watching a screen for a phone command).

**2. Audit Trail rows open the detail panel.** Clicking (or Enter/Space on a focused) audit row
shows its timestamp/action/summary/payload in the panel, and — since `dashboard_sessions` and
`action_audit` share no session_id column (see the CLAUDE.md graphify entry on this) — an exact
match on the row's `transcript` against the currently-loaded sessions list also loads that
session's own transcript/reply into the same panel when one exists. Every previously click-only
row (Sessions, Tasks, Activity, Audit) got the same `wireRowActivation()` keyboard handling
(Enter/Space), not just Audit.

**3. Sparse full-width routes got denser.** `.usage-cards` (shared by Home/Identity/Sleep/Usage)
switched from `flex-wrap` to a `grid-template-columns: repeat(auto-fill, minmax(180px, 1fr))`
layout so cards stretch to fill a wide row instead of clumping top-left with empty space beside
them. The Usage daily-spend chart grew from 90px to 180px tall; Sleep's three SVG charts grew from
a 130-tall to a 170-tall viewBox (they scale to their container, so this is a real height increase,
not just a number). Usage gained a "Tokens & cache savings by period" grid (input/cache-read/
cache-write/output tokens + $ saved, for today/week/month/all-time) from fields `/api/usage`
already returned but the UI never showed.

**4. Autonomy was restructured for at-a-glance status**, replacing the old flat list of sections.
New top-to-bottom order in `autonomy.js`'s `render()`: the summary strip (now 5 cards + a "Last
activity" line, computed client-side from the same `/api/autonomy` response's `decisions[0]` — no
new backend field, since `jarvis_autonomy.py` has no explicit "last tick" timestamp to expose) →
**Needs you** (the pending-review cards plus up to 8 recent failed decisions, in one place) →
**Running now** (in-flight campaign steps) → Open commitments → Campaigns → Rules → a secondary
"Automation details" group (file organising, skills, tool proposals, dynamic tools — unchanged,
just visually demoted) → the Activity log at the very bottom. Every existing control (suggestions,
commitments, campaigns, rules, log filters, organising roots/rules, skills, dynamic tools) is still
present and still wired to the same endpoints — nothing was removed, only grouped and re-ordered.

**5. Sleep gained two more stat cards** from fields `/api/sleep` already computed but didn't
surface: goal hit rate (`goal_hit_nights / nights_tracked`, as a %) and total sleep hours for the
selected period (`total_hours`). No backend change — both were already in `_period_stats()`'s
return dict.

**6. Home gained three cards**: "Recent sessions" (last 5, clickable → Sessions + detail, same
`showDetail` used everywhere else), "Recent autonomy activity" (last 5 `/api/autonomy` decisions,
via a new light 30s poll — `fetchAutonomySummary()` — kept separate from `autonomy.js`'s own 10s
poll so Home doesn't pull the Autonomy route's full render cost), and "Presence" (face recognition,
via a similarly light `fetchHomePresence()` poll of `/api/faces`; the whole card is hidden with
`hidden` when the feature is off on this machine, since most installs won't have it enabled). Also
added an "Open tasks" card to "Today" (client-side count of `status in (running, queued)`, no new
field). All three reuse existing endpoints — no new backend route.

**Voice fixes (jarvis.py, not dashboard_static)**: two real playback bugs, both in `speak_text()`'s
Deepgram-streaming path (`_speak_streamed`/`_play_pcm_stream`), root-caused rather than papered
over:
- **"breaks/glitches while speaking"**: `sd.OutputStream(...)` had no `latency` hint, so PortAudio
  used its default buffering — a chunk arriving from the network a few milliseconds late (this is a
  live WebSocket, not a local file) starves the output device mid-word, heard as a crackle/dropout.
  Fixed with `latency="high"`, trading a little more time-to-first-audio for not glitching. One-line
  fix; see the comment at `_play_pcm_stream`'s `sd.OutputStream(...)` call.
- **short utterances ("Hi") getting cut off after "One moment."**: `_speak_streamed`'s own
  docstring already explains the tradeoff it makes on a mid-stream WebSocket failure — keep
  whatever already played rather than restart from the top (restarting would double-speak).  That's
  the right call for a long reply, but for a *short* phrase (the filler phrase itself, or a short
  reply like "Hi, how can I help?") it means the whole utterance can be heard as truncated, and a
  short phrase's REST round trip is already fast enough that streaming's time-to-first-audio benefit
  there is smallest right where the truncation risk is most noticeable. Fixed with a new
  `TTS_LIVE_STREAM_MIN_CHARS` (default 40, `JARVIS_TTS_LIVE_STREAM_MIN_CHARS`): text shorter than
  that skips the live WebSocket entirely and goes straight to the REST/cache cascade. The filler
  phrase ("One moment.", 12 chars) and most short greetings now never open a live stream at all.
- **Residual limitation, accepted rather than solved**: a longer reply that hits a genuine
  mid-utterance WebSocket drop *after* already streaming past `TTS_LIVE_STREAM_MIN_CHARS` still
  ends with whatever was spoken before the drop — the alternative (restarting the whole sentence)
  would double-speak, which is worse. This is the same kind of documented tradeoff as the Phase C
  "a connection drop after some sentences already played will repeat the whole reply on retry" note
  in SPEED.md, just for TTS instead of the LLM stream; real network jitter that severe is rare and
  the buffering fix above addresses the far more common (chunk-timing, not connection-loss) cause.
- Tests: `test_play_pcm_stream_asks_portaudio_for_high_latency_buffering` and
  `test_speak_text_short_phrase_skips_live_stream` in `test_deepgram_voice.py` pin both fixes; one
  pre-existing test (`test_speak_text_caches_complete_streamed_audio_for_reuse`) was updated to use
  text long enough to still exercise the streaming path it's testing. Full suite: 733 tests, same 4
  pre-existing unrelated failures (deleted urgent-email-monitor skill files, documented in CLAUDE.md).

**Audit-and-fix pass (2026-09-22, same day)** — adversarial re-read of everything above, three real
bugs found and fixed:
1. *`_fetch_audit` (the Activity route's `/api/state` compact audit list) never selected the
   `transcript` column at all*, only `_fetch_audit_filtered` (the dedicated Audit Trail route) did
   — so clicking an Activity row could never show its "View session →" link even when a real
   session shared its transcript, silently (not a crash, just a feature that never activated on
   that one route). Fixed by adding `transcript` to `_fetch_audit`'s SELECT and output dict —
   read-only, no schema change (the column already existed on `action_audit`). Pinned by
   `test_state_audit_rows_include_transcript_for_session_linking` in `test_dashboard.py`.
2. *`_play_pcm_stream`'s odd-byte-chunk crash* — see SPEED.md's Phase B section for the full
   write-up; a real cause of playback stopping mid-utterance, independent of network health.
3. *Home's "Recent autonomy activity" card mislabeled "not available in this build" as "Autonomy
   is off"* — it checked `lastAutonomy.enabled` without first checking `lastAutonomy.available`
   (the same two fields `autonomy.js`'s own render() checks, in the same order). Fixed to match.
Also audited and confirmed correct, no changes needed: the auto-open/follow logic under rapid
consecutive commands (the newest session always wins `state.followedSessionId`, an older
`session_end` for a since-superseded session is a no-op); no leaked duplicate `setInterval`s or
WebSocket connections on route changes (every interval is set up exactly once, at module load,
not inside `onRouteActivated`); the sentence-pipelining pre-fetch thread still never streams/plays
audio (dedicated test already covers this); the Autonomy restructure still routes every existing
control (Approve/Dismiss/Never, Done/Cancel, Accept, Pause/Resume campaign, Add step, Remove
policy, Add rule, Revoke/Disable skills and dynamic tools, organise rules/roots, tool-proposal
approve/reject) through the exact same handlers, just regrouped into the new sections — none were
dropped or duplicated. Full suite: 736 tests (2 new here, same 4 pre-existing unrelated failures).

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
