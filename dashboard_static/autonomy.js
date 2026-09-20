// Autonomy tab: suggestion cards (Approve / Dismiss / Never for this category), commitments,
// projects, editable policy rules, recent decisions, and dynamic tools. Everything is built with
// textContent (never innerHTML) because suggestion text can come from other people's email.
(function () {
  const panel = document.getElementById("tab-autonomy");
  if (!panel) return;
  const root = document.getElementById("autonomy-root");

  function h(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") n.className = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    }
    for (const kid of kids.flat()) {
      if (kid == null) continue;
      n.appendChild(typeof kid === "string" ? document.createTextNode(kid) : kid);
    }
    return n;
  }

  async function call(method, url, body) {
    try {
      const res = await fetch(url, {
        method,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      const data = await res.json();
      if (data.message && !data.ok) alert(data.message);
      return data;
    } catch (e) {
      alert("Could not reach Jarvis.");
      return {};
    } finally {
      refresh();
    }
  }

  // Activity log: built ONCE so the filter inputs keep focus across the 10s refresh.
  const logFilters = { hours: "24", decision: "", outcome: "", category: "", q: "" };
  function selectOf(key, options) {
    return h("select", { onchange: (e) => { logFilters[key] = e.target.value; loadLog(); } },
      ...options.map(([v, label]) => h("option", { value: v }, label)));
  }
  const logList = h("ul", { class: "list compact", id: "auto-log-list" });
  const logMeta = h("div", { class: "muted" });
  const logSection = h("div", {},
    h("div", { class: "auto-form" },
      selectOf("hours", [["1", "last hour"], ["24", "last 24 h"], ["168", "last 7 days"], ["720", "last 30 days"]]),
      selectOf("decision", [["", "any type"], ["act", "actions"], ["inbound", "inbound"], ["queued", "queued"],
        ["suggest", "recorded"], ["silent", "skipped"], ["skill", "skills"], ["error", "errors"]]),
      selectOf("outcome", [["", "any outcome"], ["ok", "ok"], ["failed", "failed"], ["dry_run", "dry run"],
        ["skipped", "skipped"], ["info", "info"]]),
      h("input", { placeholder: "category", size: "14", oninput: (e) => { logFilters.category = e.target.value.trim(); loadLog(); } }),
      h("input", { placeholder: "search text", size: "18", oninput: (e) => { logFilters.q = e.target.value.trim(); loadLog(); } })),
    logMeta, logList);

  function logRow(x) {
    let payload = null;
    try { payload = JSON.parse(x.payload_json || "null"); } catch (e) { /* ignore */ }
    return h("li", {}, h("details", {},
      h("summary", {}, `${when(x.created_at)} · ${x.decision}${x.outcome ? " [" + x.outcome + "]" : ""} · ${(x.context_summary || "").slice(0, 90)}`),
      h("div", { class: "muted" }, "Why: " + (x.policy_reason || "n/a")),
      x.source_quote ? h("div", { class: "muted" }, "Source: \u201c" + x.source_quote + "\u201d") : null,
      h("div", { class: "muted" }, "Did: " + (x.action_taken || "nothing")),
      payload ? h("pre", {}, JSON.stringify(payload, null, 2)) : null,
      x.result ? h("div", { class: "muted" }, "Result: " + x.result) : null));
  }

  async function loadLog() {
    const qs = new URLSearchParams(Object.entries(logFilters).filter(([, v]) => v !== "")).toString();
    try {
      const d = await (await fetch("/api/autonomy/log?" + qs)).json();
      const b = d.budgets || {};
      logMeta.textContent = d.available
        ? `Budget today: ${b.acts_today}/${b.max_acts} actions (soft), ${b.suggestions_today}/${b.max_suggestions} cards. ${d.entries.length} entries.`
        : "Log unavailable.";
      logList.replaceChildren(...(d.entries && d.entries.length ? d.entries.map(logRow) : [h("li", { class: "muted" }, "Nothing matches.")]));
    } catch (e) { /* keep last */ }
  }

  const openReviews = new Set(); // suggestion ids whose review panel is open (survives the 10s refresh)
  const pct = (c) => Math.round((Number(c) || 0) * 100) + "%";
  const when = (iso) => (iso ? iso.replace("T", " ").slice(0, 16) : "");
  const section = (title) => h("h4", { class: "sleep-sub" }, title);
  const none = (text) => [h("li", { class: "muted" }, text)];

  function card(label, value) {
    return h("div", { class: "usage-card" },
      h("div", { class: "usage-card-label" }, label),
      h("div", { class: "usage-card-value" }, String(value)));
  }

  function render(d) {
    if (!d.available) {
      root.replaceChildren(h("p", { class: "muted" }, "Autonomy is not available in this build."));
      return;
    }
    const b = d.budgets || {};
    const top = h("div", { class: "usage-cards" },
      card("Autonomy", d.enabled ? "ON" : "off"),
      card("Mode", d.dry_run ? "dry run" : "live"),
      card("Acts today", `${b.acts_today}/${b.max_acts}`),
      card("Suggestions today", `${b.suggestions_today}/${b.max_suggestions}`));

    const controls = h("div", { class: "auto-controls" },
      h("button", {
        class: "btn " + (d.enabled ? "btn-danger" : ""),
        onclick: () => {
          if (!d.enabled && !confirm("Turn autonomy on? Jarvis will extract commitments from your conversations and mail and suggest actions. It asks before acting unless a rule says otherwise.")) return;
          call("POST", "/api/autonomy/enabled", { enabled: !d.enabled });
        },
      }, d.enabled ? "Turn autonomy off" : "Turn autonomy on"),
      h("button", { class: "btn btn-ghost", onclick: () => call("POST", "/api/autonomy/dry_run", { enabled: !d.dry_run }) },
        d.dry_run ? "Leave dry run" : "Dry run (log only)"),
      d.hard_disabled ? h("span", { class: "muted" }, "Hard-disabled by JARVIS_AUTONOMY_DISABLED.") : null);

    const sugg = d.pending_suggestions || []; // recorded for review: below the confidence floor, or under a user "ask" rule
    // Approve lives inside the review panel on purpose: the user must see exactly what will run
    // (the same sanitized details the agent will be given) before the button is even reachable.
    const detailPane = (s) => {
      let details = {};
      try { details = JSON.parse(s.action_json || "{}"); } catch (e) { /* ignore */ }
      return h("div", { class: "auto-review" },
        h("div", { class: "muted" }, "This will run (" + (s.action_type || "?") + ") with exactly this data:"),
        h("pre", {}, JSON.stringify(details, null, 2)),
        s.sender ? h("div", { class: "muted" }, "Triggered by content from " + s.sender + " - check it is really them.") : null,
        h("button", { class: "btn btn-small", onclick: () => { openReviews.delete(s.id); call("POST", `/api/autonomy/suggestions/${s.id}/approve`); } }, "Approve and run"));
    };
    const suggList = sugg.length ? sugg.map((s) => h("li", { class: "auto-card" },
      h("div", {}, h("strong", {}, s.title), h("span", { class: "muted" }, `  ${pct(s.confidence)} · ${s.category}`)),
      s.evidence ? h("div", { class: "muted" }, "“" + s.evidence + "”") : null,
      s.sender ? h("div", { class: "muted" }, "from " + s.sender) : null,
      openReviews.has(s.id) ? detailPane(s) : null,
      h("div", {},
        h("button", {
          class: "btn btn-small",
          onclick: () => { if (openReviews.has(s.id)) openReviews.delete(s.id); else openReviews.add(s.id); refresh(); },
        }, openReviews.has(s.id) ? "Hide details" : "Review"),
        " ",
        h("button", { class: "btn btn-small btn-ghost", onclick: () => call("POST", `/api/autonomy/suggestions/${s.id}/dismiss`) }, "Dismiss"),
        " ",
        h("button", {
          class: "btn btn-small btn-ghost",
          onclick: () => { if (confirm(`Never suggest "${s.category}" again?`)) call("POST", `/api/autonomy/suggestions/${s.id}/never`); },
        }, "Never for this category")))) : none("Nothing waiting for you.");

    const commits = (d.commitments || []).map((c) => h("li", {},
      `#${c.id} [${c.type}] ${c.description}`,
      c.deadline_iso ? ` — due ${when(c.deadline_iso)}` : "",
      c.who_is_responsible !== "user" ? ` (${c.who_is_responsible})` : "", " ",
      c.quarantined ? h("span", { class: "muted" }, "[unverified - from someone else; not used until you accept] ") : null,
      c.quarantined ? h("button", { class: "btn btn-small", onclick: () => call("POST", `/api/autonomy/commitments/${c.id}/accept`) }, "Accept") : null,
      c.quarantined ? " " : null,
      h("button", { class: "btn btn-small btn-ghost", onclick: () => call("POST", `/api/autonomy/commitments/${c.id}/status`, { status: "completed" }) }, "Done"),
      " ",
      h("button", { class: "btn btn-small btn-ghost", onclick: () => call("POST", `/api/autonomy/commitments/${c.id}/status`, { status: "cancelled" }) }, "Cancel")));

    const actionsByProject = {};
    (d.project_actions || []).forEach((a) => (actionsByProject[a.project_id] = actionsByProject[a.project_id] || []).push(a));
    const projects = (d.projects || []).map((p) => {
      let meta = {};
      try { meta = JSON.parse(p.metadata_json || "{}"); } catch (e) { /* ignore */ }
      return h("li", {},
        h("strong", {}, p.name),
        ` (${p.status}, risk ${p.risk_level || "low"}${meta.campaign_approved === false ? ", campaign PAUSED" : ", running"}) `,
        h("button", {
          class: "btn btn-small btn-ghost",
          onclick: () => call("POST", "/api/autonomy/campaigns/approve", { project: p.name, approved: meta.campaign_approved === false }),
        }, meta.campaign_approved === false ? "Resume campaign" : "Pause campaign"),
        (actionsByProject[p.id] || []).map((a) => h("div", { class: "muted" }, `· ${a.status}: ${a.description}`)),
        h("form", {
          class: "auto-form",
          onsubmit: (e) => {
            e.preventDefault();
            const f = e.target;
            call("POST", "/api/autonomy/campaigns/action", { project: p.name, description: f.description.value.trim() });
            f.reset();
          },
        }, h("input", { name: "description", placeholder: "add a step (background task)", size: "30" }),
          h("button", { class: "btn btn-small btn-ghost", type: "submit" }, "Add step")));
    });

    const policies = (d.policies || []).map((p) => h("li", {},
      `#${p.id} ${p.match_kind} ${p.match_value || p.category} → ${p.verdict} `,
      h("span", { class: "muted" }, `(${p.source}${p.min_confidence != null ? ", min " + pct(p.min_confidence) : ""})`), " ",
      h("button", { class: "btn btn-small btn-ghost", onclick: () => call("DELETE", `/api/autonomy/policies/${p.id}`) }, "Remove")));

    const form = h("form", {
      class: "auto-form",
      onsubmit: (e) => {
        e.preventDefault();
        const f = e.target;
        call("POST", "/api/autonomy/policies", {
          category: f.category.value.trim(), match_kind: f.match_kind.value, match_value: f.match_value.value.trim(),
          verdict: f.verdict.value, min_confidence: f.min_confidence.value || null,
        });
        f.reset();
      },
    },
      h("input", { name: "category", placeholder: "category e.g. email:calendar", size: "24" }),
      h("select", { name: "match_kind" }, ...["category", "sender", "keyword"].map((k) => h("option", { value: k }, k))),
      h("input", { name: "match_value", placeholder: "sender / keyword", size: "16" }),
      h("select", { name: "verdict" }, ...["always_ask", "ask_once", "auto_act", "ignore"].map((k) => h("option", { value: k }, k))),
      h("input", { name: "min_confidence", placeholder: "min conf 0-1", size: "8" }),
      h("button", { class: "btn btn-small", type: "submit" }, "Add rule"));

    const decisions = (d.decisions || []).slice(0, 15).map((x) => h("li", { class: "muted" },
      `${when(x.created_at)} · ${x.decision}: ${(x.action_taken || x.context_summary || "").slice(0, 110)}`,
      x.policy_reason ? ` (${x.policy_reason})` : ""));

    const tools = (d.dynamic_tools || []).map((t) => h("li", {},
      h("strong", {}, "dyn_" + t.name), ` ${t.is_enabled ? "" : "(disabled) "}— ${t.description} `,
      h("button", {
        class: "btn btn-small btn-ghost",
        onclick: () => call("POST", `/api/dynamic_tools/${encodeURIComponent(t.name)}/${t.is_enabled ? "disable" : "enable"}`),
      }, t.is_enabled ? "Disable" : "Enable"),
      " ",
      h("button", {
        class: "btn btn-small btn-danger",
        onclick: () => { if (confirm(`Delete dynamic tool ${t.name}?`)) call("DELETE", `/api/dynamic_tools/${encodeURIComponent(t.name)}`); },
      }, "Revoke")));

    const skills = (d.skills || []).map((s) => {
      let steps = [];
      try { steps = JSON.parse(s.steps_json || "[]").map((x) => x.tool); } catch (e) { /* ignore */ }
      return h("li", {},
        h("strong", {}, s.name), ` ${s.is_enabled ? "" : "(disabled) "}[${s.source}, used ${s.use_count}x] ${steps.join(" \u2192 ")} `,
        h("button", { class: "btn btn-small btn-ghost", onclick: () => call("POST", `/api/autonomy/skills/${encodeURIComponent(s.name)}/${s.is_enabled ? "disable" : "enable"}`) }, s.is_enabled ? "Disable" : "Enable"),
        " ",
        h("button", { class: "btn btn-small btn-danger", onclick: () => { if (confirm(`Delete skill ${s.name}?`)) call("POST", `/api/autonomy/skills/${encodeURIComponent(s.name)}/revoke`); } }, "Revoke"));
    });

    const proposals = (d.dynamic_tool_proposals || []).map((t) => h("li", { class: "auto-card" },
      h("strong", {}, "dyn_" + t.name), ` - ${t.description}`,
      h("div", { class: "muted" }, "Proposed by Jarvis. It has NOT run. Read the code; approving lets it run with your privileges."),
      h("pre", {}, t.code_text),
      h("button", { class: "btn btn-small", onclick: () => { if (confirm(`Approve tool ${t.name}?`)) call("POST", `/api/dynamic_tools/proposals/${t.id}/approve`); } }, "Approve"),
      " ",
      h("button", { class: "btn btn-small btn-ghost", onclick: () => call("POST", `/api/dynamic_tools/proposals/${t.id}/reject`) }, "Reject")));

    root.replaceChildren(top, controls,
      section("Recorded for review (low confidence or an ask rule)"), h("ul", { class: "list" }, suggList),
      section("Open commitments"), h("ul", { class: "list compact" }, commits.length ? commits : none("None tracked yet.")),
      section("Projects & campaigns"), h("ul", { class: "list compact" }, projects.length ? projects : none("None.")),
      section("Rules (auto-approve / ask / ignore)"), h("ul", { class: "list compact" }, policies), form,
      section("Activity log - what autonomy did and why"), logSection,
      section("Skills (composed sequences of existing tools)"), h("ul", { class: "list compact" }, skills.length ? skills : none("None yet.")),
      section("Tool proposals waiting for you"), h("ul", { class: "list" }, proposals.length ? proposals : none("None.")),
      section("Dynamic tools" + (d.dynamic_tools_disabled ? " (disabled by env)" : "")),
      h("ul", { class: "list compact" }, tools.length ? tools : none("None created.")));
  }

  async function refresh() {
    try {
      const res = await fetch("/api/autonomy");
      render(await res.json());
      loadLog();
    } catch (e) { /* keep last render */ }
  }

  window.refreshAutonomy = () => { if (panel.classList.contains("active")) refresh(); };
  document.querySelector('.tab-btn[data-tab="autonomy"]').addEventListener("click", refresh);
  setInterval(window.refreshAutonomy, 10000);
})();
