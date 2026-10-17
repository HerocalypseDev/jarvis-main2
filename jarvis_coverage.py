"""Which dashboard action can Jarvis do too? (2026-10-16, "see and manage everything I can do", PR 3)

Every state-changing thing the dashboard can do is listed here, with how Jarvis covers it:
  tool    - an agent tool does the same thing (`tool`, and `action` when the tool has an action enum)
  owner   - deliberately the owner's alone (approving a staged shutdown, turning autonomy on, biometric erasure, ...)
  command - done by telling Jarvis something in a normal message (the dashboard box is just another way to say it)
  input   - the dashboard's own input surface
Keys: "feature:<name>:<action>" for every @_feature handler action (the Toolbox and Home cards) and
"route:<METHOD> <path>" for every state-changing route in jarvis_dashboard.py.

`test_coverage.py` scans the code for both lists and fails when one is missing here, so a new dashboard button
cannot ship without a decision: add a tool action, or write down why it stays with the owner.
Pure data: no import of jarvis.py.
"""
from __future__ import annotations


def _tool(tool: str, action: str | None = None, note: str = "") -> dict:
    return {"how": "tool", "tool": tool, "action": action, "note": note}


def _owner(why: str) -> dict:
    return {"how": "owner", "why": why}


def _command(note: str) -> dict:
    return {"how": "command", "note": note}


