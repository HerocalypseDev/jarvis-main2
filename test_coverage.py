"""PR 3 of "Jarvis sees and manages everything the owner can" (2026-10-16): the small dashboard actions as tools
(`housekeeping`, meeting delete, caretaker unignore/forget_lesson, Pro routine switch) and the coverage map that keeps
every dashboard button matched to a tool or a written reason. Temp DB only."""
import ast
from pathlib import Path

import pytest

import jarvis_coverage as cov

ROOT = Path(__file__).resolve().parent


# --- the map itself ---------------------------------------------------------------------------------------------
def _feature_actions() -> set[str]:
    tree = ast.parse((ROOT / "jarvis.py").read_text(encoding="utf-8"))
    out = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        name = next((d.args[0].value for d in fn.decorator_list if isinstance(d, ast.Call)
                     and getattr(d.func, "id", "") == "_feature"), None)
        if not name:
            continue
        for n in ast.walk(fn):
            if isinstance(n, ast.Compare) and isinstance(n.left, ast.Name) and n.left.id == "action":
                for c in n.comparators:
                    vals = [c] if isinstance(c, ast.Constant) else list(getattr(c, "elts", []))
                    out |= {f"feature:{name}:{v.value}" for v in vals
                            if isinstance(v, ast.Constant) and isinstance(v.value, str) and v.value != "get"}
    return out


def _routes() -> set[str]:
    tree = ast.parse((ROOT / "jarvis_dashboard.py").read_text(encoding="utf-8"))
    out = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for d in fn.decorator_list:
            if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and getattr(d.func.value, "id", "") == "app"
                    and d.func.attr in ("post", "delete", "put", "patch")):
                out.add(f"route:{d.func.attr.upper()} {d.args[0].value}")
    return out


def test_scanners_actually_find_things():
    # a scanner that finds nothing would make the consistency test pass for the wrong reason
    assert len(_feature_actions()) >= 40 and "feature:caretaker:unignore" in _feature_actions()
    assert len(_routes()) >= 30 and "route:POST /api/pending/approve" in _routes()


def test_every_dashboard_action_is_matched_to_a_tool_or_a_reason(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "c.db"))
    import jarvis as j
    names = {t["name"] for t in list(j.AGENT_TOOLS) + list(j.FACE_TOOLS)}
    actions = {t["name"]: set(((t.get("input_schema") or {}).get("properties", {}).get("action") or {}).get("enum") or [])
               for t in list(j.AGENT_TOOLS) + list(j.FACE_TOOLS)}
    assert cov.problems(_feature_actions(), _routes(), names, actions) == []


def test_problems_reports_each_kind_of_mistake():
    out = cov.problems({"feature:x:new_button"}, {"route:POST /api/pending/approve"}, {"housekeeping"},
                       {"housekeeping": {"profile_set"}})
    text = "\n".join(out)
    assert "feature:x:new_button: not in" in text            # a button nobody decided about
    assert "feature:caretaker:fix: listed but" in text       # a map entry for a button that is gone
    assert "no tool called caretaker" in text                # a tool that doesn't exist
    assert "housekeeping has no action clear_missed" in text  # an action the tool doesn't have


def test_owner_only_entries_all_say_why():
    owners = [k for k, e in cov.COVERAGE.items() if e["how"] == "owner"]
    assert owners and all(cov.COVERAGE[k]["why"].strip() for k in owners)
    # the things the owner kept for themselves, by name
    for k in ("route:POST /api/pending/approve", "route:POST /api/autonomy/enabled", "feature:license:activate"):
        assert cov.COVERAGE[k]["how"] == "owner", k


# --- the new tool actions ---------------------------------------------------------------------------------------
@pytest.fixture
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "h.db"))
    import jarvis as j
    j._command_ctx.source = "voice"
    for a in ("untrusted_origin", "outside_text_seen", "hands_free", "wake", "autonomous"):
        setattr(j._command_ctx, a, False)
    yield j
    j._command_ctx.source = None


def test_housekeeping_is_a_registered_tool_blocked_for_outside_text(J):
    t = next(t for t in J.AGENT_TOOLS if t["name"] == "housekeeping")
    assert set(t["input_schema"]["properties"]["action"]["enum"]) == set(J.HOUSEKEEPING_ACTIONS)
    J._command_ctx.untrusted_origin = True
    assert J._untrusted_block("housekeeping")
    J._command_ctx.untrusted_origin = False
    J._command_ctx.outside_text_seen = True
    assert J._taint_block("housekeeping")


def test_housekeeping_only_for_the_owner(J, monkeypatch):
    called = []
    monkeypatch.setattr(J, "_reset_notification_stats", lambda: called.append(1))
    run = lambda: J._execute_tool("housekeeping", {"action": "reset_notification_stats"}, "x")  # noqa: E731
    J._command_ctx.untrusted_origin = True
    assert run().startswith("Refused")
    J._command_ctx.untrusted_origin = False
    J._command_ctx.source = None  # a scheduled run
    assert run().startswith("Tool failed")
    J._command_ctx.source = "voice"
    J._command_ctx.hands_free = True  # follow-up window, not 'Hey Jarvis'
    assert run().startswith("Tool failed")
    assert called == []
    J._command_ctx.hands_free = False
    assert "Forgot" in run() and called == [1]


