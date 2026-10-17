# Telegram Calling: full audit, optimization and fix pass (hand this to the coordinator)

You coordinate the Jarvis project (private repo `jarvis-main2`, branch `main`). The owner built **Telegram calling**:
the owner can ring Jarvis and talk, and Jarvis can ring the owner and talk. Audit it end to end, optimize it, fix
everything you find, prove each fix with a test, and report with measured time. Do not stop at a skim.

**Time box: at least 90 minutes of real engineering. Report measured elapsed time (clock), never an estimate.**

---

## 0. Ground rules (read first, never violate)

0.1 **Ask before building.** CLAUDE.md "Ask before building" (owner rule 2026-10-03): for any NEW capability use
    AskUserQuestion with a recommended option and trade-offs. Fixing bugs and finishing the stated intent below needs
    no question.
0.2 **Catastrophic gate stays.** Shutdown/restart/format/wipe (and widened equivalents) only STAGE. A voice "yes" on a
    call can NEVER confirm: caller speech is `source="phone"` with `_command_ctx.hands_free = True`. Do not relax.
0.3 **Secrets and identity.** The spare Telegram account's phone number, the API hash, session files and the owner's
    Telegram id never appear in code, tests, docs, logs, commit messages or reports. `TGCALL_API_HASH_SECRET` is
    write-only. Tests build fake secrets at runtime.
0.4 **Only the owner's main account** may reach Jarvis. Any other caller is ignored (no answer, no reply, no log of
    contents). Do not add other allowed callers.
0.5 **Full auto-act** stays for non-catastrophic tools (owner decision). No new permission nags.
0.6 **Quiet assistant.** A call is something the owner asked for or is making, so speech on the call is fine; everything
    else (call results, failures, "I tried to ring you") goes to the "what did I miss" inbox unless urgent.
0.7 **Local-first**: no new mandatory cloud service. Telegram + the speech engines already in use only.
0.8 **Tests never touch the real `jarvis_memory.db`, `.env`, or a real Telegram account.** Use `JARVIS_MEMORY_DB_PATH`
    temp DBs and fakes. Never ring anyone from a test.
0.9 **Public export**: `jarvis_tgcall.py` and its tests are public-exported. No personal words, numbers, ids, names.
    Run `python tools/export_public.py ../jarvis4u` and require "Privacy scan: clean". Then follow the standing rule to
    publish to Jarvis4U.
0.10 After each phase of work: `graphify update .`, commit with a clear message, push to `main` (merge first if moved,
    never force-push), then publish to the public repo. Report the cost table (format in CLAUDE.md).

---

## 1. Map the system (write this down before editing)

1.1 Files (read each fully, not only hunks):
    - `jarvis_tgcall.py` (about 1,130 lines): audio helpers, `Listener` (energy VAD), `Talker` (paced frames, barge-in),
      `Conversation`, `TelegramTransport` (outgoing), `InboundTransport` + `start_inbound`/`stop_inbound`, `call_owner`,
      `start_in_background`, session claim (`claim_session`, `_release_session`), limits (`reserve`/`refund`), CLI
      (`login`, `test`, `status`, `load_dotenv`).
    - `jarvis_callmebot.py` (one-way fallback) and `test_callmebot.py`.
    - `jarvis.py` wiring: `_tgcall_run_command`, `_tgcall_synth`, `_tgcall_shape`, `_tgcall_hooks`, `_tgcall_done`,
      `_tgcall_inbound_done`, `_place_phone_call`, the urgent-alert call path (`JARVIS_CALL_ON_URGENT`), the
      `send_to_my_phone` channel `call`, and the `start_inbound` call in `main()`.
    - `jarvis_settings.py` entries for TGCALL/CALL settings; `test_tgcall.py` (about 750 lines).
    - CLAUDE.md section "Two-way Telegram calls" and phase rows 180-188.
1.2 Draw (text diagram is fine) the two flows with every thread named:
    a) Outgoing: trigger -> `reserve` -> `call_owner` -> `TelegramTransport._run` -> ring -> answer -> `Conversation.run`
       -> Listener/Talker -> `_tgcall_run_command` -> reply -> TTS -> frames -> hang up -> `CallResult` -> inbox.
    b) Incoming: `start_inbound` loop -> connect -> wait for ring -> verify caller id -> answer -> same Conversation ->
       hang up -> listener resumes.
