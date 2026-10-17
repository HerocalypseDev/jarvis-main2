"""Caretaker storage fixes (jarvis_caretaker_fix.py): real temp folders, nothing outside tmp_path is touched."""
import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import jarvis_caretaker as ct
import jarvis_caretaker_fix as fx

DAY = 86400
MB = 1024 * 1024


def make(path: Path, size: int = 10, age_days: float = 0, data: bytes | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if data is not None else b"x" * size)
    t = time.time() - age_days * DAY
    os.utime(path, (t, t))
    return path


@pytest.fixture()
def store(tmp_path):
    db = tmp_path / "c.db"
    return ct.Store(lambda: sqlite3.connect(db))


@pytest.fixture()
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


# --- caches ---------------------------------------------------------------------------------------
def test_clear_caches_deletes_only_old_files_inside_the_roots(tmp_path):
    cache = tmp_path / "cache"
    old = make(cache / "a" / "old.bin", 100, age_days=5)
    fresh = make(cache / "fresh.bin", 100, age_days=0)
    outside = make(tmp_path / "keep.txt", 100, age_days=50)
    r = fx.clear_caches([cache])
    assert r["files"] == 1 and r["freed"] == 100
    assert not old.exists() and fresh.exists() and outside.exists()


def test_clear_caches_never_follows_a_symlink_out_of_the_root(tmp_path):
    cache, secret_dir = tmp_path / "cache", tmp_path / "docs"
    precious = make(secret_dir / "thesis.docx", 50, age_days=100)
    cache.mkdir()
    try:
        (cache / "link").symlink_to(secret_dir, target_is_directory=True)
        (cache / "flink").symlink_to(precious)
    except OSError:
        pytest.skip("symlinks need privileges here")
    fx.clear_caches([cache])
    assert precious.exists()


def test_clear_caches_refuses_a_whole_drive_or_profile_root(tmp_path):
    r = fx.clear_caches([Path(Path.home().anchor or "/"), Path.home()])
    assert r["files"] == 0 and r["skipped"] >= 2


def test_clear_caches_dry_run_changes_nothing(tmp_path):
    f = make(tmp_path / "c" / "x.bin", 10, age_days=9)
    r = fx.clear_caches([tmp_path / "c"], dry_run=True)
    assert r["files"] == 1 and f.exists()


# --- recycle bin ----------------------------------------------------------------------------------
def test_purge_recycle_removes_only_items_deleted_long_ago(tmp_path):
    b = tmp_path / "$Recycle.Bin" / "S-1"
    make(b / "$IOLD.txt", 5, age_days=40); make(b / "$ROLD.txt", 1000, age_days=40)
    make(b / "$INEW.txt", 5, age_days=2); make(b / "$RNEW.txt", 500, age_days=2)
    make(b / "$RDIR" / "inner.bin", 300, age_days=40)
    make(b / "$IDIR", 5, age_days=40)
    r = fx.purge_recycle([b])
    assert r["items"] == 2 and r["freed"] == 1300
    assert not (b / "$ROLD.txt").exists() and not (b / "$IOLD.txt").exists() and not (b / "$RDIR").exists()
    assert (b / "$RNEW.txt").exists() and (b / "$INEW.txt").exists()


# --- holding folder -------------------------------------------------------------------------------
def test_hold_moves_an_old_installer_and_undo_puts_it_back(tmp_path, home):
    inst = make(home / "Downloads" / "setup.exe", 7, age_days=60)
    hr = tmp_path / "holding"
    r = fx.hold([str(inst)], hr, home=home)
    assert len(r["moved"]) == 1 and not inst.exists() and Path(r["moved"][0]["held"]).exists()
    msg = fx.undo({"kind": "hold", "manifest": r["manifest"]})
    assert "Put 1 file" in msg and inst.read_bytes() == b"x" * 7
    assert not hr.exists() or not any(hr.iterdir())          # the empty batch is cleaned up


