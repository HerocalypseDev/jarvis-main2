# Jarvis (`jarvis.py`) — Architecture Report

> Analysis of the actual current state of `jarvis.py` in this repository. No `main.py`/`paste.txt` exists in this workspace — `jarvis.py` is the real target.

## Executive Summary

`jarvis.py` is a single-file, Windows-only desktop voice assistant with five core subsystems:

1. **Activation** — a custom clap-burst detector (1 clap = serious mode, 3 claps = normal mode) plus a push-to-talk hotkey, with feedback-loop suppression so Jarvis can't hear itself.
2. **Speech recognition** — fully local transcription via `faster-whisper` (CPU, int8), no audio ever leaves the machine.
3. **Reasoning** — a single forced Anthropic tool call (`perform_actions`) per command, returning an ordered list of steps from a 15-action allowlist plus a spoken reply, with a 3-exchange rolling memory.
4. **Computer control** — a mix of command-based launches (safest), title-based window focus, and coordinate-based mouse/scroll (`pyautogui`, the most fragile category).
5. **Screen/multimodal** — single-shot screenshot-to-vision-LLM understanding (Claude vision), with a lightweight `---CODE---` text protocol for optionally typing a fix, and Cartesia TTS for spoken output.

**Classification:** a desktop automation assistant with voice I/O and one narrow, single-shot multimodal capability — not a full autonomous computer-use agent (no observe-act-observe loop, no self-verification of results).

**Biggest strengths:** allowlisted + doubly-validated actions, forced structured tool calling, no shutdown/restart/delete in the vocabulary at all, `type_text` never auto-submits, and a real architectural fix (not just tuning) for the mic-hears-itself feedback loop.

**Biggest risks:** screenshots/clipboard/code are sent to a cloud API unfiltered with no confirmation step; no runtime confirmation before clicking/typing/locking; coordinate-based actions have no DPI/multi-monitor/staleness checks; no audit log; possible prompt injection via untrusted screen/clipboard content feeding back into actions.

---

## Component 1: Activation and Input Sensing

The mic is opened once in `main()` via `sd.InputStream(device=input_idx, samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32", blocksize=blocksize)`, where `blocksize = block_samples()` computes `SAMPLE_RATE * BLOCK_MS / 1000` samples. Constants: `SAMPLE_RATE=44100`, `BLOCK_MS=40`, `CHANNELS=1` — the main loop reads one ~40ms mono block at a time, forever.

Each block's loudness reduces to one number via `rms_mono()`. An **adaptive noise floor** updates only during quiet periods (`level < noise_floor * QUIET_GATE_MULT` (2.2)) via an exponential moving average (`NOISE_FLOOR_ALPHA=0.992` — close to 1 means slow drift, so it tracks ambient noise without being dragged up by claps/speech). A clap is a **spike**: `threshold = max(noise_floor * SPIKE_RATIO, MIN_RMS)` (9× the floor, or an absolute `0.012`). `spike_armed`/`retrigger_level = threshold * RETRIGGER_RATIO(0.55)` implements hysteresis so a clap's decay tail can't double-count.

Claps are grouped into a **burst**: each qualifying spike extends the burst if it arrives within `MAX_DOUBLE_GAP_S` (0.35s) of the previous clap, or starts a new one; anything closer than `MIN_DOUBLE_GAP_S` (0.05s) is bounce and ignored. The burst resolves once `MAX_DOUBLE_GAP_S` of silence follows the last clap — then the count decides: **1 clap → `run_serious_mode_actions()`, 3 claps → `run_normal_mode_actions()`**, anything else is logged and dropped. `COOLDOWN_S` (0.45s, via `last_mode_trigger_time`) briefly blocks new spike processing right after a burst resolves.

Mic selection (`_choose_input_device`) supports a `JARVIS_INPUT_DEVICE` env override (`_resolve_input_device_index`), else probes the default device's loudness (`_probe_input_max_rms`, `INPUT_PROBE_S=0.5s` vs `INPUT_SILENT_RMS=0.001`) and scans all inputs for the loudest if the default is silent.

**Push-to-talk** (`JARVIS_PTT_KEY`, default `"left shift"`) is polled every block via `_keyboard_is_pressed()` (wraps the `keyboard` package). It's ignored entirely before activation (one log via `ptt_locked_notice_shown`). Once `jarvis_activated` is `True`, holding the key buffers blocks into `ptt_buffer`; release concatenates them and dispatches to `handle_voice_command` on a new thread.

