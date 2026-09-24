// QOL pass (2026-09-23): Settings route + Alt+K command palette. Plain JS, no framework, same
// conventions as app.js (esc() from app.js for escaping).

// --- Settings -------------------------------------------------------------------------------
async function refreshSettings() {
  const known = document.getElementById("settings-known");
  const other = document.getElementById("settings-other");
  if (!known) return;
  let data;
  try {
    data = await (await fetch("/api/settings", { cache: "no-store" })).json();
  } catch (e) {
    known.innerHTML = `<p class="muted">Couldn't load settings: ${esc(String(e))}</p>`;
    return;
  }
  known.innerHTML = data.known.map((s) => `
    <div class="setting-row" data-key="${esc(s.key)}">
      <div class="setting-text">
        <div class="setting-label">${esc(s.label)}</div>
        <div class="setting-help">${esc(s.help || "")} <span class="setting-applies">${s.applies === "now" ? "Applies immediately." : "Applies after a restart."}</span></div>
      </div>
      <div class="setting-control">${settingControl(s)}</div>
      <div class="setting-status" aria-live="polite"></div>
    </div>`).join("");
  other.innerHTML = data.other.length ? data.other.map((s) => `
    <div class="setting-row" data-key="${esc(s.key)}">
      <div class="setting-text"><div class="setting-label mono">${esc(s.key)}</div>
        <div class="setting-help">${s.secret ? (s.set ? "Secret, set (hidden). Type a new value to replace it." : "Secret, not set.") : ""}</div></div>
      <div class="setting-control"><input type="${s.secret ? "password" : "text"}" class="setting-input" data-kind="text"
        value="${s.secret ? "" : esc(s.value || "")}" placeholder="${s.secret ? "new value" : ""}" autocomplete="off"></div>
      <div class="setting-status" aria-live="polite"></div>
    </div>`).join("") : `<p class="muted">No other settings in .env.</p>`;
  filterSettings();
}

// Hides setting rows (both lists) whose name/label/help doesn't contain every typed word.
function filterSettings() {
  const words = (document.getElementById("settings-search")?.value || "").toLowerCase().split(/\s+/).filter(Boolean);
  document.querySelectorAll("#view-settings .setting-row").forEach((row) => {
    const text = (row.dataset.key + " " + row.querySelector(".setting-text").textContent).toLowerCase();
    row.hidden = !words.every((w) => text.includes(w));
  });
}
document.getElementById("settings-search")?.addEventListener("input", filterSettings);

