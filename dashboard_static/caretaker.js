// Caretaker route (2026-10-16): what Jarvis noticed is wrong with the laptop or with itself, what it
// fixed, and an Undo for every fix that can be undone. GET/POST /api/feature/caretaker[/action].
// Plain JS, esc()/escAttr() from app.js. Everything drawn here comes from fixed fields: no HTML from the server.

const CT_SEV_CLASS = { critical: "usage-card-danger", high: "usage-card-danger", warn: "", info: "" };

function ctBytes(n) {
  n = Number(n || 0);
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (Math.abs(n) >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i < 2 ? Math.round(n) : n.toFixed(1)) + " " + u[i];
}

function ctWhen(iso) {
  return esc(String(iso || "").replace("T", " ").slice(0, 16));
}

async function ctGet() {
  const res = await fetch("/api/feature/caretaker", { cache: "no-store" });
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

async function ctPost(action, body) {
  const res = await fetch(`/api/feature/caretaker/${action}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || data.detail || "HTTP " + res.status);
  return data;
}

function ctCards(rep) {
  const s = rep.summary || {};
  const open = (rep.issues || []).length;
  const urgent = (rep.issues || []).filter((i) => i.severity === "critical" || i.severity === "high").length;
  const card = (label, value, cls) =>
    `<div class="usage-card ${cls || ""}"><div class="usage-card-label">${esc(label)}</div>` +
    `<div class="usage-card-value">${esc(String(value))}</div></div>`;
  return [
    card("Open problems", open, urgent ? "usage-card-danger" : open ? "" : "usage-card-good"),
    card("Fixed today", s.fixed || 0, s.fixed ? "usage-card-good" : ""),
    card("Space freed today", ctBytes(s.freed_bytes), s.freed_bytes ? "usage-card-good" : ""),
    card("Held (undoable)", ctBytes(s.held_bytes), s.held_bytes ? "usage-card-good" : ""),
  ].join("");
}

function ctIssueRow(i) {
  const gaveUp = i.status === "gave_up";
  const tried = (i.tried || []).length
    ? `<div class="muted">Tried: ${(i.tried || []).map(esc).join("; ")}</div>` : "";
  return `
    <li class="list-item ${CT_SEV_CLASS[i.severity] || ""}">
      <span class="src-badge">${esc(i.severity)}</span>
      <div class="ct-issue-body">
        <div>${esc(i.title)}</div>
        <div class="muted">${esc(i.category)} &middot; first seen ${ctWhen(i.first_seen)} &middot; last ${ctWhen(i.last_seen)}
          ${gaveUp ? " &middot; <strong>gave up after " + esc(String(i.attempts)) + " tries</strong>" : ""}</div>
        ${tried}
      </div>
      <button class="btn btn-ghost" type="button" data-ct-ignore="${escAttr(i.key)}">Ignore</button>
    </li>`;
}

function ctActionRow(a) {
  const canUndo = a.undo && !a.undone;
  return `
    <li class="list-item compact">
      <span class="src-badge">${esc(a.tier)}</span>
      <span>${esc(a.action)}: ${esc(a.detail)} ${a.freed_bytes ? "(" + ctBytes(a.freed_bytes) + ")" : ""}
        <span class="muted">&middot; ${esc(a.result)}</span></span>
      <span class="muted">${ctWhen(a.ts)}</span>
      ${a.undone ? '<span class="muted">undone</span>' : ""}
      ${canUndo ? `<button class="btn btn-ghost" type="button" data-ct-undo="${escAttr(String(a.id))}">Undo</button>` : ""}
    </li>`;
}

async function refreshCaretaker(message) {
  const view = document.getElementById("view-caretaker");
  if (!view) return;
  const status = document.getElementById("ct-status");
  let rep;
  try {
    rep = await ctGet();
  } catch (e) {
    if (status) status.textContent = "Couldn't load the Caretaker: " + e.message;
    return;
  }
  document.getElementById("ct-cards").innerHTML = ctCards(rep);
  const issues = rep.issues || [];
  document.getElementById("ct-issues").innerHTML = issues.length
    ? issues.map(ctIssueRow).join("")
    : `<li class="empty-state">Nothing wrong that I can see.</li>`;
  const actions = rep.actions || [];
  document.getElementById("ct-actions").innerHTML = actions.length
    ? actions.map(ctActionRow).join("")
    : `<li class="empty-state">No fixes yet.</li>`;
  if (status) {
    const last = rep.last_scan && rep.last_scan.at;
    status.textContent = message ? message : !rep.enabled ? "The Caretaker is switched off in Settings (JARVIS_CARETAKER)."
      : last ? `Last checked ${String(last).replace("T", " ").slice(0, 16)}.` : "Not checked yet since Jarvis started.";
  }
}
window.refreshCaretaker = refreshCaretaker;

document.getElementById("ct-scan")?.addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  btn.disabled = true;
  try { await ctPost("scan", {}); } catch (err) { alert("Check failed: " + err.message); }
  btn.disabled = false;
  refreshCaretaker();
});

document.getElementById("ct-fix")?.addEventListener("click", async (e) => {
  const btn = e.currentTarget;
  btn.disabled = true;
  let msg;
  try {
    const r = await ctPost("fix", {});
    msg = r.error ? "Not fixing right now: " + r.error
      : (r.done && r.done.length ? "Done: " + r.done.join("; ") + "." : "Nothing I can fix on my own right now.");
  } catch (err) { alert("Fix failed: " + err.message); }
  btn.disabled = false;
  refreshCaretaker(msg);
});

document.getElementById("ct-issues")?.addEventListener("click", async (e) => {
  const key = e.target.dataset.ctIgnore;
  if (!key) return;
  if (!confirm("Stop tracking this problem? Jarvis won't try to fix it.")) return;
  try { await ctPost("ignore", { key }); } catch (err) { alert(err.message); }
  refreshCaretaker();
});

document.getElementById("ct-actions")?.addEventListener("click", async (e) => {
  const id = e.target.dataset.ctUndo;
  if (!id) return;
  if (!confirm("Undo this fix? Files Jarvis moved go back where they were.")) return;
  let msg;
  try {
    const r = await ctPost("undo", { id: Number(id) });
    msg = r && r.result;
  } catch (err) { alert("Undo failed: " + err.message); }
  refreshCaretaker(msg);
});

// app.js routes before this file loads: a direct #/caretaker link must still fill the page.
if (typeof currentRoute === "function" && currentRoute() === "caretaker") refreshCaretaker();
