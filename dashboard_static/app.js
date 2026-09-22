const state = { data: null, followedSessionId: null };

// --- router ---------------------------------------------------------------------------------
// Hash-based, single active <section class="view" id="view-NAME">. Kept deliberately simple:
// no history API, no nested routes — this is a supervision dashboard, not a SPA framework demo.
const ROUTES = [
  "home", "sessions", "tasks", "autonomy", "identity", "sleep",
  "usage", "activity", "audit", "victory", "daily",
];
// Routes that have somewhere to click *into* more detail — Autonomy/Identity/Sleep/Usage/
// Victory/Daily each already show everything inline and want the full width instead (see
// DASHBOARD.md's "fill empty space" notes), so the context panel stays reserved for the routes
// where clicking a row genuinely means "tell me more about this one thing."
const ROUTES_WITH_CONTEXT = new Set(["home", "sessions", "tasks", "audit", "activity"]);

function currentRoute() {
  const raw = (location.hash || "#/home").replace(/^#\/?/, "");
  return ROUTES.includes(raw) ? raw : "home";
}

function isRouteActive(name) {
  const view = document.getElementById("view-" + name);
  return !!view && view.classList.contains("active");
}

function onRouteActivated(route) {
  if (route === "home") renderHome();
  if (route === "audit") fetchAuditResults();
  if (route === "daily") fetchDailyItems();
  if (route === "usage") fetchUsage();
  if (route === "sleep") fetchSleep();
  if (route === "identity") fetchIdentity();
  if (route === "autonomy" && window.refreshAutonomy) window.refreshAutonomy();
  syncContextVisibility();
}

// Split out from renderRoute() so a detail update can re-check visibility without a hash change
// (e.g. a new command starts while you're already sitting on Sessions).
function syncContextVisibility() {
  const ctx = document.getElementById("context");
  if (ctx) ctx.classList.toggle("hidden", !ROUTES_WITH_CONTEXT.has(currentRoute()));
}

function renderRoute() {
  const route = currentRoute();
  document.querySelectorAll(".nav-link").forEach((a) => a.classList.toggle("active", a.dataset.route === route));
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  const view = document.getElementById("view-" + route);
  if (view) view.classList.add("active");
  onRouteActivated(route);
}

window.addEventListener("hashchange", renderRoute);
if (!location.hash) location.hash = "#/home";

// Sidebar collapse, remembered per browser (localStorage — a per-viewer UI convenience, safe to
// wrap defensively since a private window or blocked storage must never break navigation).
(function initSidebar() {
  const appBody = document.querySelector(".app-body");
  const btn = document.getElementById("sidebar-toggle-btn");
  if (!appBody || !btn) return;
  let collapsed = false;
  try {
    collapsed = localStorage.getItem("jarvis-sidebar-collapsed") === "1";
  } catch (e) { /* ignore */ }
  appBody.classList.toggle("sidebar-collapsed", collapsed);
  btn.addEventListener("click", () => {
    collapsed = !appBody.classList.contains("sidebar-collapsed");
    appBody.classList.toggle("sidebar-collapsed", collapsed);
    try {
      localStorage.setItem("jarvis-sidebar-collapsed", collapsed ? "1" : "0");
    } catch (e) { /* ignore */ }
  });
})();

// `/` focuses the nearest visible command box, unless the user is already typing somewhere.
document.addEventListener("keydown", (e) => {
  if (e.key !== "/" || e.target.matches("input, textarea, select")) return;
  const input = isRouteActive("sessions")
    ? document.getElementById("compose-input")
    : document.getElementById("home-compose-input");
  if (input) {
    e.preventDefault();
    input.focus();
  }
});

async function fetchState() {
  try {
    const res = await fetch("/api/state");
    state.data = await res.json();
    render();
  } catch (e) {
    console.error("Failed to fetch dashboard state", e);
  }
}

function render() {
  const d = state.data;
  if (!d) return;
  renderApproval(d.pending_action);
  renderSessions(d.sessions);
  renderTasks(d.tasks);
  renderActivity(d.audit);
  renderVictory(d.victory_log, d.counts);
  renderMetrics(d.metrics);
  populateToolNames(d.tool_names);
  renderInputMode(d.sessions);
  if (isRouteActive("home")) renderHome();
  // Keep the detail panel in sync with whichever session is being followed — covers both the
  // 15s poll and any WS message, not just the two explicit session_start/session_end events
  // handleLiveEvent reacts to, so a reply that lands between those still shows up promptly.
  if (state.followedSessionId != null) {
    const found = (d.sessions || []).find((s) => s.id === state.followedSessionId);
    if (found) showDetail("session", found, { navigate: false });
  }
}

function renderInputMode(sessions) {
  const el = document.getElementById("input-mode-chip");
  const latest = sessions && sessions.length ? sessions[0] : null;
  el.className = "input-mode-chip";
  if (!latest) {
    el.textContent = "idle";
    return;
  }
  const label = { voice: "voice", text: "typed", phone: "phone", dashboard: "dashboard" }[
    latest.source
  ] || latest.source;
  el.textContent = latest.status === "active" ? `${label}…` : `last: ${label}`;
  el.classList.add(`mode-${latest.source}`);
}

function renderMetrics(metrics) {
  const el = document.getElementById("metrics-strip");
  if (!metrics) {
    el.innerHTML = "";
    return;
  }
  const bars = [];
  if (metrics.cpu) {
    bars.push(metricBar("CPU", metrics.cpu.overall_percent, "%"));
  }
  if (metrics.memory) {
    bars.push(metricBar("RAM", metrics.memory.percent, "%"));
  }
  if (metrics.disks && metrics.disks.length) {
    const d0 = metrics.disks[0];
    bars.push(metricBar(d0.mountpoint || "Disk", d0.percent, "%"));
  }
  const uptimeHours = metrics.system && metrics.system.uptime_hours;
  const uptimeText =
    uptimeHours != null ? `<span class="metric-value">Uptime ${uptimeHours.toFixed(1)}h</span>` : "";
  let heatmap = "";
  if (metrics.cpu && Array.isArray(metrics.cpu.per_core_percent) && metrics.cpu.per_core_percent.length > 1) {
    heatmap = coreHeatmap(metrics.cpu.per_core_percent);
  }
  el.innerHTML = bars.join("") + heatmap + uptimeText;
}

// Per-core CPU heatmap: one cell per core, colored on a cool-to-hot gradient by load — a
// visual "receptor" for load distribution a single averaged bar can't show (e.g. one pegged
// core vs. even load across all of them look identical as a plain percentage).
function coreHeatmap(perCore) {
  const cells = perCore
    .map((pct) => `<span class="heatmap-cell" style="background:${heatColor(pct)}" title="${pct.toFixed(0)}%"></span>`)
    .join("");
  return `
    <div class="heatmap">
      <span class="heatmap-label">Cores</span>
      <span class="heatmap-cells">${cells}</span>
    </div>`;
}

// green (cool/idle) -> yellow -> red (hot/saturated), interpolated by load percent.
function heatColor(pct) {
  const p = Math.max(0, Math.min(100, Number(pct) || 0)) / 100;
  let r, g;
  if (p < 0.5) {
    r = Math.round(255 * (p / 0.5));
    g = 200;
  } else {
    r = 255;
    g = Math.round(200 * (1 - (p - 0.5) / 0.5));
  }
  return `rgb(${r},${g},60)`;
}

function metricBar(label, percent, unit) {
  const pct = Math.max(0, Math.min(100, Number(percent) || 0));
  const cls = pct >= 90 ? "metric-danger" : pct >= 75 ? "metric-warn" : "";
  return `
    <div class="metric">
      <span class="metric-label">${esc(label)}</span>
      <span class="metric-bar"><span class="metric-bar-fill ${cls}" style="width:${pct}%"></span></span>
      <span class="metric-value">${pct.toFixed(0)}${unit}</span>
    </div>`;
}

function populateToolNames(toolNames) {
  const sel = document.getElementById("audit-tool");
  if (!sel || !toolNames) return;
  const current = sel.value;
  const existing = new Set(Array.from(sel.options).map((o) => o.value));
  toolNames.forEach((name) => {
    if (!existing.has(name)) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      sel.appendChild(opt);
    }
  });
  sel.value = current;
}

