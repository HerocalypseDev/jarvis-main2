const state = { data: null, followedSessionId: null };

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
    li.className = "list-item" + (s.status === "active" ? " active" : "");
    li.innerHTML = `
      <div class="list-item-title">${badge(s.source)} ${esc(truncate(s.transcript, 60))}</div>
      <div class="list-item-meta">${statusPill(s.status)} &middot; ${esc(s.started_at || "")}</div>`;
    li.addEventListener("click", () => showDetail("session", s));
    el.appendChild(li);
  });
  if (!sessions || !sessions.length) el.innerHTML = '<li class="muted">No sessions yet.</li>';
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
    li.addEventListener("click", (e) => {
      if (e.target.closest(".btn-stop")) return;
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
  if (!tasks || !tasks.length) el.innerHTML = '<li class="muted">No tasks yet.</li>';
}

function renderActivity(audit) {
  const el = document.getElementById("activity-list");
  el.innerHTML = "";
  (audit || []).forEach((a) => {
    const li = document.createElement("li");
    li.className = "list-item compact";
    li.innerHTML = `<span class="ts">${esc(a.timestamp)}</span><span class="tool">${esc(a.tool_name)}</span><span class="muted">${esc(truncate(a.result_preview, 80))}</span>`;
    li.addEventListener("click", () => showDetail("audit", a));
    el.appendChild(li);
  });
  if (!audit || !audit.length) el.innerHTML = '<li class="muted">No activity yet.</li>';
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
  if (!victoryLog || !victoryLog.length) el.innerHTML = '<li class="muted">Nothing completed yet.</li>';
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

function showDetail(kind, item) {
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
          <pre class="detail-code">${item.reply ? esc(item.reply) : '<span class="muted">(pending)</span>'}</pre>
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
      </div>`;
  }
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
    el.innerHTML = '<li class="muted">Failed to load audit trail.</li>';
  }
}

function renderAuditResults(rows) {
  const el = document.getElementById("audit-list");
  el.innerHTML = "";
  rows.forEach((a) => {
    const li = document.createElement("li");
    li.className = "list-item compact";
    li.innerHTML = `<span class="ts">${esc(a.timestamp)}</span><span class="tool">${esc(a.tool_name)}</span><span class="muted">${esc(truncate(a.result_preview, 80))}</span>`;
    li.addEventListener("click", () => showDetail("audit", a));
    el.appendChild(li);
  });
  if (!rows.length) el.innerHTML = '<li class="muted">No matching actions.</li>';
}

function isAuditTabActive() {
  const panel = document.getElementById("tab-audit");
  return !!panel && panel.classList.contains("active");
}

// Recurring skills + recurring reminders — kept as its own tab rather than folded into Tasks,
// since these are standing routines, not one-off/in-flight work.
async function fetchDailyItems() {
  const el = document.getElementById("daily-list");
  try {
    const res = await fetch("/api/daily");
    const data = await res.json();
    renderDailyItems(data.items || []);
  } catch (e) {
    el.innerHTML = '<li class="muted">Failed to load daily items.</li>';
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
  if (!items.length) el.innerHTML = '<li class="muted">No recurring skills or reminders yet.</li>';
}

// Local Claude-spend estimate (GET /api/usage): every API call's token usage x list price,
// tracked by Jarvis itself — no admin key. Shown as a top-bar chip (refreshed every minute) and a
// Usage tab (refreshed when opened and every 30s while it's the active tab).
function fmtUsd(n) {
  n = Number(n) || 0;
  return "$" + (n < 1 ? n.toFixed(3) : n.toFixed(2));
}

async function fetchUsage() {
  try {
    const res = await fetch("/api/usage");
    const data = await res.json();
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
    : '<li class="muted">No usage recorded yet.</li>';
  const extra = u.unknown_price_models.length
    ? ` Approximate pricing used for: ${u.unknown_price_models.join(", ")}.`
    : "";
  document.getElementById("usage-note").textContent = u.estimate_note + extra;
}

function isUsageTabActive() {
  const panel = document.getElementById("tab-usage");
  return !!panel && panel.classList.contains("active");
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
  document.querySelector('.tab-btn[data-tab="usage"]').click();
});
fetchUsage();
setInterval(fetchUsage, 60000);
setInterval(() => { if (isUsageTabActive()) fetchUsage(); }, 30000);

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
    if (btn.dataset.tab === "audit") fetchAuditResults();
    if (btn.dataset.tab === "daily") fetchDailyItems();
    if (btn.dataset.tab === "usage") fetchUsage();
    document.querySelector("footer.bottom").classList.toggle("tall", btn.dataset.tab === "sleep");
  });
});

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
document.getElementById("compose-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("compose-input");
  const statusEl = document.getElementById("compose-status");
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
function handleLiveEvent(event) {
  if (!event || !event.type) return;
  if (event.type === "session_start" && event.data && event.data.source === "voice") {
    showDetail("session", {
      id: event.data.id,
      source: "voice",
      transcript: event.data.transcript,
      status: "active",
      reply: null,
      started_at: new Date().toISOString(),
      ended_at: null,
    });
  } else if (event.type === "session_end" && event.data && event.data.id === state.followedSessionId) {
    const d = state.data;
    const found = d && d.sessions && d.sessions.find((s) => s.id === event.data.id);
    if (found) showDetail("session", found);
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
    if (isAuditTabActive()) fetchAuditResults();
  };
}

fetchState();
connectWs();
setInterval(fetchState, 15000);


// Sleep tab (GET /api/sleep): trends from Sleep Mode's own log. Week/Month toggle re-slices the
// 90 days already fetched, no extra request.
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
  const W = 420, H = 130, L = 26, B = 16, T = 8;
  const vals = days.map((d) => d.hours || 0);
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
    if (d.hours != null) {
      const top = y(d.hours);
      const r = Math.min(3, bw / 2);
      out += `<path class="bar ${d.hours >= goal ? "" : "bar-low"}" d="M${x},${H - B} V${top + r} Q${x},${top} ${x + r},${top} H${x + bw - r} Q${x + bw},${top} ${x + bw},${top + r} V${H - B} Z"><title>${esc(d.date)}: ${esc(fmtHours(d.hours))}${d.sessions > 1 ? " (" + d.sessions + " sessions)" : ""}</title></path>`;
    }
    const lab = labelFn(d, i);
    if (lab) out += `<text class="ax" x="${x + bw / 2}" y="${H - 4}" text-anchor="middle">${esc(lab)}</text>`;
  });
  out += `<line class="goal" x1="${L}" x2="${W}" y1="${y(goal)}" y2="${y(goal)}"/></svg>`;
  return out;
}

function sleepTimesSvg(days) {
  const W = 420, H = 130, L = 34, B = 16, T = 8;
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
    ["Sleep debt", `${cur.debt_hours}h`, `vs ${u.goal_hours}h/night`, ""],
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
    ? `Sleep Mode is on — ${fmtHours(u.current.elapsed_minutes / 60)} so far`
    : "Sleep Mode is off";
  document.getElementById("sleep-digests").innerHTML = u.digests.length
    ? u.digests
        .map((d) => `<li class="list-item compact"><span class="muted">${esc(d.ended_at.replace("T", " ").slice(0, 16))}</span> ${esc(d.digest)}</li>`)
        .join("")
    : '<li class="muted">No wake-up recaps yet. One is saved each time Sleep Mode ends.</li>';
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
document.querySelector('.tab-btn[data-tab="sleep"]').addEventListener("click", fetchSleep);
