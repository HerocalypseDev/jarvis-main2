# Graph Report - jarvis-main2  (2026-09-19)

## Corpus Check
- 37 files · ~97,447 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 23 file(s) not represented in the graph (top: .log 21, (none) 1, .css 1)

## Summary
- 1280 nodes · 2509 edges · 64 communities (57 shown, 6 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 126 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `0a418101`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- _memory_db_connect
- _execute_tool_impl
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
- _launch_app
- _mcp_connect_one
- queue_or_deliver_notification
- CLAUDE.md
- app.js
- jarvis_dashboard.py
- jarvis_voice_tone.py
- main
- test_dashboard.py
- Tween
- test_shutdown_via_run_shell_is_staged_not_run
- run_agent_loop
- Path
- build_system_blocks
- _scripted_claude
- handle_text_command
- TTLCache
- Brag Plan: Jarvis
- SqliteKV
- jarvis_task_scheduler.py
- test_billing_failures_are_plain_sentences
- ce
- _FakeProc
- ce
- test_sleep_mail.py
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
- _ensure_mcp_loop
- test_short_notification_is_spoken_unchanged_without_a_claude_call

## God Nodes (most connected - your core abstractions)
1. `_execute_tool_impl()` - 82 edges
2. `_memory_db_connect()` - 35 edges
3. `main()` - 28 edges
4. `run_agent_loop()` - 26 edges
5. `esc()` - 20 edges
6. `handle_text_command()` - 20 edges
7. `_build_app()` - 19 edges
8. `queue_or_deliver_notification()` - 18 edges
9. `_claude_request()` - 17 edges
10. `enable()` - 17 edges

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

## Communities (64 total, 6 thin omitted)

### Community 0 - "_memory_db_connect"
Cohesion: 0.07
Nodes (41): _append_history(), _apply_memory_db_pragmas(), _background_tasks_dir(), cancel_reminder(), _catastrophic_reason(), _count_running_background_tasks(), _create_memory_tables(), notify() (+33 more)

### Community 1 - "_execute_tool_impl"
Cohesion: 0.05
Nodes (59): click_at(), drag_and_drop(), _execute_tool_impl(), focus_window(), _http_request_tool(), Writes name/description/instructions (and optional schedule) as a new…, Strips ANSI/VT100 escape sequences (color codes, cursor movement) that a…, Runs one tool call and returns the text to feed back to Claude as its… (+51 more)

### Community 2 - "brag-output-2026-09-19-001152/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 3 - "jarvis_sleep_mode.py"
Cohesion: 0.05
Nodes (68): _block_distractions(), _cancel_media_autopause(), check_wakeup(), _connect(), _dark_mode_is_on(), _db_path(), disable(), enable() (+60 more)

### Community 4 - "brag-output/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 5 - "FileWatcher"
Cohesion: 0.10
Nodes (14): add_watched_folder(), _connect(), _db_path(), _default_watch_paths(), FileWatcher, get_recent_file_events(), list_watched_folders(), Connection (+6 more)

### Community 6 - "jarvis.py"
Cohesion: 0.07
Nodes (48): _bytes_to_gb(), _bytes_to_mb(), check_system_health(), _choose_input_device(), _craft_system_status_summary(), _default_session_context(), execute_mcp_tool(), _format_uptime() (+40 more)

### Community 8 - "jarvis_memory_enhance.py"
Cohesion: 0.13
Nodes (22): _connect(), _cosine(), _db_path(), link_facts(), list_code_patterns(), list_decisions(), Connection, Path (+14 more)

### Community 9 - "test_gemini.py"
Cohesion: 0.06
Nodes (53): api_key(), call(), convert_messages(), convert_tools(), from_response(), get_provider(), model_name(), Path (+45 more)

### Community 10 - "jarvis_billing.py"
Cohesion: 0.15
Nodes (19): compute_cost(), _dollars(), _ensure_usage_table(), fetch_cost_buckets(), format_local_summary(), get_api_spend(), local_summary(), Connection (+11 more)

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
Cohesion: 0.09
Nodes (5): _kv_db(), Tests for the caching layers (jarvis_cache.py + their wiring in jarvis.py). Run…, test_1h_ttl_rejection_falls_back_to_5m_and_retries(), test_enabled_flag(), test_record_and_local_summary()

### Community 17 - "TTSDiskCache"
Cohesion: 0.29
Nodes (5): Path, WAV files under one directory, keyed by hash. LRU by mtime (touched on every…, TTSDiskCache, test_tts_cache_skips_synthesis_on_repeat(), test_tts_disk_cache_roundtrip_and_eviction()

### Community 18 - "jarvis_proactive.py"
Cohesion: 0.27
Nodes (12): check_project_health(), _connect(), _db_path(), _fmt_findings(), _iter_source_files(), Connection, Path, Proactive problem detection for Jarvis. Scans a file or project directory for… (+4 more)

### Community 19 - "_launch_app"
Cohesion: 0.12
Nodes (17): _chrome_executable(), _cursor_executable(), _cursor_foreground_hwnd_win32(), _cursor_largest_main_hwnd_win32(), _cursor_send_f11_fullscreen_win32(), _focus_existing_cursor_window_win32(), _launch_app(), _launch_app_calculator() (+9 more)

### Community 20 - "_mcp_connect_one"
Cohesion: 0.25
Nodes (7): _mcp_connect_all_async(), _mcp_connect_one(), _mcp_server_supervisor(), _McpServerHandle, One MCP server's connection state. Tool-call requests are dispatched into…, Owns one MCP server's stdio connection for the entire process lifetime. The…, Connects a single MCP server and registers its tools on success. Returns…

### Community 21 - "queue_or_deliver_notification"
Cohesion: 0.08
Nodes (37): _check_background_tasks(), _check_due_reminders(), create_reminder(), _get_active_window_title(), _get_last_skill_run(), _guess_project_from_window_title(), _is_preferred_work_hours(), _parse_due_at() (+29 more)

### Community 22 - "CLAUDE.md"
Cohesion: 0.11
Nodes (17): API spend lookup (2026-09-18), Confirmation gate follow-up (2026-09-18), Cost reporting, Dashboard (supervision UI), Gemini brain option (2026-09-18), Git, graphify, MCP startup (2026-09-18) (+9 more)

### Community 23 - "app.js"
Cohesion: 0.11
Nodes (46): actOnPending(), badge(), connectWs(), coreHeatmap(), esc(), fetchAuditResults(), fetchDailyItems(), fetchLlm() (+38 more)

### Community 24 - "jarvis_dashboard.py"
Cohesion: 0.06
Nodes (38): _build_app(), api_audit(), api_clear_finished_sessions(), api_command(), _sink(), api_llm(), api_set_llm(), api_state() (+30 more)

### Community 25 - "jarvis_voice_tone.py"
Cohesion: 0.32
Nodes (7): analyze_tone(), _lexical_scores(), _prosody(), Basic voice tone/sentiment awareness for Jarvis. Rule-based, deliberately…, Short line to fold into the agent system prompt for this turn; empty string if…, Returns {"tone": category, "confidence": 0..1, "signals": [short strings]}.…, tone_context_line()

### Community 26 - "main"
Cohesion: 0.07
Nodes (28): block_samples(), _dashboard_get_pending(), _dashboard_get_sleep(), _dashboard_get_usage(), _dashboard_kill_background_task(), _keyboard_is_pressed(), main(), _notify_phone() (+20 more)

### Community 27 - "test_dashboard.py"
Cohesion: 0.05
Nodes (13): client(), dashboard(), db_path(), fixture, QA regression suite for jarvis_dashboard.py. Run with: python -m pytest…, test_command_endpoint_invokes_run_command(), test_daily_endpoint_exception_does_not_break(), test_get_pending_exception_does_not_break_state() (+5 more)

### Community 28 - "Tween"
Cohesion: 0.19
Nodes (21): _a(), Ao(), _assertThisInitialized(), cb(), cc(), ga(), gb(), hb() (+13 more)

### Community 30 - "run_agent_loop"
Cohesion: 0.09
Nodes (37): enabled(), is_self_contained(), normalize_text(), Small, local-only cache helpers shared by jarvis.py: an env-flag reader,…, JARVIS_<LAYER>_CACHE env flag, default on. Read on every call so it can be…, Lowercase, punctuation-stripped, whitespace-collapsed — so 'System status?' and…, record(), stable_hash() (+29 more)

### Community 31 - "Path"
Cohesion: 0.11
Nodes (23): _dashboard_get_services_status(), _fmt_gb(), get_large_files_report(), _load_mcp_server_configs(), _mcp_servers_config_path(), _memory_db_path(), _print_large_files_breakdown(), Path (+15 more)

### Community 32 - "build_system_blocks"
Cohesion: 0.10
Nodes (25): build_system_blocks(), build_system_prompt(), _dashboard_get_daily_items(), _fetch_projects(), get_active_facts_context(), get_projects_context(), get_skills_context(), get_user_profile_context() (+17 more)

### Community 33 - "_scripted_claude"
Cohesion: 0.22
Nodes (8): Fake Claude: with a tool_name, the first call requests it and the next returns…, _scripted_claude(), fake(), test_reply_cache_disabled_by_env(), test_reply_cache_never_stores_mutating_turns(), test_reply_cache_serves_readonly_repeat_without_claude(), test_reply_cache_skips_context_dependent_and_toolless_turns(), test_summary_cache_skips_second_claude_call()

### Community 34 - "handle_text_command"
Cohesion: 0.10
Nodes (24): _collapse_paths_for_speech(), _dashboard_approve_pending(), _sink(), _dashboard_reject_pending(), _execute_confirmed_action(), flush_pending_notifications(), handle_text_command(), _humanize_path_for_speech() (+16 more)

### Community 36 - "Brag Plan: Jarvis"
Cohesion: 0.10
Nodes (19): Audio direction, Brag Plan: Jarvis, Duration: ~21 seconds, Format: landscape — 1920x1080, Hook (first 3.3 seconds), Key moments (the middle), Outro / punchline, Scene 1 — Hook — 3.3s (+11 more)

### Community 37 - "SqliteKV"
Cohesion: 0.36
Nodes (4): Connection, key -> text value with a created_at timestamp; max_age_s is checked on read,…, SqliteKV, test_sqlite_kv_max_age_and_prune()

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
Cohesion: 0.05
Nodes (72): _body_of(), _classify_critical(), _connect(), _db_path(), _emails(), _env_set(), _handle_family(), _send() (+64 more)

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

### Community 53 - "_claude_request"
Cohesion: 0.10
Nodes (24): _build_sleep_digest(), _claude_request(), _claude_text(), _duckduckgo_search(), _fish_audio_synthesize(), _has_cache_ttl(), Request, urlopen(timeout=...) is supposed to bound the whole call, but a wedged TLS… (+16 more)

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

### Community 65 - "_ensure_mcp_loop"
Cohesion: 0.50
Nodes (3): AbstractEventLoop, _ensure_mcp_loop(), MCP's client SDK is asyncio-only; Jarvis is thread-based throughout. This runs…

## Knowledge Gaps
- **59 isolated node(s):** `state`, `servicesPanel`, `servicesToggleBtn`, `Git`, `graphify` (+54 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 445 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_execute_tool_impl()` connect `_execute_tool_impl` to `_memory_db_connect`, `handle_text_command`, `jarvis_sleep_mode.py`, `FileWatcher`, `jarvis.py`, `jarvis_task_scheduler.py`, `jarvis_memory_enhance.py`, `test_gemini.py`, `jarvis_billing.py`, `jarvis_workflow.py`, `jarvis_proactive.py`, `_launch_app`, `queue_or_deliver_notification`, `_claude_request`, `run_agent_loop`, `Path`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `_execute_tool_impl()` (e.g. with `_memory_db_connect()` and `speak_text()`) actually correct?**
  _`_execute_tool_impl()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `_memory_db_connect()` (e.g. with `_dashboard_get_usage()` and `_execute_tool_impl()`) actually correct?**
  _`_memory_db_connect()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `main()` (e.g. with `_dashboard_approve_pending()` and `_dashboard_get_daily_items()`) actually correct?**
  _`main()` has 15 INFERRED edges - model-reasoned connections that need verification._
- **What connects `state`, `servicesPanel`, `servicesToggleBtn` to the rest of the system?**
  _59 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `_memory_db_connect` be split into smaller, more focused modules?**
  _Cohesion score 0.06829268292682927 - nodes in this community are weakly interconnected._
- **Should `_execute_tool_impl` be split into smaller, more focused modules?**
  _Cohesion score 0.05472636815920398 - nodes in this community are weakly interconnected._