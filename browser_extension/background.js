// Jarvis Tabs: lets Jarvis on this PC see and manage the tabs in this browser (Opera GX, Firefox, Chrome, Edge).
// It connects to Jarvis at ws://127.0.0.1:<port>/tabs (port and pairing key from pairing.json, which Jarvis writes into
// this folder), checks that the other side really is Jarvis (it must prove it knows the key), proves the same back,
// then answers Jarvis's commands. It never takes commands from web pages and never talks to anything but 127.0.0.1.
"use strict";

const api = globalThis.browser ?? globalThis.chrome;
const PING_MS = 20000; // a message every 20 s keeps the extension awake while Jarvis is connected
const enc = new TextEncoder();

let ws = null;
let cfg = null;
let serverVerified = false;
let authed = false;
let pingTimer = null;

function hex(bytes) {
  return [...new Uint8Array(bytes)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function nonce() {
  const a = new Uint8Array(16);
  crypto.getRandomValues(a);
  return hex(a);
}

async function hmacHex(key, msg) {
  const k = await crypto.subtle.importKey("raw", enc.encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return hex(await crypto.subtle.sign("HMAC", k, enc.encode(msg)));
}

function browserName() {
  const nav = globalThis.navigator || {};
  const ua = nav.userAgent || "";
  const brands = ((nav.userAgentData && nav.userAgentData.brands) || []).map((b) => b.brand || "");
  if (brands.some((b) => /Opera GX/i.test(b))) return "Opera GX";
  if (/OPR\//.test(ua) || brands.some((b) => /Opera/i.test(b))) return "Opera";
  if (/Firefox\//.test(ua)) return "Firefox";
  if (/Edg\//.test(ua) || brands.some((b) => /Edge/i.test(b))) return "Edge";
  if (/Chrome\//.test(ua)) return "Chrome";
  return "Browser";
}

async function loadConfig() {
  const res = await fetch(api.runtime.getURL("pairing.json"));
  const c = await res.json();
  if (!c || !c.key || !c.port) throw new Error("pairing.json is incomplete");
  return c;
}

function tabInfo(t) {
  return {
    id: t.id, windowId: t.windowId, index: t.index, title: t.title || "", url: t.url || t.pendingUrl || "",
    active: !!t.active, incognito: !!t.incognito, pinned: !!t.pinned, audible: !!t.audible,
    muted: !!(t.mutedInfo && t.mutedInfo.muted), discarded: !!t.discarded, lastAccessed: t.lastAccessed || 0,
  };
}

// Runs inside the page (must not use anything from this file).
function pageText(max) {
  const desc = document.querySelector('meta[name="description"],meta[property="og:description"]');
  const sel = String(typeof getSelection === "function" ? getSelection() : "").trim();
  const text = (document.body ? document.body.innerText || "" : "").replace(/\n{3,}/g, "\n\n").trim();
  return {
    title: document.title, url: location.href, description: desc ? String(desc.content || "").slice(0, 400) : "",
    selection: sel.slice(0, 4000), text: text.slice(0, max), textLength: text.length,
  };
}

async function readTab(tabId, maxChars) {
  const t = tabInfo(await api.tabs.get(Number(tabId)));
  const max = Math.max(500, Math.min(Number(maxChars) || 12000, 60000));
  if (t.discarded) {
    return { ...t, text: null, reason: "the tab is asleep (the browser unloaded it to save memory); open it once and ask again" };
  }
  try {
    const res = await api.scripting.executeScript({ target: { tabId: t.id }, func: pageText, args: [max] });
    const r = res && res[0] && res[0].result;
    if (!r) return { ...t, text: null, reason: "the page gave nothing back" };
    return { ...t, ...r, title: r.title || t.title };
  } catch (e) {
    return { ...t, text: null, reason: "the browser doesn't let extensions read this page (" + String((e && e.message) || e).slice(0, 120) + ")" };
  }
}

function closedItem(s) {
  const when = s.lastModified || 0;
  if (s.tab) return { kind: "tab", sessionId: s.tab.sessionId, title: s.tab.title || "", url: s.tab.url || "", closedAt: when };
  if (s.window) {
    const tabs = s.window.tabs || [];
    return { kind: "window", sessionId: s.window.sessionId, tabs: tabs.length, title: (tabs[0] && tabs[0].title) || "", url: (tabs[0] && tabs[0].url) || "", closedAt: when };
  }
  return null;
}

async function runCommand(action, a) {
  switch (action) {
    case "list": {
      const tabs = await api.tabs.query({});
      let focused = null;
      try { focused = (await api.windows.getLastFocused()).id; } catch (e) { /* no window */ }
      return { browser: browserName(), focusedWindowId: focused, tabs: tabs.map(tabInfo) };
    }
    case "read":
      return await readTab(a.tabId, a.maxChars);
    case "close": {
      const ids = (a.tabIds || []).map(Number);
      const found = (await Promise.all(ids.map((id) => api.tabs.get(id).then(tabInfo, () => null)))).filter(Boolean);
      if (found.length) await api.tabs.remove(found.map((t) => t.id));
      return { closed: found };
    }
    case "activate": {
      const t = await api.tabs.update(Number(a.tabId), { active: true });
      try { await api.windows.update(t.windowId, { focused: true }); } catch (e) { /* window gone */ }
      return tabInfo(t);
    }
    case "open": {
      const url = String(a.url || "");
      if (!/^https?:\/\//i.test(url)) throw new Error("only http(s) links can be opened");
      return tabInfo(await api.tabs.create({ url, active: a.active !== false }));
    }
    case "closed": {
      const items = await api.sessions.getRecentlyClosed({ maxResults: 25 });
      return { items: items.map(closedItem).filter(Boolean) };
    }
    case "reopen": {
      const r = await api.sessions.restore(a.sessionId || undefined);
      const t = r && (r.tab || (r.window && r.window.tabs && r.window.tabs[0]));
      return { kind: r && r.window ? "window" : "tab", title: t ? t.title || "" : "", url: t ? t.url || "" : "",
        tabs: r && r.window ? (r.window.tabs || []).length : 1 };
    }
    case "ping":
      return { ok: true };
  }
  throw new Error("unknown action " + action);
}

function stopPing() {
  if (pingTimer) clearInterval(pingTimer);
  pingTimer = null;
}

async function onMessage(sock, myNonce, raw) {
  let msg;
  try { msg = JSON.parse(raw); } catch (e) { return; }
  if (msg.type === "challenge") {
    // The other side must prove it knows the key before we say anything else: a program squatting on the port gets nothing.
    if (msg.proof !== (await hmacHex(cfg.key, "jarvis-server:" + myNonce))) { sock.close(); return; }
    serverVerified = true;
    sock.send(JSON.stringify({ type: "auth", proof: await hmacHex(cfg.key, "jarvis-extension:" + String(msg.nonce || "")) }));
    return;
  }
  if (msg.type === "ready" && serverVerified) {
    authed = true;
    stopPing();
    pingTimer = setInterval(() => { if (sock.readyState === 1) sock.send('{"type":"ping"}'); }, PING_MS);
    return;
  }
  if (msg.type === "cmd" && authed) {
    let reply;
    try {
      reply = { type: "result", id: msg.id, ok: true, data: await runCommand(msg.action, msg.args || {}) };
    } catch (e) {
      reply = { type: "result", id: msg.id, ok: false, error: String((e && e.message) || e) };
    }
    if (sock.readyState === 1) sock.send(JSON.stringify(reply));
  }
}

async function connect() {
  if (ws && ws.readyState <= 1) return; // connecting or open
  try {
    cfg = await loadConfig();
  } catch (e) {
    return; // Jarvis hasn't written pairing.json yet
  }
  const myNonce = nonce();
  let sock;
  try {
    sock = new WebSocket("ws://127.0.0.1:" + Number(cfg.port) + "/tabs");
  } catch (e) {
    return;
  }
  ws = sock;
  serverVerified = false;
  authed = false;
  sock.onopen = () => sock.send(JSON.stringify({ type: "hello", nonce: myNonce, browser: browserName(), version: api.runtime.getManifest().version }));
  sock.onmessage = (ev) => { onMessage(sock, myNonce, ev.data).catch(() => {}); };
  sock.onclose = () => {
    if (ws === sock) { ws = null; serverVerified = false; authed = false; stopPing(); }
  };
  sock.onerror = () => { try { sock.close(); } catch (e) { /* already closed */ } };
}

if (api && api.runtime && api.alarms) {
  // Jarvis may start after the browser (or restart): try again every 30 s until it answers.
  api.alarms.create("jarvis-reconnect", { periodInMinutes: 0.5 });
  api.alarms.onAlarm.addListener(() => { connect(); });
  api.runtime.onStartup.addListener(() => { connect(); });
  api.runtime.onInstalled.addListener(() => { connect(); });
  connect();
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { connect, runCommand, hmacHex, browserName, state: () => ({ ws, serverVerified, authed }) };
}
