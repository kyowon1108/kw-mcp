"""Signed releases, so PC agents and the Claude Desktop extension update without trusting the server.

The bridge serves /dist/latest.json, written by scripts/release.sh on the release machine:

  {"version": "0.9.1",
   "wheel": "kw_mcp-0.9.1-py3-none-any.whl", "sha256": "<hex>", "signature": "<b64>",
   "constraints": {"file": "kw_mcp-0.9.1-constraints.txt", "sha256": "<hex>", "signature": "<b64>"},
   "mcpb": {"version": "0.9.1", "file": "kw-campus.mcpb", "sha256": "<hex>", "signature": "<b64>"}}

Each signature is Ed25519, made with a key that lives only in the release machine's keychain:
  wheel        `kw-mcp-release:<version>:<wheel>:<sha256>` (unchanged since 0.6, so released agents still verify)
  constraints  `kw-mcp-constraints:<version>:<sha256>`: every dependency pinned (exported from uv.lock,
               with an `# exclude-newer:` cutoff line), so an update can't pull an untested package
  mcpb         `kw-mcp-mcpb:<version>:<sha256>`, version being the kw-mcp version packed inside

Agents and the extension carry the public key below and install nothing that fails it. That covers
background updates only: a first install, a manual reinstall with the setup page's command, and the
.mcpb downloaded from /setup trust the server they come from (over TLS).

  python -m kw_mcp.release keygen        # once: create the key in the keychain, print the public key
  python -m kw_mcp.release check <dir>   # verify a release folder (latest.json + the files it names)
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
import tomllib
import zipfile
from datetime import UTC, datetime
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
MANIFEST_NAME = "latest.json"
MCPB_NAME = "kw-campus.mcpb"
_WHEEL = re.compile(r"^kw_mcp-(?P<version>[0-9][\w.]*)-py3-none-any\.whl$")
_CONSTRAINTS = re.compile(r"^kw_mcp-(?P<version>[0-9][\w.]*)-constraints\.txt$")
_EXCLUDE_NEWER = re.compile(r"^# exclude-newer: (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)$", re.MULTILINE)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_RELEASE_VERSION = re.compile(r"\d+(\.\d+){1,3}")  # plain numbers only: no rc/dev tags to compare
# What a .mcpb may contain. Anything else (a stale worktree under .claude/, local settings, caches)
# makes signing refuse the bundle.
BUNDLE_FILES = frozenset({"manifest.json", "icon.png", "pyproject.toml", "uv.lock", ".python-version", "README.md",
                          "LICENSE"})
_BUNDLE_SOURCE = re.compile(r"^src/kw_mcp/(\w+\.py|py\.typed)$")


def message(version: str, wheel: str, sha256: str) -> bytes:
    return f"kw-mcp-release:{version}:{wheel}:{sha256}".encode()


def constraints_message(version: str, sha256: str) -> bytes:
    return f"kw-mcp-constraints:{version}:{sha256}".encode()


def mcpb_message(version: str, sha256: str) -> bytes:
    return f"kw-mcp-mcpb:{version}:{sha256}".encode()


def constraints_name(version: str) -> str:
    return f"kw_mcp-{version}-constraints.txt"


def version_tuple(version: str) -> tuple[int, ...]:
    numbers = [int(x) for x in re.findall(r"\d+", version)[:4]]
    return tuple(numbers + [0] * (4 - len(numbers)))  # 0.6 == 0.6.0


def is_release_version(version: str) -> bool:
    """A version releases may carry: plain numbers, so version_tuple compares them correctly."""
    return bool(_RELEASE_VERSION.fullmatch(version))


def _check(key: str, signature: Any, signed: bytes) -> None:
    Ed25519PublicKey.from_public_bytes(base64.b64decode(key)).verify(base64.b64decode(str(signature)), signed)


def verify(manifest: dict[str, Any], public_key: str | None = None) -> bool:
    """True if the manifest's wheel entry is well formed and signed by the release key."""
    key = public_key if public_key is not None else PUBLIC_KEY
    try:
        version, wheel, sha256 = str(manifest["version"]), str(manifest["wheel"]), str(manifest["sha256"])
        match = _WHEEL.match(wheel)
        if not key or not match or match["version"] != version or not _SHA256.fullmatch(sha256):
            return False
        _check(key, manifest["signature"], message(version, wheel, sha256))
        return True
    except (KeyError, ValueError, TypeError, InvalidSignature):
        return False


