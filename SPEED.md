# Speed Upgrade: Deepgram-native voice pipeline + cloud-latency pass

Goal: cut voice-in -> first-audio-out latency by swapping local Whisper (STT) and the
Fish->Piper chain (TTS) for Deepgram Nova-3 / Aura 2 as the *primary* path, with the existing
engines kept as automatic fallback. Off by default (no `DEEPGRAM_API_KEY` = unchanged behavior).
A second, later pass (also documented below) added real-time streaming on top: a live STT
WebSocket during push-to-talk (Phase A), a live TTS WebSocket for progressive playback
(Phase B), a zero/reduced-LLM fast path for simple commands (Phase D), and token-level streaming
from Claude straight into speech for the agent loop's first round trip (Phase C) — all cloud-only,
no new local/heavy models, all individually falling back to the exact same proven non-streaming
paths on any failure.

## Architecture

- `jarvis_stt_deepgram.py` — `transcribe()`: Nova-3 pre-recorded transcription (`POST
  /v1/listen`) via stdlib `urllib`, no SDK. `StreamingSession` (cloud-latency pass, Phase A):
  live `wss://.../v1/listen`, via `websocket-client` — fed while push-to-talk is held, so
  transcription mostly finishes by release instead of only starting then.
- `jarvis_tts_deepgram.py` — `synthesize()`: Aura 2 synthesis (`POST /v1/speak`) via stdlib
  `urllib`, requesting `encoding=linear16&container=wav` so the response is a self-describing
  WAV, same `(pcm_int16_bytes, sample_rate)` contract as the existing Fish/Piper functions.
  `StreamingSynthesis` (Phase B): Deepgram's *separate* streaming speak endpoint
  (`wss://.../v1/speak`), yielding raw PCM chunks as they're generated so playback can start
  before the whole utterance finishes.
- `jarvis_latency.py` — per-command latency tracker + a tiny intent classifier, used only for
  voice commands (`jarvis.transcribe_pcm`, `run_agent_loop`, `speak_text` call `latency.current()`
  and no-op if it's `None`, i.e. for text/dashboard/phone commands). `VoiceLatency.path` (Phase D)
  records which fast path, if any, a command took.
- `jarvis_cache.CircuitBreaker` — shared by both Deepgram backends: 3 consecutive failures trips
  it for 120s, so a Deepgram outage is skipped fast instead of paying a timeout on every command.
- `jarvis._claude_stream_first_round` (in jarvis.py itself, not a separate module — it needs to
  slot directly into `run_agent_loop`'s existing loop) — Claude cloud-latency pass, Phase C:
  parses Claude's own `text/event-stream` SSE response over plain `urllib` (no WebSocket, no new
  dependency; Claude streams over the same REST endpoint with `stream: true`, unlike Deepgram's
  separate WS endpoints).

### Why REST + `urllib`, not the `deepgram-sdk` package

The plan called for pinning `deepgram-sdk`, but the installed/latest version (7.x) has a very
different API from the plan's snippets (which target the old 3.x SDK), and Deepgram's
pre-recorded STT and TTS REST endpoints are simple enough that the existing codebase's own
pattern — `_fish_audio_synthesize` in jarvis.py, plain `urllib.request` — covers them with zero
new dependencies and zero SDK-version risk. `requirements.txt` is unchanged.

### What was deliberately *not* built

- **Semantic/embedding response cache.** Reuses the existing REPLY + TTS caches
  (`jarvis_cache.py`) unchanged; `sentence-transformers`-style semantic caching was explicitly
  out of scope unless clearly beneficial, and it isn't obviously worth a new heavy dependency
  here.
- **Dashboard latency panel.** `jarvis_latency.recent(n)` exists in memory for this if wanted
  later; no UI was built (explicitly nice-to-have, not required).
- **A standalone "instant ack" filler for complex commands** (cloud-latency pass, Phase E). The
  existing filler phrase (below) already covers this exact need — a second, separate ack
  mechanism would either duplicate it or need careful anti-stacking logic against it for no real
  gain.

Streaming STT (a live WebSocket during the push-to-talk hold) and token-level streaming from
Claude — both listed as *not built* in the original pass — were added in a later cloud-latency
pass; see the sections below.

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
| `JARVIS_DEEPGRAM_STT_STREAM` | `1` (on) | Stream STT live during the push-to-talk hold (Phase A) instead of only POSTing the full buffer after release. |
| `JARVIS_DEEPGRAM_STREAM_TIMEOUT_S` | `15.0` | Socket timeout for the STT WebSocket (connect + each subsequent read). |
| `JARVIS_DEEPGRAM_STREAM_FINALIZE_TIMEOUT_S` | `5.0` | How long `finish()` waits for the final transcript after sending Finalize/CloseStream. |
| `JARVIS_DEEPGRAM_TTS_STREAM` | `1` (on) | Use Deepgram's streaming speak WebSocket (Phase B) instead of the plain REST call. |
| `JARVIS_DEEPGRAM_TTS_STREAM_TIMEOUT_S` | `15.0` | Socket timeout for the TTS WebSocket. |
| `JARVIS_LLM_TTS_STREAM` | `1` (on) | Stream Claude's own response token-by-token and speak complete sentences as they arrive (Phase C), for the agent loop's first round trip only. Claude-only; no-ops on Gemini. |

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

## Cloud-latency pass (2026-09-22): streaming STT/TTS, simple-intent fast path, LLM token streaming

A second pass, on top of the Deepgram REST work above, all still cloud-only (no new local
heavy models) and all documented in CLAUDE.md too. New dependency: `websocket-client==1.9.0`
(pinned in `requirements.txt`) — a small, widely-used *synchronous* WebSocket client, chosen
because it fits this codebase's threaded (not asyncio) architecture far more naturally than an
async client would; it's used for three real-time protocols below (Deepgram STT stream,
Deepgram TTS stream, none for Claude — that one is plain SSE over `urllib`, no WS needed).

