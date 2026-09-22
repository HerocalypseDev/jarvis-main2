# Graph Report - jarvis-main2  (2026-09-22)

## Corpus Check
- 74 files · ~203,684 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 1, .vbs 1, .css 1)

## Summary
- 2952 nodes · 6475 edges · 145 communities (130 shown, 12 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 326 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c942ae7d`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_autonomy.py
- _execute_tool_impl
- brag-output-2026-09-19-001152/composition/assets/gsap.min.js
- test_sleep.py
- brag-output/composition/assets/gsap.min.js
- FileWatcher
- jarvis.py
- test_billing_summary_and_pagination
- jarvis_memory_enhance.py
- test_gemini.py
- _iso
- dry_run
- jarvis_workflow.py
- Full Autonomy Stack
- jarvis_dynamic_tools.py
- Tween
- test_cache.py
- TTSDiskCache
- jarvis_proactive.py
- jarvis_autonomy.py
- enable
- ensure_mcp_started
- CLAUDE.md
- app.js
- _build_app
- _tools
- jarvis_sleep_mode.py
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
- jarvis
- ce
- test_sleep_mail.py
- test_restart.py
- run_agent_loop
- na
- na
- Hyperframes Composition Brief: Jarvis
- test_face.py
- la
- la
- neutralize_injection
- jarvis_sleep_mail.py
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
- timedelta
- is_paused
- Google Maps location sharing -> "where is <person>?" (2026-09-19)
- test_deepgram_voice.py
- jarvis_face.py
- jarvis_autonomy_skills.py
- enroll
- jarvis_memory_consolidation.py
- is_active
- Fake
- test_engine_refuses_when_models_are_missing_instead_of_letting_insightface_download
- build_calendar_args
- build_system_prompt
- boom
- RuntimeError
- test_own_signature_is_skipped_but_quoted_signature_is_not
- queue_or_deliver_notification
- autonomy.js
- calibrate
- _mail_answer
- jarvis_latency.py
- jarvis_dashboard.py
- _evaluate_base
- enabled
- state
- jarvis
- synthesize
- StreamingSession
- Dashboard UI/UX overhaul (2026-09-22)
- _connect
- snake.cpp
- start
- test_dashboard_llm_endpoints
- _ConnectionManager
- stats_summary
- _scheduler_callbacks
- _set_broadcast
- _speak_shaped
- _origin_is_loopback
- Speed Upgrade: Deepgram-native voice pipeline + cloud-latency pass
- snake.js
- _StubSession
- jarvis_cache.py
- _set_dark_mode
- speak_text
- _memory_db_connect
- test_short_notification_is_spoken_unchanged_without_a_claude_call
- CircuitBreaker
- jarvis_voice_tone.py
- fixture
- _claude_stream_first_round
- StreamingSynthesis
- test_scheduled_skill_with_silent_flag_speaks_nothing_on_empty_reply
- _scripted_claude
- test_dev_features.py
- test_guest_reminders.py
- _DuckDuckGoResultParser
- send_with_retry
- _handle_family
- _handle_text_command_impl
- _speak_session_stub
- test_run_agent_loop_multi_round_streams_narration_then_speaks_final_reply_once
- _FakeSSEResponse
- jarvis_guest_reminders.py
- j
- Snake
- test_record_usage_never_raises
- _FakeOutputStream
- _urlopen_hard_timeout
- jarvis
- test_a01_known_bypass_routes_are_rejected
- test_catastrophic_actions_still_require_confirmation_even_when_autonomy_runs_them
- test_autonomy_code_cannot_reach_the_confirmation_gate
- test_g02_worker_threads_are_bounded_and_extras_dropped

## God Nodes (most connected - your core abstractions)
1. `_execute_tool_impl()` - 118 edges
2. `Fake` - 102 edges
3. `_on()` - 59 edges
4. `_future()` - 55 edges
5. `_build_app()` - 51 edges
6. `main()` - 48 edges
7. `_iso()` - 46 edges
8. `_rows()` - 41 edges
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

## Communities (145 total, 12 thin omitted)

### Community 0 - "test_autonomy.py"
Cohesion: 0.03
Nodes (31): skipif, _acted(), _file(), Tests for jarvis_autonomy.py, jarvis_dynamic_tools.py,…, jarvis.py wires run_tool to _execute_tool, so a skill step naming run_shell…, Autonomy on => injection hardening, the third-party bar and file organising are…, test_b_a_file_still_downloading_is_retried_not_dropped(), test_b_a_symlink_that_leaves_the_folder_is_rejected() (+23 more)

### Community 1 - "_execute_tool_impl"
Cohesion: 0.10
Nodes (42): click_at(), drag_and_drop(), _execute_tool_impl(), focus_window(), list_background_tasks(), list_reminders(), quick_recall(), Synthesizes 'where we left off': tracked projects and their next steps,… (+34 more)

### Community 2 - "brag-output-2026-09-19-001152/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 3 - "test_sleep.py"
Cohesion: 0.10
Nodes (12): db(), jarvis(), fixture, Tests for sleep trend stats and the wake-up digest. Run with: python -m pytest…, A .env setting read at import time (sleep goal) must reach the modules…, test_digest_important_first_then_lighter_note(), test_disable_logs_duration_to_memory_only_when_long_enough(), run() (+4 more)

### Community 4 - "brag-output/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 5 - "FileWatcher"
Cohesion: 0.10
Nodes (15): add_watched_folder(), _connect(), _db_path(), _default_watch_paths(), FileWatcher, get_recent_file_events(), list_watched_folders(), Connection (+7 more)

### Community 6 - "jarvis.py"
Cohesion: 0.04
Nodes (73): _bytes_to_gb(), _bytes_to_mb(), check_system_health(), _choose_input_device(), _chrome_executable(), _craft_system_status_summary(), _cursor_executable(), _cursor_foreground_hwnd_win32() (+65 more)

### Community 8 - "jarvis_memory_enhance.py"
Cohesion: 0.13
Nodes (22): _connect(), _cosine(), _db_path(), link_facts(), list_code_patterns(), list_decisions(), Connection, Path (+14 more)

### Community 9 - "test_gemini.py"
Cohesion: 0.07
Nodes (48): call(), convert_messages(), convert_tools(), from_response(), get_provider(), Path, Request, Gemini (Google AI Studio) backend for Jarvis's LLM calls. Jarvis's callers all… (+40 more)

### Community 10 - "_iso"
Cohesion: 0.13
Nodes (21): approve_suggestion(), _exec_rc(), _finish_suggestion(), _insert_commitment(), _iso(), _mark_seen(), _merge_into(), process_inbound_message_for_events() (+13 more)

### Community 11 - "dry_run"
Cohesion: 0.25
Nodes (14): accept_commitment(), _action_for_commitment(), _commitment(), _deadline_scan(), dry_run(), _ingest(), _meta(), The one concrete action a stored commitment implies, or (None, {}) if it is… (+6 more)

### Community 12 - "jarvis_workflow.py"
Cohesion: 0.16
Nodes (20): _connect(), _db_path(), detect_stack(), get_context_summary(), get_workflow_status(), git_info(), Connection, Path (+12 more)

### Community 13 - "Full Autonomy Stack"
Cohesion: 0.05
Nodes (38): Audit-and-fix pass (2026-09-20, after the full-permission change), Audit pass 2 (after injection hardening + file organising): what changed because of real bugs, Calendar and skills (small hardening), Dynamic tools, File organising (ON by default whenever autonomy is on), Full Autonomy Stack, How the tick works, How to verify (do this before trusting it) (+30 more)

### Community 14 - "jarvis_dynamic_tools.py"
Cohesion: 0.06
Nodes (58): find_dm_with_user(), list_dm_channels(), list_servers(), on_ready(), Custom MCP server wrapping discord.py-self to let Jarvis act as the user's own…, Lists the Discord servers (guilds) this account is a member of, with their IDs., Lists currently open DM conversations, with their channel IDs., Finds a DM channel ID by matching a username against currently open DM… (+50 more)

### Community 15 - "Tween"
Cohesion: 0.19
Nodes (21): _a(), Ao(), _assertThisInitialized(), cb(), cc(), ga(), gb(), hb() (+13 more)

### Community 16 - "test_cache.py"
Cohesion: 0.06
Nodes (8): _gate_env(), _kv_db(), Tests for the caching layers (jarvis_cache.py + their wiring in jarvis.py). Run…, test_1h_ttl_rejection_falls_back_to_5m_and_retries(), test_busy_gate_holds_ordinary_notification_but_not_reminders(), test_bypass_busy_gate_still_respects_sleep_mode(), test_record_and_local_summary(), test_shutdown_via_run_shell_is_staged_not_run()

### Community 17 - "TTSDiskCache"
Cohesion: 0.29
Nodes (5): Path, WAV files under one directory, keyed by hash. LRU by mtime (touched on every…, TTSDiskCache, test_tts_cache_skips_synthesis_on_repeat(), test_tts_disk_cache_roundtrip_and_eviction()

### Community 18 - "jarvis_proactive.py"
Cohesion: 0.27
Nodes (12): check_project_health(), _connect(), _db_path(), _fmt_findings(), _iter_source_files(), Connection, Path, Proactive problem detection for Jarvis. Scans a file or project directory for… (+4 more)

### Community 19 - "jarvis_autonomy.py"
Cohesion: 0.09
Nodes (46): add_project_action(), agent_context_line(), approve_campaign(), _brief(), budgets(), delete_policy(), dismiss_suggestion(), explain() (+38 more)

### Community 20 - "enable"
Cohesion: 0.24
Nodes (18): disable(), enable(), _get_state(), kind='nap' runs the exact same mode (quiet notifications, mail take-over, dark…, _set_state(), set_system_action_handler(), _set_volume(), toggle() (+10 more)

### Community 21 - "ensure_mcp_started"
Cohesion: 0.07
Nodes (27): AbstractEventLoop, _autonomy_create_event(), _autonomy_inbound(), _autonomy_mail_hook(), _ensure_mcp_loop(), ensure_mcp_started(), execute_mcp_tool(), _mcp_call_tool_async() (+19 more)

### Community 22 - "CLAUDE.md"
Cohesion: 0.08
Nodes (25): API spend lookup (2026-09-18), Audit hardening (2026-09-21), Cloud-latency pass (2026-09-22), Confirmation gate follow-up (2026-09-18), Cost reporting, Dashboard (supervision UI), Face recognition (2026-09-19), Full Autonomy stack (2026-09-20) (+17 more)

### Community 23 - "app.js"
Cohesion: 0.08
Nodes (64): actOnPending(), AUTO_OPEN_SOURCES, badge(), connectWs(), coreHeatmap(), currentRoute(), esc(), fetchAuditResults() (+56 more)

### Community 24 - "_build_app"
Cohesion: 0.11
Nodes (33): _build_app(), api_autonomy(), api_autonomy_campaign_action(), api_autonomy_campaign_approve(), api_autonomy_commitment(), api_autonomy_commitment_accept(), api_autonomy_dry_run(), api_autonomy_enabled() (+25 more)

### Community 25 - "_tools"
Cohesion: 0.12
Nodes (14): test_c_skill_failure_stops_logs_the_step_and_notifies_exactly_once(), test_concurrent_extraction_of_the_same_item_inserts_it_once(), go(), test_d01_two_simultaneous_approvals_run_the_action_once(), go(), test_skill_creation_budget_holds_under_concurrency(), test_skills_never_mine_typing_http_or_secret_bearing_tools_or_huge_inputs(), test_wp5_cannot_smuggle_unknown_or_forbidden_tools_or_bad_shapes() (+6 more)

### Community 26 - "jarvis_sleep_mode.py"
Cohesion: 0.11
Nodes (20): _cancel_media_autopause(), _dark_mode_is_on(), _db_path(), _endpoint_volume_call(), _get_volume(), _hhmm(), is_whitelisted_sender(), _log_duration_to_memory() (+12 more)

### Community 27 - "test_dashboard.py"
Cohesion: 0.05
Nodes (20): client(), dashboard(), db_path(), fixture, QA regression suite for jarvis_dashboard.py. Run with: python -m pytest…, Post-overhaul UX audit (2026-09-22): the Activity route's rows come from…, test_command_endpoint_invokes_run_command(), test_daily_endpoint_exception_does_not_break() (+12 more)

### Community 28 - "Tween"
Cohesion: 0.19
Nodes (21): _a(), Ao(), _assertThisInitialized(), cb(), cc(), ga(), gb(), hb() (+13 more)

### Community 29 - "download_image"
Cohesion: 0.10
Nodes (30): _contains_secret(), _http_request_tool(), _check_host(), _CheckedRedirects, _clean_stem(), download_image(), _fetch(), Path (+22 more)

### Community 30 - "jarvis_autonomy_organise.py"
Cohesion: 0.13
Nodes (36): add_root(), add_rule(), _copy_no_clobber(), handle_new_file(), handle_tool(), home(), _init(), _inside() (+28 more)

### Community 31 - "Path"
Cohesion: 0.11
Nodes (23): _dashboard_get_services_status(), _fmt_gb(), get_large_files_report(), _load_mcp_server_configs(), _mcp_servers_config_path(), _memory_db_path(), _own_code_context_line(), _print_large_files_breakdown() (+15 more)

### Community 32 - "_on"
Cohesion: 0.05
Nodes (63): _future(), _on(), FULL-PERMISSION MODEL: a confident, non-catastrophic item is acted on…, test_a_classifier_actions_influenced_by_inbound_mail_face_the_third_party_bar(), test_a_email_recipient_allowlist_is_optional_and_empty_means_unrestricted(), test_a_injected_email_at_medium_confidence_does_not_auto_act_and_says_why(), test_a_third_party_bar_matrix(), test_a_user_after_turn_still_auto_acts_at_the_normal_floor() (+55 more)

### Community 33 - "_narrating_claude"
Cohesion: 0.18
Nodes (8): _narrating_claude(), fake(), test_narrate_off_keeps_old_behaviour(), test_narrate_speaks_text_beside_a_tool_call_and_keeps_it_out_of_the_reply(), test_summary_cache_skips_second_claude_call(), test_tool_only_turn_falls_back_to_tool_result_by_default(), test_tool_result_fallback_can_be_disabled(), _tool_only_claude()

### Community 34 - "main"
Cohesion: 0.05
Nodes (48): _acquire_single_instance_lock(), block_samples(), _dashboard_get_pending(), _dashboard_get_sleep(), _dashboard_kill_background_task(), _face_release_held_notifications(), api_key(), model_name() (+40 more)

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

### Community 41 - "jarvis"
Cohesion: 0.22
Nodes (7): reset_stats(), delegation(), _FakeProc, jarvis(), fixture, jarvis(), fixture

### Community 42 - "ce"
Cohesion: 0.24
Nodes (14): Ae(), ce(), $d(), ee(), ha(), ka(), le(), me() (+6 more)

### Community 43 - "test_sleep_mail.py"
Cohesion: 0.18
Nodes (19): AttGmail, FakeGmail, Tests for the Sleep Mode mail take-over. Run: python -m pytest…, Writes the 'downloaded' file where the real tool would., _run(), _search(), test_family_email_gets_reply_recorded_and_not_repeated(), test_family_reply_with_attachment_sends_blocks_to_model() (+11 more)

### Community 44 - "test_restart.py"
Cohesion: 0.15
Nodes (18): check_syntax(), helper_command(), Event, Path, restart_jarvis: let Jarvis restart itself (voice: "restart yourself") to pick…, Error text for the first jarvis*.py that doesn't compile, else None., restart(), _stop_self() (+10 more)

### Community 45 - "run_agent_loop"
Cohesion: 0.06
Nodes (55): _autonomy_calendar_events(), _autonomy_callbacks(), _autonomy_run_agent(), build_system_blocks(), enabled(), JARVIS_<LAYER>_CACHE env flag, default on. Read on every call so it can be…, record(), stable_hash() (+47 more)

### Community 46 - "na"
Cohesion: 0.29
Nodes (6): Aa(), Ca(), na(), Vb(), wb(), Xb()

### Community 47 - "na"
Cohesion: 0.29
Nodes (6): Aa(), Ca(), na(), Vb(), wb(), Xb()

### Community 48 - "Hyperframes Composition Brief: Jarvis"
Cohesion: 0.25
Nodes (7): Audio, Creative Direction, Hyperframes Composition Brief: Jarvis, Objective, Output, Source Material, Visual Identity

### Community 49 - "test_face.py"
Cohesion: 0.07
Nodes (59): describe_presence(), enabled(), _fresh(), group_safe(), group_safe_suppress(), list_snapshots(), poll_once(), _Presence (+51 more)

### Community 50 - "la"
Cohesion: 0.53
Nodes (6): Animation(), Da(), la(), ma(), Ua(), Va()

### Community 51 - "la"
Cohesion: 0.53
Nodes (6): Animation(), Da(), la(), ma(), Ua(), Va()

### Community 52 - "neutralize_injection"
Cohesion: 0.09
Nodes (32): add_commitment(), _clean(), create_suggestion(), _execute_auto(), _file_scan_locked(), memory_context(), _norm_dt(), _notify_throttled() (+24 more)

### Community 53 - "jarvis_sleep_mail.py"
Cohesion: 0.18
Nodes (20): _classify_critical(), _connect(), _emails(), _env_set(), _handled(), _label(), load_family(), _mark() (+12 more)

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
Cohesion: 0.14
Nodes (20): compute_cost(), _dollars(), _ensure_usage_table(), fetch_cost_buckets(), format_local_summary(), get_api_spend(), local_summary(), Connection (+12 more)

### Community 66 - "start_polling"
Cohesion: 0.15
Nodes (13): _lower_thread_priority(), poll_interval(), Run the poll below normal priority so an inference burst yields to the voice…, Start the low-duty background poll (no-op unless JARVIS_FACE_ENABLED=1). The…, Once the owner has been steadily in view with nobody else, look less often…, settled_poll_interval(), start_polling(), loop() (+5 more)

### Community 67 - "jarvis_tech_understanding.py"
Cohesion: 0.13
Nodes (14): analyze_python_file(), build_import_graph(), format_analysis_report(), format_error_report(), _imports_of(), _module_name_for(), parse_error(), Path (+6 more)

### Community 68 - "transcribe"
Cohesion: 0.12
Nodes (15): ndarray, Request, Deepgram Nova-3 STT (Speed Upgrade Phase 1.1, streaming added in the cloud-…, Connection warm-up (Phase 2.2): a near-silent clip so the TLS handshake happens…, Hard-timeout watchdog: urlopen's own timeout doesn't reliably fire on a wedged…, transcribe(), _urlopen_bounded(), warm() (+7 more)

### Community 69 - "timedelta"
Cohesion: 0.08
Nodes (58): Any, _announce_pending(), _ask_model(), _audit(), _call(), _campaign_step(), _classifier_step(), _context_summary() (+50 more)

### Community 72 - "is_paused"
Cohesion: 0.10
Nodes (28): away_enabled(), away_status(), get_setting(), _greeting_text(), invalidate_profile_cache(), is_paused(), _maybe_greet(), Camera privacy switch. Pausing is always allowed (it can only make things more… (+20 more)

### Community 73 - "Google Maps location sharing -> "where is <person>?" (2026-09-19)"
Cohesion: 0.25
Nodes (7): 1. Unofficial library (closest to the goal), 2. Telegram live location (official, stable), 3. Dedicated tracker (official, always-on), Before building, Google Maps location sharing -> "where is <person>?" (2026-09-19), Later, Recommendation

### Community 74 - "test_deepgram_voice.py"
Cohesion: 0.06
Nodes (13): Tests for the Deepgram Speed Upgrade: jarvis_stt_deepgram.py,…, Simulates run_agent_loop narrating (via speak_text, on the same thread) before…, A background pre-synthesis that outlives PIPELINE_JOIN_TIMEOUT_S must not hang…, test_complex_command_gets_full_tools(), test_filler_skipped_when_narration_already_spoke(), test_pipeline_join_timeout_recovers_without_hanging_or_dropping_content(), test_speak_signal_is_per_thread(), test_speak_streamed_connect_failure_is_not_handled() (+5 more)

### Community 75 - "jarvis_face.py"
Cohesion: 0.05
Nodes (78): Exception, _already_enrolled(), _already_seen_recently(), away_grace_s(), _away_reset(), _away_step(), away_warn_s(), _camera_failed() (+70 more)

### Community 76 - "jarvis_autonomy_skills.py"
Cohesion: 0.25
Nodes (18): create_skill(), handle_tool(), _init(), _known(), list_skills(), note_turn(), _q(), Composable, side-effect-safe skills for the autonomy layer. A skill is a NAMED,… (+10 more)

### Community 77 - "enroll"
Cohesion: 0.10
Nodes (36): _clean_name(), delete(), delete_by_id(), describe_profiles(), enroll(), list_profiles(), (role, None) to enroll with, or (None, reason). The first person is always the…, Enroll a person. The first one becomes the Admin; later ones are `user`… (+28 more)

### Community 78 - "jarvis_memory_consolidation.py"
Cohesion: 0.28
Nodes (14): abstract_rules(), compress_old_summaries(), _connect(), consolidate(), _db_path(), _iso(), Connection, datetime (+6 more)

### Community 79 - "is_active"
Cohesion: 0.29
Nodes (10): Runs the Deepgram REST -> Fish -> Piper synth cascade (skipping engines that…, fish_audio_prosody_overrides(), is_active(), Piper SynthesisConfig kwargs for calmer speech while Sleep Mode is active, or…, Fish Audio's prosody equivalent of tts_overrides() above — same calmer/quieter-…, system_prompt_context_line(), tts_overrides(), _synthesize_and_cache() (+2 more)

### Community 80 - "Fake"
Cohesion: 0.09
Nodes (36): _capture(), _cb(), Fake, O(), Records callback traffic; `answers` maps a marker in the prompt to the JSON the…, test_a_classifier_context_is_framed(), test_a_conversation_extraction_of_tool_derived_text_is_framed(), test_a_inbound_prompt_is_framed_sanitised_and_length_capped() (+28 more)

### Community 81 - "test_engine_refuses_when_models_are_missing_instead_of_letting_insightface_download"
Cohesion: 0.22
Nodes (7): fn(event_dict) is called after every audit row (kind/name/confidence/ts only)…, set_event_hook(), insightface would silently fetch the pack itself with no size/hash check,…, test_a_failing_lock_hook_does_not_break_polling(), test_engine_refuses_when_models_are_missing_instead_of_letting_insightface_download(), test_event_hook_gets_labels_only_and_a_broken_hook_is_harmless(), boom()

### Community 83 - "build_system_prompt"
Cohesion: 0.12
Nodes (18): build_system_prompt(), _fetch_projects(), get_active_facts_context(), get_projects_context(), get_skills_context(), get_user_profile_context(), _load_skills(), Formats all stored user_profile facts for embedding in the system prompt. Empty… (+10 more)

### Community 84 - "boom"
Cohesion: 0.07
Nodes (19): Voice-bug pass (2026-09-22): the filler phrase ("One moment.") and short…, test_claude_stream_first_round_gemini_provider_no_ops(), test_claude_stream_first_round_network_failure_returns_none(), boom(), test_deepgram_tts_circuit_breaker_trips_after_repeated_failures(), boom(), test_deterministic_reply_skips_run_agent_loop_entirely(), test_speak_text_backend_forced_to_piper_skips_deepgram_and_fish() (+11 more)

### Community 85 - "RuntimeError"
Cohesion: 0.09
Nodes (33): _connect(), dashboard_state(), _data_dir(), _DataBlob, _db_path(), download_models(), _dpapi(), blob() (+25 more)

### Community 86 - "test_own_signature_is_skipped_but_quoted_signature_is_not"
Cohesion: 0.32
Nodes (7): _is_our_own_message(), True if the body carries our signature as an unquoted line. Stops Jarvis…, _sig_line(), test_family_reply_prompt_frames_and_neutralises_what_the_sender_wrote(), __call__(), test_own_signature_is_skipped_but_quoted_signature_is_not(), __call__()

### Community 87 - "queue_or_deliver_notification"
Cohesion: 0.12
Nodes (24): _check_due_reminders(), flush_pending_notifications(), holding_reminders(), True while due reminders must be held (not spoken, no toast)., True after the owner said "no": reminders speak even with a stranger in view., reminders_allowed(), queue_or_deliver_notification(), Caller must already hold _session_context_lock. Writes to a temp file and… (+16 more)

### Community 88 - "autonomy.js"
Cohesion: 0.51
Nodes (9): call(), card(), cardFlag(), h(), loadLog(), logRow(), refresh(), render() (+1 more)

### Community 89 - "calibrate"
Cohesion: 0.12
Nodes (12): calibrate(), camera_index(), CameraUnavailable, _capture_and_analyze(), _get_engine(), _open_camera(), Open the camera, grab one frame, release it. Returns (observations, mean, std,…, Dry run of the enrollment liveness check that stores NOTHING (no profile, no… (+4 more)

### Community 90 - "_mail_answer"
Cohesion: 0.67
Nodes (3): _mail_answer(), test_a_clean_meeting_still_acts_at_high_confidence_and_structured_meeting_at_normal_floor(), test_wp1_subject_only_is_extracted_at_lower_confidence_and_logged()

### Community 91 - "jarvis_latency.py"
Cohesion: 0.13
Nodes (15): classify_intent(), current(), end(), Per-voice-command latency tracker (Speed Upgrade Phase 0). One VoiceLatency…, recent(), start(), VoiceLatency, parametrize (+7 more)

### Community 92 - "jarvis_dashboard.py"
Cohesion: 0.17
Nodes (21): api_audit(), api_clear_finished_sessions(), api_state(), _build_state(), clear_finished_sessions(), _connect(), _db_path(), end_session() (+13 more)

### Community 93 - "_evaluate_base"
Cohesion: 0.25
Nodes (9): _env_float(), _evaluate_base(), evaluate_policy(), Name <a@b.com>' -> 'a@b.com', lower-cased. A display name can say anything, so…, Exact address (audit E-02: substring matching let a lookalike or display name…, -> ('auto_act' | 'record' | 'ask' | 'ignore', reason). FULL-PERMISSION MODEL:…, The policy verdict (see _evaluate_base) plus the ALWAYS-ON third-party bar: for…, _sender_address() (+1 more)

### Community 94 - "enabled"
Cohesion: 0.11
Nodes (23): after_turn(), _work(), _work(), _email_recipient_blocked(), enabled(), extract_commitments_and_projects(), gate_reason(), hard_disabled() (+15 more)

### Community 95 - "state"
Cohesion: 0.24
Nodes (20): answer(), has_open_question(), on_stranger_arrived(), on_stranger_left(), Handle a reply to an open question. Returns the reply to send back, or None if…, state(), _send(), The reminders question runs before the confirmation gate, and cancels (never… (+12 more)

### Community 96 - "jarvis"
Cohesion: 0.12
Nodes (15): jarvis(), parametrize, Goes through handle_text_command -> _execute_tool (not _execute_impl): also…, DNS-rebinding defence: a hostile page re-pointing its domain at 127.0.0.1 sends…, test_away_mode_tool_respects_the_source(), turn(), test_delete_via_the_real_tool_path_needs_two_user_messages(), agent_turn() (+7 more)

### Community 97 - "synthesize"
Cohesion: 0.13
Nodes (14): Request, Deepgram Aura 2 TTS (Speed Upgrade Phase 1.2; WebSocket streaming added in the…, Same hard-timeout watchdog idiom as jarvis_stt_deepgram._urlopen_bounded —…, Connection warm-up (Phase 2.2): a tiny synth-and-discard so the first real…, synthesize(), _urlopen_bounded(), warm(), test_stt_timeout_error_falls_back_to_whisper() (+6 more)

### Community 98 - "StreamingSession"
Cohesion: 0.11
Nodes (18): One push-to-talk hold's live Deepgram Nova-3 WebSocket session. Usage (see…, Flushes and closes the session, returning (transcript, confidence) or None on…, StreamingSession, _FakeWebsocketLib, _FakeWS, Duck-types the websocket-client WebSocket object's send/recv/close surface., Mirrors jarvis.py's real usage: start() is kicked off on a helper thread and…, finish() called (almost) immediately after start() is kicked off on another… (+10 more)

### Community 99 - "Dashboard UI/UX overhaul (2026-09-22)"
Cohesion: 0.18
Nodes (10): Confirmation / approval path — unchanged, Dashboard UI/UX overhaul (2026-09-22), Home (mission control), How to preview without running full Jarvis, Keyboard, Layout, Post-overhaul UX pass (2026-09-22), Routes (+2 more)

### Community 100 - "_connect"
Cohesion: 0.25
Nodes (11): configure(), _connect(), _db_path(), init_autonomy_tables(), Connection, Path, Wire callbacks and arm the tick. jarvis.py's scheduler loop then calls…, Idempotent. Creates every table this module owns and seeds the single built-in… (+3 more)

### Community 101 - "snake.cpp"
Cohesion: 0.53
Nodes (8): deque, draw(), main(), newFood(), onSnake(), Pt, x, y

### Community 102 - "start"
Cohesion: 0.67
Nodes (3): Blocking call — run this in its own daemon thread from jarvis.py's main().…, start(), _metrics_loop()

### Community 103 - "test_dashboard_llm_endpoints"
Cohesion: 0.50
Nodes (5): api_llm(), api_set_llm(), test_dashboard_llm_endpoints(), get_llm(), set_llm()

### Community 105 - "stats_summary"
Cohesion: 0.21
Nodes (16): _connect(), Connection, Read-only sleep trends for the dashboard, from sleep_log alone (no new tables).…, save_digest(), set_wake_digest_handler(), stats_summary(), status(), _log() (+8 more)

### Community 106 - "_scheduler_callbacks"
Cohesion: 0.29
Nodes (7): Fake callbacks whose task queue is the REAL jarvis_task_scheduler (same…, _scheduler_callbacks(), test_c01_approved_background_task_is_scheduled_not_left_pending(), test_c01_campaign_step_gets_a_slot_and_a_stale_one_is_failed(), test_campaign_step_orphaned_in_running_after_a_restart_is_recovered(), test_e01_turning_off_cancels_queued_tasks(), test_wp6_campaign_statuses_planned_running_done_and_cancelled()

### Community 107 - "_set_broadcast"
Cohesion: 0.50
Nodes (4): _lifespan(), _do_broadcast(), _set_broadcast(), _broadcast()

### Community 108 - "_speak_shaped"
Cohesion: 0.11
Nodes (16): _build_sleep_digest(), _collapse_paths_for_speech(), _dashboard_approve_pending(), _sink(), _dashboard_reject_pending(), _execute_confirmed_action(), _humanize_path_for_speech(), Replaces any full file path in `text` with just its containing folder's name —… (+8 more)

### Community 109 - "_origin_is_loopback"
Cohesion: 0.40
Nodes (5): _loopback_only(), ws_endpoint(), _host_is_loopback(), _origin_is_loopback(), True if an Origin header names this machine. "null" (sandboxed iframes,…

### Community 110 - "Speed Upgrade: Deepgram-native voice pipeline + cloud-latency pass"
Cohesion: 0.10
Nodes (20): Architecture, Audit-and-fix pass (2026-09-22), Backend order, Cloud-latency pass (2026-09-22): streaming STT/TTS, simple-intent fast path, LLM token streaming, Env vars, Filler phrase (Phase 3.2), How to measure a real before/after, Latency measurement (+12 more)

### Community 111 - "snake.js"
Cohesion: 0.28
Nodes (7): canvas, ctx, KEYS, placeFood(), reset(), scoreEl, step()

### Community 112 - "_StubSession"
Cohesion: 0.25
Nodes (5): Duck-types jarvis_stt_deepgram.StreamingSession's finish() surface for…, _StubSession, test_transcribe_pcm_falls_back_to_rest_when_stream_fails(), test_transcribe_pcm_too_short_audio_still_tears_down_stream_session(), test_transcribe_pcm_uses_streaming_session_result_when_present()

### Community 113 - "jarvis_cache.py"
Cohesion: 0.38
Nodes (5): is_self_contained(), normalize_text(), Small, local-only cache helpers shared by jarvis.py: an env-flag reader,…, Lowercase, punctuation-stripped, whitespace-collapsed — so 'System status?' and…, test_normalize_and_self_contained()

### Community 114 - "_set_dark_mode"
Cohesion: 0.40
Nodes (5): _broadcast_theme_change(), Tells running apps the theme changed (what Windows Settings does). The registry…, _set_dark_mode(), test_broadcast_never_runs_under_pytest(), test_theme_change_is_broadcast_after_the_registry_write()

### Community 115 - "speak_text"
Cohesion: 0.08
Nodes (23): _away_warn(), _current_speak_signal(), _face_greet(), _play_pcm_bytes(), _play_pcm_stream(), Event, Speak arbitrary dynamic text (voice-command replies). Deepgram Aura 2 (cloud)…, Spoken warning before away mode locks the computer (not routed through the… (+15 more)

### Community 116 - "_memory_db_connect"
Cohesion: 0.05
Nodes (56): _append_history(), _apply_memory_db_pragmas(), _background_tasks_dir(), cancel_reminder(), _catastrophic_reason(), _check_background_tasks(), _count_running_background_tasks(), _create_memory_tables() (+48 more)

### Community 118 - "CircuitBreaker"
Cohesion: 0.20
Nodes (6): CircuitBreaker, Trips after `threshold` consecutive failures and refuses calls for…, test_circuit_breaker_success_resets_failures(), test_circuit_breaker_trips_and_cools_down(), test_stt_backend_recovers_after_breaker_cooldown(), flaky()

### Community 119 - "jarvis_voice_tone.py"
Cohesion: 0.32
Nodes (7): analyze_tone(), _lexical_scores(), _prosody(), Basic voice tone/sentiment awareness for Jarvis. Rule-based, deliberately…, Short line to fold into the agent system prompt for this turn; empty string if…, Returns {"tone": category, "confidence": 0..1, "signals": [short strings]}.…, tone_context_line()

### Community 120 - "fixture"
Cohesion: 0.29
Nodes (7): A(), client(), D(), fixture, S(), test_b_tool_and_dashboard_routes(), dash()

### Community 121 - "_claude_stream_first_round"
Cohesion: 0.25
Nodes (7): _claude_stream_first_round(), _speak_ready(), _extract_ready_sentences(), Logs this response's token usage + estimated cost to the api_usage table…, Splits `buf` on sentence boundaries the same way _split_sentences does (same…, Streams one Claude Messages API round trip via SSE. speak_live(text), if given,…, _record_api_usage()

### Community 122 - "StreamingSynthesis"
Cohesion: 0.13
Nodes (11): One request to Deepgram's streaming speak WebSocket. Usage: session =…, Generator yielding raw int16 PCM bytes as Aura 2 generates them. Text…, StreamingSynthesis, _FakeSpeakWebsocketLib, _FakeSpeakWS, create_connection(), test_streaming_synthesis_chunks_yields_only_binary_frames(), test_streaming_synthesis_connect_failure_returns_false() (+3 more)

### Community 124 - "_scripted_claude"
Cohesion: 0.33
Nodes (6): Fake Claude: with a tool_name, the first call requests it and the next returns…, _scripted_claude(), test_reply_cache_disabled_by_env(), test_reply_cache_never_stores_mutating_turns(), test_reply_cache_serves_readonly_repeat_without_claude(), test_reply_cache_skips_context_dependent_and_toolless_turns()

### Community 125 - "test_dev_features.py"
Cohesion: 0.06
Nodes (59): analyze_repo(), _existing_tests(), generate_tests(), _public_api(), _py_files(), Path, Repository analysis, unit-test generation and module boilerplate. Deterministic…, New `<name>.py` plus a matching test file, in the style the repo already uses. (+51 more)

### Community 126 - "test_guest_reminders.py"
Cohesion: 0.19
Nodes (15): set_disabled(), _held(), Tests for jarvis_guest_reminders (the stranger -> "disable reminders?" Telegram…, test_default_group_safe_hold_still_lets_urgent_reminders_speak(), test_flush_on_any_command_does_not_leak_held_reminders(), test_pending_question_holds_reminders_but_does_not_text_them_yet(), test_reenabling_reads_out_the_held_reminders(), test_reminders_are_held_texted_and_silent_once_disabled() (+7 more)

### Community 127 - "_DuckDuckGoResultParser"
Cohesion: 0.33
Nodes (3): HTMLParser, _duckduckgo_search(), _DuckDuckGoResultParser

### Community 128 - "send_with_retry"
Cohesion: 0.33
Nodes (6): send() -> (ok, detail). Tries once, then retries every delay_s seconds, up to…, send_with_retry(), test_send_exception_counts_as_failure(), test_send_gives_up_after_five_retries(), test_send_retries_every_minute_then_succeeds(), send()

### Community 129 - "_handle_family"
Cohesion: 0.12
Nodes (19): _autonomy_poll_mail(), New inbox messages (not the user's own, not yet seen by autonomy) with their…, _body_of(), _db_path(), _handle_family(), looks_like_error(), _sleep_mail_mcp(), parse_attachments() (+11 more)

### Community 130 - "_handle_text_command_impl"
Cohesion: 0.14
Nodes (14): _deterministic_intent_reply(), True when each held reminder should also be texted to the owner., should_forward(), _handle_text_command_impl(), _is_confirmation_yes(), A clear, short, non-negated affirmative. Whole-word matching (so 'yesterday'…, Called at the start of every command (_handle_text_command_impl), not just when…, Checked by _handle_text_command_impl right after run_agent_loop returns: True… (+6 more)

### Community 131 - "_speak_session_stub"
Cohesion: 0.14
Nodes (11): Duck-types tts_deepgram.StreamingSynthesis for _speak_streamed tests:…, Real audio already played before the interruption — must be reported as handled…, The critical Phase B safety property: the background pre-fetch thread for the…, _speak_session_stub(), test_speak_streamed_failure_before_any_audio_is_not_handled(), test_speak_streamed_happy_path(), test_speak_streamed_mid_stream_failure_after_audio_is_handled_but_incomplete(), test_speak_text_caches_complete_streamed_audio_for_reuse() (+3 more)

### Community 132 - "test_run_agent_loop_multi_round_streams_narration_then_speaks_final_reply_once"
Cohesion: 0.17
Nodes (7): Audit scenario: round 0 streams narration + a tool_use (so the loop must…, test_reply_already_spoken_flag_resets_between_commands(), test_run_agent_loop_falls_back_to_non_streaming_when_stream_fails(), fake_request(), test_run_agent_loop_multi_round_streams_narration_then_speaks_final_reply_once(), test_run_agent_loop_streams_text_only_final_reply_and_marks_spoken(), fake_stream()

### Community 133 - "_FakeSSEResponse"
Cohesion: 0.13
Nodes (13): _FakeSSEResponse, Voice-bug audit pass (2026-09-22): a WebSocket frame boundary has no reason to…, Voice-bug pass (2026-09-22): an unbuffered OutputStream starves on uneven…, _sse_lines(), _sse_text_reply(), test_claude_stream_first_round_error_event_returns_none(), test_claude_stream_first_round_fires_on_first_token_once(), test_claude_stream_first_round_speaks_sentences_live_and_reconstructs_content() (+5 more)

### Community 134 - "jarvis_guest_reminders.py"
Cohesion: 0.17
Nodes (12): _forward_held_reminders(), forward_reminder(), _norm(), parse_yes_no(), Reminders while an unrecognized person is at the computer (driven by the face…, True/False for a clear yes/no, None otherwise. Deliberately strict: the WHOLE…, Text a held reminder to the owner's phone (best effort; it stays queued either…, status() (+4 more)

### Community 135 - "j"
Cohesion: 0.18
Nodes (9): configure(), reset(), j(), Phone, fixture, Stands in for Telegram: records what Jarvis texts, and can be made to fail., test_no_telegram_means_no_question_and_no_new_hold(), test_reminders_mode_tool_from_any_source() (+1 more)

### Community 136 - "Snake"
Cohesion: 0.31
Nodes (3): Simple Snake game using tkinter. Arrow keys / WASD to move, R to restart., Snake, test_the_gate_still_works_normally_when_no_question_is_open()

### Community 139 - "_urlopen_hard_timeout"
Cohesion: 0.33
Nodes (5): _fish_audio_synthesize(), Request, urlopen(timeout=...) is supposed to bound the whole call, but a wedged TLS…, Calls Fish Audio's TTS REST API and returns (pcm_int16_bytes, sample_rate) —…, _urlopen_hard_timeout()

### Community 140 - "jarvis"
Cohesion: 0.30
Nodes (5): db(), jarvis(), fixture, test_tick_runs_every_30_minutes_only_while_asleep(), tick()

## Knowledge Gaps
- **127 isolated node(s):** `state`, `ROUTES`, `ROUTES_WITH_CONTEXT`, `servicesPanel`, `servicesToggleBtn` (+122 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1037 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_execute_tool_impl()` connect `_execute_tool_impl` to `FileWatcher`, `jarvis.py`, `jarvis_guest_reminders.py`, `jarvis_memory_enhance.py`, `jarvis_workflow.py`, `jarvis_dynamic_tools.py`, `jarvis_proactive.py`, `jarvis_autonomy.py`, `enable`, `ensure_mcp_started`, `download_image`, `jarvis_autonomy_organise.py`, `Path`, `main`, `jarvis_task_scheduler.py`, `test_restart.py`, `run_agent_loop`, `test_face.py`, `test_hardening.py`, `jarvis_billing.py`, `jarvis_tech_understanding.py`, `is_paused`, `jarvis_autonomy_skills.py`, `enroll`, `build_system_prompt`, `queue_or_deliver_notification`, `stats_summary`, `speak_text`, `_memory_db_connect`, `test_dev_features.py`, `test_guest_reminders.py`?**
  _High betweenness centrality (0.060) - this node is a cross-community bridge._
- **Why does `_build_app()` connect `_build_app` to `start`, `test_dashboard_llm_endpoints`, `_ConnectionManager`, `_set_broadcast`, `_origin_is_loopback`, `_memory_db_connect`, `jarvis_dashboard.py`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Why does `j()` connect `j` to `jarvis`, `test_hardening.py`, `test_sleep.py`, `jarvis`, `test_gemini.py`, `jarvis`, `test_guest_reminders.py`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `_execute_tool_impl()` (e.g. with `_launch_focus_app()` and `_memory_db_connect()`) actually correct?**
  _`_execute_tool_impl()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 57 inferred relationships involving `timedelta` (e.g. with `_action_for_commitment()` and `agent_context_line()`) actually correct?**
  _`timedelta` has 57 INFERRED edges - model-reasoned connections that need verification._
- **What connects `state`, `ROUTES`, `ROUTES_WITH_CONTEXT` to the rest of the system?**
  _127 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `test_autonomy.py` be split into smaller, more focused modules?**
  _Cohesion score 0.025479195885928004 - nodes in this community are weakly interconnected._