def test_housekeeping_unknown_action(J):
    assert J._execute_tool("housekeeping", {"action": "format_c"}, "x").startswith("Tool failed")


def test_clear_missed_and_finished_sessions_and_stats(J, monkeypatch):
    J.missed.add(J._memory_db_connect, J._memory_db_lock, "Something quiet happened", "test")
    assert "Cleared 1 item" in J._execute_tool("housekeeping", {"action": "clear_missed"}, "mark read")
    assert "nothing to clear" in J._execute_tool("housekeeping", {"action": "clear_missed"}, "mark read")
    monkeypatch.setattr(J.dashboard, "clear_finished_sessions", lambda: 3)
    assert "Removed 3 finished sessions" in J._execute_tool("housekeeping", {"action": "clear_finished_sessions"}, "x")
    assert "Forgot" in J._execute_tool("housekeeping", {"action": "reset_notification_stats"}, "x")
    assert J.notify_priority.stats(J._memory_db_connect, J._memory_db_lock) == {}


def test_dismiss_question(J, monkeypatch):
    rows = {5: {"id": 5, "status": "open"}, 6: {"id": 6, "status": "answered"}}
    closed = []
    monkeypatch.setattr(J.asks_mod, "get", lambda c, l, i: rows.get(i))
    monkeypatch.setattr(J.asks_mod, "close", lambda c, l, i, why: closed.append((i, why)))
    assert "Dismissed question #5" in J._execute_tool("housekeeping", {"action": "dismiss_question", "id": 5}, "x")
    assert closed == [(5, "dismissed")]
    assert J._execute_tool("housekeeping", {"action": "dismiss_question", "id": 6}, "x").startswith("Tool failed")
    assert J._execute_tool("housekeeping", {"action": "dismiss_question"}, "x").startswith("Tool failed")
    assert closed == [(5, "dismissed")]


def test_profile_set_and_delete_with_the_dashboards_limits(J):
    out = J._execute_tool("housekeeping", {"action": "profile_set", "key": "city", "value": "Lagos"}, "x")
    assert "Saved" in out
    assert "city" in J.get_user_profile_context() and "Lagos" in J.get_user_profile_context()
    assert J._execute_tool("housekeeping", {"action": "profile_set", "key": "k" * 61, "value": "v"}, "x").startswith("Tool failed")
    assert J._execute_tool("housekeeping", {"action": "profile_set", "key": "k", "value": "v" * 501}, "x").startswith("Tool failed")
    assert J._execute_tool("housekeeping", {"action": "profile_set", "key": "k"}, "x").startswith("Tool failed")
    assert "Removed" in J._execute_tool("housekeeping", {"action": "profile_delete", "key": "city"}, "x")
    assert J._execute_tool("housekeeping", {"action": "profile_delete", "key": "city"}, "x").startswith("Tool failed")


def test_profile_refuses_secrets(J):
    out = J._execute_tool("housekeeping", {"action": "profile_set", "key": "bank password", "value": "hunter2"}, "x")
    assert out.startswith("Refused")
    fake_key = "sk-" + "ant-api03-" + "A" * 40
    out = J._execute_tool("housekeeping", {"action": "profile_set", "key": "note", "value": fake_key}, "x")
    assert out.startswith("Refused")
    assert "hunter2" not in J.get_user_profile_context() and "ant-api03" not in J.get_user_profile_context()


def test_meeting_delete_checks_owner_and_the_meeting(J, monkeypatch):
    deleted = []
    monkeypatch.setattr(J.meeting, "list_meetings", lambda store, n: [{"id": 4, "title": "t"}])
    monkeypatch.setattr(J.meeting, "delete_meeting", lambda store, i: deleted.append(i))
    J._command_ctx.untrusted_origin = True
    assert J._execute_tool("meeting_notes", {"action": "delete", "id": 4}, "x").startswith("Refused")
    J._command_ctx.untrusted_origin = False
    assert J._execute_tool("meeting_notes", {"action": "delete", "id": 9}, "x").startswith("Tool failed")
    assert J._execute_tool("meeting_notes", {"action": "delete"}, "x").startswith("Tool failed")
    assert deleted == []
    assert "Deleted" in J._execute_tool("meeting_notes", {"action": "delete", "id": 4}, "delete meeting 4")
    assert deleted == [4]


