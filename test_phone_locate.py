"""Phone locator (2026-10-17): pairing code, sealing, report checks, storage, the relay listener and the Jarvis wiring.
No network: the relay and the place lookup are faked. Temp DB only."""

import io
import json
import sqlite3

import pytest

import jarvis_latency as latency
import jarvis_phone_locate as pl

NOW = 1_800_000_000_000


@pytest.fixture
def pairing():
    p = pl.new_pairing()
    return ("https://ntfy.sh", p["topic"], p["key"])


@pytest.fixture
def store(tmp_path):
    db = str(tmp_path / "p.db")
    return pl.Store(lambda: sqlite3.connect(db))


def report(**kw):
    r = {"type": "loc", "id": "abcdef0123456789", "phone": "Tecno", "lat": 6.6018, "lon": 3.3515, "acc": 12.0,
         "sent_ts": NOW - 1000, "fix_ts": NOW - 2000, "battery": 54, "charging": False, "reason": "ask"}
    r.update(kw)
    return r


def test_setup_code_round_trip_and_rejects_garbage(pairing):
    code = pl.setup_code(*pairing)
    assert code.startswith("JLOC1.")
    got = pl.parse_setup_code("  " + code[:20] + "\n" + code[20:])  # pasted with a line break
    assert (got["server"], got["topic"], got["key"]) == pairing
    assert pl.parse_setup_code("hello") is None
    assert pl.parse_setup_code("JLOC1.bm90IGpzb24") is None
    bad = pl.setup_code("http://evil.example", pairing[1], pairing[2])
    assert pl.parse_setup_code(bad) is None  # never plain http


def test_sealed_messages_only_open_with_the_same_key_and_topic(pairing):
    _, topic, key = pairing
    text = pl.seal(key, topic, {"type": "ask", "ts": 1})
    assert pl.open_sealed(key, topic, text) == {"type": "ask", "ts": 1}
    assert "ask" not in text  # the relay sees random text
    other = pl.new_pairing()
    assert pl.open_sealed(other["key"], topic, text) is None
    assert pl.open_sealed(key, other["topic"], text) is None  # moved to another topic
    flipped = text[:-3] + ("A" if text[-3] != "A" else "B") + text[-2:]
    assert pl.open_sealed(key, topic, flipped) is None
    assert pl.open_sealed(key, topic, "not base64 !!") is None


def test_report_fields_are_checked():
    rep = pl.parse_report(report(), NOW)
    assert rep["kind"] == "loc" and rep["lat"] == 6.6018 and rep["battery"] == 54
    assert pl.parse_report(report(lat=91), NOW) is None
    assert pl.parse_report(report(lon="x"), NOW) is None
    assert pl.parse_report(report(id="../../etc"), NOW) is None
    assert pl.parse_report(report(sent_ts=NOW + 3_600_000), NOW) is None  # from the future
    assert pl.parse_report({"type": "ask", "ts": NOW}, NOW) is None  # our own ask
    assert pl.parse_report(report(phone="<script>x</script>" * 5), NOW)["name"].count("<") == 0
    nofix = pl.parse_report({"type": "nofix", "id": "abcdef0123456789", "sent_ts": NOW, "problem": "location_off"}, NOW)
    assert nofix["kind"] == "nofix" and nofix["problem"] == "location_off"


def test_store_keeps_latest_refuses_replays_and_caps_devices(store):
    assert store.record(pl.parse_report(report(), NOW), NOW) == "new"
    assert store.record(pl.parse_report(report(sent_ts=NOW - 500, lat=6.7), NOW), NOW) == "updated"
    # a replayed older message never moves the pin back
    assert store.record(pl.parse_report(report(sent_ts=NOW - 900, lat=1.0), NOW), NOW) == "stale"
    d = store.devices()[0]
    assert d["lat"] == 6.7 and d["recv_ts"] == NOW
    assert len(store.trail(d["id"], 0)) == 2
    nofix = pl.parse_report({"type": "nofix", "id": "abcdef0123456789", "sent_ts": NOW, "problem": "no_fix"}, NOW)
    store.record(nofix, NOW)
    d = store.devices()[0]
    assert d["lat"] == 6.7 and d["problem"] == "no_fix"  # the last position stays, the problem is added
    assert "couldn't get a GPS fix" in pl.describe(d, NOW)
    for i in range(pl.MAX_DEVICES - 1):
        store.record(pl.parse_report(report(id=f"dev{i:05d}aa", sent_ts=NOW), NOW), NOW)
    assert store.record(pl.parse_report(report(id="onetoomany99", sent_ts=NOW), NOW), NOW) == "full"
    assert store.forget("abcdef0123456789") and not store.trail("abcdef0123456789", 0)