def test_undo_never_overwrites_a_new_file_at_the_old_path(tmp_path, home):
    inst = make(home / "Downloads" / "setup.exe", 7, age_days=60)
    r = fx.hold([str(inst)], tmp_path / "h", home=home)
    inst.write_bytes(b"NEW")                                   # the user downloaded something with that name
    fx.undo({"kind": "hold", "manifest": r["manifest"]})
    assert inst.read_bytes() == b"NEW" and (inst.parent / "setup (restored).exe").read_bytes() == b"x" * 7


@pytest.mark.parametrize("rel", ["Documents/essay.docx", "Desktop/a.zip", "Pictures/p.iso", "OneDrive/x.zip",
                                 "OneDrive - School/y.zip", "projects/app/build.zip", ".ssh/id.zip"])
def test_hold_refuses_the_users_own_folders(tmp_path, home, rel):
    f = make(home / rel, 5, age_days=400)
    r = fx.hold([str(f)], tmp_path / "h", home=home)
    assert r["moved"] == [] and f.exists() and r["refused"], rel


def test_hold_refuses_recent_files_code_projects_links_and_secrets(tmp_path, home):
    recent = make(home / "Downloads" / "new.zip", 5, age_days=3)
    proj = make(home / "Downloads" / "repo" / "dist.zip", 5, age_days=300)
    (home / "Downloads" / "repo" / ".git").mkdir()
    env = make(home / "Downloads" / ".env", 5, age_days=300)
    for f in (recent, proj, env):
        r = fx.hold([str(f)], tmp_path / "h", home=home)
        assert r["moved"] == [] and f.exists(), f
    target = make(home / "Downloads" / "real.zip", 5, age_days=300)
    link = home / "Downloads" / "l.zip"
    try:
        link.symlink_to(target)
    except OSError:
        return
    assert fx.hold([str(link)], tmp_path / "h", home=home)["moved"] == [] and target.exists()


def test_hold_refuses_jarvis_own_code_and_the_holding_folder(tmp_path, home):
    code = tmp_path / "jarvis"
    f = make(code / "x.zip", 5, age_days=300)
    assert fx.hold([str(f)], tmp_path / "h", home=home, code_dir=code)["moved"] == []
    held = make(tmp_path / "h" / "2026-01-01-ab" / "000__a.zip", 5, age_days=300)
    assert fx.hold([str(held)], tmp_path / "h", home=home)["moved"] == []


def test_purge_holding_deletes_only_batches_past_their_days(tmp_path, home):
    a = make(home / "Downloads" / "a.zip", 9, age_days=60)
    hr = tmp_path / "h"
    old_now = datetime.now() - timedelta(days=ct.HOLDING_DAYS + 1)
    fx.hold([str(a)], hr, home=home, now=old_now)
    b = make(home / "Downloads" / "b.zip", 4, age_days=60)
    fx.hold([str(b)], hr, home=home)                            # held just now
    r = fx.purge_holding(hr)
    assert r["batches"] == 1 and r["freed"] > 0
    assert len(list(hr.iterdir())) == 1


def test_undo_after_purge_is_honest(tmp_path, home):
    a = make(home / "Downloads" / "a.zip", 9, age_days=60)
    r = fx.hold([str(a)], tmp_path / "h", home=home, now=datetime.now() - timedelta(days=30))
    fx.purge_holding(tmp_path / "h")
    assert "gone" in fx.undo({"kind": "hold", "manifest": r["manifest"]})
    assert fx.undo(None) == "That action can't be undone."
    assert fx.undo({"kind": "caches"}) == "That action can't be undone."


# --- stale installers -----------------------------------------------------------------------------
def test_find_stale_installers_needs_size_age_and_kind(tmp_path):
    d = tmp_path / "Downloads"
    big_old = make(d / "big.iso", data=b"0" * (60 * MB), age_days=90)
    make(d / "small_old.exe", 10, age_days=90)
    make(d / "big_new.zip", data=b"0" * (60 * MB), age_days=2)
    make(d / "big_doc.pdf", data=b"0" * (60 * MB), age_days=90)
    assert [p for p, _ in fx.find_stale_installers(d)] == [str(big_old.resolve())]