class _FakeStore:
    def __init__(self):
        self.issues = {"disk": {"key": "disk", "status": "ignored"}, "net": {"key": "net", "status": "open"}}
        self.lessons_ = {"network|dns": {"sig": "network|dns"}}
        self.log = []

    def get(self, key):
        return self.issues.get(key)

    def set_status(self, key, status):
        self.issues[key]["status"] = status
        self.log.append((key, status))

    def lesson_get(self, sig):
        return self.lessons_.get(sig)

    def lessons(self):
        return list(self.lessons_.values())

    def lesson_delete(self, sig):
        self.lessons_.pop(sig, None)


def test_caretaker_unignore_and_forget_lesson(J, monkeypatch):
    store = _FakeStore()
    monkeypatch.setattr(J, "_caretaker_store", store)
    assert "again" in J._execute_tool("caretaker", {"action": "unignore", "key": "disk"}, "x")
    assert store.issues["disk"]["status"] == "open"
    assert "isn't ignored" in J._execute_tool("caretaker", {"action": "unignore", "key": "net"}, "x")
    assert J._execute_tool("caretaker", {"action": "unignore", "key": "nope"}, "x").startswith("Tool failed")
    assert "Forgot" in J._execute_tool("caretaker", {"action": "forget_lesson", "sig": "network|dns"}, "x")
    assert store.lessons_ == {}
    out = J._execute_tool("caretaker", {"action": "forget_lesson", "sig": "network|dns"}, "x")
    assert out.startswith("Tool failed")


def test_caretaker_changes_need_the_owner(J, monkeypatch):
    store = _FakeStore()
    monkeypatch.setattr(J, "_caretaker_store", store)
    J._command_ctx.source = None  # unattended
    assert J._execute_tool("caretaker", {"action": "unignore", "key": "disk"}, "x").startswith("Tool failed")
    assert J._execute_tool("caretaker", {"action": "forget_lesson", "sig": "network|dns"}, "x").startswith("Tool failed")
    assert store.issues["disk"]["status"] == "ignored" and store.lessons_


def test_macros_enable_switches_a_pro_routine(J, monkeypatch):
    saved = {}
    monkeypatch.setattr(J, "_pack_macros", lambda: [{"name": "Study Mode"}])
    monkeypatch.setattr(J.settings, "set_setting", lambda k, v: saved.update({k: v}) or {"ok": True})
    monkeypatch.delenv(J.PRO_MACROS_OFF_KEY, raising=False)
    assert "now off" in J._execute_tool("macros", {"action": "disable", "name": "study mode"}, "x")
    assert saved == {J.PRO_MACROS_OFF_KEY: "study mode"}
    monkeypatch.setenv(J.PRO_MACROS_OFF_KEY, "study mode")
    assert "now on" in J._execute_tool("macros", {"action": "enable", "name": "Study Mode"}, "x")
    assert saved[J.PRO_MACROS_OFF_KEY] == ""
    # not attended (phone): Pro routine untouched, normal refusal from the macros tool
    saved.clear()
    J._command_ctx.source = "phone"
    assert "only be changed from the PC" in J._execute_tool("macros", {"action": "disable", "name": "Study Mode"}, "x")
    assert saved == {}


def test_a_users_own_macro_wins_over_a_pro_routine_of_the_same_name(J, monkeypatch):
    saved = {}
    monkeypatch.setattr(J, "_pack_macros", lambda: [{"name": "Focus"}])
    monkeypatch.setattr(J.settings, "set_setting", lambda k, v: saved.update({k: v}) or {"ok": True})
    monkeypatch.setattr(J.macros, "list_macros", lambda c, l: [{"name": "focus"}])
    seen = {}
    monkeypatch.setattr(J.macros, "handle_tool", lambda *a, **k: seen.setdefault("hit", "own macro handled"))
    assert J._execute_tool("macros", {"action": "disable", "name": "focus"}, "x") == "own macro handled"
    assert saved == {}


def test_toolbox_switch_still_flips(J, monkeypatch):
    saved = {}
    monkeypatch.setattr(J, "_pack_macros", lambda: [{"name": "Study Mode"}])
    monkeypatch.setattr(J.settings, "set_setting", lambda k, v: saved.update({k: v}) or {"ok": True})
    monkeypatch.delenv(J.PRO_MACROS_OFF_KEY, raising=False)
    res = J._feature_macros("pack_toggle", {"name": "Study Mode"})
    assert "now off" in res["result"] and saved[J.PRO_MACROS_OFF_KEY] == "study mode"
    assert J._feature_macros("pack_toggle", {"name": "nope"})["result"] == "No Pro routine by that name."


def test_narrowing_offers_the_new_tools(J):
    assert "housekeeping" in J._narrowing_core("mark everything as read")
    assert "housekeeping" in J._narrowing_core("clear the finished sessions")
    assert "housekeeping" in J._narrowing_core("change my profile city to Abuja")
    assert "meeting_notes" in J._narrowing_core("delete the meeting notes from Monday")
    assert "caretaker" in J._narrowing_core("forget the learned fix for the network")
    assert "housekeeping" not in J._narrowing_core("what's the weather")
