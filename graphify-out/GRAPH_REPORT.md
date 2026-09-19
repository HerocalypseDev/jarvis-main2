# Graph Report - jarvis-main2  (2026-09-19)

## Corpus Check
- 48 files · ~104,461 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 30 file(s) not represented in the graph (top: .log 27, (none) 1, .vbs 1)

## Summary
- 1420 nodes · 2774 edges · 74 communities (66 shown, 5 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 129 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `18b93757`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- _memory_db_connect
- _execute_tool_impl
- brag-output-2026-09-19-001152/composition/assets/gsap.min.js
- test_sleep.py
- brag-output/composition/assets/gsap.min.js
- FileWatcher
- jarvis.py
- test_billing_summary_and_pagination
- jarvis_memory_enhance.py
- test_gemini.py
- jarvis_billing.py
- test_dev_features.py
- _finish_background_task
- Jarvis desktop voice assistant
- discord_selfbot_server.py
- Tween
- test_cache.py
- TTSDiskCache
- jarvis_proactive.py
- open_cursor_window
- _mcp_connect_one
- queue_or_deliver_notification
- CLAUDE.md
- app.js
- jarvis_dashboard.py
- jarvis_voice_tone.py
- handle_text_command
- test_dashboard.py
- Tween
- download_image
- jarvis_cache.py
- Path
- build_system_blocks
- _scripted_claude
- main
- TTLCache
- Brag Plan: Jarvis
- SqliteKV
- _scheduler_loop
- test_billing_failures_are_plain_sentences
- ce
- _FakeProc
- ce
- test_sleep_mail.py
- test_restart.py
- run_agent_loop
- na
- na
- Hyperframes Composition Brief: Jarvis
- enable
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
- jarvis_sleep_mode.py
- stats_summary
- test_short_notification_is_spoken_unchanged_without_a_claude_call
- is_active
- _set_dark_mode
- _urlopen_hard_timeout
- test_1h_ttl_rejection_falls_back_to_5m_and_retries

## God Nodes (most connected - your core abstractions)
1. `_execute_tool_impl()` - 99 edges
2. `_memory_db_connect()` - 35 edges
3. `main()` - 29 edges
4. `run_agent_loop()` - 26 edges
5. `handle_text_command()` - 21 edges
6. `esc()` - 20 edges
7. `enable()` - 20 edges
8. `queue_or_deliver_notification()` - 19 edges
9. `_build_app()` - 19 edges
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

## Communities (74 total, 5 thin omitted)

### Community 0 - "_memory_db_connect"
Cohesion: 0.10
Nodes (24): _append_history(), _apply_memory_db_pragmas(), cancel_reminder(), _create_memory_tables(), _history_snapshot(), list_background_tasks(), list_reminders(), _mark_plan_step() (+16 more)

### Community 1 - "_execute_tool_impl"
Cohesion: 0.06
Nodes (57): click_at(), drag_and_drop(), _execute_tool_impl(), focus_window(), _http_request_tool(), Strips ANSI/VT100 escape sequences (color codes, cursor movement) that a…, Runs one tool call and returns the text to feed back to Claude as its…, _run_python_code() (+49 more)

### Community 2 - "brag-output-2026-09-19-001152/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 3 - "test_sleep.py"
Cohesion: 0.10
Nodes (14): status(), db(), jarvis(), _log_kind(), fixture, Tests for sleep trend stats and the wake-up digest. Run with: python -m pytest…, A .env setting read at import time (sleep goal) must reach the modules…, test_digest_important_first_then_lighter_note() (+6 more)

### Community 4 - "brag-output/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 5 - "FileWatcher"
Cohesion: 0.10
Nodes (14): add_watched_folder(), _connect(), _db_path(), _default_watch_paths(), FileWatcher, get_recent_file_events(), list_watched_folders(), Connection (+6 more)

### Community 6 - "jarvis.py"
Cohesion: 0.08
Nodes (44): AbstractEventLoop, _choose_input_device(), _chrome_executable(), _default_session_context(), _ensure_mcp_loop(), execute_mcp_tool(), _get_piper_voice(), _get_whisper_model() (+36 more)

### Community 8 - "jarvis_memory_enhance.py"
Cohesion: 0.13
Nodes (22): _connect(), _cosine(), _db_path(), link_facts(), list_code_patterns(), list_decisions(), Connection, Path (+14 more)

### Community 9 - "test_gemini.py"
Cohesion: 0.07
Nodes (48): call(), convert_messages(), convert_tools(), from_response(), get_provider(), Path, Request, Gemini (Google AI Studio) backend for Jarvis's LLM calls. Jarvis's callers all… (+40 more)

### Community 10 - "jarvis_billing.py"
Cohesion: 0.14
Nodes (20): compute_cost(), _dollars(), _ensure_usage_table(), fetch_cost_buckets(), format_local_summary(), get_api_spend(), local_summary(), Connection (+12 more)

### Community 11 - "test_dev_features.py"
Cohesion: 0.06
Nodes (59): analyze_repo(), _existing_tests(), generate_tests(), _public_api(), _py_files(), Path, Repository analysis, unit-test generation and module boilerplate. Deterministic…, New `<name>.py` plus a matching test file, in the style the repo already uses. (+51 more)

### Community 12 - "_finish_background_task"
Cohesion: 0.08
Nodes (38): _background_tasks_dir(), _catastrophic_reason(), _check_background_tasks(), _count_running_background_tasks(), _dashboard_kill_background_task(), _delegate_research(), _run(), _delegate_to_claude_code() (+30 more)

### Community 13 - "Jarvis desktop voice assistant"
Cohesion: 0.10
Nodes (19): Available tools, Background tasks: delegating real coding work and research (`delegate_to_claude_code`, `delegate_research`), Discord — a self-bot, not a normal integration (real ban risk), Environment variables, ⚠️ Full system access, by design, Integrations, Jarvis desktop voice assistant, Optional (+11 more)

### Community 14 - "discord_selfbot_server.py"
Cohesion: 0.16
Nodes (15): find_dm_with_user(), list_dm_channels(), list_servers(), on_ready(), event, Custom MCP server wrapping discord.py-self to let Jarvis act as the user's own…, Lists the Discord servers (guilds) this account is a member of, with their IDs., Lists currently open DM conversations, with their channel IDs. (+7 more)

### Community 15 - "Tween"
Cohesion: 0.19
Nodes (21): _a(), Ao(), _assertThisInitialized(), cb(), cc(), ga(), gb(), hb() (+13 more)

### Community 16 - "test_cache.py"
Cohesion: 0.08
Nodes (7): _gate_env(), _kv_db(), Tests for the caching layers (jarvis_cache.py + their wiring in jarvis.py). Run…, test_busy_gate_holds_ordinary_notification_but_not_reminders(), test_bypass_busy_gate_still_respects_sleep_mode(), test_record_and_local_summary(), test_record_usage_never_raises()

### Community 17 - "TTSDiskCache"
Cohesion: 0.29
Nodes (5): Path, WAV files under one directory, keyed by hash. LRU by mtime (touched on every…, TTSDiskCache, test_tts_cache_skips_synthesis_on_repeat(), test_tts_disk_cache_roundtrip_and_eviction()

### Community 18 - "jarvis_proactive.py"
Cohesion: 0.27
Nodes (12): check_project_health(), _connect(), _db_path(), _fmt_findings(), _iter_source_files(), Connection, Path, Proactive problem detection for Jarvis. Scans a file or project directory for… (+4 more)

### Community 19 - "open_cursor_window"
Cohesion: 0.24
Nodes (9): _cursor_executable(), _cursor_foreground_hwnd_win32(), _cursor_largest_main_hwnd_win32(), _cursor_send_f11_fullscreen_win32(), _focus_existing_cursor_window_win32(), open_cursor_window(), Largest top-level Cursor.exe window (visible or minimized)., F11 toggles Zen/fullscreen in Cursor (Electron). (+1 more)

### Community 20 - "_mcp_connect_one"
Cohesion: 0.25
Nodes (7): _mcp_connect_all_async(), _mcp_connect_one(), _mcp_server_supervisor(), _McpServerHandle, One MCP server's connection state. Tool-call requests are dispatched into…, Owns one MCP server's stdio connection for the entire process lifetime. The…, Connects a single MCP server and registers its tools on success. Returns…

### Community 21 - "queue_or_deliver_notification"
Cohesion: 0.13
Nodes (18): _get_idle_seconds(), queue_or_deliver_notification(), Caller must already hold _session_context_lock. Writes to a temp file and…, Seconds since the last system-wide keyboard/mouse input, via GetLastInputInfo.…, True if the user touched the keyboard/mouse within ACTIVE_IDLE_THRESHOLD_S…, Files something under the wake-up recap's important section without speaking it., The interrupt gate every proactive message (scheduled skills, health-check…, Registered with jarvis_sleep_mode: when Sleep Mode ends, replaces the old flood… (+10 more)

### Community 22 - "CLAUDE.md"
Cohesion: 0.10
Nodes (20): API spend lookup (2026-09-18), Confirmation gate follow-up (2026-09-18), Cost reporting, Dashboard (supervision UI), Gemini brain option (2026-09-18), Git, graphify, Image download (2026-09-19) (+12 more)

### Community 23 - "app.js"
Cohesion: 0.11
Nodes (46): actOnPending(), badge(), connectWs(), coreHeatmap(), esc(), fetchAuditResults(), fetchDailyItems(), fetchLlm() (+38 more)

### Community 24 - "jarvis_dashboard.py"
Cohesion: 0.06
Nodes (41): _build_app(), api_audit(), api_clear_finished_sessions(), api_command(), _sink(), api_llm(), api_set_llm(), api_state() (+33 more)

### Community 25 - "jarvis_voice_tone.py"
Cohesion: 0.32
Nodes (7): analyze_tone(), _lexical_scores(), _prosody(), Basic voice tone/sentiment awareness for Jarvis. Rule-based, deliberately…, Short line to fold into the agent system prompt for this turn; empty string if…, Returns {"tone": category, "confidence": 0..1, "signals": [short strings]}.…, tone_context_line()

### Community 26 - "handle_text_command"
Cohesion: 0.09
Nodes (26): _collapse_paths_for_speech(), _dashboard_approve_pending(), _sink(), _dashboard_reject_pending(), _execute_confirmed_action(), flush_pending_notifications(), handle_text_command(), _humanize_path_for_speech() (+18 more)

### Community 27 - "test_dashboard.py"
Cohesion: 0.05
Nodes (13): client(), dashboard(), db_path(), fixture, QA regression suite for jarvis_dashboard.py. Run with: python -m pytest…, test_command_endpoint_invokes_run_command(), test_daily_endpoint_exception_does_not_break(), test_get_pending_exception_does_not_break_state() (+5 more)

### Community 28 - "Tween"
Cohesion: 0.19
Nodes (21): _a(), Ao(), _assertThisInitialized(), cb(), cc(), ga(), gb(), hb() (+13 more)

### Community 29 - "download_image"
Cohesion: 0.11
Nodes (27): _check_host(), _CheckedRedirects, _clean_stem(), download_image(), _fetch(), Path, download_image: fetch one image URL and save it to a single fixed folder.…, i.pinimg.com/236x/.. or /736x/.. (a thumbnail) -> /originals/.. (full size). (+19 more)

### Community 30 - "jarvis_cache.py"
Cohesion: 0.38
Nodes (5): is_self_contained(), normalize_text(), Small, local-only cache helpers shared by jarvis.py: an env-flag reader,…, Lowercase, punctuation-stripped, whitespace-collapsed — so 'System status?' and…, test_normalize_and_self_contained()

### Community 31 - "Path"
Cohesion: 0.11
Nodes (23): _dashboard_get_services_status(), _fmt_gb(), get_large_files_report(), _load_mcp_server_configs(), _mcp_servers_config_path(), _memory_db_path(), _print_large_files_breakdown(), Path (+15 more)

### Community 32 - "build_system_blocks"
Cohesion: 0.09
Nodes (27): build_system_blocks(), build_system_prompt(), _dashboard_get_daily_items(), _fetch_projects(), get_active_facts_context(), get_projects_context(), get_skills_context(), get_user_profile_context() (+19 more)

### Community 33 - "_scripted_claude"
Cohesion: 0.22
Nodes (8): Fake Claude: with a tool_name, the first call requests it and the next returns…, _scripted_claude(), fake(), test_reply_cache_disabled_by_env(), test_reply_cache_never_stores_mutating_turns(), test_reply_cache_serves_readonly_repeat_without_claude(), test_reply_cache_skips_context_dependent_and_toolless_turns(), test_summary_cache_skips_second_claude_call()

### Community 34 - "main"
Cohesion: 0.09
Nodes (23): _acquire_single_instance_lock(), block_samples(), _dashboard_get_pending(), _dashboard_get_sleep(), api_key(), model_name(), _invalidate_read_caches(), _keyboard_is_pressed() (+15 more)

### Community 36 - "Brag Plan: Jarvis"
Cohesion: 0.10
Nodes (19): Audio direction, Brag Plan: Jarvis, Duration: ~21 seconds, Format: landscape — 1920x1080, Hook (first 3.3 seconds), Key moments (the middle), Outro / punchline, Scene 1 — Hook — 3.3s (+11 more)

### Community 37 - "SqliteKV"
Cohesion: 0.36
Nodes (4): Connection, key -> text value with a created_at timestamp; max_age_s is checked on read,…, SqliteKV, test_sqlite_kv_max_age_and_prune()

### Community 38 - "_scheduler_loop"
Cohesion: 0.07
Nodes (47): _check_due_reminders(), create_reminder(), _get_active_window_title(), _get_last_skill_run(), _guess_project_from_window_title(), _is_preferred_work_hours(), _parse_due_at(), datetime (+39 more)

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

### Community 44 - "test_restart.py"
Cohesion: 0.15
Nodes (18): check_syntax(), helper_command(), Event, Path, restart_jarvis: let Jarvis restart itself (voice: "restart yourself") to pick…, Error text for the first jarvis*.py that doesn't compile, else None., restart(), _stop_self() (+10 more)

### Community 45 - "run_agent_loop"
Cohesion: 0.09
Nodes (37): enabled(), JARVIS_<LAYER>_CACHE env flag, default on. Read on every call so it can be…, record(), stable_hash(), _cached_tools(), ensure_mcp_started(), _execute_tool(), get_mcp_tool_schemas() (+29 more)

### Community 46 - "na"
Cohesion: 0.29
Nodes (6): Aa(), Ca(), na(), Vb(), wb(), Xb()

### Community 47 - "na"
Cohesion: 0.29
Nodes (6): Aa(), Ca(), na(), Vb(), wb(), Xb()

### Community 48 - "Hyperframes Composition Brief: Jarvis"
Cohesion: 0.25
Nodes (7): Audio, Creative Direction, Hyperframes Composition Brief: Jarvis, Objective, Output, Source Material, Visual Identity

### Community 49 - "enable"
Cohesion: 0.22
Nodes (18): disable(), enable(), _get_state(), kind='nap' runs the exact same mode (quiet notifications, mail take-over, dark…, _set_state(), set_system_action_handler(), _set_volume(), toggle() (+10 more)

### Community 50 - "la"
Cohesion: 0.53
Nodes (6): Animation(), Da(), la(), ma(), Ua(), Va()

### Community 51 - "la"
Cohesion: 0.53
Nodes (6): Animation(), Da(), la(), ma(), Ua(), Va()

### Community 53 - "_claude_request"
Cohesion: 0.13
Nodes (20): _build_sleep_digest(), _claude_request(), _claude_text(), _duckduckgo_search(), _has_cache_ttl(), Logs this response's token usage + estimated cost to the api_usage table…, Two-part recap: what mattered first (urgent things that came through live while…, Returns (spoken_reply, code_to_type_or_empty). The fix-typing half only fires… (+12 more)

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

### Community 65 - "jarvis_sleep_mode.py"
Cohesion: 0.14
Nodes (15): _cancel_media_autopause(), _dark_mode_is_on(), _db_path(), _endpoint_volume_call(), _get_volume(), is_whitelisted_sender(), Path, Sleep Mode for Jarvis. Self-contained, like the other jarvis_*.py modules: owns… (+7 more)

### Community 66 - "stats_summary"
Cohesion: 0.18
Nodes (15): _connect(), _hhmm(), _period_stats(), Connection, datetime, Stats over the `days` calendar days ending at end_day (inclusive): tracked…, Read-only sleep trends for the dashboard, from sleep_log alone (no new tables).…, save_digest() (+7 more)

### Community 68 - "is_active"
Cohesion: 0.33
Nodes (6): fish_audio_prosody_overrides(), is_active(), Piper SynthesisConfig kwargs for calmer speech while Sleep Mode is active, or…, Fish Audio's prosody equivalent of tts_overrides() above — same calmer/quieter-…, tts_overrides(), test_enable_nap_logs_kind_and_disable_reports_it()

### Community 69 - "_set_dark_mode"
Cohesion: 0.40
Nodes (5): _broadcast_theme_change(), Tells running apps the theme changed (what Windows Settings does). The registry…, _set_dark_mode(), test_broadcast_never_runs_under_pytest(), test_theme_change_is_broadcast_after_the_registry_write()

### Community 72 - "_urlopen_hard_timeout"
Cohesion: 0.33
Nodes (5): _fish_audio_synthesize(), Request, urlopen(timeout=...) is supposed to bound the whole call, but a wedged TLS…, Calls Fish Audio's TTS REST API and returns (pcm_int16_bytes, sample_rate) —…, _urlopen_hard_timeout()

## Knowledge Gaps
- **63 isolated node(s):** `state`, `servicesPanel`, `servicesToggleBtn`, `Git`, `graphify` (+58 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 489 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_execute_tool_impl()` connect `_execute_tool_impl` to `_memory_db_connect`, `test_sleep.py`, `FileWatcher`, `jarvis.py`, `jarvis_memory_enhance.py`, `jarvis_billing.py`, `test_dev_features.py`, `_finish_background_task`, `jarvis_proactive.py`, `jarvis_dashboard.py`, `handle_text_command`, `download_image`, `Path`, `build_system_blocks`, `main`, `_scheduler_loop`, `test_restart.py`, `run_agent_loop`, `enable`, `_claude_request`, `get_system_status_report`?**
  _High betweenness centrality (0.067) - this node is a cross-community bridge._
- **Why does `TTSDiskCache` connect `TTSDiskCache` to `jarvis_cache.py`, `test_billing_failures_are_plain_sentences`?**
  _High betweenness centrality (0.014) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `_execute_tool_impl()` (e.g. with `_launch_focus_app()` and `_memory_db_connect()`) actually correct?**
  _`_execute_tool_impl()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `_memory_db_connect()` (e.g. with `_dashboard_get_usage()` and `_execute_tool_impl()`) actually correct?**
  _`_memory_db_connect()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `main()` (e.g. with `_dashboard_approve_pending()` and `_dashboard_get_daily_items()`) actually correct?**
  _`main()` has 15 INFERRED edges - model-reasoned connections that need verification._
- **What connects `state`, `servicesPanel`, `servicesToggleBtn` to the rest of the system?**
  _63 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `_memory_db_connect` be split into smaller, more focused modules?**
  _Cohesion score 0.09782608695652174 - nodes in this community are weakly interconnected._