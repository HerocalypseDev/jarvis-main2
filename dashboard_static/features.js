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
  // Pro routines: read-only (no Edit/Delete), can be switched off; only present with a valid Pro key.
  const pack = data.pack || [];
  if (pack.length) {
    list.insertAdjacentHTML("beforeend", pack.map((m) => `
    <li class="list-item">
      <div><span class="pill">Pro</span> <span class="tool">${esc(m.name)}</span> ${m.enabled ? "" : '<span class="pill">off</span>'}
        <span class="muted">say ${m.phrases.map((p) => "&ldquo;" + esc(p) + "&rdquo;").join(" or ")}</span></div>
      <div class="muted">${m.steps.map((s) => esc(s.tool)).join(" &rarr; ")}</div>
      <div class="memory-actions">
        <button class="btn btn-ghost" type="button" data-pro-routine="${escAttr(m.name)}">${m.enabled ? "Turn off" : "Turn on"}</button>
      </div></li>`).join(""));
  }
  // Habits: commands you keep repeating that always ran the same tool calls. Never created without a click.
  const sugg = data.suggestions || [];
  if (sugg.length) {
    list.insertAdjacentHTML("beforeend", sugg.map((sg) => `
    <li class="list-item">
      <div><span class="pill">Suggested</span> <span class="tool">${esc(sg.phrase)}</span>
        <span class="muted">you said this ${esc(String(sg.count))} times</span></div>
      <div class="muted">would run: ${sg.steps.map((st) => esc(st.tool)).join(" &rarr; ")} &middot; no AI call, instant</div>
      <div class="memory-actions">
        <button class="btn btn-ghost" type="button" data-suggest="${escAttr(sg.phrase)}">Make it a macro</button>
      </div></li>`).join(""));
  }
}
document.getElementById("tb-macro-list")?.addEventListener("click", async (e) => {
  const phrase = e.target.closest("[data-suggest]")?.dataset.suggest;
  if (!phrase) return;
  const status = document.getElementById("tb-macro-status");
  const r = await featurePost("macros", "accept", { phrase }).catch((err) => ({ result: String(err) }));
  if (status) status.textContent = r.result || "";
  refreshMacros();
});
document.getElementById("tb-macro-list")?.addEventListener("click", async (e) => {
  const name = e.target.closest("[data-pro-routine]")?.dataset.proRoutine;
  if (!name) return;
  const r = await featurePost("macros", "pack_toggle", { name }).catch((err) => ({ result: String(err) }));
  const st = document.getElementById("tb-macro-status");
  if (st) st.textContent = r.result || "";
  refreshMacros();
});
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

// --- Background agents (C1) --------------------------------------------------------------------
let agentTools = [];
const AGENT_CONFIG_HINTS = {
  interval: '{"every_min": 60}', daily: '{"at": "08:00", "days": "mon,tue,wed,thu,fri"}',
  mail_match: '{"query": "from:someone@example.com"}', file_event: '{"ext": "pdf", "name_contains": "invoice"}', manual: "{}",
};

function agentStepRow(step) {
  const opts = agentTools.map((t) => `<option ${step && step.tool === t ? "selected" : ""}>${esc(t)}</option>`).join("");
  return `<div class="macro-step">
    <select class="macro-step-tool" aria-label="Tool">${opts}</select>
    <input class="macro-step-input mono" aria-label="Tool input as JSON" value="${escAttr(step ? JSON.stringify(step.input || {}) : "{}")}">
    <button class="btn btn-ghost" type="button" data-step-remove>&times;</button></div>`;
}

