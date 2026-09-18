## Git

This repo is pushed to https://github.com/HerocalypseDev/jarvis-main2 (private). Push changes
after every phase of work (each meaningful chunk — a feature, a fix, a batch of related
changes), not only when explicitly asked: commit with a clear message and `git push`. Review
`git status`/`git diff` before staging, and never commit anything that looks like a real
credential, token, or PIN (check new files under `skills/` in particular — a skill can contain
things like typed passcodes).

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Dashboard (supervision UI)

- Code: `jarvis_dashboard.py` (FastAPI/WebSocket backend + own `dashboard_sessions` table in
  `jarvis_memory.db`) and `dashboard_static/` (vanilla HTML/CSS/JS frontend). It runs as a
  daemon thread started from `jarvis.py`'s `main()`, in-process — not a sibling process —
  because it needs direct access to in-memory state (`_pending_action`,
  `_RUNNING_BACKGROUND_PROCS`) that is never persisted to SQLite.
- Local-first, localhost-only by default: binds `127.0.0.1:${JARVIS_DASHBOARD_PORT:-8765}`
  only. No auth layer (accepted by the user 2026-09-18: single-user local machine). Never bind
  `0.0.0.0` and never add a tunnel (ngrok/Cloudflare/etc.) without a fresh, explicit
  confirmation in-session — this is a standing rule, not a one-time ask.
- The dashboard must never weaken or duplicate the catastrophic confirmation gate
  (`_CATASTROPHIC_PATTERNS`/`_pending_action` in jarvis.py). Any "Approve" action must call the
  *existing* `_execute_confirmed_action`/`_execute_tool(..., skip_confirmation=True)` path,
  never a reimplementation. The user explicitly accepted (2026-09-18) that the dashboard's
  Approve button may one-click-confirm catastrophic-tier actions (shutdown/format/recursive
  wipe) once that endpoint ships — this is a deliberately reviewed exception to the general
  "no silent bypass" instinct, not an oversight; keep it behind the mandatory detail view the
  original feature spec calls for, not a bare list-row button.
- New dashboard features still require the double-check protocol (map onto existing
  tables/functions, list new tables/APIs, risk review across security/cost/data-exposure/
  irreversibility/performance, stop-and-ask on non-zero risk) before implementation.
- Off by default. Start: set `JARVIS_DASHBOARD_ENABLED=1` before running `python jarvis.py`;
  it opens `http://127.0.0.1:8765` in a browser automatically (`JARVIS_DASHBOARD_AUTO_OPEN=0`
  to disable that). `JARVIS_DASHBOARD_PORT` overrides the port. No desktop shell (Tauri) yet —
  MVP is a plain browser tab; Tauri packaging is deferred until Phases 1-3 are solid.
- Visual style: dark background with cyan/electric-blue glow accents (mood reference only).
  Layout is the functional top-approval-bar + three-column (Sessions/Tasks/Detail) +
  bottom Activity/Victory-log structure — never the circular HUD composition of any reference
  image.
- Status: Phase 1 shipped (Sessions, Tasks, Victory log, read-only pending-action display,
  basic WebSocket live updates). Phase 2 shipped (Approve/Reject wired to
  `_execute_confirmed_action`/`_take_pending_action`, reachable only via the frontend's
  mandatory "Review" detail view; Stop wired to a task's own subprocess via
  `_dashboard_kill_background_task`, which only ever kills processes Jarvis itself spawned).
  System metrics and dashboard-initiated commands are later phases.

### Cost reporting

After every implementation phase, report a block with: model, a one-line summary of the work,
estimated tokens (in/out), estimated cost, and time spent — plus a **running total across all
phases** for both cost and time (not cost alone). Keep the running totals below up to date; add
a new row here each phase rather than only stating the total in chat.

| Phase | Model | Time | Est. cost |
|---|---|---|---|
| 0 (analysis + risk review) | Sonnet 5 | ~5 min | ~$0.20–$0.30 |
| 1 (Sessions/Tasks/Victory log MVP) | Sonnet 5 | ~25 min | ~$0.75–$1.10 |
| 2 (Approve/Reject/Stop) | Sonnet 5 | ~15 min | ~$0.55–$0.75 |
| **Running total** | | **~45 min** | **~$1.50–$2.15** |
