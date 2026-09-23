"""Network devices card (jarvis_netscan): parsing, new-device detection, route. Temp DB, no real scan."""

import ipaddress
import sqlite3
import threading

import jarvis_netscan as ns

IPCONFIG = """Ethernet adapter Ethernet 2:

   Physical Address. . . . . . . . . : C8-F7-50-3C-B3-B4
Wireless LAN adapter Wi-Fi 2:

   Physical Address. . . . . . . . . : D8-F2-CA-BF-93-E8
   IPv4 Address. . . . . . . . . . . : 192.168.1.20(Preferred)
   Subnet Mask . . . . . . . . . . . : 255.255.255.0
   Default Gateway . . . . . . . . . : 192.168.1.1
"""

ARP = """Interface: 192.168.1.20 --- 0xa
  Internet Address      Physical Address      Type
  192.168.1.1           a0-b1-c2-d3-e4-f5     dynamic
  192.168.1.33          2a-dc-72-62-0a-58     dynamic
  192.168.1.255         ff-ff-ff-ff-ff-ff     static
  224.0.0.22            01-00-5e-00-00-16     static
  10.0.0.5              11-22-33-44-55-66     dynamic
"""


def test_parse_ipconfig_and_arp():
    info = ns.parse_ipconfig(IPCONFIG, "192.168.1.20")
    assert info == {"mask": "255.255.255.0", "mac": "d8:f2:ca:bf:93:e8", "gateway": "192.168.1.1"}
    table = ns.parse_arp(ARP, ipaddress.IPv4Network("192.168.1.0/24"))
    assert table == {"192.168.1.1": "a0:b1:c2:d3:e4:f5", "192.168.1.33": "2a:dc:72:62:0a:58"}
    assert ns.is_private_mac("2a:dc:72:62:0a:58") and not ns.is_private_mac("a0:b1:c2:d3:e4:f5")


def _result(*macs):
    return {"ok": True, "network_id": "gw", "devices": [
        {"ip": f"192.168.1.{i}", "mac": m, "hostname": "", "private_mac": False} for i, m in enumerate(macs, 2)]}


def test_first_scan_is_silent_baseline_then_new_macs_are_reported(tmp_path):
    connect, lock = (lambda: sqlite3.connect(tmp_path / "n.db")), threading.Lock()
    assert ns.record(connect, lock, _result("aa:00:00:00:00:01", "aa:00:00:00:00:02")) == []
    assert ns.record(connect, lock, _result("aa:00:00:00:00:01")) == []  # one left: no alert
    new = ns.record(connect, lock, _result("aa:00:00:00:00:01", "aa:00:00:00:00:03"))
    assert [d["mac"] for d in new] == ["aa:00:00:00:00:03"]
    assert ns.record(connect, lock, _result("aa:00:00:00:00:03", "aa:00:00:00:00:02")) == []  # back again: known
    assert ns.record(connect, lock, {"ok": False, "devices": []}) == []
    assert "aa:00:00:00:00:03" in ns.describe(new[0])


def test_route_serves_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "d.db"))
    import jarvis_dashboard
    from fastapi.testclient import TestClient
    monkeypatch.setitem(jarvis_dashboard.providers, "network_devices", lambda: {"ok": True, "devices": [{"mac": "x"}]})
    with TestClient(jarvis_dashboard._build_app(), base_url="http://127.0.0.1:8765") as c:
        r = c.get("/api/network_devices")
    assert r.status_code == 200 and r.json()["devices"] == [{"mac": "x"}]
    assert r.headers["cache-control"] == "no-store"
