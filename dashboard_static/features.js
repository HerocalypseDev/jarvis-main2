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

// --- Meeting notes (B1) ------------------------------------------------------------------------
async function refreshMeetings() {
  const list = document.getElementById("tb-meeting-list");
  if (!list) return;
  const data = await featureGet("meetings");
  const btn = document.getElementById("tb-meeting-toggle");
  btn.textContent = data.active ? "Stop meeting notes" : "Start meeting notes";
  btn.dataset.running = data.active ? "1" : "";
  document.getElementById("tb-meeting-status").textContent = data.active
    ? `Recording since ${String(data.active.started_at).slice(11, 16)}, ${data.active.segments} segment(s).` : "";
  list.innerHTML = (data.meetings || []).length ? data.meetings.map((m) => `
    <li class="list-item">
      <div><span class="tool">${esc(m.title || "Meeting")}</span> <span class="muted">${fmtWhen(m.started_at)} · ${m.segments} segment(s) · ${esc(m.status)}${m.stop_reason ? " (" + esc(m.stop_reason) + ")" : ""}</span></div>
      <div>${esc(m.summary || "")}</div>
      ${(m.action_items || []).length ? `<ul>${m.action_items.map((a) => `<li>${esc(a.description)}${a.deadline_iso ? ` <span class="muted">by ${fmtWhen(a.deadline_iso)}</span>` : ""}</li>`).join("")}</ul>` : ""}
      <div class="memory-actions"><button class="btn btn-ghost" type="button" data-meeting-tx="${m.id}">Transcript</button>
        <button class="btn btn-ghost" type="button" data-meeting-del="${m.id}">Delete</button></div>
      <pre class="drafts" id="tb-meeting-tx-${m.id}"></pre></li>`).join("") : `<li class="empty-state">No meeting notes yet.</li>`;
}
TOOLBOX_PANELS.push(refreshMeetings);

document.getElementById("tb-meeting-toggle")?.addEventListener("click", async (e) => {
  const r = await featurePost("meetings", e.target.dataset.running ? "stop" : "start").catch((err) => ({ result: String(err) }));
  document.getElementById("tb-meeting-status").textContent = r.result || "";
  setTimeout(() => refreshMeetings().catch(() => {}), 800);
});
document.getElementById("tb-meeting-list")?.addEventListener("click", async (e) => {
  const tx = e.target.dataset.meetingTx, del = e.target.dataset.meetingDel;
  if (tx) {
    const r = await featurePost("meetings", "transcript", { id: Number(tx) }).catch(() => ({ text: "" }));
    document.getElementById("tb-meeting-tx-" + tx).textContent = r.text || "(empty)";
  }
  if (del && confirm("Delete this meeting's notes and transcript?")) {
    await featurePost("meetings", "delete", { id: Number(del) }).catch(() => {});
    refreshMeetings();
  }
});

// --- Files (B2) --------------------------------------------------------------------------------
let filesTag = "";
function fileRows(rows) {
  return rows.length ? rows.map((r) => `<li class="list-item compact"><span class="clip-preview mono" title="${escAttr(r.path)}">${esc(r.path)}</span>
    <span class="muted">${esc(r.tags)} · ${Math.round((r.size || 0) / 1024)} KB</span></li>`).join("") : `<li class="empty-state">No matching files.</li>`;
}
async function refreshFiles(mode) {
  const list = document.getElementById("tb-files-list");
  if (!list) return;
  const q = document.getElementById("tb-files-search").value.trim();
  if (mode === "dupes") {
    list.innerHTML = fileRows((await featurePost("files", "find", { duplicates: true })).rows || []);
    return;
  }
  if (q || filesTag) {
    list.innerHTML = fileRows((await featurePost("files", "find", { tag: filesTag, name_query: q })).rows || []);
    return;
  }
  const data = await featureGet("files");
  document.getElementById("tb-files-tags").innerHTML = Object.entries(data.tags || {}).slice(0, 30).map(([t, n]) =>
    `<button type="button" class="btn btn-ghost btn-xs chip${t === filesTag ? " active" : ""}" data-tag="${escAttr(t)}">${esc(t)} (${n})</button>`).join("");
  list.innerHTML = fileRows(data.recent || []);
}
TOOLBOX_PANELS.push(() => refreshFiles());
document.getElementById("tb-files-search")?.addEventListener("input", () => refreshFiles().catch(() => {}));
document.getElementById("tb-files-dupes")?.addEventListener("click", () => refreshFiles("dupes").catch(() => {}));
document.getElementById("tb-files-tags")?.addEventListener("click", (e) => {
  if (e.target.dataset.tag === undefined) return;
  filesTag = filesTag === e.target.dataset.tag ? "" : e.target.dataset.tag;
  document.querySelectorAll("#tb-files-tags .chip").forEach((c) => c.classList.toggle("active", c.dataset.tag === filesTag));
  refreshFiles().catch(() => {});
});
document.getElementById("tb-files-index")?.addEventListener("click", async () => {
  const r = await featurePost("files", "index_watched").catch((err) => ({ result: String(err) }));
  document.getElementById("tb-files-status").textContent = r.result || "";
});