### Phase A — streaming STT during push-to-talk (`jarvis_stt_deepgram.StreamingSession`)

Instead of capturing the whole hold, then POSTing it after release, a live
`wss://api.deepgram.com/v1/listen` session now opens the moment the push-to-talk key is
pressed (`main()`'s capture loop, on its own helper thread so the blocking connect can never
stall audio capture) and is fed every captured block via `feed()` while the key is held.
`feed()` only enqueues bytes — a dedicated sender thread does the actual (blocking) WebSocket
send — so a slow/stalled connection can never stall the capture loop's real-time read cadence.
On release, `transcribe_pcm(stream_session=...)` calls `finish()`, which sends
`{"type":"Finalize"}` then `{"type":"CloseStream"}` (enqueued through the *same* queue as the
audio, not sent directly — otherwise they could race ahead of trailing audio still waiting to be
sent and truncate the transcript) and waits for the final `is_final` Results message. If the
session never connected, the send failed, or the resulting transcript is below the confidence
floor, `finish()` returns `None` and `transcribe_pcm` falls through to the existing REST call on
the full buffer (still captured regardless, exactly as before) — then Whisper. Two races were
found and fixed while building this: `feed()` calls arriving before `start()`'s connect resolves
must not be dropped (queued instead — they just wait for the sender thread to exist), and
`finish()` must wait for `start()` to resolve rather than racing ahead and wrongly concluding "no
session" on a very short hold (`_start_done` event, bounded by the same connect timeout).
`latency.stt_backend` is `deepgram_stream` for this path vs plain `deepgram` for REST.
Verified live against the real API (round-tripped Aura-2-synthesized audio back through this
exact class; also verified the press-before-connect race with a real connection).

### Phase B — streaming TTS playback (`jarvis_tts_deepgram.StreamingSynthesis`)