Two mechanisms stop Jarvis hearing itself: the `jarvis_speaking` `threading.Event`, set/cleared around every `sd.play()/sd.wait()` in `_play_pcm_wav_file`/`_play_pcm_bytes` — the main loop does `if jarvis_speaking.is_set(): continue` right after reading each block. And, once `jarvis_activated` is `True`, the entire clap-detection block is skipped (`if jarvis_activated: continue`) — claps only matter for the initial activation; afterward, mode-switching only happens via the `switch_mode` voice action, which structurally eliminates the feedback-loop class of bug.

**Vs. other JARVIS projects:** implements neither a wake word (no keyword-spotting model, never inspects speech content to activate) nor always-listening transcription (Whisper only ever runs on PTT-buffered clips). What it implements is a custom acoustic-event detector (clap counter) as the wake mechanism, plus a classic push-to-talk hotkey for command capture, with the former gating the latter.

## Component 2: Speech Recognition and Language Input

PTT audio accumulates in `ptt_buffer` as raw float32 blocks; on release it's `np.concatenate`d and passed to `handle_voice_command(audio, SAMPLE_RATE)` on a background thread, keeping the main loop free to keep draining `stream.read()`.

`_resample_to_16k()` linearly interpolates (`np.interp`) from 44.1kHz to Whisper's 16kHz. `_get_whisper_model()` lazily constructs a singleton guarded by `_whisper_lock`, instantiating `faster_whisper.WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")` (CPU-only, int8-quantized). `_preload_whisper_async()` fires this at startup on a background thread so it's hopefully warm before the first PTT press. `WHISPER_MODEL_SIZE` defaults to `"base"`.

`WHISPER_LANGUAGE` (default `"en"`) forces the language rather than relying on auto-detect — a deliberate fix after auto-detect misidentified short English clips as Japanese during testing.

`transcribe_pcm()` mixes to mono, resamples, discards clips under 0.2s as noise, calls `model.transcribe(mono16k, beam_size=1, language=language)`, joins segment texts. `handle_voice_command()` wraps this in try/except and separately short-circuits on an empty transcript.

Clap audio and voice-command audio never share a pipeline: claps are real-time RMS math on live blocks, never transcribed; PTT audio is fully buffered then sent to Whisper as one batch.

**Vs. other assistants:** cloud STT (Google/Azure/OpenAI) sends audio off-device and is metered; local `faster-whisper` keeps audio on-machine (privacy, zero marginal cost) at the cost of accuracy/speed relative to larger cloud or local models — `"base"` on CPU int8 is fast for short clips but weaker than `"medium"`/`"large-v3"` or cloud SOTA.

## Component 3: AI Reasoning, Intent Interpretation, and Memory

`_claude_request()` wraps Anthropic's Messages API (`CLAUDE_API_URL`, `CLAUDE_API_VERSION="2023-06-01"`), authenticating via `x-api-key` from `ANTHROPIC_API_KEY`. Retries up to `CLAUDE_MAX_ATTEMPTS` (3) with `CLAUDE_RETRY_DELAY_S` (1.5s) sleeps, only for transient codes (429, 500, 502, 503, 504, 529) or network exceptions.

`JARVIS_ACTIONS_SYSTEM_PROMPT` is an f-string built directly from the `ALLOWED_*` tuples, describing every action's semantics/required fields, forbidding shutdown/restart/sign-out/close/delete, and instructing an empty `actions` list + clarifying `reply` when unsure.

