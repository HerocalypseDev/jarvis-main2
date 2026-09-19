import pytest
import jarvis_workspace as ws


@pytest.fixture(autouse=True)
def _root(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.delenv("JARVIS_WORKSPACE_STRICT", raising=False)
    return tmp_path


@pytest.mark.parametrize("name,content,sub", [
    ("logo.png", "", "Assets"),
    ("song.mp3", "", "Assets"),
    ("tool.py", "print(1)", "Code_Projects"),
    ("todo.md", "buy milk", "Notes"),
    ("ideas", "", "Notes"),
    ("login_bug.md", "", "Bugs"),
    ("crash.txt", "Traceback (most recent call last):\n", "Bugs"),
    ("run.log", "", "Bugs"),
    ("python_tutorial.md", "", "Learning_Resources"),
    ("scratch.txt", "", "Temp"),
    ("x.tmp", "", "Temp"),
    ("game.rbxl", "", "Roblox_Projects"),
    ("notes.md", "my Roblox obby script", "Roblox_Projects"),
    ("Hello.lua", "", "Code_Projects"),
])
def test_classify(name, content, sub):
    assert ws.classify(name, content) == sub


def test_bare_name_routes_into_workspace(_root):
    p, err = ws.resolve_write_path("app.py", "x")
    assert not err and p == (_root / "Code_Projects" / "app.py").resolve()


def test_explicit_subfolder_kept(_root):
    p, _ = ws.resolve_write_path("Notes/deep/a.py", "")
    assert p == (_root / "Notes" / "deep" / "a.py").resolve()


def test_dotdot_cannot_escape(_root):
    p, err = ws.resolve_write_path("../../evil.txt", "")
    assert p is None and "outside" in err


def test_absolute_honored_unless_strict(_root, tmp_path_factory, monkeypatch):
    other = tmp_path_factory.mktemp("other") / "f.txt"
    assert ws.resolve_write_path(str(other), "")[0] == other
    monkeypatch.setenv("JARVIS_WORKSPACE_STRICT", "1")
    assert ws.resolve_write_path(str(other), "")[0] is None
    inside = _root / "Notes" / "ok.md"
    assert ws.resolve_write_path(str(inside), "")[0] == inside


def test_read_finds_file_in_subfolder(_root):
    (_root / "Notes").mkdir()
    f = _root / "Notes" / "a.md"
    f.write_text("hi")
    assert ws.resolve_read_path("a.md") == f


def test_write_and_read_tools(_root):
    import jarvis
    assert "Code_Projects" in jarvis._write_file_tool("hello.py", "print('x')", False)
    assert (_root / "Code_Projects" / "hello.py").exists()
    assert "print" in jarvis._read_file_tool("hello.py")
    assert jarvis._write_file_tool("../../x.txt", "", False).startswith("Refused")


def test_image_default_dir(_root, monkeypatch):
    import jarvis_image_download as d
    monkeypatch.delenv("JARVIS_IMAGE_DIR", raising=False)
    assert d.save_dir() == _root / "Assets"