Deepgram also has a *separate* streaming speak endpoint (`wss://api.deepgram.com/v1/speak`,
distinct from the streaming listen one) that returns raw PCM audio chunks as Aura 2 generates
them, instead of the complete WAV file REST returns only once generation finishes. `speak_text()`
tries this first for the sentence about to play *right now* (`_speak_streamed`, playing via the
new `_play_pcm_stream`, which uses `sd.OutputStream.write()` per chunk instead of `sd.play()`
on a complete buffer) — first-chunk latency on a live test was ~0.3s into a ~1.3s total
utterance, i.e. audio starts well before the sentence has finished generating. Deliberately
**never** used by the sentence-pipelining background pre-fetch thread (existing feature, Phase
2.1 above): that thread only calls the non-streaming `_synthesize_and_cache`, because if it also
streamed+played, its playback would fight the main thread's over the shared device/lock and turn
"synthesize the next sentence while this one plays" into "wait for this one, then wait again" —
exactly backwards from the point of pre-fetching. A cache pre-check (`_tts_cache_peek`) runs
before any streaming attempt, so a repeated short phrase never pays for a WebSocket connect at
all. Once real audio has started playing, a mid-stream failure is reported as "handled" (so the
caller never falls back to Fish/Piper and double-speaks what already played) but "incomplete" (so
it's never cached as if it were the full utterance) — `latency.tts_backend` is `deepgram_stream`
either way. Verified live: real audio played through actual speakers via `_speak_streamed`
end-to-end.

### Phase D — simple-intent fast path (no new local model)

Two narrow, safe shortcuts around the ~100+ tool schema prefix, both gated by
`jarvis_latency.classify_intent()`:
- **Deterministic, zero-LLM-call** for `time`/`date` (`_deterministic_intent_reply`) — computed
  from the local clock, no network round trip at all, `run_agent_loop` is never called.
- **Reduced tool list** for `volume` (just the `system_action` tool) and a *confidently named*
  `open_app` (just the `open_app` tool, and only when the transcript actually contains one of
  `ALLOWED_APPS` — `classify_intent`'s "open ..." regex is deliberately broad for logging
  purposes, so `_reduced_tools_for_intent` re-narrows it before it's allowed to restrict
  anything; "open my email" correctly falls through to the full tool list since it needs Gmail
  tools, not `open_app`). `run_agent_loop(tools_override=...)` swaps in the smaller list; the
  catastrophic gate is unaffected either way (`_execute_tool` enforces it regardless of which
  tools were on offer). Builds its own separate cached prompt prefix from the full-tool-list one
  (Anthropic caches by exact prefix match), so it ramps up its own hit rate independently as
  these short commands repeat.
`latency.path` records which of `deterministic` / `reduced_tools` / `full` a command took.

### Phase C — LLM token streaming to speech (`_claude_stream_first_round`)

The highest-risk piece, scoped narrowly on purpose: only the agent loop's **first** round trip
streams (`iteration == 0`), and only when the reply will actually be spoken here (`narrate=True`
— the same condition existing mid-task narration already uses). It parses Claude's SSE response
directly (`text/event-stream` over plain `urllib`, no new dependency — Claude has no separate
streaming *service*, just a `stream: true` flag on the same endpoint) on a background reader
thread feeding a queue, reconstructing the *exact same* `{"content": [...], "stop_reason": ...,
"usage": {...}}` shape `_claude_request` returns non-streamed — so every later round trip (after
a tool call) and all tool-result handling in `run_agent_loop`'s loop is completely untouched
either way; this only replaces where iteration 0's `data` comes from. As text deltas arrive,
`_extract_ready_sentences` (same merge-short-fragments logic as `_split_sentences`) pulls out
each complete sentence and speaks it immediately via the normal `speak_text()` — which means
Phase C and Phase B compose for free: a live-streamed sentence's *audio* can itself stream via
Aura 2. The moment a `tool_use` content block starts, further text is only accumulated silently
(matching the *existing* narrate semantics for a non-final turn — a message with both text and a
tool call already gets its text spoken as a unit today, this just makes that progressive instead
of synchronous) and the earlier live-spoken text is flushed at that block's own `content_block_stop`
rather than waiting for the whole message to end (a real bug caught by testing: a short narration
line immediately followed by a tool call was being silently dropped, since the incremental
extractor holds back anything under 20 chars waiting for more text to merge with, and none was
coming in that content block). `on_first_token` fires at the real first token, not after the
whole stream completes, so `ttft` stays an honest measurement. On **any** failure — network,
malformed SSE, Gemini as the active provider (Claude-only; the function checks `_llm_provider()`
and no-ops instead of guessing at a Gemini streaming shape) — it returns `None` and the exact
same round trip is retried via the proven non-streaming `_claude_request`, so the model always
still gets a real answer either way.
`run_agent_loop`'s caller (`_handle_text_command_impl`) must not speak the reply *again* once it
was already spoken live sentence-by-sentence — `reply_already_spoken_via_stream()` (a per-thread
flag, explicitly reset at the *start* of every command, not only read-and-reset at the end, so an
unrelated exception between a streamed command finishing and its own check can never leak the
flag into the next command on the same worker thread and wrongly silence a real reply) answers
that. A streamed reply also skips `_summarize_for_speech` — that function exists to soften the
"wait for the whole reply, then read a shortened version" cost, which a live-streamed reply never
had in the first place.
**Audit fix (2026-09-22, second pass)**: a multi-round command — round 0 streams narration and
ends in a `tool_use`, later rounds run the normal non-streaming path — was speaking the
narration **twice**: once live during the stream, and again because the streamed text was still
being folded into `reply_parts` regardless of whether the round continued into a tool call, so
it ended up concatenated into the final `reply` text that `_handle_text_command_impl` then spoke
in full ("Let me check that. Your CPU is at 42 percent." spoken live, then the exact same thing
spoken again as one block). Fixed to match the existing (non-streamed) narrate branch's own
behavior exactly: streamed text is excluded from `reply_parts` whenever the round continues
(`going_on=True`) and only included — with `reply_already_spoken_via_stream()` then set — when
that round is the actual final one. Caught by a new test that runs a real two-round scenario
(streamed narration + tool_use, then a plain final round) rather than only single-round cases.

**Accepted rough edge**: if the connection drops *after* some sentences were already spoken live,
retrying via the non-streaming path will speak the *whole* reply again, repeating what already
played — rare (a mid-response network drop) and bounded (a stutter, not silence or corruption),
not worth the extra bookkeeping to avoid for how infrequently it should happen.
**Test-safety note**: with a fake `ANTHROPIC_API_KEY`, an unguarded `narrate=True` test would make
a *real* network call to Anthropic's streaming endpoint — both `jarvis`-fixture files now default
`JARVIS_LLM_TTS_STREAM=0`, and the handful of tests that specifically exercise streaming opt back
in with a fully mocked `urlopen`/`_claude_stream_first_round`.
Not verified live end-to-end (this session's Anthropic API key has no credit balance — a
pre-existing, unrelated limitation, not something this work caused): confirmed instead that (a)
the real API's actual HTTP-error response shape is handled identically by both the streaming and
non-streaming paths (same "credit balance too low" 400, same graceful `None` return, same
warning log), and (b) the SSE event parsing itself — the genuinely new, risky code — is covered
by mocked tests built from Anthropic's documented event shapes (`message_start`,
`content_block_start/delta/stop`, `message_delta`, `message_stop`).