function esc(s) {
  const div = document.createElement("div");
  div.textContent = s == null ? "" : String(s);
  return div.innerHTML;
}

function truncate(s, n) {
  s = s || "";
  return s.length > n ? s.slice(0, n) + "…" : s;
}

function badge(source) {
  const map = { voice: "\u{1F3A4}", text: "⌨", phone: "\u{1F4F1}", dashboard: "\u{1F5A5}" };
  return `<span class="src-badge">${map[source] || "•"} ${esc(source || "")}</span>`;
}

function statusPill(status) {
  return `<span class="pill pill-${esc(status || "unknown")}">${esc(status || "unknown")}</span>`;
}

function renderApproval(pending) {
  const el = document.getElementById("approval-queue");
  if (!pending) {
    el.innerHTML = '<span class="approval-empty">No pending confirmations</span>';
    return;
  }
  el.innerHTML = `
    <div class="approval-item">
      <span class="approval-badge">CONFIRMATION NEEDED</span>
      <span class="approval-reason">${esc(pending.tool_name)} would ${esc(pending.reason)}</span>
      <button class="btn btn-review" id="review-pending-btn">Review &rarr;</button>
    </div>`;
  const btn = document.getElementById("review-pending-btn");
  if (btn) btn.addEventListener("click", () => showPendingDetail(pending));
}

// Deliberately reached only via the "Review" button above, never a one-click action on the
// compact top bar itself — the user accepted (2026-09-18) that Approve may one-click-confirm
// even catastrophic-tier actions, on condition it only happens from this detail view.
function showPendingDetail(pending) {
  state.followedSessionId = null;
  location.hash = "#/sessions";
  const el = document.getElementById("detail-panel");
  el.innerHTML = `
    <div class="detail-card">
      <div class="detail-header">
        <span class="detail-title danger-text">Confirmation needed</span>
      </div>
      <p class="danger-text"><strong>${esc(pending.tool_name)}</strong> would ${esc(pending.reason)}.</p>
      <div>
        <p class="detail-section-label">Full input</p>
        <pre class="detail-code">${prettyCodeHtml(pending.tool_input)}</pre>
      </div>
      <div class="detail-actions">
        <button class="btn btn-danger" id="approve-btn">Approve &amp; Run</button>
        <button class="btn btn-ghost" id="reject-btn">Reject</button>
      </div>
      <p id="pending-action-status" class="muted"></p>
    </div>`;
  document.getElementById("approve-btn").addEventListener("click", () => actOnPending("approve"));
  document.getElementById("reject-btn").addEventListener("click", () => actOnPending("reject"));
}

async function actOnPending(action) {
  const statusEl = document.getElementById("pending-action-status");
  const approveBtn = document.getElementById("approve-btn");
  const rejectBtn = document.getElementById("reject-btn");
  if (approveBtn) approveBtn.disabled = true;
  if (rejectBtn) rejectBtn.disabled = true;
  if (statusEl) statusEl.textContent = action === "approve" ? "Approving…" : "Rejecting…";
  try {
    const res = await fetch(`/api/pending/${action}`, { method: "POST" });
    const data = await res.json();
    if (statusEl) statusEl.textContent = data.ok ? (data.reply || "Done.") : (data.error || "Failed.");
  } catch (e) {
    if (statusEl) statusEl.textContent = "Request failed: " + e;
  }
  fetchState();
}

// "Today" / "Yesterday" / a short date — so a long-running session log reads as organized
// history instead of one undifferentiated pile that just keeps growing.
function sessionDateLabel(isoStr) {
  if (!isoStr) return "Unknown";
  const d = new Date(isoStr);
  if (isNaN(d)) return "Unknown";
  const now = new Date();
  const startOfDay = (dt) => new Date(dt.getFullYear(), dt.getMonth(), dt.getDate());
  const diffDays = Math.round((startOfDay(now) - startOfDay(d)) / 86400000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  const opts = { month: "short", day: "numeric" };
  if (d.getFullYear() !== now.getFullYear()) opts.year = "numeric";
  return d.toLocaleDateString(undefined, opts);
}

function renderSessions(sessions) {
  const el = document.getElementById("sessions-list");
  el.innerHTML = "";
  let lastGroup = null;
  (sessions || []).forEach((s) => {
    const group = sessionDateLabel(s.started_at);
    if (group !== lastGroup) {
      const header = document.createElement("li");
      header.className = "session-group-header";
      header.textContent = group;
      el.appendChild(header);
      lastGroup = group;
    }
    const li = document.createElement("li");
    li.className = "list-item"
      + (s.status === "active" ? " active" : "")
      + (state.followedSessionId === s.id ? " followed" : "");
    li.innerHTML = `
      <div class="list-item-title">${badge(s.source)} ${esc(truncate(s.transcript, 60))}</div>
      <div class="list-item-meta">${statusPill(s.status)} &middot; ${esc(s.started_at || "")}</div>`;
    wireRowActivation(li, () => showDetail("session", s));
    el.appendChild(li);
  });
  if (!sessions || !sessions.length) el.innerHTML = '<li class="empty-state">No sessions yet.</li>';
}

document.getElementById("clear-sessions-btn").addEventListener("click", async () => {
  const btn = document.getElementById("clear-sessions-btn");
  btn.disabled = true;
  try {
    await fetch("/api/sessions/finished", { method: "DELETE" });
  } catch (e) {
    console.error("Clear finished sessions failed", e);
  }
  btn.disabled = false;
  fetchState();
});

function renderTasks(tasks) {
  const el = document.getElementById("tasks-list");
  el.innerHTML = "";
  (tasks || []).forEach((t) => {
    const li = document.createElement("li");
    li.className = "list-item";
    const progress = t.progress ? ` &middot; step ${esc(t.progress)}` : "";
    const stopBtn = t.stoppable
      ? `<button class="btn btn-stop" data-task-id="${esc(t.id)}">Stop</button>`
      : "";
    li.innerHTML = `
      <div class="list-item-title">${esc(truncate(t.description, 60))}</div>
      <div class="list-item-meta">${statusPill(t.status)} &middot; ${esc(t.kind || "")}${progress} &middot; ${esc(t.started_at || "")}</div>
      ${stopBtn}`;
    wireRowActivation(li, (e) => {
      if (e && e.target && e.target.closest && e.target.closest(".btn-stop")) return;
      showDetail("task", t);
    });
    const btn = li.querySelector(".btn-stop");
    if (btn) {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        btn.disabled = true;
        btn.textContent = "Stopping…";
        try {
          await fetch(`/api/tasks/${encodeURIComponent(t.id)}/stop`, { method: "POST" });
        } catch (err) {
          console.error("Stop failed", err);
        }
        fetchState();
      });
    }
    el.appendChild(li);
  });
  if (!tasks || !tasks.length) el.innerHTML = '<li class="empty-state">No tasks yet.</li>';
}

function renderActivity(audit) {
  const el = document.getElementById("activity-list");
  el.innerHTML = "";
  (audit || []).forEach((a) => {
    const li = document.createElement("li");
    li.className = "list-item compact";
    li.innerHTML = `<span class="ts">${esc(a.timestamp)}</span><span class="tool">${esc(a.tool_name)}</span><span class="muted">${esc(truncate(a.result_preview, 80))}</span>`;
    wireRowActivation(li, () => showDetail("audit", a));
    el.appendChild(li);
  });
  if (!audit || !audit.length) el.innerHTML = '<li class="empty-state">No activity yet.</li>';
}

