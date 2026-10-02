"""Internet speed test (jarvis_speedtest): measuring, data cap, wording, history, voice routing. No real network."""

import sqlite3
import threading

import pytest

import jarvis_latency as latency
import jarvis_speedtest as st


class _Resp:
    def __init__(self, body: bytes, status=200, headers=None):
        self.body, self.status, self.pos = body, status, 0
        self.headers = headers or {}

    def read(self, n=None):
        if n is None:
            out, self.pos = self.body[self.pos:], len(self.body)
            return out
        out = self.body[self.pos:self.pos + n]
        self.pos += len(out)
        return out

    def getheader(self, name, default=None):
        return self.headers.get(name, default)


class _FakeConn:
    """Stands in for http.client.HTTPSConnection against speed.cloudflare.com."""

    def __init__(self, log):
        self.log = log
        self._next = None
        self.sent = 0

    def request(self, method, path, headers=None):
        size = int(path.split("bytes=")[1]) if "bytes=" in path else 0
        self.log.append(("GET", size))
        self._next = _Resp(b"x" * size, headers={"cf-meta-colo": "LOS",
                                                  "Server-Timing": "cfSpeedEdge;dur=1, cfSpeedWorker;dur=2"})

    def putrequest(self, method, path):
        self.sent = 0

    def putheader(self, *a):
        pass

    def endheaders(self):
        pass

    def send(self, data):
        self.sent += len(data)

    def getresponse(self):
        if self._next is not None:
            r, self._next = self._next, None
            return r
        self.log.append(("POST", self.sent))
        return _Resp(b"")

    def close(self):
        pass


def _factory(log):
    return lambda: _FakeConn(log)


def test_run_measures_ping_download_upload_and_respects_the_data_cap():
    log = []
    r = st.run(_factory(log), down_s=0.4, up_s=0.3, cap_mb=10)
    assert r["ok"] and r["server"] == "LOS"
    assert r["download_mbps"] > 0 and r["upload_mbps"] > 0 and r["ping_ms"] >= 0
    down = sum(n for kind, n in log if kind == "GET")
    up = sum(n for kind, n in log if kind == "POST")
    assert up <= 5_000_000  # uploads stop at half the cap, even with 4 streams at once
    assert r["data_mb"] <= 10 + 5 + 4 * 0.07 + 1  # the download stops within a block of the cap per stream
    assert down > 0


def test_unreachable_server_is_a_plain_answer_not_a_crash():
    def broken():
        raise OSError("Name or service not known")
    r = st.run(broken, down_s=0.1, up_s=0.1)
    assert not r["ok"] and "couldn't reach" in r["error"]
    assert "Are you online" in st.describe(r)


def test_only_one_test_at_a_time():
    assert st._running.acquire(blocking=False)
    try:
        r = st.run(_factory([]), down_s=0.1, up_s=0.1)
    finally:
        st._running.release()
    assert r == {"ok": False, "error": "busy"} and "already running" in st.describe(r)


def test_wording_and_comparison_with_the_last_test(tmp_path):
    db = tmp_path / "t.db"
    lock = threading.Lock()
    connect = lambda: sqlite3.connect(db)  # noqa: E731
    first = {"ok": True, "download_mbps": 10.0, "upload_mbps": 3.0, "ping_ms": 40.0, "jitter_ms": 2, "server": "LOS",
             "data_mb": 12.0}
    st.save(connect, lock, first, now=1_000.0)
    text = st.measure_and_describe(connect, lock, runner=lambda: {**first, "download_mbps": 30.0})
    assert text.startswith("Download 30 megabits per second, upload 3.0, ping 40 milliseconds.")
    assert "good" in text and "Faster than" in text and "12 MB of data" in text
    assert len(st.history(connect, lock, 5)) == 2
    assert "Last test" in st.handle_tool(connect, lock, {"action": "last"})
    assert st.handle_tool(connect, lock, {"action": "history"}).count("down ") == 2
    assert "very slow" in st.verdict(0.5) and "fast" in st.verdict(120)


@pytest.mark.parametrize("said", [
    "what's my network speed", "What is my internet speed?", "how fast is my wifi", "run a speed test",
    "speed test", "Jarvis, test my internet speed please", "check the connection speed", "how fast is the internet right now",
])
def test_voice_phrases_route_to_the_speed_test(said):
    assert latency.classify_intent(said) == "speedtest"


@pytest.mark.parametrize("said", ["what's the speed of light", "speed up the video", "how fast is a cheetah",
                                  "write a python speed test script for my code"])
def test_other_speed_questions_do_not(said):
    assert latency.classify_intent(said) != "speedtest"


