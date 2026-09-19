# Graph Report - jarvis-main2  (2026-09-19)

## Corpus Check
- 37 files · ~97,276 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 25 file(s) not represented in the graph (top: .log 23, (none) 1, .css 1)

## Summary
- 1280 nodes · 2506 edges · 74 communities (67 shown, 6 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 122 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `337e7141`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- _memory_db_connect
- jarvis_window_control.py
- brag-output-2026-09-19-001152/composition/assets/gsap.min.js
- jarvis_sleep_mode.py
- brag-output/composition/assets/gsap.min.js
- FileWatcher
- jarvis.py
- test_billing_summary_and_pagination
- jarvis_memory_enhance.py
- test_gemini.py
- jarvis_billing.py
- test_record_usage_never_raises
- jarvis_workflow.py
- Jarvis desktop voice assistant
- discord_selfbot_server.py
- Tween
- test_cache.py
- TTSDiskCache
- jarvis_proactive.py
- open_cursor_window
- ensure_mcp_started
- queue_or_deliver_notification
- CLAUDE.md
- app.js
- jarvis_dashboard.py
- jarvis_voice_tone.py
- main
- test_dashboard.py
- Tween
- test_shutdown_via_run_shell_is_staged_not_run
- jarvis_cache.py
- Path
- build_system_blocks
- _scripted_claude
- speak_text
- TTLCache
- Brag Plan: Jarvis
- _summarize_for_speech
- jarvis_task_scheduler.py
- test_billing_failures_are_plain_sentences
- ce
- _FakeProc
- ce
- test_sleep_mail.py
- jarvis_tech_understanding.py
- enabled
- na
- na
- Hyperframes Composition Brief: Jarvis
- user_is_actively_working
- la
- la
- _DuckDuckGoResultParser
- _claude_request
- fb
- he
- Za
- Rd
- fb
- he
- Za
- Rd
- Brag Plan: Jarvis (chaotic cut)
- get_system_status_report
- _execute_tool_impl
- _finish_background_task
- test_short_notification_is_spoken_unchanged_without_a_claude_call
- run_agent_loop
- _load_skills
- timedelta
- _notify_phone
- _urlopen_hard_timeout
- test_1h_ttl_rejection_falls_back_to_5m_and_retries

## God Nodes (most connected - your core abstractions)
1. `_execute_tool_impl()` - 81 edges
2. `_memory_db_connect()` - 35 edges
3. `main()` - 28 edges
4. `run_agent_loop()` - 26 edges
5. `esc()` - 20 edges
6. `handle_text_command()` - 20 edges
7. `enable()` - 20 edges
8. `_build_app()` - 19 edges
9. `queue_or_deliver_notification()` - 18 edges
10. `_claude_request()` - 17 edges

## Surprising Connections (you probably didn't know these)
- `_run()` --indirect_call--> `started_at()`  [INFERRED]
  jarvis.py → jarvis_sleep_mode.py
- `_execute_tool_impl()` --calls--> `format_local_summary()`  [EXTRACTED]
  jarvis.py → jarvis_billing.py
- `_execute_tool_impl()` --calls--> `add_watched_folder()`  [EXTRACTED]
  jarvis.py → jarvis_filewatcher.py
- `_execute_tool_impl()` --calls--> `get_recent_file_events()`  [EXTRACTED]
  jarvis.py → jarvis_filewatcher.py
- `_execute_tool_impl()` --calls--> `list_watched_folders()`  [EXTRACTED]
  jarvis.py → jarvis_filewatcher.py

## Import Cycles
- None detected.

## Communities (74 total, 6 thin omitted)

### Community 0 - "_memory_db_connect"
Cohesion: 0.13
Nodes (19): _apply_memory_db_pragmas(), cancel_reminder(), _count_running_background_tasks(), _create_memory_tables(), _mark_plan_step(), _memory_db_connect(), Connection, WAL mode lets readers proceed while a writer is mid-transaction instead of the… (+11 more)

### Community 1 - "jarvis_window_control.py"
Cohesion: 0.14
Nodes (29): arrange_windows(), _cascade_rects(), close_window(), _connect(), _db_path(), delete_layout(), _find(), _grid_rects() (+21 more)

### Community 2 - "brag-output-2026-09-19-001152/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 3 - "jarvis_sleep_mode.py"
Cohesion: 0.05
Nodes (71): _dashboard_get_sleep(), _cancel_media_autopause(), _connect(), _dark_mode_is_on(), _db_path(), disable(), enable(), _endpoint_volume_call() (+63 more)

### Community 4 - "brag-output/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 5 - "FileWatcher"
Cohesion: 0.10
Nodes (14): add_watched_folder(), _connect(), _db_path(), _default_watch_paths(), FileWatcher, get_recent_file_events(), list_watched_folders(), Connection (+6 more)

### Community 6 - "jarvis.py"
Cohesion: 0.10
Nodes (35): _choose_input_device(), _chrome_executable(), _default_session_context(), _get_piper_voice(), _input_devices(), _launch_app(), _launch_app_calculator(), _launch_app_chrome() (+27 more)

### Community 8 - "jarvis_memory_enhance.py"
Cohesion: 0.13
Nodes (22): _connect(), _cosine(), _db_path(), link_facts(), list_code_patterns(), list_decisions(), Connection, Path (+14 more)

### Community 9 - "test_gemini.py"
Cohesion: 0.06
Nodes (54): api_key(), call(), convert_messages(), convert_tools(), from_response(), get_provider(), model_name(), Path (+46 more)

### Community 10 - "jarvis_billing.py"
Cohesion: 0.14
Nodes (20): compute_cost(), _dollars(), _ensure_usage_table(), fetch_cost_buckets(), format_local_summary(), get_api_spend(), local_summary(), Connection (+12 more)

### Community 12 - "jarvis_workflow.py"
Cohesion: 0.16
Nodes (20): _connect(), _db_path(), detect_stack(), get_context_summary(), get_workflow_status(), git_info(), Connection, Path (+12 more)

### Community 13 - "Jarvis desktop voice assistant"
Cohesion: 0.11
Nodes (18): Available tools, Background tasks: delegating real coding work and research (`delegate_to_claude_code`, `delegate_research`), Discord — a self-bot, not a normal integration (real ban risk), Environment variables, ⚠️ Full system access, by design, Integrations, Jarvis desktop voice assistant, Optional (+10 more)

### Community 14 - "discord_selfbot_server.py"
Cohesion: 0.16
Nodes (15): find_dm_with_user(), list_dm_channels(), list_servers(), on_ready(), Custom MCP server wrapping discord.py-self to let Jarvis act as the user's own…, Lists the Discord servers (guilds) this account is a member of, with their IDs., Lists currently open DM conversations, with their channel IDs., Finds a DM channel ID by matching a username against currently open DM… (+7 more)

### Community 15 - "Tween"
Cohesion: 0.19
Nodes (21): _a(), Ao(), _assertThisInitialized(), cb(), cc(), ga(), gb(), hb() (+13 more)

### Community 16 - "test_cache.py"
Cohesion: 0.10
Nodes (3): _kv_db(), Tests for the caching layers (jarvis_cache.py + their wiring in jarvis.py). Run…, test_record_and_local_summary()

### Community 17 - "TTSDiskCache"
Cohesion: 0.29
Nodes (5): Path, WAV files under one directory, keyed by hash. LRU by mtime (touched on every…, TTSDiskCache, test_tts_cache_skips_synthesis_on_repeat(), test_tts_disk_cache_roundtrip_and_eviction()

### Community 18 - "jarvis_proactive.py"
Cohesion: 0.27
Nodes (12): check_project_health(), _connect(), _db_path(), _fmt_findings(), _iter_source_files(), Connection, Path, Proactive problem detection for Jarvis. Scans a file or project directory for… (+4 more)

### Community 19 - "open_cursor_window"
Cohesion: 0.24
Nodes (9): _cursor_executable(), _cursor_foreground_hwnd_win32(), _cursor_largest_main_hwnd_win32(), _cursor_send_f11_fullscreen_win32(), _focus_existing_cursor_window_win32(), open_cursor_window(), Largest top-level Cursor.exe window (visible or minimized)., F11 toggles Zen/fullscreen in Cursor (Electron). (+1 more)

### Community 20 - "ensure_mcp_started"
Cohesion: 0.10
Nodes (20): AbstractEventLoop, _ensure_mcp_loop(), ensure_mcp_started(), execute_mcp_tool(), get_mcp_tool_schemas(), _mcp_call_tool_async(), _mcp_connect_all_async(), _mcp_connect_one() (+12 more)

### Community 21 - "queue_or_deliver_notification"
Cohesion: 0.07
Nodes (40): _background_tasks_dir(), _check_background_tasks(), _check_due_reminders(), _get_active_window_title(), _get_last_skill_run(), _guess_project_from_window_title(), _is_preferred_work_hours(), _parse_due_at() (+32 more)

### Community 22 - "CLAUDE.md"
Cohesion: 0.11
Nodes (17): API spend lookup (2026-09-18), Confirmation gate follow-up (2026-09-18), Cost reporting, Dashboard (supervision UI), Gemini brain option (2026-09-18), Git, graphify, MCP startup (2026-09-18) (+9 more)

### Community 23 - "app.js"
Cohesion: 0.11
Nodes (46): actOnPending(), badge(), connectWs(), coreHeatmap(), esc(), fetchAuditResults(), fetchDailyItems(), fetchLlm() (+38 more)

### Community 24 - "jarvis_dashboard.py"
Cohesion: 0.06
Nodes (41): _build_app(), api_audit(), api_clear_finished_sessions(), api_command(), _sink(), api_llm(), api_set_llm(), api_state() (+33 more)

### Community 25 - "jarvis_voice_tone.py"
Cohesion: 0.32
Nodes (7): analyze_tone(), _lexical_scores(), _prosody(), Basic voice tone/sentiment awareness for Jarvis. Rule-based, deliberately…, Short line to fold into the agent system prompt for this turn; empty string if…, Returns {"tone": category, "confidence": 0..1, "signals": [short strings]}.…, tone_context_line()

### Community 26 - "main"
Cohesion: 0.08
Nodes (32): block_samples(), _dashboard_approve_pending(), _sink(), _dashboard_get_pending(), _dashboard_reject_pending(), _execute_confirmed_action(), flush_pending_notifications(), _get_whisper_model() (+24 more)

### Community 27 - "test_dashboard.py"
Cohesion: 0.05
Nodes (13): client(), dashboard(), db_path(), fixture, QA regression suite for jarvis_dashboard.py. Run with: python -m pytest…, test_command_endpoint_invokes_run_command(), test_daily_endpoint_exception_does_not_break(), test_get_pending_exception_does_not_break_state() (+5 more)

### Community 28 - "Tween"
Cohesion: 0.19
Nodes (21): _a(), Ao(), _assertThisInitialized(), cb(), cc(), ga(), gb(), hb() (+13 more)

### Community 30 - "jarvis_cache.py"
Cohesion: 0.21
Nodes (10): is_self_contained(), normalize_text(), Small, local-only cache helpers shared by jarvis.py: an env-flag reader,…, Lowercase, punctuation-stripped, whitespace-collapsed — so 'System status?' and…, stable_hash(), _execute_tool(), _log_action_audit(), _looks_failed() (+2 more)

### Community 31 - "Path"
Cohesion: 0.13
Nodes (20): _dashboard_get_services_status(), _fmt_gb(), get_large_files_report(), _load_mcp_server_configs(), _mcp_servers_config_path(), _memory_db_path(), _print_large_files_breakdown(), Path (+12 more)

### Community 32 - "build_system_blocks"
Cohesion: 0.15
Nodes (17): build_system_blocks(), build_system_prompt(), _fetch_projects(), get_active_facts_context(), get_projects_context(), get_skills_context(), get_user_profile_context(), _long_cache_control() (+9 more)

### Community 33 - "_scripted_claude"
Cohesion: 0.22
Nodes (8): Fake Claude: with a tool_name, the first call requests it and the next returns…, _scripted_claude(), fake(), test_reply_cache_disabled_by_env(), test_reply_cache_never_stores_mutating_turns(), test_reply_cache_serves_readonly_repeat_without_claude(), test_reply_cache_skips_context_dependent_and_toolless_turns(), test_summary_cache_skips_second_claude_call()

### Community 34 - "speak_text"
Cohesion: 0.14
Nodes (13): _collapse_paths_for_speech(), _fish_audio_synthesize(), _humanize_path_for_speech(), _play_pcm_bytes(), Replaces any full file path in `text` with just its containing folder's name —…, Registered with jarvis_sleep_mode: when Sleep Mode ends, replaces the old flood…, Calls Fish Audio's TTS REST API and returns (pcm_int16_bytes, sample_rate) —…, Strips markdown and rewrites symbols Piper's phonemizer mangles into garbled… (+5 more)

### Community 36 - "Brag Plan: Jarvis"
Cohesion: 0.10
Nodes (19): Audio direction, Brag Plan: Jarvis, Duration: ~21 seconds, Format: landscape — 1920x1080, Hook (first 3.3 seconds), Key moments (the middle), Outro / punchline, Scene 1 — Hook — 3.3s (+11 more)

### Community 37 - "_summarize_for_speech"
Cohesion: 0.24
Nodes (7): Connection, key -> text value with a created_at timestamp; max_age_s is checked on read,…, SqliteKV, Shortens a reply for Piper to speak — the dashboard still shows `text` in full…, _speech_summary_kv(), _summarize_for_speech(), test_sqlite_kv_max_age_and_prune()

### Community 38 - "jarvis_task_scheduler.py"
Cohesion: 0.19
Nodes (19): cancel_task(), _connect(), _db_path(), _free_slots(), _inflate_estimate(), list_task_queue(), _normalize(), _parse_busy_intervals() (+11 more)

### Community 39 - "test_billing_failures_are_plain_sentences"
Cohesion: 0.40
Nodes (3): test_billing_failures_are_plain_sentences(), test_tts_fallback_audio_not_stored_under_fish_key(), boom()

### Community 40 - "ce"
Cohesion: 0.24
Nodes (14): Ae(), ce(), $d(), ee(), ha(), ka(), le(), me() (+6 more)

### Community 41 - "_FakeProc"
Cohesion: 0.29
Nodes (5): reset_stats(), delegation(), _FakeProc, jarvis(), fixture

### Community 42 - "ce"
Cohesion: 0.24
Nodes (14): Ae(), ce(), $d(), ee(), ha(), ka(), le(), me() (+6 more)

### Community 43 - "test_sleep_mail.py"
Cohesion: 0.06
Nodes (68): _body_of(), _classify_critical(), _connect(), _db_path(), _emails(), _env_set(), _handle_family(), _send() (+60 more)

### Community 44 - "jarvis_tech_understanding.py"
Cohesion: 0.13
Nodes (14): analyze_python_file(), build_import_graph(), format_analysis_report(), format_error_report(), _imports_of(), _module_name_for(), parse_error(), Path (+6 more)

### Community 45 - "enabled"
Cohesion: 0.17
Nodes (16): enabled(), JARVIS_<LAYER>_CACHE env flag, default on. Read on every call so it can be…, record(), _cached_tools(), _log_cache_usage(), _messages_with_cache_breakpoint(), _prompt_cache_keepwarm_loop(), _prompt_cache_warm_request() (+8 more)

### Community 46 - "na"
Cohesion: 0.29
Nodes (6): Aa(), Ca(), na(), Vb(), wb(), Xb()

### Community 47 - "na"
Cohesion: 0.29
Nodes (6): Aa(), Ca(), na(), Vb(), wb(), Xb()

### Community 48 - "Hyperframes Composition Brief: Jarvis"
Cohesion: 0.25
Nodes (7): Audio, Creative Direction, Hyperframes Composition Brief: Jarvis, Objective, Output, Source Material, Visual Identity

### Community 49 - "user_is_actively_working"
Cohesion: 0.50
Nodes (4): _get_idle_seconds(), Seconds since the last system-wide keyboard/mouse input, via GetLastInputInfo.…, True if the user touched the keyboard/mouse within ACTIVE_IDLE_THRESHOLD_S…, user_is_actively_working()

### Community 50 - "la"
Cohesion: 0.53
Nodes (6): Animation(), Da(), la(), ma(), Ua(), Va()

### Community 51 - "la"
Cohesion: 0.53
Nodes (6): Animation(), Da(), la(), ma(), Ua(), Va()

### Community 52 - "_DuckDuckGoResultParser"
Cohesion: 0.29
Nodes (4): HTMLParser, _duckduckgo_search(), _DuckDuckGoResultParser, web_search_and_summarize()

### Community 53 - "_claude_request"
Cohesion: 0.16
Nodes (16): _build_sleep_digest(), _claude_request(), _claude_text(), _has_cache_ttl(), Logs this response's token usage + estimated cost to the api_usage table…, Two-part recap: what mattered first (urgent things that came through live while…, Returns (spoken_reply, code_to_type_or_empty). The fix-typing half only fires…, Returns (spoken_explanation, refactored_code_or_empty). (+8 more)

### Community 54 - "fb"
Cohesion: 0.40
Nodes (5): Context(), Db(), Eb(), fb(), Gw()

### Community 55 - "he"
Cohesion: 0.40
Nodes (5): he(), Md(), Nd(), Od(), Pd()

### Community 56 - "Za"
Cohesion: 0.40
Nodes (5): kb(), ob(), ra(), rb(), Za()

### Community 57 - "Rd"
Cohesion: 0.40
Nodes (5): Rd(), Vd(), Wd(), yd(), ye()

### Community 58 - "fb"
Cohesion: 0.40
Nodes (5): Context(), Db(), Eb(), fb(), Gw()

### Community 59 - "he"
Cohesion: 0.40
Nodes (5): he(), Md(), Nd(), Od(), Pd()

### Community 60 - "Za"
Cohesion: 0.40
Nodes (5): kb(), ob(), ra(), rb(), Za()

### Community 61 - "Rd"
Cohesion: 0.40
Nodes (5): Rd(), Vd(), Wd(), yd(), ye()

### Community 62 - "Brag Plan: Jarvis (chaotic cut)"
Cohesion: 0.50
Nodes (3): Brag Plan: Jarvis (chaotic cut), Revision 2 (user feedback), Revision 2 (user feedback)

### Community 64 - "get_system_status_report"
Cohesion: 0.13
Nodes (15): _bytes_to_gb(), _bytes_to_mb(), check_system_health(), _craft_system_status_summary(), _format_uptime(), get_system_status_report(), _health_monitor_loop(), _log_proactive_suggestion() (+7 more)

### Community 65 - "_execute_tool_impl"
Cohesion: 0.16
Nodes (14): click_at(), drag_and_drop(), _execute_tool_impl(), focus_window(), _http_request_tool(), list_background_tasks(), list_reminders(), quick_recall() (+6 more)

### Community 66 - "_finish_background_task"
Cohesion: 0.18
Nodes (13): _catastrophic_reason(), _dashboard_kill_background_task(), _delegate_research(), _run(), _delegate_to_claude_code(), _finish_background_task(), _insert_background_task(), Short human description if `text` (a shell command or Python snippet) matches… (+5 more)

### Community 68 - "run_agent_loop"
Cohesion: 0.28
Nodes (9): _append_history(), _history_snapshot(), _llm_configured(), _llm_provider(), _llm_unavailable_reply(), Last CONVERSATION_HISTORY_MAX_TURNS messages from memory_turns, oldest first., Permanently records a turn in memory_turns. The table is never trimmed — it's…, Real observe-act-observe loop: Claude picks tools, sees each result, and… (+1 more)

### Community 69 - "_load_skills"
Cohesion: 0.25
Nodes (9): _dashboard_get_daily_items(), _load_skills(), Skills from disk, re-parsed only when a skills/*.json file was added, removed…, Reads every *.json skill file from the skills directory. A malformed file is…, Writes name/description/instructions (and optional schedule) as a new…, Read-only snapshot for the dashboard's own Daily section (recurring skills +…, _read_skills_from_disk(), save_skill() (+1 more)

### Community 70 - "timedelta"
Cohesion: 0.33
Nodes (7): create_reminder(), Schedules a reminder for an absolute time (due_at) or a delay from now…, test_tick_runs_every_30_minutes_only_while_asleep(), tick(), test_tick_speeds_up_to_2_minutes_after_a_message_then_relaxes(), tick(), timedelta

### Community 71 - "_notify_phone"
Cohesion: 0.33
Nodes (6): _notify_phone(), _ntfy_publish(), Best-effort push via ntfy's JSON publish endpoint (not the raw-body+headers…, Best-effort push via Telegram's sendMessage. Never raises., Pushes to every configured phone channel — but only when…, _telegram_send()

### Community 72 - "_urlopen_hard_timeout"
Cohesion: 0.50
Nodes (3): Request, urlopen(timeout=...) is supposed to bound the whole call, but a wedged TLS…, _urlopen_hard_timeout()

## Knowledge Gaps
- **59 isolated node(s):** `state`, `servicesPanel`, `servicesToggleBtn`, `Git`, `graphify` (+54 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 445 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_execute_tool_impl()` connect `_execute_tool_impl` to `_memory_db_connect`, `jarvis_window_control.py`, `jarvis_sleep_mode.py`, `FileWatcher`, `jarvis.py`, `jarvis_memory_enhance.py`, `test_gemini.py`, `jarvis_billing.py`, `jarvis_workflow.py`, `jarvis_proactive.py`, `ensure_mcp_started`, `jarvis_dashboard.py`, `jarvis_cache.py`, `Path`, `speak_text`, `jarvis_task_scheduler.py`, `jarvis_tech_understanding.py`, `_DuckDuckGoResultParser`, `_claude_request`, `get_system_status_report`, `_finish_background_task`, `_load_skills`, `timedelta`?**
  _High betweenness centrality (0.041) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `_execute_tool_impl()` (e.g. with `_memory_db_connect()` and `speak_text()`) actually correct?**
  _`_execute_tool_impl()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `_memory_db_connect()` (e.g. with `_dashboard_get_usage()` and `_execute_tool_impl()`) actually correct?**
  _`_memory_db_connect()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `main()` (e.g. with `_dashboard_approve_pending()` and `_dashboard_get_daily_items()`) actually correct?**
  _`main()` has 15 INFERRED edges - model-reasoned connections that need verification._
- **What connects `state`, `servicesPanel`, `servicesToggleBtn` to the rest of the system?**
  _59 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `_memory_db_connect` be split into smaller, more focused modules?**
  _Cohesion score 0.13450292397660818 - nodes in this community are weakly interconnected._
- **Should `jarvis_window_control.py` be split into smaller, more focused modules?**
  _Cohesion score 0.14022988505747128 - nodes in this community are weakly interconnected._