function renderVictory(victoryLog, counts) {
  const countsEl = document.getElementById("victory-counts");
  if (counts) {
    countsEl.innerHTML = `
      <span class="count-chip">Today: ${counts.tasks_done_today ?? 0}</span>
      <span class="count-chip">This week: ${counts.tasks_done_week ?? 0}</span>
      <span class="count-chip warn">Failed today: ${counts.tasks_failed_today ?? 0}</span>`;
  }
  const el = document.getElementById("victory-list");
  el.innerHTML = "";
  (victoryLog || []).forEach((v) => {
    const li = document.createElement("li");
    li.className = "list-item compact";
    li.innerHTML = `<span class="ts">${esc(v.timestamp || "")}</span>${esc(v.text)}`;
    el.appendChild(li);
  });
  if (!victoryLog || !victoryLog.length) el.innerHTML = '<li class="empty-state">Nothing completed yet.</li>';
}

// Recursively renders a parsed JSON value as syntax-colored HTML text (not innerHTML on raw
// strings — every leaf goes through esc() first, so this is safe even for adversarial content
// like a tool_input containing "<script>").
function renderJsonValue(v, indent) {
  const pad = "  ".repeat(indent);
  const pad2 = "  ".repeat(indent + 1);
  if (v === null) return '<span class="json-null">null</span>';
  if (typeof v === "boolean") return `<span class="json-bool">${v}</span>`;
  if (typeof v === "number") return `<span class="json-number">${v}</span>`;
  if (typeof v === "string") return `<span class="json-string">${esc(JSON.stringify(v))}</span>`;
  if (Array.isArray(v)) {
    if (!v.length) return "[]";
    const items = v.map((item) => pad2 + renderJsonValue(item, indent + 1)).join(",\n");
    return `[\n${items}\n${pad}]`;
  }
  if (typeof v === "object") {
    const keys = Object.keys(v);
    if (!keys.length) return "{}";
    const items = keys
      .map(
        (k) =>
          `${pad2}<span class="json-key">${esc(JSON.stringify(k))}</span>: ${renderJsonValue(v[k], indent + 1)}`
      )
      .join(",\n");
    return `{\n${items}\n${pad}}`;
  }
  return esc(String(v));
}

// Pretty-prints `raw` as colored JSON if it parses as JSON; otherwise falls back to plain
// escaped text (most tool results are just strings, not JSON, and that's fine here too).
function prettyCodeHtml(raw) {
  if (raw == null || raw === "") return '<span class="muted">(none)</span>';
  if (typeof raw === "object") return renderJsonValue(raw, 0);
  try {
    return renderJsonValue(JSON.parse(raw), 0);
  } catch (e) {
    return esc(String(raw));
  }
}

// tabindex + click + Enter, so every clickable row (sessions/tasks/activity/audit) is also
// keyboard-reachable without duplicating the wiring at each call site.
function wireRowActivation(li, handler) {
  li.tabIndex = 0;
  li.addEventListener("click", handler);
  li.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handler();
    }
  });
}

// navigate=true (the default, for a direct user click) jumps to the owning route so the thing
// you just clicked is obviously visible. navigate=false (used for the live auto-open in
// handleLiveEvent/render()) only updates the panel's content and — via syncContextVisibility —
// reveals it if the route you're *already* on happens to have one, without yanking you away
// from wherever you're currently looking (see DASHBOARD.md, item 1's navigation write-up).
function showDetail(kind, item, opts) {
  const navigate = !opts || opts.navigate !== false;
  if (navigate && (kind === "session" || kind === "task")) {
    location.hash = kind === "session" ? "#/sessions" : "#/tasks";
  }
  const el = document.getElementById("detail-panel");
  if (kind === "session") {
    state.followedSessionId = item.id;
    el.innerHTML = `
      <div class="detail-card">
        <div class="detail-header">
          ${badge(item.source)}
          <span class="detail-title">Session #${esc(item.id)}</span>
          <span class="detail-timestamp">${esc(item.started_at)} &rarr; ${esc(item.ended_at || "active")}</span>
        </div>
        <div class="detail-row"><span class="detail-row-label">Status</span>${statusPill(item.status)}</div>
        <div>
          <p class="detail-section-label">Transcript</p>
          <blockquote class="detail-quote">${esc(item.transcript)}</blockquote>
        </div>
        <div>
          <p class="detail-section-label">Reply</p>
          <pre class="detail-code">${item.reply ? esc(item.reply) : '<span class="muted">Waiting for a reply&hellip;</span>'}</pre>
        </div>
      </div>`;
  } else if (kind === "task") {
    state.followedSessionId = null;
    el.innerHTML = `
      <div class="detail-card">
        <div class="detail-header">
          <span class="detail-title">${esc(truncate(item.description, 70))}</span>
          <span class="detail-timestamp">${esc(item.started_at || "")} &rarr; ${esc(item.finished_at || "running")}</span>
        </div>
        <div class="detail-row"><span class="detail-row-label">Status</span>${statusPill(item.status)}</div>
        <div class="detail-row"><span class="detail-row-label">Kind</span><span>${esc(item.kind || "")}${item.progress ? ` &middot; step ${esc(item.progress)}` : ""}</span></div>
        <div>
          <p class="detail-section-label">Result</p>
          <pre class="detail-code">${item.result_summary ? esc(item.result_summary) : '<span class="muted">(none yet)</span>'}</pre>
        </div>
      </div>`;
  } else if (kind === "audit") {
    state.followedSessionId = null;
    const fromTranscript = item.transcript
      ? `<blockquote class="detail-quote">${esc(truncate(item.transcript, 200))}</blockquote>`
      : "";
    // Same exact-transcript join the backend already documents for Audit <-> Sessions (no
    // session_id column needed — handle_text_command passes the identical transcript string
    // into both dashboard_sessions and every audit row for that turn).
    const linkedSession = item.transcript
      ? (state.data && state.data.sessions || []).find((s) => s.transcript === item.transcript)
      : null;
    const sessionLink = linkedSession
      ? `<button class="btn btn-small" id="audit-view-session-btn">View session #${esc(linkedSession.id)} &rarr;</button>`
      : "";
    el.innerHTML = `
      <div class="detail-card">
        <div class="detail-header">
          <span class="detail-title">${esc(item.tool_name)}</span>
          <span class="detail-timestamp">${esc(item.timestamp)}</span>
        </div>
        ${fromTranscript}
        <div>
          <p class="detail-section-label">Input</p>
          <pre class="detail-code">${prettyCodeHtml(item.tool_input)}</pre>
        </div>
        <div>
          <p class="detail-section-label">Result</p>
          <pre class="detail-code">${prettyCodeHtml(item.result)}</pre>
        </div>
        ${sessionLink}
      </div>`;
    if (linkedSession) {
      document.getElementById("audit-view-session-btn").addEventListener("click", () => showDetail("session", linkedSession));
    }
  }
  syncContextVisibility();
}

async function fetchAuditResults() {
  const el = document.getElementById("audit-list");
  const params = new URLSearchParams();
  const dateFrom = document.getElementById("audit-date-from").value;
  const dateTo = document.getElementById("audit-date-to").value;
  const tool = document.getElementById("audit-tool").value;
  const q = document.getElementById("audit-q").value.trim();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo + "T23:59:59");
  if (tool) params.set("tool_name", tool);
  if (q) params.set("q", q);
  try {
    const res = await fetch(`/api/audit?${params.toString()}`);
    const data = await res.json();
    renderAuditResults(data.rows || []);
  } catch (e) {
    el.innerHTML = '<li class="empty-state">Failed to load audit trail.</li>';
  }
}

function renderAuditResults(rows) {
  const el = document.getElementById("audit-list");
  el.innerHTML = "";
  rows.forEach((a) => {
    const li = document.createElement("li");
    li.className = "list-item compact";
    li.innerHTML = `<span class="ts">${esc(a.timestamp)}</span><span class="tool">${esc(a.tool_name)}</span><span class="muted">${esc(truncate(a.result_preview, 80))}</span>`;
    wireRowActivation(li, () => showDetail("audit", a));
    el.appendChild(li);
  });
  if (!rows.length) el.innerHTML = '<li class="empty-state">No matching actions.</li>';
}