def test_describe_and_matching(store):
    store.record(pl.parse_report(report(), NOW), NOW)
    store.record(pl.parse_report(report(id="1111222233334444", phone="Samsung A15"), NOW), NOW)
    devs = store.devices()
    store.set_place("abcdef0123456789", "Allen Avenue, Ikeja")
    d = [x for x in store.devices() if x["name"] == "Tecno"][0]
    text = pl.describe(d, NOW + 5 * 60000)
    assert "near Allen Avenue, Ikeja" in text and "within about 12 m" in text and "5 minutes ago" in text
    assert [x["name"] for x in pl.match_device(devs, "where's my samsung phone")] == ["Samsung A15"]
    assert pl.match_device(devs, "where are my phones") == []
    assert pl.short_place({"name": "", "address": {"road": "Allen Avenue", "suburb": "Ikeja", "city": "Lagos",
                                                    "postcode": "100001", "country": "Nigeria"}}) == \
        "Allen Avenue, Ikeja, Lagos"


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_listener_records_only_sealed_reports_and_ask_is_sealed(store, pairing):
    server, topic, key = pairing
    lines = [json.dumps({"event": "open"}),
             json.dumps({"event": "message", "id": "m1", "message": "stranger says hi"}),
             json.dumps({"event": "message", "id": "m2", "message": pl.seal(key, topic, report(sent_ts=NOW))}),
             json.dumps({"event": "keepalive"})]
    sent = []

    def opener(req, timeout=0):
        if req.data:
            sent.append((req.full_url, req.data.decode()))
            return FakeResp(b"{}")
        assert "since=" in req.full_url
        return FakeResp(("\n".join(lines) + "\n").encode())

    seen = []
    loc = pl.Locator(store, lambda: pairing, on_report=lambda r, s: seen.append((r["name"], s)), opener=opener,
                     now_ms=lambda: NOW)
    loc._listen_once()
    assert seen == [("Tecno", "new")] and loc._since == "m2"
    assert loc.ask("abcdef0123456789")
    url, body = sent[0]
    assert url == f"{server}/{topic}"
    ask = pl.open_sealed(key, topic, body)
    assert ask["type"] == "ask" and ask["phone"] == "abcdef0123456789" and ask["ts"] == NOW
    assert loc.wait_for(["abcdef0123456789"], NOW - 1, 0.1) == {"abcdef0123456789"}
    assert loc.wait_for(["abcdef0123456789"], NOW + 1, 0.1) == set()


def test_unpaired_locator_does_nothing(store):
    loc = pl.Locator(store, lambda: None)
    assert loc.ask() is False and loc.handle_text("x") is None
    assert pl.env_config({}) is None
    assert pl.env_config({pl.ENV_TOPIC: "short", pl.ENV_KEY: "AAAA"}) is None


@pytest.mark.parametrize("text,want", [
    ("where's my phone", "phone_where"), ("Where are my phones, show me visually", "phone_where"),
    ("Hey Jarvis, where is my Samsung phone?", "phone_where"), ("show my phones on the map", "phone_where"),
    ("where is my phone charger", "complex"), ("what's my phone number", "complex"),
])
def test_voice_phrases(text, want):
    assert latency.classify_intent(text) == want