1.3 List every shared resource: the single-user Telethon session file, the claim file, the audio device (must NOT be
    the PC speakers/mic), the TTS engines and their circuit breakers, the daily call counter, the `_command_ctx`
    thread-locals, the Deepgram/Whisper STT path.
1.4 Environment facts to verify, not assume: the PC runs Python 3.14 (seen in tracebacks) while the pinned call stack is
    `telethon==1.45.0 py-tgcalls==3.0.0 ntgcalls==3.0.3` documented for Python 3.12. Find out which interpreter Jarvis
    really uses (`jarvis_python.txt`) and whether those wheels exist for it.

---

## 2. Known open problems (start here, these are real)

2.1 **Calls drop after about 3-4 seconds in both directions** (phase 188: root cause NOT known; diagnostics added).
    Work through, with evidence:
    - Read how the drop is recorded (Telegram `LEFT_CALL`, failed audio send, seconds after answer). Use the owner's
      `python jarvis_tgcall.py test` output if provided; otherwise ask the owner for it (AskUserQuestion), do not guess.
    - Candidates, each to confirm or kill: wrong frame size/channel layout for ntgcalls (20 ms mono vs 10 ms stereo; the
      latest commits switched the default to 10 ms stereo, `JARVIS_TGCALL_STEREO=0` for mono); sample rate not 48 kHz;
      `send_frame` coroutine vs plain call; no audio sent for the first N ms so the peer times out; keepalive/ping missing;
      event loop blocked by synchronous TTS/STT on the asyncio thread; the asyncio loop and Jarvis threads sharing the
      Telethon client unsafely; session lock errors ("database is locked") killing the call; Python 3.14 vs 3.12 binary
      mismatch in ntgcalls; Opus encoder starvation (frames paced too slowly or in bursts).
    - Add a **hermetic reproduction** with a fake transport that models the failure (e.g. the peer drops if no frame
      arrives within 2 s, or if a frame is the wrong size) and prove the fix against it.
2.2 **Unverified assumptions** listed in CLAUDE.md: incoming-frame tagging, whether `play()` returns/blocks, whether
    py-tgcalls 3.0.0 exposes `ChatUpdate.Status.INCOMING_CALL`, whether `app.play()` answers a ringing private call.
    For each: read the installed library source (pip download or the site-packages copy) and confirm the exact API. Where
    it differs, fix the code and pin it with a test that uses a fake modelled on the REAL signature.
2.3 **Session contention**: the incoming listener, outgoing `call_owner`, the CLI `test`/`login`, and any second Jarvis
    instance share one session file. Verify the claim/yield protocol under races (listener connecting while an outgoing
    call starts; crash while holding the claim; stale claim from a dead PID; PID reuse; two quick "call me" commands).
2.4 **"It said it was ringing but never rang"** (phase 185) and **"database is locked"** (phase 187): confirm both fixes
    hold, and that every "calling you now" reply is only spoken AFTER the ring actually started (or says "trying").

---

## 3. Audit checklist (go through every item; record PASS/FAIL/FIXED with evidence)

### 3A. Security and safety
3A.1 Gate: from a call, send "shut down the computer", then "yes", on both outgoing and incoming calls. The action must
      stay staged; "yes" must be refused with the "use push-to-talk" style message. Prove with a test through the real
      `_tgcall_run_command` path, not a mock of the gate.
3A.2 Caller identity: incoming accepts ONLY the owner's chat id. Test: another user id, a bot, a group call, a
      call from the spare account itself, a missing/None id, a string-vs-int id mismatch, a username that changes.
3A.3 What the caller can do: calls are `source="phone"`. Confirm the phone-source limits (attended-only tools refused,
      `forget_fact`, enroll/delete face, restart/update refused for hands-free) still hold on a call.
3A.4 Prompt-injection: caller speech and also anything Jarvis reads aloud (mail text, web text) is data. Confirm
      transcripts are framed/sanitized before the agent sees them, and that Jarvis reading untrusted text to the owner
      on a call cannot trigger tools by itself.
