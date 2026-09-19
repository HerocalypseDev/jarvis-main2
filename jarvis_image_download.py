"""download_image: fetch one image URL and save it to a single fixed folder.

Purpose-built so "grab that Pinterest image" doesn't need run_shell/run_python (and their
confirmation gate). Narrow on purpose: http(s) only, no private/loopback hosts, the response must
really be a raster image (content-type AND magic bytes; SVG is refused since it can carry
scripts), a size cap, and the destination is always `JARVIS_IMAGE_DIR` (default
~/Pictures/Jarvis) — the caller can choose a file name, never a path. Never overwrites.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MAX_BYTES = 25 * 1024 * 1024
TIMEOUT_S = 25
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
_EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/avif": ".avif",
}


def save_dir() -> Path:
    raw = os.environ.get("JARVIS_IMAGE_DIR", "").strip()
    return Path(raw) if raw else Path.home() / "Pictures" / "Jarvis"


def upgrade_pinterest_url(url: str) -> str:
    """i.pinimg.com/236x/.. or /736x/.. (a thumbnail) -> /originals/.. (full size)."""
    p = urllib.parse.urlsplit(url)
    if (p.hostname or "").lower() != "i.pinimg.com":
        return url
    path = re.sub(r"^/(?:\d+x\d*|\d*x\d+)/", "/originals/", p.path)
    return urllib.parse.urlunsplit((p.scheme, p.netloc, path, p.query, ""))


def sniff_image_ext(head: bytes) -> str | None:
    """Extension from magic bytes, or None if it isn't a raster image we accept."""
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    if head.startswith(b"BM"):
        return ".bmp"
    if head[4:12] in (b"ftypavif", b"ftypavis"):
        return ".avif"
    return None


def _check_host(url: str) -> str | None:
    """Error text if the URL isn't a public http(s) address, else None."""
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ("http", "https"):
        return "Only http and https links can be downloaded."
    host = p.hostname
    if not host:
        return "That link has no host."
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as e:
        return f"Couldn't resolve {host}: {e}"
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global:
            return "That address is on a private or local network; refusing to fetch it."
    return None


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        err = _check_host(newurl)
        if err:
            raise urllib.error.URLError(err)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _clean_stem(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" ._")
    return name[:80] or "image"


def _unique_path(folder: Path, stem: str, ext: str) -> Path:
    p = folder / f"{stem}{ext}"
    n = 1
    while p.exists():
        p = folder / f"{stem}-{n}{ext}"
        n += 1
    return p


def _fetch(url: str, referer: str | None) -> bytes:
    err = _check_host(url)
    if err:
        raise ValueError(err)
    headers = {"User-Agent": _UA, "Accept": "image/*,*/*;q=0.5"}
    if referer:
        headers["Referer"] = referer
    opener = urllib.request.build_opener(_CheckedRedirects)
    with opener.open(urllib.request.Request(url, headers=headers), timeout=TIMEOUT_S) as resp:
        ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype and not ctype.startswith("image/") and ctype != "application/octet-stream":
            raise ValueError(f"That link is {ctype or 'not an image'}, not an image.")
        declared = resp.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > MAX_BYTES:
            raise ValueError("That image is over the 25 megabyte limit.")
        data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("That image is over the 25 megabyte limit.")
    return data


def download_image(url: str, filename: str | None = None, referer: str | None = None) -> str:
    url = (url or "").strip()
    if not url:
        return "No image URL given."
    candidates = [upgrade_pinterest_url(url)]
    if candidates[0] != url:
        candidates.append(url)  # originals/ can 404 for some pins; fall back to the shown size

    data, last_err = None, ""
    for cand in candidates:
        try:
            data = _fetch(cand, referer)
            url = cand
            break
        except ValueError as e:
            return f"Not saved: {e}"
        except Exception as e:  # HTTPError, URLError, timeouts
            last_err = str(e)
    if data is None:
        return f"Download failed: {last_err}"

    ext = sniff_image_ext(data[:16])
    if ext is None:
        return "Not saved: the downloaded file isn't a recognised image (jpg/png/gif/webp/bmp/avif)."

    if filename:
        stem = _clean_stem(Path(filename.replace("\\", "/")).stem)
    else:
        stem = _clean_stem(Path(urllib.parse.urlsplit(url).path).stem)
    folder = save_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        dest = _unique_path(folder, stem, ext)
        dest.write_bytes(data)
    except OSError as e:
        return f"Couldn't save the file: {e}"
    return f"Saved {len(data) // 1024} KB image to {dest}"
