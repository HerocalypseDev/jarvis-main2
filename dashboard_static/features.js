// Feature batch 2026-09-27 (FEATURES.md): the Toolbox route. Each panel talks to the generic
// GET /api/feature/{name} and POST /api/feature/{name}/{action} routes. Plain JS, esc() from app.js.

async function featureGet(name) {
  const res = await fetch(`/api/feature/${name}`, { cache: "no-store" });
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

async function featurePost(name, action, body) {
  const res = await fetch(`/api/feature/${name}/${action}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || data.detail || "HTTP " + res.status);
  return data;
}

function fmtWhen(iso) {
  return esc(String(iso || "").replace("T", " ").slice(0, 16));
}

const TOOLBOX_PANELS = [];

async function refreshToolbox() {
  for (const p of TOOLBOX_PANELS) {
    try { await p(); } catch (e) { console.warn("toolbox panel failed", e); }
  }
}
window.refreshToolbox = refreshToolbox;

// --- Clipboard history (A1) -------------------------------------------------------------------
function clipRows(items) {
  return items.length ? items.map((c) => `
    <li class="list-item compact">
      <span class="src-badge">${esc(c.kind)}</span>
      <span class="clip-preview">${c.kind === "sensitive" ? `<span class="muted">hidden secret, ${c.char_len} characters</span>` : esc(c.preview)}</span>
      <span class="muted">${fmtWhen(c.created_at)}</span>
      ${c.kind === "sensitive" ? "" : `<button class="btn btn-ghost" type="button" data-clip-copy="${c.id}">Copy</button>`}
    </li>`).join("") : `<li class="empty-state">Nothing copied yet.</li>`;
}

async function refreshClipboard() {
  const list = document.getElementById("tb-clip-list");
  if (!list) return;
  const q = (document.getElementById("tb-clip-search").value || "").trim();
  const data = q ? await featurePost("clipboard", "search", { query: q }) : await featureGet("clipboard");
  list.innerHTML = clipRows(data.items || []);
}
TOOLBOX_PANELS.push(refreshClipboard);

document.getElementById("tb-clip-search")?.addEventListener("input", () => refreshClipboard().catch(() => {}));
document.getElementById("tb-clip-list")?.addEventListener("click", async (e) => {
  const id = e.target.dataset.clipCopy;
  if (!id) return;
  const r = await featurePost("clipboard", "copy", { id: Number(id) }).catch((err) => ({ result: String(err) }));
  document.getElementById("tb-clip-status").textContent = r.result || "";
});
document.getElementById("tb-clip-clear")?.addEventListener("click", async () => {
  if (!confirm("Delete the whole clipboard history?")) return;
  const r = await featurePost("clipboard", "clear").catch((err) => ({ result: String(err) }));
  document.getElementById("tb-clip-status").textContent = r.result || "";
  refreshClipboard();
});

// --- Macros (A4 + D1 form builder) ------------------------------------------------------------
let macroTools = [];

function macroStepRow(step) {
  const opts = macroTools.map((t) => `<option ${step && step.tool === t ? "selected" : ""}>${esc(t)}</option>`).join("");
  return `<div class="macro-step">
    <select class="macro-step-tool" aria-label="Tool">${opts}</select>
    <input class="macro-step-input mono" aria-label="Tool input as JSON" placeholder='{"app": "vscode"}'
      value="${escAttr(step ? JSON.stringify(step.input || {}) : "{}")}">
    <button class="btn btn-ghost" type="button" data-step-remove>&times;</button></div>`;
}

async function refreshMacros() {
  const list = document.getElementById("tb-macro-list");
  if (!list) return;
  const data = await featureGet("macros");
  macroTools = data.tools || [];
  const steps = document.getElementById("tb-macro-steps");
  if (!steps.children.length) steps.innerHTML = macroStepRow(null);
  list.innerHTML = (data.macros || []).length ? data.macros.map((m) => `
    <li class="list-item">
      <div><span class="tool">${esc(m.name)}</span> ${m.enabled ? "" : '<span class="pill">off</span>'}
        <span class="muted">say ${m.phrases.map((p) => "&ldquo;" + esc(p) + "&rdquo;").join(" or ")}</span></div>
      <div class="muted">${m.steps.map((s) => esc(s.tool)).join(" &rarr; ")} · ran ${m.runs} time(s)${m.last_run ? ", last " + fmtWhen(m.last_run) : ""}</div>
      <div class="memory-actions">
        <button class="btn btn-ghost" type="button" data-macro="${escAttr(m.name)}" data-verb="run">Run</button>
        <button class="btn btn-ghost" type="button" data-macro="${escAttr(m.name)}" data-verb="${m.enabled ? "disable" : "enable"}">${m.enabled ? "Turn off" : "Turn on"}</button>
        <button class="btn btn-ghost" type="button" data-macro="${escAttr(m.name)}" data-verb="edit">Edit</button>
        <button class="btn btn-ghost" type="button" data-macro="${escAttr(m.name)}" data-verb="delete">Delete</button>
      </div></li>`).join("") : `<li class="empty-state">No macros yet. Make one below, or say "when I say start work mode, open VS Code and turn on focus mode".</li>`;
  list._macros = data.macros || [];
}
TOOLBOX_PANELS.push(refreshMacros);

document.getElementById("tb-macro-add-step")?.addEventListener("click", () => {
  document.getElementById("tb-macro-steps").insertAdjacentHTML("beforeend", macroStepRow(null));
});
document.getElementById("tb-macro-steps")?.addEventListener("click", (e) => {
  if (e.target.dataset.stepRemove !== undefined) e.target.closest(".macro-step").remove();
});
document.getElementById("tb-macro-list")?.addEventListener("click", async (e) => {
  const name = e.target.dataset.macro, verb = e.target.dataset.verb;
  if (!name) return;
  const status = document.getElementById("tb-macro-status");
  if (verb === "edit") {
    const m = (e.currentTarget._macros || []).find((x) => x.name === name);
    document.getElementById("tb-macro-name").value = m.name;
    document.getElementById("tb-macro-phrases").value = m.phrases.join(", ");
    document.getElementById("tb-macro-steps").innerHTML = m.steps.map(macroStepRow).join("");
    return;
  }
  if (verb === "delete" && !confirm(`Delete the macro "${name}"?`)) return;
  const r = await featurePost("macros", verb, { name }).catch((err) => ({ result: String(err) }));
  status.textContent = r.result || "";
  refreshMacros();
});
document.getElementById("tb-macro-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("tb-macro-status");
  const steps = [];
  for (const row of document.querySelectorAll("#tb-macro-steps .macro-step")) {
    let input;
    try { input = JSON.parse(row.querySelector(".macro-step-input").value || "{}"); } catch (err) {
      status.textContent = "A step's input isn't valid JSON."; return;
    }
    steps.push({ tool: row.querySelector(".macro-step-tool").value, input });
  }
  const phrases = document.getElementById("tb-macro-phrases").value.split(",").map((p) => p.trim()).filter(Boolean);
  const r = await featurePost("macros", "create", { name: document.getElementById("tb-macro-name").value, phrases, steps })
    .catch((err) => ({ result: String(err) }));
  status.textContent = r.result || "";
  refreshMacros();
});

// --- Home network card: rename a device (A3) ---------------------------------------------------
document.getElementById("home-network")?.addEventListener("click", async (e) => {
  const mac = e.target.dataset.renameMac;
  if (!mac) return;
  const name = prompt("Name for this device (empty removes the name):", e.target.dataset.current || "");
  if (name === null) return;
  await featurePost("devices", "name", { mac, name }).catch((err) => alert(String(err)));
  if (window.refreshNetwork) window.refreshNetwork();
});