function settingControl(s) {
  if (s.kind === "bool") {
    const on = ["1", "true", "yes", "on"].includes(String(s.value).toLowerCase());
    return `<label class="switch"><input type="checkbox" class="setting-input" data-kind="bool" ${on ? "checked" : ""}><span></span></label>`;
  }
  if (s.kind === "choice") {
    return `<select class="setting-input" data-kind="choice">${s.choices.map((c) =>
      `<option value="${esc(c)}" ${c === s.value ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>`;
  }
  return `<input class="setting-input" data-kind="${s.kind}" type="${s.kind === "number" ? "number" : "text"}"
    step="any" value="${esc(s.value ?? "")}" autocomplete="off">`;
}

async function saveSetting(row, key, value) {
  const status = row.querySelector(".setting-status");
  status.textContent = "Saving…";
  status.className = "setting-status";
  try {
    const res = await fetch("/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, value }),
    });
    const data = await res.json();
    if (data.ok) {
      status.textContent = data.applies === "now" ? "Saved" : "Saved, restart to apply";
      status.classList.add("ok");
    } else {
      status.textContent = data.error || "Failed";
      status.classList.add("err");
    }
  } catch (e) {
    status.textContent = "Failed: " + e;
    status.classList.add("err");
  }
}

document.addEventListener("change", (e) => {
  const input = e.target.closest(".setting-input");
  if (!input) return;
  const row = input.closest(".setting-row");
  const value = input.dataset.kind === "bool" ? (input.checked ? "1" : "0") : input.value;
  if (input.type === "password" && !value) return;  // leaving a secret blank never clears it
  saveSetting(row, row.dataset.key, value);
});

document.getElementById("settings-add-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const key = document.getElementById("settings-add-key").value.trim().toUpperCase();
  const value = document.getElementById("settings-add-value").value;
  const status = document.getElementById("settings-add-status");
  const res = await fetch("/api/settings", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key, value }),
  });
  const data = await res.json();
  status.textContent = data.ok ? `Saved ${key}${data.applies === "now" ? "" : " (restart to apply)"}.` : (data.error || "Failed");
  if (data.ok) { e.target.reset(); refreshSettings(); }
});

window.refreshSettings = refreshSettings;
// app.js activates the initial route before this file loads, so cover a direct #/settings load.
if (typeof currentRoute === "function" && currentRoute() === "settings") refreshSettings();

// --- Command palette (Alt+K) ---------------------------------------------------------------
const PIN_KEY = "jarvis.palette.pins";
function loadPins() {
  try { return JSON.parse(localStorage.getItem(PIN_KEY) || "[]"); } catch { return []; }
}
function savePins(pins) {
  try { localStorage.setItem(PIN_KEY, JSON.stringify(pins)); } catch { /* storage blocked: pins just don't persist */ }
}

const palette = { el: null, input: null, list: null, items: [], recent: [], sel: 0 };

function buildPalette() {
  const el = document.createElement("div");
  el.className = "palette-backdrop hidden";
  el.innerHTML = `
    <div class="palette" role="dialog" aria-label="Command palette">
      <input class="palette-input" type="text" placeholder="Run a command, or search past ones…" autocomplete="off">
      <ul class="palette-list" role="listbox"></ul>
      <div class="palette-foot muted">Enter runs · ↑↓ move · ☆ pin · Esc closes</div>
    </div>`;
  document.body.appendChild(el);
  palette.el = el;
  palette.input = el.querySelector(".palette-input");
  palette.list = el.querySelector(".palette-list");
  el.addEventListener("mousedown", (e) => { if (e.target === el) closePalette(); });
  palette.input.addEventListener("input", renderPalette);
  palette.input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { palette.sel = Math.min(palette.sel + 1, palette.items.length - 1); renderPalette(false); e.preventDefault(); }
    else if (e.key === "ArrowUp") { palette.sel = Math.max(palette.sel - 1, 0); renderPalette(false); e.preventDefault(); }
    else if (e.key === "Enter") { e.preventDefault(); runPalette(palette.items[palette.sel]?.text ?? palette.input.value); }
  });
  palette.list.addEventListener("click", (e) => {
    const li = e.target.closest("li");
    if (!li) return;
    const text = palette.items[+li.dataset.i]?.text;
    if (e.target.closest(".pin")) {
      const pins = loadPins();
      savePins(pins.includes(text) ? pins.filter((p) => p !== text) : [text, ...pins].slice(0, 30));
      renderPalette(false);
    } else runPalette(text);
  });
}

// "wthr tmrw" finds "what's the weather tomorrow": letters in order, bonus for a plain substring
// and for letters close together. 0 = no match.
function fuzzyScore(text, q) {
  if (text.includes(q)) return 1000 - text.indexOf(q);
  let ti = 0, gaps = 0, last = -1;
  for (const ch of q.replace(/\s+/g, "")) {
    const at = text.indexOf(ch, ti);
    if (at < 0) return 0;
    if (last >= 0) gaps += at - last - 1;
    last = at; ti = at + 1;
  }
  return Math.max(1, 500 - gaps);
}

function renderPalette(resetSel = true) {
  const q = palette.input.value.trim().toLowerCase();
  const pins = loadPins();
  const seen = new Set();
  const all = [...pins.map((t) => ({ text: t, pinned: true })), ...palette.recent.map((r) => ({ text: r.text, pinned: false }))]
    .filter((c) => !seen.has(c.text) && seen.add(c.text));
  palette.items = (q ? all.map((c) => ({ c, s: fuzzyScore(c.text.toLowerCase(), q) })).filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s).map((x) => x.c) : all).slice(0, 40);
  if (q && !palette.items.some((c) => c.text.toLowerCase() === q)) palette.items.unshift({ text: palette.input.value.trim(), fresh: true });
  if (resetSel) palette.sel = 0;
  palette.list.innerHTML = palette.items.map((c, i) => `
    <li data-i="${i}" class="${i === palette.sel ? "sel" : ""}" role="option" aria-selected="${i === palette.sel}">
      <span class="palette-text">${c.fresh ? "Run: " : ""}${esc(c.text)}</span>
      ${c.fresh ? "" : `<button class="pin" title="${c.pinned ? "Unpin" : "Pin"}">${c.pinned ? "★" : "☆"}</button>`}
    </li>`).join("") || `<li class="muted">No past commands yet.</li>`;
  palette.list.querySelector(".sel")?.scrollIntoView({ block: "nearest" });
}

async function openPalette() {
  if (!palette.el) buildPalette();
  palette.el.classList.remove("hidden");
  palette.input.value = "";
  palette.input.focus();
  try {
    palette.recent = (await (await fetch("/api/commands/recent?limit=100")).json()).commands || [];
  } catch { palette.recent = []; }
  renderPalette();
}

function closePalette() { palette.el?.classList.add("hidden"); }

async function runPalette(text) {
  text = (text || "").trim();
  if (!text) return;
  closePalette();
  try {
    const res = await fetch("/api/command", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
    if (!res.ok) alert(`Couldn't send the command (HTTP ${res.status}).`);
  } catch (e) { alert("Couldn't send the command: " + e); }
}

document.addEventListener("keydown", (e) => {
  // Esc closes it wherever focus is (e.g. after clicking a pin button, focus leaves the input).
  if (e.key === "Escape" && palette.el && !palette.el.classList.contains("hidden")) { closePalette(); return; }
  if (e.altKey && !e.ctrlKey && !e.metaKey && e.key.toLowerCase() === "k") {
    e.preventDefault();
    palette.el && !palette.el.classList.contains("hidden") ? closePalette() : openPalette();
  }
});
document.getElementById("palette-btn")?.addEventListener("click", openPalette);

// --- Home briefing card (briefing v2): GET /api/briefing, composed server-side from real data ---
let briefingKind = "urgent";
let briefingBusy = false;
async function refreshBriefing() {
  const el = document.getElementById("home-briefing");
  if (!el || briefingBusy) return;
  briefingBusy = true;
  try {
    const res = await fetch(`/api/briefing?kind=${briefingKind}`, { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const b = await res.json();
    el.innerHTML = b.sections.length
      ? b.sections.map((s) => `<div class="briefing-section"><div class="briefing-title">${esc(s.title)}</div>
          <ul class="list compact">${s.items.map((i) => `<li class="list-item compact">${esc(i)}</li>`).join("")}</ul></div>`).join("")
        + `<p class="muted briefing-time">Updated ${esc(b.generated_at.slice(11, 16))}</p>`
      : `<p class="empty-state">Nothing needs you right now.</p>`;
  } catch (e) {
    el.innerHTML = `<p class="muted">Couldn't load the briefing: ${esc(String(e))}</p>`;
  } finally {
    briefingBusy = false;
  }
}
document.querySelectorAll(".briefing-kind").forEach((btn) => btn.addEventListener("click", () => {
  document.querySelectorAll(".briefing-kind").forEach((b) => b.classList.toggle("active", b === btn));
  briefingKind = btn.dataset.kind;
  refreshBriefing();
}));
document.getElementById("briefing-refresh")?.addEventListener("click", refreshBriefing);
window.addEventListener("hashchange", () => { if (currentRoute() === "home") refreshBriefing(); });
if (typeof currentRoute === "function" && currentRoute() === "home") refreshBriefing();
setInterval(() => { if (currentRoute() === "home" && !document.hidden) refreshBriefing(); }, 10 * 60 * 1000);

// --- Memory route (P3): facts + "about me" profile fields, editable -------------------------------
let memoryData = null;
async function refreshMemory() {
  const hist = document.getElementById("memory-history")?.checked;
  try {
    const res = await fetch(`/api/memory?include_superseded=${hist ? "true" : "false"}`, { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    memoryData = await res.json();
  } catch (e) {
    document.getElementById("memory-facts").innerHTML = `<li class="muted">Couldn't load memory: ${esc(String(e))}</li>`;
    return;
  }
  const sel = document.getElementById("memory-add-category");
  if (!sel.options.length) sel.innerHTML = memoryData.categories.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
  document.getElementById("memory-profile").innerHTML = memoryData.profile.length
    ? memoryData.profile.map((p) => `<div class="setting-row"><div class="setting-text"><div class="setting-label mono">${esc(p.key)}</div>
        <div class="setting-help">${esc(p.value)}</div></div>
        <div class="setting-control"><button class="btn btn-ghost" data-profile-del="${esc(p.key)}" type="button">Delete</button></div></div>`).join("")
    : `<p class="muted">No profile fields yet.</p>`;
  renderMemoryFacts();
}

function renderMemoryFacts() {
  if (!memoryData) return;
  const q = (document.getElementById("memory-search").value || "").trim().toLowerCase();
  const facts = memoryData.facts.filter((f) => !q || `${f.content} ${f.key || ""} ${f.category}`.toLowerCase().includes(q));
  document.getElementById("memory-facts").innerHTML = facts.length ? facts.map((f) => `
    <li class="list-item memory-fact${f.superseded_at ? " memory-old" : ""}" data-id="${f.id}">
      <div class="memory-main"><span class="src-badge">${esc(f.category)}</span> <span class="memory-text">${esc(f.content)}</span></div>
      <div class="memory-meta muted">#${f.id} · ${esc((f.created_at || "").replace("T", " ").slice(0, 16))} ·
        ${f.source === "auto" ? "picked up from conversation" : "remembered"}${f.key ? " · " + esc(f.key) : ""}
        ${f.superseded_at ? " · replaced by #" + esc(String(f.superseded_by || "")) : ""}</div>
      ${f.superseded_at ? "" : `<div class="memory-actions"><button class="btn btn-ghost" data-edit="${f.id}" type="button">Edit</button>
        <button class="btn btn-ghost" data-forget="${f.id}" type="button">Forget</button></div>`}
    </li>`).join("") : `<li class="empty-state">${q ? "No matching facts." : "Nothing remembered yet."}</li>`;
}

async function memoryCall(url, method, body) {
  const status = document.getElementById("memory-status");
  const res = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  const data = await res.json().catch(() => ({}));
  status.textContent = res.ok ? (data.result || "Saved.") : (data.error || data.result || `Failed (HTTP ${res.status})`);
  await refreshMemory();
  return res.ok;
}

document.getElementById("memory-facts")?.addEventListener("click", async (e) => {
  const edit = e.target.closest("[data-edit]");
  const forget = e.target.closest("[data-forget]");
  const save = e.target.closest("[data-save]");
  if (forget) {
    const f = memoryData.facts.find((x) => x.id === +forget.dataset.forget);
    if (f && confirm(`Forget this for good?\n\n${f.content}`)) memoryCall(`/api/memory/facts/${f.id}`, "DELETE");
  } else if (edit) {
    const li = edit.closest("li");
    const f = memoryData.facts.find((x) => x.id === +edit.dataset.edit);
    li.querySelector(".memory-main").innerHTML = `<input class="memory-edit-input" maxlength="1000" value="${esc(f.content)}" aria-label="Edit fact">`;
    li.querySelector(".memory-actions").innerHTML = `<button class="btn" data-save="${f.id}" type="button">Save</button>
      <button class="btn btn-ghost" data-cancel type="button">Cancel</button>`;
    li.querySelector(".memory-edit-input").focus();
  } else if (save) {
    const input = save.closest("li").querySelector(".memory-edit-input");
    memoryCall(`/api/memory/facts/${save.dataset.save}`, "POST", { content: input.value });
  } else if (e.target.closest("[data-cancel]")) {
    renderMemoryFacts();
  }
});
document.getElementById("memory-profile")?.addEventListener("click", (e) => {
  const del = e.target.closest("[data-profile-del]");
  if (del && confirm(`Delete "${del.dataset.profileDel}"?`)) memoryCall(`/api/memory/profile/${encodeURIComponent(del.dataset.profileDel)}`, "DELETE");
});
document.getElementById("memory-add-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const ok = await memoryCall("/api/memory/facts", "POST", {
    category: document.getElementById("memory-add-category").value,
    content: document.getElementById("memory-add-content").value,
  });
  if (ok) document.getElementById("memory-add-content").value = "";
});
document.getElementById("memory-profile-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const ok = await memoryCall("/api/memory/profile", "POST", {
    key: document.getElementById("memory-profile-key").value, value: document.getElementById("memory-profile-value").value,
  });
  if (ok) e.target.reset();
});
document.getElementById("memory-search")?.addEventListener("input", renderMemoryFacts);
document.getElementById("memory-history")?.addEventListener("change", refreshMemory);
window.refreshMemory = refreshMemory;
if (typeof currentRoute === "function" && currentRoute() === "memory") refreshMemory();

