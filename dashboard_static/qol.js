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
}

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
    else if (e.key === "Escape") closePalette();
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

function renderPalette(resetSel = true) {
  const q = palette.input.value.trim().toLowerCase();
  const pins = loadPins();
  const seen = new Set();
  const all = [...pins.map((t) => ({ text: t, pinned: true })), ...palette.recent.map((r) => ({ text: r.text, pinned: false }))]
    .filter((c) => !seen.has(c.text) && seen.add(c.text));
  palette.items = all.filter((c) => !q || c.text.toLowerCase().includes(q)).slice(0, 40);
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
    await fetch("/api/command", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
  } catch (e) { alert("Couldn't send the command: " + e); }
}

document.addEventListener("keydown", (e) => {
  if (e.altKey && !e.ctrlKey && !e.metaKey && e.key.toLowerCase() === "k") {
    e.preventDefault();
    palette.el && !palette.el.classList.contains("hidden") ? closePalette() : openPalette();
  }
});
document.getElementById("palette-btn")?.addEventListener("click", openPalette);