async function refreshAgents() {
  const list = document.getElementById("tb-agent-list");
  if (!list) return;
  const data = await featureGet("agents");
  agentTools = data.tools || [];
  const steps = document.getElementById("tb-agent-steps");
  if (!steps.children.length) steps.innerHTML = agentStepRow(null);
  const running = new Set(data.running || []);
  list.innerHTML = (data.agents || []).length ? data.agents.map((a) => `
    <li class="list-item">
      <div><span class="tool">${esc(a.name)}</span> ${a.enabled ? "" : '<span class="pill">off</span>'}
        ${running.has(a.id) ? '<span class="pill pill-running">running</span>' : ""}
        <span class="muted">${esc(a.trigger_type)} <code>${esc(JSON.stringify(a.trigger_config))}</code> &rarr; ${a.steps.map((s) => esc(s.tool)).join(" &rarr; ")}</span></div>
      <div class="muted">${a.last_run ? `Last run ${fmtWhen(a.last_run)} (${a.last_ok ? "ok" : "failed"}): ${esc(String(a.last_result || "").slice(0, 200))}` : "Not run yet."}
        · ${a.runs_day === new Date().toISOString().slice(0, 10) ? a.runs_today : 0}/${a.max_runs_per_day} today</div>
      <div class="memory-actions">
        <button class="btn btn-ghost" type="button" data-agent="${escAttr(a.name)}" data-verb="run">Run now</button>
        <button class="btn btn-ghost" type="button" data-agent="${escAttr(a.name)}" data-verb="${a.enabled ? "disable" : "enable"}">${a.enabled ? "Turn off" : "Turn on"}</button>
        <button class="btn btn-ghost" type="button" data-agent="${escAttr(a.name)}" data-verb="delete">Delete</button>
      </div></li>`).join("") : `<li class="empty-state">No background agents yet.</li>`;
}
TOOLBOX_PANELS.push(refreshAgents);

document.getElementById("tb-agent-trigger")?.addEventListener("change", (e) => {
  document.getElementById("tb-agent-config").value = AGENT_CONFIG_HINTS[e.target.value] || "{}";
});
document.getElementById("tb-agent-add-step")?.addEventListener("click", () => {
  document.getElementById("tb-agent-steps").insertAdjacentHTML("beforeend", agentStepRow(null));
});
document.getElementById("tb-agent-steps")?.addEventListener("click", (e) => {
  if (e.target.dataset.stepRemove !== undefined) e.target.closest(".macro-step").remove();
});
document.getElementById("tb-agent-list")?.addEventListener("click", async (e) => {
  const name = e.target.dataset.agent, verb = e.target.dataset.verb;
  if (!name) return;
  if (verb === "delete" && !confirm(`Delete the background agent "${name}"?`)) return;
  const r = await featurePost("agents", verb, { name }).catch((err) => ({ result: String(err) }));
  document.getElementById("tb-agent-status").textContent = r.result || "";
  setTimeout(() => refreshAgents().catch(() => {}), 500);
});
document.getElementById("tb-agent-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const status = document.getElementById("tb-agent-status");
  let config;
  const steps = [];
  try {
    config = JSON.parse(document.getElementById("tb-agent-config").value || "{}");
    for (const row of document.querySelectorAll("#tb-agent-steps .macro-step")) {
      steps.push({ tool: row.querySelector(".macro-step-tool").value, input: JSON.parse(row.querySelector(".macro-step-input").value || "{}") });
    }
  } catch (err) { status.textContent = "The trigger settings or a step input isn't valid JSON."; return; }
  const r = await featurePost("agents", "create", {
    name: document.getElementById("tb-agent-name").value, trigger_type: document.getElementById("tb-agent-trigger").value,
    trigger_config: config, steps, max_runs_per_day: Number(document.getElementById("tb-agent-max").value || 24),
  }).catch((err) => ({ result: String(err) }));
  status.textContent = r.result || "";
  refreshAgents();
});

// --- Notification priority (C6) ----------------------------------------------------------------
async function refreshNotifyStats() {
  const list = document.getElementById("tb-notify-list");
  if (!list) return;
  const data = await featureGet("notifications");
  const rows = Object.entries(data.stats || {});
  list.innerHTML = rows.length ? rows.map(([k, s]) => `<li class="list-item compact"><span class="tool">${esc(k)}</span>
    <span class="muted">${s.delivered} spoken · ${s.acted} followed up · ${s.dismissed} cut off · ${s.score == null ? "still learning" : "score " + s.score.toFixed(2)}</span>
    ${s.batched ? '<span class="pill">hourly digest</span>' : ""}</li>`).join("") : `<li class="empty-state">No announcements counted yet.</li>`;
  document.getElementById("tb-notify-digest").textContent = (data.digest || []).length
    ? `${data.digest.length} message(s) waiting for the next digest.` : "";
}
TOOLBOX_PANELS.push(refreshNotifyStats);
document.getElementById("tb-notify-reset")?.addEventListener("click", async () => {
  if (!confirm("Forget what Jarvis learned about which announcements you want?")) return;
  await featurePost("notifications", "reset").catch(() => {});
  refreshNotifyStats();
});

