"""Cut a signed kw-mcp release into dist/release/. Run it through scripts/release.sh.

  scripts/release.sh             the release: clean tree, HEAD tagged v<version>, keychain signing key
  scripts/release.sh --dry-run   the same steps signed with a throwaway key, into dist/release-dry-run/
                                 (nothing there verifies against the real key, so it can't be deployed)
  scripts/release.sh stage DIR   copy only the extension's files into DIR (CI packs that)
  scripts/release.sh check-install   build this checkout's wheel and pins and install them like an
                                 agent update does, then run the self-test (CI runs this on every OS)

Steps: refuse a dirty tree or a missing tag; check pyproject, manifest.json and uv.lock agree on the
version; export HEAD (so nothing untracked, like .claude/ worktrees, can get in); `uv lock --check`;
pytest; build the wheel; export the dependency pins from uv.lock; install the wheel into a throwaway
uv tool environment exactly like an agent update does and run its self-test; `mcpb pack` an
allow-listed copy; sign wheel, pins and extension; verify everything; then replace dist/release.
kw-campus/scripts/build_lambda.sh only copies a finished dist/release into the bridge bundle.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MCPB_CLI = "@anthropic-ai/mcpb@2.1.2"


class ReleaseError(RuntimeError):
    pass


def versions(root: Path) -> dict[str, str]:
    """The version pyproject.toml, manifest.json and uv.lock each give kw-mcp."""
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))["version"]
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    locked = next((p.get("version") for p in lock.get("package", []) if p.get("name") == "kw-mcp"), None)
    return {"pyproject.toml": pyproject, "manifest.json": manifest, "uv.lock": str(locked)}


def release_version(root: Path) -> str:
    found = versions(root)
    if len(set(found.values())) != 1:
        raise ReleaseError("versions disagree: " + ", ".join(f"{k} {v}" for k, v in found.items())
                           + " (bump pyproject.toml and manifest.json, then `uv lock`)")
    return found["pyproject.toml"]


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


def dirty(root: Path) -> list[str]:
    return [line for line in git(root, "status", "--porcelain", "--untracked-files=normal").splitlines() if line]


def tagged(root: Path, version: str) -> bool:
    return f"v{version}" in git(root, "tag", "--points-at", "HEAD").split()


def export_head(root: Path, dest: Path) -> None:
    """HEAD's tracked files only."""
    archive = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=root, check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(dest, filter="data")


def stage_bundle(src: Path, dest: Path) -> list[str]:
    """Copy the files the extension needs (release.BUNDLE_FILES and src/kw_mcp) into dest."""
    from kw_mcp import release

    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in sorted(release.BUNDLE_FILES):
        if (src / name).is_file():
            shutil.copy2(src / name, dest / name)
            copied.append(name)
    (dest / "src" / "kw_mcp").mkdir(parents=True, exist_ok=True)
    for path in sorted((src / "src" / "kw_mcp").iterdir()):
        name = f"src/kw_mcp/{path.name}"
        if path.is_file() and not release.bundle_extras([name]):
            shutil.copy2(path, dest / name)
            copied.append(name)
    missing = {"manifest.json", "pyproject.toml", "uv.lock", "LICENSE", "src/kw_mcp/server.py"} - set(copied)
    if missing:
        raise ReleaseError(f"the extension would lack {', '.join(sorted(missing))}")
    return copied


def run(argv: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(argv), flush=True)
    done = subprocess.run(argv, cwd=cwd, env=env, check=False)
    if done.returncode != 0:
        raise ReleaseError(f"failed ({done.returncode}): {' '.join(argv)}")


def npx() -> str:
    for candidate in (shutil.which("npx"), "/opt/homebrew/bin/npx", "/usr/local/bin/npx"):
        if candidate and Path(candidate).exists():
            return candidate
    raise ReleaseError("npx not found (needed for `mcpb pack`); install Node.js")


def smoke_install(src: Path, wheel: Path, constraints: Path, version: str, work: Path) -> None:
    """Install the wheel the way an agent update does (agent.install_argv) into a throwaway uv tool
    environment, then run the self-test the agent runs before restarting."""
    from kw_mcp import agent

    uv = shutil.which("uv") or agent.find_uv()
    if not uv:
        raise ReleaseError("uv not found")
    env = {**os.environ, "UV_TOOL_DIR": str(work / "tools"), "UV_TOOL_BIN_DIR": str(work / "bin")}
    run(agent.install_argv(uv, wheel, constraints), cwd=work, env=env)
    python = work / "tools" / "kw-mcp" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run(agent.self_test_argv(python, version), cwd=work, env=env)