COVERAGE: dict[str, dict] = {
    # --- Toolbox / Home card actions (@_feature) -------------------------------------------------------------------
    "feature:license:activate": _owner("a licence key is a secret the owner pastes in; it never passes through the model"),
    "feature:license:deactivate": _owner("licence changes stay with the owner"),
    "feature:license:theme_css": _owner("serves the Pro theme stylesheet to the browser, nothing to decide"),
    "feature:clipboard:clear": _tool("clipboard_history", "clear"),
    "feature:clipboard:copy": _tool("clipboard_history", "get", "get with copy=true puts the item back on the clipboard"),
    "feature:clipboard:search": _tool("clipboard_history", "search"),
    "feature:devices:name": _tool("network_devices", "name"),
    "feature:missed:seen": _tool("housekeeping", "clear_missed"),
    "feature:running:cancel": _tool("running_now", "cancel"),
    "feature:asks:answer": _command("the card sends the question and the exact call as a normal command"),
    "feature:asks:dismiss": _tool("housekeeping", "dismiss_question"),
    "feature:macros:pack_toggle": _tool("macros", "enable", "enable/disable also switch a Pro routine"),
    "feature:meetings:start": _tool("meeting_notes", "start"),
    "feature:meetings:stop": _tool("meeting_notes", "stop"),
    "feature:meetings:transcript": _tool("meeting_notes", "get"),
    "feature:meetings:delete": _tool("meeting_notes", "delete"),
    "feature:files:find": _tool("find_files", "find"),
    "feature:files:index_watched": _tool("find_files", "index_watched"),
    "feature:shortcuts:add": _tool("app_shortcuts", "add"),
    "feature:shortcuts:delete": _tool("app_shortcuts", "delete"),
    "feature:shortcuts:run": _tool("app_shortcuts", "run"),
    "feature:email:save_template": _tool("email_reply", "save_template"),
    "feature:email:delete_template": _tool("email_reply", "delete_template"),
    "feature:email:suggest": _tool("email_reply", "suggest"),
    "feature:watches:check": _tool("watches", "check"),
    "feature:watches:delete": _tool("watches", "delete"),
    "feature:watches:off": _tool("watches", "off"),
    "feature:watches:on": _tool("watches", "on"),
    "feature:agents:create": _tool("background_agents", "create"),
    "feature:agents:delete": _tool("background_agents", "delete"),
    "feature:agents:disable": _tool("background_agents", "disable"),
    "feature:agents:enable": _tool("background_agents", "enable"),
    "feature:agents:run": _tool("background_agents", "run"),
    "feature:notifications:reset": _tool("housekeeping", "reset_notification_stats"),
    "feature:graph:query": _tool("knowledge_graph", "query"),
    "feature:graph:sync": _tool("knowledge_graph", "sync"),
    "feature:phones:ask": _tool("phone_location", "where"),
    "feature:phones:send_setup": _tool("phone_location", "setup"),
    "feature:phones:pair": _owner("makes the secret pairing key; it never passes through the model"),
    "feature:phones:setup_code": _owner("shows the secret pairing code on the owner's own screen only"),
    "feature:phones:repair": _owner("a new key cuts off every phone until it is set up again: the owner's call"),
    "feature:phones:forget": _owner("removing a phone from the map is the owner's call"),
    "feature:caretaker:fix": _tool("caretaker", "fix"),
    "feature:caretaker:scan": _tool("caretaker", "scan"),
    "feature:caretaker:undo": _tool("caretaker", "undo"),
    "feature:caretaker:ignore": _tool("caretaker", "ignore"),
    "feature:caretaker:unignore": _tool("caretaker", "unignore"),
    "feature:caretaker:forget_lesson": _tool("caretaker", "forget_lesson"),
    "feature:caretaker:helper_install": _tool("caretaker", "install_helper", "attended only; Windows asks the owner"),
    "feature:caretaker:helper_remove": _tool("caretaker", "remove_helper", "attended only; Windows asks the owner"),
    "feature:caretaker:helper_refresh": _tool("caretaker", "helper", "a status read"),
    "feature:deferred:cancel": _tool("scheduled_jobs", "cancel"),
    # --- state-changing dashboard routes ---------------------------------------------------------------------------
    "route:POST /api/memory/facts": _tool("remember_fact"),
    "route:POST /api/memory/facts/{fact_id}": _tool("remember_fact", None, "a new wording replaces the old fact"),
    "route:DELETE /api/memory/facts/{fact_id}": _tool("forget_fact"),
    "route:POST /api/memory/profile": _tool("housekeeping", "profile_set"),
    "route:DELETE /api/memory/profile/{key}": _tool("housekeeping", "profile_delete"),
    "route:POST /api/safe_mode": _tool("safe_mode"),
    "route:POST /api/feature/{name}/{action}": {"how": "feature", "note": "each feature action has its own feature: entry"},
    "route:POST /api/settings": _tool("settings", "set", "secrets, paths, addresses, camera stay the owner's"),
    "route:POST /api/llm": _tool("set_llm_provider"),
    "route:DELETE /api/sessions/finished": _tool("housekeeping", "clear_finished_sessions"),
    "route:POST /api/pending/approve": _owner("approving a staged shutdown/format/wipe/force-close is the owner's yes"),
    "route:POST /api/pending/reject": _owner("answering the confirmation gate stays with the owner"),
    "route:POST /api/tasks/{task_id}/stop": _tool("stop_background_task"),
    "route:POST /api/command": {"how": "input", "note": "the dashboard's own command box"},
    "route:DELETE /api/faces/snapshots": _owner("biometric pictures are erased by the owner only"),
    "route:DELETE /api/faces/{profile_id}": _tool("delete_face", None, "asks twice, never from a phone or unattended run"),
    "route:POST /api/faces/away": _tool("away_mode"),
    "route:POST /api/faces/pause": _tool("face_privacy"),
    "route:POST /api/autonomy/enabled": _owner("turning autonomy on is configuration, dashboard only"),
    "route:POST /api/autonomy/dry_run": _owner("leaving dry run is configuration, dashboard only"),
    "route:POST /api/autonomy/suggestions/{sid}/{verb}": _tool("autonomy", None, "approve/dismiss: attended only"),
    "route:POST /api/autonomy/policies": _owner("writing or loosening policy rules is dashboard only"),
    "route:DELETE /api/autonomy/policies/{pid}": _owner("changing policy rules is dashboard only"),
    "route:POST /api/autonomy/commitments/{cid}/status": _tool("autonomy", None, "complete/cancel_commitment: attended only"),
    "route:POST /api/autonomy/commitments/{cid}/accept": _tool("autonomy", None, "accept_commitment: attended only"),
    "route:POST /api/autonomy/organise/rules": _tool("autonomy_organise", "add_rule"),
    "route:DELETE /api/autonomy/organise/rules/{name}": _tool("autonomy_organise", "remove_rule"),
    "route:POST /api/autonomy/organise/roots": _tool("autonomy_organise", "add_root"),
    "route:POST /api/autonomy/organise/roots/remove": _tool("autonomy_organise", "remove_root"),
    "route:POST /api/autonomy/skills/{name}/{verb}": _tool("autonomy_skill"),
    "route:POST /api/autonomy/campaigns/approve": _tool("autonomy", None, "approve_campaign: attended only"),
    "route:POST /api/autonomy/campaigns/action": _tool("autonomy", None, "add_action: attended only"),
    "route:POST /api/dynamic_tools/proposals/{pid}/{verb}": _owner("approving code the AI wrote is the owner's call"),
    "route:POST /api/dynamic_tools/{name}/{verb}": _tool("manage_dynamic_tool"),
    "route:DELETE /api/dynamic_tools/{name}": _owner("deleting an AI-written tool is the owner's call"),
}


def problems(feature_actions: set[str], routes: set[str], tool_names: set[str],
             tool_actions: dict[str, set[str]]) -> list[str]:
    """What is wrong with the map: unlisted buttons, stale entries, tools or actions that don't exist."""
    out = []
    for key in sorted((feature_actions | routes) - set(COVERAGE)):
        out.append(f"{key}: not in jarvis_coverage.COVERAGE (add a tool action, or say why it is the owner's)")
    for key in sorted(set(COVERAGE) - (feature_actions | routes)):
        out.append(f"{key}: listed but the dashboard no longer has it")
    for key, e in sorted(COVERAGE.items()):
        if e["how"] == "owner" and not e.get("why"):
            out.append(f"{key}: an owner-only entry needs a reason")
        if e["how"] != "tool":
            continue
        if e["tool"] not in tool_names:
            out.append(f"{key}: no tool called {e['tool']}")
        elif e.get("action") and e["action"] not in tool_actions.get(e["tool"], set()):
            out.append(f"{key}: {e['tool']} has no action {e['action']}")
    return out
