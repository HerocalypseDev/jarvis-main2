sfx = [  # (id, start, file, vol)
 ("s1", 0.10, "impact/impactPunch_heavy_000.ogg", 0.8), ("g1", 1.90, "interface/glitch_002.ogg", 0.6),
 ("p2", 2.46, "impact/impactPunch_heavy_002.ogg", 0.8), ("g2", 4.10, "interface/glitch_004.ogg", 0.6),
 ("p3", 4.64, "impact/impactMetal_heavy_000.ogg", 0.7), ("c4", 6.28, "casino/card-slide-2.ogg", 0.6),
 ("p4", 6.82, "impact/impactPunch_heavy_000.ogg", 0.7), ("p4b", 7.35, "impact/impactPunch_heavy_002.ogg", 0.7),
 ("g3", 8.22, "interface/glitch_002.ogg", 0.6), ("m5", 8.73, "ui/mouseclick1.ogg", 0.7),
 ("p5", 9.83, "impact/impactMetal_heavy_000.ogg", 0.7),
 ("g4", 10.93, "interface/glitch_004.ogg", 0.6), ("p6", 11.47, "impact/impactPunch_heavy_000.ogg", 0.7),
 ("c7", 13.11, "casino/card-slide-2.ogg", 0.6), ("p7", 13.64, "impact/impactPunch_heavy_002.ogg", 0.7),
 ("k1", 15.28, "ui/mouseclick1.ogg", 0.7), ("k2", 15.82, "ui/mouseclick1.ogg", 0.7),
 ("k3", 16.38, "ui/mouseclick1.ogg", 0.7), ("k4", 16.93, "ui/mouseclick1.ogg", 0.7),
 ("p8", 17.47, "impact/impactPunch_heavy_002.ogg", 0.85),
 ("g5", 18.55, "interface/glitch_002.ogg", 0.6), ("p9", 19.10, "impact/impactPunch_heavy_000.ogg", 0.7),
 ("bell", 20.74, "impact/impactBell_heavy_004.ogg", 0.85), ("p10", 21.83, "impact/impactPunch_heavy_000.ogg", 0.8),
]
audio = '  <audio id="bg-music" data-start="0" data-duration="24" data-track-index="10" data-volume="0.4" src="assets/music/happy-beats-business-moves-vol-10-by-ende-dot-app.mp3"></audio>\n'
for i, (n, t, f, v) in enumerate(sfx):
    audio += f'  <audio id="sfx-{n}" data-start="{t}" data-duration="0.5" data-track-index="{11+i}" data-volume="{v}" src="assets/sfx/{f}"></audio>\n'

tpl = open("../src/template.html", encoding="utf-8").read()
open("../composition/index.html", "w", encoding="utf-8").write(tpl.replace("__AUDIO__", audio))
