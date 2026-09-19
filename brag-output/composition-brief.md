# Hyperframes Composition Brief: Jarvis

## Objective
Short cinematic launch-style brag video for Jarvis (voice assistant + supervision dashboard).

## Output
- Composition: `brag-output/composition/` (single `index.html`, local GSAP + audio in `assets/`)
- Rendered video: `brag-output/brag.mp4`
- Format: landscape, 1920x1080, ~21.3s

## Source Material
- Project root: jarvis-main2
- Primary files read: dashboard_static/index.html, dashboard_static/style.css, README.md, CLAUDE.md
- Copy verbatim: "Hold a key. Say it." / "shut down my computer" / "No pending confirmations" / "Every command. On the record." / "Localhost only. Your machine. Your call."
- Key UI recreated: top approval bar with pending confirmation + Review; metrics strip with per-core CPU heatmap; Sessions/Tasks/Detail columns.

## Creative Direction
- Preset: cinematic — quiet-power control room
- Hook: push-to-talk typed transcript "shut down my computer"; Outro: JARVIS / SUPERVISION.

## Visual Identity
bg #050b14, panels #0a1420/#0d1826, accent #2fd8ff, text #d7ecf5, danger #ff5470; Segoe UI + Cascadia Code (via local() @font-face).

## Audio
- Role: cinematic support. Music: happy-beats-business-moves-vol-12 @0.30, preset cues (strong: 8.74, 13.11, 17.47).
- SFX: keypress typing, bell on gate + title, click on Review, soft card sounds.
- Audio-reactive: not implemented (Hyperframes creative helper unavailable in this environment); documented, not blocking.