// Recurring skills + recurring reminders — kept as its own route rather than folded into Tasks,
// since these are standing routines, not one-off/in-flight work.
async function fetchDailyItems() {
  const el = document.getElementById("daily-list");
  try {
    const res = await fetch("/api/daily");
    const data = await res.json();
    renderDailyItems(data.items || []);
  } catch (e) {
    el.innerHTML = '<li class="empty-state">Failed to load daily items.</li>';
  }
}

function renderDailyItems(items) {
  const el = document.getElementById("daily-list");
  el.innerHTML = "";
  items.forEach((item) => {
    const li = document.createElement("li");
    li.className = "list-item compact";
    const kindIcon = item.kind === "reminder" ? "⏰" : "\u{1F501}";
    const lastRun = item.last_run_at ? `last ran ${esc(item.last_run_at)}` : "";
    const nextDue = item.next_due ? `next ${esc(item.next_due)}` : "";
    const meta = [esc(item.schedule || ""), lastRun, nextDue].filter(Boolean).join(" &middot; ");
    li.innerHTML = `
      <div class="list-item-title">${kindIcon} ${esc(item.name)}</div>
      <div class="list-item-meta">${meta}</div>`;
    el.appendChild(li);
  });
  if (!items.length) el.innerHTML = '<li class="empty-state">No recurring skills or reminders yet.</li>';
}

// Local Claude-spend estimate (GET /api/usage): every API call's token usage x list price,
// tracked by Jarvis itself — no admin key. Shown as a top-bar chip (refreshed every minute) and a
// Usage route (refreshed when opened and every 30s while it's the active route).
let lastUsage = null;

function fmtUsd(n) {
  n = Number(n) || 0;
  return "$" + (n < 1 ? n.toFixed(3) : n.toFixed(2));
}

async function fetchUsage() {
  try {
    const res = await fetch("/api/usage");
    const data = await res.json();
    lastUsage = data.usage;
    renderUsage(data.usage);
  } catch (e) {
    /* leave the last render in place */
  }
}

function renderUsage(u) {
  const chip = document.getElementById("spend-chip");
  if (!u) {
    chip.textContent = "$– today";
    return;
  }
  const p = u.periods;
  chip.textContent = `${fmtUsd(p.today.cost_usd)} today`;
  const cards = [
    ["Today", p.today], ["7 days", p.week], ["This month", p.month], ["All time", p.all_time],
  ].map(([label, d]) => `<div class="usage-card"><div class="usage-card-label">${esc(label)}</div>
      <div class="usage-card-value">${esc(fmtUsd(d.cost_usd))}</div>
      <div class="muted">${esc(String(d.calls))} calls</div></div>`);
  cards.push(`<div class="usage-card usage-card-good"><div class="usage-card-label">Saved by caching (month)</div>
      <div class="usage-card-value">${esc(fmtUsd(p.month.cache_saved_usd))}</div>
      <div class="muted">${esc(String(p.month.cache_read_tokens.toLocaleString()))} tokens read from cache</div></div>`);
  document.getElementById("usage-cards").innerHTML = cards.join("");

  const max = Math.max(0.0001, ...u.daily.map((d) => d.cost_usd));
  document.getElementById("usage-chart").innerHTML = u.daily
    .map((d) => {
      const h = Math.max(2, Math.round((d.cost_usd / max) * 100));
      return `<div class="usage-bar-col" title="${esc(d.date)}: ${esc(fmtUsd(d.cost_usd))}">
        <div class="usage-bar" style="height:${h}%"></div><div class="usage-bar-label">${esc(d.date.slice(8))}</div></div>`;
    })
    .join("");

  const models = document.getElementById("usage-models");
  models.innerHTML = u.by_model.length
    ? u.by_model
        .map((m) => `<li class="list-item compact"><span class="tool">${esc(m.model)}</span>
          <span class="muted">${esc(fmtUsd(m.cost_usd))} this month &middot; ${esc(String(m.calls))} calls &middot; ${esc(Number(m.tokens || 0).toLocaleString())} tokens</span></li>`)
        .join("")
    : '<li class="empty-state">No usage recorded yet.</li>';
  const extra = u.unknown_price_models.length
    ? ` Approximate pricing used for: ${u.unknown_price_models.join(", ")}.`
    : "";
  document.getElementById("usage-note").textContent = u.estimate_note + extra;

  document.getElementById("usage-tokens").innerHTML = [
    ["Today", p.today], ["7 days", p.week], ["This month", p.month], ["All time", p.all_time],
  ].map(([label, d]) => `<div class="usage-token-card">
      <div class="usage-card-label">${esc(label)}</div>
      <div class="usage-token-row"><span>Input</span><span>${esc(Number(d.input_tokens || 0).toLocaleString())}</span></div>
      <div class="usage-token-row"><span>Cache read</span><span>${esc(Number(d.cache_read_tokens || 0).toLocaleString())}</span></div>
      <div class="usage-token-row"><span>Cache write</span><span>${esc(Number(d.cache_write_tokens || 0).toLocaleString())}</span></div>
      <div class="usage-token-row"><span>Output</span><span>${esc(Number(d.output_tokens || 0).toLocaleString())}</span></div>
      <div class="usage-token-row"><span>Saved by caching</span><span>${esc(fmtUsd(d.cache_saved_usd))}</span></div>
    </div>`).join("");
}

// Brain switch (Claude <-> Gemini): the chip shows the active provider; clicking switches to the
// other one after a confirmation (Gemini's free tier may use prompts to improve Google products).
let currentLlm = null;

function renderLlm(llm) {
  const chip = document.getElementById("llm-chip");
  if (!llm) {
    chip.textContent = "brain: ?";
    return;
  }
  currentLlm = llm;
  const model = llm.provider === "gemini" ? llm.gemini_model : llm.claude_model;
  chip.textContent = `brain: ${llm.provider}`;
  chip.title = `Model: ${model}. Click to switch to ${llm.provider === "gemini" ? "Claude" : "Gemini"}.`;
  chip.classList.toggle("llm-gemini", llm.provider === "gemini");
}

async function fetchLlm() {
  try {
    const res = await fetch("/api/llm");
    renderLlm((await res.json()).llm);
  } catch (e) {
    /* keep the last render */
  }
}

document.getElementById("llm-chip").addEventListener("click", async () => {
  if (!currentLlm) return;
  const target = currentLlm.provider === "gemini" ? "claude" : "gemini";
  if (target === "gemini" && !window.confirm(
    "Switch Jarvis's brain to Gemini?\n\nOn Google's free tier, your prompts and tool results " +
    "(emails, screen contents, shell output) may be used by Google to improve its products."
  )) return;
  try {
    const res = await fetch("/api/llm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: target }),
    });
    const data = await res.json();
    if (data.llm) renderLlm(data.llm);
    if (!data.ok) window.alert(data.message || "Couldn't switch.");
  } catch (e) {
    window.alert("Couldn't switch the brain.");
  }
});
fetchLlm();
setInterval(fetchLlm, 60000);

document.getElementById("spend-chip").addEventListener("click", () => {
  location.hash = "#/usage";
});
fetchUsage();
setInterval(fetchUsage, 60000);
setInterval(() => { if (isRouteActive("usage")) fetchUsage(); }, 30000);

// Light background polls just for Home's "Recent autonomy activity" / "Presence" cards — reuse
// the existing /api/autonomy and /api/faces endpoints (no new backend route). Slower cadence
// than their own routes' polling since Home only needs a glance, not a live feed.
let lastAutonomy = null;
let homePresence = null;

async function fetchAutonomySummary() {
  try {
    const res = await fetch("/api/autonomy");
    lastAutonomy = await res.json();
    if (isRouteActive("home")) renderHome();
  } catch (e) {
    /* keep last render */
  }
}

async function fetchHomePresence() {
  try {
    const res = await fetch("/api/faces");
    const data = await res.json();
    homePresence = data.enabled ? data : null;
    if (isRouteActive("home")) renderHome();
  } catch (e) {
    /* keep last render */
  }
}

