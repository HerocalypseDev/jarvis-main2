# Graph Report - jarvis-main2  (2026-09-22)

## Corpus Check
- 74 files · ~205,883 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 1, .vbs 1, .css 1)

## Summary
- 2968 nodes · 6495 edges · 137 communities (121 shown, 13 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 326 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `e0e9dd2b`
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
- jarvis_sleep_mail.py
- _planner_step
- jarvis_workflow.py
- Full Autonomy Stack
- jarvis_dynamic_tools.py
- Tween
- test_cache.py
- TTSDiskCache
- jarvis_proactive.py
- jarvis_autonomy.py
- _run_enrollment
- queue_or_deliver_notification
- CLAUDE.md
- app.js
- _build_app
- _tools
- read_attachments
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
- jarvis
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
- _body_of
- jarvis_tech_understanding.py
- transcribe
- _call
- is_paused
- Google Maps location sharing -> "where is <person>?" (2026-09-19)
- test_deepgram_voice.py
- jarvis_face.py
- jarvis_autonomy_skills.py
- test_face.py
- jarvis_memory_consolidation.py
- _handle_family
- Fake
- _InsightEngine
- timedelta
- build_system_blocks
- boom
- RuntimeError
- _fake_mcp_run_coro
- ensure_mcp_started
- autonomy.js
- calibrate
- _mail_answer
- jarvis_latency.py
- jarvis_dashboard.py
- _evaluate_base
- enabled
- test_guest_reminders.py
- jarvis
- synthesize
- StreamingSession
- Dashboard UI/UX overhaul (2026-09-22)
- _connect
- snake.cpp
- start
- test_dashboard_llm_endpoints
- _ConnectionManager
- jarvis_cache.py
- _scheduler_callbacks
- _set_broadcast
- test_1h_ttl_rejection_falls_back_to_5m_and_retries
- _origin_is_loopback
- Speed Upgrade: Deepgram-native voice pipeline + cloud-latency pass
- snake.js
- _StubSession
- send_with_retry
- _speak_streamed
- _handle_text_command_impl
- _execute_tool_impl
- test_short_notification_is_spoken_unchanged_without_a_claude_call
- CircuitBreaker
- jarvis_untrusted.py
- fixture
- _work
- StreamingSynthesis
- _narrating_claude
- test_pipeline_join_timeout_recovers_without_hanging_or_dropping_content
- test_dev_features.py
- test_tick_runs_every_30_minutes_only_while_asleep
- _DuckDuckGoResultParser
- _autonomy_callbacks
- _speak_session_stub
- test_run_agent_loop_multi_round_streams_narration_then_speaks_final_reply_once
- _FakeOutputStream
- _claude_request
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
- `_execute_tool_impl()` --calls--> `format_local_summary()`  [EXTRACTED]
  jarvis.py → jarvis_billing.py
- `_execute_tool_impl()` --calls--> `is_dynamic()`  [EXTRACTED]
  jarvis.py → jarvis_dynamic_tools.py
- `_execute_tool_impl()` --calls--> `add_watched_folder()`  [EXTRACTED]
  jarvis.py → jarvis_filewatcher.py
- `_execute_tool_impl()` --calls--> `get_recent_file_events()`  [EXTRACTED]
  jarvis.py → jarvis_filewatcher.py
- `_execute_tool_impl()` --calls--> `list_watched_folders()`  [EXTRACTED]
  jarvis.py → jarvis_filewatcher.py

## Import Cycles
- None detected.

## Communities (137 total, 13 thin omitted)

### Community 0 - "test_autonomy.py"
Cohesion: 0.03
Nodes (31): skipif, _acted(), _file(), Tests for jarvis_autonomy.py, jarvis_dynamic_tools.py,…, jarvis.py wires run_tool to _execute_tool, so a skill step naming run_shell…, Autonomy on => injection hardening, the third-party bar and file organising are…, test_b_a_file_still_downloading_is_retried_not_dropped(), test_b_a_symlink_that_leaves_the_folder_is_rejected() (+23 more)

### Community 1 - "jarvis_window_control.py"
Cohesion: 0.14
Nodes (29): arrange_windows(), _cascade_rects(), close_window(), _connect(), _db_path(), delete_layout(), _find(), _grid_rects() (+21 more)

### Community 2 - "brag-output-2026-09-19-001152/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 3 - "jarvis_sleep_mode.py"
Cohesion: 0.05
Nodes (68): _broadcast_theme_change(), _cancel_media_autopause(), _connect(), _dark_mode_is_on(), _db_path(), disable(), enable(), _endpoint_volume_call() (+60 more)

### Community 4 - "brag-output/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 5 - "FileWatcher"
Cohesion: 0.10
Nodes (15): add_watched_folder(), _connect(), _db_path(), _default_watch_paths(), FileWatcher, get_recent_file_events(), list_watched_folders(), Connection (+7 more)

### Community 6 - "jarvis.py"
Cohesion: 0.06
Nodes (56): _bytes_to_gb(), _bytes_to_mb(), check_system_health(), _choose_input_device(), _chrome_executable(), _craft_system_status_summary(), _cursor_executable(), _cursor_foreground_hwnd_win32() (+48 more)

### Community 8 - "jarvis_memory_enhance.py"
Cohesion: 0.13
Nodes (22): _connect(), _cosine(), _db_path(), link_facts(), list_code_patterns(), list_decisions(), Connection, Path (+14 more)

### Community 9 - "test_gemini.py"
Cohesion: 0.07
Nodes (48): call(), convert_messages(), convert_tools(), from_response(), get_provider(), Path, Request, Gemini (Google AI Studio) backend for Jarvis's LLM calls. Jarvis's callers all… (+40 more)

### Community 10 - "jarvis_sleep_mail.py"
Cohesion: 0.15
Nodes (24): _autonomy_poll_mail(), New inbox messages (not the user's own, not yet seen by autonomy) with their…, _classify_critical(), _connect(), _db_path(), _emails(), _env_set(), _handled() (+16 more)

### Community 11 - "_planner_step"
Cohesion: 0.20
Nodes (18): accept_commitment(), _action_for_commitment(), _commitment(), _deadline_scan(), dry_run(), get_setting(), _ingest(), _meta() (+10 more)

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
Cohesion: 0.06
Nodes (8): _gate_env(), _kv_db(), Tests for the caching layers (jarvis_cache.py + their wiring in jarvis.py). Run…, test_busy_gate_holds_ordinary_notification_but_not_reminders(), test_bypass_busy_gate_still_respects_sleep_mode(), test_enabled_flag(), test_record_and_local_summary(), test_shutdown_via_run_shell_is_staged_not_run()

### Community 17 - "TTSDiskCache"
Cohesion: 0.29
Nodes (5): Path, WAV files under one directory, keyed by hash. LRU by mtime (touched on every…, TTSDiskCache, test_tts_cache_skips_synthesis_on_repeat(), test_tts_disk_cache_roundtrip_and_eviction()

### Community 18 - "jarvis_proactive.py"
Cohesion: 0.27
Nodes (12): check_project_health(), _connect(), _db_path(), _fmt_findings(), _iter_source_files(), Connection, Path, Proactive problem detection for Jarvis. Scans a file or project directory for… (+4 more)

### Community 19 - "jarvis_autonomy.py"
Cohesion: 0.09
Nodes (52): add_project_action(), approve_campaign(), approve_suggestion(), _brief(), budgets(), delete_policy(), dismiss_suggestion(), _exec() (+44 more)

### Community 20 - "_run_enrollment"
Cohesion: 0.18
Nodes (18): _already_seen_recently(), _decrypt(), get_snapshot(), identify(), load_embeddings(), _pack_embeddings(), _profiles_for_matching(), ndarray (+10 more)

### Community 21 - "queue_or_deliver_notification"
Cohesion: 0.06
Nodes (48): _autonomy_run_agent(), _background_tasks_dir(), _check_background_tasks(), _check_due_reminders(), _forward_held_reminders(), _get_active_window_title(), _get_last_skill_run(), _guess_project_from_window_title() (+40 more)

### Community 22 - "CLAUDE.md"
Cohesion: 0.08
Nodes (25): API spend lookup (2026-09-18), Audit hardening (2026-09-21), Cloud-latency pass (2026-09-22), Confirmation gate follow-up (2026-09-18), Cost reporting, Dashboard (supervision UI), Face recognition (2026-09-19), Full Autonomy stack (2026-09-20) (+17 more)

### Community 23 - "app.js"
Cohesion: 0.08
Nodes (64): actOnPending(), AUTO_OPEN_SOURCES, badge(), connectWs(), coreHeatmap(), currentRoute(), esc(), fetchAuditResults() (+56 more)

### Community 24 - "_build_app"
Cohesion: 0.10
Nodes (36): _build_app(), api_autonomy(), api_autonomy_campaign_action(), api_autonomy_campaign_approve(), api_autonomy_commitment(), api_autonomy_commitment_accept(), api_autonomy_dry_run(), api_autonomy_enabled() (+28 more)

### Community 25 - "_tools"
Cohesion: 0.12
Nodes (14): test_c_skill_failure_stops_logs_the_step_and_notifies_exactly_once(), test_concurrent_extraction_of_the_same_item_inserts_it_once(), go(), test_d01_two_simultaneous_approvals_run_the_action_once(), go(), test_skill_creation_budget_holds_under_concurrency(), test_skills_never_mine_typing_http_or_secret_bearing_tools_or_huge_inputs(), test_wp5_cannot_smuggle_unknown_or_forbidden_tools_or_bad_shapes() (+6 more)

### Community 26 - "read_attachments"
Cohesion: 0.24
Nodes (9): Path, Downloads (to a throwaway folder, deleted afterwards) and reads what it can.…, read_attachments(), AttGmail, Writes the 'downloaded' file where the real tool would., test_family_reply_prompt_frames_and_neutralises_what_the_sender_wrote(), __call__(), test_oversized_and_failed_downloads_are_reported() (+1 more)

### Community 27 - "test_dashboard.py"
Cohesion: 0.05
Nodes (20): client(), dashboard(), db_path(), fixture, QA regression suite for jarvis_dashboard.py. Run with: python -m pytest…, Post-overhaul UX audit (2026-09-22): the Activity route's rows come from…, test_command_endpoint_invokes_run_command(), test_daily_endpoint_exception_does_not_break() (+12 more)

### Community 28 - "Tween"
Cohesion: 0.19
Nodes (21): _a(), Ao(), _assertThisInitialized(), cb(), cc(), ga(), gb(), hb() (+13 more)

### Community 29 - "download_image"
Cohesion: 0.11
Nodes (27): _check_host(), _CheckedRedirects, _clean_stem(), download_image(), _fetch(), Path, download_image: fetch one image URL and save it to a single fixed folder.…, i.pinimg.com/236x/.. or /736x/.. (a thumbnail) -> /originals/.. (full size). (+19 more)

### Community 30 - "jarvis_autonomy_organise.py"
Cohesion: 0.12
Nodes (38): _exec_rc(), add_root(), add_rule(), _copy_no_clobber(), handle_new_file(), handle_tool(), home(), _init() (+30 more)

### Community 31 - "Path"
Cohesion: 0.11
Nodes (24): _dashboard_get_daily_items(), _fmt_gb(), get_large_files_report(), _load_skills(), _memory_db_path(), _own_code_context_line(), _print_large_files_breakdown(), Path (+16 more)

### Community 32 - "_on"
Cohesion: 0.05
Nodes (63): _future(), _on(), FULL-PERMISSION MODEL: a confident, non-catastrophic item is acted on…, test_a_classifier_actions_influenced_by_inbound_mail_face_the_third_party_bar(), test_a_email_recipient_allowlist_is_optional_and_empty_means_unrestricted(), test_a_injected_email_at_medium_confidence_does_not_auto_act_and_says_why(), test_a_third_party_bar_matrix(), test_a_user_after_turn_still_auto_acts_at_the_normal_floor() (+55 more)

### Community 33 - "_scripted_claude"
Cohesion: 0.15
Nodes (11): Fake Claude: with a tool_name, the first call requests it and the next returns…, _scripted_claude(), fake(), test_reply_cache_disabled_by_env(), test_reply_cache_never_stores_mutating_turns(), test_reply_cache_serves_readonly_repeat_without_claude(), test_reply_cache_skips_context_dependent_and_toolless_turns(), test_summary_cache_skips_second_claude_call() (+3 more)

### Community 34 - "main"
Cohesion: 0.06
Nodes (41): _acquire_single_instance_lock(), block_samples(), _dashboard_get_pending(), _dashboard_get_sleep(), _dashboard_get_usage(), _dashboard_kill_background_task(), _get_whisper_model(), handle_text_command() (+33 more)

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

### Community 41 - "jarvis"
Cohesion: 0.22
Nodes (7): reset_stats(), delegation(), _FakeProc, jarvis(), fixture, jarvis(), fixture

### Community 42 - "ce"
Cohesion: 0.24
Nodes (14): Ae(), ce(), $d(), ee(), ha(), ka(), le(), me() (+6 more)

### Community 43 - "test_sleep_mail.py"
Cohesion: 0.18
Nodes (18): db(), FakeGmail, jarvis(), fixture, Tests for the Sleep Mode mail take-over. Run: python -m pytest…, _run(), _search(), test_family_email_gets_reply_recorded_and_not_repeated() (+10 more)

### Community 44 - "test_restart.py"
Cohesion: 0.15
Nodes (18): check_syntax(), helper_command(), Event, Path, restart_jarvis: let Jarvis restart itself (voice: "restart yourself") to pick…, Error text for the first jarvis*.py that doesn't compile, else None., restart(), _stop_self() (+10 more)

### Community 45 - "run_agent_loop"
Cohesion: 0.06
Nodes (52): _away_warn(), enabled(), JARVIS_<LAYER>_CACHE env flag, default on. Read on every call so it can be…, record(), stable_hash(), _cached_tools(), Tool definitions for the model, sorted so the tool prefix (and its prompt…, schemas() (+44 more)

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
Cohesion: 0.11
Nodes (46): describe_presence(), enabled(), _fresh(), group_safe(), group_safe_suppress(), list_snapshots(), poll_once(), _Presence (+38 more)

### Community 50 - "la"
Cohesion: 0.53
Nodes (6): Animation(), Da(), la(), ma(), Ua(), Va()

### Community 51 - "la"
Cohesion: 0.53
Nodes (6): Animation(), Da(), la(), ma(), Ua(), Va()

### Community 52 - "_log_decision"
Cohesion: 0.15
Nodes (23): Any, _ask_model(), _audit(), _clean(), create_suggestion(), _execute_auto(), _log_decision(), _notify_throttled() (+15 more)

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
Nodes (39): _read_file_tool(), classify(), default_dir(), _inside(), Path, Jarvis_Workspace: the default home for every file Jarvis creates, saves or…, Where a file should be written. Returns (path, "") or (None, reason it was…, Absolute paths are used as given; a relative one is looked up in the workspace… (+31 more)

### Community 65 - "jarvis_billing.py"
Cohesion: 0.15
Nodes (19): compute_cost(), _dollars(), _ensure_usage_table(), fetch_cost_buckets(), format_local_summary(), get_api_spend(), local_summary(), Connection (+11 more)

### Community 66 - "_body_of"
Cohesion: 0.25
Nodes (8): _body_of(), parse_attachments(), read_email lists attachments as '- name (mime, N KB, ID: xxx)' under…, (thread_id, body) from read_email output., Drops the quoted earlier thread from a reply: everything from an 'On ...…, _strip_quoted(), test_parse_attachments_and_body_excludes_listing(), test_quoted_history_is_stripped_from_replies()

### Community 67 - "jarvis_tech_understanding.py"
Cohesion: 0.13
Nodes (14): analyze_python_file(), build_import_graph(), format_analysis_report(), format_error_report(), _imports_of(), _module_name_for(), parse_error(), Path (+6 more)

### Community 68 - "transcribe"
Cohesion: 0.12
Nodes (16): ndarray, Request, Deepgram Nova-3 STT (Speed Upgrade Phase 1.1, streaming added in the cloud-…, Connection warm-up (Phase 2.2): a near-silent clip so the TLS handshake happens…, Hard-timeout watchdog: urlopen's own timeout doesn't reliably fire on a wedged…, transcribe(), _urlopen_bounded(), warm() (+8 more)

### Community 69 - "_call"
Cohesion: 0.08
Nodes (44): add_commitment(), _announce_pending(), _call(), _campaign_step(), _classifier_step(), _context_summary(), _env_int(), extract_commitments_and_projects() (+36 more)

### Community 72 - "is_paused"
Cohesion: 0.08
Nodes (31): away_enabled(), away_status(), get_setting(), _greeting_text(), invalidate_profile_cache(), is_paused(), _maybe_greet(), Camera privacy switch. Pausing is always allowed (it can only make things more… (+23 more)

### Community 73 - "Google Maps location sharing -> "where is <person>?" (2026-09-19)"
Cohesion: 0.25
Nodes (7): 1. Unofficial library (closest to the goal), 2. Telegram live location (official, stable), 3. Dedicated tracker (official, always-on), Before building, Google Maps location sharing -> "where is <person>?" (2026-09-19), Later, Recommendation

### Community 74 - "test_deepgram_voice.py"
Cohesion: 0.06
Nodes (19): _FakeSSEResponse, Tests for the Deepgram Speed Upgrade: jarvis_stt_deepgram.py,…, Voice-bug follow-up (2026-09-22): "Hi" and "thanks" answer with no Claude call…, Voice-bug follow-up (2026-09-22): TTSDiskCache.get() has no integrity check on…, _sse_lines(), _sse_text_reply(), test_claude_stream_first_round_error_event_returns_none(), test_claude_stream_first_round_fires_on_first_token_once() (+11 more)

### Community 75 - "jarvis_face.py"
Cohesion: 0.05
Nodes (72): Exception, _already_enrolled(), away_grace_s(), _away_reset(), _away_step(), away_warn_s(), _camera_failed(), _camera_ok() (+64 more)

### Community 76 - "jarvis_autonomy_skills.py"
Cohesion: 0.23
Nodes (19): create_skill(), handle_tool(), _init(), _known(), list_skills(), note_turn(), _q(), Composable, side-effect-safe skills for the autonomy layer. A skill is a NAMED,… (+11 more)

### Community 77 - "test_face.py"
Cohesion: 0.07
Nodes (42): _clean_name(), delete(), delete_by_id(), describe_profiles(), enroll(), list_profiles(), Enroll a person. The first one becomes the Admin; later ones are `user`…, Remove a profile and its embeddings. The audit trail of events is kept (it… (+34 more)

### Community 78 - "jarvis_memory_consolidation.py"
Cohesion: 0.28
Nodes (14): abstract_rules(), compress_old_summaries(), _connect(), consolidate(), _db_path(), _iso(), Connection, datetime (+6 more)

### Community 79 - "_handle_family"
Cohesion: 0.32
Nodes (8): _handle_family(), _is_our_own_message(), True if the body carries our signature as an unquoted line. Stops Jarvis…, _sig_line(), _signature(), _system_prompt(), test_own_signature_is_skipped_but_quoted_signature_is_not(), __call__()

### Community 80 - "Fake"
Cohesion: 0.09
Nodes (36): _capture(), _cb(), Fake, O(), Records callback traffic; `answers` maps a marker in the prompt to the JSON the…, test_a_classifier_context_is_framed(), test_a_conversation_extraction_of_tool_derived_text_is_framed(), test_a_inbound_prompt_is_framed_sanitised_and_length_capped() (+28 more)

### Community 81 - "_InsightEngine"
Cohesion: 0.13
Nodes (10): _InsightEngine, Observation, fn(event_dict) is called after every audit row (kind/name/confidence/ts only)…, set_event_hook(), insightface would silently fetch the pack itself with no size/hash check,…, test_a_failing_lock_hook_does_not_break_polling(), test_engine_caps_onnx_threads_so_it_cannot_stall_the_voice_loop(), test_engine_refuses_when_models_are_missing_instead_of_letting_insightface_download() (+2 more)

### Community 82 - "timedelta"
Cohesion: 0.15
Nodes (20): agent_context_line(), build_calendar_args(), _expire_old(), _iso(), _learned_ignore_expired(), log_entries(), _now(), _plausible_deadline() (+12 more)

### Community 83 - "build_system_blocks"
Cohesion: 0.17
Nodes (15): build_system_blocks(), build_system_prompt(), _fetch_projects(), get_active_facts_context(), get_projects_context(), get_skills_context(), get_user_profile_context(), _long_cache_control() (+7 more)

### Community 84 - "boom"
Cohesion: 0.07
Nodes (20): The exact reported bug: saying "Hi" must produce a clean full reply, never the…, Voice-bug pass (2026-09-22): the filler phrase ("One moment.") and short…, test_claude_stream_first_round_gemini_provider_no_ops(), test_claude_stream_first_round_network_failure_returns_none(), boom(), test_deepgram_tts_circuit_breaker_trips_after_repeated_failures(), boom(), test_deterministic_reply_skips_run_agent_loop_entirely() (+12 more)

### Community 85 - "RuntimeError"
Cohesion: 0.09
Nodes (30): _data_dir(), _DataBlob, _db_path(), download_models(), _dpapi(), blob(), _encrypt(), _has_encrypted_data() (+22 more)

### Community 86 - "_fake_mcp_run_coro"
Cohesion: 0.32
Nodes (6): _fake_mcp_run_coro(), _FakeMcpResult, execute_mcp_tool always builds the real coroutine before calling _mcp_run_coro;…, test_calendar_invalid_grant_embedded_in_json_still_gets_the_hint(), test_gmail_invalid_grant_becomes_a_reauth_instruction(), test_other_mcp_errors_are_unaffected_by_the_auth_hint()

### Community 87 - "ensure_mcp_started"
Cohesion: 0.09
Nodes (21): AbstractEventLoop, _dashboard_get_services_status(), _ensure_mcp_loop(), ensure_mcp_started(), get_mcp_tool_schemas(), _load_mcp_server_configs(), _mcp_connect_all_async(), _mcp_connect_one() (+13 more)

### Community 88 - "autonomy.js"
Cohesion: 0.51
Nodes (9): call(), card(), cardFlag(), h(), loadLog(), logRow(), refresh(), render() (+1 more)

### Community 89 - "calibrate"
Cohesion: 0.07
Nodes (22): calibrate(), camera_index(), CameraUnavailable, _capture_and_analyze(), _get_engine(), liveness_min_swing(), _open_camera(), Open the camera, grab one frame, release it. Returns (observations, mean, std,… (+14 more)

### Community 90 - "_mail_answer"
Cohesion: 0.67
Nodes (3): _mail_answer(), test_a_clean_meeting_still_acts_at_high_confidence_and_structured_meeting_at_normal_floor(), test_wp1_subject_only_is_extracted_at_lower_confidence_and_logged()

### Community 91 - "jarvis_latency.py"
Cohesion: 0.13
Nodes (15): classify_intent(), current(), end(), Per-voice-command latency tracker (Speed Upgrade Phase 0). One VoiceLatency…, recent(), start(), VoiceLatency, parametrize (+7 more)

### Community 92 - "jarvis_dashboard.py"
Cohesion: 0.19
Nodes (20): api_audit(), api_clear_finished_sessions(), _build_state(), clear_finished_sessions(), _connect(), _db_path(), end_session(), _fetch_audit() (+12 more)

### Community 93 - "_evaluate_base"
Cohesion: 0.18
Nodes (12): _env_float(), _evaluate_base(), evaluate_policy(), _norm_dt(), Name <a@b.com>' -> 'a@b.com', lower-cased. A display name can say anything, so…, Exact address (audit E-02: substring matching let a lookalike or display name…, -> ('auto_act' | 'record' | 'ask' | 'ignore', reason). FULL-PERMISSION MODEL:…, A clear meeting: a title and a plausible start datetime. (+4 more)

### Community 94 - "enabled"
Cohesion: 0.10
Nodes (23): after_turn(), _work(), _direct_calendar(), _email_recipient_blocked(), enabled(), hard_disabled(), _mark_seen(), process_inbound_async() (+15 more)

### Community 95 - "test_guest_reminders.py"
Cohesion: 0.06
Nodes (61): answer(), configure(), forward_reminder(), has_open_question(), holding_reminders(), _norm(), on_stranger_arrived(), on_stranger_left() (+53 more)

### Community 96 - "jarvis"
Cohesion: 0.14
Nodes (12): jarvis(), Goes through handle_text_command -> _execute_tool (not _execute_impl): also…, test_away_mode_tool_respects_the_source(), turn(), test_delete_via_the_real_tool_path_needs_two_user_messages(), agent_turn(), test_face_privacy_tool_pause_from_phone_works_resume_does_not(), agent() (+4 more)

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

### Community 105 - "jarvis_cache.py"
Cohesion: 0.38
Nodes (5): is_self_contained(), normalize_text(), Small, local-only cache helpers shared by jarvis.py: an env-flag reader,…, Lowercase, punctuation-stripped, whitespace-collapsed — so 'System status?' and…, test_normalize_and_self_contained()

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

### Community 112 - "_StubSession"
Cohesion: 0.25
Nodes (5): Duck-types jarvis_stt_deepgram.StreamingSession's finish() surface for…, _StubSession, test_transcribe_pcm_falls_back_to_rest_when_stream_fails(), test_transcribe_pcm_too_short_audio_still_tears_down_stream_session(), test_transcribe_pcm_uses_streaming_session_result_when_present()

### Community 113 - "send_with_retry"
Cohesion: 0.33
Nodes (6): send() -> (ok, detail). Tries once, then retries every delay_s seconds, up to…, send_with_retry(), test_send_exception_counts_as_failure(), test_send_gives_up_after_five_retries(), test_send_retries_every_minute_then_succeeds(), send()

### Community 114 - "_speak_streamed"
Cohesion: 0.33
Nodes (4): _play_pcm_stream(), Attempts Deepgram's streaming speak WebSocket for `text`, playing audio as it's…, Plays int16 PCM chunks as they're produced by an iterable (a live WebSocket…, _speak_streamed()

### Community 115 - "_handle_text_command_impl"
Cohesion: 0.06
Nodes (36): _collapse_paths_for_speech(), _dashboard_approve_pending(), _sink(), _dashboard_reject_pending(), _deterministic_intent_reply(), _execute_confirmed_action(), _face_release_held_notifications(), flush_pending_notifications() (+28 more)

### Community 116 - "_execute_tool_impl"
Cohesion: 0.05
Nodes (60): _append_history(), _apply_memory_db_pragmas(), cancel_reminder(), _catastrophic_reason(), click_at(), _contains_secret(), _count_running_background_tasks(), _create_memory_tables() (+52 more)

### Community 118 - "CircuitBreaker"
Cohesion: 0.20
Nodes (6): CircuitBreaker, Trips after `threshold` consecutive failures and refuses calls for…, test_circuit_breaker_success_resets_failures(), test_circuit_breaker_trips_and_cools_down(), test_stt_backend_recovers_after_breaker_cooldown(), flaky()

### Community 119 - "jarvis_untrusted.py"
Cohesion: 0.40
Nodes (5): canonical(), _fix_word(), Handling of text written by other people (mail, messages, file names, web…, The text as a human would read it: NFKC, invisible characters removed, look-…, Match

### Community 120 - "fixture"
Cohesion: 0.29
Nodes (7): A(), client(), D(), fixture, S(), test_b_tool_and_dashboard_routes(), dash()

### Community 121 - "_work"
Cohesion: 0.50
Nodes (5): _work(), True if this turn read mail/web/files/screen: its reply and tool results may…, _recent_tool_actions(), _recent_tool_rows(), _used_untrusted_tool()

### Community 122 - "StreamingSynthesis"
Cohesion: 0.13
Nodes (11): One request to Deepgram's streaming speak WebSocket. Usage: session =…, Generator yielding raw int16 PCM bytes as Aura 2 generates them. Text…, StreamingSynthesis, _FakeSpeakWebsocketLib, _FakeSpeakWS, create_connection(), test_streaming_synthesis_chunks_yields_only_binary_frames(), test_streaming_synthesis_connect_failure_returns_false() (+3 more)

### Community 123 - "_narrating_claude"
Cohesion: 0.50
Nodes (3): _narrating_claude(), test_narrate_off_keeps_old_behaviour(), test_narrate_speaks_text_beside_a_tool_call_and_keeps_it_out_of_the_reply()

### Community 125 - "test_dev_features.py"
Cohesion: 0.05
Nodes (60): analyze_repo(), _existing_tests(), generate_tests(), _public_api(), _py_files(), Path, Repository analysis, unit-test generation and module boilerplate. Deterministic…, New `<name>.py` plus a matching test file, in the style the repo already uses. (+52 more)

### Community 129 - "_autonomy_callbacks"
Cohesion: 0.07
Nodes (31): _autonomy_calendar_events(), _autonomy_callbacks(), _autonomy_create_event(), _autonomy_inbound(), _autonomy_mail_hook(), _commands_in_flight(), create_reminder(), execute_mcp_tool() (+23 more)

### Community 131 - "_speak_session_stub"
Cohesion: 0.14
Nodes (11): Duck-types tts_deepgram.StreamingSynthesis for _speak_streamed tests:…, Real audio already played before the interruption — must be reported as handled…, The critical Phase B safety property: the background pre-fetch thread for the…, _speak_session_stub(), test_speak_streamed_failure_before_any_audio_is_not_handled(), test_speak_streamed_happy_path(), test_speak_streamed_mid_stream_failure_after_audio_is_handled_but_incomplete(), test_speak_text_caches_complete_streamed_audio_for_reuse() (+3 more)

### Community 132 - "test_run_agent_loop_multi_round_streams_narration_then_speaks_final_reply_once"
Cohesion: 0.17
Nodes (7): Audit scenario: round 0 streams narration + a tool_use (so the loop must…, test_reply_already_spoken_flag_resets_between_commands(), test_run_agent_loop_falls_back_to_non_streaming_when_stream_fails(), fake_request(), test_run_agent_loop_multi_round_streams_narration_then_speaks_final_reply_once(), test_run_agent_loop_streams_text_only_final_reply_and_marks_spoken(), fake_stream()

### Community 139 - "_claude_request"
Cohesion: 0.07
Nodes (36): _build_sleep_digest(), _claude_request(), _claude_stream_first_round(), _speak_ready(), _claude_text(), _duckduckgo_search(), _extract_ready_sentences(), _fish_audio_synthesize() (+28 more)

## Knowledge Gaps
- **130 isolated node(s):** `state`, `ROUTES`, `ROUTES_WITH_CONTEXT`, `servicesPanel`, `servicesToggleBtn` (+125 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1046 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_execute_tool_impl()` connect `_execute_tool_impl` to `_autonomy_callbacks`, `jarvis_window_control.py`, `jarvis_sleep_mode.py`, `FileWatcher`, `jarvis.py`, `jarvis_memory_enhance.py`, `_claude_request`, `jarvis_workflow.py`, `jarvis_dynamic_tools.py`, `jarvis_proactive.py`, `jarvis_autonomy.py`, `queue_or_deliver_notification`, `download_image`, `jarvis_autonomy_organise.py`, `Path`, `jarvis_task_scheduler.py`, `test_restart.py`, `run_agent_loop`, `poll_once`, `test_hardening.py`, `jarvis_billing.py`, `jarvis_tech_understanding.py`, `is_paused`, `jarvis_autonomy_skills.py`, `test_face.py`, `test_guest_reminders.py`, `_handle_text_command_impl`, `test_dev_features.py`?**
  _High betweenness centrality (0.060) - this node is a cross-community bridge._
- **Why does `_build_app()` connect `_build_app` to `start`, `test_dashboard_llm_endpoints`, `_ConnectionManager`, `_set_broadcast`, `_origin_is_loopback`, `jarvis_dashboard.py`?**
  _High betweenness centrality (0.041) - this node is a cross-community bridge._
- **Why does `dash()` connect `fixture` to `is_paused`, `test_face.py`, `test_dashboard_llm_endpoints`?**
  _High betweenness centrality (0.017) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `_execute_tool_impl()` (e.g. with `_launch_focus_app()` and `_memory_db_connect()`) actually correct?**
  _`_execute_tool_impl()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 57 inferred relationships involving `timedelta` (e.g. with `_action_for_commitment()` and `agent_context_line()`) actually correct?**
  _`timedelta` has 57 INFERRED edges - model-reasoned connections that need verification._
- **What connects `state`, `ROUTES`, `ROUTES_WITH_CONTEXT` to the rest of the system?**
  _130 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `test_autonomy.py` be split into smaller, more focused modules?**
  _Cohesion score 0.025479195885928004 - nodes in this community are weakly interconnected._