// --- Home health status + safe mode (P4): GET /api/health, POST /api/safe_mode -------------------
let healthSafe = false;
async function refreshHealth() {
  const list = document.getElementById("home-health-status");
  if (!list) return;
  try {
    const res = await fetch("/api/health", { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const h = await res.json();
    healthSafe = !!h.safe_mode;
    const btn = document.getElementById("safe-mode-btn");
    btn.textContent = `Safe mode: ${healthSafe ? "on" : "off"}`;
    btn.setAttribute("aria-pressed", String(healthSafe));
    btn.classList.toggle("active", healthSafe);
    list.innerHTML = h.items.map((i) => `<li class="list-item compact"><span class="health-dot ${i.ok ? "ok" : "bad"}" aria-hidden="true"></span>
      <span class="tool">${esc(i.name)}</span> <span class="muted">${esc(i.detail)}</span></li>`).join("");
  } catch (e) {
    list.innerHTML = `<li class="muted">Couldn't load health: ${esc(String(e))}</li>`;
  }
}
document.getElementById("safe-mode-btn")?.addEventListener("click", async () => {
  const turnOn = !healthSafe;
  if (turnOn && !confirm("Turn on safe mode? Autonomy pauses, the follow-up window turns off and non-urgent announcements are held. Commands still work.")) return;
  try {
    await fetch("/api/safe_mode", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ on: turnOn }) });
  } catch (e) { alert("Couldn't change safe mode: " + e); }
  refreshHealth();
});
window.addEventListener("hashchange", () => { if (currentRoute() === "home") refreshHealth(); });
if (typeof currentRoute === "function" && currentRoute() === "home") refreshHealth();
setInterval(() => { if (currentRoute() === "home" && !document.hidden) refreshHealth(); }, 30000);

