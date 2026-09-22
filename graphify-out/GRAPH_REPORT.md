# Graph Report - jarvis-main2  (2026-09-22)

## Corpus Check
- 74 files · ~207,086 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 1, .vbs 1, .css 1)

## Summary
- 2973 nodes · 6515 edges · 132 communities (116 shown, 13 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 327 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ada33938`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_autonomy.py
- _execute_tool_impl
- brag-output-2026-09-19-001152/composition/assets/gsap.min.js
- jarvis_sleep_mode.py
- brag-output/composition/assets/gsap.min.js
- FileWatcher
- jarvis.py
- test_billing_summary_and_pagination
- jarvis_memory_enhance.py
- test_gemini.py
- test_sleep_mail.py
- RuntimeError
- jarvis_workflow.py
- Full Autonomy Stack
- jarvis_dynamic_tools.py
- Tween
- test_cache.py
- TTSDiskCache
- jarvis_proactive.py
- _iso
- identify
- queue_or_deliver_notification
- CLAUDE.md
- app.js
- _build_app
- _tools
- _delegate_to_claude_code
- test_dashboard.py
- Tween
- download_image
- jarvis_autonomy_organise.py
- Path
- _on
- _narrating_claude
- main
- TTLCache
- Brag Plan: Jarvis
- SqliteKV
- jarvis_task_scheduler.py
- test_billing_failures_are_plain_sentences
- ce
- _FakeProc
- ce
- jarvis_focus.py
- test_restart.py
- speak_text
- na
- na
- Hyperframes Composition Brief: Jarvis
- poll_once
- la
- la
- _call
- .__init__
- fb
- he
- Za
- Rd
- fb
- he
- Za
- Rd
- Brag Plan: Jarvis (chaotic cut)
- test_hardening.py
- jarvis_billing.py
- start_polling
- jarvis_tech_understanding.py
- transcribe
- _maybe_summarize
- _db
- Google Maps location sharing -> "where is <person>?" (2026-09-19)
- test_deepgram_voice.py
- jarvis_face.py
- jarvis_autonomy_skills.py
- test_face.py
- jarvis_memory_consolidation.py
- jarvis_roblox.py
- Fake
- download_models
- timedelta
- _load_skills
- boom
- dashboard_state
- _fake_mcp_run_coro
- jarvis_vibes.py
- autonomy.js
- calibrate
- _mail_answer
- jarvis_latency.py
- jarvis_dashboard.py
- add_commitment
- jarvis_autonomy.py
- test_guest_reminders.py
- is_paused
- synthesize
- StreamingSession
- Dashboard UI/UX overhaul (2026-09-22)
- _urlopen_hard_timeout
- snake.cpp
- start
- test_dashboard_llm_endpoints
- _ConnectionManager
- _scripted_claude
- _scheduler_callbacks
- _set_broadcast
- test_1h_ttl_rejection_falls_back_to_5m_and_retries
- _origin_is_loopback
- Speed Upgrade: Deepgram-native voice pipeline + cloud-latency pass
- snake.js
- build_calendar_args
- log_summary
- _speak_streamed
- _handle_text_command_impl
- _memory_db_connect
- test_short_notification_is_spoken_unchanged_without_a_claude_call
- CircuitBreaker
- test_wp5_a_skill_run_still_goes_through_the_execute_tool_gate
- fixture
- test_f_defaults_are_on_with_no_flags_needed
- StreamingSynthesis
- test_scheduled_skill_with_silent_flag_speaks_nothing_on_empty_reply
- test_shutdown_via_run_shell_is_staged_not_run
- test_dev_features.py
- _autonomy_callbacks
- _speak_session_stub
- _FakeOutputStream
- run_agent_loop
- test_a01_known_bypass_routes_are_rejected
- test_autonomy_code_cannot_reach_the_confirmation_gate

## God Nodes (most connected - your core abstractions)
1. `_execute_tool_impl()` - 118 edges
2. `Fake` - 103 edges
3. `_on()` - 60 edges
4. `_future()` - 55 edges
5. `_build_app()` - 51 edges
6. `main()` - 48 edges
7. `_iso()` - 47 edges
8. `_rows()` - 42 edges
9. `run_agent_loop()` - 36 edges
10. `_memory_db_connect()` - 35 edges

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

## Communities (132 total, 13 thin omitted)

### Community 0 - "test_autonomy.py"
Cohesion: 0.03
Nodes (30): skipif, _acted(), _file(), Tests for jarvis_autonomy.py, jarvis_dynamic_tools.py,…, The gate is untouched: an autonomous agent run that reaches a catastrophic…, test_b_a_file_still_downloading_is_retried_not_dropped(), test_b_a_symlink_that_leaves_the_folder_is_rejected(), test_b_default_rules_file_documents_images_and_spreadsheets() (+22 more)

### Community 1 - "_execute_tool_impl"
Cohesion: 0.11
Nodes (38): click_at(), drag_and_drop(), _execute_tool_impl(), focus_window(), Runs one tool call and returns the text to feed back to Claude as its…, scroll_screen(), guided_breathing_steps(), play_ambient() (+30 more)

### Community 2 - "brag-output-2026-09-19-001152/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 3 - "jarvis_sleep_mode.py"
Cohesion: 0.05
Nodes (72): _broadcast_theme_change(), _cancel_media_autopause(), _connect(), _dark_mode_is_on(), _db_path(), disable(), enable(), _endpoint_volume_call() (+64 more)

### Community 4 - "brag-output/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 5 - "FileWatcher"
Cohesion: 0.10
Nodes (15): add_watched_folder(), _connect(), _db_path(), _default_watch_paths(), FileWatcher, get_recent_file_events(), list_watched_folders(), Connection (+7 more)

### Community 6 - "jarvis.py"
Cohesion: 0.05
Nodes (68): _bytes_to_gb(), _bytes_to_mb(), check_system_health(), _choose_input_device(), _chrome_executable(), _craft_system_status_summary(), _cursor_executable(), _cursor_foreground_hwnd_win32() (+60 more)

### Community 8 - "jarvis_memory_enhance.py"
Cohesion: 0.13
Nodes (24): _connect(), _cosine(), _db_path(), link_facts(), list_code_patterns(), list_decisions(), Connection, Path (+16 more)

### Community 9 - "test_gemini.py"
Cohesion: 0.07
Nodes (48): call(), convert_messages(), convert_tools(), from_response(), get_provider(), Path, Request, Gemini (Google AI Studio) backend for Jarvis's LLM calls. Jarvis's callers all… (+40 more)

### Community 10 - "test_sleep_mail.py"
Cohesion: 0.05
Nodes (75): _autonomy_poll_mail(), New inbox messages (not the user's own, not yet seen by autonomy) with their…, _body_of(), _classify_critical(), _connect(), _db_path(), _emails(), _env_set() (+67 more)

### Community 11 - "RuntimeError"
Cohesion: 0.07
Nodes (28): RuntimeError, test_one_bad_item_does_not_lose_the_rest_of_the_batch(), test_tick_hands_slow_steps_to_bounded_workers_and_survives_a_failing_step(), test_record_usage_never_raises(), broken(), test_daily_endpoint_exception_does_not_break(), boom(), test_get_pending_exception_does_not_break_state() (+20 more)

### Community 12 - "jarvis_workflow.py"
Cohesion: 0.18
Nodes (18): _connect(), _db_path(), detect_stack(), get_workflow_status(), git_info(), Connection, Path, Workflow integration for Jarvis. Tracks which development workspace(s) the user… (+10 more)

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
Cohesion: 0.07
Nodes (7): _gate_env(), _kv_db(), Tests for the caching layers (jarvis_cache.py + their wiring in jarvis.py). Run…, test_busy_gate_holds_ordinary_notification_but_not_reminders(), test_bypass_busy_gate_still_respects_sleep_mode(), test_enabled_flag(), test_record_and_local_summary()

### Community 17 - "TTSDiskCache"
Cohesion: 0.29
Nodes (5): Path, WAV files under one directory, keyed by hash. LRU by mtime (touched on every…, TTSDiskCache, test_tts_cache_skips_synthesis_on_repeat(), test_tts_disk_cache_roundtrip_and_eviction()

### Community 18 - "jarvis_proactive.py"
Cohesion: 0.27
Nodes (12): check_project_health(), _connect(), _db_path(), _fmt_findings(), _iter_source_files(), Connection, Path, Proactive problem detection for Jarvis. Scans a file or project directory for… (+4 more)

### Community 19 - "_iso"
Cohesion: 0.12
Nodes (41): accept_commitment(), add_project_action(), approve_campaign(), approve_suggestion(), _commitment(), delete_policy(), dismiss_suggestion(), _exec() (+33 more)

### Community 20 - "identify"
Cohesion: 0.21
Nodes (15): _already_seen_recently(), _decrypt(), get_snapshot(), identify(), load_embeddings(), match_threshold(), _profiles_for_matching(), ndarray (+7 more)

### Community 21 - "queue_or_deliver_notification"
Cohesion: 0.06
Nodes (43): AbstractEventLoop, _autonomy_inbound(), _autonomy_mail_hook(), _check_due_reminders(), _ensure_mcp_loop(), _forward_held_reminders(), _get_active_window_title(), _get_last_skill_run() (+35 more)

### Community 22 - "CLAUDE.md"
Cohesion: 0.07
Nodes (26): API spend lookup (2026-09-18), Audit hardening (2026-09-21), Cloud-latency pass (2026-09-22), Confirmation gate follow-up (2026-09-18), Cost reporting, Dashboard (supervision UI), Face recognition (2026-09-19), Full Autonomy stack (2026-09-20) (+18 more)

### Community 23 - "app.js"
Cohesion: 0.08
Nodes (64): actOnPending(), AUTO_OPEN_SOURCES, badge(), connectWs(), coreHeatmap(), currentRoute(), esc(), fetchAuditResults() (+56 more)

### Community 24 - "_build_app"
Cohesion: 0.10
Nodes (36): _build_app(), api_autonomy(), api_autonomy_campaign_action(), api_autonomy_campaign_approve(), api_autonomy_commitment(), api_autonomy_commitment_accept(), api_autonomy_dry_run(), api_autonomy_enabled() (+28 more)

### Community 25 - "_tools"
Cohesion: 0.12
Nodes (14): test_c_skill_failure_stops_logs_the_step_and_notifies_exactly_once(), test_concurrent_extraction_of_the_same_item_inserts_it_once(), go(), test_d01_two_simultaneous_approvals_run_the_action_once(), go(), test_skill_creation_budget_holds_under_concurrency(), test_skills_never_mine_typing_http_or_secret_bearing_tools_or_huge_inputs(), test_wp5_cannot_smuggle_unknown_or_forbidden_tools_or_bad_shapes() (+6 more)

### Community 26 - "_delegate_to_claude_code"
Cohesion: 0.09
Nodes (29): _background_tasks_dir(), _catastrophic_reason(), _check_background_tasks(), _count_running_background_tasks(), _current_command_source(), notify(), _dashboard_reject_pending(), _delegate_child_env() (+21 more)

### Community 27 - "test_dashboard.py"
Cohesion: 0.06
Nodes (8): client(), dashboard(), db_path(), fixture, QA regression suite for jarvis_dashboard.py. Run with: python -m pytest…, Post-overhaul UX audit (2026-09-22): the Activity route's rows come from…, test_command_endpoint_invokes_run_command(), test_state_audit_rows_include_transcript_for_session_linking()

### Community 28 - "Tween"
Cohesion: 0.19
Nodes (21): _a(), Ao(), _assertThisInitialized(), cb(), cc(), ga(), gb(), hb() (+13 more)

### Community 29 - "download_image"
Cohesion: 0.10
Nodes (30): _contains_secret(), _http_request_tool(), _check_host(), _CheckedRedirects, _clean_stem(), download_image(), _fetch(), Path (+22 more)

### Community 30 - "jarvis_autonomy_organise.py"
Cohesion: 0.13
Nodes (37): add_root(), add_rule(), _copy_no_clobber(), handle_new_file(), handle_tool(), home(), _init(), _inside() (+29 more)

### Community 31 - "Path"
Cohesion: 0.11
Nodes (23): _dashboard_get_services_status(), _fmt_gb(), get_large_files_report(), _load_mcp_server_configs(), _mcp_servers_config_path(), _memory_db_path(), _own_code_context_line(), _print_large_files_breakdown() (+15 more)

### Community 32 - "_on"
Cohesion: 0.05
Nodes (62): _future(), _on(), FULL-PERMISSION MODEL: a confident, non-catastrophic item is acted on…, test_a_classifier_actions_influenced_by_inbound_mail_face_the_third_party_bar(), test_a_email_recipient_allowlist_is_optional_and_empty_means_unrestricted(), test_a_injected_email_at_medium_confidence_does_not_auto_act_and_says_why(), test_a_third_party_bar_matrix(), test_a_user_after_turn_still_auto_acts_at_the_normal_floor() (+54 more)

### Community 33 - "_narrating_claude"
Cohesion: 0.18
Nodes (8): _narrating_claude(), fake(), test_narrate_off_keeps_old_behaviour(), test_narrate_speaks_text_beside_a_tool_call_and_keeps_it_out_of_the_reply(), test_summary_cache_skips_second_claude_call(), test_tool_only_turn_falls_back_to_tool_result_by_default(), test_tool_result_fallback_can_be_disabled(), _tool_only_claude()

### Community 34 - "main"
Cohesion: 0.05
Nodes (48): _acquire_single_instance_lock(), _away_warn(), block_samples(), _dashboard_get_pending(), _dashboard_get_sleep(), _dashboard_kill_background_task(), api_key(), model_name() (+40 more)

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

### Community 43 - "jarvis_focus.py"
Cohesion: 0.18
Nodes (17): classify_mood(), current_track(), disable(), enable(), _enabled_flag(), is_active(), Focus Mode, optionally triggered by the mood of what Spotify is playing. Mood…, launch_app(name) opens a whitelisted app. Returns a plain-English summary. (+9 more)

### Community 44 - "test_restart.py"
Cohesion: 0.15
Nodes (18): check_syntax(), helper_command(), Event, Path, restart_jarvis: let Jarvis restart itself (voice: "restart yourself") to pick…, Error text for the first jarvis*.py that doesn't compile, else None., restart(), _stop_self() (+10 more)

### Community 45 - "speak_text"
Cohesion: 0.09
Nodes (32): enabled(), is_self_contained(), normalize_text(), Small, local-only cache helpers shared by jarvis.py: an env-flag reader,…, JARVIS_<LAYER>_CACHE env flag, default on. Read on every call so it can be…, Lowercase, punctuation-stripped, whitespace-collapsed — so 'System status?' and…, record(), stable_hash() (+24 more)

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
Cohesion: 0.09
Nodes (48): group_safe(), group_safe_suppress(), list_snapshots(), poll_once(), _Presence, One recognition cycle. Returns a short status word (used by tests and…, True while an unrecognized person is in view. Only ever used to hold *spoken…, One volatile-block line so the agent knows who is present. Personalization… (+40 more)

### Community 50 - "la"
Cohesion: 0.53
Nodes (6): Animation(), Da(), la(), ma(), Ua(), Va()

### Community 51 - "la"
Cohesion: 0.53
Nodes (6): Animation(), Da(), la(), ma(), Ua(), Va()

### Community 52 - "_call"
Cohesion: 0.09
Nodes (44): Any, _work(), _ask_model(), _audit(), budgets(), _call(), _campaign_step(), _clean() (+36 more)

### Community 53 - ".__init__"
Cohesion: 0.15
Nodes (11): Voice-bug audit pass (2026-09-22): a WebSocket frame boundary has no reason to…, Voice-bug pass (2026-09-22): an unbuffered OutputStream starves on uneven…, Voice-bug follow-up (2026-09-22): the first few chunks off a live WebSocket are…, test_play_pcm_stream_asks_portaudio_for_high_latency_buffering(), __init__(), test_play_pcm_stream_jitter_buffer_disabled_writes_each_chunk_immediately(), __init__(), test_play_pcm_stream_jitter_buffer_merges_leading_small_chunks_then_streams() (+3 more)

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

### Community 64 - "test_hardening.py"
Cohesion: 0.06
Nodes (40): _read_file_tool(), classify(), default_dir(), _inside(), Path, Jarvis_Workspace: the default home for every file Jarvis creates, saves or…, Where a file should be written. Returns (path, "") or (None, reason it was…, Absolute paths are used as given; a relative one is looked up in the workspace… (+32 more)

### Community 65 - "jarvis_billing.py"
Cohesion: 0.15
Nodes (19): compute_cost(), _dollars(), _ensure_usage_table(), fetch_cost_buckets(), format_local_summary(), get_api_spend(), local_summary(), Connection (+11 more)

### Community 66 - "start_polling"
Cohesion: 0.15
Nodes (13): _lower_thread_priority(), poll_interval(), Run the poll below normal priority so an inference burst yields to the voice…, Start the low-duty background poll (no-op unless JARVIS_FACE_ENABLED=1). The…, Once the owner has been steadily in view with nobody else, look less often…, settled_poll_interval(), start_polling(), loop() (+5 more)

### Community 67 - "jarvis_tech_understanding.py"
Cohesion: 0.13
Nodes (14): analyze_python_file(), build_import_graph(), format_analysis_report(), format_error_report(), _imports_of(), _module_name_for(), parse_error(), Path (+6 more)

### Community 68 - "transcribe"
Cohesion: 0.12
Nodes (16): ndarray, Request, Deepgram Nova-3 STT (Speed Upgrade Phase 1.1, streaming added in the cloud-…, Connection warm-up (Phase 2.2): a near-silent clip so the TLS handshake happens…, Hard-timeout watchdog: urlopen's own timeout doesn't reliably fire on a wedged…, transcribe(), _urlopen_bounded(), warm() (+8 more)

### Community 69 - "_maybe_summarize"
Cohesion: 0.09
Nodes (26): extract_commitments_and_projects(), _fill(), _mark_seen(), _maybe_summarize(), memory_context(), process_inbound_message_for_events(), Manual hook: runs the extraction prompt and returns the parsed, validated items…, Semantic recall over the exchange, so extraction sees what Jarvis already knows… (+18 more)

### Community 72 - "_db"
Cohesion: 0.13
Nodes (28): _db(), delete_all_snapshots(), _encrypt(), event_keep_days(), housekeeping(), invalidate_profile_cache(), _pack_embeddings(), prune_events() (+20 more)

### Community 73 - "Google Maps location sharing -> "where is <person>?" (2026-09-19)"
Cohesion: 0.25
Nodes (7): 1. Unofficial library (closest to the goal), 2. Telegram live location (official, stable), 3. Dedicated tracker (official, always-on), Before building, Google Maps location sharing -> "where is <person>?" (2026-09-19), Later, Recommendation

### Community 74 - "test_deepgram_voice.py"
Cohesion: 0.05
Nodes (26): _FakeSSEResponse, Tests for the Deepgram Speed Upgrade: jarvis_stt_deepgram.py,…, A background pre-synthesis that outlives PIPELINE_JOIN_TIMEOUT_S must not hang…, Voice-bug follow-up (2026-09-22): "Hi" and "thanks" answer with no Claude call…, Duck-types jarvis_stt_deepgram.StreamingSession's finish() surface for…, Voice-bug follow-up (2026-09-22): TTSDiskCache.get() has no integrity check on…, _sse_lines(), _sse_text_reply() (+18 more)

### Community 75 - "jarvis_face.py"
Cohesion: 0.07
Nodes (54): Exception, _already_enrolled(), away_enabled(), away_grace_s(), _away_reset(), away_status(), _away_step(), away_warn_s() (+46 more)

### Community 76 - "jarvis_autonomy_skills.py"
Cohesion: 0.17
Nodes (25): _connect(), _db_path(), init_autonomy_tables(), Connection, Path, Idempotent. Creates every table this module owns and seeds the single built-in…, _raw_connect(), create_skill() (+17 more)

### Community 77 - "test_face.py"
Cohesion: 0.07
Nodes (44): _clean_name(), delete(), delete_by_id(), enroll(), list_profiles(), Enroll a person. The first one becomes the Admin; later ones are `user`…, Remove a profile and its embeddings. The audit trail of events is kept (it…, _Cap (+36 more)

### Community 78 - "jarvis_memory_consolidation.py"
Cohesion: 0.28
Nodes (14): abstract_rules(), compress_old_summaries(), _connect(), consolidate(), _db_path(), _iso(), Connection, datetime (+6 more)

### Community 79 - "jarvis_roblox.py"
Cohesion: 0.18
Nodes (16): performance_flag(), Roblox Game Dev Companion: watches Roblox Studio and reviews Lua/Luau scripts.…, CPU/memory of running Roblox Studio processes, or None if it isn't running., Scheduler hook. Flags sustained load (3 checks in a row) and, once per changed…, Findings for one script's text, as 'name:line: suggestion'., review_folder(), review_source(), start() (+8 more)

### Community 80 - "Fake"
Cohesion: 0.09
Nodes (36): _capture(), _cb(), Fake, O(), Records callback traffic; `answers` maps a marker in the prompt to the JSON the…, test_a_classifier_context_is_framed(), test_a_conversation_extraction_of_tool_derived_text_is_framed(), test_a_inbound_prompt_is_framed_sanitised_and_length_capped() (+28 more)

### Community 81 - "download_models"
Cohesion: 0.10
Nodes (17): download_models(), _InsightEngine, _model_root(), models_ready(), Observation, fn(event_dict) is called after every audit row (kind/name/confidence/ts only)…, One-time fetch of the buffalo_l pack from insightface's GitHub release.…, set_event_hook() (+9 more)

### Community 82 - "timedelta"
Cohesion: 0.09
Nodes (41): _action_for_commitment(), agent_context_line(), _announce_pending(), _classifier_step(), _context_summary(), _deadline_scan(), _env_int(), explain() (+33 more)

### Community 83 - "_load_skills"
Cohesion: 0.25
Nodes (9): _dashboard_get_daily_items(), _load_skills(), Skills from disk, re-parsed only when a skills/*.json file was added, removed…, Reads every *.json skill file from the skills directory. A malformed file is…, Writes name/description/instructions (and optional schedule) as a new…, Read-only snapshot for the dashboard's own Daily section (recurring skills +…, _read_skills_from_disk(), save_skill() (+1 more)

### Community 84 - "boom"
Cohesion: 0.06
Nodes (19): The exact reported bug: saying "Hi" must produce a clean full reply, never the…, Audit scenario: round 0 streams narration + a tool_use (so the loop must…, Voice-bug pass (2026-09-22): the filler phrase ("One moment.") and short…, test_claude_stream_first_round_gemini_provider_no_ops(), test_claude_stream_first_round_network_failure_returns_none(), boom(), test_deterministic_reply_skips_run_agent_loop_entirely(), test_greeting_command_skips_run_agent_loop_and_never_spawns_filler() (+11 more)

### Community 85 - "dashboard_state"
Cohesion: 0.13
Nodes (23): _connect(), dashboard_state(), _data_dir(), _DataBlob, _db_path(), _dpapi(), blob(), event_kinds() (+15 more)

### Community 86 - "_fake_mcp_run_coro"
Cohesion: 0.32
Nodes (6): _fake_mcp_run_coro(), _FakeMcpResult, execute_mcp_tool always builds the real coroutine before calling _mcp_run_coro;…, test_calendar_invalid_grant_embedded_in_json_still_gets_the_hint(), test_gmail_invalid_grant_becomes_a_reauth_instruction(), test_other_mcp_errors_are_unaffected_by_the_auth_hint()

### Community 87 - "jarvis_vibes.py"
Cohesion: 0.36
Nodes (8): decorate(), is_enabled(), pick_reaction(), datetime, Context-aware anime-style reactions for the *text* of a reply (dashboard,…, The reply with a reaction line appended, or unchanged when off / nothing fits., set_enabled(), test_vibes_off_by_default_and_text_only()

### Community 88 - "autonomy.js"
Cohesion: 0.51
Nodes (9): call(), card(), cardFlag(), h(), loadLog(), logRow(), refresh(), render() (+1 more)

### Community 89 - "calibrate"
Cohesion: 0.12
Nodes (13): calibrate(), camera_index(), CameraUnavailable, _capture_and_analyze(), _get_engine(), _open_camera(), Open the camera, grab one frame, release it. Returns (observations, mean, std,…, Dry run of the enrollment liveness check that stores NOTHING (no profile, no… (+5 more)

### Community 90 - "_mail_answer"
Cohesion: 0.67
Nodes (3): _mail_answer(), test_a_clean_meeting_still_acts_at_high_confidence_and_structured_meeting_at_normal_floor(), test_wp1_subject_only_is_extracted_at_lower_confidence_and_logged()

### Community 91 - "jarvis_latency.py"
Cohesion: 0.13
Nodes (15): classify_intent(), current(), end(), Per-voice-command latency tracker (Speed Upgrade Phase 0). One VoiceLatency…, recent(), start(), VoiceLatency, parametrize (+7 more)

### Community 92 - "jarvis_dashboard.py"
Cohesion: 0.19
Nodes (20): api_audit(), api_clear_finished_sessions(), _build_state(), clear_finished_sessions(), _connect(), _db_path(), end_session(), _fetch_audit() (+12 more)

### Community 93 - "add_commitment"
Cohesion: 0.15
Nodes (14): add_commitment(), _env_float(), _evaluate_base(), evaluate_policy(), _norm_dt(), Validates and stores one extracted item; returns its new id, or None if it was…, Name <a@b.com>' -> 'a@b.com', lower-cased. A display name can say anything, so…, Exact address (audit E-02: substring matching let a lookalike or display name… (+6 more)

### Community 94 - "jarvis_autonomy.py"
Cohesion: 0.09
Nodes (38): after_turn(), _work(), _brief(), configure(), enabled(), _find_duplicate(), gate_reason(), _halt_pending_work() (+30 more)

### Community 95 - "test_guest_reminders.py"
Cohesion: 0.05
Nodes (65): answer(), configure(), forward_reminder(), has_open_question(), holding_reminders(), _norm(), on_stranger_arrived(), on_stranger_left() (+57 more)

### Community 96 - "is_paused"
Cohesion: 0.09
Nodes (22): is_paused(), jarvis(), parametrize, Goes through handle_text_command -> _execute_tool (not _execute_impl): also…, DNS-rebinding defence: a hostile page re-pointing its domain at 127.0.0.1 sends…, _snap(), test_away_mode_tool_respects_the_source(), turn() (+14 more)

### Community 97 - "synthesize"
Cohesion: 0.13
Nodes (14): Request, Deepgram Aura 2 TTS (Speed Upgrade Phase 1.2; WebSocket streaming added in the…, Same hard-timeout watchdog idiom as jarvis_stt_deepgram._urlopen_bounded —…, Connection warm-up (Phase 2.2): a tiny synth-and-discard so the first real…, synthesize(), _urlopen_bounded(), warm(), test_stt_timeout_error_falls_back_to_whisper() (+6 more)

### Community 98 - "StreamingSession"
Cohesion: 0.11
Nodes (18): One push-to-talk hold's live Deepgram Nova-3 WebSocket session. Usage (see…, Flushes and closes the session, returning (transcript, confidence) or None on…, StreamingSession, _FakeWebsocketLib, _FakeWS, Duck-types the websocket-client WebSocket object's send/recv/close surface., Mirrors jarvis.py's real usage: start() is kicked off on a helper thread and…, finish() called (almost) immediately after start() is kicked off on another… (+10 more)

### Community 99 - "Dashboard UI/UX overhaul (2026-09-22)"
Cohesion: 0.18
Nodes (10): Confirmation / approval path — unchanged, Dashboard UI/UX overhaul (2026-09-22), Home (mission control), How to preview without running full Jarvis, Keyboard, Layout, Post-overhaul UX pass (2026-09-22), Routes (+2 more)

### Community 100 - "_urlopen_hard_timeout"
Cohesion: 0.33
Nodes (5): _fish_audio_synthesize(), Request, urlopen(timeout=...) is supposed to bound the whole call, but a wedged TLS…, Calls Fish Audio's TTS REST API and returns (pcm_int16_bytes, sample_rate) —…, _urlopen_hard_timeout()

### Community 101 - "snake.cpp"
Cohesion: 0.53
Nodes (8): deque, draw(), main(), newFood(), onSnake(), Pt, x, y

### Community 102 - "start"
Cohesion: 0.67
Nodes (3): Blocking call — run this in its own daemon thread from jarvis.py's main().…, start(), _metrics_loop()

### Community 103 - "test_dashboard_llm_endpoints"
Cohesion: 0.50
Nodes (5): api_llm(), api_set_llm(), test_dashboard_llm_endpoints(), get_llm(), set_llm()

### Community 105 - "_scripted_claude"
Cohesion: 0.33
Nodes (6): Fake Claude: with a tool_name, the first call requests it and the next returns…, _scripted_claude(), test_reply_cache_disabled_by_env(), test_reply_cache_never_stores_mutating_turns(), test_reply_cache_serves_readonly_repeat_without_claude(), test_reply_cache_skips_context_dependent_and_toolless_turns()

### Community 106 - "_scheduler_callbacks"
Cohesion: 0.29
Nodes (7): Fake callbacks whose task queue is the REAL jarvis_task_scheduler (same…, _scheduler_callbacks(), test_c01_approved_background_task_is_scheduled_not_left_pending(), test_c01_campaign_step_gets_a_slot_and_a_stale_one_is_failed(), test_campaign_step_orphaned_in_running_after_a_restart_is_recovered(), test_e01_turning_off_cancels_queued_tasks(), test_wp6_campaign_statuses_planned_running_done_and_cancelled()

### Community 107 - "_set_broadcast"
Cohesion: 0.50
Nodes (4): _lifespan(), _do_broadcast(), _set_broadcast(), _broadcast()

### Community 109 - "_origin_is_loopback"
Cohesion: 0.40
Nodes (5): _loopback_only(), ws_endpoint(), _host_is_loopback(), _origin_is_loopback(), True if an Origin header names this machine. "null" (sandboxed iframes,…

### Community 110 - "Speed Upgrade: Deepgram-native voice pipeline + cloud-latency pass"
Cohesion: 0.08
Nodes (23): Architecture, Audit-and-fix pass (2026-09-22), Backend order, Cloud-latency pass (2026-09-22): streaming STT/TTS, simple-intent fast path, LLM token streaming, Env vars, Filler phrase (Phase 3.2), How to measure a real before/after, Latency measurement (+15 more)

### Community 111 - "snake.js"
Cohesion: 0.28
Nodes (7): canvas, ctx, KEYS, placeFood(), reset(), scoreEl, step()

### Community 113 - "log_summary"
Cohesion: 0.50
Nodes (4): log_summary(), Human-readable 'what did autonomy do' (acts first, with counts)., Speaks the summary (shortened for speech by jarvis.py's _speak_shaped) and…, speak_log()

### Community 114 - "_speak_streamed"
Cohesion: 0.33
Nodes (4): _play_pcm_stream(), Attempts Deepgram's streaming speak WebSocket for `text`, playing audio as it's…, Plays int16 PCM chunks as they're produced by an iterable (a live WebSocket…, _speak_streamed()

### Community 115 - "_handle_text_command_impl"
Cohesion: 0.05
Nodes (39): _build_sleep_digest(), _collapse_paths_for_speech(), _dashboard_approve_pending(), _sink(), _deterministic_intent_reply(), _execute_confirmed_action(), _face_release_held_notifications(), flush_pending_notifications() (+31 more)

### Community 116 - "_memory_db_connect"
Cohesion: 0.06
Nodes (42): _append_history(), _apply_memory_db_pragmas(), build_system_blocks(), build_system_prompt(), cancel_reminder(), _create_memory_tables(), _dashboard_get_usage(), _fetch_projects() (+34 more)

### Community 118 - "CircuitBreaker"
Cohesion: 0.17
Nodes (8): CircuitBreaker, Trips after `threshold` consecutive failures and refuses calls for…, jarvis(), fixture, test_circuit_breaker_success_resets_failures(), test_circuit_breaker_trips_and_cools_down(), test_stt_backend_recovers_after_breaker_cooldown(), flaky()

### Community 120 - "fixture"
Cohesion: 0.29
Nodes (7): A(), client(), D(), fixture, S(), test_b_tool_and_dashboard_routes(), dash()

### Community 122 - "StreamingSynthesis"
Cohesion: 0.13
Nodes (11): One request to Deepgram's streaming speak WebSocket. Usage: session =…, Generator yielding raw int16 PCM bytes as Aura 2 generates them. Text…, StreamingSynthesis, _FakeSpeakWebsocketLib, _FakeSpeakWS, create_connection(), test_streaming_synthesis_chunks_yields_only_binary_frames(), test_streaming_synthesis_connect_failure_returns_false() (+3 more)

### Community 125 - "test_dev_features.py"
Cohesion: 0.21
Nodes (16): analyze_repo(), _existing_tests(), generate_tests(), _public_api(), _py_files(), Path, Repository analysis, unit-test generation and module boilerplate. Deterministic…, New `<name>.py` plus a matching test file, in the style the repo already uses. (+8 more)

### Community 129 - "_autonomy_callbacks"
Cohesion: 0.08
Nodes (29): _autonomy_calendar_events(), _autonomy_callbacks(), _autonomy_create_event(), _autonomy_run_agent(), _commands_in_flight(), create_reminder(), execute_mcp_tool(), _execute_tool() (+21 more)

### Community 131 - "_speak_session_stub"
Cohesion: 0.14
Nodes (11): Duck-types tts_deepgram.StreamingSynthesis for _speak_streamed tests:…, Real audio already played before the interruption — must be reported as handled…, The critical Phase B safety property: the background pre-fetch thread for the…, _speak_session_stub(), test_speak_streamed_failure_before_any_audio_is_not_handled(), test_speak_streamed_happy_path(), test_speak_streamed_mid_stream_failure_after_audio_is_handled_but_incomplete(), test_speak_text_caches_complete_streamed_audio_for_reuse() (+3 more)

### Community 139 - "run_agent_loop"
Cohesion: 0.06
Nodes (46): HTMLParser, _cached_tools(), _claude_request(), _claude_stream_first_round(), _speak_ready(), _claude_text(), _duckduckgo_search(), _DuckDuckGoResultParser (+38 more)

## Knowledge Gaps
- **131 isolated node(s):** `state`, `ROUTES`, `ROUTES_WITH_CONTEXT`, `servicesPanel`, `servicesToggleBtn` (+126 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1047 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_execute_tool_impl()` connect `_execute_tool_impl` to `_autonomy_callbacks`, `jarvis_sleep_mode.py`, `FileWatcher`, `jarvis.py`, `jarvis_memory_enhance.py`, `run_agent_loop`, `jarvis_workflow.py`, `jarvis_dynamic_tools.py`, `jarvis_proactive.py`, `_iso`, `queue_or_deliver_notification`, `_delegate_to_claude_code`, `download_image`, `jarvis_autonomy_organise.py`, `Path`, `main`, `jarvis_task_scheduler.py`, `jarvis_focus.py`, `test_restart.py`, `speak_text`, `test_hardening.py`, `jarvis_billing.py`, `jarvis_tech_understanding.py`, `_db`, `jarvis_face.py`, `jarvis_autonomy_skills.py`, `test_face.py`, `jarvis_roblox.py`, `_load_skills`, `jarvis_vibes.py`, `test_guest_reminders.py`, `is_paused`, `_handle_text_command_impl`, `_memory_db_connect`, `test_dev_features.py`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Why does `_build_app()` connect `_build_app` to `start`, `test_dashboard_llm_endpoints`, `_ConnectionManager`, `_set_broadcast`, `_origin_is_loopback`, `jarvis_dashboard.py`?**
  _High betweenness centrality (0.037) - this node is a cross-community bridge._
- **Why does `j()` connect `test_guest_reminders.py` to `is_paused`, `test_hardening.py`, `jarvis_sleep_mode.py`, `_FakeProc`, `test_gemini.py`, `test_sleep_mail.py`, `CircuitBreaker`?**
  _High betweenness centrality (0.018) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `_execute_tool_impl()` (e.g. with `_launch_focus_app()` and `_memory_db_connect()`) actually correct?**
  _`_execute_tool_impl()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 58 inferred relationships involving `timedelta` (e.g. with `_action_for_commitment()` and `agent_context_line()`) actually correct?**
  _`timedelta` has 58 INFERRED edges - model-reasoned connections that need verification._
- **What connects `state`, `ROUTES`, `ROUTES_WITH_CONTEXT` to the rest of the system?**
  _131 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `test_autonomy.py` be split into smaller, more focused modules?**
  _Cohesion score 0.025479195885928004 - nodes in this community are weakly interconnected._