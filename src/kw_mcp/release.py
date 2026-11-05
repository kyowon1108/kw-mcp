"""Signed agent releases, so PC agents can update themselves without trusting the server.

The bridge serves /dist/latest.json: {"version", "wheel", "sha256", "signature"}. The signature is
Ed25519 over `kw-mcp-release:<version>:<wheel>:<sha256>`, made with a key that lives only in the
release machine's keychain. Agents carry the public key below and install nothing that fails it,
so a compromised server can't push code to people's PCs.

  python -m kw_mcp.release keygen        # once: create the key in the keychain, print the public key
  python -m kw_mcp.release sign <wheel>  # print latest.json for that wheel
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

PUBLIC_KEY = "QwRJgXfphlR4iZ1gKTfeAZlC5occZx7bgxaVHeAztw0="  # base64 raw Ed25519 public key (`keygen` prints it)
KEYRING_SERVICE = "kw-campus-release"
KEYRING_USER = "signing-key"
_WHEEL = re.compile(r"^kw_mcp-(?P<version>[0-9][\w.]*)-py3-none-any\.whl$")


def message(version: str, wheel: str, sha256: str) -> bytes:
    return f"kw-mcp-release:{version}:{wheel}:{sha256}".encode()


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", version)[:4])


def verify(manifest: dict[str, Any], public_key: str | None = None) -> bool:
    """True if the manifest is well formed and signed by the release key."""
    key = public_key if public_key is not None else PUBLIC_KEY
    try:
        version, wheel, sha256 = str(manifest["version"]), str(manifest["wheel"]), str(manifest["sha256"])
        match = _WHEEL.match(wheel)
        if not key or not match or match["version"] != version or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            return False
        Ed25519PublicKey.from_public_bytes(base64.b64decode(key)).verify(
            base64.b64decode(str(manifest["signature"])), message(version, wheel, sha256))
        return True
    except (KeyError, ValueError, TypeError, InvalidSignature):
        return False


def sign(wheel_path: Path, private_key: Ed25519PrivateKey) -> dict[str, str]:
    match = _WHEEL.match(wheel_path.name)
    if not match:
        raise ValueError(f"not a kw-mcp wheel: {wheel_path.name}")
    sha256 = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
    version = match["version"]
    signature = private_key.sign(message(version, wheel_path.name, sha256))
    return {"version": version, "wheel": wheel_path.name, "sha256": sha256,
            "signature": base64.b64encode(signature).decode()}


def _load_private_key() -> Ed25519PrivateKey:
    import keyring

    raw = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
    if not raw:
        raise SystemExit("release signing key not found in the keychain; run `python -m kw_mcp.release keygen` first")
    return Ed25519PrivateKey.from_private_bytes(base64.b64decode(raw))


def _main(argv: list[str]) -> None:
    if argv[:1] == ["keygen"]:
        import keyring
        from cryptography.hazmat.primitives import serialization

        if keyring.get_password(KEYRING_SERVICE, KEYRING_USER):
            raise SystemExit("a signing key already exists in the keychain; refusing to replace it")
        key = Ed25519PrivateKey.generate()
        raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                serialization.NoEncryption())
        keyring.set_password(KEYRING_SERVICE, KEYRING_USER, base64.b64encode(raw).decode())
        public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        print(base64.b64encode(public).decode())
    elif argv[:1] == ["sign"] and len(argv) == 2:
        manifest = sign(Path(argv[1]), _load_private_key())
        if not verify(manifest):
            raise SystemExit("signature does not match PUBLIC_KEY in kw_mcp/release.py")
        print(json.dumps(manifest))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    _main(sys.argv[1:])
