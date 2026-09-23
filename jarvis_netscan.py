"""Devices on the local network (2026-09-23), for the dashboard Home tab's "Network devices" card.

Every JARVIS_NETSCAN_INTERVAL_S (60 s, 0 = off) the scheduler runs `scan()` on its own thread:
one UDP datagram to every address in this PC's IPv4 subnet (capped at the /24 around it) makes
Windows ARP-resolve each address, then `arp -a` lists the ones that answered with their MAC.
Nothing is installed and nothing is sent beyond the LAN.

Known devices are kept in `network_devices` (jarvis_memory.db), keyed by (network, mac), where the
network is the gateway's MAC so a different Wi-Fi gets its own list. A MAC never seen before on
this network is "new" and the caller notifies about it; the very first scan of a network is a
silent baseline (otherwise every device already there would be announced at once).

Limits: a device that ignores ARP while asleep (some phones) may drop out of a scan and come back;
phones with "private Wi-Fi address" use a random MAC per network, flagged `private_mac`.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Callable

ARP_SETTLE_S = 1.5
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_MAC_RE = re.compile(r"^([0-9a-f]{2}[-:]){5}[0-9a-f]{2}$", re.I)
_hostname_cache: dict[str, str] = {}


def _run(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True, timeout=15, creationflags=_NO_WINDOW,
                          errors="replace").stdout


def local_ip() -> str | None:
    """The IPv4 address of the interface that holds the default route (UDP connect sends nothing)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def parse_ipconfig(text: str, ip: str) -> dict:
    """From `ipconfig /all`, the adapter block holding `ip`: {"mask", "mac", "gateway"}."""
    for block in re.split(r"\n(?=\S)", text):
        if not re.search(rf"IPv4 Address[ .]*:\s*{re.escape(ip)}\b", block):
            continue
        field = lambda name: (re.search(rf"{name}[ .]*:\s*(\S+)", block) or [None, None])[1]
        return {"mask": field("Subnet Mask"), "mac": normalize_mac(field("Physical Address") or ""),
                "gateway": field("Default Gateway")}
    return {}


def normalize_mac(mac: str) -> str:
    mac = (mac or "").strip().lower().replace("-", ":")
    return mac if _MAC_RE.match(mac) else ""


def parse_arp(text: str, network: ipaddress.IPv4Network) -> dict[str, str]:
    """`arp -a` output -> {ip: mac} for dynamic entries inside `network` (no broadcast/multicast)."""
    found = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[2].lower() != "dynamic":
            continue
        try:
            addr = ipaddress.IPv4Address(parts[0])
        except ValueError:
            continue
        mac = normalize_mac(parts[1])
        if addr in network and addr != network.broadcast_address and mac and mac != "ff:ff:ff:ff:ff:ff":
            found[str(addr)] = mac
    return found


def is_private_mac(mac: str) -> bool:
    """Locally administered bit set: a randomised ("private") MAC, typical of phones."""
    try:
        return bool(int(mac.split(":")[0], 16) & 0x02)
    except (ValueError, IndexError):
        return False


def _hostnames(ips: list[str], budget_s: float = 2.0) -> dict[str, str]:
    todo = [ip for ip in ips if ip not in _hostname_cache]
    if todo:
        pool = ThreadPoolExecutor(max_workers=16)
        futures = {pool.submit(socket.gethostbyaddr, ip): ip for ip in todo}
        done, _ = wait(futures, timeout=budget_s)
        for f in done:
            try:
                _hostname_cache[futures[f]] = f.result()[0].split(".")[0]
            except Exception:
                _hostname_cache[futures[f]] = ""
        pool.shutdown(wait=False, cancel_futures=True)  # slow lookups are retried next scan
    return {ip: _hostname_cache.get(ip, "") for ip in ips}


def scan() -> dict:
    """One sweep: {"ok", "ip", "network", "gateway", "devices": [{ip, mac, hostname, this_pc, private_mac}]}."""
    if sys.platform != "win32":
        return {"ok": False, "error": "network scan is Windows-only", "devices": []}
    ip = local_ip()
    if not ip:
        return {"ok": False, "error": "not connected to a network", "devices": []}
    info = parse_ipconfig(_run(["ipconfig", "/all"]), ip)
    net = ipaddress.IPv4Network(f"{ip}/{info.get('mask') or '255.255.255.0'}", strict=False)
    if net.prefixlen < 24:
        net = ipaddress.IPv4Network(f"{ip}/24", strict=False)  # never sweep more than 254 addresses
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        for host in net.hosts():
            if str(host) != ip:
                try:
                    s.sendto(b"", (str(host), 9))  # discard port; the point is the ARP request
                except OSError:
                    pass
    time.sleep(ARP_SETTLE_S)
    table = parse_arp(_run(["arp", "-a", "-N", ip]), net)
    if info.get("mac"):
        table[ip] = info["mac"]
    names = _hostnames(list(table))
    try:
        names[ip] = names.get(ip) or socket.gethostname()
    except OSError:
        pass
    gateway = info.get("gateway") or ""
    devices = [{"ip": a, "mac": m, "hostname": names.get(a, ""), "this_pc": a == ip,
                "gateway": a == gateway, "private_mac": is_private_mac(m)} for a, m in table.items()]
    devices.sort(key=lambda d: ipaddress.IPv4Address(d["ip"]))
    return {"ok": True, "ip": ip, "network": str(net), "gateway": gateway,
            "network_id": table.get(gateway) or str(net), "devices": devices}


def _ensure(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS network_devices (network TEXT NOT NULL, mac TEXT NOT NULL, "
                 "ip TEXT, hostname TEXT, first_seen REAL NOT NULL, last_seen REAL NOT NULL, "
                 "PRIMARY KEY (network, mac))")


def record(connect: Callable[[], sqlite3.Connection], lock, result: dict, now: float | None = None) -> list[dict]:
    """Store a scan; returns the devices never seen before on this network (empty on its first scan)."""
    if not result.get("ok"):
        return []
    now = now or time.time()
    network = result["network_id"]
    with lock:
        conn = connect()
        try:
            _ensure(conn)
            rows = conn.execute("SELECT mac, first_seen FROM network_devices WHERE network=?", (network,)).fetchall()
            known = {r[0]: r[1] for r in rows}
            new = [d for d in result["devices"] if d["mac"] not in known] if known else []
            for d in result["devices"]:
                conn.execute("INSERT INTO network_devices VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(network, mac) "
                             "DO UPDATE SET ip=excluded.ip, hostname=COALESCE(NULLIF(excluded.hostname, ''), hostname), "
                             "last_seen=excluded.last_seen",
                             (network, d["mac"], d["ip"], d["hostname"], now, now))
                d["first_seen"] = known.get(d["mac"], now)
            conn.commit()
            result["known_count"] = len(set(known) | {d["mac"] for d in result["devices"]})
        finally:
            conn.close()
    return new


def describe(d: dict) -> str:
    name = d.get("hostname") or ("the router" if d.get("gateway") else
                                 "a device with a private MAC, probably a phone" if d.get("private_mac") else "an unnamed device")
    return f"{name} at {d['ip']} (MAC {d['mac']})"