### Phase E — perceived-latency polish

Already covered by the above, so nothing further was built: the filler phrase already backs off
correctly against both a finished command and live narration (see below); `stt_backend`/
`tts_backend` already carry distinct `deepgram_stream` vs `deepgram` (REST) vs `whisper`/`fish`/
`piper` labels wherever more than one path exists.

## Latency measurement

Every voice command logs one line:

```
latency stt=180ms ttft=610ms tts=95ms e2e=1120ms stt_backend=deepgram_stream tts_backend=deepgram_stream intent=complex path=full
```

- `stt` = time from capture-end to transcript ready.
- `ttft` = time to the *first* Claude response of the agent loop (not necessarily the final one
  — a multi-tool command has more round trips after this) — the real first streamed token when
  `JARVIS_LLM_TTS_STREAM` is on and eligible (Phase C), `None` for a `deterministic`-path command
  (no Claude call happened at all).
- `tts` = time from capture-end to the first audio chunk being ready to play (time-to-first-audio,
  TTFA) — for a pipelined multi-sentence reply this is the first sentence's synthesis time, not
  the whole reply's; the real first chunk written to the output device when Deepgram's streaming
  speak WebSocket was used (Phase B).
- `e2e` = total time from capture-end to the last sentence finishing playback.
- `stt_backend`/`tts_backend` = `deepgram_stream` (live WebSocket) vs `deepgram` (REST) vs
  `whisper`/`fish`/`piper`.
