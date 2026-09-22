# Graph Report - jarvis-main2  (2026-09-19)

## Corpus Check
- 53 files · ~121,832 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 30 file(s) not represented in the graph (top: .log 27, (none) 1, .vbs 1)

## Summary
- 1766 nodes · 3651 edges · 90 communities (80 shown, 7 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 173 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `046495a4`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- _obs
- jarvis_window_control.py
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
- jarvis_workflow.py
- Jarvis desktop voice assistant
- discord_selfbot_server.py
- Tween
- test_cache.py
- TTSDiskCache
- jarvis_proactive.py
- stats_summary
- ensure_mcp_started
- _scheduler_loop
- CLAUDE.md
- app.js
- _build_app
- jarvis_voice_tone.py
- _handle_text_command_impl
- test_dashboard.py
- Tween
- download_image
- jarvis_cache.py
- Path
- jarvis_sleep_mode.py
- _scripted_claude
- main
- TTLCache
- Brag Plan: Jarvis
- SqliteKV
- jarvis_task_scheduler.py
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
- invalidate_profile_cache
- la
- la
- _DuckDuckGoResultParser
- enable
- fb
- he
- Za
- Rd
- fb
- he
- Za
- Rd
- Brag Plan: Jarvis (chaotic cut)
- resolve_write_path
- _execute_tool_impl
- _float_env
- jarvis_tech_understanding.py
- is_paused
- download_models
- analyze_python_file
- Google Maps location sharing -> "where is <person>?" (2026-09-19)
- _narrating_claude
- jarvis_face.py
- build_system_prompt
- test_face.py
- _set_dark_mode
- _memory_db_connect
- test_short_notification_is_spoken_unchanged_without_a_claude_call
- create_reminder
- user_is_actively_working
- _urlopen_hard_timeout
- _endpoint_volume_call
- dashboard_state
- test_record_usage_never_raises
- test_shutdown_via_run_shell_is_staged_not_run
- calibrate
- test_1h_ttl_rejection_falls_back_to_5m_and_retries

## God Nodes (most connected - your core abstractions)
1. `_execute_tool_impl()` - 106 edges
2. `_memory_db_connect()` - 35 edges
3. `main()` - 35 edges
4. `run_agent_loop()` - 29 edges
5. `_build_app()` - 29 edges
6. `_obs()` - 27 edges
7. `list_profiles()` - 25 edges
8. `enroll()` - 25 edges
9. `_db()` - 24 edges
10. `esc()` - 23 edges

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

## Communities (90 total, 7 thin omitted)

### Community 0 - "_obs"
Cohesion: 0.12
Nodes (36): describe_presence(), enabled(), _fresh(), group_safe(), list_snapshots(), poll_once(), _Presence, One recognition cycle. Returns a short status word (used by tests and… (+28 more)

### Community 1 - "jarvis_window_control.py"
Cohesion: 0.17
Nodes (24): arrange_windows(), _cascade_rects(), _connect(), _db_path(), delete_layout(), _find(), _grid_rects(), list_layouts() (+16 more)

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
Cohesion: 0.05
Nodes (63): _bytes_to_gb(), _bytes_to_mb(), check_system_health(), _choose_input_device(), _chrome_executable(), _craft_system_status_summary(), _cursor_executable(), _cursor_foreground_hwnd_win32() (+55 more)

### Community 8 - "jarvis_memory_enhance.py"
Cohesion: 0.13
Nodes (22): _connect(), _cosine(), _db_path(), link_facts(), list_code_patterns(), list_decisions(), Connection, Path (+14 more)

### Community 9 - "test_gemini.py"
Cohesion: 0.06
Nodes (54): api_key(), call(), convert_messages(), convert_tools(), from_response(), get_provider(), model_name(), Path (+46 more)

### Community 10 - "jarvis_billing.py"
Cohesion: 0.14
Nodes (20): compute_cost(), _dollars(), _ensure_usage_table(), fetch_cost_buckets(), format_local_summary(), get_api_spend(), local_summary(), Connection (+12 more)

### Community 11 - "test_dev_features.py"
Cohesion: 0.06
Nodes (59): analyze_repo(), _existing_tests(), generate_tests(), _public_api(), _py_files(), Path, Repository analysis, unit-test generation and module boilerplate. Deterministic…, New `<name>.py` plus a matching test file, in the style the repo already uses. (+51 more)

### Community 12 - "jarvis_workflow.py"
Cohesion: 0.16
Nodes (20): _connect(), _db_path(), detect_stack(), get_context_summary(), get_workflow_status(), git_info(), Connection, Path (+12 more)

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
Nodes (6): _gate_env(), _kv_db(), Tests for the caching layers (jarvis_cache.py + their wiring in jarvis.py). Run…, test_busy_gate_holds_ordinary_notification_but_not_reminders(), test_bypass_busy_gate_still_respects_sleep_mode(), test_record_and_local_summary()

### Community 17 - "TTSDiskCache"
Cohesion: 0.29
Nodes (5): Path, WAV files under one directory, keyed by hash. LRU by mtime (touched on every…, TTSDiskCache, test_tts_cache_skips_synthesis_on_repeat(), test_tts_disk_cache_roundtrip_and_eviction()

### Community 18 - "jarvis_proactive.py"
Cohesion: 0.27
Nodes (12): check_project_health(), _connect(), _db_path(), _fmt_findings(), _iter_source_files(), Connection, Path, Proactive problem detection for Jarvis. Scans a file or project directory for… (+4 more)

### Community 19 - "stats_summary"
Cohesion: 0.16
Nodes (18): _connect(), _db_path(), _hhmm(), _period_stats(), Connection, datetime, Path, Stats over the `days` calendar days ending at end_day (inclusive): tracked… (+10 more)

### Community 20 - "ensure_mcp_started"
Cohesion: 0.10
Nodes (20): _dashboard_get_services_status(), ensure_mcp_started(), _load_mcp_server_configs(), _mcp_connect_all_async(), _mcp_connect_one(), _mcp_server_supervisor(), _mcp_servers_config_path(), _McpServerHandle (+12 more)

### Community 21 - "_scheduler_loop"
Cohesion: 0.07
Nodes (38): AbstractEventLoop, _background_tasks_dir(), _check_background_tasks(), _check_due_reminders(), _ensure_mcp_loop(), _get_active_window_title(), _get_last_skill_run(), _guess_project_from_window_title() (+30 more)

### Community 22 - "CLAUDE.md"
Cohesion: 0.09
Nodes (21): API spend lookup (2026-09-18), Confirmation gate follow-up (2026-09-18), Cost reporting, Dashboard (supervision UI), Face recognition (2026-09-19), Gemini brain option (2026-09-18), Git, graphify (+13 more)

### Community 23 - "app.js"
Cohesion: 0.09
Nodes (54): actOnPending(), badge(), connectWs(), coreHeatmap(), esc(), fetchAuditResults(), fetchDailyItems(), fetchIdentity() (+46 more)

### Community 24 - "_build_app"
Cohesion: 0.05
Nodes (54): _build_app(), api_audit(), api_clear_finished_sessions(), api_command(), _sink(), api_face_delete(), api_face_delete_snapshots(), api_face_events() (+46 more)

### Community 25 - "jarvis_voice_tone.py"
Cohesion: 0.32
Nodes (7): analyze_tone(), _lexical_scores(), _prosody(), Basic voice tone/sentiment awareness for Jarvis. Rule-based, deliberately…, Short line to fold into the agent system prompt for this turn; empty string if…, Returns {"tone": category, "confidence": 0..1, "signals": [short strings]}.…, tone_context_line()

### Community 26 - "_handle_text_command_impl"
Cohesion: 0.12
Nodes (19): _collapse_paths_for_speech(), _dashboard_approve_pending(), _sink(), _dashboard_reject_pending(), start_session(), _execute_confirmed_action(), _face_release_held_notifications(), flush_pending_notifications() (+11 more)

### Community 27 - "test_dashboard.py"
Cohesion: 0.05
Nodes (22): RuntimeError, client(), dashboard(), db_path(), fixture, QA regression suite for jarvis_dashboard.py. Run with: python -m pytest…, test_command_endpoint_invokes_run_command(), test_daily_endpoint_exception_does_not_break() (+14 more)

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
Cohesion: 0.14
Nodes (18): _fmt_gb(), get_large_files_report(), _memory_db_path(), _own_code_context_line(), _print_large_files_breakdown(), Path, _quarantine_corrupt_memory_db(), Renames a corrupted memory DB aside (never deletes) so a fresh one can take its… (+10 more)

### Community 32 - "jarvis_sleep_mode.py"
Cohesion: 0.15
Nodes (17): queue_or_deliver_notification(), The interrupt gate every proactive message (scheduled skills, health-check…, _cancel_media_autopause(), _dark_mode_is_on(), fish_audio_prosody_overrides(), is_active(), is_whitelisted_sender(), Sleep Mode for Jarvis. Self-contained, like the other jarvis_*.py modules: owns… (+9 more)

### Community 33 - "_scripted_claude"
Cohesion: 0.33
Nodes (6): Fake Claude: with a tool_name, the first call requests it and the next returns…, _scripted_claude(), test_reply_cache_disabled_by_env(), test_reply_cache_never_stores_mutating_turns(), test_reply_cache_serves_readonly_repeat_without_claude(), test_reply_cache_skips_context_dependent_and_toolless_turns()

### Community 34 - "main"
Cohesion: 0.07
Nodes (36): _acquire_single_instance_lock(), block_samples(), _dashboard_get_pending(), _dashboard_get_sleep(), _dashboard_kill_background_task(), _face_greet(), _get_whisper_model(), handle_text_command() (+28 more)

### Community 36 - "Brag Plan: Jarvis"
Cohesion: 0.10
Nodes (19): Audio direction, Brag Plan: Jarvis, Duration: ~21 seconds, Format: landscape — 1920x1080, Hook (first 3.3 seconds), Key moments (the middle), Outro / punchline, Scene 1 — Hook — 3.3s (+11 more)

### Community 37 - "SqliteKV"
Cohesion: 0.31
Nodes (5): Connection, key -> text value with a created_at timestamp; max_age_s is checked on read,…, SqliteKV, _speech_summary_kv(), test_sqlite_kv_max_age_and_prune()

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
Nodes (70): _body_of(), _classify_critical(), _connect(), _db_path(), _emails(), _env_set(), _handle_family(), _send() (+62 more)

### Community 44 - "test_restart.py"
Cohesion: 0.15
Nodes (18): check_syntax(), helper_command(), Event, Path, restart_jarvis: let Jarvis restart itself (voice: "restart yourself") to pick…, Error text for the first jarvis*.py that doesn't compile, else None., restart(), _stop_self() (+10 more)

### Community 45 - "run_agent_loop"
Cohesion: 0.07
Nodes (51): _build_sleep_digest(), build_system_blocks(), enabled(), JARVIS_<LAYER>_CACHE env flag, default on. Read on every call so it can be…, record(), stable_hash(), _cached_tools(), _claude_request() (+43 more)

### Community 46 - "na"
Cohesion: 0.29
Nodes (6): Aa(), Ca(), na(), Vb(), wb(), Xb()

### Community 47 - "na"
Cohesion: 0.29
Nodes (6): Aa(), Ca(), na(), Vb(), wb(), Xb()

### Community 48 - "Hyperframes Composition Brief: Jarvis"
Cohesion: 0.25
Nodes (7): Audio, Creative Direction, Hyperframes Composition Brief: Jarvis, Objective, Output, Source Material, Visual Identity

### Community 49 - "invalidate_profile_cache"
Cohesion: 0.15
Nodes (13): invalidate_profile_cache(), enrolled(), fx(), jarvis(), fixture, quiet_jarvis(), Goes through handle_text_command -> _execute_tool (not _execute_impl): also…, test_delete_via_the_real_tool_path_needs_two_user_messages() (+5 more)

### Community 50 - "la"
Cohesion: 0.53
Nodes (6): Animation(), Da(), la(), ma(), Ua(), Va()

### Community 51 - "la"
Cohesion: 0.53
Nodes (6): Animation(), Da(), la(), ma(), Ua(), Va()

### Community 52 - "_DuckDuckGoResultParser"
Cohesion: 0.33
Nodes (3): HTMLParser, _duckduckgo_search(), _DuckDuckGoResultParser

### Community 53 - "enable"
Cohesion: 0.24
Nodes (18): disable(), enable(), _get_state(), kind='nap' runs the exact same mode (quiet notifications, mail take-over, dark…, _set_state(), set_system_action_handler(), _set_volume(), toggle() (+10 more)

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

### Community 64 - "resolve_write_path"
Cohesion: 0.12
Nodes (24): _read_file_tool(), classify(), default_dir(), _inside(), Path, Jarvis_Workspace: the default home for every file Jarvis creates, saves or…, Absolute paths are used as given; a relative one is looked up in the workspace…, A workspace subfolder, created if missing (for tools that pick their own file… (+16 more)

### Community 65 - "_execute_tool_impl"
Cohesion: 0.14
Nodes (17): click_at(), _current_command_source(), drag_and_drop(), _execute_tool_impl(), focus_window(), _http_request_tool(), Runs one tool call and returns the text to feed back to Claude as its…, Where the command being run came from ("voice"/"text"/"dashboard"/"phone"), or… (+9 more)

### Community 66 - "_float_env"
Cohesion: 0.20
Nodes (14): _float_env(), _lower_thread_priority(), poll_interval(), Run the poll below normal priority so an inference burst yields to the voice…, Start the low-duty background poll (no-op unless JARVIS_FACE_ENABLED=1). The…, Once the owner has been steadily in view with nobody else, look less often…, settled_poll_interval(), snapshot_keep_days() (+6 more)

### Community 67 - "jarvis_tech_understanding.py"
Cohesion: 0.23
Nodes (12): build_import_graph(), format_analysis_report(), format_error_report(), _imports_of(), _module_name_for(), parse_error(), Path, Deep technical understanding helpers for Jarvis. Three independent… (+4 more)

### Community 68 - "is_paused"
Cohesion: 0.15
Nodes (14): is_paused(), Reset live presence *after* any in-flight poll finishes, so that poll cannot…, Camera privacy switch. Pausing is always allowed (it can only make things more…, Why enroll/delete must not run for this command source, or None if it may., Forget live presence (feature paused / asleep / nothing enrolled): stale…, refuse_reason(), _reset_presence_serialized(), _reset_transient() (+6 more)

### Community 69 - "download_models"
Cohesion: 0.15
Nodes (13): download_models(), _model_root(), models_ready(), fn(event_dict) is called after every audit row (kind/name/confidence/ts only)…, One-time fetch of the buffalo_l pack from insightface's GitHub release.…, set_event_hook(), insightface would silently fetch the pack itself with no size/hash check,…, _Resp (+5 more)

### Community 73 - "Google Maps location sharing -> "where is <person>?" (2026-09-19)"
Cohesion: 0.25
Nodes (7): 1. Unofficial library (closest to the goal), 2. Telegram live location (official, stable), 3. Dedicated tracker (official, always-on), Before building, Google Maps location sharing -> "where is <person>?" (2026-09-19), Later, Recommendation

### Community 74 - "_narrating_claude"
Cohesion: 0.29
Nodes (5): _narrating_claude(), fake(), test_narrate_off_keeps_old_behaviour(), test_narrate_speaks_text_beside_a_tool_call_and_keeps_it_out_of_the_reply(), test_summary_cache_skips_second_claude_call()

### Community 75 - "jarvis_face.py"
Cohesion: 0.06
Nodes (65): Exception, _already_seen_recently(), _camera_failed(), _camera_ok(), _connect(), _consent_summary(), _crop_jpeg(), _db() (+57 more)

### Community 76 - "build_system_prompt"
Cohesion: 0.12
Nodes (17): build_system_prompt(), _dashboard_get_daily_items(), get_active_facts_context(), get_skills_context(), get_user_profile_context(), _load_skills(), Formats all stored user_profile facts for embedding in the system prompt. Empty…, Formats currently-active remembered facts for the system prompt — this is what… (+9 more)

### Community 77 - "test_face.py"
Cohesion: 0.06
Nodes (44): _already_enrolled(), _clean_name(), delete(), delete_by_id(), describe_profiles(), enroll(), list_profiles(), Enroll the (single) owner. Refused unless no one is enrolled yet, so a second… (+36 more)

### Community 78 - "_set_dark_mode"
Cohesion: 0.40
Nodes (5): _broadcast_theme_change(), Tells running apps the theme changed (what Windows Settings does). The registry…, _set_dark_mode(), test_broadcast_never_runs_under_pytest(), test_theme_change_is_broadcast_after_the_registry_write()

### Community 79 - "_memory_db_connect"
Cohesion: 0.06
Nodes (41): _append_history(), _apply_memory_db_pragmas(), cancel_reminder(), _catastrophic_reason(), _count_running_background_tasks(), _create_memory_tables(), _delegate_research(), _run() (+33 more)

### Community 81 - "create_reminder"
Cohesion: 0.50
Nodes (4): create_reminder(), _parse_due_at(), Accepts the ISO-ish formats a model is likely to produce ("2026-09-16 15:00",…, Schedules a reminder for an absolute time (due_at) or a delay from now…

### Community 82 - "user_is_actively_working"
Cohesion: 0.50
Nodes (4): _get_idle_seconds(), Seconds since the last system-wide keyboard/mouse input, via GetLastInputInfo.…, True if the user touched the keyboard/mouse within ACTIVE_IDLE_THRESHOLD_S…, user_is_actively_working()

### Community 83 - "_urlopen_hard_timeout"
Cohesion: 0.33
Nodes (5): _fish_audio_synthesize(), Request, urlopen(timeout=...) is supposed to bound the whole call, but a wedged TLS…, Calls Fish Audio's TTS REST API and returns (pcm_int16_bytes, sample_rate) —…, _urlopen_hard_timeout()

### Community 84 - "_endpoint_volume_call"
Cohesion: 0.50
Nodes (4): _endpoint_volume_call(), _get_volume(), Runs fn(endpoint_volume) with COM initialised on this thread. None on any…, Master volume as 0.0-1.0, or None if it can't be read.

### Community 85 - "dashboard_state"
Cohesion: 0.13
Nodes (22): dashboard_state(), _data_dir(), _DataBlob, _db_path(), _dpapi(), blob(), event_kinds(), _has_encrypted_data() (+14 more)

### Community 89 - "calibrate"
Cohesion: 0.12
Nodes (12): calibrate(), camera_index(), CameraUnavailable, _capture_and_analyze(), _get_engine(), _InsightEngine, _open_camera(), Dry run of the enrollment liveness check that stores NOTHING (no profile, no… (+4 more)

## Knowledge Gaps
- **70 isolated node(s):** `state`, `servicesPanel`, `servicesToggleBtn`, `IDENTITY_KIND_LABELS`, `Git` (+65 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 588 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_execute_tool_impl()` connect `_execute_tool_impl` to `_obs`, `jarvis_window_control.py`, `test_sleep.py`, `FileWatcher`, `jarvis.py`, `jarvis_memory_enhance.py`, `test_gemini.py`, `jarvis_billing.py`, `test_dev_features.py`, `jarvis_workflow.py`, `jarvis_proactive.py`, `_build_app`, `_handle_text_command_impl`, `download_image`, `Path`, `jarvis_task_scheduler.py`, `test_restart.py`, `run_agent_loop`, `enable`, `resolve_write_path`, `jarvis_tech_understanding.py`, `is_paused`, `analyze_python_file`, `build_system_prompt`, `test_face.py`, `_memory_db_connect`, `create_reminder`?**
  _High betweenness centrality (0.086) - this node is a cross-community bridge._
- **Why does `_fish_audio_synthesize()` connect `_urlopen_hard_timeout` to `test_dashboard.py`, `run_agent_loop`, `jarvis.py`?**
  _High betweenness centrality (0.022) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `_execute_tool_impl()` (e.g. with `_launch_focus_app()` and `_memory_db_connect()`) actually correct?**
  _`_execute_tool_impl()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `_memory_db_connect()` (e.g. with `_dashboard_get_usage()` and `_execute_tool_impl()`) actually correct?**
  _`_memory_db_connect()` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `main()` (e.g. with `_dashboard_approve_pending()` and `_dashboard_get_daily_items()`) actually correct?**
  _`main()` has 18 INFERRED edges - model-reasoned connections that need verification._
- **What connects `state`, `servicesPanel`, `servicesToggleBtn` to the rest of the system?**
  _70 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `_obs` be split into smaller, more focused modules?**
  _Cohesion score 0.11806543385490754 - nodes in this community are weakly interconnected._