// --- Knowledge graph (C5) ----------------------------------------------------------------------
document.getElementById("tb-graph-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = document.getElementById("tb-graph-out");
  const r = await featurePost("graph", "query", { name: document.getElementById("tb-graph-q").value }).catch(() => null);
  if (!r) { out.innerHTML = '<li class="muted">Lookup failed.</li>'; return; }
  if (!r.matches.length) { out.innerHTML = '<li class="empty-state">Nothing by that name.</li>'; return; }
  out.innerHTML = r.edges.length ? r.edges.map((x) => `<li class="list-item compact">${esc(x.a)} <span class="muted">(${esc(x.at)})</span>
    <span class="src-badge">${esc(x.rel.replace(/_/g, " "))}</span> ${esc(x.b)} <span class="muted">(${esc(x.bt)})</span></li>`).join("")
    : `<li class="muted">Found ${r.matches.map((m) => esc(m.name)).join(", ")}, nothing linked yet.</li>`;
});
document.getElementById("tb-graph-sync")?.addEventListener("click", async () => {
  const r = await featurePost("graph", "sync").catch(() => null);
  document.getElementById("tb-graph-out").innerHTML = r ? `<li class="muted">Refreshed: ${Object.entries(r.counts).map(([k, n]) => `${n} ${esc(k)}`).join(", ")}</li>` : "";
});

// --- Weekly improvement suggestions (D5) -------------------------------------------------------
async function refreshReport() {
  const list = document.getElementById("tb-report-list");
  if (!list) return;
  const data = await featureGet("report");
  list.innerHTML = (data.suggestions || []).length ? data.suggestions.map((x) => `<li class="list-item compact">${esc(x)}</li>`).join("")
    : `<li class="empty-state">Nothing to suggest from the last week.</li>`;
}
TOOLBOX_PANELS.push(refreshReport);

// Direct load of #/toolbox: app.js routed before this file existed.
if (typeof currentRoute === "function" && currentRoute() === "toolbox") refreshToolbox();

// --- Scheduled work (executive autonomy) --------------------------------------------------------
async function refreshJobs() {
  const list = document.getElementById("tb-jobs-list");
  if (!list) return;
  const data = await featureGet("deferred");
  list.innerHTML = (data.jobs || []).length ? data.jobs.map((j) => `<li class="list-item">
    <div><span class="pill${j.status === "pending" || j.status === "running" ? " pill-running" : ""}">${esc(j.status)}</span>
      <span class="tool">${esc(j.instruction)}</span> <span class="muted">${fmtWhen(j.due_at)} · ${esc(j.origin)}${j.attempts ? " · try " + j.attempts : ""}</span>
      ${j.status === "pending" ? `<button class="btn btn-ghost btn-xs" type="button" data-job-cancel="${j.id}">Cancel</button>` : ""}</div>
    ${j.result ? `<div class="muted">${esc(String(j.result).slice(0, 300))}</div>` : ""}</li>`).join("")
    : `<li class="empty-state">Nothing scheduled. Say "in an hour, run the tests in my project".</li>`;
}
TOOLBOX_PANELS.push(refreshJobs);
document.getElementById("tb-jobs-list")?.addEventListener("click", async (e) => {
  if (!e.target.dataset.jobCancel) return;
  await featurePost("deferred", "cancel", { id: Number(e.target.dataset.jobCancel) }).catch(() => {});
  refreshJobs();
});

