"""Signed agent releases, so PC agents can update themselves without trusting the server.

The bridge serves /dist/latest.json: {"version", "wheel", "sha256", "signature"}. The signature is
Ed25519 over `kw-mcp-release:<version>:<wheel>:<sha256>`, made with a key that lives only in the
release machine's keychain. Agents carry the public key below and install nothing that fails it,
so a compromised server can't push code to people's PCs.

The Claude Desktop extension can't replace itself, so latest.json also carries "mcpb":
{"version", "file", "sha256", "signature"} over `kw-mcp-mcpb:<version>:<sha256>`, where version is
the kw-mcp version packed inside. The installed extension uses it to offer a verified download.

  python -m kw_mcp.release keygen                # once: create the key in the keychain, print the public key
  python -m kw_mcp.release sign <wheel> [<mcpb>]  # print latest.json for that wheel (and extension)
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
import tomllib
import zipfile
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

PUBLIC_KEY = "QwRJgXfphlR4iZ1gKTfeAZlC5occZx7bgxaVHeAztw0="  # base64 raw Ed25519 public key (`keygen` prints it)
KEYRING_SERVICE = "kw-campus-release"
KEYRING_USER = "signing-key"
_WHEEL = re.compile(r"^kw_mcp-(?P<version>[0-9][\w.]*)-py3-none-any\.whl$")


def message(version: str, wheel: str, sha256: str) -> bytes:
    return f"kw-mcp-release:{version}:{wheel}:{sha256}".encode()


_RELEASE_VERSION = re.compile(r"\d+(\.\d+){1,3}")  # plain numbers only: no rc/dev tags to compare


def version_tuple(version: str) -> tuple[int, ...]:
    numbers = [int(x) for x in re.findall(r"\d+", version)[:4]]
    return tuple(numbers + [0] * (4 - len(numbers)))  # 0.6 == 0.6.0


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


def mcpb_message(version: str, sha256: str) -> bytes:
    return f"kw-mcp-mcpb:{version}:{sha256}".encode()


def verify_mcpb(entry: dict[str, Any], public_key: str | None = None) -> bool:
    """True if the extension entry of latest.json is well formed and signed by the release key."""
    key = public_key if public_key is not None else PUBLIC_KEY
    try:
        version, sha256, file = str(entry["version"]), str(entry["sha256"]), str(entry["file"])
        if (not key or not re.fullmatch(r"[0-9][\w.]*", version) or not re.fullmatch(r"[0-9a-f]{64}", sha256)
                or not re.fullmatch(r"[\w.-]+\.mcpb", file)):
            return False
        Ed25519PublicKey.from_public_bytes(base64.b64decode(key)).verify(
            base64.b64decode(str(entry["signature"])), mcpb_message(version, sha256))
        return True
    except (KeyError, ValueError, TypeError, InvalidSignature):
        return False


PACKED_PROJECT_FILES = ("pyproject.toml", "uv.lock", "manifest.json")


def sign_mcpb(mcpb_path: Path, private_key: Ed25519PrivateKey, wheel_path: Path | None = None,
              project_dir: Path | None = None) -> dict[str, str]:
    """Sign a packed extension. With wheel_path (and project_dir), refuse unless it carries exactly the
    wheel's code (and the project's lockfile and manifest), so a stale or experimental bundle left in
    dist/ can't go out as a verified update."""
    with zipfile.ZipFile(mcpb_path) as bundle:
        version = tomllib.loads(bundle.read("pyproject.toml").decode())["project"]["version"]
        shown = json.loads(bundle.read("manifest.json"))["version"]
        sources = {n.removeprefix("src/"): bundle.read(n) for n in bundle.namelist()
                   if n.startswith("src/kw_mcp/") and n.endswith(".py")}
        packed_project = {n: bundle.read(n) for n in PACKED_PROJECT_FILES} if project_dir is not None else {}
    if any((project_dir / n).read_bytes() != b for n, b in packed_project.items()):
        raise ValueError(f"{mcpb_path.name} has an older pyproject.toml, uv.lock or manifest.json; repack it")
    if shown != version:
        raise ValueError(f"manifest.json version {shown} differs from pyproject version {version}")
    if not _RELEASE_VERSION.fullmatch(version):
        raise ValueError(f"release versions are plain numbers: {version}")
    if wheel_path is not None:
        with zipfile.ZipFile(wheel_path) as wheel:
            packed = {n: wheel.read(n) for n in wheel.namelist() if n.startswith("kw_mcp/") and n.endswith(".py")}
        if _WHEEL.match(wheel_path.name)["version"] != version or packed != sources:
            raise ValueError(f"{mcpb_path.name} was not packed from the same code as {wheel_path.name}; repack it")
    sha256 = hashlib.sha256(mcpb_path.read_bytes()).hexdigest()
    signature = private_key.sign(mcpb_message(version, sha256))
    return {"version": version, "file": mcpb_path.name, "sha256": sha256,
            "signature": base64.b64encode(signature).decode()}


def sign(wheel_path: Path, private_key: Ed25519PrivateKey) -> dict[str, str]:
    match = _WHEEL.match(wheel_path.name)
    if not match:
        raise ValueError(f"not a kw-mcp wheel: {wheel_path.name}")
    sha256 = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
    version = match["version"]
    if not _RELEASE_VERSION.fullmatch(version):
        raise ValueError(f"release versions are plain numbers: {version}")
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
    elif argv[:1] == ["sign"] and len(argv) in (2, 3):
        key = _load_private_key()
        manifest: dict[str, Any] = sign(Path(argv[1]), key)
        if len(argv) == 3:
            manifest["mcpb"] = sign_mcpb(Path(argv[2]), key, wheel_path=Path(argv[1]), project_dir=Path("."))
        if not verify(manifest) or ("mcpb" in manifest and not verify_mcpb(manifest["mcpb"])):
            raise SystemExit("signature does not match PUBLIC_KEY in kw_mcp/release.py")
        print(json.dumps(manifest))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    _main(sys.argv[1:])
