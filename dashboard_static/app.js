const state = { data: null };

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
  el.innerHTML = bars.join("") + uptimeText;
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
  const el = document.getElementById("detail-panel");
  let inputText;
  try {
    inputText = JSON.stringify(pending.tool_input, null, 2);
  } catch (e) {
    inputText = String(pending.tool_input);
  }
  el.innerHTML = `
    <h3>Confirmation needed</h3>
    <p class="danger-text"><strong>${esc(pending.tool_name)}</strong> would ${esc(pending.reason)}.</p>
    <p><strong>Full input:</strong></p>
    <pre>${esc(inputText)}</pre>
    <div class="detail-actions">
      <button class="btn btn-danger" id="approve-btn">Approve &amp; Run</button>
      <button class="btn btn-ghost" id="reject-btn">Reject</button>
    </div>
    <p id="pending-action-status" class="muted"></p>`;
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

function renderSessions(sessions) {
  const el = document.getElementById("sessions-list");
  el.innerHTML = "";
  (sessions || []).forEach((s) => {
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

function showDetail(kind, item) {
  const el = document.getElementById("detail-panel");
  if (kind === "session") {
    el.innerHTML = `
      <h3>${badge(item.source)} Session #${esc(item.id)}</h3>
      <p><strong>Status:</strong> ${statusPill(item.status)}</p>
      <p><strong>Transcript:</strong> ${esc(item.transcript)}</p>
      <p><strong>Reply:</strong> ${esc(item.reply || "(pending)")}</p>
      <p class="muted">${esc(item.started_at)} &rarr; ${esc(item.ended_at || "active")}</p>`;
  } else if (kind === "task") {
    el.innerHTML = `
      <h3>Task ${esc(item.id)}</h3>
      <p><strong>Status:</strong> ${statusPill(item.status)}</p>
      <p><strong>Description:</strong> ${esc(item.description)}</p>
      <p><strong>Result:</strong> ${esc(item.result_summary || "(none yet)")}</p>
      <p class="muted">${esc(item.started_at || "")} &rarr; ${esc(item.finished_at || "running")}</p>`;
  } else if (kind === "audit") {
    const fromTranscript = item.transcript
      ? `<p><strong>From command:</strong> ${esc(truncate(item.transcript, 200))}</p>`
      : "";
    el.innerHTML = `
      <h3>${esc(item.tool_name)}</h3>
      <p class="muted">${esc(item.timestamp)}</p>
      ${fromTranscript}
      <p><strong>Input:</strong></p><pre>${esc(item.tool_input)}</pre>
      <p><strong>Result:</strong></p><pre>${esc(item.result)}</pre>`;
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

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
    if (btn.dataset.tab === "audit") fetchAuditResults();
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
  ws.onmessage = () => {
    fetchState();
    if (isAuditTabActive()) fetchAuditResults();
  };
}

fetchState();
connectWs();
setInterval(fetchState, 15000);
