"""Make Jarvis4U Pro license keys (seller only; this file is never published).

One-time setup, on YOUR computer:
    python tools/make_license.py --init
  Creates your private signing key at ~/.jarvis4u/license_signing_key.pem (outside every repo)
  and prints the PUBLIC key to put in jarvis_license.py's PUBLIC_KEY_B64. Back the .pem file up
  somewhere safe and private (a USB stick / password manager): if you lose it you can't make new
  keys that old copies of Jarvis accept; if someone else gets it they can make keys too.

After each Selar sale:
    python tools/make_license.py buyer@example.com
  Prints the key to send to the buyer, and appends a line to ~/.jarvis4u/issued_keys.csv
  (email, date, key id) so you can look sales up or revoke a key later.

Check a key someone sends you:
    python tools/make_license.py --check J4U1.xxxx.yyyy
"""
from __future__ import annotations

import base64
import csv
import datetime as dt
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import jarvis_license as lic  # noqa: E402

HOME = Path(os.environ.get("JARVIS4U_SELLER_DIR") or (Path.home() / ".jarvis4u"))
KEY_FILE = HOME / "license_signing_key.pem"
LOG_FILE = HOME / "issued_keys.csv"


def _load_private():
    from cryptography.hazmat.primitives import serialization

    if not KEY_FILE.exists():
        sys.exit(f"No signing key at {KEY_FILE}. Run: python tools/make_license.py --init")
    return serialization.load_pem_private_key(KEY_FILE.read_bytes(), password=None)


def _public_b64(private) -> str:
    from cryptography.hazmat.primitives import serialization

    raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def init() -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if KEY_FILE.exists():
        print(f"You already have a signing key at {KEY_FILE}. Not replacing it (old keys would stop working).")
        print("Your public key:", _public_b64(_load_private()))
        return
    HOME.mkdir(parents=True, exist_ok=True)
    private = Ed25519PrivateKey.generate()
    KEY_FILE.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
    try:
        os.chmod(KEY_FILE, 0o600)
    except OSError:
        pass
    print(f"Created your PRIVATE signing key: {KEY_FILE}")
    print("  -> Back it up somewhere private. Never commit, email or share it.")
    print()
    print("Your PUBLIC key (safe to share; goes in jarvis_license.py PUBLIC_KEY_B64):")
    print(_public_b64(private))


def make(email: str, tier: str = "pro") -> str:
    email = email.strip()
    if "@" not in email or " " in email:
        sys.exit("Give the buyer's email address, e.g. python tools/make_license.py buyer@example.com")
    private = _load_private()
    key_id = secrets.token_hex(4)
    payload = {"e": email, "t": tier, "i": dt.date.today().isoformat(), "n": key_id}
    key = lic.sign(payload, private)
    check = lic.verify(key, _public_b64(private))
    if not check["valid"]:
        sys.exit(f"Self-check failed: {check['reason']}")
    new = not LOG_FILE.exists()
    with LOG_FILE.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["email", "issued", "key_id", "tier"])
        w.writerow([email, payload["i"], key_id, tier])
    return key


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--init":
        init()
        return 0
    if argv[0] == "--check":
        pub = _public_b64(_load_private())
        print(lic.verify(" ".join(argv[1:]), pub))
        return 0
    key = make(argv[0])
    if lic.PUBLIC_KEY_B64 and lic.PUBLIC_KEY_B64 != _public_b64(_load_private()):
        print("WARNING: jarvis_license.py has a different public key than your signing key; "
              "this key won't work in that build.", file=sys.stderr)
    print("License key for", argv[0])
    print(key)
    print()
    print("Send it with: Open Jarvis dashboard -> Settings -> Jarvis4U Pro -> paste -> Activate.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
