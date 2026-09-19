# Brag Plan: Jarvis

## What is this app?
A desktop voice assistant you drive with push-to-talk that runs a real Claude tool-use loop against your own machine — and a supervision dashboard that shows every command, task, and approval, and asks before anything catastrophic runs.

## The angle
Everyone builds an assistant that *does things*. This one is built around the moment before it does something you can't undo. The hook is the confirmation gate: you tell your computer to shut down, and Jarvis stops and asks. Then the video pulls back to show it's a whole supervised system: sessions, tasks, audit trail, four ways in, all local.

## Hook (first 3.3 seconds)
Black. A single cyan cursor. "Hold a key. Say it." then the transcript types itself: `shut down my computer`.

## Key moments (the middle)
- The gate: Jarvis's reply "I'm about to shut down. Say yes." while the dashboard's approval bar (dashed "No pending confirmations") flips to a pending action with a Review button. Nothing has run.
- The dashboard: Sessions / Tasks / Detail columns, the metrics strip with CPU per-core heatmap, sessions landing one by one.
- Four inputs: Voice, Text hotkey, Phone, Dashboard cards arrive one by one — all through the same gate.

## Outro / punchline
"JARVIS Supervision." Then the small line: "Localhost only. Your machine. Your call."

## User flow worth showing
1. Entry: hold push-to-talk, speak "shut down my computer"
2. Key action: Jarvis stages it, asks for a yes; approval bar shows pending action, Review opens the detail view
3. Result: the audit trail row appears; nothing was executed until approved

## Tone
- Preset: cinematic
- Creative direction: quiet-power control room — Iron Man restraint, not Iron Man volume
- Interpretation: slow declarative lines, big type, one dramatic reveal (the gate), and the humor is that the scariest command gets the calmest response.

## Format: landscape — 1920x1080
## Duration: ~21 seconds

## Visual identity (from the project)
- Background: #050b14 (panels #0a1420 / #0d1826, borders #123047)
- Accent: #2fd8ff (cyan, glow rgba(47,216,255,0.35)); danger #ff5470, warn #ffb020, ok #35e39c
- Text: #d7ecf5 (muted #6f92a6)
- Display font: Segoe UI (system stack; fallback to a bundled sans if unavailable in the renderer)
- Body font: Segoe UI; mono: Cascadia Code / Consolas for transcripts and data
- Strongest visual element: the dashboard's top approval bar and three-column layout with cyan glow on near-black.

## Share copy (draft)
I built a voice assistant that runs on my own machine, and the first thing it learned was to ask "are you sure?" before it shuts anything down.

## Audio direction
- Role: cinematic support
- Music: happy-beats-business-moves-vol-12 (steady and clean), ~110 BPM
- Music treatment: fade in from 0.0s at ~0.30 volume, sit under; a short dip before the gate reveal; fade out over the last 2s under the outro
- Music cue guidance: preset read (vol-12, 109.96 BPM). Strong cues to target: 8.74s (gate → dashboard reveal), 13.11s (four inputs), 17.47s (outro title). Beat-grid for sequential reveals: 9.83, 10.93, 12.02 (sessions, hold text between); 13.64, 14.73, 15.84, 16.93 (input cards — every other beat, since these are readable labels).
- Audio-reactive treatment: subtle; music bass makes the cyan glow on the approval bar and title breathe. No waveform/equalizer visuals.
- SFX posture: sparse; motion-matched
- Audio-coupled moments: transcript types with soft keypresses; gate reveal gets one deep impact; input cards get soft card/drop sounds; outro title gets a bell.
- Restraint rule: no stinger over the spoken-line reading beats; nothing louder than the music at the hook.

## Storyboard

### Scene 1 — Hook — 3.3s
Black. Cyan text "Hold a key. Say it." fades in (hold ≥1.2s). Below, in mono, `shut down my computer` types out character by character in a transcript pill.
Sequential/interaction: yes — typing; simulated push-to-talk key press before it.
Audio intent: quiet tension
Audio-coupled idea: subtle keypress on each character
Music: fade-in
Transition mood: hard cut → Scene 2

### Scene 2 — The gate — 5.4s
Dashboard top bar recreated: JARVIS Supervision brand, approval queue reading "No pending confirmations" then flipping (danger red outline) to a pending row `run_shell: shutdown /s /t 0` with a Review button. Jarvis reply line: "I'm about to shut down. Say yes." Held ≥1.5s. A cursor clicks Review; detail card opens.
Sequential/interaction: yes — cursor click on Review
Audio intent: the dramatic beat; low swell then a hit as the pending row lands
Audio-coupled idea: click on Review, deep impact on the reveal
Music: dip slightly then return
Transition mood: dramatic wipe → Scene 3 (lands on the 8.74s strong cue)

### Scene 3 — The dashboard — 4.4s
Pull back to the full layout: metrics strip (CPU/RAM/disk/uptime, per-core heatmap), Sessions / Tasks / Detail columns. Three session rows land one by one ("shut down my computer", etc.), a task shows "running". Headline: "Every command. On the record."
Sequential/interaction: yes — session rows arrive one by one, hold text ~1.2s
Audio intent: confident, controlled
Audio-coupled idea: card sounds on the first and last rows
Music: full
Transition mood: clean slide → Scene 4 (lands on 13.11s strong cue)

### Scene 4 — Four ways in — 4.4s
Four chips arrive one by one: Voice · Text hotkey · Phone · Dashboard. Line beneath: "Same gate for all of them." Hold the full set ≥1.0s.
Sequential/interaction: yes — 4 cards, every other beat, readable labels
Audio intent: momentum
Audio-coupled idea: card-place sounds on first and last
Music: full
Transition mood: soft crossfade → Scene 5

### Scene 5 — Outro — 3.8s
"JARVIS" large with "Supervision" small in cyan glow. Below: "Localhost only. Your machine. Your call." Hold on empty space, music fades.
Sequential/interaction: none
Audio intent: resolve
Audio-coupled idea: bell on title (locked to 17.47s)
Music: swell then fade out
Transition mood: end

**Music mood for this video:** cinematic, restrained
**Audio summary:** quiet typing, one heavy reveal at the gate, light card sounds through the middle, one bell on the title.