3A.5 Secrets: grep logs, `CallResult`, inbox entries, audit rows and exceptions for the API hash, session path
      contents, phone number, tokens. `_redact`/`mask_secrets` applied where text is stored.
3A.6 Files: session dir outside the repo and OneDrive; `.session` treated as sensitive (read refused by file tools);
      file permissions; `JARVIS_TGCALL_DIR` validation; no path traversal.
3A.7 Abuse and cost: `JARVIS_CALLS_PER_DAY`, `JARVIS_TGCALL_MAX_MIN`, `JARVIS_TGCALL_IDLE_S`, same-opening-once-an-hour,
      one call at a time, refund of unanswered calls. Try to defeat each (counter reset at midnight, restart mid-call,
      concurrent triggers, refund double-count, negative/NaN env values). Telegram flood-wait and ban handling: back off
      with a clear message; never retry-loop into a ban.
3A.8 Account risk: the spare account can be banned for automation. Confirm nothing in the code calls the main account's
      session, and the docs say so. Check for aggressive reconnect/ring loops.
3A.9 Hand-over: someone holding the owner's phone can speak commands. Confirm this is documented and consider (propose,
      do not build without asking) an optional spoken passphrase or "call-only mode" that limits tools on a call.

### 3B. Correctness of the conversation engine
3B.1 `Listener`: VAD thresholds (start 0.25 s voiced, 0.5 s while Jarvis talks, end 0.8 s silence, max 20 s), noise floor
      adaptation, DC offset, clipping, one-sided/quiet callers (the latest commit keeps the louder stereo channel),
      stereo/mono conversion correctness (`stereo_to_mono`, `mono_to_stereo_frames`) with odd lengths and empty buffers.
3B.2 `Talker`: real-time pacing without drift (use a monotonic deadline schedule, not sleep(20 ms) accumulation), prefetch of
      the next sentence, barge-in stops within one frame, no audio after hang-up, no frame after `stop()`, thread joins.
3B.3 Barge-in notes: the `[Call: the caller talked over ...]` note reaches the next command exactly once.
3B.4 Goodbye detection (`is_goodbye`): "bye" inside a sentence ("that's the bye-law"), other languages, false positives
      that would hang up on the owner. Idle timeout and max-minutes enforcement, including while Jarvis is speaking.
3B.5 Filler (`FILLER_AFTER_S`): spoken once per slow command, never overlapping the real reply, never when the reply is
      already streaming. Respect the existing rule: speech stays ordered.
3B.6 Opening line, personality: the opening and replies on a call use the active personality's wording rules and voice
      sensibly (no stage directions, abbreviations said in words). Foreign scripts via the speech-script helper.
3B.7 Long replies: `_tgcall_shape` shortens for the ear (no URLs, paths, tables, code blocks, markdown, emoji read aloud).
      Test with a table, a file path, a long list, a URL.
3B.8 Numbers/units/time spoken naturally; names; the "yes/no" confirmation prompts spoken clearly on a call.
3B.9 Concurrency: what happens when a scheduled job, reminder or urgent alert wants to speak during a call? Define and
      implement: during a call, proactive messages go to the inbox (or are read after the call), never played on the PC
      speakers while the owner is on the phone, and never ring a second call.
3B.10 What happens on the PC while a call is active: is the PC mic/speaker path muted for call audio? Ensure call audio never
      plays on the PC speakers and PC speech is not fed into the call unless intended. Wake word / follow-up window must be
      off during a call (otherwise the PC mic hears the room and the call reply).
3B.11 End of call: `CallResult` always produced (answered, unanswered, declined, dropped, error, timeout) with a reason and
      duration; inbox entry written once; counters refunded only for unanswered; resources released in `finally`.

### 3C. Audio quality and latency (measure, don't guess)
3C.1 Build or extend a **latency harness** that logs, per turn: end-of-speech to STT start, STT time, agent time,
      first TTS audio, first frame sent. Report p50/p95 from the fake transport and from `python jarvis_tgcall.py test`.
3C.2 Targets (propose, confirm with owner): end-of-speech to first reply audio under 2.5 s for simple commands; under
      1 s for no-LLM intents (time, timer, volume, missed).