- `path` = `deterministic` / `reduced_tools` / `full` — which of the Phase D fast paths this
  command took (see below).

Grep the Jarvis log for `latency ` to compare runs, or call `jarvis_latency.recent(n)` for the
last N as structured dicts. Text/dashboard/phone commands don't log this line (no push-to-talk
capture-end to measure from).

## How to measure a real before/after

1. Baseline: leave `DEEPGRAM_API_KEY` unset, run a few representative voice commands (a
   read-only question, a tool call, a longer multi-sentence reply), note the `latency` lines.
2. Set `DEEPGRAM_API_KEY` in `.env`, restart Jarvis, repeat the same commands.
3. Compare `stt`, `tts`, and `e2e` between the two logs. `ttft` is now meaningfully affected too
   when `JARVIS_LLM_TTS_STREAM` is on (Phase C): it marks the real first streamed token instead
   of the whole non-streamed response, and `path=deterministic` commands (time/date) show no
   `ttft` at all since no Claude call happens. `stt_backend`/`tts_backend` show `deepgram_stream`
   when the live WebSocket paths (Phases A/B) were used instead of the REST ones.

## Privacy / risk (documented per CLAUDE.md's standing rule)

- With Deepgram enabled, microphone audio (STT) and spoken-reply text (TTS) leave the machine
  for Deepgram's API — same category of exposure Fish Audio and every Claude API call already
  have (see CLAUDE.md's TTS section), not a new kind of risk, just a second cloud vendor.
  `DEEPGRAM_API_KEY` unset keeps everything local (Whisper + Piper), same as before. Streaming
  (Phases A/B) sends the exact same audio/text over the exact same vendor connection, just live
  instead of after the fact — no new exposure category.
- Confidence gating and the circuit breaker are latency/quality safeguards, not security
  controls — they only affect which engine answers, never the confirmation gate or any tool
  permission.
- Phase D's reduced tool lists and Phase C's token streaming are latency optimizations only —
  the catastrophic gate (`_execute_tool`/`_CATASTROPHIC_PATTERNS`) is enforced identically
  regardless of which tools were offered or whether the response streamed; neither path can
  reach it any differently than the normal full-tool, non-streamed path.

## Tests

`test_deepgram_voice.py` (90 tests, no real network — every `urlopen`/WebSocket call is mocked):
everything in the first pass above (`jarvis_cache.CircuitBreaker`, `jarvis_latency`,
`jarvis_stt_deepgram.transcribe`, `jarvis_tts_deepgram.synthesize`, the REST fallback cascades,
circuit-breaker trip/recovery, sentence pipelining, the pipeline join timeout, the filler phrase,
lazy-Whisper-preload), plus the cloud-latency pass: `StreamingSession`/`StreamingSynthesis`
protocol tests (happy path, connect failure, no key, mid-stream failure before/after audio
played, the feed-before-connect and finish-races-ahead-of-start races), `speak_text`'s streaming
integration (streams only the current sentence, pre-fetch never streams, cache pre-check skips
streaming, complete streamed audio gets cached for reuse), the Phase D intent-routing functions
and their `handle_text_command`/latency-log integration, and `_claude_stream_first_round`'s SSE
parsing (sentence-by-sentence live speech, first-token timing, stopping at tool_use *and*
flushing the held-back fragment right there, Gemini no-op, network/error-event failure, and the
full `run_agent_loop` integration including the stream-then-fallback path and the
already-spoken-flag not leaking between commands). `test_cache.py`'s existing Fish/Piper tests
are unaffected (its `jarvis` fixture zeroes both Deepgram module keys and defaults
`JARVIS_LLM_TTS_STREAM=0`, so a real `.env` key or a `narrate=True` test elsewhere can't hit a
real network endpoint or change pre-existing tests' behavior).

Not verified live (would need a real `DEEPGRAM_API_KEY`/microphone, or Anthropic API credit —
this session's key has none, a pre-existing unrelated limitation): actual Nova-3/Aura-2
streaming quality on real conversational speech (vs. the synthesized-audio round-trip and the
real text-to-speech test that *were* run live), and the full Claude SSE happy path against a
real successful response (the error path — an actual HTTP 400 from the real API — was verified
live and handled identically to the non-streaming path).

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
