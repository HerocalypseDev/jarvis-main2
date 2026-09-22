# Speed Upgrade: Deepgram-native voice pipeline

Goal: cut voice-in -> first-audio-out latency by swapping local Whisper (STT) and the
Fish->Piper chain (TTS) for Deepgram Nova-3 / Aura 2 as the *primary* path, with the existing
engines kept as automatic fallback. Off by default (no `DEEPGRAM_API_KEY` = unchanged behavior).

## Architecture

- `jarvis_stt_deepgram.py` — Nova-3 pre-recorded transcription (`POST /v1/listen`) via stdlib
  `urllib`, no SDK. The push-to-talk capture path is unchanged (the full hold-to-release buffer
  is still captured first); this only swaps what happens to that buffer after release.
- `jarvis_tts_deepgram.py` — Aura 2 synthesis (`POST /v1/speak`) via stdlib `urllib`, requesting
  `encoding=linear16&container=wav` so the response is a self-describing WAV, same
  `(pcm_int16_bytes, sample_rate)` contract as the existing Fish/Piper functions.
- `jarvis_latency.py` — per-command latency tracker + a tiny intent classifier, used only for
  voice commands (`jarvis.transcribe_pcm`, `run_agent_loop`, `speak_text` call `latency.current()`
  and no-op if it's `None`, i.e. for text/dashboard/phone commands).
- `jarvis_cache.CircuitBreaker` — shared by both Deepgram backends: 3 consecutive failures trips
  it for 120s, so a Deepgram outage is skipped fast instead of paying a timeout on every command.

### Why REST + `urllib`, not the `deepgram-sdk` package

The plan called for pinning `deepgram-sdk`, but the installed/latest version (7.x) has a very
different API from the plan's snippets (which target the old 3.x SDK), and Deepgram's
pre-recorded STT and TTS REST endpoints are simple enough that the existing codebase's own
pattern — `_fish_audio_synthesize` in jarvis.py, plain `urllib.request` — covers them with zero
new dependencies and zero SDK-version risk. `requirements.txt` is unchanged.

### What was deliberately *not* built

- **True duplex/streaming STT.** Nova-3 is used via the pre-recorded endpoint on the whole
  captured buffer, not a live WebSocket fed chunk-by-chunk during the hold. The task explicitly
  said to preserve the push-to-talk capture path; streaming STT would mean rewriting audio
  capture itself. Pre-recorded Nova-3 on a short clip is still fast.
- **Token-level streaming from Claude (`_claude_request`).** `run_agent_loop` still gets the
  full reply text back before speaking. Real SSE streaming would touch the tool_use parsing loop
  (a sensitive, well-tested path) for a benefit mostly already captured by sentence-level TTS
  pipelining below — the mismatch between "big architecture change" and "marginal extra win"
  wasn't worth it here.
- **Routing simple intents to a cheaper model.** `CLAUDE_MODEL` already defaults to Haiku 4.5 —
  there's no cheaper model to route to. `jarvis_latency.classify_intent()` still classifies and
  logs the intent (time/date/volume/open_app/timer_reminder/complex) for observability and any
  future routing decision, it just doesn't change which model answers.
- **Semantic/embedding response cache.** Reuses the existing REPLY + TTS caches
  (`jarvis_cache.py`) unchanged; `sentence-transformers`-style semantic caching was explicitly
  out of scope unless clearly beneficial, and it isn't obviously worth a new heavy dependency
  here.
- **Dashboard latency panel.** `jarvis_latency.recent(n)` exists in memory for this if wanted
  later; no UI was built (explicitly nice-to-have, not required).

## Env vars

| Var | Default | Meaning |
|---|---|---|
| `DEEPGRAM_API_KEY` | (unset) | Required for either Deepgram backend. Unset = pure Whisper + Fish/Piper, identical to before this upgrade. |
| `JARVIS_STT_BACKEND` | `auto` | `deepgram` \| `whisper` \| `auto` (deepgram if a key is set and the STT circuit breaker isn't tripped). |
| `JARVIS_TTS_BACKEND` | `auto` | `deepgram` \| `fish` \| `piper` \| `auto` (deepgram if a key is set and the TTS circuit breaker isn't tripped; explicit `fish`/`piper` skip Deepgram entirely). |
| `JARVIS_DEEPGRAM_STT_MODEL` | `nova-3` | Passed as `model=` on `/v1/listen`. |
| `JARVIS_DEEPGRAM_TTS_MODEL` | `aura-2-thalia-en` | Passed as `model=` on `/v1/speak`. Any Aura 2 English voice id works. |
| `JARVIS_DEEPGRAM_STT_TIMEOUT_S` | `8.0` | Hard timeout (watchdog-thread enforced, same idiom as `_urlopen_hard_timeout`) for the STT request. |
| `JARVIS_DEEPGRAM_TTS_TIMEOUT_S` | `15.0` | Same, for TTS. |
| `JARVIS_DEEPGRAM_STT_MIN_CONFIDENCE` | `0.6` | Below this, the Deepgram transcript is discarded and Whisper is tried instead. |
| `JARVIS_TTS_SENTENCE_STREAM_MIN_CHARS` | `120` | Replies longer than this are split into sentences and pipelined (see below); shorter replies are spoken as one utterance, same as before. |
| `JARVIS_TTS_FILLER_DELAY_S` | `2.5` | If nothing has been spoken yet after this many seconds into a voice/dashboard command, Jarvis says "One moment." once. |

## Backend order

- **STT**: Deepgram Nova-3 -> local Whisper (on any failure, exception, timeout, or
  below-floor confidence).
- **TTS**: Deepgram Aura 2 -> Fish Audio -> Piper (on any failure of the previous engine).
  Both breakers (`jarvis._dg_stt_breaker`, `jarvis._dg_tts_breaker`) trip after 3 consecutive
  failures and cool down for 120s, so an outage doesn't pay a timeout on every single command.

Every engine's output is cached under its own key in the existing on-disk TTS cache
(`.cache/tts/`, `jarvis_cache.TTSDiskCache`) — a cache hit for *any* configured engine is served
before synthesizing again, but a fallback clip is never stored under a different engine's key.

## Sentence-level TTS pipelining (Phase 2.1)

`speak_text()` splits a reply longer than `JARVIS_TTS_SENTENCE_STREAM_MIN_CHARS` into sentences
(`_split_sentences`, punctuation-based, merges fragments under 20 chars into a neighbor so
nothing choppy gets spoken alone). It synthesizes and plays the first sentence, then — while that
sentence is playing — synthesizes the *next* one on a background thread, so time-to-first-audio
is bounded by one sentence's synthesis time instead of the whole reply's. No cancellation logic
is needed: if the real audio becomes ready before a short filler phrase finishes, they just
serialize through the existing playback lock for well under a second.

The background pre-synthesis is joined with a bounded `PIPELINE_JOIN_TIMEOUT_S` (90s) rather
than an unbounded `join()` — every engine call inside it is already individually timeout-bounded
(Deepgram, Fish) or purely local/CPU (Piper), so this is a defense-in-depth backstop, not the
primary bound. If it's ever hit, nothing spoken is lost: the abandoned prefetch is just
discarded (`pending` stays `None`) and that sentence is synthesized again, synchronously, on the
next loop iteration — the timeout costs only the overlap benefit for that one sentence, never
the content. A warning is logged either way (audit fix, 2026-09-22).

`speak_text()`'s per-command `tts_backend` (in the latency log) is the *last* engine that
actually spoke, not the first — updated on every successful sentence, not latched after the
first one. A command that narrates via Deepgram but whose final (longer) reply falls back to
Piper mid-command now correctly logs `tts_backend=piper`, not a stale `deepgram` from the
narration (audit fix, 2026-09-22; `tts_ttfa_ms` is unaffected — that still marks only the first
successful sentence, which is the correct TTFA definition).

## Filler phrase (Phase 3.2)

If `reply_sink is None or source == "dashboard"` (i.e. this command will be spoken here) and
`run_agent_loop` hasn't returned within `JARVIS_TTS_FILLER_DELAY_S`, Jarvis says "One moment."
once (`jarvis._speak_filler_if_slow`). It's a single fixed short phrase — it hits the existing
TTS disk cache after the first use, so on every later slow command it's served instantly rather
than re-synthesized.

The filler also backs off if a mid-task narration line already spoke real content for this same
command before the delay elapsed, not only if the command finished (audit fix, 2026-09-22): the
same `threading.Event` used to signal "command done" is also set by `speak_text()` itself the
moment any audio actually plays. `speak_text()` reaches it via a thread-local
(`jarvis._current_speak_signal()`, set by `_handle_text_command_impl` for the duration of the
command on the same thread that runs `run_agent_loop`/narration); the filler's own watcher thread
holds a direct reference to the same `Event`, so no cross-thread lookup is needed on that side.
Without this, a command that narrated at ~1s and kept working past 2.5s would get a stale "One
moment." spoken after real content had already answered part of the question.

## Lazy Whisper preload

`main()` only calls `_preload_whisper_async()` at startup when Whisper is actually likely to be
needed — i.e. `JARVIS_STT_BACKEND=whisper`, or no `DEEPGRAM_API_KEY` is set (same condition as
`_use_deepgram_stt()`). When Deepgram is configured and healthy, Whisper is never touched at
startup; `_get_whisper_model()` still loads it lazily (and only once, lock-guarded) the first
time a real command actually falls back to it. Before this fix, Whisper's `faster-whisper` model
was preloaded unconditionally whenever push-to-talk was enabled, paying its CPU/RAM load cost on
every restart even when Deepgram was primary and healthy and Whisper might never run that session
(audit fix, 2026-09-22).

## Latency measurement

Every voice command logs one line:

```
latency stt=180ms ttft=610ms tts=95ms e2e=1120ms stt_backend=deepgram tts_backend=deepgram intent=complex
```

- `stt` = time from capture-end to transcript ready.
- `ttft` = time to the *first* Claude response of the agent loop (not necessarily the final one
  — a multi-tool command has more round trips after this).
- `tts` = time from capture-end to the first audio chunk being ready to play (time-to-first-audio,
  TTFA) — for a pipelined multi-sentence reply this is the first sentence's synthesis time, not
  the whole reply's.
- `e2e` = total time from capture-end to the last sentence finishing playback.

Grep the Jarvis log for `latency ` to compare runs, or call `jarvis_latency.recent(n)` for the
last N as structured dicts. Text/dashboard/phone commands don't log this line (no push-to-talk
capture-end to measure from).

## How to measure a real before/after

1. Baseline: leave `DEEPGRAM_API_KEY` unset, run a few representative voice commands (a
   read-only question, a tool call, a longer multi-sentence reply), note the `latency` lines.
2. Set `DEEPGRAM_API_KEY` in `.env`, restart Jarvis, repeat the same commands.
3. Compare `stt`, `tts`, and `e2e` between the two logs. `ttft` should be roughly unchanged
   (Claude's own latency + prompt caching, untouched by this work) unless the intent classifier
   later gets wired to an actual routing decision.

## Privacy / risk (documented per CLAUDE.md's standing rule)

- With Deepgram enabled, microphone audio (STT) and spoken-reply text (TTS) leave the machine
  for Deepgram's API — same category of exposure Fish Audio and every Claude API call already
  have (see CLAUDE.md's TTS section), not a new kind of risk, just a second cloud vendor.
  `DEEPGRAM_API_KEY` unset keeps everything local (Whisper + Piper), same as before.
- Confidence gating and the circuit breaker are latency/quality safeguards, not security
  controls — they only affect which engine answers, never the confirmation gate or any tool
  permission.

## Tests

`test_deepgram_voice.py` (41 tests, no real network): `jarvis_cache.CircuitBreaker`,
`jarvis_latency` (marks/finish/classify_intent), `jarvis_stt_deepgram.transcribe` (success, low
confidence, network error, timeout, no key, empty audio), `jarvis_tts_deepgram.synthesize`
(success, network error, timeout, no key, warm), and jarvis.py wiring (Deepgram-first with
fallback for both STT and TTS, explicit backend overrides, both circuit breakers tripping *and*
recovering after cooldown, sentence splitting/pipelining, the bounded pipeline join timeout,
filler phrase including the narration-already-spoke backoff, and the lazy-Whisper-preload
condition). `test_cache.py`'s existing Fish/Piper tests are unaffected (its `jarvis` fixture now
also zeroes both Deepgram module keys so a real `.env` key on the dev machine can't change their
behavior).

Not verified live (would need a real `DEEPGRAM_API_KEY` and microphone): actual Nova-3
transcription accuracy/latency on real speech, actual Aura 2 audio quality, real end-to-end
voice-in -> first-audio-out timing numbers.

## Audit-and-fix pass (2026-09-22)

An adversarial re-read of the whole stack (wiring, lazy-Whisper, STT/TTS correctness, fallback
chains, latency honesty, sentence pipelining, caching, concurrency, privacy) found five real
issues, all fixed and pinned by new tests: Whisper was preloaded eagerly even with Deepgram
configured (now lazy — see above); `tts_backend` latched to the first engine used instead of the
last (now updated every successful sentence); the filler phrase could speak after narration
already had (now backs off via a shared signal — see above); the sentence-pipelining background
thread was joined without a timeout (now bounded, degrades to synchronous re-synthesis rather
than hanging); and STT circuit-breaker tripping/recovery and a real `TimeoutError` path weren't
covered by tests (now are). No catastrophic-gate, autonomy-permission, or fallback-removal
changes were made. Full suite green afterward.