# --- the playbook ---------------------------------------------------------------------------------
def make_env(tmp_path, home, free):
    d = home / "Downloads"
    return fx.StorageEnv(cache_roots=[tmp_path / "cache"], bin_dirs=[tmp_path / "bin"], downloads=d,
                         holding_root=tmp_path / "hold", home=home, free_fraction=lambda: free[0])


def test_playbook_stops_as_soon_as_enough_space_is_free(tmp_path, home, store):
    make(tmp_path / "cache" / "x.bin", 1000, age_days=9)
    big = make(home / "Downloads" / "big.iso", data=b"0" * (60 * MB), age_days=90)
    free = [0.05]

    env = make_env(tmp_path, home, free)
    orig = fx.clear_caches
    fx.clear_caches = lambda *a, **k: (free.__setitem__(0, 0.20) or orig(*a, **k))   # the cleanup frees enough
    try:
        r = fx.fix_storage(store, "disk:C:", env)
    finally:
        fx.clear_caches = orig
    assert r["reached"] and r["steps"] and "caches" in r["steps"][0]
    assert big.exists()                                         # step 3 was never needed
    assert [a["action"] for a in store.recent_actions()] == ["clear_caches"]


def test_playbook_does_nothing_when_the_drive_is_already_fine(tmp_path, home, store):
    f = make(tmp_path / "cache" / "x.bin", 1000, age_days=9)
    r = fx.fix_storage(store, "disk:C:", make_env(tmp_path, home, [0.5]))
    assert r["reached"] and r["steps"] == [] and f.exists() and store.recent_actions() == []


def test_playbook_holds_installers_logs_an_undo_and_reports_held_not_freed(tmp_path, home, store):
    big = make(home / "Downloads" / "big.iso", data=b"0" * (60 * MB), age_days=90)
    r = fx.fix_storage(store, "disk:C:", make_env(tmp_path, home, [0.05]))
    assert not r["reached"] and r["freed"] == 0 and r["held"] == 60 * MB
    assert not big.exists() and any("holding folder" in s for s in r["steps"])
    act = store.recent_actions(undoable_only=True)[0]
    assert act["tier"] == ct.YELLOW and act["undo"]["kind"] == "hold"
    assert "Put 1 file" in fx.undo(act["undo"]) and big.exists()
    s = store.summary_since(24)
    assert s["freed_bytes"] == 0                                 # moving files is not freeing space


def test_playbook_respects_the_hourly_budget(tmp_path, home, store):
    for _ in range(ct.MAX_ACTIONS_PER_HOUR):
        store.log_action("k", ct.GREEN, "a", "", "ok")
    f = make(tmp_path / "cache" / "x.bin", 1000, age_days=9)
    r = fx.fix_storage(store, "disk:C:", make_env(tmp_path, home, [0.05]))
    assert r["blocked"] and "this hour" in r["blocked"] and f.exists()


def test_playbook_respects_the_daily_move_cap(tmp_path, home, store, monkeypatch):
    monkeypatch.setattr(ct, "MAX_MOVE_GB_PER_DAY", 0.05)         # 51 MB: a 60 MB installer does not fit
    big = make(home / "Downloads" / "big.iso", data=b"0" * (60 * MB), age_days=90)
    r = fx.fix_storage(store, "disk:C:", make_env(tmp_path, home, [0.05]))
    assert big.exists() and r["blocked"] and "today" in r["blocked"]


def test_cache_roots_never_include_uvs_environment_cache(tmp_path, monkeypatch):
    """uv's archive-v0 holds the unpacked environments `uvx` runs tools from; deleting old single files there broke
    Windows-MCP ("No module named 'windows_mcp.__main__'", 2026-10-16)."""
    import jarvis_caretaker_probe as probe
    local = tmp_path / "Local"
    for d in ("Temp", "uv/cache/archive-v0", "npm-cache"):
        (local / d).mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.delenv("APPDATA", raising=False)
    roots = [str(r) for r in probe.cache_roots()]
    assert any(r.endswith("npm-cache") for r in roots)
    assert not any("uv" in Path(r).parts for r in roots)