fetchAutonomySummary();
fetchHomePresence();
setInterval(fetchAutonomySummary, 30000);
setInterval(fetchHomePresence, 30000);

document.getElementById("audit-apply-btn").addEventListener("click", fetchAuditResults);
document.getElementById("audit-clear-btn").addEventListener("click", () => {
  document.getElementById("audit-date-from").value = "";
  document.getElementById("audit-date-to").value = "";
  document.getElementById("audit-tool").value = "";
  document.getElementById("audit-q").value = "";
  fetchAuditResults();
});
document.getElementById("audit-q").addEventListener("keydown", (e) => {
  if (e.key === "Enter") fetchAuditResults();
});

// Compose box: a dashboard-typed command is a 4th input surface alongside voice/text-hotkey/
// phone. It goes through the exact same handle_text_command pipeline server-side (see
// jarvis.py's main()), including the confirmation gate — this box has no special privileges.
// Wired to both the Sessions route's form and the Home route's form (same endpoint, same code).
function wireComposeForm(formId, inputId, statusId) {
  const form = document.getElementById(formId);
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = document.getElementById(inputId);
    const statusEl = document.getElementById(statusId);
    const text = input.value.trim();
    if (!text) return;
    input.disabled = true;
    statusEl.textContent = "Sending…";
    try {
      const res = await fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const data = await res.json();
      statusEl.textContent = data.ok ? "Sent — watch Sessions for the reply." : (data.error || "Failed.");
      if (data.ok) input.value = "";
    } catch (err) {
      statusEl.textContent = "Request failed: " + err;
    }
    input.disabled = false;
    input.focus();
  });
}
wireComposeForm("compose-form", "compose-input", "compose-status");
wireComposeForm("home-compose-form", "home-compose-input", "home-compose-status");

function slugStatus(status) {
  return String(status || "unknown").toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

async function loadServices() {
  const panel = document.getElementById("services-panel");
  panel.innerHTML = '<p class="muted">Loading&hellip;</p>';
  try {
    const res = await fetch("/api/services");
    const data = await res.json();
    const services = data.services || [];
    if (!services.length) {
      panel.innerHTML = '<p class="muted">No services configured.</p>';
      return;
    }
    panel.innerHTML = services
      .map(
        (s) => `
      <div class="service-row">
        <span class="service-dot status-${slugStatus(s.status)}"></span>
        <span class="service-name">${esc(s.name)}</span>
        <span class="service-detail">${esc(s.detail || s.status)}</span>
      </div>`
      )
      .join("");
  } catch (e) {
    panel.innerHTML = '<p class="muted">Failed to load services.</p>';
  }
}

const servicesPanel = document.getElementById("services-panel");
const servicesToggleBtn = document.getElementById("services-toggle-btn");
servicesToggleBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  const willOpen = servicesPanel.classList.contains("hidden");
  servicesPanel.classList.toggle("hidden");
  if (willOpen) loadServices();
});
document.addEventListener("click", (e) => {
  if (!servicesPanel.classList.contains("hidden") && !e.target.closest(".services-dropdown")) {
    servicesPanel.classList.add("hidden");
  }
});

// When a new voice-originated session starts, open/focus it in the Detail panel so a complex
// task kicked off by voice elsewhere in the room is immediately visible here too.
// Any new command — voice, text (typed hotkey), or a dashboard Send — auto-opens the detail
// panel with that session the instant it starts, transcript first and the reply filled in as
// soon as it lands (session_end below, and render()'s poll-driven re-sync as a backstop for
// anything in between). Deliberately excludes "phone": those are meant to stay in the
// background, not grab dashboard focus for a remote command nobody's watching for.
// navigate:false on purpose (see showDetail's docstring) — a background command starting
// shouldn't yank you off whatever route you're already looking at; it only updates the panel
// and reveals it if the current route already has one.
const AUTO_OPEN_SOURCES = new Set(["voice", "text", "dashboard"]);

function handleLiveEvent(event) {
  if (!event || !event.type) return;
  if (event.type === "session_start" && event.data && AUTO_OPEN_SOURCES.has(event.data.source)) {
    showDetail("session", {
      id: event.data.id,
      source: event.data.source,
      transcript: event.data.transcript,
      status: "active",
      reply: null,
      started_at: new Date().toISOString(),
      ended_at: null,
    }, { navigate: false });
  } else if (event.type === "session_end" && event.data && event.data.id === state.followedSessionId) {
    const d = state.data;
    const found = d && d.sessions && d.sessions.find((s) => s.id === event.data.id);
    if (found) showDetail("session", found, { navigate: false });
  }
}

function connectWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  const statusEl = document.getElementById("conn-status");
  ws.onopen = () => {
    statusEl.textContent = "live";
    statusEl.classList.remove("offline");
  };
  ws.onclose = () => {
    statusEl.textContent = "reconnecting…";
    statusEl.classList.add("offline");
    setTimeout(connectWs, 2000);
  };
  ws.onerror = () => ws.close();
  ws.onmessage = async (msg) => {
    let event = null;
    try {
      event = JSON.parse(msg.data);
    } catch (e) {
      // non-JSON message; ignore
    }
    if (event && event.type === "session_start") handleLiveEvent(event);
    await fetchState();
    if (event && event.type === "session_end") handleLiveEvent(event);
    if (isRouteActive("audit")) fetchAuditResults();
    if (event && event.type === "face_event" && isRouteActive("identity")) fetchIdentity();
    if (event && event.type === "autonomy_update" && window.refreshAutonomy) window.refreshAutonomy();
  };
}

renderRoute();
fetchState();
connectWs();
setInterval(fetchState, 15000);


// Sleep route (GET /api/sleep): trends from Sleep Mode's own log. Week/Month toggle re-slices
// the 90 days already fetched, no extra request.
let sleepData = null;
let sleepRange = 7;

function fmtHours(h) {
  if (h == null) return "–";
  const m = Math.round(h * 60);
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
}

function sleepDelta(cur, prev, unit) {
  if (cur == null || prev == null) return "";
  const d = cur - prev;
  if (Math.abs(d) < 0.05) return '<div class="usage-delta muted">same as before</div>';
  const cls = d > 0 ? "up" : "down";
  return `<div class="usage-delta ${cls}">${d > 0 ? "▲" : "▼"} ${fmtHours(Math.abs(d))} vs prior ${unit}</div>`;
}

async function fetchSleep() {
  try {
    const res = await fetch("/api/sleep");
    const data = await res.json();
    sleepData = data.sleep;
    renderSleep();
  } catch (e) {
    /* keep last render */
  }
}

// labelFn(d, i) -> x-axis label or "" to skip.
function sleepBarsSvg(days, goal, labelFn) {
  const W = 420, H = 170, L = 26, B = 16, T = 8;
  const vals = days.map((d) => (d.hours || 0) + (d.nap_hours || 0));
  const max = Math.max(goal + 1, ...vals, 1);
  const y = (h) => T + (H - T - B) * (1 - h / max);
  const slot = (W - L) / days.length;
  const bw = Math.max(2, slot - 2);
  let out = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Hours slept">`;
  for (let h = 0; h <= max; h += 2) {
    out += `<line class="grid" x1="${L}" x2="${W}" y1="${y(h)}" y2="${y(h)}"/><text class="ax" x="${L - 4}" y="${y(h) + 3}" text-anchor="end">${h}</text>`;
  }
  days.forEach((d, i) => {
    const x = L + i * slot + (slot - bw) / 2;
    const r = Math.min(3, bw / 2);
    // Rounded-top bar from `from` (px) up to `top` (px).
    const seg = (cls, from, top, tip) =>
      `<path class="bar ${cls}" d="M${x},${from} V${top + r} Q${x},${top} ${x + r},${top} H${x + bw - r} Q${x + bw},${top} ${x + bw},${top + r} V${from} Z"><title>${esc(tip)}</title></path>`;
    let base = H - B;
    if (d.hours != null) {
      const top = y(d.hours);
      out += seg(d.hours >= goal ? "" : "bar-low", base, top, `${d.date}: ${fmtHours(d.hours)}${d.sessions > 1 ? " (" + d.sessions + " sessions)" : ""}`);
      base = top - 2; // 2px gap between the night and nap segments
    }
    if (d.nap_hours != null) {
      const top = Math.min(y((d.hours || 0) + d.nap_hours), base - 3);
      out += seg("bar-nap", base, top, `${d.date}: ${d.naps} nap${d.naps > 1 ? "s" : ""}, ${fmtHours(d.nap_hours)}`);
    }
    const lab = labelFn(d, i);
    if (lab) out += `<text class="ax" x="${x + bw / 2}" y="${H - 4}" text-anchor="middle">${esc(lab)}</text>`;
  });
  out += `<line class="goal" x1="${L}" x2="${W}" y1="${y(goal)}" y2="${y(goal)}"/></svg>`;
  return out;
}

