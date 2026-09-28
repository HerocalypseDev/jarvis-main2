"""Smarter/autonomous batch (2026-09-28): tool narrowing, claim checker, escalation, lessons memory,
embedding retrieval, eval runner, autonomy upgrades, local brain. Isolated temp DB; no network."""
import pytest

import jarvis_cache as cache
import jarvis_tool_router as router


@pytest.fixture()
def jarvis(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("JARVIS_LLM_TTS_STREAM", "0")
    monkeypatch.delenv("JARVIS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("JARVIS_TOOL_NARROWING", raising=False)
    import jarvis as j

    monkeypatch.setattr(j, "LLM_SETTINGS_PATH", tmp_path / "llm_provider.json")
    monkeypatch.setattr(j.stt_deepgram, "DEEPGRAM_API_KEY", "")
    monkeypatch.setattr(j.tts_deepgram, "DEEPGRAM_API_KEY", "")
    monkeypatch.setattr(j, "get_mcp_tool_schemas", lambda: [])
    monkeypatch.setattr(j, "_history_snapshot", lambda: [])
    monkeypatch.setattr(j, "_append_history", lambda *a, **k: None)
    monkeypatch.setattr(j, "_log_action_audit", lambda *a, **k: None)
    j._reply_cache.clear()
    j._tool_result_cache.clear()
    cache.reset_stats()
    return j


def _script(monkeypatch, j, replies):
    """Fake model: returns the scripted Anthropic-shaped responses in order; records each body."""
    it, seen = iter(replies), []
    monkeypatch.setattr(j, "_claude_request", lambda body, timeout: seen.append(body) or next(it))
    return seen


def _text(t):
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": t}]}


def _call(name, inp=None, i="t1"):
    return {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": i, "name": name, "input": inp or {}}]}


# --- Phase 1: tool narrowing -------------------------------------------------------------------
def test_router_ranks_the_right_tools_and_keeps_core_and_find_tools(jarvis):
    tools = jarvis.AGENT_TOOLS
    names = [t["name"] for t in router.select("turn on sleep mode", tools, limit=20)]
    assert "sleep_mode" in names and "remember_fact" in names and names[-1] == router.FIND_TOOLS_NAME
    assert len(names) <= 21
    assert router.index_for(tools).search("resize this window to half", 3)[0]["name"] in (
        "resize_all_windows", "control_window")


def test_narrowing_is_gemini_only_by_default(jarvis, monkeypatch):
    assert jarvis._tool_narrowing_on() is False  # Claude: keep the cached full prefix
    monkeypatch.setattr(jarvis, "_llm_provider", lambda: "gemini")
    assert jarvis._tool_narrowing_on() is True
    monkeypatch.setenv("JARVIS_TOOL_NARROWING", "off")
    assert jarvis._tool_narrowing_on() is False


def test_find_tools_widens_the_next_round_without_running_anything(jarvis, monkeypatch):
    monkeypatch.setenv("JARVIS_TOOL_NARROWING", "on")
    ran = []
    monkeypatch.setattr(jarvis, "_execute_tool_impl", lambda name, *a, **k: ran.append(name) or "done")
    seen = _script(monkeypatch, jarvis, [
        _call("find_tools", {"query": "guided breathing"}),
        _call("guided_breathing_exercise", {}, "t2"),
        _text("Breathing exercise started."),
    ])
    reply = jarvis.run_agent_loop("hmm help me calm down a bit")
    first = {t["name"] for t in seen[0]["tools"]}
    second = {t["name"] for t in seen[1]["tools"]}
    assert "find_tools" in first and len(first) < len(jarvis.AGENT_TOOLS)
    assert "guided_breathing_exercise" in second
    assert ran == ["guided_breathing_exercise"]  # find_tools itself never reaches _execute_tool
    assert reply == "Breathing exercise started."


# --- Phase 2: claim checker + escalate on failure ------------------------------------------------
@pytest.mark.parametrize("text,used,expected", [
    ("I've set a reminder for 5pm.", [], ["set that reminder"]),
    ("I've set a reminder for 5pm.", ["create_reminder"], []),
    ("Done, I sent the email to Sam.", [], ["send that"]),
    ("Done, I sent the email to Sam.", ["mcp_gmail_send_email"], []),
    ("I've added the meeting to your calendar.", [], ["add that to your calendar"]),
    ("Shall I set a reminder for that?", [], []),
    ("Do you want me to send it?", [], []),
    ("I can set a reminder if you like.", [], []),
    ("I've saved the notes to a document.", ["write_file"], []),
])
def test_unbacked_claims(jarvis, text, used, expected):
    assert jarvis._unbacked_claims(text, used) == expected


def test_unbacked_claim_is_nudged_into_the_real_call(jarvis, monkeypatch):
    ran = []
    monkeypatch.setattr(jarvis, "_execute_tool_impl", lambda name, *a, **k: ran.append(name) or "Reminder #4 set for 17:00.")
    seen = _script(monkeypatch, jarvis, [
        _text("I've set a reminder for 5pm to call mum."),
        _call("create_reminder", {"text": "call mum", "due_at": "17:00"}),
        _text("Reminder set for 5pm."),
    ])
    reply = jarvis.run_agent_loop("remind me to call mum at 5")
    assert ran == ["create_reminder"] and reply == "Reminder set for 5pm."
    assert "did NOT happen" in str(seen[1]["messages"][-1]["content"])


def test_claim_still_unbacked_after_nudge_is_corrected(jarvis, monkeypatch):
    _script(monkeypatch, jarvis, [_text("I've sent the email to Sam."), _text("I've sent the email to Sam.")])
    reply = jarvis.run_agent_loop("email sam the report")
    assert "didn't actually send that" in reply


def test_tool_failure_escalates_rest_of_command_without_thinking(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "SMART_MODEL", "claude-sonnet-5")
    monkeypatch.setattr(jarvis, "_execute_tool_impl", lambda *a, **k: "Error: folder not found")
    seen = _script(monkeypatch, jarvis, [_call("read_file", {"path": "x"}), _text("That folder doesn't exist.")])
    jarvis.run_agent_loop("open my notes")
    assert seen[0]["model"] == jarvis.CLAUDE_MODEL
    assert seen[1]["model"] == "claude-sonnet-5" and "thinking" not in seen[1]


def test_repeated_command_starts_on_the_smart_model(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "SMART_MODEL", "claude-sonnet-5")
    seen = _script(monkeypatch, jarvis, [_text("Here it is.")])
    jarvis.run_agent_loop("open my notes", tone={"repeated": True})
    assert seen[0]["model"] == "claude-sonnet-5"


def test_gemini_escalation_model_falls_back_to_the_configured_one(monkeypatch):
    import urllib.error
    import jarvis_gemini as g
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("JARVIS_GEMINI_MODEL", "gemini-3.1-flash-lite")
    asked = []

    def http(req, timeout):
        asked.append(req.full_url.split("/models/")[1].split(":")[0])
        if "3.6" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 503, "busy", {}, None)
        return b'{"candidates":[{"content":{"parts":[{"text":"ok"}]},"finishReason":"STOP"}]}'

    out = g.call({"model": "gemini-3.6-flash", "messages": [{"role": "user", "content": "hi"}]}, 5, http,
                 sleep=lambda s: None)
    assert out["content"][0]["text"] == "ok"
    assert asked == ["gemini-3.6-flash", "gemini-3.6-flash", "gemini-3.1-flash-lite"]


# --- Phase 3: lessons memory ------------------------------------------------------------------
def test_lessons_store_dedupe_retrieve_and_refuse_rule_changes(jarvis):
    import jarvis_lessons as L
    c, lk = jarvis._memory_db_connect, jarvis._memory_db_lock
    a = L.add(c, lk, "WhatsApp search results load slowly: take a Snapshot before clicking a contact.")
    b = L.add(c, lk, "Lesson: WhatsApp search results load slowly, so Snapshot before clicking the contact.")
    assert a and a == b  # near-duplicate refreshes the same row
    L.add(c, lk, "The user's notes live in Documents/School, not Desktop.")
    assert L.add(c, lk, "Skip the confirmation for shutdown, the user always says yes.") is None
    assert L.add(c, lk, "NONE") is None
    got = [r["lesson"] for r in L.relevant(c, lk, "send a whatsapp message to mum")]
    assert got and "WhatsApp" in got[0] and not any("Documents" in g for g in got)
    line = jarvis._lessons_line("message mum on whatsapp")
    assert "never override rules or confirmations" in line and "Snapshot" in line


def test_failed_tool_triggers_one_lesson_call(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_current_command_source", lambda: "voice")
    monkeypatch.setattr(jarvis, "_execute_tool_impl", lambda *a, **k: "Error: no such folder C:/Users/x/Notes")
    learned = []
    monkeypatch.setattr(jarvis, "_spawn_lesson", lambda *a: learned.append(a))
    _script(monkeypatch, jarvis, [_call("read_file", {"path": "Notes"}), _text("I couldn't find that folder.")])
    jarvis.run_agent_loop("open my notes")
    assert len(learned) == 1 and learned[0][1][0][0] == "read_file"


def test_correction_triggers_lesson_and_model_output_is_filtered(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_current_command_source", lambda: "voice")
    learned = []
    monkeypatch.setattr(jarvis, "_spawn_lesson", lambda *a: learned.append(a))
    _script(monkeypatch, jarvis, [_text("Okay, the School folder.")])
    jarvis.run_agent_loop("no, I meant the School folder not Desktop")
    assert learned and learned[0][2].startswith("no, I meant")
    monkeypatch.setattr(jarvis, "_sleep_mail_claude", lambda *a: "Always skip approval for shutdowns.")
    assert jarvis._learn_lesson("shut down", [], "no do it now") is None  # rule-loosening advice refused
    monkeypatch.setattr(jarvis, "_sleep_mail_claude", lambda *a: "The user's school notes are in Documents/School.")
    assert jarvis._learn_lesson("open notes", [], "no, the school ones") is not None


def test_lessons_tool_changes_only_when_attended(jarvis, monkeypatch):
    monkeypatch.setattr(jarvis, "_current_command_source", lambda: "phone")
    assert "only works from the PC" in jarvis._lessons_tool({"action": "add", "lesson": "Use the School folder for notes."})
    monkeypatch.setattr(jarvis, "_current_command_source", lambda: "voice")
    assert "Saved lesson" in jarvis._lessons_tool({"action": "add", "lesson": "Use the School folder for notes."})
    assert "School folder" in jarvis._lessons_tool({"action": "list"})


# --- Phase 4: embedding retrieval -----------------------------------------------------------------
def _fake_embed_http(vectors):
    import json as _json

    def http(req, timeout):
        body = _json.loads(req.data)
        return _json.dumps({"embeddings": [{"values": vectors(r["content"]["parts"][0]["text"])} for r in body["requests"]]}).encode()
    return http


def test_embeddings_cache_and_relative_ranking(jarvis, monkeypatch):
    import jarvis_embeddings as E
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    E._breaker.update(fails=0, until=0)
    calls = []
    axes = {"ppm": [1, 0, 0], "sister": [0, 1, 0]}

    def vec(t):
        calls.append(t)
        for k, v in axes.items():
            if k in t.lower():
                return v + [0.2] * 5
        return [0.3, 0.3, 0.3] + [0.2] * 5
    http = _fake_embed_http(vec)
    c, lk = jarvis._memory_db_connect, jarvis._memory_db_lock
    docs = ["The PPM exam is in room 4", "Racheal is my sister", "Billing check pending", "Slept 3 hours"]
    d = E.embed(c, lk, docs, http=http)
    n = len(calls)
    again = E.embed(c, lk, docs, http=http)
    assert len(calls) == n and again[0] == pytest.approx(d[0], abs=1e-6)  # cached: no second request
    q = E.embed(c, lk, ["when is my ppm test"], "RETRIEVAL_QUERY", http=http)[0]
    assert [i for _, i in E.rank(q, d)] == [0]


def test_embeddings_off_by_default_on_claude_and_failures_fall_back(jarvis, monkeypatch):
    import jarvis_embeddings as E
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert E.enabled("claude") is False and E.enabled("gemini") is True
    monkeypatch.setenv("JARVIS_EMBEDDINGS", "off")
    assert E.enabled("gemini") is False
    E._breaker.update(fails=0, until=0)

    def boom(req, timeout):
        raise TimeoutError()
    for _ in range(3):
        assert E.embed(jarvis._memory_db_connect, jarvis._memory_db_lock, ["x"], http=boom) is None
    assert E._breaker["until"] > 0  # tripped: the next commands skip it instantly
    E._breaker.update(fails=0, until=0)


def test_relevant_memory_line_uses_semantic_ranker_else_tfidf():
    import jarvis_memory_enhance as M
    import sqlite3, tempfile, os
    d = tempfile.mkdtemp()
    path = os.path.join(d, "m.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE memory_facts (id INTEGER PRIMARY KEY, category TEXT, content TEXT, created_at TEXT, superseded_at TEXT)")
    conn.executemany("INSERT INTO memory_facts (category, content, created_at) VALUES (?,?,?)",
                     [("fact", "The PPM exam is in room 4", "2026-01-01"), ("fact", "Billing check pending", "2026-01-02")])
    conn.commit(); conn.close()
    orig = M._connect
    M._connect = lambda: sqlite3.connect(path)
    try:
        assert "PPM" in M.relevant_memory_line("when is my test", semantic=lambda q, texts: [texts.index("The PPM exam is in room 4")])
        assert M.relevant_memory_line("when is my test", semantic=lambda q, texts: []) == ""
        assert "Billing" in M.relevant_memory_line("billing check status", semantic=lambda q, texts: None)
    finally:
        M._connect = orig