// --- Home voice speed (second wave): last 20 voice commands from jarvis_latency.recent ------------
async function refreshLatency() {
  const el = document.getElementById("home-latency");
  if (!el) return;
  try {
    const rows = ((await (await fetch("/api/latency", { cache: "no-store" })).json()).recent || []).filter((r) => r.e2e_ms != null);
    if (!rows.length) { el.textContent = "No voice commands since Jarvis started."; return; }
    const sorted = rows.map((r) => r.e2e_ms).sort((a, b) => a - b);
    const med = sorted[Math.floor(sorted.length / 2)];
    const ttfa = rows.map((r) => r.tts_ttfa_ms).filter((v) => v != null).sort((a, b) => a - b);
    const last = rows.slice(-5).reverse().map((r) => (r.e2e_ms / 1000).toFixed(1) + "s").join(", ");
    el.textContent = `Median ${(med / 1000).toFixed(1)}s end to end` +
      (ttfa.length ? `, first words after ${(ttfa[Math.floor(ttfa.length / 2)] / 1000).toFixed(1)}s` : "") +
      ` (last ${rows.length}). Latest: ${last}.`;
  } catch (e) { el.textContent = "Couldn't load voice timings."; }
}
window.addEventListener("hashchange", () => { if (currentRoute() === "home") refreshLatency(); });
if (typeof currentRoute === "function" && currentRoute() === "home") refreshLatency();
setInterval(() => { if (currentRoute() === "home" && !document.hidden) refreshLatency(); }, 30000);