function sleepTimesSvg(days) {
  const W = 420, H = 170, L = 34, B = 16, T = 8;
  // Minutes since 18:00; bedtime and wake share one clock axis from 18:00 to 12:00 next day.
  const hi = 18 * 60;
  const y = (m) => T + (H - T - B) * (m / hi);
  const slot = (W - L) / days.length;
  const pts = (key, conv) =>
    days.map((d, i) => (d[key] == null ? null : [L + i * slot + slot / 2, y(conv(d[key])), d])).filter(Boolean);
  const bed = pts("bed_min", (m) => m);
  const wake = pts("wake_min", (m) => (m - 18 * 60 + 1440) % 1440);
  let out = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Bedtime and wake time per night">`;
  for (let m = 0; m <= hi; m += 180) {
    const clock = String(((18 * 60 + m) / 60) % 24).padStart(2, "0") + ":00";
    out += `<line class="grid" x1="${L}" x2="${W}" y1="${y(m)}" y2="${y(m)}"/><text class="ax" x="${L - 4}" y="${y(m) + 3}" text-anchor="end">${clock}</text>`;
  }
  const line = (arr, cls) => (arr.length > 1 ? `<polyline class="${cls}" points="${arr.map((p) => p[0] + "," + p[1]).join(" ")}"/>` : "");
  out += line(bed, "line-bed") + line(wake, "line-wake");
  bed.forEach((p) => (out += `<circle class="dot-bed" cx="${p[0]}" cy="${p[1]}" r="4"><title>${esc(p[2].date)}: bed ${esc(p[2].bedtime)}</title></circle>`));
  wake.forEach((p) => (out += `<circle class="dot-wake" cx="${p[0]}" cy="${p[1]}" r="4"><title>${esc(p[2].date)}: up ${esc(p[2].wake)}</title></circle>`));
  return out + "</svg>";
}

function renderSleep() {
  const u = sleepData;
  const cards = document.getElementById("sleep-cards");
  if (!u) {
    cards.innerHTML = '<div class="muted">Sleep data unavailable.</div>';
    return;
  }
  const isWeek = sleepRange === 7;
  const cur = isWeek ? u.week : u.month;
  const prev = isWeek ? u.prev_week : u.prev_month;
  const unit = isWeek ? "week" : "month";
  const last = [...u.daily].reverse().find((d) => d.hours != null);
  const c = [
    ["Last night", last ? fmtHours(last.hours) : "–", last ? `${esc(last.bedtime)} → ${esc(last.wake)}` : "no data yet", ""],
    [`Average (${isWeek ? "7" : "30"} days)`, fmtHours(cur.avg_hours), `${cur.nights_tracked} nights tracked`, sleepDelta(cur.avg_hours, prev.avg_hours, unit)],
    ["Best / worst", fmtHours(cur.best_hours), `worst ${fmtHours(cur.worst_hours)}`, ""],
    ["Avg bedtime → wake", `${cur.avg_bedtime || "–"} → ${cur.avg_wake || "–"}`, cur.bedtime_variability_min != null ? `bedtime varies ±${cur.bedtime_variability_min} min` : "", ""],
    [`Goal (${u.goal_hours}h)`, `${cur.goal_hit_nights}/${cur.nights_tracked}`, `${u.goal_streak_nights}-night streak`, ""],
    [`Goal hit rate`, cur.nights_tracked ? `${Math.round((cur.goal_hit_nights / cur.nights_tracked) * 100)}%` : "–", `${unit} so far`, ""],
    ["Sleep debt", `${cur.debt_hours}h`, `vs ${u.goal_hours}h/night`, ""],
    [`Total sleep (${unit})`, fmtHours(cur.total_hours), `over ${cur.nights_tracked} tracked nights`, ""],
    ["Naps", cur.nap_count ? `${cur.nap_count}` : "0", cur.nap_count ? `avg ${cur.nap_avg_minutes} min &middot; ${fmtHours(cur.nap_total_hours)} total` : `none yet (say "nap mode")`, ""],
  ];
  cards.innerHTML = c
    .map(([label, val, sub, delta]) => `<div class="usage-card"><div class="usage-card-label">${esc(label)}</div>
      <div class="usage-card-value">${esc(val)}</div><div class="muted">${sub}</div>${delta}</div>`)
    .join("");

  const days = u.daily.slice(-sleepRange);
  const dow = (d) => ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][new Date(d.date + "T12:00").getDay()];
  const labelFn = (d, i) =>
    days.length <= 7 ? dow(d) : i % 5 === 0 || i === days.length - 1 ? d.date.slice(8) : "";
  document.getElementById("sleep-hours").innerHTML = sleepBarsSvg(days, u.goal_hours, labelFn);
  document.getElementById("sleep-times").innerHTML = sleepTimesSvg(days);
  const wd = u.weekday.map((w) => ({ date: w.day, hours: w.avg_hours, sessions: 0 }));
  document.getElementById("sleep-weekday").innerHTML = sleepBarsSvg(wd, u.goal_hours, (d) => d.date);

  document.getElementById("sleep-current").textContent = u.current
    ? `Sleep Mode is on (${u.current.is_nap ? "nap" : "night"}) — ${fmtHours(u.current.elapsed_minutes / 60)} so far`
    : "Sleep Mode is off";
  document.getElementById("sleep-digests").innerHTML = u.digests.length
    ? u.digests
        .map((d) => `<li class="list-item compact"><span class="muted">${esc(d.ended_at.replace("T", " ").slice(0, 16))}</span> ${esc(d.digest)}</li>`)
        .join("")
    : '<li class="empty-state">No wake-up recaps yet. One is saved each time Sleep Mode ends.</li>';
  document.getElementById("sleep-note").textContent = u.note;
}

document.querySelectorAll(".seg-btn").forEach((b) =>
  b.addEventListener("click", () => {
    document.querySelectorAll(".seg-btn").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    sleepRange = Number(b.dataset.range);
    renderSleep();
  })
);
fetchSleep();
setInterval(fetchSleep, 60000);


// Identity route (GET /api/faces*): who the camera sees, the enrolled profile and its consent
// summary, pictures of unknown visitors, and the recognition event stream. Pictures are only put
// in the page while this route is open (an <img> loads the moment it is in the DOM), and the
// server never sends face vectors at all.
let identityState = null;

const IDENTITY_KIND_LABELS = {
  owner_arrived: "arrived", owner_left: "left", unknown_seen: "unknown person", unknown_left: "unknown left",
  camera_covered: "camera covered", camera_uncovered: "camera uncovered", camera_unreachable: "camera unreachable",
  camera_restored: "camera back", enroll: "enrolled", enroll_failed: "enroll failed", delete: "erased",
  paused: "paused", resumed: "resumed", export: "exported", snapshots_deleted: "pictures deleted",
};

function identityKindLabel(k) {
  return IDENTITY_KIND_LABELS[k] || k;
}

async function fetchIdentity() {
  try {
    const res = await fetch("/api/faces");
    identityState = await res.json();
    renderIdentity();
    if (identityState.enabled) {
      await Promise.all([fetchIdentityEvents(), fetchIdentitySnaps()]);
    }
  } catch (e) {
    /* leave the last render in place */
  }
}

