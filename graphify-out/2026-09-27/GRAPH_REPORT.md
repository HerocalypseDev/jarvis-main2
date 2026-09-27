# Graph Report - jarvis-main2  (2026-09-27)

## Corpus Check
- 118 files · ~268,623 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 1, .vbs 1, .css 1)

## Summary
- 3862 nodes · 8364 edges · 182 communities (165 shown, 14 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 498 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `bec5909c`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- test_autonomy.py
- jarvis_window_control.py
- brag-output-2026-09-19-001152/composition/assets/gsap.min.js
- test_sleep.py
- brag-output/composition/assets/gsap.min.js
- FileWatcher
- jarvis.py
- jarvis_clipboard_history.py
- jarvis_memory_enhance.py
- test_gemini.py
- test_sleep_mail.py
- jarvis_sleep_mode.py
- jarvis_workflow.py
- Full Autonomy Stack
- jarvis_dynamic_tools.py
- Tween
- test_cache.py
- TTSDiskCache
- jarvis_proactive.py
- _iso
- test_chief.py
- j
- CLAUDE.md
- app.js
- _build_app
- _tools
- jarvis_meeting_capture.py
- test_dashboard.py
- Tween
- download_image
- jarvis_autonomy_organise.py
- Path
- Fake
- _narrating_claude
- test_voice_usage.py
- test_dev_features.py
- Brag Plan: Jarvis
- SqliteKV
- jarvis_netscan.py
- test_billing_failures_are_plain_sentences
- ce
- _FakeProc
- ce
- _claude_request
- test_restart.py
- jarvis_notify_priority.py
- na
- na
- Hyperframes Composition Brief: Jarvis
- poll_once
- la
- la
- _log_decision
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
- jarvis_everything.py
- jarvis_tech_understanding.py
- transcribe
- jarvis_macros.py
- test_face.py
- Google Maps location sharing -> "where is <person>?" (2026-09-19)
- test_deepgram_voice.py
- jarvis_face.py
- enabled
- enroll
- Index
- qol.js
- _cb
- voice.js
- timedelta
- run_agent_loop
- boom
- process_inbound_message_for_events
- _fake_mcp_run_coro
- jarvis_audio_duck.py
- autonomy.js
- _run_enrollment
- _provider
- jarvis_latency.py
- jarvis_dashboard.py
- jarvis_autonomy.py
- log_entries
- test_guest_reminders.py
- _Latex
- synthesize
- StreamingSession
- Dashboard UI/UX overhaul (2026-09-22)
- start_polling
- FollowUpListener
- jarvis_focus.py
- test_dashboard_llm_endpoints
- _ConnectionManager
- test_run_agent_loop_multi_round_streams_narration_then_speaks_final_reply_once
- _scheduler_callbacks
- _set_broadcast
- jarvis_settings.py
- _origin_is_loopback
- Speed Upgrade: Deepgram-native voice pipeline + cloud-latency pass
- snake.js
- self_check_report
- RuntimeError
- jarvis_sleep_mail.py
- jarvis_task_scheduler.py
- _execute_tool_impl
- speak_text
- CircuitBreaker
- run_cycle
- fixture
- execute
- StreamingSynthesis
- _deterministic_intent_reply
- _set_dark_mode
- test_hold_modes.py
- jarvis_battery.py
- boom
- enable
- test_feature_batch_a.py
- _foreground_window
- _speak_session_stub
- Snake
- _briefing_fetchers
- jarvis_memory_consolidation.py
- jarvis_briefing.py
- jarvis_email_templates.py
- queue_or_deliver_notification
- _FakeOutputStream
- _scripted_claude
- jarvis_guest_reminders.py
- start
- features.js
- test_qol.py
- test_memory_edit.py
- Store
- jarvis_code_tools.py
- Google re-authentication (when tokens expire, every 7 days in Testing mode)
- jarvis_kg.py
- calibrate
- jarvis_cache.py
- test_1h_ttl_rejection_falls_back_to_5m_and_retries
- _StubSession
- _autonomy_callbacks
- jarvis_weather.py
- _handle_text_command_impl
- jarvis_agents.py
- fixture
- jarvis_memory_search.py
- _mail_answer
- read_attachments
- main
- jarvis_voice_tone.py
- jarvis_pptx.py
- test_record_usage_never_raises
- test_shutdown_via_run_shell_is_staged_not_run
- test_short_notification_is_spoken_unchanged_without_a_claude_call
- test_state_audit_rows_include_transcript_for_session_linking
- test_command_endpoint_invokes_run_command
- test_feature_batch_b.py
- test_feature_batch_c.py
- Feature batch 2026-09-27
- _log_action_audit
- start
- send_with_retry
- ForegroundTracker
- jarvis_improvement_report.py
- FakeRecorder
- _Resp
- _acted
- loopback_recorder
- test_f_defaults_are_on_with_no_flags_needed

## God Nodes (most connected - your core abstractions)
1. `_execute_tool_impl()` - 125 edges
2. `Fake` - 103 edges
3. `_memory_db_connect()` - 68 edges
4. `_build_app()` - 68 edges
5. `_on()` - 60 edges
6. `main()` - 55 edges
7. `_future()` - 55 edges
8. `_iso()` - 47 edges
9. `queue_or_deliver_notification()` - 44 edges
10. `_rows()` - 42 edges

## Surprising Connections (you probably didn't know these)
- `test_queue_gate_batches_and_digest_flushes()` --indirect_call--> `j()`  [INFERRED]
  test_feature_batch_c.py → test_guest_reminders.py
- `_run()` --indirect_call--> `started_at()`  [INFERRED]
  jarvis.py → jarvis_sleep_mode.py
- `_mcp_server_supervisor()` --indirect_call--> `read()`  [INFERRED]
  jarvis.py → jarvis_battery.py
- `_execute_tool_impl()` --calls--> `format_local_summary()`  [EXTRACTED]
  jarvis.py → jarvis_billing.py
- `_execute_tool_impl()` --calls--> `add_watched_folder()`  [EXTRACTED]
  jarvis.py → jarvis_filewatcher.py

## Import Cycles
- None detected.

## Communities (182 total, 14 thin omitted)

### Community 0 - "test_autonomy.py"
Cohesion: 0.02
Nodes (32): skipif, _file(), parametrize, Tests for jarvis_autonomy.py, jarvis_dynamic_tools.py,…, The gate is untouched: an autonomous agent run that reaches a catastrophic…, jarvis.py wires run_tool to _execute_tool, so a skill step naming run_shell…, Like face: the new modules may never touch the catastrophic gate or import…, test_a01_known_bypass_routes_are_rejected() (+24 more)

### Community 1 - "jarvis_window_control.py"
Cohesion: 0.14
Nodes (29): arrange_windows(), _cascade_rects(), close_window(), _connect(), _db_path(), delete_layout(), _find(), _grid_rects() (+21 more)

### Community 2 - "brag-output-2026-09-19-001152/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 3 - "test_sleep.py"
Cohesion: 0.08
Nodes (26): _dashboard_get_sleep(), _hhmm(), _period_stats(), Stats over the `days` calendar days ending at end_day (inclusive): tracked…, Read-only sleep trends for the dashboard, from sleep_log alone (no new tables).…, stats_summary(), status(), db() (+18 more)

### Community 4 - "brag-output/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 5 - "FileWatcher"
Cohesion: 0.10
Nodes (15): add_watched_folder(), _connect(), _db_path(), _default_watch_paths(), FileWatcher, get_recent_file_events(), list_watched_folders(), Connection (+7 more)

### Community 6 - "jarvis.py"
Cohesion: 0.04
Nodes (72): _autonomy_inbound(), _autonomy_mail_hook(), _bytes_to_gb(), _bytes_to_mb(), check_system_health(), _choose_input_device(), _chrome_executable(), _craft_system_status_summary() (+64 more)

### Community 7 - "jarvis_clipboard_history.py"
Cohesion: 0.22
Nodes (19): classify(), clear(), ensure(), get(), handle_tool(), _line(), list_items(), Connection (+11 more)

### Community 8 - "jarvis_memory_enhance.py"
Cohesion: 0.13
Nodes (24): _connect(), _cosine(), _db_path(), link_facts(), list_code_patterns(), list_decisions(), Connection, Path (+16 more)

### Community 9 - "test_gemini.py"
Cohesion: 0.06
Nodes (50): call(), convert_messages(), convert_tools(), from_response(), get_provider(), list_models(), Path, Request (+42 more)

### Community 10 - "test_sleep_mail.py"
Cohesion: 0.16
Nodes (19): db(), FakeGmail, jarvis(), fixture, Tests for the Sleep Mode mail take-over. Run: python -m pytest…, _run(), _search(), test_family_email_gets_reply_recorded_and_not_repeated() (+11 more)

### Community 11 - "jarvis_sleep_mode.py"
Cohesion: 0.12
Nodes (19): Short, unambiguous volume commands ("volume up", "turn it down", "mute",…, _cancel_media_autopause(), _db_path(), _endpoint_volume_call(), _get_volume(), guided_breathing_steps(), is_whitelisted_sender(), _log_duration_to_memory() (+11 more)

### Community 12 - "jarvis_workflow.py"
Cohesion: 0.16
Nodes (20): _connect(), _db_path(), detect_stack(), get_context_summary(), get_workflow_status(), git_info(), Connection, Path (+12 more)

### Community 13 - "Full Autonomy Stack"
Cohesion: 0.05
Nodes (38): Audit-and-fix pass (2026-09-20, after the full-permission change), Audit pass 2 (after injection hardening + file organising): what changed because of real bugs, Calendar and skills (small hardening), Dynamic tools, File organising (ON by default whenever autonomy is on), Full Autonomy Stack, How the tick works, How to verify (do this before trusting it) (+30 more)

### Community 14 - "jarvis_dynamic_tools.py"
Cohesion: 0.07
Nodes (57): find_dm_with_user(), list_dm_channels(), list_servers(), on_ready(), Custom MCP server wrapping discord.py-self to let Jarvis act as the user's own…, Lists the Discord servers (guilds) this account is a member of, with their IDs., Lists currently open DM conversations, with their channel IDs., Finds a DM channel ID by matching a username against currently open DM… (+49 more)

### Community 15 - "Tween"
Cohesion: 0.19
Nodes (21): _a(), Ao(), _assertThisInitialized(), cb(), cc(), ga(), gb(), hb() (+13 more)

### Community 16 - "test_cache.py"
Cohesion: 0.05
Nodes (8): _gate_env(), _kv_db(), Tests for the caching layers (jarvis_cache.py + their wiring in jarvis.py). Run…, test_billing_summary_and_pagination(), test_busy_gate_holds_ordinary_notification_but_not_reminders(), test_bypass_busy_gate_still_respects_sleep_mode(), test_record_and_local_summary(), test_scheduled_skill_never_speaks_tool_ack_or_bare_ok()

### Community 17 - "TTSDiskCache"
Cohesion: 0.29
Nodes (5): Path, WAV files under one directory, keyed by hash. LRU by mtime (touched on every…, TTSDiskCache, test_tts_cache_skips_synthesis_on_repeat(), test_tts_disk_cache_roundtrip_and_eviction()

### Community 18 - "jarvis_proactive.py"
Cohesion: 0.27
Nodes (12): check_project_health(), _connect(), _db_path(), _fmt_findings(), _iter_source_files(), Connection, Path, Proactive problem detection for Jarvis. Scans a file or project directory for… (+4 more)

### Community 19 - "_iso"
Cohesion: 0.10
Nodes (46): accept_commitment(), add_project_action(), approve_campaign(), approve_suggestion(), _brief(), _commitment(), delete_policy(), dismiss_suggestion() (+38 more)

### Community 20 - "test_chief.py"
Cohesion: 0.09
Nodes (22): dtime, budget_alert(), headsup_text(), in_quiet_hours(), _local(), meetings_starting(), parse_quiet_hours(), parse_reply_style() (+14 more)

### Community 21 - "j"
Cohesion: 0.11
Nodes (11): configure(), reset(), j(), Phone, fixture, Stands in for Telegram: records what Jarvis texts, and can be made to fail., test_reminders_mode_tool_from_any_source(), run() (+3 more)

### Community 22 - "CLAUDE.md"
Cohesion: 0.06
Nodes (33): API spend lookup (2026-09-18), Audit hardening (2026-09-21), Chief-of-staff batch (2026-09-23), Cloud-latency pass (2026-09-22), Confirmation gate follow-up (2026-09-18), Context7 + Windows-MCP (2026-09-23), Cost reporting, Dashboard (supervision UI) (+25 more)

### Community 23 - "app.js"
Cohesion: 0.08
Nodes (65): actOnPending(), AUTO_OPEN_SOURCES, badge(), connectWs(), coreHeatmap(), currentRoute(), esc(), escAttr() (+57 more)

### Community 24 - "_build_app"
Cohesion: 0.10
Nodes (33): _build_app(), api_autonomy(), api_autonomy_campaign_action(), api_autonomy_campaign_approve(), api_autonomy_commitment(), api_autonomy_commitment_accept(), api_autonomy_dry_run(), api_autonomy_enabled() (+25 more)

### Community 25 - "_tools"
Cohesion: 0.12
Nodes (14): test_c_skill_failure_stops_logs_the_step_and_notifies_exactly_once(), test_concurrent_extraction_of_the_same_item_inserts_it_once(), go(), test_d01_two_simultaneous_approvals_run_the_action_once(), go(), test_skill_creation_budget_holds_under_concurrency(), test_skills_never_mine_typing_http_or_secret_bearing_tools_or_huge_inputs(), test_wp5_cannot_smuggle_unknown_or_forbidden_tools_or_bad_shapes() (+6 more)

### Community 26 - "jarvis_meeting_capture.py"
Cohesion: 0.15
Nodes (23): _feature_meetings(), active(), delete_meeting(), ensure(), _env_num(), _finish(), list_meetings(), _now() (+15 more)

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
Cohesion: 0.08
Nodes (31): _cleanup_old_logs(), _dashboard_get_daily_items(), _fmt_gb(), get_large_files_report(), _load_skills(), _memory_db_path(), _print_large_files_breakdown(), Path (+23 more)

### Community 32 - "Fake"
Cohesion: 0.06
Nodes (71): Fake, _future(), _on(), FULL-PERMISSION MODEL: a confident, non-catastrophic item is acted on…, Records callback traffic; `answers` maps a marker in the prompt to the JSON the…, test_a_classifier_actions_influenced_by_inbound_mail_face_the_third_party_bar(), test_a_email_recipient_allowlist_is_optional_and_empty_means_unrestricted(), test_a_injected_email_at_medium_confidence_does_not_auto_act_and_says_why() (+63 more)

### Community 33 - "_narrating_claude"
Cohesion: 0.15
Nodes (9): _narrating_claude(), fake(), test_narrate_off_keeps_old_behaviour(), test_narrate_speaks_text_beside_a_tool_call_and_keeps_it_out_of_the_reply(), test_summary_cache_skips_second_claude_call(), test_tool_only_turn_falls_back_to_tool_result_by_default(), test_tool_result_fallback_can_be_disabled(), test_truncated_tool_call_is_not_run_and_not_silent() (+1 more)

### Community 34 - "test_voice_usage.py"
Cohesion: 0.21
Nodes (12): _ensure(), Connection, Voice usage stats (2026-09-23): how much text Jarvis turns into speech (TTS)…, kind "tts" (Jarvis spoke `text`) or "stt" (the user said `text`); only its…, record(), summary(), _db(), jarvis() (+4 more)

### Community 35 - "test_dev_features.py"
Cohesion: 0.08
Nodes (40): analyze_repo(), _existing_tests(), generate_tests(), _public_api(), _py_files(), Path, Repository analysis, unit-test generation and module boilerplate. Deterministic…, New `<name>.py` plus a matching test file, in the style the repo already uses. (+32 more)

### Community 36 - "Brag Plan: Jarvis"
Cohesion: 0.10
Nodes (19): Audio direction, Brag Plan: Jarvis, Duration: ~21 seconds, Format: landscape — 1920x1080, Hook (first 3.3 seconds), Key moments (the middle), Outro / punchline, Scene 1 — Hook — 3.3s (+11 more)

### Community 37 - "SqliteKV"
Cohesion: 0.36
Nodes (4): Connection, key -> text value with a created_at timestamp; max_age_s is checked on read,…, SqliteKV, test_sqlite_kv_max_age_and_prune()

### Community 38 - "jarvis_netscan.py"
Cohesion: 0.10
Nodes (36): IPv4Network, _feature_devices(), apply_names(), describe(), _ensure(), _ensure_names(), handle_tool(), _hostnames() (+28 more)

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

### Community 43 - "_claude_request"
Cohesion: 0.05
Nodes (48): HTMLParser, _build_sleep_digest(), _claude_request(), _claude_stream_first_round(), _speak_ready(), _claude_text(), _duckduckgo_search(), _DuckDuckGoResultParser (+40 more)

### Community 44 - "test_restart.py"
Cohesion: 0.15
Nodes (18): check_syntax(), helper_command(), Event, Path, restart_jarvis: let Jarvis restart itself (voice: "restart yourself") to pick…, Error text for the first jarvis*.py that doesn't compile, else None., restart(), _stop_self() (+10 more)

### Community 45 - "jarvis_notify_priority.py"
Cohesion: 0.20
Nodes (18): _feature_notifications(), _interrupt_speech(), _bump(), delivered(), digest_text(), ensure(), infer_kind(), on_interrupt() (+10 more)

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
Nodes (44): describe_presence(), _fresh(), group_safe(), group_safe_suppress(), list_snapshots(), poll_once(), _Presence, One recognition cycle. Returns a short status word (used by tests and… (+36 more)

### Community 50 - "la"
Cohesion: 0.53
Nodes (6): Animation(), Da(), la(), ma(), Ua(), Va()

### Community 51 - "la"
Cohesion: 0.53
Nodes (6): Animation(), Da(), la(), ma(), Ua(), Va()

### Community 52 - "_log_decision"
Cohesion: 0.12
Nodes (30): Any, _work(), _ask_model(), _audit(), budgets(), _clean(), create_suggestion(), _direct_calendar() (+22 more)

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
Nodes (41): _read_file_tool(), classify(), default_dir(), _inside(), Path, Jarvis_Workspace: the default home for every file Jarvis creates, saves or…, Where a file should be written. Returns (path, "") or (None, reason it was…, Absolute paths are used as given; a relative one is looked up in the workspace… (+33 more)

### Community 65 - "jarvis_billing.py"
Cohesion: 0.14
Nodes (20): compute_cost(), _dollars(), _ensure_usage_table(), fetch_cost_buckets(), format_local_summary(), get_api_spend(), local_summary(), Connection (+12 more)

### Community 66 - "jarvis_everything.py"
Cohesion: 0.24
Nodes (12): build_query(), _candidate_urls(), _es(), format_results(), _http(), _is_loopback(), Instant file search through voidtools Everything (2026-09-27, feature batch…, {"ok", "backend", "results": [{path, type, size?}], "ms", "error"?}. (+4 more)

### Community 67 - "jarvis_tech_understanding.py"
Cohesion: 0.13
Nodes (14): analyze_python_file(), build_import_graph(), format_analysis_report(), format_error_report(), _imports_of(), _module_name_for(), parse_error(), Path (+6 more)

### Community 68 - "transcribe"
Cohesion: 0.12
Nodes (16): ndarray, Request, Deepgram Nova-3 STT (Speed Upgrade Phase 1.1, streaming added in the cloud-…, Connection warm-up (Phase 2.2): a near-silent clip so the TLS handshake happens…, Hard-timeout watchdog: urlopen's own timeout doesn't reliably fire on a wedged…, transcribe(), _urlopen_bounded(), warm() (+8 more)

### Community 69 - "jarvis_macros.py"
Cohesion: 0.23
Nodes (17): _macro_reply(), delete(), ensure(), handle_tool(), list_macros(), match(), normalize(), Connection (+9 more)

### Community 72 - "test_face.py"
Cohesion: 0.05
Nodes (42): invalidate_profile_cache(), is_paused(), Camera privacy switch. Pausing is always allowed (it can only make things more…, True while the Windows lock screen (secure desktop) is up: the camera is off-…, _session_locked(), set_paused(), away(), enrolled() (+34 more)

### Community 73 - "Google Maps location sharing -> "where is <person>?" (2026-09-19)"
Cohesion: 0.22
Nodes (8): 1. Unofficial library (closest to the goal), 2. Telegram live location (official, stable), 3. Dedicated tracker (official, always-on), Before building, Feature batch 2026-09-27: deliberately not built, Google Maps location sharing -> "where is <person>?" (2026-09-19), Later, Recommendation

### Community 74 - "test_deepgram_voice.py"
Cohesion: 0.05
Nodes (21): _FakeSSEResponse, Tests for the Deepgram Speed Upgrade: jarvis_stt_deepgram.py,…, A background pre-synthesis that outlives PIPELINE_JOIN_TIMEOUT_S must not hang…, Voice-bug follow-up (2026-09-22): "Hi" and "thanks" answer with no Claude call…, Voice-bug follow-up (2026-09-22): TTSDiskCache.get() has no integrity check on…, _sse_lines(), _sse_text_reply(), test_claude_stream_first_round_error_event_returns_none() (+13 more)

### Community 75 - "jarvis_face.py"
Cohesion: 0.06
Nodes (69): Exception, _already_enrolled(), away_enabled(), away_grace_s(), _away_reset(), away_status(), _away_step(), away_warn_s() (+61 more)

### Community 76 - "enabled"
Cohesion: 0.12
Nodes (31): after_turn(), enabled(), hard_disabled(), ingest_external(), process_inbound_async(), Already-extracted items from another feature (e.g. meeting notes' action items)…, Cheap fast path first (planning-cue regex), then anything long enough to hold a…, Called by jarvis.py after every command. Cheap unless the exchange looks like… (+23 more)

### Community 77 - "enroll"
Cohesion: 0.10
Nodes (36): _clean_name(), delete(), delete_by_id(), describe_profiles(), enroll(), list_profiles(), (role, None) to enroll with, or (None, reason). The first person is always the…, Enroll a person. The first one becomes the Admin; later ones are `user`… (+28 more)

### Community 78 - "Index"
Cohesion: 0.11
Nodes (16): _feature_files(), ensure(), extract_text(), format_find(), Index, _parse_tags(), Connection, File index + tags + duplicates (2026-09-27, feature batch B2). Fed by the file… (+8 more)

### Community 79 - "qol.js"
Cohesion: 0.16
Nodes (16): buildPalette(), closePalette(), filterSettings(), fuzzyScore(), loadPins(), memoryCall(), openPalette(), palette (+8 more)

### Community 80 - "_cb"
Cohesion: 0.07
Nodes (28): _capture(), _cb(), test_a_classifier_context_is_framed(), test_a_conversation_extraction_of_tool_derived_text_is_framed(), test_a_inbound_prompt_is_framed_sanitised_and_length_capped(), test_agent_replies_that_admit_failure_are_failures(), test_c_calendar_logs_distinguish_mcp_missing_from_failure_from_success(), test_c_structured_fallback_prompt_and_no_calendar_tool_is_a_clear_failure() (+20 more)

### Community 81 - "voice.js"
Cohesion: 0.32
Nodes (14): refreshVoice(), renderVoiceCards(), renderVoiceDaily(), renderVoiceEngines(), renderVoiceLatency(), renderVoiceRecords(), renderVoiceRhythm(), renderVoiceSplit() (+6 more)

### Community 82 - "timedelta"
Cohesion: 0.08
Nodes (56): _action_for_commitment(), _announce_pending(), _call(), _campaign_step(), _classifier_step(), _context_summary(), _deadline_scan(), dry_run() (+48 more)

### Community 83 - "run_agent_loop"
Cohesion: 0.05
Nodes (53): _append_history(), _autonomy_run_agent(), build_system_blocks(), build_system_prompt(), enabled(), JARVIS_<LAYER>_CACHE env flag, default on. Read on every call so it can be…, record(), _cached_tools() (+45 more)

### Community 84 - "boom"
Cohesion: 0.07
Nodes (20): The exact reported bug: saying "Hi" must produce a clean full reply, never the…, Voice-bug pass (2026-09-22): the filler phrase ("One moment.") and short…, test_claude_stream_first_round_gemini_provider_no_ops(), test_claude_stream_first_round_network_failure_returns_none(), boom(), test_deepgram_tts_circuit_breaker_trips_after_repeated_failures(), boom(), test_deterministic_reply_skips_run_agent_loop_entirely() (+12 more)

### Community 85 - "process_inbound_message_for_events"
Cohesion: 0.11
Nodes (21): agent_context_line(), extract_commitments_and_projects(), _fill(), process_inbound_message_for_events(), Manual hook: runs the extraction prompt and returns the parsed, validated items…, Semantic recall over the exchange, so extraction sees what Jarvis already knows…, conversation text -> commitments (+ projects) -> policy routing. Returns new…, THE inbound hook for mail / Telegram / Discord / any message. Meetings become… (+13 more)

### Community 86 - "_fake_mcp_run_coro"
Cohesion: 0.32
Nodes (6): _fake_mcp_run_coro(), _FakeMcpResult, execute_mcp_tool always builds the real coroutine before calling _mcp_run_coro;…, test_calendar_invalid_grant_embedded_in_json_still_gets_the_hint(), test_gmail_invalid_grant_becomes_a_reauth_instruction(), test_other_mcp_errors_are_unaffected_by_the_auth_hint()

### Community 87 - "jarvis_audio_duck.py"
Cohesion: 0.09
Nodes (34): _ctl_read(), _ctl_start(), duck(), enabled(), media_control(), _mute_others(), _pause_music(), _pause_pattern() (+26 more)

### Community 88 - "autonomy.js"
Cohesion: 0.51
Nodes (9): call(), card(), cardFlag(), h(), loadLog(), logRow(), refresh(), render() (+1 more)

### Community 89 - "_run_enrollment"
Cohesion: 0.18
Nodes (18): _already_seen_recently(), _decrypt(), get_snapshot(), identify(), load_embeddings(), _pack_embeddings(), _profiles_for_matching(), ndarray (+10 more)

### Community 90 - "_provider"
Cohesion: 0.13
Nodes (15): api_briefing(), api_feature_get(), api_feature_post(), api_health(), api_latency(), api_memory(), api_memory_add(), api_memory_edit() (+7 more)

### Community 91 - "jarvis_latency.py"
Cohesion: 0.16
Nodes (12): current(), end(), Per-voice-command latency tracker (Speed Upgrade Phase 0). One VoiceLatency…, recent(), start(), VoiceLatency, A narrated mid-task line speaks via Deepgram; the final (longer) reply's…, test_deterministic_path_recorded_on_voice_latency() (+4 more)

### Community 92 - "jarvis_dashboard.py"
Cohesion: 0.15
Nodes (24): api_audit(), api_clear_finished_sessions(), api_recent_commands(), api_state(), _build_state(), clear_finished_sessions(), _connect(), _db_path() (+16 more)

### Community 93 - "jarvis_autonomy.py"
Cohesion: 0.07
Nodes (44): add_commitment(), _work(), build_calendar_args(), configure(), _connect(), _db_path(), _env_float(), _evaluate_base() (+36 more)

### Community 94 - "log_entries"
Cohesion: 0.20
Nodes (10): explain(), log_entries(), log_summary(), Cap free-text fields: the dashboard needs enough to review an item, not whole…, Filterable view of autonomy_decisions (time range, type, category, outcome,…, Human-readable 'what did autonomy do' (acts first, with counts)., Why did you do X?': the matching decisions with their policy reason, source…, Speaks the summary (shortened for speech by jarvis.py's _speak_shaped) and… (+2 more)

### Community 95 - "test_guest_reminders.py"
Cohesion: 0.13
Nodes (37): answer(), has_open_question(), holding_reminders(), on_stranger_arrived(), on_stranger_left(), Handle a reply to an open question. Returns the reply to send back, or None if…, True while due reminders must be held (not spoken, no toast)., set_disabled() (+29 more)

### Community 96 - "_Latex"
Cohesion: 0.22
Nodes (13): _add_inline(), _add_table(), _base_styles(), _cells(), _Latex, _m(), _mr(), _omath() (+5 more)

### Community 97 - "synthesize"
Cohesion: 0.13
Nodes (14): Request, Deepgram Aura 2 TTS (Speed Upgrade Phase 1.2; WebSocket streaming added in the…, Same hard-timeout watchdog idiom as jarvis_stt_deepgram._urlopen_bounded —…, Connection warm-up (Phase 2.2): a tiny synth-and-discard so the first real…, synthesize(), _urlopen_bounded(), warm(), test_stt_timeout_error_falls_back_to_whisper() (+6 more)

### Community 98 - "StreamingSession"
Cohesion: 0.11
Nodes (18): One push-to-talk hold's live Deepgram Nova-3 WebSocket session. Usage (see…, Flushes and closes the session, returning (transcript, confidence) or None on…, StreamingSession, _FakeWebsocketLib, _FakeWS, Duck-types the websocket-client WebSocket object's send/recv/close surface., Mirrors jarvis.py's real usage: start() is kicked off on a helper thread and…, finish() called (almost) immediately after start() is kicked off on another… (+10 more)

### Community 99 - "Dashboard UI/UX overhaul (2026-09-22)"
Cohesion: 0.18
Nodes (10): Confirmation / approval path — unchanged, Dashboard UI/UX overhaul (2026-09-22), Home (mission control), How to preview without running full Jarvis, Keyboard, Layout, Post-overhaul UX pass (2026-09-22), Routes (+2 more)

### Community 100 - "start_polling"
Cohesion: 0.15
Nodes (14): _lower_thread_priority(), poll_interval(), Run the poll below normal priority so an inference burst yields to the voice…, Start the low-duty background poll (no-op unless JARVIS_FACE_ENABLED=1). The…, Once the owner has been steadily in view with nobody else, look less often…, settled_poll_interval(), start_polling(), loop() (+6 more)

### Community 101 - "FollowUpListener"
Cohesion: 0.11
Nodes (23): deque, FollowUpListener, ndarray, Follow-up window (QOL pass, 2026-09-23): after Jarvis answers a voice command,…, chained: this reply answered a hands-free follow-up. After MAX_CHAIN of those…, Call with every mic block while push-to-talk isn't held and Jarvis isn't…, draw(), main() (+15 more)

### Community 102 - "jarvis_focus.py"
Cohesion: 0.16
Nodes (20): classify_mood(), current_track(), disable(), enable(), _enabled_flag(), is_active(), Focus Mode, optionally triggered by the mood of what Spotify is playing. Mood…, Queue non-urgent notifications while Focus Mode is on; urgent ones always get… (+12 more)

### Community 103 - "test_dashboard_llm_endpoints"
Cohesion: 0.50
Nodes (5): api_llm(), api_set_llm(), test_dashboard_llm_endpoints(), get_llm(), set_llm()

### Community 105 - "test_run_agent_loop_multi_round_streams_narration_then_speaks_final_reply_once"
Cohesion: 0.13
Nodes (8): Audit scenario: round 0 streams narration + a tool_use (so the loop must…, test_reply_already_spoken_flag_resets_between_commands(), test_run_agent_loop_falls_back_to_non_streaming_when_stream_fails(), fake_request(), test_run_agent_loop_multi_round_streams_narration_then_speaks_final_reply_once(), test_run_agent_loop_streams_text_only_final_reply_and_marks_spoken(), fake_stream(), test_smart_model_request_has_thinking_and_skips_live_stream()

### Community 106 - "_scheduler_callbacks"
Cohesion: 0.29
Nodes (7): Fake callbacks whose task queue is the REAL jarvis_task_scheduler (same…, _scheduler_callbacks(), test_c01_approved_background_task_is_scheduled_not_left_pending(), test_c01_campaign_step_gets_a_slot_and_a_stale_one_is_failed(), test_campaign_step_orphaned_in_running_after_a_restart_is_recovered(), test_e01_turning_off_cancels_queued_tasks(), test_wp6_campaign_statuses_planned_running_done_and_cancelled()

### Community 107 - "_set_broadcast"
Cohesion: 0.50
Nodes (4): _lifespan(), _do_broadcast(), _set_broadcast(), _broadcast()

### Community 108 - "jarvis_settings.py"
Cohesion: 0.31
Nodes (10): _apply_live(), _bool(), env_path(), is_secret(), list_settings(), _parse_env(), Path, Dashboard Settings page backend (QOL pass, 2026-09-23): view and change… (+2 more)

### Community 109 - "_origin_is_loopback"
Cohesion: 0.40
Nodes (5): _loopback_only(), ws_endpoint(), _host_is_loopback(), _origin_is_loopback(), True if an Origin header names this machine. "null" (sandboxed iframes,…

### Community 110 - "Speed Upgrade: Deepgram-native voice pipeline + cloud-latency pass"
Cohesion: 0.08
Nodes (23): Architecture, Audit-and-fix pass (2026-09-22), Backend order, Cloud-latency pass (2026-09-22): streaming STT/TTS, simple-intent fast path, LLM token streaming, Env vars, Filler phrase (Phase 3.2), How to measure a real before/after, Latency measurement (+15 more)

### Community 111 - "snake.js"
Cohesion: 0.28
Nodes (7): canvas, ctx, KEYS, placeFood(), reset(), scoreEl, step()

### Community 112 - "self_check_report"
Cohesion: 0.17
Nodes (12): _claude_failure_reason(), _claude_live_problem(), _dashboard_get_services_status(), _load_mcp_server_configs(), _mcp_servers_config_path(), One ~10-token request straight to Anthropic (no failover) to see if Claude…, Checks every moving part and says what's broken first. Works with no LLM at…, (short spoken reason, account_level) for an HTTP error from Anthropic. (+4 more)

### Community 113 - "RuntimeError"
Cohesion: 0.06
Nodes (37): _data_dir(), _DataBlob, _db_path(), download_models(), _dpapi(), blob(), _encrypt(), _has_encrypted_data() (+29 more)

### Community 114 - "jarvis_sleep_mail.py"
Cohesion: 0.18
Nodes (17): _body_of(), _handle_family(), _is_our_own_message(), looks_like_error(), parse_attachments(), Sleep Mode mail take-over. While Sleep Mode is on, jarvis.py calls run_cycle()…, read_email lists attachments as '- name (mime, N KB, ID: xxx)' under…, (thread_id, body) from read_email output. (+9 more)

### Community 115 - "jarvis_task_scheduler.py"
Cohesion: 0.19
Nodes (19): cancel_task(), _connect(), _db_path(), _free_slots(), _inflate_estimate(), list_task_queue(), _normalize(), _parse_busy_intervals() (+11 more)

### Community 116 - "_execute_tool_impl"
Cohesion: 0.04
Nodes (68): _apply_memory_db_pragmas(), _background_tasks_dir(), cancel_reminder(), _catastrophic_reason(), _check_background_tasks(), click_at(), _count_running_background_tasks(), _create_memory_tables() (+60 more)

### Community 117 - "speak_text"
Cohesion: 0.07
Nodes (37): stable_hash(), _collapse_paths_for_speech(), _dashboard_approve_pending(), _sink(), _dashboard_reject_pending(), _execute_confirmed_action(), _humanize_path_for_speech(), _pcm_seconds() (+29 more)

### Community 118 - "CircuitBreaker"
Cohesion: 0.17
Nodes (8): CircuitBreaker, Trips after `threshold` consecutive failures and refuses calls for…, jarvis(), fixture, test_circuit_breaker_success_resets_failures(), test_circuit_breaker_trips_and_cools_down(), test_stt_backend_recovers_after_breaker_cooldown(), flaky()

### Community 119 - "run_cycle"
Cohesion: 0.16
Nodes (18): _classify_critical(), _connect(), _emails(), _env_set(), _handled(), _label(), load_family(), _mark() (+10 more)

### Community 120 - "fixture"
Cohesion: 0.25
Nodes (8): A(), client(), D(), O(), fixture, S(), test_b_tool_and_dashboard_routes(), dash()

### Community 122 - "StreamingSynthesis"
Cohesion: 0.11
Nodes (13): Attempts Deepgram's streaming speak WebSocket for `text`, playing audio as it's…, _speak_streamed(), One request to Deepgram's streaming speak WebSocket. Usage: session =…, Generator yielding raw int16 PCM bytes as Aura 2 generates them. Text…, StreamingSynthesis, _FakeSpeakWebsocketLib, _FakeSpeakWS, create_connection() (+5 more)

### Community 123 - "_deterministic_intent_reply"
Cohesion: 0.08
Nodes (31): _cancel_timers(), _deterministic_intent_reply(), _face_release_held_notifications(), flush_pending_notifications(), _last_actions_reply(), _parse_duration_s(), pasta" from "set a pasta timer for 10 minutes" / "a timer called pasta" / "10…, Timers persist in jarvis_memory.db so a restart doesn't lose them. (+23 more)

### Community 124 - "_set_dark_mode"
Cohesion: 0.40
Nodes (5): _broadcast_theme_change(), Tells running apps the theme changed (what Windows Settings does). The registry…, _set_dark_mode(), test_broadcast_never_runs_under_pytest(), test_theme_change_is_broadcast_after_the_registry_write()

### Community 125 - "test_hold_modes.py"
Cohesion: 0.23
Nodes (8): _fake_keyboard(), jarvis(), fixture, Appshot (ask about the window in front) and dictation hold modes. No real…, test_a_mouse_click_during_the_hold_is_a_shortcut_not_a_hold(), test_appshot_attaches_window_picture_and_is_never_reply_cached(), test_dictation_copies_instead_when_the_window_changed(), test_dictation_types_into_the_same_window_and_audits_without_the_words()

### Community 126 - "jarvis_battery.py"
Cohesion: 0.31
Nodes (9): classify(), enabled(), _pct(), Battery-aware background work (2026-09-27, feature batch A5). On battery (not…, Updates the stored level; returns a line to announce, or None., read(), _battery_tick(), transition() (+1 more)

### Community 127 - "boom"
Cohesion: 0.17
Nodes (12): test_daily_endpoint_exception_does_not_break(), boom(), test_get_pending_exception_does_not_break_state(), boom(), test_metrics_callback_exception_does_not_break_state(), boom(), test_services_endpoint_exception_does_not_break(), boom() (+4 more)

### Community 128 - "enable"
Cohesion: 0.16
Nodes (27): _connect(), disable(), enable(), _get_state(), is_active(), Connection, ISO start time of the current Sleep Mode session, or None if it's off., kind='nap' runs the exact same mode (quiet notifications, mail take-over, dark… (+19 more)

### Community 129 - "test_feature_batch_a.py"
Cohesion: 0.15
Nodes (10): db(), jarvis(), fixture, parametrize, Feature batch 2026-09-27, Phase A (FEATURES.md): clipboard history, Everything…, test_clipboard_classify(), test_deadline_nudge_includes_context(), test_everything_refuses_non_loopback() (+2 more)

### Community 130 - "_foreground_window"
Cohesion: 0.09
Nodes (22): _dictate(), _foreground_window(), _get_active_window_title(), _grab_appshot(), _grab_dictation(), _keyboard_is_pressed(), _mouse_button_down(), _other_keys_down() (+14 more)

### Community 131 - "_speak_session_stub"
Cohesion: 0.14
Nodes (11): Duck-types tts_deepgram.StreamingSynthesis for _speak_streamed tests:…, Real audio already played before the interruption — must be reported as handled…, The critical Phase B safety property: the background pre-fetch thread for the…, _speak_session_stub(), test_speak_streamed_failure_before_any_audio_is_not_handled(), test_speak_streamed_happy_path(), test_speak_streamed_mid_stream_failure_after_audio_is_handled_but_incomplete(), test_speak_text_caches_complete_streamed_audio_for_reuse() (+3 more)

### Community 132 - "Snake"
Cohesion: 0.31
Nodes (3): Simple Snake game using tkinter. Arrow keys / WASD to move, R to restart., Snake, test_the_gate_still_works_normally_when_no_question_is_open()

### Community 133 - "_briefing_fetchers"
Cohesion: 0.06
Nodes (30): AbstractEventLoop, _autonomy_calendar_events(), _autonomy_create_event(), _briefing_fetchers(), calendar(), failed(), mail(), pending() (+22 more)

### Community 134 - "jarvis_memory_consolidation.py"
Cohesion: 0.28
Nodes (14): abstract_rules(), compress_old_summaries(), _connect(), consolidate(), _db_path(), _iso(), Connection, datetime (+6 more)

### Community 135 - "jarvis_briefing.py"
Cohesion: 0.07
Nodes (35): calendar_items(), compose(), deadline_items(), _hm(), mail_items(), datetime, Morning briefing v2 and "what's urgent?" (2026-09-23). One composition used by…, Calendar MCP (@cocal/google-calendar-mcp) list-events JSON -> "9:30 AM Standup"… (+27 more)

### Community 136 - "jarvis_email_templates.py"
Cohesion: 0.24
Nodes (15): _email_reply_tool(), _db(), delete(), ensure(), fill(), format_drafts(), list_templates(), parse_drafts() (+7 more)

### Community 137 - "queue_or_deliver_notification"
Cohesion: 0.06
Nodes (54): _agent_mail_check(), _agent_run_async(), _agents_tick(), _autonomy_tick_battery_aware(), current(), _budget_check(), _check_due_reminders(), _chief_tick() (+46 more)

### Community 139 - "_scripted_claude"
Cohesion: 0.25
Nodes (8): Fake Claude: with a tool_name, the first call requests it and the next returns…, _scripted_claude(), test_background_task_status_is_never_reply_cached(), test_handoff_claim_still_unbacked_after_nudge_is_corrected(), test_reply_cache_disabled_by_env(), test_reply_cache_never_stores_mutating_turns(), test_reply_cache_serves_readonly_repeat_without_claude(), test_reply_cache_skips_context_dependent_and_toolless_turns()

### Community 140 - "jarvis_guest_reminders.py"
Cohesion: 0.17
Nodes (12): _forward_held_reminders(), forward_reminder(), _norm(), parse_yes_no(), Reminders while an unrecognized person is at the computer (driven by the face…, True/False for a clear yes/no, None otherwise. Deliberately strict: the WHOLE…, Text a held reminder to the owner's phone (best effort; it stays queued either…, status() (+4 more)

### Community 141 - "start"
Cohesion: 0.67
Nodes (3): Blocking call — run this in its own daemon thread from jarvis.py's main().…, start(), _metrics_loop()

### Community 142 - "features.js"
Cohesion: 0.17
Nodes (20): AGENT_CONFIG_HINTS, agentStepRow(), agentTools, clipRows(), featureGet(), featurePost(), fileRows(), fmtWhen() (+12 more)

### Community 143 - "test_qol.py"
Cohesion: 0.06
Nodes (38): _clipboard_has_non_text(), _get_whisper_model(), _grab_selection(), handle_text_command(), handle_voice_command(), _handle_voice_command_impl(), _inflight_enter(), _inflight_exit() (+30 more)

### Community 144 - "test_memory_edit.py"
Cohesion: 0.25
Nodes (3): jarvis(), fixture, Editable memory (P3): list/edit/forget facts, profile fields, forget_fact tool,…

### Community 145 - "Store"
Cohesion: 0.17
Nodes (11): create(), ensure(), file_event_matches(), _agents_on_file_event(), Connection, Store, validate(), test_agent_failure_notifies_once_and_staged_stops() (+3 more)

### Community 146 - "jarvis_code_tools.py"
Cohesion: 0.19
Nodes (14): _code_search_tool(), default_roots(), format_review(), format_search(), load_for_review(), Code search + code review (2026-09-27, feature batch C2/C3). Both on demand…, (name, code) for a file, or a repo/folder's uncommitted `git diff`; an error…, read_guard(path) -> reason: hits in files Jarvis must not read (.env, keys, its… (+6 more)

### Community 147 - "Google re-authentication (when tokens expire, every 7 days in Testing mode)"
Cohesion: 0.50
Nodes (3): Calendar, Gmail, Google re-authentication (when tokens expire, every 7 days in Testing mode)

### Community 148 - "jarvis_kg.py"
Cohesion: 0.25
Nodes (15): add_edge(), ensure(), _exists(), format_query(), _person_name(), Connection, query(), Lite knowledge graph (2026-09-27, feature batch C5): people, projects, tasks,… (+7 more)

### Community 149 - "calibrate"
Cohesion: 0.07
Nodes (22): calibrate(), camera_index(), CameraUnavailable, _capture_and_analyze(), _get_engine(), liveness_min_swing(), _open_camera(), Open the camera, grab one frame, release it. Returns (observations, mean, std,… (+14 more)

### Community 150 - "jarvis_cache.py"
Cohesion: 0.16
Nodes (7): is_self_contained(), normalize_text(), Small, local-only cache helpers shared by jarvis.py: an env-flag reader,…, Lowercase, punctuation-stripped, whitespace-collapsed — so 'System status?' and…, TTLCache, test_normalize_and_self_contained(), test_ttl_cache_expiry_and_lru()

### Community 152 - "_StubSession"
Cohesion: 0.25
Nodes (5): Duck-types jarvis_stt_deepgram.StreamingSession's finish() surface for…, _StubSession, test_transcribe_pcm_falls_back_to_rest_when_stream_fails(), test_transcribe_pcm_too_short_audio_still_tears_down_stream_session(), test_transcribe_pcm_uses_streaming_session_result_when_present()

### Community 153 - "_autonomy_callbacks"
Cohesion: 0.16
Nodes (15): _autonomy_callbacks(), _autonomy_poll_mail(), _commands_in_flight(), _deadline_context(), _get_idle_seconds(), _meeting_headsup(), Seconds since the last system-wide keyboard/mouse input, via GetLastInputInfo.…, True if the user touched the keyboard/mouse within ACTIVE_IDLE_THRESHOLD_S… (+7 more)

### Community 154 - "jarvis_weather.py"
Cohesion: 0.50
Nodes (7): _fmt_temp(), _geocode(), _get(), _locate_by_ip(), Weather via Open-Meteo (free, no API key). QOL pass, 2026-09-23. Location: the…, resolve_location(), weather_report()

### Community 155 - "_handle_text_command_impl"
Cohesion: 0.14
Nodes (14): True when each held reminder should also be texted to the owner., should_forward(), _handle_text_command_impl(), _is_confirmation_yes(), A small, safe tool subset for a couple of simple intents that still need Claude…, Runs one already-transcribed command (typed or spoken) through the confirmation…, Read the whole reply aloud instead of the one-or-two-sentence spoken summary:…, A clear, short, non-negated affirmative. Whole-word matching (so 'yesterday'… (+6 more)

### Community 156 - "jarvis_agents.py"
Cohesion: 0.32
Nodes (10): budget_left(), due(), fill(), datetime, Background agents (2026-09-27, feature batch C1): small standing jobs ("every…, Time-based and queued-event triggers. mail_match is checked separately (needs a…, {subject}/{sender}/{path} placeholders in string step inputs., run() (+2 more)

### Community 157 - "fixture"
Cohesion: 0.40
Nodes (5): client(), dashboard(), db_path(), _private_environ(), fixture

### Community 158 - "jarvis_memory_search.py"
Cohesion: 0.29
Nodes (11): ensure(), format_results(), fts_query(), _ids(), Connection, Full-text memory search (2026-09-27, feature batch C4). Offline, SQLite FTS5…, User words -> a safe FTS5 query: each word quoted, OR-ed (BM25 still favours…, search() (+3 more)

### Community 159 - "_mail_answer"
Cohesion: 0.67
Nodes (3): _mail_answer(), test_a_clean_meeting_still_acts_at_high_confidence_and_structured_meeting_at_normal_floor(), test_wp1_subject_only_is_extracted_at_lower_confidence_and_logged()

### Community 160 - "read_attachments"
Cohesion: 0.20
Nodes (11): _db_path(), Path, Downloads (to a throwaway folder, deleted afterwards) and reads what it can.…, read_attachments(), AttGmail, Writes the 'downloaded' file where the real tool would., test_family_reply_prompt_frames_and_neutralises_what_the_sender_wrote(), __call__() (+3 more)

### Community 161 - "main"
Cohesion: 0.07
Nodes (33): _acquire_single_instance_lock(), _away_warn(), block_samples(), _dashboard_kill_background_task(), _face_greet(), _hold_modes(), main(), _notify_phone() (+25 more)

### Community 162 - "jarvis_voice_tone.py"
Cohesion: 0.24
Nodes (11): adapt(), analyze_tone(), _lexical_scores(), _norm_cmd(), _prosody(), Basic voice tone/sentiment awareness for Jarvis. Rule-based, deliberately…, Returns {"tone": category, "confidence": 0..1, "signals": [short strings]}.…, Adds two signals to an analyze_tone() result, using only the transcript and… (+3 more)

### Community 163 - "jarvis_pptx.py"
Cohesion: 0.25
Nodes (7): parse(), _plain(), Path, PowerPoint (.pptx) files from simple Markdown (2026-09-27, feature batch D3),…, write(), Feature batch 2026-09-27, Phase D (FEATURES.md): .pptx via write_file, weekly…, test_pptx_parse_and_write()

### Community 169 - "test_feature_batch_b.py"
Cohesion: 0.25
Nodes (4): db(), jarvis(), fixture, Feature batch 2026-09-27, Phase B (FEATURES.md): meeting notes, file index, app…

### Community 170 - "test_feature_batch_c.py"
Cohesion: 0.25
Nodes (7): db(), jarvis(), fixture, Feature batch 2026-09-27, Phase C (FEATURES.md): background agents, code…, test_code_search_fallbacks_and_secret_guard(), test_memory_fts_ranks_filters_and_forgets(), test_queue_gate_batches_and_digest_flushes()

### Community 171 - "Feature batch 2026-09-27"
Cohesion: 0.29
Nodes (6): Feature batch 2026-09-27, Phase A, Phase B, Phase C, Phase D (optional items), Verification (all phases)

### Community 172 - "_log_action_audit"
Cohesion: 0.09
Nodes (38): _agent_known_tools(), work(), _app_shortcut_route(), all_shortcuts(), app_matches(), _db(), delete(), ensure() (+30 more)

### Community 173 - "start"
Cohesion: 0.29
Nodes (6): _private_on_clipboard(), Password managers flag their copies; honour both conventions Windows' own…, _read_text(), start(), loop(), Thread

### Community 174 - "send_with_retry"
Cohesion: 0.33
Nodes (6): send() -> (ok, detail). Tries once, then retries every delay_s seconds, up to…, send_with_retry(), test_send_exception_counts_as_failure(), test_send_gives_up_after_five_retries(), test_send_retries_every_minute_then_succeeds(), send()

### Community 175 - "ForegroundTracker"
Cohesion: 0.40
Nodes (3): ForegroundTracker, loop(), Remembers the last real app window the user was in (skips Jarvis's own…

### Community 176 - "jarvis_improvement_report.py"
Cohesion: 0.47
Nodes (5): build(), _exists(), format_report(), Weekly "how could Jarvis work better for you" report (2026-09-27, feature batch…, suggestions()

### Community 179 - "_acted"
Cohesion: 0.50
Nodes (4): _acted(), test_wp3_dashboard_log_api_shape_and_filters(), test_wp3_log_filters_summary_and_explain(), test_wp3_tool_actions_and_spoken_summary()

## Knowledge Gaps
- **152 isolated node(s):** `state`, `ROUTES`, `ROUTES_WITH_CONTEXT`, `servicesPanel`, `servicesToggleBtn` (+147 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1329 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **14 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_build_app()` connect `_build_app` to `test_dashboard_llm_endpoints`, `_ConnectionManager`, `_set_broadcast`, `_origin_is_loopback`, `start`, `_execute_tool_impl`, `_provider`, `jarvis_dashboard.py`?**
  _High betweenness centrality (0.042) - this node is a cross-community bridge._
- **Why does `_execute_tool_impl()` connect `_execute_tool_impl` to `enable`, `jarvis_window_control.py`, `test_sleep.py`, `_briefing_fetchers`, `jarvis.py`, `FileWatcher`, `jarvis_memory_enhance.py`, `jarvis_sleep_mode.py`, `jarvis_guest_reminders.py`, `jarvis_workflow.py`, `jarvis_dynamic_tools.py`, `jarvis_proactive.py`, `_iso`, `jarvis_weather.py`, `download_image`, `jarvis_autonomy_organise.py`, `Path`, `test_dev_features.py`, `_claude_request`, `_log_action_audit`, `test_restart.py`, `poll_once`, `test_hardening.py`, `jarvis_billing.py`, `jarvis_tech_understanding.py`, `test_face.py`, `jarvis_face.py`, `enabled`, `enroll`, `test_guest_reminders.py`, `jarvis_focus.py`, `self_check_report`, `jarvis_task_scheduler.py`, `speak_text`, `_deterministic_intent_reply`?**
  _High betweenness centrality (0.033) - this node is a cross-community bridge._
- **Why does `j()` connect `j` to `test_hardening.py`, `test_feature_batch_a.py`, `test_voice_usage.py`, `test_sleep.py`, `jarvis_briefing.py`, `test_face.py`, `_FakeProc`, `test_feature_batch_b.py`, `test_feature_batch_c.py`, `test_gemini.py`, `test_sleep_mail.py`, `test_memory_edit.py`, `test_chief.py`, `CircuitBreaker`, `test_hold_modes.py`, `test_guest_reminders.py`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `_execute_tool_impl()` (e.g. with `_launch_focus_app()` and `_memory_db_connect()`) actually correct?**
  _`_execute_tool_impl()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 73 inferred relationships involving `timedelta` (e.g. with `due()` and `_agents_tick()`) actually correct?**
  _`timedelta` has 73 INFERRED edges - model-reasoned connections that need verification._
- **Are the 29 inferred relationships involving `_memory_db_connect()` (e.g. with `_app_shortcut_route()` and `_app_shortcuts_tool()`) actually correct?**
  _`_memory_db_connect()` has 29 INFERRED edges - model-reasoned connections that need verification._
- **What connects `state`, `ROUTES`, `ROUTES_WITH_CONTEXT` to the rest of the system?**
  _152 weakly-connected nodes found - possible documentation gaps or missing edges._