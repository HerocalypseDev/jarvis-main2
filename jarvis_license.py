"""Jarvis4U Pro license keys: offline, signed, no server.

A key is `J4U1.<payload>.<signature>` (base64url). The payload is a small JSON object
({"e": buyer email, "t": tier, "i": issue date, "n": key id}); the signature is Ed25519 over the
payload bytes. Jarvis only holds the PUBLIC half of the signing key (PUBLIC_KEY_B64 below), so it
can check a key but can never make one. Keys are made by the seller with tools/make_license.py,
whose private signing key lives only on the seller's own computer (never in any repo).

Honest limits (documented in README/FEATURES): there is no activation count (a buyer could share a
key; the key shows its owner's email in Settings, which discourages it), and like any check in
open-source code it can be edited out. The paid Pro *content* ships separately, so there is still
something real behind the key.

Pure functions, no network, no database. A key is read from the JARVIS_PRO_LICENSE_KEY setting
(write-only in the dashboard, because the name contains KEY).
"""
from __future__ import annotations

import base64
import json
import os
import re

PREFIX = "J4U1"

# Set once by the seller: `python tools/make_license.py --init` prints this value. Empty = this
# build has no Pro license key yet, and every key is reported as "not available in this build".
PUBLIC_KEY_B64 = "JIvxSUPK_7GUrS5m6YsP0ATjXQq_DKlWB79gLXOVc_0"

# Key ids (the "n" field) that were refunded or leaked. Takes effect in the next release.
REVOKED_IDS: frozenset[str] = frozenset()

TIERS = {"pro"}
ENV_KEY = "JARVIS_PRO_LICENSE_KEY"
_KEY_RE = re.compile(r"^J4U1\.[A-Za-z0-9_-]{8,600}\.[A-Za-z0-9_-]{80,90}$")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _clean(key: str) -> str:
    # Keys get pasted from emails: drop spaces/newlines that mail clients insert.
    return re.sub(r"\s+", "", key or "")


def verify(key: str, public_key_b64: str | None = None) -> dict:
    """{"valid": bool, "reason": str, "email", "tier", "issued", "id"} for a pasted key."""
    pub = PUBLIC_KEY_B64 if public_key_b64 is None else public_key_b64
    key = _clean(key)
    if not key:
        return {"valid": False, "reason": "No license key entered."}
    if not pub:
        return {"valid": False, "reason": "Pro licenses aren't available in this build yet."}
    if not _KEY_RE.match(key):
        return {"valid": False, "reason": "That doesn't look like a Jarvis4U license key (it starts with J4U1.)."}
    _, payload_b64, sig_b64 = key.split(".")
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        payload = _b64d(payload_b64)
        Ed25519PublicKey.from_public_bytes(_b64d(pub)).verify(_b64d(sig_b64), payload)
    except InvalidSignature:
        return {"valid": False, "reason": "This license key isn't genuine (the signature doesn't match)."}
    except Exception:
        return {"valid": False, "reason": "This license key is damaged. Copy it again from your email."}
    try:
        data = json.loads(payload.decode("utf-8"))
    except Exception:
        return {"valid": False, "reason": "This license key is damaged. Copy it again from your email."}
    info = {"email": str(data.get("e") or ""), "tier": str(data.get("t") or ""),
            "issued": str(data.get("i") or ""), "id": str(data.get("n") or "")}
    if info["tier"] not in TIERS:
        return {"valid": False, "reason": "This key is for a different product.", **info}
    if info["id"] in REVOKED_IDS:
        return {"valid": False, "reason": "This license key has been cancelled (refunded or shared).", **info}
    return {"valid": True, "reason": "Active.", **info}


def status() -> dict:
    """The license currently saved in settings (the env var), verified. Never returns the key."""
    return verify(os.environ.get(ENV_KEY, ""))


def is_pro() -> bool:
    return bool(status().get("valid"))


def sign(payload: dict, private_key) -> str:
    """Used by tools/make_license.py only (needs the private key object)."""
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return f"{PREFIX}.{_b64e(raw)}.{_b64e(private_key.sign(raw))}"