def verify_constraints(manifest: dict[str, Any], public_key: str | None = None) -> bool:
    """True if the manifest pins the dependencies of its version with a signed constraints file."""
    key = public_key if public_key is not None else PUBLIC_KEY
    try:
        version, entry = str(manifest["version"]), manifest["constraints"]
        file, sha256 = str(entry["file"]), str(entry["sha256"])
        match = _CONSTRAINTS.match(file)
        if not key or not match or match["version"] != version or not _SHA256.fullmatch(sha256):
            return False
        _check(key, entry["signature"], constraints_message(version, sha256))
        return True
    except (KeyError, ValueError, TypeError, InvalidSignature):
        return False


def verify_mcpb(entry: dict[str, Any], public_key: str | None = None) -> bool:
    """True if the extension entry of latest.json is well formed and signed by the release key."""
    key = public_key if public_key is not None else PUBLIC_KEY
    try:
        version, sha256, file = str(entry["version"]), str(entry["sha256"]), str(entry["file"])
        if (not key or not re.fullmatch(r"[0-9][\w.]*", version) or not _SHA256.fullmatch(sha256)
                or not re.fullmatch(r"[\w.-]+\.mcpb", file)):
            return False
        _check(key, entry["signature"], mcpb_message(version, sha256))
        return True
    except (KeyError, ValueError, TypeError, InvalidSignature):
        return False


def exclude_newer(constraints_text: str) -> str | None:
    """The `--exclude-newer` cutoff written into a constraints file at release time."""
    match = _EXCLUDE_NEWER.search(constraints_text)
    return match.group(1) if match else None


