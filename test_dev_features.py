"""Tests for devtools, focus mode, roblox companion and vibes."""
import subprocess
import sys
from datetime import datetime

import jarvis_devtools as dt
import jarvis_focus as focus
import jarvis_roblox as rb
import jarvis_vibes as vibes


def _repo(tmp_path):
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n\nclass Box:\n    pass\n\ndef _hidden():\n    pass\n")
    (tmp_path / "tested.py").write_text("def f():\n    pass\n")
    (tmp_path / "test_tested.py").write_text("def test_x():\n    pass\n")
    return tmp_path


def test_analyze_and_generate_tests_run_green(tmp_path):
    root = _repo(tmp_path)
    assert "no tests" in dt.analyze_repo(str(root))
    out = dt.generate_tests(str(root))
    assert "Wrote 1" in out
    gen = root / "tests_generated" / "test_calc.py"
    assert gen.exists() and not (root / "tests_generated" / "test_tested.py").exists()
    r = subprocess.run([sys.executable, "-m", "pytest", str(gen), "-q", "-p", "no:cacheprovider"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    gen.write_text("# mine")
    assert "No new tests" in dt.generate_tests(str(root))
    assert gen.read_text() == "# mine"  # never overwritten


def test_scaffold_never_overwrites_and_validates(tmp_path):
    assert "Created" in dt.scaffold_module(str(tmp_path), "widget", "A widget.")
    assert "already exists" in dt.scaffold_module(str(tmp_path), "widget")
    assert "lowercase" in dt.scaffold_module(str(tmp_path), "../evil")
    assert not (tmp_path.parent / "evil.py").exists()


def test_not_a_folder():
    assert "not a folder" in dt.analyze_repo("Z:/nope/nope")


def test_focus_mood_classification():
    assert focus.classify_mood("Lofi Girl - lofi beats to study to")["focus_suggested"]
    assert focus.classify_mood("Gym Class - Workout Mix")["mood"] == "energetic"
    assert focus.classify_mood("Someone - Something")["mood"] == "unknown"
    assert focus.current_track(["Spotify Free"]) is None
    assert focus.current_track(["Artist - Song"]) == "Artist - Song"


def test_focus_mode_gates_notifications_and_opens_only_given_apps(monkeypatch):
    monkeypatch.setenv("JARVIS_FOCUS_APPS", "cursor, notepad")
    monkeypatch.setenv("JARVIS_FOCUS_DARK_MODE", "0")
    opened = []
    assert not focus.should_suppress(False)
    out = focus.enable(opened.append)
    try:
        assert "cursor, notepad" in out and opened == ["cursor", "notepad"]
        assert focus.should_suppress(False) and not focus.should_suppress(True)
    finally:
        assert "off" in focus.disable()
    assert not focus.should_suppress(False)


def test_focus_auto_is_opt_in(monkeypatch):
    monkeypatch.delenv("JARVIS_FOCUS_AUTO", raising=False)
    monkeypatch.setattr(focus, "current_track", lambda titles=None: "Lofi - study")
    said = []
    focus.tick(lambda a: None, said.append)
    focus.tick(lambda a: None, said.append)
    assert said == [] and not focus.is_active()


def test_roblox_review_finds_issues():
    src = "wait(1)\nwhile true do\n  s = s .. 'x'\nend\nlocal p = game.Workspace -- wait()\nfoo:connect(f)\n"
    joined = "\n".join(rb.review_source(src, "a.lua"))
    assert "task.wait" in joined and "concatenation" in joined and "workspace" in joined and ":Connect" in joined
    assert "a.lua:5" in joined and joined.count("wait() is deprecated") == 1  # comment ignored


def test_roblox_review_folder(tmp_path):
    (tmp_path / "s.luau").write_text("spawn(function() end)\n")
    assert "1 suggestions" in rb.review_folder(str(tmp_path))
    assert "not a folder" in rb.review_folder(str(tmp_path / "x"))


def test_roblox_flags_and_tick(monkeypatch):
    assert rb.performance_flag(None) is None
    assert rb.performance_flag({"cpu_percent": 10, "memory_mb": 100}) is None
    monkeypatch.setattr(rb, "studio_stats", lambda: {"cpu_percent": 99, "memory_mb": 1})
    said = []
    rb.start()
    for _ in range(4):
        rb._state["last"] = 0
        rb.tick(said.append)
    rb.stop()
    assert len(said) == 1 and "99" in said[0]


def test_vibes_off_by_default_and_text_only(monkeypatch):
    monkeypatch.setattr(vibes, "_enabled", None)
    monkeypatch.delenv("JARVIS_VIBES", raising=False)
    assert vibes.decorate("thanks", "ok") == "ok"
    vibes.set_enabled(True)
    try:
        assert vibes.decorate("thanks a lot", "You're welcome.") != "You're welcome."
        assert vibes.pick_reaction("x", "It failed with an error.") is not None
        assert vibes.pick_reaction("what's 2+2", "Four.", datetime(2026, 1, 1, 14)) is None
    finally:
        vibes._enabled = None


def test_tools_registered():
    import jarvis

    names = {t["name"] for t in jarvis.AGENT_TOOLS}
    assert {"dev_tools", "focus_mode", "roblox_companion", "vibe_mode"} <= names