// --- App shortcuts (B3) ------------------------------------------------------------------------
async function refreshShortcuts() {
  const list = document.getElementById("tb-sc-list");
  if (!list) return;
  const data = await featureGet("shortcuts");
  document.getElementById("tb-sc-app").textContent = data.foreground.app ? `${data.foreground.app} (${data.foreground.title})` : "unknown";
  const current = new Set((data.current || []).map((s) => s.id));
  list.innerHTML = (data.all || []).length ? data.all.map((s) => `<li class="list-item compact">
    <span class="tool">${esc(s.label)}</span> <span class="muted">in ${esc(s.app)} · ${esc(s.kind)} ${esc(s.value)}</span>
    ${current.has(s.id) ? '<span class="pill pill-running">current app</span>' : ""}
    <button class="btn btn-ghost btn-xs" type="button" data-sc-del="${s.id}">Delete</button></li>`).join("")
    : `<li class="empty-state">No app shortcuts yet.</li>`;
  const appIn = document.getElementById("tb-sc-app-in");
  if (!appIn.value && data.foreground.app) appIn.value = data.foreground.app;
}
TOOLBOX_PANELS.push(refreshShortcuts);
document.getElementById("tb-sc-list")?.addEventListener("click", async (e) => {
  if (!e.target.dataset.scDel) return;
  await featurePost("shortcuts", "delete", { id: Number(e.target.dataset.scDel) }).catch(() => {});
  refreshShortcuts();
});
document.getElementById("tb-sc-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const r = await featurePost("shortcuts", "add", {
    app: document.getElementById("tb-sc-app-in").value, label: document.getElementById("tb-sc-label").value,
    kind: document.getElementById("tb-sc-kind").value, value: document.getElementById("tb-sc-value").value,
  }).catch((err) => ({ result: String(err) }));
  document.getElementById("tb-sc-status").textContent = r.result || "";
  refreshShortcuts();
});

// --- Email replies + templates (B4) ------------------------------------------------------------
async function refreshTemplates() {
  const list = document.getElementById("tb-tpl-list");
  if (!list) return;
  const data = await featureGet("email");
  list.innerHTML = (data.templates || []).length ? data.templates.map((t) => `<li class="list-item compact">
    <span class="tool">${esc(t.name)}</span> <span class="clip-preview muted">${esc(t.body)}</span>
    <button class="btn btn-ghost btn-xs" type="button" data-tpl-del="${escAttr(t.name)}">Delete</button></li>`).join("")
    : `<li class="empty-state">No templates. Save one below, or say "save that as an email template".</li>`;
}
TOOLBOX_PANELS.push(refreshTemplates);
document.getElementById("tb-tpl-list")?.addEventListener("click", async (e) => {
  if (!e.target.dataset.tplDel) return;
  await featurePost("email", "delete_template", { name: e.target.dataset.tplDel }).catch(() => {});
  refreshTemplates();
});
document.getElementById("tb-tpl-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  await featurePost("email", "save_template", { name: document.getElementById("tb-tpl-name").value,
    subject: document.getElementById("tb-tpl-subject").value, body: document.getElementById("tb-tpl-body").value }).catch(() => {});
  e.target.reset();
  refreshTemplates();
});
document.getElementById("tb-email-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("tb-email-status");
  status.textContent = "Writing drafts...";
  const r = await featurePost("email", "suggest", { email: document.getElementById("tb-email-text").value,
    tone: document.getElementById("tb-email-tone").value }).catch((err) => ({ result: String(err) }));
  status.textContent = "";
  document.getElementById("tb-email-drafts").textContent = r.result || "";
});