def constraints_text(exported: str, version: str, cutoff: datetime) -> str:
    """A release's constraints file: uv's export of uv.lock plus the cutoff the agent passes to uv."""
    stamp = cutoff.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (f"# kw-mcp {version}: every runtime dependency, pinned from uv.lock (with hashes).\n"
            f"# exclude-newer: {stamp}\n{exported.lstrip()}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wheel_metadata_version(wheel_path: Path, version: str) -> str | None:
    with zipfile.ZipFile(wheel_path) as wheel:
        try:
            metadata = wheel.read(f"kw_mcp-{version}.dist-info/METADATA").decode()
        except KeyError:
            return None
    found = re.search(r"^Version: (\S+)$", metadata, re.MULTILINE)
    return found.group(1) if found else None


def sign(wheel_path: Path, private_key: Ed25519PrivateKey) -> dict[str, str]:
    match = _WHEEL.match(wheel_path.name)
    if not match:
        raise ValueError(f"not a kw-mcp wheel: {wheel_path.name}")
    version = match["version"]
    if not _RELEASE_VERSION.fullmatch(version):
        raise ValueError(f"release versions are plain numbers: {version}")
    # The name is what agents compare; the metadata is what they then report as installed. If the
    # two differed, every agent would reinstall the same release every few minutes.
    if (inside := _wheel_metadata_version(wheel_path, version)) != version:
        raise ValueError(f"{wheel_path.name} says version {inside} inside; rebuild it")
    sha256 = _sha256(wheel_path)
    signature = private_key.sign(message(version, wheel_path.name, sha256))
    return {"version": version, "wheel": wheel_path.name, "sha256": sha256,
            "signature": base64.b64encode(signature).decode()}


def sign_constraints(path: Path, version: str, private_key: Ed25519PrivateKey) -> dict[str, str]:
    if path.name != constraints_name(version):
        raise ValueError(f"constraints file for {version} must be named {constraints_name(version)}")
    if not exclude_newer(path.read_text(encoding="utf-8")):
        raise ValueError(f"{path.name} has no '# exclude-newer:' line")
    sha256 = _sha256(path)
    signature = private_key.sign(constraints_message(version, sha256))
    return {"file": path.name, "sha256": sha256, "signature": base64.b64encode(signature).decode()}


PACKED_PROJECT_FILES = ("pyproject.toml", "uv.lock", "manifest.json")


def bundle_extras(names: list[str]) -> list[str]:
    """Entries of a .mcpb that are not on the allow-list."""
    return sorted(n for n in names if not n.endswith("/") and n not in BUNDLE_FILES and not _BUNDLE_SOURCE.match(n))


def sign_mcpb(mcpb_path: Path, private_key: Ed25519PrivateKey, wheel_path: Path | None = None,
              project_dir: Path | None = None) -> dict[str, str]:
    """Sign a packed extension. Refuse a bundle with files outside the allow-list. With wheel_path
    (and project_dir), refuse unless it carries exactly the wheel's code (and the project's lockfile
    and manifest), so a stale or experimental bundle can't go out as a verified update."""
    with zipfile.ZipFile(mcpb_path) as bundle:
        if extras := bundle_extras(bundle.namelist()):
            raise ValueError(f"{mcpb_path.name} contains files that don't belong in the extension: {', '.join(extras[:5])}")
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
    sha256 = _sha256(mcpb_path)
    signature = private_key.sign(mcpb_message(version, sha256))
    return {"version": version, "file": mcpb_path.name, "sha256": sha256,
            "signature": base64.b64encode(signature).decode()}


def sign_release(wheel: Path, constraints: Path, mcpb: Path, private_key: Ed25519PrivateKey,
                 project_dir: Path) -> dict[str, Any]:
    """latest.json for a release: the wheel, its dependency pins and the extension packed from the same code."""
    manifest: dict[str, Any] = sign(wheel, private_key)
    manifest["constraints"] = sign_constraints(constraints, manifest["version"], private_key)
    manifest["mcpb"] = sign_mcpb(mcpb, private_key, wheel_path=wheel, project_dir=project_dir)
    if manifest["mcpb"]["version"] != manifest["version"]:
        raise ValueError("the extension and the wheel have different versions")
    return manifest


def check_release(folder: Path, public_key: str | None = None) -> dict[str, Any]:
    """Verify a release folder: latest.json signed by the release key, every entry present (wheel,
    constraints, extension) and every file matching its signed hash. Returns the manifest."""
    manifest = json.loads((folder / MANIFEST_NAME).read_text(encoding="utf-8"))
    if not verify(manifest, public_key):
        raise ValueError("latest.json: the wheel entry is not signed by the release key")
    if not verify_constraints(manifest, public_key):
        raise ValueError("latest.json: no signed constraints entry")
    if not isinstance(manifest.get("mcpb"), dict) or not verify_mcpb(manifest["mcpb"], public_key):
        raise ValueError("latest.json: no signed extension (mcpb) entry")
    if manifest["mcpb"]["version"] != manifest["version"]:
        raise ValueError("latest.json: the extension and the wheel have different versions")
    for name, sha256 in ((manifest["wheel"], manifest["sha256"]),
                         (manifest["constraints"]["file"], manifest["constraints"]["sha256"]),
                         (manifest["mcpb"]["file"], manifest["mcpb"]["sha256"])):
        path = folder / name
        if not path.is_file() or _sha256(path) != sha256:
            raise ValueError(f"{name} is missing or does not match its signed hash")
    return manifest


def load_private_key() -> Ed25519PrivateKey:
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
    elif argv[:1] == ["check"] and len(argv) == 2:
        try:
            manifest = check_release(Path(argv[1]))
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise SystemExit(f"release check failed: {e}") from None
        print(f"release {manifest['version']} verified: {manifest['wheel']}, {manifest['constraints']['file']}, "
              f"{manifest['mcpb']['file']}")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    _main(sys.argv[1:])
