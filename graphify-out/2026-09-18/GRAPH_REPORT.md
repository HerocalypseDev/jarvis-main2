# Graph Report - jarvis-main2  (2026-09-18)

## Corpus Check
- 26 files · ~63,226 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 7 file(s) not represented in the graph (top: .log 5, (none) 1, .css 1)

## Summary
- 785 nodes · 1514 edges · 43 communities (39 shown, 4 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 71 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ef68ac6f`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- _memory_db_connect
- _execute_tool_impl
- handle_text_command
- jarvis_sleep_mode.py
- jarvis_dashboard.py
- FileWatcher
- jarvis.py
- queue_or_deliver_notification
- jarvis_memory_enhance.py
- _claude_request
- jarvis_billing.py
- jarvis_tech_understanding.py
- build_system_blocks
- Jarvis desktop voice assistant
- discord_selfbot_server.py
- get_system_status_report
- test_cache.py
- TTSDiskCache
- jarvis_proactive.py
- open_cursor_window
- _prompt_cache_warm_request
- handle_voice_command
- CLAUDE.md
- app.js
- _build_app
- jarvis_voice_tone.py
- main
- test_dashboard.py
- notify
- _notify_phone
- run_agent_loop
- _load_skills
- _ensure_mcp_loop
- _scripted_claude
- _mcp_connect_one
- TTLCache
- _DuckDuckGoResultParser
- _urlopen_hard_timeout
- _ConnectionManager
- test_billing_failures_are_plain_sentences
- _set_broadcast
- jarvis
- test_record_usage_never_raises

## God Nodes (most connected - your core abstractions)
1. `_execute_tool_impl()` - 81 edges
2. `_memory_db_connect()` - 35 edges
3. `main()` - 25 edges
4. `run_agent_loop()` - 23 edges
5. `handle_text_command()` - 20 edges
6. `speak_text()` - 18 edges
7. `esc()` - 17 edges
8. `queue_or_deliver_notification()` - 16 edges
9. `_build_app()` - 16 edges
10. `FileWatcher` - 15 edges

## Surprising Connections (you probably didn't know these)
- `_execute_tool_impl()` --calls--> `format_local_summary()`  [EXTRACTED]
  jarvis.py → jarvis_billing.py
- `_execute_tool_impl()` --calls--> `add_watched_folder()`  [EXTRACTED]
  jarvis.py → jarvis_filewatcher.py
- `_execute_tool_impl()` --calls--> `get_recent_file_events()`  [EXTRACTED]
  jarvis.py → jarvis_filewatcher.py
- `_execute_tool_impl()` --calls--> `list_watched_folders()`  [EXTRACTED]
  jarvis.py → jarvis_filewatcher.py
- `_execute_tool_impl()` --calls--> `remove_watched_folder()`  [EXTRACTED]
  jarvis.py → jarvis_filewatcher.py

## Import Cycles
- None detected.

## Communities (43 total, 4 thin omitted)

### Community 0 - "_memory_db_connect"
Cohesion: 0.05
Nodes (54): _append_history(), _apply_memory_db_pragmas(), _background_tasks_dir(), cancel_reminder(), _catastrophic_reason(), _check_background_tasks(), _count_running_background_tasks(), _create_memory_tables() (+46 more)

### Community 1 - "_execute_tool_impl"
Cohesion: 0.09
Nodes (45): click_at(), drag_and_drop(), _execute_tool_impl(), focus_window(), _http_request_tool(), list_background_tasks(), list_reminders(), quick_recall() (+37 more)

### Community 2 - "handle_text_command"
Cohesion: 0.18
Nodes (8): _collapse_paths_for_speech(), handle_text_command(), _humanize_path_for_speech(), _is_confirmation_yes(), Replaces any full file path in `text` with just its containing folder's name —…, Runs one already-transcribed command (typed or spoken) through the confirmation…, Small always-on-top Tkinter input box: Enter submits and runs the typed text…, _show_text_command_popup()

### Community 3 - "jarvis_sleep_mode.py"
Cohesion: 0.11
Nodes (34): _block_distractions(), _cancel_media_autopause(), check_wakeup(), _connect(), _dark_mode_is_on(), _db_path(), disable(), enable() (+26 more)

### Community 4 - "jarvis_dashboard.py"
Cohesion: 0.23
Nodes (17): api_audit(), _build_state(), _connect(), _db_path(), end_session(), _fetch_audit(), _fetch_audit_filtered(), _fetch_counts() (+9 more)

### Community 5 - "FileWatcher"
Cohesion: 0.10
Nodes (14): add_watched_folder(), _connect(), _db_path(), _default_watch_paths(), FileWatcher, get_recent_file_events(), list_watched_folders(), Connection (+6 more)

### Community 6 - "jarvis.py"
Cohesion: 0.13
Nodes (26): _chrome_executable(), _default_session_context(), _get_piper_voice(), _launch_app(), _launch_app_calculator(), _launch_app_chrome(), _launch_app_explorer(), _launch_app_notepad() (+18 more)

### Community 7 - "queue_or_deliver_notification"
Cohesion: 0.06
Nodes (54): _check_due_reminders(), create_reminder(), _get_active_window_title(), _get_idle_seconds(), _get_last_skill_run(), _guess_project_from_window_title(), _is_preferred_work_hours(), _parse_due_at() (+46 more)

### Community 8 - "jarvis_memory_enhance.py"
Cohesion: 0.13
Nodes (22): _connect(), _cosine(), _db_path(), link_facts(), list_code_patterns(), list_decisions(), Connection, Path (+14 more)

### Community 9 - "_claude_request"
Cohesion: 0.19
Nodes (15): _claude_request(), _claude_text(), _duckduckgo_search(), _has_cache_ttl(), Logs this response's token usage + estimated cost to the api_usage table…, Returns (spoken_reply, code_to_type_or_empty). The fix-typing half only fires…, Returns (spoken_explanation, refactored_code_or_empty)., _read_clipboard() (+7 more)

### Community 10 - "jarvis_billing.py"
Cohesion: 0.14
Nodes (20): compute_cost(), _dollars(), _ensure_usage_table(), fetch_cost_buckets(), format_local_summary(), get_api_spend(), local_summary(), Connection (+12 more)

### Community 11 - "jarvis_tech_understanding.py"
Cohesion: 0.13
Nodes (14): analyze_python_file(), build_import_graph(), format_analysis_report(), format_error_report(), _imports_of(), _module_name_for(), parse_error(), Path (+6 more)

### Community 12 - "build_system_blocks"
Cohesion: 0.08
Nodes (36): build_system_blocks(), build_system_prompt(), _fetch_projects(), get_active_facts_context(), get_projects_context(), get_skills_context(), get_user_profile_context(), _long_cache_control() (+28 more)

### Community 13 - "Jarvis desktop voice assistant"
Cohesion: 0.11
Nodes (18): Available tools, Background tasks: delegating real coding work and research (`delegate_to_claude_code`, `delegate_research`), Discord — a self-bot, not a normal integration (real ban risk), Environment variables, ⚠️ Full system access, by design, Integrations, Jarvis desktop voice assistant, Optional (+10 more)

### Community 14 - "discord_selfbot_server.py"
Cohesion: 0.16
Nodes (15): find_dm_with_user(), list_dm_channels(), list_servers(), on_ready(), Custom MCP server wrapping discord.py-self to let Jarvis act as the user's own…, Lists the Discord servers (guilds) this account is a member of, with their IDs., Lists currently open DM conversations, with their channel IDs., Finds a DM channel ID by matching a username against currently open DM… (+7 more)

### Community 15 - "get_system_status_report"
Cohesion: 0.13
Nodes (15): _bytes_to_gb(), _bytes_to_mb(), check_system_health(), _craft_system_status_summary(), _format_uptime(), get_system_status_report(), _health_monitor_loop(), _log_proactive_suggestion() (+7 more)

### Community 16 - "test_cache.py"
Cohesion: 0.14
Nodes (5): _kv_db(), Tests for the caching layers (jarvis_cache.py + their wiring in jarvis.py). Run…, test_1h_ttl_rejection_falls_back_to_5m_and_retries(), test_billing_summary_and_pagination(), test_record_and_local_summary()

### Community 17 - "TTSDiskCache"
Cohesion: 0.29
Nodes (5): Path, WAV files under one directory, keyed by hash. LRU by mtime (touched on every…, TTSDiskCache, test_tts_cache_skips_synthesis_on_repeat(), test_tts_disk_cache_roundtrip_and_eviction()

### Community 18 - "jarvis_proactive.py"
Cohesion: 0.27
Nodes (12): check_project_health(), _connect(), _db_path(), _fmt_findings(), _iter_source_files(), Connection, Path, Proactive problem detection for Jarvis. Scans a file or project directory for… (+4 more)

### Community 19 - "open_cursor_window"
Cohesion: 0.24
Nodes (9): _cursor_executable(), _cursor_foreground_hwnd_win32(), _cursor_largest_main_hwnd_win32(), _cursor_send_f11_fullscreen_win32(), _focus_existing_cursor_window_win32(), open_cursor_window(), Largest top-level Cursor.exe window (visible or minimized)., F11 toggles Zen/fullscreen in Cursor (Electron). (+1 more)

### Community 20 - "_prompt_cache_warm_request"
Cohesion: 0.14
Nodes (15): _dashboard_get_services_status(), ensure_mcp_started(), get_mcp_tool_schemas(), _load_mcp_server_configs(), _mcp_servers_config_path(), _preload_mcp_async(), _prompt_cache_keepwarm_loop(), _prompt_cache_warm_request() (+7 more)

### Community 21 - "handle_voice_command"
Cohesion: 0.24
Nodes (11): _choose_input_device(), _get_whisper_model(), handle_voice_command(), _input_devices(), _preload_whisper_async(), _probe_input_max_rms(), _resample_to_16k(), _resolve_input_device_index() (+3 more)

### Community 22 - "CLAUDE.md"
Cohesion: 0.17
Nodes (11): API spend lookup (2026-09-18), Cost reporting, Dashboard (supervision UI), Git, graphify, MCP startup (2026-09-18), Prompt caching (2026-09-18), Reliability fixes from real usage (2026-09-18) (+3 more)

### Community 23 - "app.js"
Cohesion: 0.13
Nodes (38): actOnPending(), badge(), connectWs(), coreHeatmap(), esc(), fetchAuditResults(), fetchDailyItems(), fetchState() (+30 more)

### Community 24 - "_build_app"
Cohesion: 0.15
Nodes (6): _build_app(), api_clear_finished_sessions(), api_state(), clear_finished_sessions(), Deletes every session that isn't currently 'active' — the dashboard's "Clear…, Builds the FastAPI app (import-guarded, testable without binding a socket).…

### Community 25 - "jarvis_voice_tone.py"
Cohesion: 0.32
Nodes (7): analyze_tone(), _lexical_scores(), _prosody(), Basic voice tone/sentiment awareness for Jarvis. Rule-based, deliberately…, Short line to fold into the agent system prompt for this turn; empty string if…, Returns {"tone": category, "confidence": 0..1, "signals": [short strings]}.…, tone_context_line()

### Community 26 - "main"
Cohesion: 0.18
Nodes (12): block_samples(), _dashboard_get_pending(), _dashboard_kill_background_task(), _keyboard_is_pressed(), main(), Read-only snapshot of _pending_action for the dashboard's top approval bar., Called once at startup, before the scheduler starts. A row still 'running' from…, Phase 2 Stop button. Only ever kills a process Jarvis itself spawned via… (+4 more)

### Community 27 - "test_dashboard.py"
Cohesion: 0.06
Nodes (12): client(), dashboard(), db_path(), fixture, QA regression suite for jarvis_dashboard.py. Run with: python -m pytest…, test_command_endpoint_invokes_run_command(), test_daily_endpoint_exception_does_not_break(), test_get_pending_exception_does_not_break_state() (+4 more)

### Community 28 - "notify"
Cohesion: 0.20
Nodes (10): api_command(), _sink(), notify(), Blocking call — run this in its own daemon thread from jarvis.py's main().…, _dashboard_reject_pending(), start(), _metrics_loop(), _queue_pending_confirmation() (+2 more)

### Community 29 - "_notify_phone"
Cohesion: 0.20
Nodes (10): _notify_phone(), _ntfy_listen_loop(), _ntfy_publish(), Best-effort push via ntfy's JSON publish endpoint (not the raw-body+headers…, Best-effort push via Telegram's sendMessage. Never raises., Pushes to every configured phone channel — but only when…, Long-polls a *separate* {NTFY_TOPIC}-cmd topic (never the outbound one, so…, Long-polls Telegram's getUpdates and runs each message through… (+2 more)

### Community 30 - "run_agent_loop"
Cohesion: 0.07
Nodes (42): enabled(), is_self_contained(), normalize_text(), Connection, Small, local-only cache helpers shared by jarvis.py: an env-flag reader,…, key -> text value with a created_at timestamp; max_age_s is checked on read,…, JARVIS_<LAYER>_CACHE env flag, default on. Read on every call so it can be…, Lowercase, punctuation-stripped, whitespace-collapsed — so 'System status?' and… (+34 more)

### Community 31 - "_load_skills"
Cohesion: 0.25
Nodes (9): _dashboard_get_daily_items(), _load_skills(), Skills from disk, re-parsed only when a skills/*.json file was added, removed…, Reads every *.json skill file from the skills directory. A malformed file is…, Writes name/description/instructions (and optional schedule) as a new…, Read-only snapshot for the dashboard's own Daily section (recurring skills +…, _read_skills_from_disk(), save_skill() (+1 more)

### Community 32 - "_ensure_mcp_loop"
Cohesion: 0.29
Nodes (6): AbstractEventLoop, _ensure_mcp_loop(), execute_mcp_tool(), _mcp_call_tool_async(), _mcp_run_coro(), MCP's client SDK is asyncio-only; Jarvis is thread-based throughout. This runs…

### Community 33 - "_scripted_claude"
Cohesion: 0.22
Nodes (8): Fake Claude: with a tool_name, the first call requests it and the next returns…, _scripted_claude(), fake(), test_reply_cache_disabled_by_env(), test_reply_cache_never_stores_mutating_turns(), test_reply_cache_serves_readonly_repeat_without_claude(), test_reply_cache_skips_context_dependent_and_toolless_turns(), test_summary_cache_skips_second_claude_call()

### Community 34 - "_mcp_connect_one"
Cohesion: 0.25
Nodes (7): _mcp_connect_all_async(), _mcp_connect_one(), _mcp_server_supervisor(), _McpServerHandle, One MCP server's connection state. Tool-call requests are dispatched into…, Owns one MCP server's stdio connection for the entire process lifetime. The…, Connects a single MCP server and registers its tools on success. Returns…

### Community 37 - "_urlopen_hard_timeout"
Cohesion: 0.33
Nodes (5): _fish_audio_synthesize(), urlopen(timeout=...) is supposed to bound the whole call, but a wedged TLS…, Calls Fish Audio's TTS REST API and returns (pcm_int16_bytes, sample_rate) —…, _urlopen_hard_timeout(), Request

### Community 39 - "test_billing_failures_are_plain_sentences"
Cohesion: 0.40
Nodes (3): test_billing_failures_are_plain_sentences(), test_tts_fallback_audio_not_stored_under_fish_key(), boom()

### Community 40 - "_set_broadcast"
Cohesion: 0.50
Nodes (4): _lifespan(), _do_broadcast(), _set_broadcast(), _broadcast()

### Community 41 - "jarvis"
Cohesion: 0.67
Nodes (3): reset_stats(), jarvis(), fixture

## Knowledge Gaps
- **28 isolated node(s):** `state`, `servicesPanel`, `servicesToggleBtn`, `Git`, `graphify` (+23 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 288 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_execute_tool_impl()` connect `_execute_tool_impl` to `_memory_db_connect`, `_ensure_mcp_loop`, `jarvis_sleep_mode.py`, `FileWatcher`, `jarvis.py`, `queue_or_deliver_notification`, `jarvis_memory_enhance.py`, `_claude_request`, `jarvis_billing.py`, `jarvis_tech_understanding.py`, `build_system_blocks`, `get_system_status_report`, `jarvis_proactive.py`, `notify`, `run_agent_loop`, `_load_skills`?**
  _High betweenness centrality (0.098) - this node is a cross-community bridge._
- **Why does `_build_app()` connect `_build_app` to `_set_broadcast`, `jarvis_dashboard.py`, `notify`, `_ConnectionManager`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `_execute_tool_impl()` (e.g. with `_memory_db_connect()` and `speak_text()`) actually correct?**
  _`_execute_tool_impl()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `_memory_db_connect()` (e.g. with `_dashboard_get_usage()` and `_execute_tool_impl()`) actually correct?**
  _`_memory_db_connect()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `main()` (e.g. with `_dashboard_approve_pending()` and `_dashboard_get_daily_items()`) actually correct?**
  _`main()` has 12 INFERRED edges - model-reasoned connections that need verification._
- **What connects `state`, `servicesPanel`, `servicesToggleBtn` to the rest of the system?**
  _28 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `_memory_db_connect` be split into smaller, more focused modules?**
  _Cohesion score 0.05380852550663871 - nodes in this community are weakly interconnected._