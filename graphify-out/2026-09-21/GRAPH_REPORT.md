# Graph Report - jarvis-main2  (2026-09-20)

## Corpus Check
- 64 files · ~172,903 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 30 file(s) not represented in the graph (top: .log 27, (none) 1, .vbs 1)

## Summary
- 2529 nodes · 5723 edges · 120 communities (104 shown, 13 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 262 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d2bea125`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_autonomy.py
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
- _ingest
- jarvis_workflow.py
- Full Autonomy Stack
- jarvis_dynamic_tools.py
- Tween
- test_cache.py
- TTSDiskCache
- jarvis_proactive.py
- jarvis_autonomy.py
- _mcp_connect_one
- execute_mcp_tool
- CLAUDE.md
- app.js
- _build_app
- _tools
- speak_text
- test_dashboard.py
- Tween
- download_image
- jarvis_autonomy_organise.py
- Path
- _on
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
- poll_once
- la
- la
- _call
- test_dev_features.py
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
- _DuckDuckGoResultParser
- start_polling
- jarvis_tech_understanding.py
- is_paused
- timedelta
- _db
- Google Maps location sharing -> "where is <person>?" (2026-09-19)
- _narrating_claude
- jarvis_face.py
- jarvis_autonomy_skills.py
- test_face.py
- jarvis_memory_consolidation.py
- _memory_db_connect
- Fake
- _InsightEngine
- build_calendar_args
- build_system_blocks
- create_reminder
- RuntimeError
- test_record_usage_never_raises
- test_shutdown_via_run_shell_is_staged_not_run
- autonomy.js
- calibrate
- _mail_answer
- test_a01_known_bypass_routes_are_rejected
- jarvis_dashboard.py
- add_commitment
- enabled
- test_guest_reminders.py
- _Rec
- user_is_actively_working
- queue_or_deliver_notification
- jarvis_focus.py
- _connect
- test_wp5_a_skill_run_still_goes_through_the_execute_tool_gate
- start
- test_dashboard_llm_endpoints
- _ConnectionManager
- jarvis_roblox.py
- _scheduler_callbacks
- _set_broadcast
- _claude_request
- _origin_is_loopback
- test_f_defaults_are_on_with_no_flags_needed
- test_autonomy_code_cannot_reach_the_confirmation_gate
- _execute_tool_impl
- _handle_text_command_impl
- test_1h_ttl_rejection_falls_back_to_5m_and_retries
- test_short_notification_is_spoken_unchanged_without_a_claude_call
- jarvis_vibes.py
- jarvis_voice_tone.py
- fixture
- _session_locked

## God Nodes (most connected - your core abstractions)
1. `_execute_tool_impl()` - 118 edges
2. `Fake` - 102 edges
3. `_on()` - 59 edges
4. `_future()` - 55 edges
5. `_build_app()` - 50 edges
6. `_iso()` - 46 edges
7. `main()` - 45 edges
8. `_rows()` - 41 edges
9. `_memory_db_connect()` - 35 edges
10. `_cb()` - 35 edges

## Surprising Connections (you probably didn't know these)
- `_run()` --indirect_call--> `started_at()`  [INFERRED]
  jarvis.py → jarvis_sleep_mode.py
- `_execute_tool_impl()` --calls--> `format_local_summary()`  [EXTRACTED]
  jarvis.py → jarvis_billing.py
- `_execute_tool_impl()` --calls--> `is_dynamic()`  [EXTRACTED]
  jarvis.py → jarvis_dynamic_tools.py
- `_execute_tool_impl()` --calls--> `add_watched_folder()`  [EXTRACTED]
  jarvis.py → jarvis_filewatcher.py
- `_execute_tool_impl()` --calls--> `get_recent_file_events()`  [EXTRACTED]
  jarvis.py → jarvis_filewatcher.py

## Import Cycles
- None detected.

## Communities (120 total, 13 thin omitted)

### Community 0 - "test_autonomy.py"
Cohesion: 0.03
Nodes (30): skipif, _acted(), _file(), Tests for jarvis_autonomy.py, jarvis_dynamic_tools.py,…, The gate is untouched: an autonomous agent run that reaches a catastrophic…, test_b_a_file_still_downloading_is_retried_not_dropped(), test_b_a_symlink_that_leaves_the_folder_is_rejected(), test_b_default_rules_file_documents_images_and_spreadsheets() (+22 more)

### Community 1 - "jarvis_window_control.py"
Cohesion: 0.14
Nodes (29): arrange_windows(), _cascade_rects(), close_window(), _connect(), _db_path(), delete_layout(), _find(), _grid_rects() (+21 more)

### Community 2 - "brag-output-2026-09-19-001152/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 3 - "jarvis_sleep_mode.py"
Cohesion: 0.05
Nodes (73): _broadcast_theme_change(), _cancel_media_autopause(), _connect(), _dark_mode_is_on(), _db_path(), disable(), enable(), _endpoint_volume_call() (+65 more)

### Community 4 - "brag-output/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 5 - "FileWatcher"
Cohesion: 0.10
Nodes (15): add_watched_folder(), _connect(), _db_path(), _default_watch_paths(), FileWatcher, get_recent_file_events(), list_watched_folders(), Connection (+7 more)

### Community 6 - "jarvis.py"
Cohesion: 0.05
Nodes (63): _autonomy_inbound(), _autonomy_mail_hook(), _bytes_to_gb(), _bytes_to_mb(), check_system_health(), _choose_input_device(), _chrome_executable(), _craft_system_status_summary() (+55 more)

### Community 8 - "jarvis_memory_enhance.py"
Cohesion: 0.13
Nodes (22): _connect(), _cosine(), _db_path(), link_facts(), list_code_patterns(), list_decisions(), Connection, Path (+14 more)

### Community 9 - "test_gemini.py"
Cohesion: 0.07
Nodes (48): call(), convert_messages(), convert_tools(), from_response(), get_provider(), Path, Request, Gemini (Google AI Studio) backend for Jarvis's LLM calls. Jarvis's callers all… (+40 more)

### Community 10 - "jarvis_billing.py"
Cohesion: 0.15
Nodes (19): compute_cost(), _dollars(), _ensure_usage_table(), fetch_cost_buckets(), format_local_summary(), get_api_spend(), local_summary(), Connection (+11 more)

### Community 11 - "_ingest"
Cohesion: 0.24
Nodes (12): accept_commitment(), _action_for_commitment(), _commitment(), gate_reason(), _ingest(), _meta(), The one concrete action a stored commitment implies, or (None, {}) if it is…, Items extracted while in dry-run were stored (so the log has them) but never… (+4 more)

### Community 12 - "jarvis_workflow.py"
Cohesion: 0.16
Nodes (20): _connect(), _db_path(), detect_stack(), get_context_summary(), get_workflow_status(), git_info(), Connection, Path (+12 more)

### Community 13 - "Full Autonomy Stack"
Cohesion: 0.05
Nodes (38): Audit-and-fix pass (2026-09-20, after the full-permission change), Audit pass 2 (after injection hardening + file organising): what changed because of real bugs, Calendar and skills (small hardening), Dynamic tools, File organising (ON by default whenever autonomy is on), Full Autonomy Stack, How the tick works, How to verify (do this before trusting it) (+30 more)

### Community 14 - "jarvis_dynamic_tools.py"
Cohesion: 0.07
Nodes (56): find_dm_with_user(), list_dm_channels(), list_servers(), on_ready(), Custom MCP server wrapping discord.py-self to let Jarvis act as the user's own…, Lists the Discord servers (guilds) this account is a member of, with their IDs., Lists currently open DM conversations, with their channel IDs., Finds a DM channel ID by matching a username against currently open DM… (+48 more)

### Community 15 - "Tween"
Cohesion: 0.19
Nodes (21): _a(), Ao(), _assertThisInitialized(), cb(), cc(), ga(), gb(), hb() (+13 more)

### Community 16 - "test_cache.py"
Cohesion: 0.08
Nodes (7): _gate_env(), _kv_db(), Tests for the caching layers (jarvis_cache.py + their wiring in jarvis.py). Run…, test_busy_gate_holds_ordinary_notification_but_not_reminders(), test_bypass_busy_gate_still_respects_sleep_mode(), test_enabled_flag(), test_record_and_local_summary()

### Community 17 - "TTSDiskCache"
Cohesion: 0.29
Nodes (5): Path, WAV files under one directory, keyed by hash. LRU by mtime (touched on every…, TTSDiskCache, test_tts_cache_skips_synthesis_on_repeat(), test_tts_disk_cache_roundtrip_and_eviction()

### Community 18 - "jarvis_proactive.py"
Cohesion: 0.27
Nodes (12): check_project_health(), _connect(), _db_path(), _fmt_findings(), _iter_source_files(), Connection, Path, Proactive problem detection for Jarvis. Scans a file or project directory for… (+4 more)

### Community 19 - "jarvis_autonomy.py"
Cohesion: 0.08
Nodes (59): add_project_action(), approve_campaign(), approve_suggestion(), _brief(), budgets(), delete_policy(), dismiss_suggestion(), _exec() (+51 more)

### Community 20 - "_mcp_connect_one"
Cohesion: 0.25
Nodes (7): _mcp_connect_all_async(), _mcp_connect_one(), _mcp_server_supervisor(), _McpServerHandle, One MCP server's connection state. Tool-call requests are dispatched into…, Owns one MCP server's stdio connection for the entire process lifetime. The…, Connects a single MCP server and registers its tools on success. Returns…

### Community 21 - "execute_mcp_tool"
Cohesion: 0.20
Nodes (9): AbstractEventLoop, _autonomy_create_event(), _ensure_mcp_loop(), execute_mcp_tool(), _mcp_call_tool_async(), _mcp_run_coro(), Direct Calendar MCP create-event (no agent loop). None = no usable calendar…, MCP's client SDK is asyncio-only; Jarvis is thread-based throughout. This runs… (+1 more)

### Community 22 - "CLAUDE.md"
Cohesion: 0.09
Nodes (22): API spend lookup (2026-09-18), Confirmation gate follow-up (2026-09-18), Cost reporting, Dashboard (supervision UI), Face recognition (2026-09-19), Full Autonomy stack (2026-09-20), Gemini brain option (2026-09-18), Git (+14 more)

### Community 23 - "app.js"
Cohesion: 0.09
Nodes (54): actOnPending(), badge(), connectWs(), coreHeatmap(), esc(), fetchAuditResults(), fetchDailyItems(), fetchIdentity() (+46 more)

### Community 24 - "_build_app"
Cohesion: 0.10
Nodes (35): _build_app(), api_autonomy(), api_autonomy_campaign_action(), api_autonomy_campaign_approve(), api_autonomy_commitment(), api_autonomy_commitment_accept(), api_autonomy_dry_run(), api_autonomy_enabled() (+27 more)

### Community 25 - "_tools"
Cohesion: 0.12
Nodes (14): test_c_skill_failure_stops_logs_the_step_and_notifies_exactly_once(), test_concurrent_extraction_of_the_same_item_inserts_it_once(), go(), test_d01_two_simultaneous_approvals_run_the_action_once(), go(), test_skill_creation_budget_holds_under_concurrency(), test_skills_never_mine_typing_http_or_secret_bearing_tools_or_huge_inputs(), test_wp5_cannot_smuggle_unknown_or_forbidden_tools_or_bad_shapes() (+6 more)

### Community 26 - "speak_text"
Cohesion: 0.13
Nodes (14): _away_warn(), _face_greet(), _fish_audio_synthesize(), _play_pcm_bytes(), Request, urlopen(timeout=...) is supposed to bound the whole call, but a wedged TLS…, Spoken warning before away mode locks the computer (not routed through the…, Spoken greeting when the owner's face appears. Skipped (not queued: a stale… (+6 more)

### Community 27 - "test_dashboard.py"
Cohesion: 0.05
Nodes (18): client(), dashboard(), db_path(), fixture, QA regression suite for jarvis_dashboard.py. Run with: python -m pytest…, test_command_endpoint_invokes_run_command(), test_daily_endpoint_exception_does_not_break(), boom() (+10 more)

### Community 28 - "Tween"
Cohesion: 0.19
Nodes (21): _a(), Ao(), _assertThisInitialized(), cb(), cc(), ga(), gb(), hb() (+13 more)

### Community 29 - "download_image"
Cohesion: 0.11
Nodes (27): _check_host(), _CheckedRedirects, _clean_stem(), download_image(), _fetch(), Path, download_image: fetch one image URL and save it to a single fixed folder.…, i.pinimg.com/236x/.. or /736x/.. (a thumbnail) -> /originals/.. (full size). (+19 more)

### Community 30 - "jarvis_autonomy_organise.py"
Cohesion: 0.13
Nodes (35): add_root(), add_rule(), _copy_no_clobber(), handle_new_file(), handle_tool(), home(), _init(), _inside() (+27 more)

### Community 31 - "Path"
Cohesion: 0.12
Nodes (21): _dashboard_get_services_status(), _fmt_gb(), get_large_files_report(), _load_mcp_server_configs(), _mcp_servers_config_path(), _memory_db_path(), _print_large_files_breakdown(), Path (+13 more)

### Community 32 - "_on"
Cohesion: 0.05
Nodes (63): _future(), _on(), FULL-PERMISSION MODEL: a confident, non-catastrophic item is acted on…, test_a_classifier_actions_influenced_by_inbound_mail_face_the_third_party_bar(), test_a_email_recipient_allowlist_is_optional_and_empty_means_unrestricted(), test_a_injected_email_at_medium_confidence_does_not_auto_act_and_says_why(), test_a_third_party_bar_matrix(), test_a_user_after_turn_still_auto_acts_at_the_normal_floor() (+55 more)

### Community 33 - "_scripted_claude"
Cohesion: 0.33
Nodes (6): Fake Claude: with a tool_name, the first call requests it and the next returns…, _scripted_claude(), test_reply_cache_disabled_by_env(), test_reply_cache_never_stores_mutating_turns(), test_reply_cache_serves_readonly_repeat_without_claude(), test_reply_cache_skips_context_dependent_and_toolless_turns()

### Community 34 - "main"
Cohesion: 0.06
Nodes (40): _acquire_single_instance_lock(), block_samples(), _dashboard_get_pending(), _dashboard_get_sleep(), _dashboard_get_usage(), _dashboard_kill_background_task(), _get_whisper_model(), handle_text_command() (+32 more)

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
Nodes (76): _autonomy_poll_mail(), New inbox messages (not the user's own, not yet seen by autonomy) with their…, _body_of(), _classify_critical(), _connect(), _db_path(), _emails(), _env_set() (+68 more)

### Community 44 - "test_restart.py"
Cohesion: 0.15
Nodes (18): check_syntax(), helper_command(), Event, Path, restart_jarvis: let Jarvis restart itself (voice: "restart yourself") to pick…, Error text for the first jarvis*.py that doesn't compile, else None., restart(), _stop_self() (+10 more)

### Community 45 - "run_agent_loop"
Cohesion: 0.07
Nodes (49): _autonomy_calendar_events(), _autonomy_callbacks(), _autonomy_run_agent(), enabled(), is_self_contained(), normalize_text(), Small, local-only cache helpers shared by jarvis.py: an env-flag reader,…, JARVIS_<LAYER>_CACHE env flag, default on. Read on every call so it can be… (+41 more)

### Community 46 - "na"
Cohesion: 0.29
Nodes (6): Aa(), Ca(), na(), Vb(), wb(), Xb()

### Community 47 - "na"
Cohesion: 0.29
Nodes (6): Aa(), Ca(), na(), Vb(), wb(), Xb()

### Community 48 - "Hyperframes Composition Brief: Jarvis"
Cohesion: 0.25
Nodes (7): Audio, Creative Direction, Hyperframes Composition Brief: Jarvis, Objective, Output, Source Material, Visual Identity

### Community 49 - "poll_once"
Cohesion: 0.12
Nodes (38): describe_presence(), enabled(), _fresh(), group_safe(), list_snapshots(), poll_once(), _Presence, One recognition cycle. Returns a short status word (used by tests and… (+30 more)

### Community 50 - "la"
Cohesion: 0.53
Nodes (6): Animation(), Da(), la(), ma(), Ua(), Va()

### Community 51 - "la"
Cohesion: 0.53
Nodes (6): Animation(), Da(), la(), ma(), Ua(), Va()

### Community 52 - "_call"
Cohesion: 0.11
Nodes (36): Any, _work(), _ask_model(), _audit(), _call(), _campaign_step(), _clean(), create_suggestion() (+28 more)

### Community 53 - "test_dev_features.py"
Cohesion: 0.19
Nodes (17): analyze_repo(), _existing_tests(), generate_tests(), _public_api(), _py_files(), Path, Repository analysis, unit-test generation and module boilerplate. Deterministic…, New `<name>.py` plus a matching test file, in the style the repo already uses. (+9 more)

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

### Community 66 - "start_polling"
Cohesion: 0.15
Nodes (13): _lower_thread_priority(), poll_interval(), Run the poll below normal priority so an inference burst yields to the voice…, Start the low-duty background poll (no-op unless JARVIS_FACE_ENABLED=1). The…, Once the owner has been steadily in view with nobody else, look less often…, settled_poll_interval(), start_polling(), loop() (+5 more)

### Community 67 - "jarvis_tech_understanding.py"
Cohesion: 0.13
Nodes (14): analyze_python_file(), build_import_graph(), format_analysis_report(), format_error_report(), _imports_of(), _module_name_for(), parse_error(), Path (+6 more)

### Community 68 - "is_paused"
Cohesion: 0.11
Nodes (20): away_enabled(), away_status(), get_setting(), _greeting_text(), is_paused(), _maybe_greet(), Camera privacy switch. Pausing is always allowed (it can only make things more…, Why enroll/delete must not run for this command source, or None if it may. (+12 more)

### Community 69 - "timedelta"
Cohesion: 0.11
Nodes (43): agent_context_line(), _announce_pending(), _classifier_step(), _context_summary(), _deadline_scan(), _env_int(), _expire_old(), _file_scan() (+35 more)

### Community 72 - "_db"
Cohesion: 0.12
Nodes (30): _consent_summary(), _db(), delete_all_snapshots(), _emit(), _encrypt(), export_profile(), housekeeping(), invalidate_profile_cache() (+22 more)

### Community 73 - "Google Maps location sharing -> "where is <person>?" (2026-09-19)"
Cohesion: 0.25
Nodes (7): 1. Unofficial library (closest to the goal), 2. Telegram live location (official, stable), 3. Dedicated tracker (official, always-on), Before building, Google Maps location sharing -> "where is <person>?" (2026-09-19), Later, Recommendation

### Community 74 - "_narrating_claude"
Cohesion: 0.29
Nodes (5): _narrating_claude(), fake(), test_narrate_off_keeps_old_behaviour(), test_narrate_speaks_text_beside_a_tool_call_and_keeps_it_out_of_the_reply(), test_summary_cache_skips_second_claude_call()

### Community 75 - "jarvis_face.py"
Cohesion: 0.08
Nodes (48): Exception, _already_enrolled(), _already_seen_recently(), away_grace_s(), _away_reset(), _away_step(), away_warn_s(), _camera_failed() (+40 more)

### Community 76 - "jarvis_autonomy_skills.py"
Cohesion: 0.18
Nodes (23): _work(), True if this turn read mail/web/files/screen: its reply and tool results may…, _recent_tool_actions(), _recent_tool_rows(), create_skill(), handle_tool(), _init(), _known() (+15 more)

### Community 77 - "test_face.py"
Cohesion: 0.07
Nodes (39): _clean_name(), delete(), delete_by_id(), enroll(), list_profiles(), Enroll the (single) owner. Refused unless no one is enrolled yet, so a second…, Remove a profile and its embeddings. The audit trail of events is kept (it…, set_setting() (+31 more)

### Community 78 - "jarvis_memory_consolidation.py"
Cohesion: 0.28
Nodes (14): abstract_rules(), compress_old_summaries(), _connect(), consolidate(), _db_path(), _iso(), Connection, datetime (+6 more)

### Community 79 - "_memory_db_connect"
Cohesion: 0.07
Nodes (39): _append_history(), _apply_memory_db_pragmas(), _background_tasks_dir(), cancel_reminder(), _catastrophic_reason(), _check_background_tasks(), _count_running_background_tasks(), _create_memory_tables() (+31 more)

### Community 80 - "Fake"
Cohesion: 0.09
Nodes (36): _capture(), _cb(), Fake, O(), Records callback traffic; `answers` maps a marker in the prompt to the JSON the…, test_a_classifier_context_is_framed(), test_a_conversation_extraction_of_tool_derived_text_is_framed(), test_a_inbound_prompt_is_framed_sanitised_and_length_capped() (+28 more)

### Community 81 - "_InsightEngine"
Cohesion: 0.13
Nodes (10): _InsightEngine, Observation, fn(event_dict) is called after every audit row (kind/name/confidence/ts only)…, set_event_hook(), insightface would silently fetch the pack itself with no size/hash check,…, test_a_failing_lock_hook_does_not_break_polling(), test_engine_caps_onnx_threads_so_it_cannot_stall_the_voice_loop(), test_engine_refuses_when_models_are_missing_instead_of_letting_insightface_download() (+2 more)

### Community 83 - "build_system_blocks"
Cohesion: 0.09
Nodes (27): build_system_blocks(), build_system_prompt(), _dashboard_get_daily_items(), _fetch_projects(), get_active_facts_context(), get_projects_context(), get_skills_context(), get_user_profile_context() (+19 more)

### Community 84 - "create_reminder"
Cohesion: 0.50
Nodes (4): create_reminder(), _parse_due_at(), Accepts the ISO-ish formats a model is likely to produce ("2026-09-16 15:00",…, Schedules a reminder for an absolute time (due_at) or a delay from now…

### Community 85 - "RuntimeError"
Cohesion: 0.09
Nodes (32): _connect(), dashboard_state(), _data_dir(), _DataBlob, _db_path(), download_models(), _dpapi(), blob() (+24 more)

### Community 88 - "autonomy.js"
Cohesion: 0.56
Nodes (8): call(), card(), h(), loadLog(), logRow(), refresh(), render(), selectOf()

### Community 89 - "calibrate"
Cohesion: 0.08
Nodes (20): calibrate(), camera_index(), CameraUnavailable, _capture_and_analyze(), _get_engine(), _open_camera(), Dry run of the enrollment liveness check that stores NOTHING (no profile, no…, Signed head-turn proxy: nose offset from the eyes' midpoint, in eye-distances.… (+12 more)

### Community 90 - "_mail_answer"
Cohesion: 0.67
Nodes (3): _mail_answer(), test_a_clean_meeting_still_acts_at_high_confidence_and_structured_meeting_at_normal_floor(), test_wp1_subject_only_is_extracted_at_lower_confidence_and_logged()

### Community 92 - "jarvis_dashboard.py"
Cohesion: 0.17
Nodes (21): api_audit(), api_clear_finished_sessions(), api_state(), _build_state(), clear_finished_sessions(), _connect(), _db_path(), end_session() (+13 more)

### Community 93 - "add_commitment"
Cohesion: 0.14
Nodes (16): add_commitment(), _env_float(), _evaluate_base(), evaluate_policy(), _norm_dt(), _plausible_deadline(), A deadline the model guessed (audit C-03) can be far in the past or absurdly…, Validates and stores one extracted item; returns its new id, or None if it was… (+8 more)

### Community 94 - "enabled"
Cohesion: 0.07
Nodes (31): after_turn(), enabled(), extract_commitments_and_projects(), _fill(), _mark_seen(), memory_context(), process_inbound_async(), process_inbound_message_for_events() (+23 more)

### Community 95 - "test_guest_reminders.py"
Cohesion: 0.07
Nodes (55): answer(), configure(), has_open_question(), holding_reminders(), _norm(), on_stranger_arrived(), on_stranger_left(), parse_yes_no() (+47 more)

### Community 96 - "_Rec"
Cohesion: 0.10
Nodes (16): away(), fx(), jarvis(), fixture, quiet_jarvis(), Records lock / warning / stranger hook calls in order., _Rec, test_away_mode_tool_respects_the_source() (+8 more)

### Community 97 - "user_is_actively_working"
Cohesion: 0.50
Nodes (4): _get_idle_seconds(), Seconds since the last system-wide keyboard/mouse input, via GetLastInputInfo.…, True if the user touched the keyboard/mouse within ACTIVE_IDLE_THRESHOLD_S…, user_is_actively_working()

### Community 98 - "queue_or_deliver_notification"
Cohesion: 0.07
Nodes (43): _check_due_reminders(), _forward_held_reminders(), _get_active_window_title(), _get_last_skill_run(), _guess_project_from_window_title(), forward_reminder(), True after the owner said "no": reminders speak even with a stranger in view., Text a held reminder to the owner's phone (best effort; it stays queued either… (+35 more)

### Community 99 - "jarvis_focus.py"
Cohesion: 0.17
Nodes (19): classify_mood(), current_track(), disable(), enable(), _enabled_flag(), is_active(), Focus Mode, optionally triggered by the mood of what Spotify is playing. Mood…, Queue non-urgent notifications while Focus Mode is on; urgent ones always get… (+11 more)

### Community 100 - "_connect"
Cohesion: 0.25
Nodes (11): configure(), _connect(), _db_path(), init_autonomy_tables(), Connection, Path, Wire callbacks and arm the tick. jarvis.py's scheduler loop then calls…, Idempotent. Creates every table this module owns and seeds the single built-in… (+3 more)

### Community 102 - "start"
Cohesion: 0.67
Nodes (3): Blocking call — run this in its own daemon thread from jarvis.py's main().…, start(), _metrics_loop()

### Community 103 - "test_dashboard_llm_endpoints"
Cohesion: 0.50
Nodes (5): api_llm(), api_set_llm(), test_dashboard_llm_endpoints(), get_llm(), set_llm()

### Community 105 - "jarvis_roblox.py"
Cohesion: 0.20
Nodes (15): performance_flag(), Roblox Game Dev Companion: watches Roblox Studio and reviews Lua/Luau scripts.…, CPU/memory of running Roblox Studio processes, or None if it isn't running., Scheduler hook. Flags sustained load (3 checks in a row) and, once per changed…, Findings for one script's text, as 'name:line: suggestion'., review_folder(), review_source(), start() (+7 more)

### Community 106 - "_scheduler_callbacks"
Cohesion: 0.29
Nodes (7): Fake callbacks whose task queue is the REAL jarvis_task_scheduler (same…, _scheduler_callbacks(), test_c01_approved_background_task_is_scheduled_not_left_pending(), test_c01_campaign_step_gets_a_slot_and_a_stale_one_is_failed(), test_campaign_step_orphaned_in_running_after_a_restart_is_recovered(), test_e01_turning_off_cancels_queued_tasks(), test_wp6_campaign_statuses_planned_running_done_and_cancelled()

### Community 107 - "_set_broadcast"
Cohesion: 0.50
Nodes (4): _lifespan(), _do_broadcast(), _set_broadcast(), _broadcast()

### Community 108 - "_claude_request"
Cohesion: 0.14
Nodes (18): _build_sleep_digest(), _claude_request(), _claude_text(), _duckduckgo_search(), _has_cache_ttl(), Logs this response's token usage + estimated cost to the api_usage table…, Two-part recap: what mattered first (urgent things that came through live while…, Returns (spoken_reply, code_to_type_or_empty). The fix-typing half only fires… (+10 more)

### Community 109 - "_origin_is_loopback"
Cohesion: 0.67
Nodes (3): ws_endpoint(), _origin_is_loopback(), True if an Origin header names this machine. "null" (sandboxed iframes,…

### Community 112 - "_execute_tool_impl"
Cohesion: 0.17
Nodes (12): click_at(), _current_command_source(), drag_and_drop(), _execute_tool_impl(), focus_window(), _http_request_tool(), Runs one tool call and returns the text to feed back to Claude as its…, Where the command being run came from ("voice"/"text"/"dashboard"/"phone"), or… (+4 more)

### Community 115 - "_handle_text_command_impl"
Cohesion: 0.09
Nodes (26): _collapse_paths_for_speech(), _dashboard_approve_pending(), _sink(), notify(), _dashboard_reject_pending(), _execute_confirmed_action(), _face_release_held_notifications(), flush_pending_notifications() (+18 more)

### Community 118 - "jarvis_vibes.py"
Cohesion: 0.36
Nodes (8): decorate(), is_enabled(), pick_reaction(), datetime, Context-aware anime-style reactions for the *text* of a reply (dashboard,…, The reply with a reaction line appended, or unchanged when off / nothing fits., set_enabled(), test_vibes_off_by_default_and_text_only()

### Community 119 - "jarvis_voice_tone.py"
Cohesion: 0.32
Nodes (7): analyze_tone(), _lexical_scores(), _prosody(), Basic voice tone/sentiment awareness for Jarvis. Rule-based, deliberately…, Short line to fold into the agent system prompt for this turn; empty string if…, Returns {"tone": category, "confidence": 0..1, "signals": [short strings]}.…, tone_context_line()

### Community 120 - "fixture"
Cohesion: 0.29
Nodes (7): A(), client(), D(), fixture, S(), test_b_tool_and_dashboard_routes(), dash()

### Community 125 - "_session_locked"
Cohesion: 0.67
Nodes (3): True while the Windows lock screen (secure desktop) is up: the camera is off-…, _session_locked(), test_real_session_lock_probe_returns_a_bool_and_never_raises()

## Knowledge Gaps
- **89 isolated node(s):** `state`, `servicesPanel`, `servicesToggleBtn`, `IDENTITY_KIND_LABELS`, `Turn it on / off (and the emergency stop)` (+84 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 840 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_execute_tool_impl()` connect `_execute_tool_impl` to `jarvis_window_control.py`, `jarvis_sleep_mode.py`, `FileWatcher`, `jarvis.py`, `jarvis_memory_enhance.py`, `jarvis_billing.py`, `jarvis_workflow.py`, `jarvis_dynamic_tools.py`, `jarvis_proactive.py`, `jarvis_autonomy.py`, `execute_mcp_tool`, `speak_text`, `download_image`, `jarvis_autonomy_organise.py`, `Path`, `jarvis_task_scheduler.py`, `test_restart.py`, `run_agent_loop`, `poll_once`, `test_dev_features.py`, `resolve_write_path`, `jarvis_tech_understanding.py`, `is_paused`, `jarvis_face.py`, `jarvis_autonomy_skills.py`, `test_face.py`, `_memory_db_connect`, `build_system_blocks`, `create_reminder`, `test_guest_reminders.py`, `queue_or_deliver_notification`, `jarvis_focus.py`, `jarvis_roblox.py`, `_claude_request`, `_handle_text_command_impl`, `jarvis_vibes.py`?**
  _High betweenness centrality (0.097) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `_execute_tool_impl()` (e.g. with `_launch_focus_app()` and `_memory_db_connect()`) actually correct?**
  _`_execute_tool_impl()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 56 inferred relationships involving `timedelta` (e.g. with `_action_for_commitment()` and `agent_context_line()`) actually correct?**
  _`timedelta` has 56 INFERRED edges - model-reasoned connections that need verification._
- **What connects `state`, `servicesPanel`, `servicesToggleBtn` to the rest of the system?**
  _89 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `test_autonomy.py` be split into smaller, more focused modules?**
  _Cohesion score 0.025800286669851888 - nodes in this community are weakly interconnected._
- **Should `jarvis_window_control.py` be split into smaller, more focused modules?**
  _Cohesion score 0.14022988505747128 - nodes in this community are weakly interconnected._
- **Should `brag-output-2026-09-19-001152/composition/assets/gsap.min.js` be split into smaller, more focused modules?**
  _Cohesion score 0.06685633001422475 - nodes in this community are weakly interconnected._