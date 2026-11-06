"""Cut a signed kw-mcp release into dist/release/. Run it through scripts/release.sh.

  scripts/release.sh             the release: clean tree, HEAD tagged v<version>, a version above
                                 every earlier release, keychain signing key
  scripts/release.sh --dry-run   the same steps signed with a throwaway key, into dist/release-dry-run/
                                 (nothing there verifies against the real key, so it can't be deployed)
  scripts/release.sh --last-latest-json FILE
                                 also refuse unless the version is above the one in FILE (save the
                                 bridge's /dist/latest.json there: the version agents run now)
  scripts/release.sh stage DIR   copy only the extension's files into DIR
  scripts/release.sh pack FILE   stage this checkout and pack it into FILE exactly as a release does
                                 (CI validates and unpacks that with mcpb)
  scripts/release.sh check-install   build this checkout's wheel and pins and install them like an
                                 agent update does, then run the self-test (CI runs this on every OS)

Steps: refuse a dirty tree, a missing tag or a version that isn't above the last release; check
pyproject, manifest.json and uv.lock agree on the version; export HEAD (so nothing untracked, like
.claude/ worktrees, can get in); pack the allow-listed extension (.mcpb, a zip made here in Python)
before any third-party code runs; `uv lock --check`; pytest; build the wheel; export the dependency
pins from uv.lock; install the wheel into a throwaway uv tool environment exactly like an agent update
does (dependencies hash-checked) and run its self-test; check that the extension, wheel and pins are
still the bytes recorded when they were made; only then load the key and sign; verify everything;
then replace dist/release. No npm code runs in a release: it could read the signing key.
kw-campus/scripts/build_lambda.sh only copies a finished dist/release into the bridge bundle.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# What `mcpb pack` (@anthropic-ai/mcpb 2.1.2) accepts; its full schema check runs in CI (packaging.yml).
MANIFEST_VERSIONS = frozenset({"0.1", "0.2", "0.3", "0.4"})
SERVER_TYPES = frozenset({"python", "node", "binary", "uv"})


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


def earlier_releases(root: Path, manifests: list[Path]) -> dict[str, str]:
    """Versions already released, by where they were found: tags v<version> on commits other than
    HEAD, and the given latest.json files that exist (the last dist/release, the bridge's copy)."""
    from kw_mcp import release

    at_head = set(git(root, "tag", "--points-at", "HEAD").split())
    found = {f"tag {tag}": tag[1:] for tag in git(root, "tag", "--list", "v*").split()
             if tag not in at_head and release.is_release_version(tag[1:])}
    for path in manifests:
        if not path.is_file():
            continue
        try:
            found[str(path)] = str(json.loads(path.read_text(encoding="utf-8"))["version"])
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise ReleaseError(f"can't read the released version in {path} ({e.__class__.__name__})") from None
    return found


def check_newer(root: Path, version: str, manifests: list[Path]) -> None:
    """Refuse a version that isn't above every earlier release: agents and the extension only take a
    higher version, so the same or a lower one would never reach anybody."""
    from kw_mcp import release

    earlier = earlier_releases(root, manifests)
    if not earlier:
        print(f"note: no earlier release found (no v* tag before this commit, no latest.json), so nothing shows "
              f"that {version} is above what agents run now. Save the bridge's /dist/latest.json and pass it "
              "with --last-latest-json to check.", file=sys.stderr)
        return
    where, newest = max(earlier.items(), key=lambda item: release.version_tuple(item[1]))
    if release.version_tuple(version) <= release.version_tuple(newest):
        hint = (" If that folder was never deployed, delete it and run again."
                if where.endswith(str(Path("dist") / "release" / release.MANIFEST_NAME)) else "")
        raise ReleaseError(f"{version} is not above the last release {newest} ({where}); bump pyproject.toml "
                           f"and manifest.json, then `uv lock`.{hint}")


def export_head(root: Path, dest: Path) -> None:
    """HEAD's tracked files only."""
    archive = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=root, check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(dest, filter="data")


def commit_time(root: Path) -> datetime:
    """HEAD's commit time: the timestamp packed files get, so the same commit packs the same bytes."""
    return datetime.fromtimestamp(int(git(root, "log", "-1", "--format=%ct", "HEAD").strip()), UTC)


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
    missing = {"manifest.json", "icon.png", "pyproject.toml", "uv.lock", "LICENSE", "src/kw_mcp/server.py"} - set(copied)
    if missing:
        raise ReleaseError(f"the extension would lack {', '.join(sorted(missing))}")
    return copied


def check_bundle_manifest(stage: Path) -> dict:
    """The checks `mcpb pack` makes before packing that matter to Claude Desktop: a manifest version
    it knows, the required fields, and a server it can start from a file in the bundle."""
    try:
        manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ReleaseError(f"manifest.json can't be read ({e.__class__.__name__})") from None
    problems = []
    if not isinstance(manifest, dict):
        raise ReleaseError("manifest.json is not a JSON object")
    if manifest.get("manifest_version") not in MANIFEST_VERSIONS:
        problems.append(f"manifest_version {manifest.get('manifest_version')!r}")
    problems += [key for key in ("name", "version", "description")
                 if not isinstance(manifest.get(key), str) or not manifest[key].strip()]
    author = manifest.get("author")
    if not isinstance(author, dict) or not isinstance(author.get("name"), str) or not author["name"].strip():
        problems.append("author.name")
    server = manifest.get("server")
    server = server if isinstance(server, dict) else {}
    config = server.get("mcp_config") if isinstance(server.get("mcp_config"), dict) else {}
    entry = server.get("entry_point")
    if server.get("type") not in SERVER_TYPES:
        problems.append("server.type")
    if not isinstance(entry, str) or not (stage / entry).is_file():
        problems.append("server.entry_point (a file in the bundle)")
    if not isinstance(config.get("command"), str) or not config["command"]:
        problems.append("server.mcp_config.command")
    if not all(isinstance(a, str) for a in config.get("args", [])):
        problems.append("server.mcp_config.args")
    env = config.get("env", {})
    if not isinstance(env, dict) or not all(isinstance(v, str) for v in env.values()):
        problems.append("server.mcp_config.env")
    if problems:
        raise ReleaseError("manifest.json is not a valid extension manifest: " + ", ".join(problems))
    return manifest


def pack_mcpb(stage: Path, out: Path, when: datetime) -> list[str]:
    """Zip an allow-listed stage into a .mcpb the way `mcpb pack` does: every file under its path in
    the stage (forward slashes, manifest.json at the root, no folder entries), deflated, with Unix
    permissions. Only this code runs, so no npm package touches what gets signed."""
    from kw_mcp import release

    check_bundle_manifest(stage)
    names = sorted(p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file())
    if extras := release.bundle_extras(names):
        raise ReleaseError(f"the stage has files that don't belong in the extension: {', '.join(extras[:5])}")
    stamp = when.astimezone(UTC).timetuple()[:6]
    partial = out.with_name(out.name + ".part")
    with zipfile.ZipFile(partial, "w") as bundle:
        for name in names:
            info = zipfile.ZipInfo(name, date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3  # Unix, so the permissions below are read on macOS
            info.external_attr = 0o644 << 16
            bundle.writestr(info, (stage / name).read_bytes(), compresslevel=9)
    partial.replace(out)
    return names


def run(argv: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(argv), flush=True)
    done = subprocess.run(argv, cwd=cwd, env=env, check=False)
    if done.returncode != 0:
        raise ReleaseError(f"failed ({done.returncode}): {' '.join(argv)}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unchanged(recorded: dict[Path, str], after: str) -> None:
    """Refuse to go on if a file changed since its hash was recorded."""
    changed = [path.name for path, digest in recorded.items() if not path.is_file() or sha256(path) != digest]
    if changed:
        raise ReleaseError(f"{', '.join(changed)} changed during {after}; nothing was signed")


def smoke_install(src: Path, wheel: Path, constraints: Path, version: str, work: Path) -> None:
    """Install the wheel the way an agent update does (agent.install_steps: uv tool install with the
    pins, then every dependency reinstalled with its hash checked) into a throwaway uv tool
    environment, then run the self-test the agent runs before restarting."""
    from kw_mcp import agent

    uv = shutil.which("uv") or agent.find_uv()
    if not uv:
        raise ReleaseError("uv not found")
    env = {**os.environ, "UV_TOOL_DIR": str(work / "tools"), "UV_TOOL_BIN_DIR": str(work / "bin")}
    python = work / "tools" / "kw-mcp" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    for step in agent.install_steps(uv, wheel, constraints, python):
        run(step, cwd=work, env=env)
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


def pack(root: Path, out: Path) -> list[str]:
    """Stage this checkout and pack it into `out` as a release does (CI checks the result with mcpb)."""
    with tempfile.TemporaryDirectory(prefix="kw-mcp-stage-") as tmp:
        stage = Path(tmp) / "stage"
        stage_bundle(root, stage)
        out.parent.mkdir(parents=True, exist_ok=True)
        return pack_mcpb(stage, out, commit_time(root))


def build(root: Path, out: Path, *, dry_run: bool = False, last_manifest: Path | None = None) -> dict:
    from kw_mcp import release

    version = release_version(root)
    if changes := dirty(root):
        if not dry_run:
            raise ReleaseError("the working tree has uncommitted changes; commit or stash them:\n  " + "\n  ".join(changes[:10]))
        print("warning: uncommitted changes are not part of this build (it uses HEAD)", file=sys.stderr)
    if not tagged(root, version):
        if not dry_run:
            raise ReleaseError(f"HEAD is not tagged v{version}; run `git tag v{version}` on the commit to release")
        print(f"warning: HEAD is not tagged v{version}", file=sys.stderr)
    try:
        check_newer(root, version, [root / "dist" / "release" / release.MANIFEST_NAME,
                                    *([last_manifest] if last_manifest else [])])
    except ReleaseError as e:
        if not dry_run:
            raise
        print(f"warning: {e}", file=sys.stderr)
    with tempfile.TemporaryDirectory(prefix="kw-mcp-release-") as tmp:
        work = Path(tmp)
        src, files, stage = work / "src", work / "out", work / "stage"
        src.mkdir()
        files.mkdir()
        export_head(root, src)
        if release_version(src) != version:
            raise ReleaseError("HEAD has a different version than the working tree; commit the version bump")
        # Packed straight from the export, before uv, pytest or any dependency runs: what they could
        # change afterwards no longer matches the hash recorded here.
        stage_bundle(src, stage)
        mcpb = files / release.MCPB_NAME
        pack_mcpb(stage, mcpb, commit_time(root))
        recorded = {mcpb: sha256(mcpb)}

        run(["uv", "lock", "--check"], cwd=src)
        run(["uv", "run", "--frozen", "pytest", "-q"], cwd=src)
        wheel, constraints = wheel_and_pins(src, files, version)
        recorded |= {wheel: sha256(wheel), constraints: sha256(constraints)}
        smoke_install(src, wheel, constraints, version, work)
        unchanged(recorded, "the test install")

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
        signed = {wheel: manifest["sha256"], constraints: manifest["constraints"]["sha256"], mcpb: manifest["mcpb"]["sha256"]}
        if signed != recorded:  # the bytes read while signing must be the ones tested
            raise ReleaseError("a file changed while it was being signed; nothing was written")
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
    parser.add_argument("--last-latest-json", type=Path, metavar="FILE",
                        help="the bridge's /dist/latest.json: refuse unless the new version is above it")
    parser.add_argument("command", nargs="?", choices=["build", "stage", "pack", "check-install"], default="build")
    parser.add_argument("dest", nargs="?", help="stage: the folder to fill; pack: the .mcpb to write")
    args = parser.parse_args(argv)
    try:
        if args.command in ("stage", "pack"):
            if not args.dest:
                parser.error(f"{args.command} needs a destination")
            names = stage_bundle(ROOT, Path(args.dest)) if args.command == "stage" else pack(ROOT, Path(args.dest))
            for name in names:
                print(name)
            return 0
        if args.command == "check-install":
            check_install(ROOT)
            return 0
        if args.last_latest_json is not None and not args.last_latest_json.is_file():
            parser.error(f"--last-latest-json: {args.last_latest_json} does not exist")
        build(ROOT, ROOT / "dist" / ("release-dry-run" if args.dry_run else "release"), dry_run=args.dry_run,
              last_manifest=args.last_latest_json)
    except (ReleaseError, subprocess.CalledProcessError, ValueError) as e:  # ValueError: a signing refusal
        print(f"release stopped: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