// --- Home: today's plan + evening review (smarter batch 2026-09-28) ----------------------------
async function refreshDailyPlan() {
  const list = document.getElementById("home-plan");
  if (!list) return;
  const data = await featureGet("daily_plan").catch(() => null);
  if (!data) { list.innerHTML = `<li class="empty-state">Plan unavailable.</li>`; return; }
  const done = new Set(((data.review || {}).done || []).map((i) => i.ref));
  list.innerHTML = (data.items || []).length ? data.items.map((i) => `
    <li class="list-item compact${done.has(i.ref) ? " done" : ""}">
      <span class="src-badge">${esc(i.kind || "")}</span> ${esc(i.text)}
      ${i.due ? `<span class="muted">${fmtWhen(i.due)}</span>` : ""}
      ${i.why ? `<div class="muted">${esc(i.why)}</div>` : ""}</li>`).join("")
    : `<li class="empty-state">No plan yet today. It's made each morning, or press Rebuild.</li>`;
  document.getElementById("home-plan-review").textContent = data.review_line || "";
}
document.getElementById("plan-refresh")?.addEventListener("click", async (e) => {
  e.target.disabled = true;
  await featurePost("daily_plan", "refresh").catch(() => {});
  e.target.disabled = false;
  refreshDailyPlan().catch(() => {});
});
refreshDailyPlan().catch(() => {});
setInterval(() => refreshDailyPlan().catch(() => {}), 300000);

// --- Jarvis4U Pro license (Settings card) -------------------------------------------------------
// The key is sent once to POST /api/feature/license/activate, verified server-side before it is
// saved to .env, and never shown again (the status only carries the licensee email and date).
async function refreshProCard() {
  const card = document.getElementById("pro-card");
  if (!card) return;
  const st = await featureGet("license").catch(() => null);
  const badge = document.getElementById("pro-badge");
  const status = document.getElementById("pro-status");
  const remove = document.getElementById("pro-remove");
  if (!st) { status.textContent = "Couldn't check the license right now."; return; }
  const lic = st.license || {};
  card.classList.toggle("is-pro", !!lic.valid);
  badge.textContent = lic.valid ? "PRO" : "free";
  badge.className = "pill" + (lic.valid ? " pill-done" : "");
  remove.hidden = !lic.valid;
  const row = document.getElementById("pro-theme-row");
  const sel = document.getElementById("pro-theme");
  const themes = st.themes || [];
  row.hidden = !themes.length;
  sel.innerHTML = '<option value="">Default (cyan)</option>' +
    themes.map((t) => `<option value="${escAttr(t.id)}">${esc(t.name)}</option>`).join("");
  sel.value = savedProTheme();
  if (lic.valid) {
    const pack = st.installed ? `Pro pack ${esc(st.pack.version || "")} installed, ${st.skills} Pro skill(s) active.`
      : "Now unzip the Pro pack you downloaded into the <span class=\"mono\">pro</span> folder next to jarvis.py.";
    status.innerHTML = `Licensed to <strong>${esc(lic.email)}</strong> since ${esc(lic.issued)}. ${pack}`;
  } else {
    status.textContent = lic.reason && lic.reason !== "No license key entered." ? lic.reason : "You're on the free version.";
  }
}
document.getElementById("pro-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("pro-key");
  const msg = document.getElementById("pro-msg");
  msg.textContent = "Checking…";
  const r = await featurePost("license", "activate", { key: input.value }).catch((err) => ({ ok: false, error: String(err.message || err) }));
  msg.textContent = r.ok ? "Pro activated. Thank you for supporting Jarvis4U!" : r.error;
  if (r.ok) input.value = "";
  refreshProCard();
});
document.getElementById("pro-remove")?.addEventListener("click", async () => {
  if (!confirm("Remove the Pro license key from this PC?")) return;
  await featurePost("license", "deactivate").catch(() => {});
  applyProTheme("");
  document.getElementById("pro-msg").textContent = "Key removed.";
  refreshProCard();
});
window.addEventListener("hashchange", () => { if (currentRoute() === "settings") refreshProCard().catch(() => {}); });
if (typeof currentRoute === "function" && currentRoute() === "settings") refreshProCard().catch(() => {});

// --- Pro themes: the choice is a per-browser convenience (localStorage); the CSS comes from the
// server, which rebuilds it from colour tokens only (jarvis_pro.theme_css) and only with a valid key.
function savedProTheme() {
  try { return localStorage.getItem("jarvis-pro-theme") || ""; } catch (e) { return ""; }
}
async function applyProTheme(id) {
  let style = document.getElementById("pro-theme-style");
  if (!id) { if (style) style.remove(); return; }
  const r = await featurePost("license", "theme_css", { id }).catch(() => null);
  if (!r || !r.ok) { if (style) style.remove(); return; }
  if (!style) { style = document.createElement("style"); style.id = "pro-theme-style"; document.head.appendChild(style); }
  style.textContent = r.css;
}
document.getElementById("pro-theme")?.addEventListener("change", (e) => {
  try { localStorage.setItem("jarvis-pro-theme", e.target.value); } catch (err) { /* ignore */ }
  applyProTheme(e.target.value);
});
applyProTheme(savedProTheme());