3C.3 STT: use the streaming Deepgram path for calls if available (the push-to-talk code opens a live session at press;
      a call has no press, so open it at speech start and feed blocks). Fall back to REST then Whisper. Confirm the
      audio sample-rate conversion 48 kHz to 16 kHz is high quality and not a naive decimation (aliasing hurts accuracy).
3C.4 TTS: sentence-level pipelining so the first sentence plays while the next is synthesized; reuse the TTS cache for
      fixed lines (opening, "one moment", goodbye); resample 24 kHz/22.05 kHz to 48 kHz with proper filtering; normalize
      loudness; avoid clicks at sentence joins (short fades).
3C.5 Opus and network: frame size, bitrate, jitter handling, packet loss behaviour, what the code does when
      `send` raises or blocks, and a bounded queue so a slow link never grows memory.
3C.6 CPU: the VAD and resampling must not starve the asyncio loop. Measure CPU per call minute. Heavy work (STT, TTS,
      agent loop) runs off the event-loop thread.
3C.7 Echo and feedback: Jarvis's own voice returning through the caller's speaker is picked up as "caller speech" and
      triggers barge-in. Check the cut-in logic uses level relative to what Jarvis is sending; add echo-aware gating if
      needed (do not cut in on a quiet echo of our own audio).

### 3D. Reliability and recovery
3D.1 Login lifecycle: expired/revoked session, 2FA password, flood-wait on login, deleted account. Clear one-line messages,
      `status` shows the state, the listener backs off (cap, jitter), never spins.
3D.2 The inbound listener thread: crash-safe (supervise like the mic loop: reconnect with backoff, log to the crash log, no
      silent death), stops cleanly on Jarvis exit, does not keep the process alive, and does not hold the session while idle
      longer than needed (or holds it deliberately; document it).
3D.3 Network loss mid-call: detect, say nothing on a dead line, record "dropped", offer a retry once, no infinite redial.
3D.4 Jarvis restart during a call: the call ends cleanly; the next start does not claim a stale session; the "call
      me when you are back" path (if any) is bounded.
3D.5 Clock changes, sleep/wake, VPN or proxy switches while the listener is up.
3D.6 Interpreter and dependency checks: a clear `INSTALL_HINT` message and a doctor entry (`jarvis_doctor.py`) when the
      optional packages are missing or incompatible with the running Python; health card shows call status
      (configured, logged in, listener up, last call result, last drop reason).
3D.7 Windows specifics: console encodings, the hidden launcher (`Jarvis.vbs`), antivirus/firewall prompts, long paths.

### 3E. Integration with the rest of Jarvis
3E.1 `send_to_my_phone(channel="call")` and urgent alerts: only ring when the alert truly is urgent (CLAUDE.md quiet
      rules); never ring in Sleep Mode unless the owner enabled it; never while a call is active; respect safe mode.
3E.2 Reminders: a due reminder may speak its CONTENT on a call if one is active; otherwise follow existing delivery.
3E.3 "Call me" voice/text commands: deterministic intent where possible (no LLM round trip), honest result wording
      ("ringing now", "couldn't reach Telegram: reason").
3E.4 Dashboard: a Calls card (Home or Toolbox): status, last 10 calls (time, direction, duration, result, drop reason),
      Settings switches, a "Test call" button that is attended-only and goes through the same Host/Origin guards. Read-only
      data via `dashboard_data` so Jarvis can answer "when did I last call you".
3E.5 Settings: every `TGCALL_*`/`JARVIS_TGCALL_*`/`JARVIS_CALL*` key is in `jarvis_settings.py` with a help string, secrets
      are write-only, numeric values go through `jarvis_env.env_int/env_float`, bad values never crash import.
3E.6 Self-awareness journal: call started/ended/dropped/failed is recorded (`selfaware.record`, subsystem "system" or a
      new one added to `SUBSYSTEMS`), without contents.
3E.7 Audit trail: each call gets one audit row (direction, duration, result), no transcripts of private content beyond
      what the normal command audit already stores.
3E.8 Conversation memory: commands spoken on a call enter history like phone commands; the reply cache must not serve a
      cached reply that depends on call state.
3E.9 Multi-user/Guest/face rules unaffected; Away mode / Sleep Mode interplay defined and tested.

---

## 4. Optimization work (after correctness)

