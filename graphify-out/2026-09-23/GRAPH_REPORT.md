# Graph Report - jarvis-main2  (2026-09-23)

## Corpus Check
- 94 files · ~235,394 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 4 file(s) not represented in the graph (top: (none) 1, .vbs 1, .css 1)

## Summary
- 3382 nodes · 7307 edges · 158 communities (145 shown, 10 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 407 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `7ff05406`
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
- run_agent_loop
- jarvis_memory_enhance.py
- test_gemini.py
- test_sleep_mail.py
- _claude_text
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
- test_safe_mode.py
- test_dashboard.py
- Tween
- download_image
- jarvis_autonomy_organise.py
- Path
- Fake
- _narrating_claude
- test_voice_usage.py
- main
- Brag Plan: Jarvis
- SqliteKV
- jarvis_briefing.py
- test_billing_failures_are_plain_sentences
- ce
- _FakeProc
- ce
- test_qol.py
- test_restart.py
- jarvis_voice_tone.py
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
- start_polling
- jarvis_tech_understanding.py
- transcribe
- _deterministic_intent_reply
- is_paused
- Google Maps location sharing -> "where is <person>?" (2026-09-19)
- test_deepgram_voice.py
- jarvis_face.py
- jarvis_autonomy_skills.py
- test_face.py
- jarvis_sleep_mail.py
- qol.js
- _cb
- voice.js
- _call
- process_inbound_message_for_events
- RuntimeError
- download_models
- _fake_mcp_run_coro
- jarvis_audio_duck.py
- autonomy.js
- calibrate
- _provider
- jarvis_latency.py
- jarvis_dashboard.py
- jarvis_autonomy.py
- enabled
- state
- run_cycle
- synthesize
- StreamingSession
- Dashboard UI/UX overhaul (2026-09-22)
- _db
- FollowUpListener
- identify
- test_dashboard_llm_endpoints
- _ConnectionManager
- test_run_agent_loop_multi_round_streams_narration_then_speaks_final_reply_once
- timedelta
- _set_broadcast
- jarvis_settings.py
- _origin_is_loopback
- Speed Upgrade: Deepgram-native voice pipeline + cloud-latency pass
- snake.js
- test_dev_features.py
- dashboard_state
- _exec_rc
- jarvis_task_scheduler.py
- _execute_tool_impl
- speak_text
- CircuitBreaker
- test_timers.py
- fixture
- test_guest_reminders.py
- StreamingSynthesis
- _timer_reply
- _handle_text_command_impl
- test_hold_modes.py
- execute_mcp_tool
- boom
- _grab_selection
- jarvis_cache.py
- test_memory_edit.py
- _speak_session_stub
- Snake
- TTLCache
- _DuckDuckGoResultParser
- _claude_request
- classify_intent
- queue_or_deliver_notification
- _FakeOutputStream
- _scripted_claude
- jarvis_guest_reminders.py
- start
- test_1h_ttl_rejection_falls_back_to_5m_and_retries
- test_scheduled_skill_never_speaks_tool_ack_or_bare_ok
- _StubSession
- _wait_solo_hold
- test_media_control_reuses_one_worker
- Google re-authentication (when tokens expire, every 7 days in Testing mode)
- jarvis_weather.py
- AttGmail
- send_with_retry
- _http_error
- jarvis_untrusted.py
- fixture
- _acted
- _selection_key_usable
- test_state_audit_rows_include_transcript_for_session_linking
- test_command_endpoint_invokes_run_command

## God Nodes (most connected - your core abstractions)
1. `_execute_tool_impl()` - 123 edges
2. `Fake` - 103 edges
3. `_build_app()` - 65 edges
4. `_on()` - 60 edges
5. `_future()` - 55 edges
6. `main()` - 52 edges
7. `_iso()` - 47 edges
8. `_memory_db_connect()` - 45 edges
9. `_rows()` - 42 edges
10. `run_agent_loop()` - 38 edges

## Surprising Connections (you probably didn't know these)
- `compose()` --calls--> `wait()`  [INFERRED]
  jarvis_briefing.py → test_face.py
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

## Communities (158 total, 10 thin omitted)

### Community 0 - "test_autonomy.py"
Cohesion: 0.03
Nodes (29): skipif, _file(), parametrize, Tests for jarvis_autonomy.py, jarvis_dynamic_tools.py,…, The gate is untouched: an autonomous agent run that reaches a catastrophic…, jarvis.py wires run_tool to _execute_tool, so a skill step naming run_shell…, Autonomy on => injection hardening, the third-party bar and file organising are…, Like face: the new modules may never touch the catastrophic gate or import… (+21 more)

### Community 1 - "jarvis_window_control.py"
Cohesion: 0.14
Nodes (29): arrange_windows(), _cascade_rects(), close_window(), _connect(), _db_path(), delete_layout(), _find(), _grid_rects() (+21 more)

### Community 2 - "brag-output-2026-09-19-001152/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 3 - "jarvis_sleep_mode.py"
Cohesion: 0.05
Nodes (70): Short, unambiguous volume commands ("volume up", "turn it down", "mute",…, _broadcast_theme_change(), _cancel_media_autopause(), _connect(), _db_path(), disable(), enable(), _endpoint_volume_call() (+62 more)

### Community 4 - "brag-output/composition/assets/gsap.min.js"
Cohesion: 0.07
Nodes (15): Gc(), Hc(), ia(), ja(), Lc(), Nc(), oa(), pa() (+7 more)

### Community 5 - "FileWatcher"
Cohesion: 0.10
Nodes (15): add_watched_folder(), _connect(), _db_path(), _default_watch_paths(), FileWatcher, get_recent_file_events(), list_watched_folders(), Connection (+7 more)

### Community 6 - "jarvis.py"
Cohesion: 0.06
Nodes (59): _bytes_to_gb(), _bytes_to_mb(), check_system_health(), _choose_input_device(), _chrome_executable(), _contains_secret(), _craft_system_status_summary(), _cursor_executable() (+51 more)

### Community 7 - "run_agent_loop"
Cohesion: 0.06
Nodes (55): build_system_blocks(), build_system_prompt(), enabled(), JARVIS_<LAYER>_CACHE env flag, default on. Read on every call so it can be…, record(), _cached_tools(), reply_style_line(), _duckduckgo_search() (+47 more)

### Community 8 - "jarvis_memory_enhance.py"
Cohesion: 0.13
Nodes (24): _connect(), _cosine(), _db_path(), link_facts(), list_code_patterns(), list_decisions(), Connection, Path (+16 more)

### Community 9 - "test_gemini.py"
Cohesion: 0.07
Nodes (48): call(), convert_messages(), convert_tools(), from_response(), get_provider(), Path, Request, Gemini (Google AI Studio) backend for Jarvis's LLM calls. Jarvis's callers all… (+40 more)

### Community 10 - "test_sleep_mail.py"
Cohesion: 0.16
Nodes (19): db(), FakeGmail, jarvis(), fixture, Tests for the Sleep Mode mail take-over. Run: python -m pytest…, _run(), _search(), test_family_email_gets_reply_recorded_and_not_repeated() (+11 more)

### Community 11 - "_claude_text"
Cohesion: 0.08
Nodes (25): _autonomy_inbound(), _autonomy_mail_hook(), _build_sleep_digest(), _claude_text(), Files something under the wake-up recap's important section without speaking it., Registered with jarvis_sleep_mode: when Sleep Mode ends, replaces the old flood…, Two-part recap: what mattered first (urgent things that came through live while…, While Sleep Mode is on, check Gmail every SLEEP_MAIL_INTERVAL_MIN minutes… (+17 more)

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
Nodes (9): _gate_env(), _kv_db(), Tests for the caching layers (jarvis_cache.py + their wiring in jarvis.py). Run…, test_billing_summary_and_pagination(), test_busy_gate_holds_ordinary_notification_but_not_reminders(), test_bypass_busy_gate_still_respects_sleep_mode(), test_enabled_flag(), test_record_and_local_summary() (+1 more)

### Community 17 - "TTSDiskCache"
Cohesion: 0.29
Nodes (5): Path, WAV files under one directory, keyed by hash. LRU by mtime (touched on every…, TTSDiskCache, test_tts_cache_skips_synthesis_on_repeat(), test_tts_disk_cache_roundtrip_and_eviction()

### Community 18 - "jarvis_proactive.py"
Cohesion: 0.27
Nodes (12): check_project_health(), _connect(), _db_path(), _fmt_findings(), _iter_source_files(), Connection, Path, Proactive problem detection for Jarvis. Scans a file or project directory for… (+4 more)

### Community 19 - "_iso"
Cohesion: 0.10
Nodes (47): accept_commitment(), add_project_action(), approve_campaign(), approve_suggestion(), _brief(), budgets(), _commitment(), delete_policy() (+39 more)

### Community 20 - "test_chief.py"
Cohesion: 0.09
Nodes (21): dtime, budget_alert(), headsup_text(), in_quiet_hours(), _local(), meetings_starting(), parse_quiet_hours(), parse_reply_style() (+13 more)

### Community 21 - "j"
Cohesion: 0.20
Nodes (8): configure(), reset(), j(), Phone, fixture, Stands in for Telegram: records what Jarvis texts, and can be made to fail., test_reminders_mode_tool_from_any_source(), run()

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

### Community 26 - "test_safe_mode.py"
Cohesion: 0.25
Nodes (3): jarvis(), fixture, Safe mode + health card (P4). Temp DB and temp .env only.

### Community 28 - "Tween"
Cohesion: 0.19
Nodes (21): _a(), Ao(), _assertThisInitialized(), cb(), cc(), ga(), gb(), hb() (+13 more)

### Community 29 - "download_image"
Cohesion: 0.11
Nodes (27): _check_host(), _CheckedRedirects, _clean_stem(), download_image(), _fetch(), Path, download_image: fetch one image URL and save it to a single fixed folder.…, i.pinimg.com/236x/.. or /736x/.. (a thumbnail) -> /originals/.. (full size). (+19 more)

### Community 30 - "jarvis_autonomy_organise.py"
Cohesion: 0.13
Nodes (36): add_root(), add_rule(), _copy_no_clobber(), handle_new_file(), handle_tool(), home(), _init(), _inside() (+28 more)

### Community 31 - "Path"
Cohesion: 0.07
Nodes (35): _cleanup_old_logs(), _dashboard_get_daily_items(), _dashboard_get_services_status(), _fmt_gb(), get_large_files_report(), _load_mcp_server_configs(), _load_skills(), _mcp_servers_config_path() (+27 more)

### Community 32 - "Fake"
Cohesion: 0.06
Nodes (67): Fake, _future(), _mail_answer(), _on(), FULL-PERMISSION MODEL: a confident, non-catastrophic item is acted on…, Records callback traffic; `answers` maps a marker in the prompt to the JSON the…, test_a_clean_meeting_still_acts_at_high_confidence_and_structured_meeting_at_normal_floor(), test_a_email_recipient_allowlist_is_optional_and_empty_means_unrestricted() (+59 more)

### Community 33 - "_narrating_claude"
Cohesion: 0.15
Nodes (9): _narrating_claude(), fake(), test_narrate_off_keeps_old_behaviour(), test_narrate_speaks_text_beside_a_tool_call_and_keeps_it_out_of_the_reply(), test_summary_cache_skips_second_claude_call(), test_tool_only_turn_falls_back_to_tool_result_by_default(), test_tool_result_fallback_can_be_disabled(), test_truncated_tool_call_is_not_run_and_not_silent() (+1 more)

### Community 34 - "test_voice_usage.py"
Cohesion: 0.21
Nodes (12): _ensure(), Connection, Voice usage stats (2026-09-23): how much text Jarvis turns into speech (TTS)…, kind "tts" (Jarvis spoke `text`) or "stt" (the user said `text`); only its…, record(), summary(), _db(), jarvis() (+4 more)

### Community 35 - "main"
Cohesion: 0.06
Nodes (43): _acquire_single_instance_lock(), block_samples(), _dashboard_get_sleep(), _dashboard_get_usage(), _dictate(), handle_text_command(), handle_voice_command(), _handle_voice_command_impl() (+35 more)

### Community 36 - "Brag Plan: Jarvis"
Cohesion: 0.10
Nodes (19): Audio direction, Brag Plan: Jarvis, Duration: ~21 seconds, Format: landscape — 1920x1080, Hook (first 3.3 seconds), Key moments (the middle), Outro / punchline, Scene 1 — Hook — 3.3s (+11 more)

### Community 37 - "SqliteKV"
Cohesion: 0.36
Nodes (4): Connection, key -> text value with a created_at timestamp; max_age_s is checked on read,…, SqliteKV, test_sqlite_kv_max_age_and_prune()

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
Cohesion: 0.13
Nodes (12): fixture, QOL pass (2026-09-23): Claude->Gemini failover, self-check, timers/stopwatch,…, _reset(), test_cleanup_old_logs(), test_hands_free_yes_never_confirms_a_staged_action(), test_repeat_and_last_reply_tracking(), test_self_check_reports_problems_first(), test_timer_edge_cases() (+4 more)

### Community 44 - "test_restart.py"
Cohesion: 0.15
Nodes (18): check_syntax(), helper_command(), Event, Path, restart_jarvis: let Jarvis restart itself (voice: "restart yourself") to pick…, Error text for the first jarvis*.py that doesn't compile, else None., restart(), _stop_self() (+10 more)

### Community 45 - "jarvis_voice_tone.py"
Cohesion: 0.32
Nodes (7): analyze_tone(), _lexical_scores(), _prosody(), Basic voice tone/sentiment awareness for Jarvis. Rule-based, deliberately…, Short line to fold into the agent system prompt for this turn; empty string if…, Returns {"tone": category, "confidence": 0..1, "signals": [short strings]}.…, tone_context_line()

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
Nodes (40): classify(), default_dir(), _inside(), Path, Jarvis_Workspace: the default home for every file Jarvis creates, saves or…, Where a file should be written. Returns (path, "") or (None, reason it was…, Absolute paths are used as given; a relative one is looked up in the workspace…, A workspace subfolder, created if missing (for tools that pick their own file… (+32 more)

### Community 65 - "jarvis_billing.py"
Cohesion: 0.15
Nodes (19): compute_cost(), _dollars(), _ensure_usage_table(), fetch_cost_buckets(), format_local_summary(), get_api_spend(), local_summary(), Connection (+11 more)

### Community 66 - "start_polling"
Cohesion: 0.15
Nodes (14): _lower_thread_priority(), poll_interval(), Run the poll below normal priority so an inference burst yields to the voice…, Start the low-duty background poll (no-op unless JARVIS_FACE_ENABLED=1). The…, Once the owner has been steadily in view with nobody else, look less often…, settled_poll_interval(), start_polling(), loop() (+6 more)

### Community 67 - "jarvis_tech_understanding.py"
Cohesion: 0.13
Nodes (14): analyze_python_file(), build_import_graph(), format_analysis_report(), format_error_report(), _imports_of(), _module_name_for(), parse_error(), Path (+6 more)

### Community 68 - "transcribe"
Cohesion: 0.12
Nodes (16): ndarray, Request, Deepgram Nova-3 STT (Speed Upgrade Phase 1.1, streaming added in the cloud-…, Connection warm-up (Phase 2.2): a near-silent clip so the TLS handshake happens…, Hard-timeout watchdog: urlopen's own timeout doesn't reliably fire on a wedged…, transcribe(), _urlopen_bounded(), warm() (+8 more)

### Community 69 - "_deterministic_intent_reply"
Cohesion: 0.09
Nodes (22): pending(), briefing_report(), _dashboard_get_pending(), _deterministic_intent_reply(), _face_release_held_notifications(), flush_pending_notifications(), health_report(), _interrupt_speech() (+14 more)

### Community 72 - "is_paused"
Cohesion: 0.09
Nodes (22): is_paused(), jarvis(), parametrize, Goes through handle_text_command -> _execute_tool (not _execute_impl): also…, DNS-rebinding defence: a hostile page re-pointing its domain at 127.0.0.1 sends…, _snap(), test_away_mode_tool_respects_the_source(), turn() (+14 more)

### Community 73 - "Google Maps location sharing -> "where is <person>?" (2026-09-19)"
Cohesion: 0.25
Nodes (7): 1. Unofficial library (closest to the goal), 2. Telegram live location (official, stable), 3. Dedicated tracker (official, always-on), Before building, Google Maps location sharing -> "where is <person>?" (2026-09-19), Later, Recommendation

### Community 74 - "test_deepgram_voice.py"
Cohesion: 0.05
Nodes (21): _FakeSSEResponse, Tests for the Deepgram Speed Upgrade: jarvis_stt_deepgram.py,…, A background pre-synthesis that outlives PIPELINE_JOIN_TIMEOUT_S must not hang…, Voice-bug follow-up (2026-09-22): "Hi" and "thanks" answer with no Claude call…, Voice-bug follow-up (2026-09-22): TTSDiskCache.get() has no integrity check on…, _sse_lines(), _sse_text_reply(), test_claude_stream_first_round_error_event_returns_none() (+13 more)

### Community 75 - "jarvis_face.py"
Cohesion: 0.07
Nodes (54): Exception, _already_enrolled(), away_enabled(), away_grace_s(), _away_reset(), away_status(), _away_step(), away_warn_s() (+46 more)

### Community 76 - "jarvis_autonomy_skills.py"
Cohesion: 0.23
Nodes (19): create_skill(), handle_tool(), _init(), _known(), list_skills(), note_turn(), _q(), Composable, side-effect-safe skills for the autonomy layer. A skill is a NAMED,… (+11 more)

### Community 77 - "test_face.py"
Cohesion: 0.07
Nodes (44): _clean_name(), delete(), delete_by_id(), enroll(), list_profiles(), Enroll a person. The first one becomes the Admin; later ones are `user`…, Remove a profile and its embeddings. The audit trail of events is kept (it…, _Cap (+36 more)

### Community 78 - "jarvis_sleep_mail.py"
Cohesion: 0.15
Nodes (21): _body_of(), _db_path(), _handle_family(), _is_our_own_message(), looks_like_error(), parse_attachments(), Path, Sleep Mode mail take-over. While Sleep Mode is on, jarvis.py calls run_cycle()… (+13 more)

### Community 79 - "qol.js"
Cohesion: 0.18
Nodes (14): buildPalette(), closePalette(), fuzzyScore(), loadPins(), memoryCall(), openPalette(), palette, refreshMemory() (+6 more)

### Community 80 - "_cb"
Cohesion: 0.08
Nodes (24): _capture(), _cb(), test_a_classifier_context_is_framed(), test_a_conversation_extraction_of_tool_derived_text_is_framed(), test_a_inbound_prompt_is_framed_sanitised_and_length_capped(), test_agent_replies_that_admit_failure_are_failures(), test_c_calendar_logs_distinguish_mcp_missing_from_failure_from_success(), test_c_structured_fallback_prompt_and_no_calendar_tool_is_a_clear_failure() (+16 more)

### Community 81 - "voice.js"
Cohesion: 0.32
Nodes (14): refreshVoice(), renderVoiceCards(), renderVoiceDaily(), renderVoiceEngines(), renderVoiceLatency(), renderVoiceRecords(), renderVoiceRhythm(), renderVoiceSplit() (+6 more)

### Community 82 - "_call"
Cohesion: 0.09
Nodes (46): _announce_pending(), _call(), _classifier_step(), _context_summary(), _env_int(), _file_scan(), _file_scan_locked(), gate_reason() (+38 more)

### Community 83 - "process_inbound_message_for_events"
Cohesion: 0.13
Nodes (18): Any, _ask_model(), extract_commitments_and_projects(), _fill(), _parse_json(), process_inbound_message_for_events(), After queue_task: the task is only 'pending' and nothing runs it until the…, Manual hook: runs the extraction prompt and returns the parsed, validated items… (+10 more)

### Community 84 - "RuntimeError"
Cohesion: 0.05
Nodes (29): RuntimeError, test_one_bad_item_does_not_lose_the_rest_of_the_batch(), test_tick_hands_slow_steps_to_bounded_workers_and_survives_a_failing_step(), test_record_usage_never_raises(), broken(), The exact reported bug: saying "Hi" must produce a clean full reply, never the…, Voice-bug pass (2026-09-22): the filler phrase ("One moment.") and short…, test_claude_stream_first_round_gemini_provider_no_ops() (+21 more)

### Community 85 - "download_models"
Cohesion: 0.10
Nodes (17): download_models(), _InsightEngine, _model_root(), models_ready(), Observation, fn(event_dict) is called after every audit row (kind/name/confidence/ts only)…, One-time fetch of the buffalo_l pack from insightface's GitHub release.…, set_event_hook() (+9 more)

### Community 86 - "_fake_mcp_run_coro"
Cohesion: 0.32
Nodes (6): _fake_mcp_run_coro(), _FakeMcpResult, execute_mcp_tool always builds the real coroutine before calling _mcp_run_coro;…, test_calendar_invalid_grant_embedded_in_json_still_gets_the_hint(), test_gmail_invalid_grant_becomes_a_reauth_instruction(), test_other_mcp_errors_are_unaffected_by_the_auth_hint()

### Community 87 - "jarvis_audio_duck.py"
Cohesion: 0.09
Nodes (33): _ctl_read(), _ctl_start(), duck(), enabled(), media_control(), _mute_others(), _pause_music(), _pause_pattern() (+25 more)

### Community 88 - "autonomy.js"
Cohesion: 0.51
Nodes (9): call(), card(), cardFlag(), h(), loadLog(), logRow(), refresh(), render() (+1 more)

### Community 89 - "calibrate"
Cohesion: 0.12
Nodes (13): calibrate(), camera_index(), CameraUnavailable, _capture_and_analyze(), _get_engine(), _open_camera(), Open the camera, grab one frame, release it. Returns (observations, mean, std,…, Dry run of the enrollment liveness check that stores NOTHING (no profile, no… (+5 more)

### Community 90 - "_provider"
Cohesion: 0.13
Nodes (14): api_briefing(), api_command(), _sink(), api_health(), api_latency(), api_memory(), api_memory_add(), api_memory_edit() (+6 more)

### Community 91 - "jarvis_latency.py"
Cohesion: 0.16
Nodes (12): current(), end(), Per-voice-command latency tracker (Speed Upgrade Phase 0). One VoiceLatency…, recent(), start(), VoiceLatency, A narrated mid-task line speaks via Deepgram; the final (longer) reply's…, test_deterministic_path_recorded_on_voice_latency() (+4 more)

### Community 92 - "jarvis_dashboard.py"
Cohesion: 0.15
Nodes (24): api_audit(), api_clear_finished_sessions(), api_recent_commands(), api_state(), _build_state(), clear_finished_sessions(), _connect(), _db_path() (+16 more)

### Community 93 - "jarvis_autonomy.py"
Cohesion: 0.09
Nodes (33): add_commitment(), _work(), _env_float(), _evaluate_base(), evaluate_policy(), _find_duplicate(), _insert_commitment(), _memory_query() (+25 more)

### Community 94 - "enabled"
Cohesion: 0.12
Nodes (22): _action_for_commitment(), after_turn(), agent_context_line(), _deadline_scan(), dry_run(), enabled(), hard_disabled(), _meta() (+14 more)

### Community 95 - "state"
Cohesion: 0.21
Nodes (23): answer(), has_open_question(), holding_reminders(), on_stranger_arrived(), on_stranger_left(), Handle a reply to an open question. Returns the reply to send back, or None if…, True while due reminders must be held (not spoken, no toast)., state() (+15 more)

### Community 96 - "run_cycle"
Cohesion: 0.16
Nodes (18): _classify_critical(), _connect(), _emails(), _env_set(), _handled(), _label(), load_family(), _mark() (+10 more)

### Community 97 - "synthesize"
Cohesion: 0.13
Nodes (14): Request, Deepgram Aura 2 TTS (Speed Upgrade Phase 1.2; WebSocket streaming added in the…, Same hard-timeout watchdog idiom as jarvis_stt_deepgram._urlopen_bounded —…, Connection warm-up (Phase 2.2): a tiny synth-and-discard so the first real…, synthesize(), _urlopen_bounded(), warm(), test_stt_timeout_error_falls_back_to_whisper() (+6 more)

### Community 98 - "StreamingSession"
Cohesion: 0.11
Nodes (17): One push-to-talk hold's live Deepgram Nova-3 WebSocket session. Usage (see…, Flushes and closes the session, returning (transcript, confidence) or None on…, StreamingSession, _FakeWebsocketLib, _FakeWS, Duck-types the websocket-client WebSocket object's send/recv/close surface., Mirrors jarvis.py's real usage: start() is kicked off on a helper thread and…, finish() called (almost) immediately after start() is kicked off on another… (+9 more)

### Community 99 - "Dashboard UI/UX overhaul (2026-09-22)"
Cohesion: 0.18
Nodes (10): Confirmation / approval path — unchanged, Dashboard UI/UX overhaul (2026-09-22), Home (mission control), How to preview without running full Jarvis, Keyboard, Layout, Post-overhaul UX pass (2026-09-22), Routes (+2 more)

### Community 100 - "_db"
Cohesion: 0.13
Nodes (28): _db(), delete_all_snapshots(), _encrypt(), event_keep_days(), housekeeping(), invalidate_profile_cache(), _pack_embeddings(), prune_events() (+20 more)

### Community 101 - "FollowUpListener"
Cohesion: 0.11
Nodes (23): deque, FollowUpListener, ndarray, Follow-up window (QOL pass, 2026-09-23): after Jarvis answers a voice command,…, chained: this reply answered a hands-free follow-up. After MAX_CHAIN of those…, Call with every mic block while push-to-talk isn't held and Jarvis isn't…, draw(), main() (+15 more)

### Community 102 - "identify"
Cohesion: 0.21
Nodes (15): _already_seen_recently(), _decrypt(), get_snapshot(), identify(), load_embeddings(), match_threshold(), _profiles_for_matching(), ndarray (+7 more)

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

### Community 112 - "test_dev_features.py"
Cohesion: 0.06
Nodes (58): analyze_repo(), _existing_tests(), generate_tests(), _public_api(), _py_files(), Path, Repository analysis, unit-test generation and module boilerplate. Deterministic…, New `<name>.py` plus a matching test file, in the style the repo already uses. (+50 more)

### Community 113 - "dashboard_state"
Cohesion: 0.13
Nodes (23): _connect(), dashboard_state(), _data_dir(), _DataBlob, _db_path(), _dpapi(), blob(), event_kinds() (+15 more)

### Community 114 - "_exec_rc"
Cohesion: 0.17
Nodes (15): configure(), _connect(), _db_path(), _exec_rc(), init_autonomy_tables(), _mark_seen(), Connection, Path (+7 more)

### Community 115 - "jarvis_task_scheduler.py"
Cohesion: 0.11
Nodes (33): abstract_rules(), compress_old_summaries(), _connect(), consolidate(), _db_path(), _iso(), Connection, datetime (+25 more)

### Community 116 - "_execute_tool_impl"
Cohesion: 0.04
Nodes (67): _append_history(), _apply_memory_db_pragmas(), _background_tasks_dir(), cancel_reminder(), _catastrophic_reason(), _check_background_tasks(), click_at(), _count_running_background_tasks() (+59 more)

### Community 117 - "speak_text"
Cohesion: 0.10
Nodes (27): _away_warn(), stable_hash(), _fish_audio_synthesize(), _pcm_seconds(), Cloud-latency pass, Phase B: gates Deepgram's WebSocket speak API (audio plays…, Silent cache lookup (no hit/miss stats recorded — the caller decides…, Runs the Deepgram REST -> Fish -> Piper synth cascade (skipping engines that…, Speak arbitrary dynamic text (voice-command replies). Deepgram Aura 2 (cloud)… (+19 more)

### Community 118 - "CircuitBreaker"
Cohesion: 0.17
Nodes (8): CircuitBreaker, Trips after `threshold` consecutive failures and refuses calls for…, jarvis(), fixture, test_circuit_breaker_success_resets_failures(), test_circuit_breaker_trips_and_cools_down(), test_stt_backend_recovers_after_breaker_cooldown(), flaky()

### Community 119 - "test_timers.py"
Cohesion: 0.20
Nodes (7): jarvis(), fixture, parametrize, Persistent named timers (P5). Temp DB only; no real waiting beyond fractions of…, test_named_timer_phrases_route_to_the_timer_fast_path(), test_timer_names(), test_timers_survive_a_restart_and_missed_ones_are_announced()

### Community 120 - "fixture"
Cohesion: 0.25
Nodes (8): A(), client(), D(), O(), fixture, S(), test_b_tool_and_dashboard_routes(), dash()

### Community 121 - "test_guest_reminders.py"
Cohesion: 0.20
Nodes (14): set_disabled(), _held(), Tests for jarvis_guest_reminders (the stranger -> "disable reminders?" Telegram…, test_default_group_safe_hold_still_lets_urgent_reminders_speak(), test_flush_on_any_command_does_not_leak_held_reminders(), test_pending_question_holds_reminders_but_does_not_text_them_yet(), test_reenabling_reads_out_the_held_reminders(), test_reminders_are_held_texted_and_silent_once_disabled() (+6 more)

### Community 122 - "StreamingSynthesis"
Cohesion: 0.11
Nodes (13): Attempts Deepgram's streaming speak WebSocket for `text`, playing audio as it's…, _speak_streamed(), One request to Deepgram's streaming speak WebSocket. Usage: session =…, Generator yielding raw int16 PCM bytes as Aura 2 generates them. Text…, StreamingSynthesis, _FakeSpeakWebsocketLib, _FakeSpeakWS, create_connection() (+5 more)

### Community 123 - "_timer_reply"
Cohesion: 0.19
Nodes (14): _cancel_timers(), _parse_duration_s(), pasta" from "set a pasta timer for 10 minutes" / "a timer called pasta" / "10…, Timers persist in jarvis_memory.db so a restart doesn't lose them., Startup: re-arm timers that were running when Jarvis stopped; one that went off…, Local handling for timers and the stopwatch; None = let the agent loop handle…, _restore_timers(), _say_duration() (+6 more)

### Community 124 - "_handle_text_command_impl"
Cohesion: 0.09
Nodes (25): _collapse_paths_for_speech(), _dashboard_approve_pending(), _sink(), _dashboard_reject_pending(), _execute_confirmed_action(), _forward_held_reminders(), _handle_text_command_impl(), _humanize_path_for_speech() (+17 more)

### Community 125 - "test_hold_modes.py"
Cohesion: 0.23
Nodes (8): _fake_keyboard(), jarvis(), fixture, Appshot (ask about the window in front) and dictation hold modes. No real…, test_a_mouse_click_during_the_hold_is_a_shortcut_not_a_hold(), test_appshot_attaches_window_picture_and_is_never_reply_cached(), test_dictation_copies_instead_when_the_window_changed(), test_dictation_types_into_the_same_window_and_audits_without_the_words()

### Community 126 - "execute_mcp_tool"
Cohesion: 0.10
Nodes (19): AbstractEventLoop, _autonomy_create_event(), _ensure_mcp_loop(), execute_mcp_tool(), _mcp_auth_error_hint(), _mcp_call_tool_async(), _mcp_connect_all_async(), _mcp_connect_one() (+11 more)

### Community 127 - "boom"
Cohesion: 0.17
Nodes (12): test_daily_endpoint_exception_does_not_break(), boom(), test_get_pending_exception_does_not_break_state(), boom(), test_metrics_callback_exception_does_not_break_state(), boom(), test_services_endpoint_exception_does_not_break(), boom() (+4 more)

### Community 128 - "_grab_selection"
Cohesion: 0.28
Nodes (8): _clipboard_has_non_text(), _grab_selection(), True when the clipboard holds an image/files and no text: Jarvis can't put that…, Copies the focused app's selection into holder["text"], then puts the user's…, _fake_selection_env(), test_selection_is_grabbed_attached_and_clipboard_restored(), test_selection_leaves_a_picture_clipboard_alone(), test_selection_never_injects_into_a_shortcut_chord()

### Community 129 - "jarvis_cache.py"
Cohesion: 0.38
Nodes (5): is_self_contained(), normalize_text(), Small, local-only cache helpers shared by jarvis.py: an env-flag reader,…, Lowercase, punctuation-stripped, whitespace-collapsed — so 'System status?' and…, test_normalize_and_self_contained()

### Community 130 - "test_memory_edit.py"
Cohesion: 0.25
Nodes (3): jarvis(), fixture, Editable memory (P3): list/edit/forget facts, profile fields, forget_fact tool,…

### Community 131 - "_speak_session_stub"
Cohesion: 0.14
Nodes (11): Duck-types tts_deepgram.StreamingSynthesis for _speak_streamed tests:…, Real audio already played before the interruption — must be reported as handled…, The critical Phase B safety property: the background pre-fetch thread for the…, _speak_session_stub(), test_speak_streamed_failure_before_any_audio_is_not_handled(), test_speak_streamed_happy_path(), test_speak_streamed_mid_stream_failure_after_audio_is_handled_but_incomplete(), test_speak_text_caches_complete_streamed_audio_for_reuse() (+3 more)

### Community 132 - "Snake"
Cohesion: 0.31
Nodes (3): Simple Snake game using tkinter. Arrow keys / WASD to move, R to restart., Snake, test_the_gate_still_works_normally_when_no_question_is_open()

### Community 135 - "_claude_request"
Cohesion: 0.08
Nodes (33): system(), _claude_failure_reason(), _claude_in_cooldown(), _claude_live_problem(), _claude_request(), _claude_stream_first_round(), _speak_ready(), _extract_ready_sentences() (+25 more)

### Community 136 - "classify_intent"
Cohesion: 0.29
Nodes (8): classify_intent(), parametrize, test_briefing_intents(), parametrize, test_classify_intent(), parametrize, test_media_voice_commands(), test_new_intents()

### Community 137 - "queue_or_deliver_notification"
Cohesion: 0.04
Nodes (67): _autonomy_calendar_events(), _autonomy_callbacks(), _autonomy_poll_mail(), _autonomy_run_agent(), _briefing_fetchers(), calendar(), failed(), mail() (+59 more)

### Community 139 - "_scripted_claude"
Cohesion: 0.33
Nodes (6): Fake Claude: with a tool_name, the first call requests it and the next returns…, _scripted_claude(), test_reply_cache_disabled_by_env(), test_reply_cache_never_stores_mutating_turns(), test_reply_cache_serves_readonly_repeat_without_claude(), test_reply_cache_skips_context_dependent_and_toolless_turns()

### Community 140 - "jarvis_guest_reminders.py"
Cohesion: 0.15
Nodes (15): forward_reminder(), _norm(), parse_yes_no(), Reminders while an unrecognized person is at the computer (driven by the face…, True/False for a clear yes/no, None otherwise. Deliberately strict: the WHOLE…, True after the owner said "no": reminders speak even with a stranger in view., True when each held reminder should also be texted to the owner., Text a held reminder to the owner's phone (best effort; it stays queued either… (+7 more)

### Community 141 - "start"
Cohesion: 0.67
Nodes (3): Blocking call — run this in its own daemon thread from jarvis.py's main().…, start(), _metrics_loop()

### Community 144 - "_StubSession"
Cohesion: 0.25
Nodes (5): Duck-types jarvis_stt_deepgram.StreamingSession's finish() surface for…, _StubSession, test_transcribe_pcm_falls_back_to_rest_when_stream_fails(), test_transcribe_pcm_too_short_audio_still_tears_down_stream_session(), test_transcribe_pcm_uses_streaming_session_result_when_present()

### Community 145 - "_wait_solo_hold"
Cohesion: 0.10
Nodes (20): _foreground_window(), _get_active_window_title(), _grab_appshot(), _grab_dictation(), _keyboard_is_pressed(), _mouse_button_down(), _other_keys_down(), Best-effort title of the current foreground window (Windows only) — used purely… (+12 more)

### Community 147 - "Google re-authentication (when tokens expire, every 7 days in Testing mode)"
Cohesion: 0.50
Nodes (3): Calendar, Gmail, Google re-authentication (when tokens expire, every 7 days in Testing mode)

### Community 148 - "jarvis_weather.py"
Cohesion: 0.50
Nodes (7): _fmt_temp(), _geocode(), _get(), _locate_by_ip(), Weather via Open-Meteo (free, no API key). QOL pass, 2026-09-23. Location: the…, resolve_location(), weather_report()

### Community 149 - "AttGmail"
Cohesion: 0.29
Nodes (7): AttGmail, Writes the 'downloaded' file where the real tool would., test_family_reply_prompt_frames_and_neutralises_what_the_sender_wrote(), __call__(), test_oversized_and_failed_downloads_are_reported(), __call__(), test_read_attachments_text_scanned_pdf_image_and_unreadable()

### Community 150 - "send_with_retry"
Cohesion: 0.33
Nodes (6): send() -> (ok, detail). Tries once, then retries every delay_s seconds, up to…, send_with_retry(), test_send_exception_counts_as_failure(), test_send_gives_up_after_five_retries(), test_send_retries_every_minute_then_succeeds(), send()

### Community 151 - "_http_error"
Cohesion: 0.33
Nodes (6): _http_error(), test_credit_error_fails_over_to_gemini_and_skips_claude_for_a_while(), fake_urlopen(), test_gemini_private_fields_are_not_sent_to_claude(), fake_urlopen(), test_no_failover_without_gemini_key_or_when_disabled()

### Community 152 - "jarvis_untrusted.py"
Cohesion: 0.40
Nodes (5): canonical(), _fix_word(), Handling of text written by other people (mail, messages, file names, web…, The text as a human would read it: NFKC, invisible characters removed, look-…, Match

### Community 153 - "fixture"
Cohesion: 0.40
Nodes (5): client(), dashboard(), db_path(), _private_environ(), fixture

### Community 154 - "_acted"
Cohesion: 0.50
Nodes (4): _acted(), test_wp3_dashboard_log_api_shape_and_filters(), test_wp3_log_filters_summary_and_explain(), test_wp3_tool_actions_and_spoken_summary()

### Community 155 - "_selection_key_usable"
Cohesion: 0.67
Nodes (3): Shift/Alt/Win can't be a hold key (the injected Ctrl+C would become…, _selection_key_usable(), test_selection_key_validation()

## Knowledge Gaps
- **139 isolated node(s):** `state`, `ROUTES`, `ROUTES_WITH_CONTEXT`, `servicesPanel`, `servicesToggleBtn` (+134 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 1199 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_execute_tool_impl()` connect `_execute_tool_impl` to `jarvis_window_control.py`, `jarvis_sleep_mode.py`, `FileWatcher`, `jarvis.py`, `run_agent_loop`, `jarvis_memory_enhance.py`, `queue_or_deliver_notification`, `_claude_request`, `_claude_text`, `jarvis_guest_reminders.py`, `jarvis_workflow.py`, `jarvis_dynamic_tools.py`, `jarvis_proactive.py`, `_iso`, `jarvis_weather.py`, `download_image`, `jarvis_autonomy_organise.py`, `Path`, `main`, `test_restart.py`, `jarvis_billing.py`, `jarvis_tech_understanding.py`, `_deterministic_intent_reply`, `is_paused`, `jarvis_face.py`, `jarvis_autonomy_skills.py`, `test_face.py`, `_db`, `test_dev_features.py`, `jarvis_task_scheduler.py`, `speak_text`, `test_guest_reminders.py`, `_handle_text_command_impl`, `execute_mcp_tool`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Why does `j()` connect `j` to `test_hardening.py`, `test_memory_edit.py`, `jarvis_sleep_mode.py`, `test_voice_usage.py`, `is_paused`, `_FakeProc`, `test_gemini.py`, `test_sleep_mail.py`, `test_chief.py`, `CircuitBreaker`, `test_timers.py`, `test_guest_reminders.py`, `test_safe_mode.py`, `test_hold_modes.py`?**
  _High betweenness centrality (0.042) - this node is a cross-community bridge._
- **Why does `jarvis()` connect `is_paused` to `j`, `_db`, `test_face.py`?**
  _High betweenness centrality (0.017) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `_execute_tool_impl()` (e.g. with `_launch_focus_app()` and `_memory_db_connect()`) actually correct?**
  _`_execute_tool_impl()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 68 inferred relationships involving `timedelta` (e.g. with `_action_for_commitment()` and `agent_context_line()`) actually correct?**
  _`timedelta` has 68 INFERRED edges - model-reasoned connections that need verification._
- **What connects `state`, `ROUTES`, `ROUTES_WITH_CONTEXT` to the rest of the system?**
  _139 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `test_autonomy.py` be split into smaller, more focused modules?**
  _Cohesion score 0.02508361204013378 - nodes in this community are weakly interconnected._