// --- Jarvis4U Pro Home widgets: GET /api/feature/pro_widgets (read-only) ------------------------------
// The pack only describes widgets (fixed types, fixed read-only sources). Every widget is drawn here by fixed
// code and every string goes through esc(): no HTML, CSS or script from a pack ever reaches the page.
function proSparkline(points) {
  if (!points || points.length < 2) return "";
  const w = 64, h = 24, step = w / (points.length - 1);
  const xy = points.map((p, i) => `${(i * step).toFixed(1)},${(h - (Math.max(0, Math.min(100, p)) / 100) * h).toFixed(1)}`);
  return `<svg class="pro-spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true">
    <polyline points="${xy.join(" ")}" fill="none" stroke="var(--color-accent)" stroke-width="2" stroke-linejoin="round"/></svg>`;
}

function proWidgetBody(wg) {
  if (wg.type === "stat") {
    return `<div class="pro-stat"><span class="pro-stat-value">${esc(String(wg.value))}</span>
      <span class="muted">${esc(wg.caption || "")}</span></div>`;
  }
  if (wg.type === "countdown") {
    return `<ul class="list compact">${(wg.items || []).map((it) => `<li class="list-item compact pro-row">
      <span>${esc(it.label)}</span><span class="pro-days">${it.days === 0 ? "today" : esc(String(it.days)) + (it.days === 1 ? " day" : " days")}</span></li>`).join("")}</ul>`;
  }
  if (wg.type === "score_trend") {
    return `<ul class="list compact">${(wg.subjects || []).map((s) => {
      const delta = s.latest - s.first;
      const trend = s.sessions > 1 ? ` <span class="muted">(${delta >= 0 ? "+" : ""}${esc(String(delta))})</span>` : "";
      return `<li class="list-item compact pro-row"><span>${esc(s.subject)}<br><span class="muted">${esc(String(s.sessions))} session${s.sessions === 1 ? "" : "s"}${s.weak ? " · weak: " + esc(s.weak) : ""}</span></span>
        <span class="pro-score">${proSparkline(s.points)}<strong>${esc(String(s.latest))}%</strong>${trend}</span></li>`;
    }).join("")}</ul>`;
  }
  if (wg.type === "board") {
    return `<div class="pro-board">${(wg.columns || []).map((c) => `<div class="pro-col">
      <div class="pro-col-head">${esc(c.status)} <span class="muted">${esc(String(c.count))}</span></div>
      ${(c.items || []).map((it) => `<div class="pro-card">${esc(it)}</div>`).join("")}</div>`).join("")}</div>`;
  }
  return `<ul class="list compact">${(wg.items || []).map((it) => `<li class="list-item compact pro-row">
    <span>${esc(it.label)}</span>${it.when ? `<span class="muted">${esc(it.when)}</span>` : ""}</li>`).join("")}</ul>`;
}

async function refreshProWidgets() {
  const box = document.getElementById("home-pro");
  const grid = document.getElementById("home-pro-widgets");
  if (!box || !grid) return;
  try {
    const res = await fetch("/api/feature/pro_widgets", { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    if (!data.active) { box.hidden = true; return; }
    const shown = (data.widgets || []).filter((wg) => !wg.empty);
    box.hidden = false;
    grid.innerHTML = shown.length
      ? shown.map((wg) => `<section class="pro-widget pro-w-${esc(wg.type)}"><h4 class="pro-widget-title">${esc(wg.title)}</h4>${proWidgetBody(wg)}</section>`).join("")
      : '<p class="muted">Your Pro widgets fill in as you use the packs: save an exam, do a practice test, track a job application or plan your week.</p>';
  } catch (e) {
    box.hidden = true;  // widgets are extras: never show a broken Home because of them
  }
}
window.addEventListener("hashchange", () => { if (currentRoute() === "home") refreshProWidgets(); });
if (typeof currentRoute === "function" && currentRoute() === "home") refreshProWidgets();
setInterval(() => { if (currentRoute() === "home" && !document.hidden) refreshProWidgets(); }, 30000);