// --- Home network devices: GET /api/network_devices (scanned server-side every 60s) --------------
async function refreshNetwork() {
  const list = document.getElementById("home-network");
  const meta = document.getElementById("home-network-meta");
  if (!list) return;
  try {
    const res = await fetch("/api/network_devices", { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const n = await res.json();
    if (!n.ok) {
      meta.textContent = "";
      list.innerHTML = `<li class="muted">${n.pending ? (n.enabled === false ? "Network scan is off (JARVIS_NETSCAN_INTERVAL_S=0)." : "First scan runs within a minute of Jarvis starting&hellip;") : "Scan failed: " + esc(n.error || "unknown")}</li>`;
      return;
    }
    const when = n.scanned_at ? new Date(n.scanned_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
    meta.textContent = `${n.devices.length} online · ${n.network} · ${when}`;
    list.innerHTML = n.devices.map((d) => {
      const tag = d.this_pc ? "this PC" : d.gateway ? "router" : d.private_mac ? "private MAC" : "";
      const isNew = !d.this_pc && d.first_seen && Date.now() / 1000 - d.first_seen < 3600;
      return `<li class="list-item compact"><span class="health-dot ok" aria-hidden="true"></span>
        <span class="tool">${esc(d.hostname || d.ip)}</span> <span class="muted">${esc(d.ip)} · <code>${esc(d.mac)}</code>${tag ? " · " + tag : ""}</span>${isNew ? ' <span class="pill pill-running">new</span>' : ""}</li>`;
    }).join("") || '<li class="muted">No devices found.</li>';
  } catch (e) {
    list.innerHTML = `<li class="muted">Couldn't load network devices: ${esc(String(e))}</li>`;
  }
}
window.addEventListener("hashchange", () => { if (currentRoute() === "home") refreshNetwork(); });
if (typeof currentRoute === "function" && currentRoute() === "home") refreshNetwork();
setInterval(() => { if (currentRoute() === "home" && !document.hidden) refreshNetwork(); }, 60000);