async function fetchIdentityEvents() {
  const kind = document.getElementById("identity-kind").value;
  try {
    const res = await fetch("/api/faces/events?limit=100" + (kind ? "&kind=" + encodeURIComponent(kind) : ""));
    const data = await res.json();
    document.getElementById("identity-events").innerHTML = data.rows.length
      ? data.rows
          .map((r) => {
            const conf = r.confidence == null ? "" : ` &middot; ${esc(Math.round(r.confidence * 100) + "%")}`;
            const who = r.name ? ` &middot; ${esc(r.name)}` : "";
            const detail = r.detail ? ` &middot; ${esc(r.detail)}` : "";
            return `<li class="list-item compact"><span class="tool">${esc(identityKindLabel(r.kind))}</span>
              <span class="muted">${esc(r.ts.replace("T", " "))}${who}${conf}${detail}</span></li>`;
          })
          .join("")
      : '<li class="empty-state">No recognition events yet.</li>';
  } catch (e) {
    /* keep last render */
  }
}

async function fetchIdentitySnaps() {
  try {
    const res = await fetch("/api/faces/snapshots");
    const data = await res.json();
    const box = document.getElementById("identity-snaps");
    document.getElementById("identity-snap-count").textContent = data.rows.length ? `(${data.rows.length})` : "";
    document.getElementById("identity-snap-delete").hidden = !data.rows.length;
    if (!isRouteActive("identity")) return; // never load pictures into a hidden route
    box.innerHTML = data.rows.length
      ? data.rows
          .map(
            (r) => `<figure class="snap"><img loading="lazy" alt="Unknown visitor" src="/api/faces/snapshots/${Number(r.id)}/image">
              <figcaption>${esc(r.ts.replace("T", " ").slice(5, 16))}<br>${esc(Math.round((r.confidence || 0) * 100) + "% like you")}</figcaption></figure>`
          )
          .join("")
      : '<span class="muted">No pictures saved. They are only kept for unrecognized faces, expire after 14 days, and never leave this computer.</span>';
  } catch (e) {
    /* keep last render */
  }
}

function identityPresenceText(st) {
  if (identityState.paused) return "Paused — the camera is off";
  if (st.camera_unreachable) return "Camera unreachable";
  if (st.camera_covered) return "Camera covered";
  const bits = [];
  if (st.owner_present) bits.push(`${st.owner_name} is here` + (st.owner_confidence ? ` (${Math.round(st.owner_confidence * 100)}%)` : ""));
  if (st.unknown_present) bits.push("someone unrecognized is in view");
  return bits.length ? bits.join(" · ") : "Nobody in view";
}

function renderIdentity() {
  const s = identityState;
  const cards = document.getElementById("identity-cards");
  const pauseBtn = document.getElementById("identity-pause-btn");
  if (!s || !s.enabled) {
    cards.innerHTML = '<div class="muted">Face recognition is off. Set JARVIS_FACE_ENABLED=1 and restart Jarvis to use it.</div>';
    document.getElementById("identity-status").textContent = "";
    document.getElementById("identity-profile").innerHTML = "";
    document.getElementById("identity-snaps").innerHTML = "";
    document.getElementById("identity-events").innerHTML = "";
    pauseBtn.hidden = true;
    document.getElementById("identity-snap-delete").hidden = true;
    return;
  }
  const st = s.presence;
  const cfg = s.settings;
  document.getElementById("identity-status").textContent = s.paused ? "Camera paused" : s.polling ? "Watching (low duty)" : "Not watching";
  pauseBtn.hidden = false;
  pauseBtn.textContent = s.paused ? "Resume camera" : "Pause camera";
  const awayBtn = document.getElementById("identity-away-btn");
  awayBtn.hidden = !s.profiles.length;
  awayBtn.textContent = s.away.enabled ? "Away mode: ON" : "Away mode: off";
  awayBtn.classList.toggle("btn-danger", !!s.away.enabled);
  const cardHtml = (label, value, sub) =>
    `<div class="usage-card"><div class="usage-card-label">${esc(label)}</div><div class="usage-card-value id-value">${esc(value)}</div><div class="muted">${esc(sub || "")}</div></div>`;
  cards.innerHTML = [
    cardHtml("Right now", identityPresenceText(st), `looks every ${cfg.poll_seconds}s (${cfg.settled_poll_seconds}s once settled)`),
    cardHtml("Enrolled", String(s.profiles.length), s.profiles.length ? s.profiles.map((p) => p.name).join(", ") : "say “enroll me as …”"),
    cardHtml("Unknown pictures", String(s.snapshot_count), cfg.save_unknown_pictures ? `kept ${cfg.picture_keep_days} days` : "saving is off"),
    cardHtml("Away mode", s.away.enabled ? "On" : "Off",
      s.away.enabled ? `locks after ${s.away.grace_seconds}s unseen` + (s.away.absent_seconds ? ` (unseen ${s.away.absent_seconds}s)` : "") : "locks the PC if you're not seen"),
    cardHtml("Match threshold", String(cfg.match_threshold), "higher = stricter"),
  ].join("");

  document.getElementById("identity-profile").innerHTML = s.profiles
    .map((p) => {
      const c = p.consent;
      const li = (arr) => arr.map((x) => `<li>${esc(x)}</li>`).join("");
      return `<div class="profile-box">
        <div class="profile-row"><strong>${esc(p.name)}</strong> <span class="pill">${esc(p.role)}</span>
          <span class="muted">enrolled ${esc(p.created_at.replace("T", " "))} &middot; consent given ${esc(c.consent_given_at.replace("T", " "))}</span>
          <span class="profile-actions">
            <a class="btn btn-small" href="/api/faces/${Number(p.id)}/export" download>Export my data</a>
            <button class="btn btn-small btn-danger" data-erase="${Number(p.id)}" data-name="${esc(p.name)}">Erase profile</button>
          </span></div>
        <div class="consent-cols">
          <div><div class="muted">Stored</div><ul class="consent-list">${li(c.stored)}</ul></div>
          <div><div class="muted">Never stored</div><ul class="consent-list">${li(c.never_stored)}</ul></div>
          <div><div class="muted">Who can read it</div><p class="consent-list">${esc(c.who_can_read_it)}</p>
            <div class="muted">How consent was given</div><p class="consent-list">${esc(c.how)}</p></div>
        </div></div>`;
    })
    .join("");

  const kindSel = document.getElementById("identity-kind");
  const current = kindSel.value;
  kindSel.innerHTML =
    '<option value="">All events</option>' +
    s.event_kinds.map((k) => `<option value="${esc(k)}">${esc(identityKindLabel(k))}</option>`).join("");
  kindSel.value = s.event_kinds.includes(current) ? current : "";
  const note = document.getElementById("identity-note");
  note.textContent = s.problem
    ? "Problem: " + s.problem
    : "A face only personalizes Jarvis — it never approves or unlocks anything. Everything here stays on this computer.";
  note.classList.toggle("danger-text", !!s.problem);
}

document.getElementById("identity-profile").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-erase]");
  if (!btn) return;
  if (!confirm(`Erase ${btn.dataset.name}'s face profile? Jarvis will stop recognizing them. This can't be undone, but you can enroll again.`)) return;
  try {
    const res = await fetch(`/api/faces/${btn.dataset.erase}?confirm=true`, { method: "DELETE" });
    const data = await res.json();
    if (!data.ok) alert(data.message || data.error || "Couldn't erase that profile.");
  } catch (err) {
    alert("Couldn't reach Jarvis.");
  }
  fetchIdentity();
});

document.getElementById("identity-snap-delete").addEventListener("click", async () => {
  if (!confirm("Delete every saved picture of unknown visitors? This can't be undone.")) return;
  try {
    await fetch("/api/faces/snapshots", { method: "DELETE" });
  } catch (err) {
    alert("Couldn't reach Jarvis.");
  }
  fetchIdentity();
});