4.1 Latency: apply the findings of 3C.1 with the biggest win first; keep a before/after table in the report.
4.2 Cost: STT/TTS characters per call minute, cache hit rate for fixed phrases, avoid re-synthesizing the opening, use the
    cheap model for the simple-intent path, keep the prompt small (calls are short turns: no long history, no tool
    narrowing mistakes). Add a voice-usage record for call audio (lengths only, never text) so the Voice page counts it.
4.3 Memory/CPU: reuse buffers, avoid per-frame allocations in the hot loop, avoid numpy copies per 10 ms frame where a
    preallocated buffer works; confirm no growth over a 15-minute simulated call.
4.4 Startup: the inbound listener must not slow Jarvis startup (lazy import of telethon/py-tgcalls, thread start staggered).
4.5 Code health: split `jarvis_tgcall.py` only if a clear seam exists (audio/VAD, transport, CLI); keep the module free of
    `jarvis` imports (a test pins it); remove dead code; no duplicated helpers with `jarvis_callmebot.py`.

---

## 5. Test and proof requirements

5.1 For every bug: write the failing test first (show it fails on the old code), then the fix, then the passing run.
    Mutation-check the important ones (revert the fix, confirm the test fails).
5.2 Extend `test_tgcall.py`: fake transport modelled on the real library signatures; simulated 15-minute call with
    synthetic audio (silence, speech, one-sided, clipped, echo); barge-in timing; drop-after-N-seconds regression;
    session-claim races with threads; inbound caller-id matrix; gate-can't-be-confirmed-on-a-call end to end.
5.3 Pin invariants with AST/grep tests: `jarvis_tgcall.py` never imports `jarvis`, never references the gate or
    `skip_confirmation`; secrets never appear in `repr` of config/result objects; the wrapper in `jarvis.py` sets
    `hands_free`.
5.4 Run the full suite and diff the failure list against the known baseline (about 83 pre-existing Linux-container
    failures: Windows-only, camera, missing packages). **No new failures allowed.** Run `python -m pyflakes` on every
    changed module.
5.5 Public export: scan clean, then run the public copy's tests for the changed area.

---

## 6. What cannot be proven in the cloud (list for the owner, do not claim it works)

- A real ring from the spare account to the main account and back (needs the owner's phones and the SMS login).
- Real audio quality, echo on speakerphone vs headphones, latency over the owner's actual network.
- Python 3.14 behaviour of ntgcalls/py-tgcalls on the owner's PC.
- Windows firewall/antivirus prompts, Telegram anti-spam responses.
Provide a numbered **live checklist** for the owner: exact commands (`python jarvis_tgcall.py status`, `test`), what to
say, what each outcome means, and where the logs/crash log are (`jarvis_crash.log`, `jarvis_standalone.log`).

---

## 7. Docs

7.1 Update CLAUDE.md: replace the "Not verified" lines with what is now verified or still open; add rules to keep from
    this pass (frame format, claim protocol, echo gating, per-call limits). Add phase rows with MEASURED time and the
    running total. Match the existing style, no novel.
7.2 Update `public/README.md` only for user-facing changes. Keep personal data out of public docs.
7.3 Add a short "Telegram calls: setup and troubleshooting" block (login, test, status, common errors: UserIdInvalid,
    database is locked, FloodWait, LEFT_CALL, missing packages) to the right doc, with no personal values.

---

## 8. Final report (exactly these sections)

1. Scope: files, functions, commits (SHAs) reviewed, and elapsed time measured.
2. Findings table: id, severity (high/medium/low), area (3A..3E), what was wrong, evidence.
3. Fixes: file and behavior change per finding, with the test that pins it.
4. Optimizations: before/after numbers (latency p50/p95, CPU, memory, cost per call minute).
5. Root cause of the 3-4 second drop: confirmed / still unknown, and the evidence either way.
6. New tests and suite result vs baseline.
7. Live checklist for the owner and everything that is unverified.
8. Proposals needing the owner's decision (do not build): e.g. call passphrase, call-only tool limits, second allowed caller.
9. Cost table in the CLAUDE.md format, with the running total.

If two goals conflict, prefer: safety > not spamming the owner > a working call > lower latency > code tidiness.