def wheel_and_pins(src: Path, files: Path, version: str) -> tuple[Path, Path]:
    """Build the wheel and write its constraints file (uv.lock's pins plus an exclude-newer cutoff)."""
    from kw_mcp import (
        release,  # the running checkout: the same code as HEAD when the tree is clean
    )

    run(["uv", "build", "--wheel", "--out-dir", str(files)], cwd=src)
    wheel = files / f"kw_mcp-{version}-py3-none-any.whl"
    if not wheel.is_file():
        raise ReleaseError(f"uv build did not produce {wheel.name}")
    exported = subprocess.run(["uv", "export", "--frozen", "--no-dev", "--no-emit-project", "--no-header",
                               "--format", "requirements-txt"], cwd=src, check=True, capture_output=True,
                              text=True).stdout
    constraints = files / release.constraints_name(version)
    constraints.write_text(release.constraints_text(exported, version, datetime.now(UTC)), encoding="utf-8")
    return wheel, constraints


def check_install(root: Path) -> None:
    version = release_version(root)
    with tempfile.TemporaryDirectory(prefix="kw-mcp-install-") as tmp:
        work = Path(tmp)
        wheel, constraints = wheel_and_pins(root, work, version)
        smoke_install(root, wheel, constraints, version, work)
    print(f"{version} installs with its pins and passes the self-test")


def build(root: Path, out: Path, *, dry_run: bool = False) -> dict:
    version = release_version(root)
    if changes := dirty(root):
        if not dry_run:
            raise ReleaseError("the working tree has uncommitted changes; commit or stash them:\n  " + "\n  ".join(changes[:10]))
        print("warning: uncommitted changes are not part of this build (it uses HEAD)", file=sys.stderr)
    if not tagged(root, version):
        if not dry_run:
            raise ReleaseError(f"HEAD is not tagged v{version}; run `git tag v{version}` on the commit to release")
        print(f"warning: HEAD is not tagged v{version}", file=sys.stderr)
    with tempfile.TemporaryDirectory(prefix="kw-mcp-release-") as tmp:
        work = Path(tmp)
        src, files, stage = work / "src", work / "out", work / "stage"
        src.mkdir()
        files.mkdir()
        export_head(root, src)
        if release_version(src) != version:
            raise ReleaseError("HEAD has a different version than the working tree; commit the version bump")
        run(["uv", "lock", "--check"], cwd=src)
        run(["uv", "run", "--frozen", "pytest", "-q"], cwd=src)
        wheel, constraints = wheel_and_pins(src, files, version)
        smoke_install(src, wheel, constraints, version, work)

        from kw_mcp import release

        stage_bundle(src, stage)
        mcpb = files / release.MCPB_NAME
        run([npx(), "--yes", MCPB_CLI, "pack", str(stage), str(mcpb)], cwd=work)

        if dry_run:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PrivateKey,
            )

            key = Ed25519PrivateKey.generate()
            public = base64.b64encode(key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
        else:
            key, public = release.load_private_key(), None  # verify against the shipped PUBLIC_KEY
        manifest = release.sign_release(wheel, constraints, mcpb, key, project_dir=src)
        (files / release.MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        release.check_release(files, public)
        if dry_run:
            (files / "DRY-RUN-NOT-DEPLOYABLE").write_text(f"signed with a throwaway key {public}\n")

        partial = out.with_name(out.name + ".partial")
        shutil.rmtree(partial, ignore_errors=True)
        partial.mkdir(parents=True)
        for name in (manifest["wheel"], manifest["constraints"]["file"], manifest["mcpb"]["file"],
                     release.MANIFEST_NAME, "DRY-RUN-NOT-DEPLOYABLE"):
            if (files / name).is_file():
                shutil.copy2(files / name, partial / name)
        shutil.rmtree(out, ignore_errors=True)
        partial.replace(out)
    print(f"release {version} ready in {out}" + (" (dry run, not deployable)" if dry_run else ""))
    return manifest


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="scripts/release.sh", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="sign with a throwaway key into dist/release-dry-run")
    parser.add_argument("command", nargs="?", choices=["build", "stage", "check-install"], default="build")
    parser.add_argument("dest", nargs="?", help="stage: the folder to fill")
    args = parser.parse_args(argv)
    try:
        if args.command == "stage":
            if not args.dest:
                parser.error("stage needs a destination folder")
            for name in stage_bundle(ROOT, Path(args.dest)):
                print(name)
            return 0
        if args.command == "check-install":
            check_install(ROOT)
            return 0
        build(ROOT, ROOT / "dist" / ("release-dry-run" if args.dry_run else "release"), dry_run=args.dry_run)
    except (ReleaseError, subprocess.CalledProcessError) as e:
        print(f"release stopped: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