`JARVIS_TOOL_SCHEMA` defines one tool, `perform_actions` — `actions` (array, `maxItems: MAX_ACTIONS_PER_COMMAND`=5, each item's `action` drawn from `ALLOWED_STEP_ACTIONS`) plus `reply` (string). `interpret_command()` sets `tool_choice: {"type": "tool", "name": "perform_actions"}`, forcing structured output rather than relying on the model to "please output JSON."

Because `actions` is a list, Claude can return multiple ordered steps per utterance — `dispatch_actions()` iterates `actions[:MAX_ACTIONS_PER_COMMAND]` in order. `reply` is always included and becomes the base of the spoken response.

`conversation_history` is a `list[dict]` guarded by `_history_lock`, capped at `CONVERSATION_HISTORY_MAX_TURNS` (6 messages = 3 exchanges). `_append_history()` only stores a turn if both user text and a non-empty reply exist, trimming from the front once over the cap. `interpret_command()` prepends `_history_snapshot()` before each new message. This is **short-term, RAM-only, process-lifetime memory** — a restart wipes it; there is no long-term/persisted memory.

Unclear commands: handled at the prompt level (empty actions + clarifying reply). Unsupported/invalid actions: every branch in `dispatch_actions` checks both `kind` and required fields together; anything unmatched falls to a final `else` that just logs a warning.

**Exact allowed actions** (`ALLOWED_STEP_ACTIONS`, 15): `open_url`, `play_song`, `open_app`, `system_action`, `read_screen`, `web_search`, `type_text`, `system_status`, `read_clipboard`, `refactor_clipboard_code`, `click_at`, `drag_and_drop`, `scroll_screen`, `focus_window`, `switch_mode`.

**Why allowlisting beats arbitrary shell access:** even a manipulated or wrong LLM decision can only invoke one of a small number of individually-scoped functions, never "run any command." Every action is re-validated against the same allowlists at dispatch time, independent of the system prompt.

**Missing capabilities:** persistent memory (RAM-only); general plugin architecture (hardcoded `if/elif` chain); autonomous planning loop (single-shot per command, no re-observation); permission prompts before sensitive actions (none at runtime); user identity/authentication (none); task history/audit database (only ephemeral console logs).

## Component 4: Computer Control and Automation

App launching via `_launch_app(name)`: `_launch_app_notepad` (`notepad.exe`), `_launch_app_calculator` (`calc.exe`), `_launch_app_explorer` (`explorer.exe`), `_launch_app_chrome` (locates via `_chrome_executable()`, falls back to `webbrowser.open("about:blank")`), `_launch_app_spotify` (`os.startfile("spotify:")`, web fallback via `_open_uri`); `"cursor"` routes to `open_cursor_window()`. All launches pass `CREATE_NO_WINDOW` on Windows.

`_open_uri()` is the generic opener (`os.startfile` on Windows, `webbrowser.open` elsewhere).

Cursor gets bespoke handling: `_cursor_executable()` locates it; `open_cursor_window()` prefers focusing an existing window (`_focus_existing_cursor_window_win32` → `_cursor_largest_main_hwnd_win32`, a hand-rolled `ctypes.EnumWindows` scan filtered by owner/tool-window/visibility/process-name/size, picking the largest by area) via `_cursor_foreground_hwnd_win32` (`SetForegroundWindow` wrapped in `AttachThreadInput`), falling back to launching fresh. `focus_window()` (general-purpose) instead uses `pygetwindow`: substring title match, `.restore()` if minimized, `.activate()`.

`click_at`, `drag_and_drop`, `scroll_screen` all use `pyautogui` (`pyautogui.FAILSAFE = True` on every call — moving to a screen corner aborts). Purely coordinate-based, no understanding of what's at those pixels. `type_text()` uses `keyboard.write(t)`, deliberately never sending Enter.

Clipboard: `_read_clipboard()` (`pyperclip.paste()`), `read_clipboard_and_describe()` (read-only summary via Claude), `refactor_clipboard_code()` (uses the `---CODE---` marker convention; `dispatch_actions` both types the result via `type_text()` and writes it back via `pyperclip.copy()` as a safety net).

System actions: `_system_action_lock()` (`LockWorkStation()`), `_system_action_minimize_all()` (posts `WM_COMMAND`/`MIN_ALL` to `Shell_TrayWnd`), `_system_action_minimize_active()` (`ShowWindow(..., SW_MINIMIZE)`), volume/media via `_send_vk_key()` + `_MEDIA_VK` (virtual-key codes sent through `keybd_event`, simulating real hardware keys).

`system_status()` reads `psutil.cpu_percent`/`virtual_memory`/`disk_usage`/`sensors_battery`, phrased as one sentence.

Limits: `MAX_ACTIONS_PER_COMMAND` (5) truncates `actions`; steps run strictly in order. Invalid actions fall to a final `else` that only logs — nothing raises or halts the batch.

**Vs. other automation approaches:** mixes command-based (`_launch_app*`, `_open_uri` — most robust), coordinate-based (`pyautogui` clicks/drag/scroll — most fragile), and title/handle-based window control (`focus_window`, hand-rolled Cursor/Chrome code — a robust middle ground, still not true accessibility-tree awareness). Does **not** use Windows UI Automation/accessibility APIs, PowerShell/AppleScript, xdotool, browser automation (Playwright/Selenium), or any general RPA engine.

**Coordinate-based limitations present here:** no DPI/scaling awareness (screenshots downscale to `1600×1600`, mitigated only by restricting `click_at`/`drag_and_drop` to user-stated coordinates, never model-inferred ones); no multi-monitor validation; no re-validation against window movement since coordinates were decided; no post-click verification.

## Component 5: Screen Understanding, Feedback, and Multimodal Interaction

`_screenshot_jpeg_b64()`: `PIL.ImageGrab.grab()`, downsized via `img.thumbnail((1600, 1600))`, JPEG quality 70, base64-encoded — embedded directly in a Claude image content block.

`read_screen()` pairs that image with the user's transcript plus a fixed instruction asking for a brief answer, and — only if the screenshot shows a visible error **and** the user explicitly asked for a fix — a `---CODE---`-delimited correction. This decision happens inside `read_screen` itself (using both image and transcript), since the routing call (`interpret_command`) never sees the screen. Returns `(spoken_reply, code_to_type)`; `dispatch_actions` speaks the reply and, if code is present, calls `type_text(fix_code)` directly.

This is screenshot → vision-capable LLM — not OCR (no Tesseract, no text-extraction pass), not an accessibility API (no UIA tree), not DOM extraction (a website on screen is read through the same screenshot pathway as anything else), and not a full computer-use agent loop (no repeated observe→act→observe; never re-screenshots to verify a typed fix landed).

The `---CODE---` protocol is a hand-rolled text sentinel shared by `read_screen` and `refactor_clipboard_code`: split on the literal string, explanation before / code after — pragmatic but unenforced by schema (unlike `perform_actions`).

`read_clipboard_and_describe()`/`refactor_clipboard_code()` mirror this for text instead of pixels.

TTS splits into dynamic (`cartesia_speak`, never cached) and cached (`speak_cached_phrase`, for the two fixed clap greetings, keyed by SHA-256 of `text|voice_id|model_id|sample_rate` via `_jarvis_welcome_cache_path`, replaying `.cache/jarvis_welcome/*.wav` when unchanged). Both funnel through `_cartesia_tts()` (POST to Cartesia's `/tts/bytes`) and `_play_pcm_bytes`/`_play_pcm_wav_file`, both of which set/clear `jarvis_speaking` around playback.

**Privacy risks:** screenshots sent whole to Anthropic on every `read_screen` call, no redaction/preview/confirmation; clipboard contents sent unfiltered (`read_clipboard_and_describe`, `refactor_clipboard_code`); user code sent to a third-party cloud API for refactoring/fixing; API keys read from env vars via a local `.env` (`load_dotenv`) — plaintext on disk, nothing in the file itself prevents accidental sharing; no attempt anywhere to blur/crop/gate sensitive on-screen content before capture.

---

## A. Component Comparison Table

| Core component | What other JARVIS assistants commonly use | What `jarvis.py` implements | Main limitation | Security/privacy concern |
|---|---|---|---|---|
| Activation | Wake-word models, always-on transcription, simple hotkeys | Custom RMS clap-burst detector (1/3 claps) + PTT hotkey, gated by `jarvis_activated` | Acoustic events, not semantic; no speaker verification | Local-only — lowest-risk component |
| Speech recognition | Cloud STT, local Whisper variants | Local `faster-whisper` "base", CPU/int8, forced language | Weaker than cloud SOTA/larger local models; CPU-bound latency | Audio never leaves the machine |
| Reasoning/intent | Function calling, agent loops, planner/executor, plugins, long-term memory DBs | One forced Anthropic tool call per turn, 15-action allowlist, 6-message RAM history | No autonomous multi-step planning, no persistence, no plugins | Transcript + short history sent to Anthropic per turn |
| Computer control | PyAutoGUI, UI Automation, PowerShell/AppleScript, browser automation, RPA | Command launches + `pyautogui` coordinate clicks + `pygetwindow`/ctypes window focus | No accessibility-tree awareness; coordinate clicks unguarded against DPI/monitor/staleness | No confirmation before clicking, typing, or locking |
| Screen/multimodal | Vision LLMs, OCR, accessibility APIs, DOM extraction, computer-use loops | Screenshot → Claude vision, single-shot | Can't verify a typed fix landed; JPEG downscale limits precision | Screenshots/clipboard sent to Anthropic unfiltered |

## B. Example Execution Flows

### 1. "Open Chrome."
1. Activation already done (clap fired earlier; `jarvis_activated = True`).
2. Capture: PTT held, blocks accumulate in `ptt_buffer`.
3. Transcription: `transcribe_pcm()` → `"open chrome"`.
4. Claude receives: `JARVIS_ACTIONS_SYSTEM_PROMPT` + history + `"open chrome"`, forced `perform_actions`.
5. Representative tool call (not observed, illustrative):
   ```json
   {"actions": [{"action": "open_app", "app": "chrome"}], "reply": "Opening Chrome."}
   ```
6. Executed by: `dispatch_actions` → `_launch_app("chrome")` → `_launch_app_chrome()`.
7. Spoken via: `cartesia_speak("Opening Chrome.")`.
8. What could go wrong: Chrome not found → silently opens `about:blank` instead; Cartesia failure means the confirmation is never spoken even though Chrome did open.

### 2. "Read what is on my screen."
5. Representative tool call:
   ```json
   {"actions": [{"action": "read_screen"}], "reply": "Let me take a look."}
   ```
6. Executed by: `dispatch_actions` → `read_screen(transcript)` → internal `_screenshot_jpeg_b64()` + a second, separate Claude call carrying the image.
7. Spoken via: routing `reply` + `read_screen`'s returned description, combined into one `cartesia_speak` call.
8. What could go wrong: JPEG downscale blurs small text; the second Claude call (`timeout=60`) is noticeably slower; sensitive on-screen content gets sent with no filtering.

### 3. "Open Notepad and type this text."
5. Representative tool call (two ordered steps):
   ```json
   {"actions": [
     {"action": "open_app", "app": "notepad"},
     {"action": "type_text", "text": "this text"}
   ], "reply": "Opening Notepad and typing that."}
   ```
6. Executed by: `dispatch_actions` iterating the list — `_launch_app("notepad")` then `type_text("this text")`.
8. What could go wrong: no wait/focus-check between steps — `type_text` could fire before Notepad actually has focus, landing keystrokes elsewhere. (This exact compound-command timing gap was observed as a real limitation during live testing of this file.)

### 4. "Check my CPU and RAM."
5. Representative tool call:
   ```json
   {"actions": [{"action": "system_status"}], "reply": "Checking system stats now."}
   ```
6. Executed by: `dispatch_actions` → `system_status()` (pure `psutil`, no network).
7. Spoken via: returned sentence + routing reply, combined.
8. What could go wrong: `disk_usage` reads the script's own drive, which may not be the drive the user meant on a multi-drive machine; missing `psutil` produces a spoken apology instead of a crash.

## C. Strengths, Weaknesses, and Recommendations

**Strongest engineering decisions:**
- Action allowlisting, validated both in the prompt/schema and again independently at dispatch time.
- Forced structured tool calling (`tool_choice`) instead of free-text JSON prompting.
- `MAX_ACTIONS_PER_COMMAND` cap and shutdown/restart/close/delete structurally absent from the vocabulary (not just discouraged).
- `type_text` never sends Enter — a narrow, deliberate safety property independent of what text is typed.
- `jarvis_speaking` feedback-loop suppression — a real, previously-observed bug fixed architecturally, not by threshold tuning.
- Retry logic with transient-vs-permanent HTTP error distinction; cached TTS for fixed phrases.
- Clean separation between interpretation (`interpret_command`, never touches the OS) and execution (`dispatch_actions`, never talks to Claude directly except via clearly scoped sub-calls).

**Key weaknesses and risks:**
- Screenshots, clipboard content, and user code all transmit to a cloud API with no filtering, preview, or confirmation.
- No runtime confirmation before `type_text`, `click_at`, `drag_and_drop`, or `system_action("lock")`.
- Plausible prompt-injection vector: screen/clipboard content is not treated as untrusted relative to the user's own transcript, and can drive further actions (e.g. a `---CODE---` block that gets typed) within the same dispatch pass.
- Coordinate-based actions lack DPI/multi-monitor/staleness/result-verification safeguards.
- Hard Windows-only assumptions throughout.
- No authentication, no persisted audit log.

**Recommended modular split:** `audio/`, `ai/`, `automation/`, `vision/`, `memory/`, `safety/`, `output/`.

**Highest-priority improvements:**
1. Confirmation step for irreversible/high-blast-radius actions (`lock`, `click_at`/`drag_and_drop`, long `type_text`).
2. Treat screen/clipboard content as untrusted input, not equivalent to the user's own transcript.
3. Persistent, append-only audit log of executed actions.
4. Result verification for screen-based fixes (re-screenshot after typing a correction).
5. Secret-scanning before clipboard/screen content is sent to Claude.

## D. Final Classification

A **mixture**: a basic voice assistant at its core (Components 1–3), extended into a genuine **desktop automation assistant** (Component 4), with one narrow, single-shot **multimodal capability** (Component 5) that stops short of a full autonomous computer-use agent — no observe-act-observe loop, no self-verification, coordinate actions explicitly restricted to user-stated positions rather than model-driven autonomous targeting.

**Overall: a desktop automation assistant with voice I/O and a narrow, single-shot multimodal (vision) capability** — by design, not a computer-use agent.