def test_spoken_request_runs_the_test_without_a_model_call(monkeypatch, tmp_path):
    import jarvis
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(jarvis, "_log_action_audit", lambda *a, **k: None)
    monkeypatch.setattr(jarvis, "_append_history", lambda *a, **k: None)
    monkeypatch.setattr(jarvis.autonomy, "after_turn", lambda *a, **k: None)
    monkeypatch.setattr(jarvis.autonomy, "enabled", lambda: False)
    monkeypatch.setattr(jarvis, "flush_pending_notifications", lambda: None)
    monkeypatch.setattr(jarvis, "run_agent_loop", lambda *a, **k: pytest.fail("a speed test needs no model call"))
    monkeypatch.setattr(jarvis.speedtest, "run", lambda: {
        "ok": True, "download_mbps": 22.4, "upload_mbps": 6.1, "ping_ms": 51.0, "jitter_ms": 3.0, "server": "LOS",
        "data_mb": 30.0})
    monkeypatch.setattr(jarvis, "_start_announcement", lambda line: None)
    spoken = []
    monkeypatch.setattr(jarvis, "speak_text", lambda t: spoken.append(t))
    jarvis.handle_text_command("what's my network speed", source="text")
    assert spoken and spoken[-1].startswith("Download 22 megabits per second, upload 6.1, ping 51 milliseconds.")


def test_speed_test_tool_is_registered_and_announced():
    import jarvis
    assert any(t["name"] == "speed_test" for t in jarvis.AGENT_TOOLS)
    assert jarvis._tool_announcement("speed_test", {}) == jarvis.SPEED_TEST_ANNOUNCEMENT
    assert jarvis._tool_announcement("speed_test", {"action": "last"}) is None


@pytest.mark.parametrize("said, unit", [
    ("what's my internet speed in megabytes", "megabytes"), ("what's my internet speed in megabits", "megabits"),
    ("whats my internet speed in MB per second", "megabytes"), ("how fast is my wifi in mbps", "megabits"),
    ("run a speed test in kilobytes", "kilobytes"), ("speed test in kbps", "kilobits"),
    ("how fast is my internet in gigabits", "gigabits"), ("what's my internet speed", None),
])
def test_asking_for_a_unit(said, unit):
    assert latency.classify_intent(said) == "speedtest"
    assert st.parse_unit(said) == unit


def test_answer_in_the_unit_asked_for_and_the_default_setting(monkeypatch):
    r = {"ok": True, "download_mbps": 40.0, "upload_mbps": 8.0, "ping_ms": 30.0, "data_mb": 20.0}
    text = st.describe(r, unit="megabytes")
    # the plan's own unit is said too
    assert text.startswith("Download 5.0 megabytes per second (40 megabits), upload 1.0, ping 30 milliseconds.")
    assert st.describe(r, unit="kilobits").startswith("Download 40000 kilobits per second, upload 8000")
    monkeypatch.setenv("JARVIS_SPEEDTEST_UNIT", "megabytes")
    assert st.describe(r).startswith("Download 5.0 megabytes per second")
    assert st.describe(r, unit="megabits").startswith("Download 40 megabits per second")  # asking wins
    monkeypatch.setenv("JARVIS_SPEEDTEST_UNIT", "nonsense")
    assert st.describe(r).startswith("Download 40 megabits per second")


def test_spoken_unit_reaches_the_answer(monkeypatch):
    import jarvis
    monkeypatch.setattr(jarvis.speedtest, "measure_and_describe",
                        lambda connect, lock, runner=None, unit=None: f"unit={unit}")
    monkeypatch.setattr(jarvis, "_current_command_source", lambda: "phone")
    assert jarvis._deterministic_intent_reply("speedtest", "what's my internet speed in megabytes") == "unit=megabytes"


@pytest.mark.parametrize("said, intent", [
    ("Hey, Jarvis. Perform a speed test.", "speedtest"), ("run the internet test again", "speedtest"),
    ("ok jarvis run my wifi test", "speedtest"), ("run a test", "complex"), ("run the test", "complex"),
    ("in 10mins time run the internet test again", "complex"),  # later = a scheduled job, not now
])
def test_more_ways_of_asking(said, intent):
    assert latency.classify_intent(said) == intent


def test_one_network_hiccup_is_retried(monkeypatch):
    monkeypatch.setattr(st, "RETRY_DELAY_S", 0)
    tries = {"n": 0}
    log = []

    def flaky():
        tries["n"] += 1
        if tries["n"] == 1:
            raise OSError("[Errno 11002] getaddrinfo failed")
        return _FakeConn(log)
    r = st.run(flaky, down_s=0.2, up_s=0.2, cap_mb=10)
    assert r["ok"] and tries["n"] > 2
