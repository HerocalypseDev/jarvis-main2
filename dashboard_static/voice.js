// Voice tab (2026-09-23): how much text Jarvis speaks (text-to-speech) and how much of your speech it
// transcribes (speech-to-text), per engine, from GET /api/voice_usage (counts only, never the text).
// Plain JS like the other routes; esc() and currentRoute() come from app.js.

const VOICE_ENGINE_NAMES = {
  deepgram: "Deepgram Aura (REST)", deepgram_stream: "Deepgram Aura (live stream)", fish: "Fish Audio",
  piper: "Piper (local)", whisper: "Whisper (local)",
};

function vNum(n) { return Number(n || 0).toLocaleString(); }
function vDur(sec) {
  sec = Math.round(sec || 0);
  if (sec < 60) return `${sec}s`;
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m ${sec % 60}s`;
}
function vCompact(n) {
  n = Number(n || 0);
  return n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e4 ? Math.round(n / 1e3) + "k" : n >= 1e3 ? (n / 1e3).toFixed(1) + "k" : String(n);
}

function voiceCard(label, value, sub, cls = "") {
  return `<div class="usage-card ${cls}"><div class="usage-card-label">${esc(label)}</div>
    <div class="usage-card-value">${esc(value)}</div><div class="muted">${esc(sub)}</div></div>`;
}

function renderVoiceCards(v) {
  const p = v.periods;
  const cards = [];
  for (const [label, key] of [["Today", "today"], ["7 days", "week"], ["This month", "month"], ["All time", "all_time"]]) {
    const t = p[key].tts;
    cards.push(voiceCard(`Jarvis spoke · ${label}`, vNum(t.chars) + " chars", `${vNum(t.words)} words · ${vDur(t.audio_s)} of audio`, "voice-card-tts"));
  }
  for (const [label, key] of [["Today", "today"], ["7 days", "week"], ["This month", "month"], ["All time", "all_time"]]) {
    const s = p[key].stt;
    cards.push(voiceCard(`You said · ${label}`, vNum(s.chars) + " chars", `${vNum(s.words)} words · ${vDur(s.audio_s)} listened`, "voice-card-stt"));
  }
  document.getElementById("voice-cards").innerHTML = cards.join("");

  const m = p.month;
  const sentCard = (label, d) => {
    const cachedPct = d.tts.chars ? Math.round(100 * (d.tts.chars - d.tts.billed_chars) / d.tts.chars) : 0;
    return voiceCard(`Characters sent to TTS engines (${label})`, vNum(d.tts.billed_chars),
      `${cachedPct}% served free from the voice cache`, "usage-card-good");
  };
  document.getElementById("voice-highlights").innerHTML = [
    sentCard("today", p.today),
    sentCard("month", m),
    sentCard("all time", p.all_time),
    voiceCard("Sentences spoken (month)", vNum(m.tts.events), `${vNum(m.tts.cached_events)} straight from cache`),
  ].join("");
}

// One chart per direction, each on its own scale: Jarvis's replies are many times longer than your
// commands, so a shared scale flattened the "you said" bars to nothing.
function renderVoiceDaily(v) {
  for (const kind of ["tts", "stt"]) {
    const key = kind === "tts" ? "tts_billed_chars" : "stt_chars";  // TTS: characters actually sent to an engine
    const max = Math.max(1, ...v.daily.map((d) => d[key]));
    document.getElementById(`voice-daily-${kind}-max`).textContent = `peak ${vNum(max)} chars/day`;
    document.getElementById(`voice-daily-${kind}`).innerHTML = v.daily.map((d) => {
      const h = d[key] ? Math.max(3, Math.round((d[key] / max) * 100)) : 0;
      const tip = kind === "tts" ? `${vNum(d.tts_billed_chars)} chars sent to TTS engines (${vNum(d.tts_chars)} spoken incl. cache)`
        : `${vNum(d.stt_chars)} chars, ${vDur(d.stt_audio_s)} of audio`;
      return `<div class="voice-day" title="${esc(d.date)}: ${tip}">
        <div class="voice-day-bars"><div class="voice-bar voice-bar-${kind}" style="height:${h}%"></div></div>
        <div class="usage-bar-label">${esc(d.date.slice(8))}</div></div>`;
    }).join("");
  }
}

function renderVoiceEngines(v) {
  for (const kind of ["tts", "stt"]) {
    const rows = v.engines[kind];
    const total = rows.reduce((a, r) => a + r.chars, 0) || 1;
    document.getElementById(`voice-engines-${kind}`).innerHTML = rows.length ? rows.map((r) => {
      const pct = Math.round((100 * r.chars) / total);
      return `<div class="voice-engine">
        <div class="voice-engine-head"><span>${esc(VOICE_ENGINE_NAMES[r.engine] || r.engine)}</span><span class="muted">${vNum(r.chars)} chars · ${pct}%</span></div>
        <div class="voice-meter"><div class="voice-meter-fill voice-bar-${kind}" style="width:${pct}%"></div></div>
        <div class="muted voice-engine-sub">${vNum(r.events)} ${kind === "tts" ? "sentences" : "commands"} · ${vDur(r.audio_s)}${kind === "tts" && r.cached ? ` · ${vNum(r.cached)} from cache` : ""}</div>
      </div>`;
    }).join("") : `<p class="empty-state">Nothing in the last ${v.days} days.</p>`;
  }
}

function renderVoiceRhythm(v) {
  const maxH = Math.max(1, ...v.hours.map((h) => h.tts + h.stt));
  document.getElementById("voice-hours").innerHTML = v.hours.map((h, i) => {
    const n = h.tts + h.stt;
    const a = n ? 0.15 + 0.85 * (n / maxH) : 0.04;
    return `<div class="voice-hour" style="--a:${a.toFixed(2)}" title="${String(i).padStart(2, "0")}:00 · ${n} voice events">
      <span>${i % 3 === 0 ? String(i).padStart(2, "0") : ""}</span></div>`;
  }).join("");
  const names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const maxW = Math.max(1, ...v.weekdays.map((w) => w.tts + w.stt));
  document.getElementById("voice-weekdays").innerHTML = v.weekdays.map((w, i) => {
    const pct = Math.round((100 * (w.tts + w.stt)) / maxW);
    return `<div class="voice-weekday"><span class="voice-weekday-name">${names[i]}</span>
      <div class="voice-meter"><div class="voice-meter-fill voice-bar-mix" style="width:${pct}%"></div></div>
      <span class="muted">${w.tts + w.stt}</span></div>`;
  }).join("");
}

function renderVoiceRecords(v) {
  const r = v.records, m = v.periods.month;
  const wpm = m.stt.audio_s ? Math.round(m.stt.words / (m.stt.audio_s / 60)) : null;
  const cps = m.tts.audio_s ? (m.tts.chars / m.tts.audio_s).toFixed(1) : null;
  const items = [
    ["Longest sentence Jarvis spoke", r.tts.max_chars ? `${vNum(r.tts.max_chars)} chars (${vDur(r.tts.max_audio_s)})` : "–"],
    ["Average spoken sentence", r.tts.avg_chars ? `${r.tts.avg_chars} chars` : "–"],
    ["Longest thing you said", r.stt.max_audio_s ? `${vDur(r.stt.max_audio_s)} (${vNum(r.stt.max_chars)} chars)` : "–"],
    ["Average voice command", r.stt.avg_chars ? `${r.stt.avg_chars} chars, ${vDur(r.stt.avg_audio_s)}` : "–"],
    ["Your speaking pace", wpm ? `${wpm} words/min` : "–"],
    ["Jarvis's speaking pace", cps ? `${cps} chars/sec` : "–"],
    ["Busiest day", v.busiest_day ? `${v.busiest_day.date} · ${vCompact(v.busiest_day.tts_chars + v.busiest_day.stt_chars)} chars` : "–"],
  ];
  document.getElementById("voice-records").innerHTML = items.map(([k, val]) =>
    `<li class="list-item compact voice-record"><span>${esc(k)}</span><span class="voice-record-val">${esc(val)}</span></li>`).join("");
}

function splitBar(label, a, b, aLabel, bLabel, fmt) {
  const total = a + b;
  const pa = total ? Math.round((100 * a) / total) : 50;
  return `<div class="voice-split">
    <div class="voice-engine-head"><span>${esc(label)}</span><span class="muted">${total ? "" : "no data yet"}</span></div>
    <div class="voice-split-bar"><div class="voice-bar-tts" style="width:${pa}%"></div><div class="voice-bar-stt" style="width:${100 - pa}%"></div></div>
    <div class="voice-engine-head muted voice-engine-sub"><span>${esc(aLabel)} ${esc(fmt(a))} (${pa}%)</span><span>${esc(bLabel)} ${esc(fmt(b))} (${100 - pa}%)</span></div>
  </div>`;
}

function renderVoiceSplit(v) {
  const m = v.periods.month;
  document.getElementById("voice-split").innerHTML = [
    splitBar("Talk time", m.tts.audio_s, m.stt.audio_s, "Jarvis", "you", vDur),
    splitBar("Words", m.tts.words, m.stt.words, "Jarvis", "you", vNum),
    splitBar("Spoken characters", m.tts.billed_chars, m.tts.chars - m.tts.billed_chars, "synthesized", "from cache", vNum),
  ].join("");
}

async function renderVoiceLatency() {
  const el = document.getElementById("voice-latency");
  try {
    const rows = ((await (await fetch("/api/latency", { cache: "no-store" })).json()).recent || []).filter((r) => r.e2e_ms != null);
    if (!rows.length) { el.innerHTML = `<p class="empty-state">No voice commands since Jarvis started.</p>`; return; }
    const buckets = [["< 1s", 0, 1000], ["1–2s", 1000, 2000], ["2–3s", 2000, 3000], ["3–5s", 3000, 5000], ["5s +", 5000, Infinity]];
    const counts = buckets.map(([, lo, hi]) => rows.filter((r) => r.e2e_ms >= lo && r.e2e_ms < hi).length);
    const max = Math.max(1, ...counts);
    el.innerHTML = buckets.map(([label], i) => `<div class="voice-weekday"><span class="voice-weekday-name">${label}</span>
      <div class="voice-meter"><div class="voice-meter-fill voice-bar-tts" style="width:${Math.round((100 * counts[i]) / max)}%"></div></div>
      <span class="muted">${counts[i]}</span></div>`).join("") +
      `<p class="muted voice-note">End-to-end time for the last ${rows.length} voice commands (since Jarvis started).</p>`;
  } catch (e) { el.innerHTML = `<p class="muted">Couldn't load timings.</p>`; }
}

async function refreshVoice() {
  if (!document.getElementById("voice-cards")) return;
  let v;
  try {
    const res = await fetch("/api/voice_usage", { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    v = await res.json();
  } catch (e) {
    document.getElementById("voice-cards").innerHTML = `<p class="muted">Couldn't load voice stats: ${esc(String(e))}</p>`;
    return;
  }
  renderVoiceCards(v);
  renderVoiceDaily(v);
  renderVoiceEngines(v);
  renderVoiceRhythm(v);
  renderVoiceRecords(v);
  renderVoiceSplit(v);
  renderVoiceLatency();
}

window.refreshVoice = refreshVoice;
if (typeof currentRoute === "function" && currentRoute() === "voice") refreshVoice();
setInterval(() => { if (typeof currentRoute === "function" && currentRoute() === "voice" && !document.hidden) refreshVoice(); }, 30000);