document.getElementById("identity-pause-btn").addEventListener("click", async () => {
  try {
    await fetch("/api/faces/pause", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paused: !(identityState && identityState.paused) }),
    });
  } catch (err) {
    alert("Couldn't reach Jarvis.");
  }
  fetchIdentity();
});

document.getElementById("identity-away-btn").addEventListener("click", async () => {
  const turningOn = !(identityState && identityState.away && identityState.away.enabled);
  if (turningOn && !confirm("Turn away mode on? If Jarvis can't see you for a couple of minutes it will LOCK this computer (with a spoken warning first).")) return;
  try {
    const res = await fetch("/api/faces/away", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: turningOn }),
    });
    const data = await res.json();
    if (data.message && Boolean(data.away) !== turningOn) alert(data.message);  // e.g. "Enroll your face first"
  } catch (err) {
    alert("Couldn't reach Jarvis.");
  }
  fetchIdentity();
});

document.getElementById("identity-kind").addEventListener("change", fetchIdentityEvents);
setInterval(() => { if (isRouteActive("identity")) fetchIdentity(); }, 10000);


// --- Home (mission control) ------------------------------------------------------------------
// Answers "healthy? need me? what just happened?" in one glance. Deliberately composed entirely
// from data other routes already fetch (state.data via fetchState(), currentLlm, lastUsage) —
// no new backend endpoint, per the "only add one if painfully chatty" guidance; it isn't.
function renderHome() {
  const d = state.data;
  if (!d) return;

  const alerts = [];
  if (d.pending_action) {
    alerts.push(`<div class="home-alert">Confirmation needed: <strong>${esc(d.pending_action.tool_name)}</strong> would ${esc(d.pending_action.reason)}. <a href="#/sessions" style="color:inherit">Review &rarr;</a></div>`);
  }
  const ramPct = d.metrics && d.metrics.memory ? d.metrics.memory.percent : null;
  if (ramPct != null && ramPct >= 90) {
    alerts.push(`<div class="home-alert warn">RAM is at ${Math.round(ramPct)}%.</div>`);
  }
  document.getElementById("home-alerts").innerHTML = alerts.join("");

  const m = d.metrics || {};
  const cpuPct = m.cpu ? m.cpu.overall_percent : null;
  const uptimeH = m.system ? m.system.uptime_hours : null;
  const healthCard = (label, value, danger) =>
    `<div class="usage-card${danger ? " usage-card-danger" : ""}"><div class="usage-card-label">${esc(label)}</div><div class="usage-card-value">${esc(value)}</div></div>`;
  const healthCards = [];
  if (cpuPct != null) healthCards.push(healthCard("CPU", Math.round(cpuPct) + "%", cpuPct >= 90));
  if (ramPct != null) healthCards.push(healthCard("RAM", Math.round(ramPct) + "%", ramPct >= 90));
  if (m.disks && m.disks.length) healthCards.push(healthCard("Disk", Math.round(m.disks[0].percent) + "%", m.disks[0].percent >= 90));
  if (uptimeH != null) healthCards.push(healthCard("Uptime", uptimeH.toFixed(1) + "h", false));
  document.getElementById("home-health").innerHTML = healthCards.join("") || '<div class="empty-state">No metrics yet.</div>';

  const needs = [];
  if (d.pending_action) needs.push(`<li class="list-item compact"><span class="tool">Confirmation</span> <span class="muted">${esc(d.pending_action.tool_name)}</span></li>`);
  (d.tasks || []).filter((t) => t.status === "failed").slice(0, 5).forEach((t) => {
    needs.push(`<li class="list-item compact"><span class="tool">Failed task</span> <span class="muted">${esc(truncate(t.description, 60))}</span></li>`);
  });
  document.getElementById("home-needs").innerHTML = needs.length ? needs.join("") : '<li class="empty-state">Nothing needs you right now.</li>';

  const now = [];
  const latestSession = (d.sessions || [])[0];
  if (latestSession) {
    now.push(`<li class="list-item compact" data-home-session><span class="ts">${esc(latestSession.started_at || "")}</span>${badge(latestSession.source)} ${esc(truncate(latestSession.transcript, 60))}</li>`);
  }
  const runningTask = (d.tasks || []).find((t) => t.status === "running");
  if (runningTask) now.push(`<li class="list-item compact"><span class="tool">Running</span> <span class="muted">${esc(truncate(runningTask.description, 60))}</span></li>`);
  document.getElementById("home-now").innerHTML = now.length ? now.join("") : '<li class="empty-state">Nothing happening right now.</li>';
  const homeNowSession = document.querySelector("#home-now [data-home-session]");
  if (homeNowSession) homeNowSession.addEventListener("click", () => showDetail("session", latestSession));

  const openTasks = (d.tasks || []).filter((t) => t.status === "running" || t.status === "queued").length;
  const todayCards = [];
  if (lastUsage) todayCards.push(healthCard("Spend today", fmtUsd(lastUsage.periods.today.cost_usd), false));
  if (d.counts) todayCards.push(healthCard("Done today", String(d.counts.tasks_done_today ?? 0), false));
  todayCards.push(healthCard("Sessions", String((d.sessions || []).length), false));
  todayCards.push(healthCard("Open tasks", String(openTasks), false));
  document.getElementById("home-today").innerHTML = todayCards.join("");

  // Recent sessions (beyond the single "Now" row above): last 5, clickable -> detail panel.
  const recentSessions = (d.sessions || []).slice(0, 5);
  const recentList = document.getElementById("home-recent-sessions");
  recentList.innerHTML = "";
  if (!recentSessions.length) {
    recentList.innerHTML = '<li class="empty-state">No sessions yet.</li>';
  } else {
    recentSessions.forEach((s) => {
      const li = document.createElement("li");
      li.className = "list-item compact";
      li.innerHTML = `<span class="ts">${esc(s.started_at || "")}</span>${badge(s.source)} ${esc(truncate(s.transcript, 60))}`;
      wireRowActivation(li, () => showDetail("session", s));
      recentList.appendChild(li);
    });
  }

  // Recent autonomy activity: same /api/autonomy data the Autonomy route shows, polled lightly
  // (see fetchAutonomySummary below) so Home doesn't need its own backend endpoint.
  const autoList = document.getElementById("home-recent-autonomy");
  if (!lastAutonomy) {
    autoList.innerHTML = '<li class="empty-state">Autonomy data not loaded yet.</li>';
  } else if (!lastAutonomy.available) {
    autoList.innerHTML = '<li class="empty-state">Autonomy is not available in this build.</li>';
  } else if (!lastAutonomy.enabled) {
    autoList.innerHTML = '<li class="empty-state">Autonomy is off.</li>';
  } else {
    const recentDecisions = (lastAutonomy.decisions || []).slice(0, 5);
    autoList.innerHTML = recentDecisions.length
      ? recentDecisions
          .map((x) => `<li class="list-item compact"><span class="ts">${esc((x.created_at || "").replace("T", " ").slice(0, 16))}</span>
            <span class="tool">${esc(x.decision || "")}</span> <span class="muted">${esc(truncate(x.context_summary || x.action_taken || "", 60))}</span></li>`)
          .join("")
      : '<li class="empty-state">Nothing logged yet.</li>';
  }

  // Presence (face recognition), only shown when the feature is enabled on this machine. Kept
  // as a small local helper (not identityPresenceText, which reads the Identity route's own
  // module-level identityState) so Home works even if the Identity route was never visited.
  const presenceEl = document.getElementById("home-presence");
  const presenceBlock = presenceEl.closest(".home-block");
  if (homePresence && homePresence.enabled) {
    presenceBlock.hidden = false;
    const st = homePresence.presence || {};
    presenceEl.textContent = homePresence.paused
      ? "Paused — the camera is off"
      : st.camera_unreachable ? "Camera unreachable"
      : st.camera_covered ? "Camera covered"
      : st.owner_present ? `${st.owner_name} is here`
      : st.unknown_present ? "Someone unrecognized is in view"
      : "Nobody in view";
  } else {
    presenceBlock.hidden = true;
  }
}
