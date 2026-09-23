# Graph Report - jarvis-main2  (2026-09-23)

## Corpus Check
- 83 files · ~221,094 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 5 file(s) not represented in the graph (top: (none) 1, .vbs 1, .css 1)

## Summary
- 3166 nodes · 6886 edges · 145 communities (132 shown, 10 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 365 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `19c9817a`
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
- test_billing_summary_and_pagination
- jarvis_memory_enhance.py
- test_gemini.py
- test_sleep_mail.py
- _briefing_fetchers
- jarvis_workflow.py
- Full Autonomy Stack
- jarvis_dynamic_tools.py
- Tween
- test_cache.py
- TTSDiskCache
- jarvis_proactive.py
- _iso
- test_dev_features.py
- queue_or_deliver_notification
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
- Fake
- _narrating_claude
- main
- jarvis_cache.py
- Brag Plan: Jarvis
- SqliteKV
- jarvis_briefing.py
- test_billing_failures_are_plain_sentences
- ce
- _FakeProc
- ce
- test_qol.py
- test_restart.py
- speak_text
- na
- na
- Hyperframes Composition Brief: Jarvis
- test_face.py
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
- start_polling
- jarvis_tech_understanding.py
- transcribe
- enabled
- is_paused
- Google Maps location sharing -> "where is <person>?" (2026-09-19)
- test_deepgram_voice.py
- jarvis_face.py
- jarvis_autonomy_skills.py
- enroll
- jarvis_memory_consolidation.py
- qol.js
- _cb
- test_engine_refuses_when_models_are_missing_instead_of_letting_insightface_download
- _call
- build_system_blocks
- boom
- RuntimeError
- _fake_mcp_run_coro
- boom
- autonomy.js
- calibrate
- is_active
- jarvis_latency.py
- jarvis_dashboard.py
- _evaluate_base
- jarvis_autonomy.py
- _handle_text_command_impl
- jarvis
- synthesize
- StreamingSession
- Dashboard UI/UX overhaul (2026-09-22)
- enable
- FollowUpListener
- start
- test_dashboard_llm_endpoints
- _ConnectionManager
- test_run_agent_loop_multi_round_streams_narration_then_speaks_final_reply_once
- timedelta
- _set_broadcast
- jarvis_settings.py
- _origin_is_loopback
- Speed Upgrade: Deepgram-native voice pipeline + cloud-latency pass
- snake.js
- classify_intent
- stats_summary
- _connect
- jarvis_voice_tone.py
- _execute_tool_impl
- ensure_mcp_started
- CircuitBreaker
- jarvis_untrusted.py
- fixture
- test_guest_reminders.py
- StreamingSynthesis
- _forward_held_reminders
- fixture
- _scripted_claude
- _acted
- _deterministic_intent_reply
- test_complex_command_gets_full_tools
- run_agent_loop
- j
- _speak_session_stub
- Snake
- test_state_audit_rows_include_transcript_for_session_linking
- _set_dark_mode
- test_command_endpoint_invokes_run_command
- api_briefing
- test_short_notification_is_spoken_unchanged_without_a_claude_call
- _FakeOutputStream
- _claude_request
- jarvis_guest_reminders.py
- test_shutdown_via_run_shell_is_staged_not_run
- TTLCache
- refresh_session_context
- Google re-authentication (when tokens expire, every 7 days in Testing mode)

## God Nodes (most connected - your core abstractions)
1. `_execute_tool_impl()` - 121 edges
2. `Fake` - 103 edges
3. `_on()` - 60 edges
4. `_build_app()` - 55 edges
5. `_future()` - 55 edges
6. `main()` - 52 edges
7. `_iso()` - 47 edges
8. `_rows()` - 42 edges
9. `_memory_db_connect()` - 38 edges
10. `run_agent_loop()` - 37 edges

## Surprising Connections (you probably didn't know these)
- `compose()` --calls--> `wait()`  [INFERRED]
  jarvis_briefing.py → test_face.py
- `_run()` --indirect_call--> `started_at()`  [INFERRED]
  jarvis.py → jarvis_sleep_mode.py
- `_execute_tool_impl()` --calls--> `format_local_summary()`  [EXTRACTED]
  jarvis.py → jarvis_billing.py
- `_execute_tool_impl()` --calls--> `add_watched_folder()`  [EXTRACTED]
  jarvis.py → jarvis_filewatcher.py
- `_execute_tool_impl()` --calls--> `get_recent_file_events()`  [EXTRACTED]
  jarvis.py → jarvis_filewatcher.py

## Import Cycles
- None detected.

## Communities (145 total, 10 thin omitted)

### Community 0 - "test_autonomy.py"
Cohesion: 0.03
Nodes (29): skipif, _file(), parametrize, Tests for jarvis_autonomy.py, jarvis_dynamic_tools.py,…, The gate is untouched: an autonomous agent run that reaches a catastrophic…, jarvis.py wires run_tool to _execute_tool, so a skill step naming run_shell…, Autonomy on => injection hardening, the third-party bar and file organising are…, Like face: the new modules may never touch the catastrophic gate or import… (+21 more)

### Community 1 - "jarvis_window_control.py"
Cohesion: 0.07
Nodes (55): cancel_task(), _connect(), _db_path(), _free_slots(), _inflate_estimate(), list_task_queue(), _normalize(), _parse_busy_intervals() (+47 more)

### Community 2 - "brag-output-2026-09-19-001152/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 3 - "test_sleep.py"
Cohesion: 0.09
Nodes (16): status(), db(), jarvis(), _log_kind(), fixture, Tests for sleep trend stats and the wake-up digest. Run with: python -m pytest…, A .env setting read at import time (sleep goal) must reach the modules…, test_digest_important_first_then_lighter_note() (+8 more)

### Community 4 - "brag-output/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 5 - "FileWatcher"
Cohesion: 0.10
Nodes (15): add_watched_folder(), _connect(), _db_path(), _default_watch_paths(), FileWatcher, get_recent_file_events(), list_watched_folders(), Connection (+7 more)

### Community 6 - "jarvis.py"
Cohesion: 0.05
Nodes (64): _bytes_to_gb(), _bytes_to_mb(), check_system_health(), _choose_input_device(), _chrome_executable(), _craft_system_status_summary(), _cursor_executable(), _cursor_foreground_hwnd_win32() (+56 more)

### Community 8 - "jarvis_memory_enhance.py"
Cohesion: 0.13
Nodes (24): _connect(), _cosine(), _db_path(), link_facts(), list_code_patterns(), list_decisions(), Connection, Path (+16 more)

### Community 9 - "test_gemini.py"
Cohesion: 0.07
Nodes (48): call(), convert_messages(), convert_tools(), from_response(), get_provider(), Path, Request, Gemini (Google AI Studio) backend for Jarvis's LLM calls. Jarvis's callers all… (+40 more)

### Community 10 - "test_sleep_mail.py"
Cohesion: 0.05
Nodes (75): _autonomy_poll_mail(), New inbox messages (not the user's own, not yet seen by autonomy) with their…, _body_of(), _classify_critical(), _connect(), _db_path(), _emails(), _env_set() (+67 more)

### Community 11 - "_briefing_fetchers"
Cohesion: 0.06
Nodes (36): _autonomy_calendar_events(), _autonomy_create_event(), _autonomy_inbound(), _autonomy_mail_hook(), _briefing_fetchers(), calendar(), failed(), mail() (+28 more)

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
Cohesion: 0.06
Nodes (10): _gate_env(), _kv_db(), Tests for the caching layers (jarvis_cache.py + their wiring in jarvis.py). Run…, test_1h_ttl_rejection_falls_back_to_5m_and_retries(), test_busy_gate_holds_ordinary_notification_but_not_reminders(), test_bypass_busy_gate_still_respects_sleep_mode(), test_record_and_local_summary(), test_record_usage_never_raises() (+2 more)

### Community 17 - "TTSDiskCache"
Cohesion: 0.29
Nodes (5): Path, WAV files under one directory, keyed by hash. LRU by mtime (touched on every…, TTSDiskCache, test_tts_cache_skips_synthesis_on_repeat(), test_tts_disk_cache_roundtrip_and_eviction()

### Community 18 - "jarvis_proactive.py"
Cohesion: 0.27
Nodes (12): check_project_health(), _connect(), _db_path(), _fmt_findings(), _iter_source_files(), Connection, Path, Proactive problem detection for Jarvis. Scans a file or project directory for… (+4 more)

### Community 19 - "_iso"
Cohesion: 0.12
Nodes (36): accept_commitment(), add_project_action(), approve_suggestion(), _commitment(), delete_policy(), dismiss_suggestion(), _exec(), _expire_old() (+28 more)

### Community 20 - "test_dev_features.py"
Cohesion: 0.06
Nodes (59): analyze_repo(), _existing_tests(), generate_tests(), _public_api(), _py_files(), Path, Repository analysis, unit-test generation and module boilerplate. Deterministic…, New `<name>.py` plus a matching test file, in the style the repo already uses. (+51 more)

### Community 21 - "queue_or_deliver_notification"
Cohesion: 0.13
Nodes (22): _check_due_reminders(), flush_pending_notifications(), holding_reminders(), True while due reminders must be held (not spoken, no toast)., True after the owner said "no": reminders speak even with a stranger in view., reminders_allowed(), queue_or_deliver_notification(), Caller must already hold _session_context_lock. Writes to a temp file and… (+14 more)

### Community 22 - "CLAUDE.md"
Cohesion: 0.06
Nodes (30): API spend lookup (2026-09-18), Audit hardening (2026-09-21), Chief-of-staff batch (2026-09-23), Cloud-latency pass (2026-09-22), Confirmation gate follow-up (2026-09-18), Context7 + Windows-MCP (2026-09-23), Cost reporting, Dashboard (supervision UI) (+22 more)

### Community 23 - "app.js"
Cohesion: 0.08
Nodes (64): actOnPending(), AUTO_OPEN_SOURCES, badge(), connectWs(), coreHeatmap(), currentRoute(), esc(), fetchAuditResults() (+56 more)

### Community 24 - "_build_app"
Cohesion: 0.10
Nodes (33): _build_app(), api_autonomy(), api_autonomy_campaign_action(), api_autonomy_campaign_approve(), api_autonomy_commitment(), api_autonomy_commitment_accept(), api_autonomy_dry_run(), api_autonomy_enabled() (+25 more)

### Community 25 - "_tools"
Cohesion: 0.12
Nodes (14): test_c_skill_failure_stops_logs_the_step_and_notifies_exactly_once(), test_concurrent_extraction_of_the_same_item_inserts_it_once(), go(), test_d01_two_simultaneous_approvals_run_the_action_once(), go(), test_skill_creation_budget_holds_under_concurrency(), test_skills_never_mine_typing_http_or_secret_bearing_tools_or_huge_inputs(), test_wp5_cannot_smuggle_unknown_or_forbidden_tools_or_bad_shapes() (+6 more)

### Community 26 - "jarvis_sleep_mode.py"
Cohesion: 0.13
Nodes (16): _cancel_media_autopause(), _dark_mode_is_on(), _endpoint_volume_call(), _get_volume(), is_whitelisted_sender(), _log_duration_to_memory(), datetime, Sleep Mode for Jarvis. Self-contained, like the other jarvis_*.py modules: owns… (+8 more)

### Community 28 - "Tween"
Cohesion: 0.19
Nodes (21): _a(), Ao(), _assertThisInitialized(), cb(), cc(), ga(), gb(), hb() (+13 more)

### Community 29 - "download_image"
Cohesion: 0.10
Nodes (30): _contains_secret(), _http_request_tool(), _check_host(), _CheckedRedirects, _clean_stem(), download_image(), _fetch(), Path (+22 more)

### Community 30 - "jarvis_autonomy_organise.py"
Cohesion: 0.12
Nodes (39): _exec_rc(), add_root(), add_rule(), _copy_no_clobber(), handle_new_file(), handle_tool(), home(), _init() (+31 more)

### Community 31 - "Path"
Cohesion: 0.17
Nodes (16): _cleanup_old_logs(), _fmt_gb(), get_large_files_report(), _memory_db_path(), _print_large_files_breakdown(), Path, _quarantine_corrupt_memory_db(), Renames a corrupted memory DB aside (never deletes) so a fresh one can take its… (+8 more)

### Community 32 - "Fake"
Cohesion: 0.06
Nodes (69): Fake, _future(), _mail_answer(), _on(), FULL-PERMISSION MODEL: a confident, non-catastrophic item is acted on…, Records callback traffic; `answers` maps a marker in the prompt to the JSON the…, test_a_clean_meeting_still_acts_at_high_confidence_and_structured_meeting_at_normal_floor(), test_a_email_recipient_allowlist_is_optional_and_empty_means_unrestricted() (+61 more)

### Community 33 - "_narrating_claude"
Cohesion: 0.18
Nodes (8): _narrating_claude(), fake(), test_narrate_off_keeps_old_behaviour(), test_narrate_speaks_text_beside_a_tool_call_and_keeps_it_out_of_the_reply(), test_summary_cache_skips_second_claude_call(), test_tool_only_turn_falls_back_to_tool_result_by_default(), test_tool_result_fallback_can_be_disabled(), _tool_only_claude()

### Community 34 - "main"
Cohesion: 0.07
Nodes (34): _acquire_single_instance_lock(), block_samples(), api_command(), _sink(), _dashboard_get_sleep(), notify(), _dashboard_reject_pending(), _face_release_held_notifications() (+26 more)

### Community 35 - "jarvis_cache.py"
Cohesion: 0.38
Nodes (5): is_self_contained(), normalize_text(), Small, local-only cache helpers shared by jarvis.py: an env-flag reader,…, Lowercase, punctuation-stripped, whitespace-collapsed — so 'System status?' and…, test_normalize_and_self_contained()

### Community 36 - "Brag Plan: Jarvis"
Cohesion: 0.10
Nodes (19): Audio direction, Brag Plan: Jarvis, Duration: ~21 seconds, Format: landscape — 1920x1080, Hook (first 3.3 seconds), Key moments (the middle), Outro / punchline, Scene 1 — Hook — 3.3s (+11 more)

### Community 37 - "SqliteKV"
Cohesion: 0.31
Nodes (5): Connection, key -> text value with a created_at timestamp; max_age_s is checked on read,…, SqliteKV, _speech_summary_kv(), test_sqlite_kv_max_age_and_prune()

### Community 38 - "jarvis_briefing.py"
Cohesion: 0.17
Nodes (19): calendar_items(), compose(), deadline_items(), _hm(), mail_items(), datetime, Morning briefing v2 and "what's urgent?" (2026-09-23). One composition used by…, Calendar MCP (@cocal/google-calendar-mcp) list-events JSON -> "9:30 AM Standup"… (+11 more)

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

### Community 43 - "test_qol.py"
Cohesion: 0.06
Nodes (41): _clipboard_has_non_text(), _get_whisper_model(), _grab_selection(), handle_text_command(), handle_voice_command(), _handle_voice_command_impl(), _inflight_enter(), _inflight_exit() (+33 more)

### Community 44 - "test_restart.py"
Cohesion: 0.15
Nodes (18): check_syntax(), helper_command(), Event, Path, restart_jarvis: let Jarvis restart itself (voice: "restart yourself") to pick…, Error text for the first jarvis*.py that doesn't compile, else None., restart(), _stop_self() (+10 more)

### Community 45 - "speak_text"
Cohesion: 0.05
Nodes (34): _away_warn(), _build_sleep_digest(), _collapse_paths_for_speech(), _dashboard_approve_pending(), _sink(), _execute_confirmed_action(), _face_greet(), _humanize_path_for_speech() (+26 more)

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

### Community 52 - "_log_decision"
Cohesion: 0.13
Nodes (26): _work(), _audit(), _campaign_step(), _clean(), create_suggestion(), _direct_calendar(), _email_recipient_blocked(), _execute_auto() (+18 more)

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
Nodes (42): _read_file_tool(), classify(), default_dir(), _inside(), Path, Jarvis_Workspace: the default home for every file Jarvis creates, saves or…, Where a file should be written. Returns (path, "") or (None, reason it was…, Absolute paths are used as given; a relative one is looked up in the workspace… (+34 more)

### Community 65 - "jarvis_billing.py"
Cohesion: 0.14
Nodes (20): compute_cost(), _dollars(), _ensure_usage_table(), fetch_cost_buckets(), format_local_summary(), get_api_spend(), local_summary(), Connection (+12 more)

### Community 66 - "start_polling"
Cohesion: 0.15
Nodes (14): _lower_thread_priority(), poll_interval(), Run the poll below normal priority so an inference burst yields to the voice…, Start the low-duty background poll (no-op unless JARVIS_FACE_ENABLED=1). The…, Once the owner has been steadily in view with nobody else, look less often…, settled_poll_interval(), start_polling(), loop() (+6 more)

### Community 67 - "jarvis_tech_understanding.py"
Cohesion: 0.13
Nodes (14): analyze_python_file(), build_import_graph(), format_analysis_report(), format_error_report(), _imports_of(), _module_name_for(), parse_error(), Path (+6 more)

### Community 68 - "transcribe"
Cohesion: 0.12
Nodes (16): ndarray, Request, Deepgram Nova-3 STT (Speed Upgrade Phase 1.1, streaming added in the cloud-…, Connection warm-up (Phase 2.2): a near-silent clip so the TLS handshake happens…, Hard-timeout watchdog: urlopen's own timeout doesn't reliably fire on a wedged…, transcribe(), _urlopen_bounded(), warm() (+8 more)

### Community 69 - "enabled"
Cohesion: 0.08
Nodes (31): Any, after_turn(), _work(), _ask_model(), enabled(), extract_commitments_and_projects(), _fill(), _mark_seen() (+23 more)

### Community 72 - "is_paused"
Cohesion: 0.10
Nodes (28): away_enabled(), away_status(), get_setting(), _greeting_text(), invalidate_profile_cache(), is_paused(), _maybe_greet(), Camera privacy switch. Pausing is always allowed (it can only make things more… (+20 more)

### Community 73 - "Google Maps location sharing -> "where is <person>?" (2026-09-19)"
Cohesion: 0.25
Nodes (7): 1. Unofficial library (closest to the goal), 2. Telegram live location (official, stable), 3. Dedicated tracker (official, always-on), Before building, Google Maps location sharing -> "where is <person>?" (2026-09-19), Later, Recommendation

### Community 74 - "test_deepgram_voice.py"
Cohesion: 0.05
Nodes (23): _FakeSSEResponse, Tests for the Deepgram Speed Upgrade: jarvis_stt_deepgram.py,…, A background pre-synthesis that outlives PIPELINE_JOIN_TIMEOUT_S must not hang…, Voice-bug follow-up (2026-09-22): "Hi" and "thanks" answer with no Claude call…, Duck-types jarvis_stt_deepgram.StreamingSession's finish() surface for…, Voice-bug follow-up (2026-09-22): TTSDiskCache.get() has no integrity check on…, _sse_lines(), _sse_text_reply() (+15 more)

### Community 75 - "jarvis_face.py"
Cohesion: 0.05
Nodes (78): Exception, _already_enrolled(), _already_seen_recently(), away_grace_s(), _away_reset(), _away_step(), away_warn_s(), _camera_failed() (+70 more)

### Community 76 - "jarvis_autonomy_skills.py"
Cohesion: 0.24
Nodes (19): hard_disabled(), create_skill(), handle_tool(), _init(), _known(), list_skills(), note_turn(), _q() (+11 more)

### Community 77 - "enroll"
Cohesion: 0.10
Nodes (36): _clean_name(), delete(), delete_by_id(), describe_profiles(), enroll(), list_profiles(), (role, None) to enroll with, or (None, reason). The first person is always the…, Enroll a person. The first one becomes the Admin; later ones are `user`… (+28 more)

### Community 78 - "jarvis_memory_consolidation.py"
Cohesion: 0.28
Nodes (14): abstract_rules(), compress_old_summaries(), _connect(), consolidate(), _db_path(), _iso(), Connection, datetime (+6 more)

### Community 79 - "qol.js"
Cohesion: 0.28
Nodes (10): buildPalette(), closePalette(), loadPins(), openPalette(), palette, refreshSettings(), renderPalette(), runPalette() (+2 more)

### Community 80 - "_cb"
Cohesion: 0.08
Nodes (24): _capture(), _cb(), test_a_classifier_context_is_framed(), test_a_conversation_extraction_of_tool_derived_text_is_framed(), test_a_inbound_prompt_is_framed_sanitised_and_length_capped(), test_agent_replies_that_admit_failure_are_failures(), test_c_calendar_logs_distinguish_mcp_missing_from_failure_from_success(), test_c_structured_fallback_prompt_and_no_calendar_tool_is_a_clear_failure() (+16 more)

### Community 81 - "test_engine_refuses_when_models_are_missing_instead_of_letting_insightface_download"
Cohesion: 0.22
Nodes (7): fn(event_dict) is called after every audit row (kind/name/confidence/ts only)…, set_event_hook(), insightface would silently fetch the pack itself with no size/hash check,…, test_a_failing_lock_hook_does_not_break_polling(), test_engine_refuses_when_models_are_missing_instead_of_letting_insightface_download(), test_event_hook_gets_labels_only_and_a_broken_hook_is_harmless(), boom()

### Community 82 - "_call"
Cohesion: 0.08
Nodes (45): add_commitment(), agent_context_line(), _announce_pending(), _call(), _classifier_step(), _context_summary(), _env_int(), _file_scan() (+37 more)

### Community 83 - "build_system_blocks"
Cohesion: 0.08
Nodes (29): build_system_blocks(), build_system_prompt(), _dashboard_get_daily_items(), _fetch_projects(), get_active_facts_context(), get_projects_context(), get_skills_context(), get_user_profile_context() (+21 more)

### Community 84 - "boom"
Cohesion: 0.07
Nodes (20): The exact reported bug: saying "Hi" must produce a clean full reply, never the…, Voice-bug pass (2026-09-22): the filler phrase ("One moment.") and short…, test_claude_stream_first_round_gemini_provider_no_ops(), test_claude_stream_first_round_network_failure_returns_none(), boom(), test_deepgram_tts_circuit_breaker_trips_after_repeated_failures(), boom(), test_deterministic_reply_skips_run_agent_loop_entirely() (+12 more)

### Community 85 - "RuntimeError"
Cohesion: 0.09
Nodes (33): _connect(), dashboard_state(), _data_dir(), _DataBlob, _db_path(), download_models(), _dpapi(), blob() (+25 more)

### Community 86 - "_fake_mcp_run_coro"
Cohesion: 0.32
Nodes (6): _fake_mcp_run_coro(), _FakeMcpResult, execute_mcp_tool always builds the real coroutine before calling _mcp_run_coro;…, test_calendar_invalid_grant_embedded_in_json_still_gets_the_hint(), test_gmail_invalid_grant_becomes_a_reauth_instruction(), test_other_mcp_errors_are_unaffected_by_the_auth_hint()

### Community 87 - "boom"
Cohesion: 0.17
Nodes (12): test_daily_endpoint_exception_does_not_break(), boom(), test_get_pending_exception_does_not_break_state(), boom(), test_metrics_callback_exception_does_not_break_state(), boom(), test_services_endpoint_exception_does_not_break(), boom() (+4 more)

### Community 88 - "autonomy.js"
Cohesion: 0.51
Nodes (9): call(), card(), cardFlag(), h(), loadLog(), logRow(), refresh(), render() (+1 more)

### Community 89 - "calibrate"
Cohesion: 0.12
Nodes (12): calibrate(), camera_index(), CameraUnavailable, _capture_and_analyze(), _get_engine(), _open_camera(), Open the camera, grab one frame, release it. Returns (observations, mean, std,…, Dry run of the enrollment liveness check that stores NOTHING (no profile, no… (+4 more)

### Community 90 - "is_active"
Cohesion: 0.29
Nodes (10): Runs the Deepgram REST -> Fish -> Piper synth cascade (skipping engines that…, fish_audio_prosody_overrides(), is_active(), Piper SynthesisConfig kwargs for calmer speech while Sleep Mode is active, or…, Fish Audio's prosody equivalent of tts_overrides() above — same calmer/quieter-…, toggle(), tts_overrides(), _synthesize_and_cache() (+2 more)

### Community 91 - "jarvis_latency.py"
Cohesion: 0.16
Nodes (12): current(), end(), Per-voice-command latency tracker (Speed Upgrade Phase 0). One VoiceLatency…, recent(), start(), VoiceLatency, A narrated mid-task line speaks via Deepgram; the final (longer) reply's…, test_deterministic_path_recorded_on_voice_latency() (+4 more)

### Community 92 - "jarvis_dashboard.py"
Cohesion: 0.15
Nodes (24): api_audit(), api_clear_finished_sessions(), api_recent_commands(), api_state(), _build_state(), clear_finished_sessions(), _connect(), _db_path() (+16 more)

### Community 93 - "_evaluate_base"
Cohesion: 0.18
Nodes (12): _env_float(), _evaluate_base(), evaluate_policy(), _norm_dt(), Name <a@b.com>' -> 'a@b.com', lower-cased. A display name can say anything, so…, Exact address (audit E-02: substring matching let a lookalike or display name…, -> ('auto_act' | 'record' | 'ask' | 'ignore', reason). FULL-PERMISSION MODEL:…, A clear meeting: a title and a plausible start datetime. (+4 more)

### Community 94 - "jarvis_autonomy.py"
Cohesion: 0.09
Nodes (43): _action_for_commitment(), approve_campaign(), _brief(), budgets(), _deadline_scan(), dry_run(), explain(), _find_duplicate() (+35 more)

### Community 95 - "_handle_text_command_impl"
Cohesion: 0.14
Nodes (29): answer(), has_open_question(), on_stranger_arrived(), on_stranger_left(), Handle a reply to an open question. Returns the reply to send back, or None if…, True when each held reminder should also be texted to the owner., should_forward(), state() (+21 more)

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

### Community 100 - "enable"
Cohesion: 0.27
Nodes (16): disable(), enable(), _get_state(), kind='nap' runs the exact same mode (quiet notifications, mail take-over, dark…, _set_state(), set_system_action_handler(), _fake_env(), A mode started by the previous version (volume_steps only) must still end… (+8 more)

### Community 101 - "FollowUpListener"
Cohesion: 0.11
Nodes (23): deque, FollowUpListener, ndarray, Follow-up window (QOL pass, 2026-09-23): after Jarvis answers a voice command,…, chained: this reply answered a hands-free follow-up. After MAX_CHAIN of those…, Call with every mic block while push-to-talk isn't held and Jarvis isn't…, draw(), main() (+15 more)

### Community 102 - "start"
Cohesion: 0.67
Nodes (3): Blocking call — run this in its own daemon thread from jarvis.py's main().…, start(), _metrics_loop()

### Community 103 - "test_dashboard_llm_endpoints"
Cohesion: 0.50
Nodes (5): api_llm(), api_set_llm(), test_dashboard_llm_endpoints(), get_llm(), set_llm()

### Community 105 - "test_run_agent_loop_multi_round_streams_narration_then_speaks_final_reply_once"
Cohesion: 0.13
Nodes (8): Audit scenario: round 0 streams narration + a tool_use (so the loop must…, test_reply_already_spoken_flag_resets_between_commands(), test_run_agent_loop_falls_back_to_non_streaming_when_stream_fails(), fake_request(), test_run_agent_loop_multi_round_streams_narration_then_speaks_final_reply_once(), test_run_agent_loop_streams_text_only_final_reply_and_marks_spoken(), fake_stream(), test_smart_model_request_has_thinking_and_skips_live_stream()

### Community 106 - "timedelta"
Cohesion: 0.08
Nodes (26): build_calendar_args(), Maps an event payload onto a Calendar MCP create-event tool's own input schema…, Fake callbacks whose task queue is the REAL jarvis_task_scheduler (same…, _scheduler_callbacks(), test_a_classifier_actions_influenced_by_inbound_mail_face_the_third_party_bar(), test_c01_approved_background_task_is_scheduled_not_left_pending(), test_c01_campaign_step_gets_a_slot_and_a_stale_one_is_failed(), test_campaign_step_orphaned_in_running_after_a_restart_is_recovered() (+18 more)

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

### Community 112 - "classify_intent"
Cohesion: 0.29
Nodes (7): classify_intent(), parametrize, test_briefing_intents(), parametrize, test_classify_intent(), parametrize, test_new_intents()

### Community 113 - "stats_summary"
Cohesion: 0.17
Nodes (17): _connect(), _db_path(), _hhmm(), _period_stats(), Connection, Path, Stats over the `days` calendar days ending at end_day (inclusive): tracked…, Read-only sleep trends for the dashboard, from sleep_log alone (no new tables).… (+9 more)

### Community 114 - "_connect"
Cohesion: 0.25
Nodes (11): configure(), _connect(), _db_path(), init_autonomy_tables(), Connection, Path, Wire callbacks and arm the tick. jarvis.py's scheduler loop then calls…, Idempotent. Creates every table this module owns and seeds the single built-in… (+3 more)

### Community 115 - "jarvis_voice_tone.py"
Cohesion: 0.32
Nodes (7): analyze_tone(), _lexical_scores(), _prosody(), Basic voice tone/sentiment awareness for Jarvis. Rule-based, deliberately…, Short line to fold into the agent system prompt for this turn; empty string if…, Returns {"tone": category, "confidence": 0..1, "signals": [short strings]}.…, tone_context_line()

### Community 116 - "_execute_tool_impl"
Cohesion: 0.04
Nodes (68): _apply_memory_db_pragmas(), _autonomy_callbacks(), _background_tasks_dir(), cancel_reminder(), _catastrophic_reason(), _check_background_tasks(), click_at(), _commands_in_flight() (+60 more)

### Community 117 - "ensure_mcp_started"
Cohesion: 0.08
Nodes (23): AbstractEventLoop, _dashboard_get_services_status(), _ensure_mcp_loop(), ensure_mcp_started(), get_mcp_tool_schemas(), _load_mcp_server_configs(), _mcp_connect_all_async(), _mcp_connect_one() (+15 more)

### Community 118 - "CircuitBreaker"
Cohesion: 0.17
Nodes (8): CircuitBreaker, Trips after `threshold` consecutive failures and refuses calls for…, jarvis(), fixture, test_circuit_breaker_success_resets_failures(), test_circuit_breaker_trips_and_cools_down(), test_stt_backend_recovers_after_breaker_cooldown(), flaky()

### Community 119 - "jarvis_untrusted.py"
Cohesion: 0.40
Nodes (5): canonical(), _fix_word(), Handling of text written by other people (mail, messages, file names, web…, The text as a human would read it: NFKC, invisible characters removed, look-…, Match

### Community 120 - "fixture"
Cohesion: 0.25
Nodes (8): A(), client(), D(), O(), fixture, S(), test_b_tool_and_dashboard_routes(), dash()

### Community 121 - "test_guest_reminders.py"
Cohesion: 0.19
Nodes (15): set_disabled(), _held(), Tests for jarvis_guest_reminders (the stranger -> "disable reminders?" Telegram…, test_default_group_safe_hold_still_lets_urgent_reminders_speak(), test_flush_on_any_command_does_not_leak_held_reminders(), test_pending_question_holds_reminders_but_does_not_text_them_yet(), test_reenabling_reads_out_the_held_reminders(), test_reminders_are_held_texted_and_silent_once_disabled() (+7 more)

### Community 122 - "StreamingSynthesis"
Cohesion: 0.13
Nodes (11): One request to Deepgram's streaming speak WebSocket. Usage: session =…, Generator yielding raw int16 PCM bytes as Aura 2 generates them. Text…, StreamingSynthesis, _FakeSpeakWebsocketLib, _FakeSpeakWS, create_connection(), test_streaming_synthesis_chunks_yields_only_binary_frames(), test_streaming_synthesis_connect_failure_returns_false() (+3 more)

### Community 123 - "_forward_held_reminders"
Cohesion: 0.40
Nodes (5): _forward_held_reminders(), forward_reminder(), Text a held reminder to the owner's phone (best effort; it stays queued either…, Text every held reminder to the owner's Telegram (once each). Used when…, _send()

### Community 124 - "fixture"
Cohesion: 0.40
Nodes (5): client(), dashboard(), db_path(), _private_environ(), fixture

### Community 125 - "_scripted_claude"
Cohesion: 0.33
Nodes (6): Fake Claude: with a tool_name, the first call requests it and the next returns…, _scripted_claude(), test_reply_cache_disabled_by_env(), test_reply_cache_never_stores_mutating_turns(), test_reply_cache_serves_readonly_repeat_without_claude(), test_reply_cache_skips_context_dependent_and_toolless_turns()

### Community 126 - "_acted"
Cohesion: 0.50
Nodes (4): _acted(), test_wp3_dashboard_log_api_shape_and_filters(), test_wp3_log_filters_summary_and_explain(), test_wp3_tool_actions_and_spoken_summary()

### Community 127 - "_deterministic_intent_reply"
Cohesion: 0.17
Nodes (13): briefing_report(), _deterministic_intent_reply(), _parse_duration_s(), Morning briefing ("morning") or needs-you summary ("urgent"): {"sections":…, Local handling for timers and the stopwatch; None = let the agent loop handle…, Zero-LLM-call answers for the handful of intents that are pure local…, _say_duration(), _shorter_reply() (+5 more)

### Community 128 - "test_complex_command_gets_full_tools"
Cohesion: 0.50
Nodes (3): test_complex_command_gets_full_tools(), test_volume_command_gets_reduced_tools(), fake_run_agent_loop()

### Community 129 - "run_agent_loop"
Cohesion: 0.08
Nodes (33): _append_history(), _autonomy_run_agent(), enabled(), JARVIS_<LAYER>_CACHE env flag, default on. Read on every call so it can be…, record(), stable_hash(), _cached_tools(), _history_snapshot() (+25 more)

### Community 130 - "j"
Cohesion: 0.18
Nodes (9): configure(), reset(), j(), Phone, fixture, Stands in for Telegram: records what Jarvis texts, and can be made to fail., test_no_telegram_means_no_question_and_no_new_hold(), test_reminders_mode_tool_from_any_source() (+1 more)

### Community 131 - "_speak_session_stub"
Cohesion: 0.14
Nodes (11): Duck-types tts_deepgram.StreamingSynthesis for _speak_streamed tests:…, Real audio already played before the interruption — must be reported as handled…, The critical Phase B safety property: the background pre-fetch thread for the…, _speak_session_stub(), test_speak_streamed_failure_before_any_audio_is_not_handled(), test_speak_streamed_happy_path(), test_speak_streamed_mid_stream_failure_after_audio_is_handled_but_incomplete(), test_speak_text_caches_complete_streamed_audio_for_reuse() (+3 more)

### Community 132 - "Snake"
Cohesion: 0.24
Nodes (5): Simple Snake game using tkinter. Arrow keys / WASD to move, R to restart., Snake, The reminders question runs before the confirmation gate, and cancels (never…, test_a_yes_for_the_question_never_approves_a_staged_catastrophic_action(), test_the_gate_still_works_normally_when_no_question_is_open()

### Community 134 - "_set_dark_mode"
Cohesion: 0.40
Nodes (5): _broadcast_theme_change(), Tells running apps the theme changed (what Windows Settings does). The registry…, _set_dark_mode(), test_broadcast_never_runs_under_pytest(), test_theme_change_is_broadcast_after_the_registry_write()

### Community 139 - "_claude_request"
Cohesion: 0.05
Nodes (49): HTMLParser, system(), _claude_failure_reason(), _claude_in_cooldown(), _claude_live_problem(), _claude_request(), _claude_stream_first_round(), _speak_ready() (+41 more)

### Community 140 - "jarvis_guest_reminders.py"
Cohesion: 0.25
Nodes (8): _norm(), parse_yes_no(), Reminders while an unrecognized person is at the computer (driven by the face…, True/False for a clear yes/no, None otherwise. Deliberately strict: the WHOLE…, status(), parametrize, test_context_phrases_mean_opposite_things_in_the_two_questions(), test_parse_yes_no_is_strict_whole_message()

### Community 145 - "refresh_session_context"
Cohesion: 0.29
Nodes (7): _get_active_window_title(), _guess_project_from_window_title(), Best-effort title of the current foreground window (Windows only) — used purely…, Best-effort project/document name from a window title such as "jarvis.py -…, Updates last-active-window/project and prunes recent_tasks older than…, refresh_session_context(), _safe_parse_iso()

### Community 147 - "Google re-authentication (when tokens expire, every 7 days in Testing mode)"
Cohesion: 0.50
Nodes (3): Calendar, Gmail, Google re-authentication (when tokens expire, every 7 days in Testing mode)

## Knowledge Gaps
- **138 isolated node(s):** `state`, `ROUTES`, `ROUTES_WITH_CONTEXT`, `servicesPanel`, `servicesToggleBtn` (+133 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1112 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_execute_tool_impl()` connect `_execute_tool_impl` to `jarvis_window_control.py`, `test_sleep.py`, `FileWatcher`, `jarvis.py`, `jarvis_memory_enhance.py`, `_briefing_fetchers`, `jarvis_guest_reminders.py`, `_claude_request`, `jarvis_dynamic_tools.py`, `jarvis_workflow.py`, `jarvis_proactive.py`, `test_dev_features.py`, `queue_or_deliver_notification`, `download_image`, `jarvis_autonomy_organise.py`, `Path`, `test_restart.py`, `speak_text`, `test_face.py`, `test_hardening.py`, `jarvis_billing.py`, `jarvis_tech_understanding.py`, `is_paused`, `jarvis_autonomy_skills.py`, `enroll`, `build_system_blocks`, `is_active`, `jarvis_autonomy.py`, `enable`, `test_guest_reminders.py`, `_forward_held_reminders`, `_deterministic_intent_reply`?**
  _High betweenness centrality (0.059) - this node is a cross-community bridge._
- **Why does `_build_app()` connect `_build_app` to `main`, `start`, `test_dashboard_llm_endpoints`, `api_briefing`, `_ConnectionManager`, `_set_broadcast`, `_origin_is_loopback`, `jarvis_dashboard.py`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **Why does `j()` connect `j` to `jarvis`, `test_hardening.py`, `test_sleep.py`, `_FakeProc`, `test_gemini.py`, `test_sleep_mail.py`, `CircuitBreaker`, `test_guest_reminders.py`?**
  _High betweenness centrality (0.014) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `_execute_tool_impl()` (e.g. with `_launch_focus_app()` and `_memory_db_connect()`) actually correct?**
  _`_execute_tool_impl()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 64 inferred relationships involving `timedelta` (e.g. with `_action_for_commitment()` and `agent_context_line()`) actually correct?**
  _`timedelta` has 64 INFERRED edges - model-reasoned connections that need verification._
- **What connects `state`, `ROUTES`, `ROUTES_WITH_CONTEXT` to the rest of the system?**
  _138 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `test_autonomy.py` be split into smaller, more focused modules?**
  _Cohesion score 0.02508361204013378 - nodes in this community are weakly interconnected._