# --- Jarvis wiring ------------------------------------------------------------------------------------------------
@pytest.fixture
def J(monkeypatch, tmp_path, pairing):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "j.db"))
    monkeypatch.setenv(pl.ENV_TOPIC, pairing[1])
    monkeypatch.setenv(pl.ENV_KEY, pairing[2])
    monkeypatch.delenv("JARVIS_PHONE_LOCATOR", raising=False)
    import jarvis as j
    j._command_ctx.source = "voice"
    for a in ("untrusted_origin", "outside_text_seen", "hands_free", "wake", "autonomous"):
        setattr(j._command_ctx, a, False)
    monkeypatch.setattr(j.phone_locate, "nominatim_reverse", lambda lat, lon, timeout=8: "Allen Avenue, Ikeja")
    yield j


def test_tool_answers_from_the_last_check_in(J):
    rep = pl.parse_report(report(sent_ts=int(J.time.time() * 1000)), int(J.time.time() * 1000) + 1)
    J._phone_store.record(rep, int(J.time.time() * 1000))
    out = J._phone_location_tool({"action": "last"})
    assert "Tecno: near Allen Avenue, Ikeja" in out and "battery 54%" in out


def test_where_asks_and_says_who_did_not_answer(J, monkeypatch):
    J._phone_store.record(pl.parse_report(report(sent_ts=NOW), NOW + 1), NOW)
    asked = []
    monkeypatch.setattr(J._phone_locator, "ask", lambda dev=None: asked.append(dev) or True)
    monkeypatch.setattr(J._phone_locator, "wait_for", lambda ids, after, t: set())
    out = J._phone_location_tool({"action": "where", "phone": "tecno"})
    assert asked == ["abcdef0123456789"] and "didn't answer just now" in out


def test_show_switches_the_open_dashboard_tab(J, monkeypatch):
    J._phone_store.record(pl.parse_report(report(sent_ts=NOW), NOW + 1), NOW)
    events = []
    monkeypatch.setattr(J, "JARVIS_DASHBOARD_ENABLED", True)
    monkeypatch.setattr(J.dashboard, "client_count", lambda: 1)
    monkeypatch.setattr(J.dashboard, "notify", lambda ev: events.append(ev))
    monkeypatch.setattr(J._phone_locator, "ask", lambda dev=None: True)
    monkeypatch.setattr(J._phone_locator, "wait_for", lambda ids, after, t: set(ids))
    out = J._phone_location_tool({"action": "show"})
    nav = [e for e in events if e.get("type") == "navigate"][0]
    assert nav["data"]["route"] == "phones" and nav["data"]["cinematic"] is True and nav["data"]["device"]
    assert "on the map" in out


def test_show_without_a_tab_opens_the_cinematic_link(J, monkeypatch):
    J._phone_store.record(pl.parse_report(report(sent_ts=NOW), NOW + 1), NOW)
    opened = []
    monkeypatch.setattr(J, "JARVIS_DASHBOARD_ENABLED", True)
    monkeypatch.setattr(J.dashboard, "client_count", lambda: 0)
    monkeypatch.setattr(J.browsers, "open_link", lambda u: opened.append(u))
    monkeypatch.setattr(J._phone_locator, "ask", lambda dev=None: True)
    monkeypatch.setattr(J._phone_locator, "wait_for", lambda ids, after, t: set(ids))
    J._phone_location_tool({"action": "show"})
    assert opened and "#/phones?cine=1&device=" in opened[0]


def test_location_is_private(J):
    assert "phone_location" in J._UNTRUSTED_BLOCKED_TOOLS and "phone_location" in J._TAINT_BLOCKED_TOOLS
    J._command_ctx.source = None  # an unattended run (scheduled skill, job)
    assert "owner's own request" in J._phone_location_tool({"action": "last"})


def test_dashboard_never_gets_the_key(J):
    rep = J._feature_phones("get", {})
    assert rep["paired"] is True
    assert J.os.environ[pl.ENV_KEY] not in json.dumps(rep, default=str)
    assert "phone_location" in J._narrowing_core("where is my phone right now?")


def test_not_paired_says_how(J, monkeypatch):
    monkeypatch.delenv(pl.ENV_KEY)
    out = J._phone_location_tool({"action": "where"})
    assert "aren't paired yet" in out
