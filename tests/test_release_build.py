"""Release signing (wheel metadata, signed pins, bundle allow-list, release check) and scripts/release.py's gates."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kw_mcp import release

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import release as release_script

sys.path.pop(0)


@pytest.fixture
def key(monkeypatch):
    private = Ed25519PrivateKey.generate()  # throwaway: tests never touch the release key
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setattr(release, "PUBLIC_KEY", base64.b64encode(public).decode())
    return private


def wheel(folder: Path, version="0.9.1", inside=None, code=b"print('v')") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"kw_mcp-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("kw_mcp/server.py", code)
        z.writestr(f"kw_mcp-{version}.dist-info/METADATA", f"Metadata-Version: 2.4\nName: kw-mcp\nVersion: {inside or version}\n")
    return path


def pins(folder: Path, version="0.9.1") -> Path:
    path = folder / release.constraints_name(version)
    path.write_text(release.constraints_text("httpx==0.28.1 \\\n    --hash=sha256:ab\n", version, datetime(2026, 11, 6, tzinfo=UTC)))
    return path


NOTES = ["공지 첨부까지 읽어요", "학사 안내가 늘었어요"]


def bundle(path: Path, version="0.9.1", code=b"print('v')", extra: dict[str, bytes] | None = None,
           project: Path | None = None, notes: dict | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("pyproject.toml", f'[project]\nname = "kw-mcp"\nversion = "{version}"\n')
        z.writestr("manifest.json", json.dumps({"version": version}))
        z.writestr("uv.lock", "lock")
        z.writestr(release.RELEASE_NOTES_NAME, json.dumps(notes if notes is not None else {version: NOTES},
                                                          ensure_ascii=False))
        z.writestr("LICENSE", "MIT License")
        z.writestr("src/kw_mcp/server.py", code)
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    if project is not None:
        project.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path) as z:
            for name in release.PACKED_PROJECT_FILES:
                (project / name).write_bytes(z.read(name))
    return path


def test_a_wheel_whose_metadata_disagrees_with_its_name_is_refused(tmp_path, key):
    with pytest.raises(ValueError, match="version 0.9.0 inside"):
        release.sign(wheel(tmp_path, "0.9.1", inside="0.9.0"), key)
    assert release.verify(release.sign(wheel(tmp_path / "ok"), key))


def test_constraints_are_signed_for_their_version_only(tmp_path, key):
    m = release.sign(wheel(tmp_path), key)
    m["constraints"] = release.sign_constraints(pins(tmp_path), "0.9.1", key)
    assert release.verify_constraints(m) and release.verify(m)  # the wheel signature is unchanged
    assert release.exclude_newer(pins(tmp_path).read_text()) == "2026-11-06T00:00:00Z"
    assert not release.verify_constraints({**m, "constraints": {**m["constraints"], "sha256": "0" * 64}})
    assert not release.verify_constraints({**m, "version": "0.9.2"})
    other = release.sign_constraints(pins(tmp_path), "0.9.1", Ed25519PrivateKey.generate())
    assert not release.verify_constraints({**m, "constraints": other})
    assert not release.verify_constraints({k: v for k, v in m.items() if k != "constraints"})
    with pytest.raises(ValueError, match="must be named"):
        release.sign_constraints(pins(tmp_path), "0.9.2", key)
    (tmp_path / "kw_mcp-0.9.3-constraints.txt").write_text("httpx==0.28.1\n")
    with pytest.raises(ValueError, match="exclude-newer"):
        release.sign_constraints(tmp_path / "kw_mcp-0.9.3-constraints.txt", "0.9.3", key)


@pytest.mark.parametrize("extra", [
    ".claude/worktrees/old-branch/src/kw_mcp/agent.py",
    ".claude/settings.local.json",
    "src/kw_mcp/__pycache__/agent.cpython-313.pyc",
    "tests/test_agent.py",
    ".env",
])
def test_a_bundle_with_anything_off_the_allow_list_is_not_signed(tmp_path, key, extra):
    with pytest.raises(ValueError, match="don't belong"):
        release.sign_mcpb(bundle(tmp_path / "kw-campus.mcpb", extra={extra: b"x"}), key)


def test_a_full_release_signs_and_checks(tmp_path, key):
    out = tmp_path / "release"
    w, p = wheel(out), pins(out)
    mcpb = bundle(out / "kw-campus.mcpb", project=tmp_path / "project")
    manifest = release.sign_release(w, p, mcpb, key, project_dir=tmp_path / "project")
    (out / "latest.json").write_text(json.dumps(manifest))
    assert release.check_release(out)["version"] == "0.9.1"
    assert manifest["mcpb"]["notes"] == NOTES and release.verify_notes(manifest["mcpb"])
    assert release.verify_mcpb(manifest["mcpb"])  # the file's signature is unchanged: older extensions still verify
    for bad in ({"notes": NOTES + ["끼워 넣은 줄"]}, {"notes_signature": manifest["mcpb"]["signature"]}):
        (out / "latest.json").write_text(json.dumps({**manifest, "mcpb": {**manifest["mcpb"], **bad}}))
        with pytest.raises(ValueError, match="notes"):
            release.check_release(out)
    old = {k: v for k, v in manifest["mcpb"].items() if not k.startswith("notes")}  # a release from before notes
    (out / "latest.json").write_text(json.dumps({**manifest, "mcpb": old}))
    assert release.check_release(out)["version"] == "0.9.1"
    (out / "latest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="not packed from the same code"):
        release.sign_release(w, p, bundle(tmp_path / "stale.mcpb", code=b"old"), key, project_dir=tmp_path / "project")
    p.write_text(p.read_text() + "evil==1\n")
    with pytest.raises(ValueError, match="does not match"):
        release.check_release(out)
    (out / "latest.json").write_text(json.dumps({k: v for k, v in manifest.items() if k != "mcpb"}))
    with pytest.raises(ValueError, match="extension"):
        release.check_release(out)
    (out / "latest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="not signed by the release key"):
        release.check_release(out, public_key=base64.b64encode(b"\x01" * 32).decode())


def test_release_check_cli_reports_failure(tmp_path):
    (tmp_path / "latest.json").write_text("{}")
    with pytest.raises(SystemExit, match="release check failed"):
        release._main(["check", str(tmp_path)])


# --- scripts/release.py gates --------------------------------------------------------------

def project(tmp_path: Path, version="0.9.1", manifest_version=None) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text(f'[project]\nname = "kw-mcp"\nversion = "{version}"\n')
    (root / "manifest.json").write_text(json.dumps({"version": manifest_version or version}))
    (root / "uv.lock").write_text(f'version = 1\n\n[[package]]\nname = "kw-mcp"\nversion = "{version}"\n')
    for args in (["init", "-q"], ["add", "."], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root


def test_versions_must_agree(tmp_path):
    root = project(tmp_path, manifest_version="0.9.0")
    with pytest.raises(release_script.ReleaseError, match="versions disagree"):
        release_script.release_version(root)


def test_a_release_needs_a_clean_tree_and_its_tag(tmp_path):
    root = project(tmp_path)
    (root / "half-done.py").write_text("x")
    with pytest.raises(release_script.ReleaseError, match="uncommitted"):
        release_script.build(root, tmp_path / "out")
    (root / "half-done.py").unlink()
    with pytest.raises(release_script.ReleaseError, match="not tagged v0.9.1"):
        release_script.build(root, tmp_path / "out")
    subprocess.run(["git", "tag", "v0.9.1"], cwd=root, check=True)
    assert release_script.tagged(root, "0.9.1") and not release_script.dirty(root)
    assert not (tmp_path / "out").exists()


def test_head_is_exported_without_untracked_files(tmp_path):
    root = project(tmp_path)
    (root / ".claude").mkdir()
    (root / ".claude" / "settings.local.json").write_text("{}")
    release_script.export_head(root, tmp_path / "export")
    assert sorted(p.name for p in (tmp_path / "export").iterdir()) == ["manifest.json", "pyproject.toml", "uv.lock"]


# --- release notes --------------------------------------------------------------------------

def test_notes_are_signed_apart_from_the_file_and_tampering_fails(key):
    entry = {"version": "0.9.1", **release.sign_notes("0.9.1", NOTES, key)}
    assert release.verify_notes(entry)
    assert release.notes_message("0.9.1", NOTES).startswith(b"kw-mcp-notes:0.9.1:")
    assert not release.verify_notes({**entry, "notes": [*NOTES[:1], "다른 문장"]})
    assert not release.verify_notes({**entry, "version": "0.9.2"})  # notes of one version can't ride another
    other = release.sign_notes("0.9.1", NOTES, Ed25519PrivateKey.generate())
    assert not release.verify_notes({**entry, **other})
    assert not release.verify_notes({"version": "0.9.1", "notes": NOTES}) and not release.verify_notes({})
    with pytest.raises(ValueError, match="1-5 lines"):
        release.sign_notes("0.9.1", ["줄"] * 6, key)


def test_notes_must_be_a_few_short_lines():
    assert release.notes_ok(NOTES) and release.notes_ok(["가" * 80])
    for bad in ([], ["줄"] * 6, ["가" * 81], ["두 줄\n이에요"], [" "], [1], "한 줄", None):
        assert not release.notes_ok(bad), bad


def test_a_release_without_notes_for_its_version_is_refused(tmp_path, key):
    project_dir = tmp_path / "project"
    with pytest.raises(ValueError, match="release_notes.json is missing"):
        release.release_notes(project_dir, "0.9.1")
    out = tmp_path / "release"
    out.mkdir()
    mcpb = bundle(out / "kw-campus.mcpb", project=project_dir, notes={"0.9.0": NOTES})
    with pytest.raises(ValueError, match="no entry for 0.9.1"):
        release.sign_release(wheel(out), pins(out), mcpb, key, project_dir=project_dir)
    (project_dir / release.RELEASE_NOTES_NAME).write_text(json.dumps({"0.9.1": ["가" * 81]}))
    with pytest.raises(ValueError, match="at most 80"):
        release.release_notes(project_dir, "0.9.1")


def test_the_release_script_stops_without_notes_for_the_version(tmp_path):
    root = project(tmp_path)
    subprocess.run(["git", "tag", "v0.9.1"], cwd=root, check=True)
    with pytest.raises(release_script.ReleaseError, match="release_notes.json is missing"):
        release_script.build(root, tmp_path / "out")
    (root / release.RELEASE_NOTES_NAME).write_text(json.dumps({"0.9.0": NOTES}, ensure_ascii=False))
    with pytest.raises(release_script.ReleaseError, match="no entry for 0.9.1"):
        release_script.check_notes(root, "0.9.1")
    assert release_script.check_notes(ROOT, release_script.release_version(ROOT))  # this tree's version has lines
    assert not (tmp_path / "out").exists()


def test_the_extension_packs_and_compares_release_notes(tmp_path, key):
    assert release.RELEASE_NOTES_NAME in release.BUNDLE_FILES and release.RELEASE_NOTES_NAME in release.PACKED_PROJECT_FILES
    project_dir = tmp_path / "project"
    mcpb = bundle(tmp_path / "kw-campus.mcpb", project=project_dir)
    assert release.sign_mcpb(mcpb, key, project_dir=project_dir)["version"] == "0.9.1"
    (project_dir / release.RELEASE_NOTES_NAME).write_text(json.dumps({"0.9.1": ["고친 문장"]}, ensure_ascii=False))
    with pytest.raises(ValueError, match="release_notes.json; repack"):
        release.sign_mcpb(mcpb, key, project_dir=project_dir)
