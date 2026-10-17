// Phones route (2026-10-17): where the owner's phones are, on a dark street map, from the Jarvis Locator app.
// GET/POST /api/feature/phones[/action]. Leaflet (vendored, vendor/leaflet) with OpenStreetMap tiles, darkened in CSS.
// Plain JS, esc()/escAttr() from app.js. Everything drawn comes from fixed fields: no HTML from the server.

const PH = { map: null, layers: {}, fitted: false, data: null, timer: null, code: null };

async function phGet() {
  const res = await fetch("/api/feature/phones", { cache: "no-store" });
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

async function phPost(action, body) {
  const res = await fetch(`/api/feature/phones/${action}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || data.detail || "HTTP " + res.status);
  return data;
}

function phEnsureMap() {
  if (PH.map || typeof L === "undefined") return PH.map;
  const el = document.getElementById("ph-map");
  if (!el) return null;
  PH.map = L.map(el, { zoomControl: true, attributionControl: true }).setView([9.06, 7.49], 5);
  // OpenStreetMap's own tiles (free, no key), turned dark by a CSS filter on the tile pane (.ph-map in style.css).
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
  }).addTo(PH.map);
  return PH.map;
}

function phPinIcon(name, stale) {
  return L.divIcon({
    className: "ph-pin-wrap",
    html: `<div class="ph-pin${stale ? " ph-pin-stale" : ""}"><span class="ph-pin-dot"></span>`
      + `<span class="ph-pin-label">${esc(name)}</span></div>`,
    iconSize: [24, 24], iconAnchor: [12, 12],
  });
}

function phDrawMap(devices, now) {
  const map = phEnsureMap();
  if (!map) return;
  const seen = new Set();
  const bounds = [];
  for (const d of devices) {
    if (d.lat == null || d.lon == null) continue;
    seen.add(d.id);
    const ll = [d.lat, d.lon];
    bounds.push(ll);
    const stale = !d.fix_ts || now - d.fix_ts > 30 * 60 * 1000;
    let lay = PH.layers[d.id];
    if (!lay) {
      lay = PH.layers[d.id] = {
        marker: L.marker(ll, { icon: phPinIcon(d.name, stale) }).addTo(map),
        circle: L.circle(ll, { radius: d.acc || 0, color: "#2fd8ff", weight: 1, fillColor: "#2fd8ff", fillOpacity: 0.08 }).addTo(map),
        trail: L.polyline([], { color: "#2fd8ff", weight: 2, opacity: 0.45, dashArray: "4 6" }).addTo(map),
      };
    } else {
      lay.marker.setLatLng(ll);
      lay.marker.setIcon(phPinIcon(d.name, stale));
      lay.circle.setLatLng(ll);
      lay.circle.setRadius(d.acc || 0);
    }
    lay.trail.setLatLngs((d.trail || []).map((p) => [p[0], p[1]]));
    lay.marker.bindTooltip(esc(d.text || d.name), { direction: "top", offset: [0, -14] });
  }
  for (const id of Object.keys(PH.layers)) {
    if (!seen.has(id)) {
      const lay = PH.layers[id];
      map.removeLayer(lay.marker); map.removeLayer(lay.circle); map.removeLayer(lay.trail);
      delete PH.layers[id];
    }
  }
  if (!PH.fitted && bounds.length) {
    phFit(bounds);
    PH.fitted = true;
  }
}

function phFit(bounds) {
  if (!PH.map) return;
  bounds = bounds || (PH.data ? PH.data.devices.filter((d) => d.lat != null).map((d) => [d.lat, d.lon]) : []);
  if (!bounds.length) return;
  if (bounds.length === 1) PH.map.setView(bounds[0], 16);
  else PH.map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
}

function phBattery(d) {
  if (d.battery == null) return "";
  const low = d.battery <= 15 && !d.charging;
  return `<span class="ph-chip${low ? " ph-chip-danger" : ""}">${esc(String(d.battery))}%${d.charging ? " charging" : ""}</span>`;
}

function phDrawList(rep) {
  const el = document.getElementById("ph-list");
  if (!el) return;
  if (!rep.devices.length) {
    el.innerHTML = rep.paired
      ? `<p class="muted">Paired, waiting for a phone to check in. Open Jarvis Locator on the phone and tap
         "Save and start sharing".</p>`
      : `<p class="muted">No phone yet. Set one up below.</p>`;
    return;
  }
  el.innerHTML = rep.devices.map((d) => {
    const stale = !d.fix_ts || rep.now - d.fix_ts > 30 * 60 * 1000;
    const where = d.place || (d.lat != null ? `${Number(d.lat).toFixed(5)}, ${Number(d.lon).toFixed(5)}` : "no position yet");
    const gmaps = d.lat != null
      ? `<a class="btn" target="_blank" rel="noopener noreferrer" href="${escAttr(`https://www.google.com/maps/search/?api=1&query=${d.lat},${d.lon}`)}">Google Maps</a>`
      : "";
    return `<div class="ph-card${stale ? " ph-card-stale" : ""}" data-id="${escAttr(d.id)}">
      <div class="ph-card-head"><span class="ph-card-name">${esc(d.name)}</span>${phBattery(d)}</div>
      <div class="ph-card-where">${esc(where)}${d.acc ? ` <span class="muted">(within ${esc(String(Math.round(d.acc)))} m)</span>` : ""}</div>
      <div class="muted">${esc(d.ago || "")}${stale && d.fix_ts ? " (old position)" : ""}</div>
      <div class="ph-card-actions">
        <button class="btn btn-primary" type="button" data-ph="ask">Locate</button>
        <button class="btn" type="button" data-ph="focus">Show</button>${gmaps}
        <button class="btn" type="button" data-ph="forget">Remove</button>
      </div></div>`;
  }).join("");
}

function phDrawSetup(rep) {
  const el = document.getElementById("ph-setup");
  if (!el) return;
  const codeBlock = PH.code
    ? `<div class="ph-code"><code id="ph-code-text">${esc(PH.code)}</code>
        <div class="ph-card-actions"><button class="btn btn-primary" type="button" data-ph="copy">Copy</button>
        ${rep.telegram ? '<button class="btn" type="button" data-ph="telegram">Send to my Telegram</button>' : ""}
        <button class="btn" type="button" data-ph="hide">Hide</button></div>
        <p class="muted">This code is the key to your phones' locations. Keep it private.</p></div>`
    : "";
  el.innerHTML = `<h3 class="ph-h">${rep.devices.length ? "Add another phone" : "Set up a phone"}</h3>
    <ol class="ph-steps">
      <li>Install the <b>Jarvis Locator</b> APK on the phone (allow "install unknown apps").</li>
      <li>Get the setup code below and paste it into the app, give the phone a name, tap "Save and start sharing".</li>
      <li>Allow location ("all the time" if offered) and tap "Keep running in the background".</li>
    </ol>
    ${PH.code ? codeBlock : `<button class="btn btn-primary" type="button" data-ph="reveal">Show setup code</button>
      ${rep.telegram ? '<button class="btn" type="button" data-ph="telegram">Send it to my Telegram</button>' : ""}`}
    ${rep.paired ? '<p class="muted ph-repair">Lost a phone or shared the code by mistake? <button class="btn" type="button" data-ph="repair">Make a new key</button> (every phone then needs the new code).</p>' : ""}`;
}

function phStatus(rep) {
  const el = document.getElementById("ph-status");
  if (!el) return;
  if (!rep.enabled) el.textContent = "The phone locator is switched off in Settings.";
  else if (!rep.paired) el.textContent = "Not set up yet: follow the steps on the right.";
  else if (!rep.connected) el.textContent = "Connecting to the relay... (needs this PC's internet)" + (rep.error ? ` Last problem: ${rep.error}.` : "");
  else el.textContent = "Listening for check-ins. Tap Locate for a fresh position (phones answer in a few seconds to a minute).";
}

async function refreshPhones() {
  phEnsureMap();
  if (PH.map) setTimeout(() => PH.map.invalidateSize(), 50);
  try {
    const rep = await phGet();
    PH.data = rep;
    phStatus(rep);
    phDrawList(rep);
    phDrawSetup(rep);
    phDrawMap(rep.devices || [], rep.now || Date.now());
  } catch (e) {
    const el = document.getElementById("ph-list");
    if (el) el.innerHTML = `<p class="muted">Couldn't load the phones (${esc(e.message)}). <button class="btn" type="button" data-ph="retry">Retry</button></p>`;
  }
  clearTimeout(PH.timer);
  PH.timer = setTimeout(() => { if (isRouteActive("phones")) refreshPhones(); }, 15000);
}
window.refreshPhones = refreshPhones;

document.addEventListener("click", async (ev) => {
  const btn = ev.target.closest("[data-ph]");
  if (!btn || !btn.closest("#view-phones")) return;
  const card = btn.closest(".ph-card");
  const id = card ? card.dataset.id : "";
  const what = btn.dataset.ph;
  try {
    if (what === "ask") {
      btn.disabled = true; btn.textContent = "Asking...";
      await phPost("ask", { id });
      setTimeout(refreshPhones, 8000);
    } else if (what === "focus") {
      const d = PH.data.devices.find((x) => x.id === id);
      if (d && d.lat != null && PH.map) PH.map.setView([d.lat, d.lon], 17);
    } else if (what === "forget") {
      if (!confirm("Remove this phone from the map? It comes back the next time it checks in, unless you stop sharing in the app.")) return;
      await phPost("forget", { id });
      refreshPhones();
    } else if (what === "reveal") {
      const r = await phPost("setup_code", {});
      PH.code = r.code || null;
      refreshPhones();
    } else if (what === "copy") {
      await navigator.clipboard.writeText(PH.code || "");
      btn.textContent = "Copied";
    } else if (what === "hide") {
      PH.code = null;
      refreshPhones();
    } else if (what === "telegram") {
      const r = await phPost("send_setup", {});
      alert(r.ok ? r.message : (r.error || "Couldn't send it."));
    } else if (what === "repair") {
      if (!confirm("Make a new key? Every phone stops reaching Jarvis until you paste the new code into it.")) return;
      const r = await phPost("repair", {});
      PH.code = r.code || null;
      refreshPhones();
    } else if (what === "retry") {
      refreshPhones();
    }
  } catch (e) {
    alert(e.message);
  }
});

document.addEventListener("DOMContentLoaded", () => {
  const ask = document.getElementById("ph-ask");
  if (ask) ask.addEventListener("click", async () => {
    ask.disabled = true; ask.textContent = "Asking...";
    try { await phPost("ask", {}); } catch (e) { alert(e.message); }
    setTimeout(() => { ask.disabled = false; ask.textContent = "Locate now"; refreshPhones(); }, 8000);
  });
  const fit = document.getElementById("ph-fit");
  if (fit) fit.addEventListener("click", () => phFit());
});

// app.js routes before this file loads: a direct #/phones load would otherwise wait for the next event.
if (typeof isRouteActive === "function" && isRouteActive("phones")) refreshPhones();
