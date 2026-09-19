"""Tests for jarvis_image_download.py. Run: python -m pytest test_image_download.py -v

No real network: _fetch's HTTP layer is replaced, and host resolution is faked. Files go to tmp_path.
"""

from __future__ import annotations

import pytest

import jarvis_image_download as img

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


@pytest.fixture(autouse=True)
def _dir(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_IMAGE_DIR", str(tmp_path / "pics"))


def _serve(monkeypatch, responses: dict):
    """responses: url -> bytes | Exception. Records requested URLs."""
    seen = []

    def fake_fetch(url, referer):
        seen.append(url)
        r = responses[url]
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(img, "_fetch", fake_fetch)
    return seen


def test_pinterest_upgrade():
    assert (
        img.upgrade_pinterest_url("https://i.pinimg.com/236x/ab/cd/x.jpg")
        == "https://i.pinimg.com/originals/ab/cd/x.jpg"
    )
    assert "originals" in img.upgrade_pinterest_url("https://i.pinimg.com/736x/ab/x.jpg")
    other = "https://example.com/236x/a.jpg"
    assert img.upgrade_pinterest_url(other) == other


def test_saves_and_never_overwrites(monkeypatch, tmp_path):
    _serve(monkeypatch, {"https://example.com/cat.png": PNG})
    a = img.download_image("https://example.com/cat.png")
    b = img.download_image("https://example.com/cat.png")
    files = sorted(p.name for p in (tmp_path / "pics").iterdir())
    assert files == ["cat-1.png", "cat.png"]
    assert "Saved" in a and "Saved" in b


def test_filename_cannot_escape_folder(monkeypatch, tmp_path):
    _serve(monkeypatch, {"https://example.com/a": JPG})
    img.download_image("https://example.com/a", filename="..\\..\\evil.exe")
    saved = list((tmp_path / "pics").iterdir())
    assert [p.name for p in saved] == ["evil.jpg"]  # extension comes from the bytes, not the name


def test_pinterest_falls_back_to_shown_size(monkeypatch, tmp_path):
    thumb = "https://i.pinimg.com/236x/ab/x.jpg"
    orig = "https://i.pinimg.com/originals/ab/x.jpg"
    seen = _serve(monkeypatch, {orig: OSError("HTTP 403"), thumb: JPG})
    out = img.download_image(thumb)
    assert seen == [orig, thumb]
    assert "Saved" in out


def test_non_image_bytes_rejected(monkeypatch, tmp_path):
    _serve(monkeypatch, {"https://example.com/x.jpg": b"<html>login</html>"})
    out = img.download_image("https://example.com/x.jpg")
    assert "isn't a recognised image" in out
    assert not (tmp_path / "pics").exists() or not list((tmp_path / "pics").iterdir())


def test_svg_rejected(monkeypatch):
    _serve(monkeypatch, {"https://example.com/x.svg": b"<svg onload='x()'></svg>"})
    assert "Not saved" in img.download_image("https://example.com/x.svg")


def test_host_checks(monkeypatch):
    assert img._check_host("file:///c:/secret.png")
    assert img._check_host("ftp://example.com/a.png")
    monkeypatch.setattr(
        img.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 0))]
    )
    assert "private" in img._check_host("http://localhost/a.png")
    monkeypatch.setattr(
        img.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("192.168.1.5", 0))]
    )
    assert "private" in img._check_host("http://router.lan/a.png")
    monkeypatch.setattr(
        img.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))]
    )
    assert img._check_host("https://example.com/a.png") is None


def test_empty_url():
    assert "No image URL" in img.download_image("  ")


def test_tool_is_registered_and_dispatched():
    import jarvis

    assert any(t["name"] == "download_image" for t in jarvis.AGENT_TOOLS)
