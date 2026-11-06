"""What gets packed and installed: versions, manifest tool list, platform pins, bundle allow-list."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

from packaging.markers import Marker
from packaging.requirements import Requirement

from kw_mcp import release

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
# The environments students install on (marker values as Python reports them).
STUDENT_PCS = {
    "Apple Silicon Mac": {"sys_platform": "darwin", "platform_machine": "arm64"},
    "Intel Mac": {"sys_platform": "darwin", "platform_machine": "x86_64"},
    "Windows x64": {"sys_platform": "win32", "platform_machine": "AMD64"},
    "Windows on ARM": {"sys_platform": "win32", "platform_machine": "ARM64"},
    "Linux": {"sys_platform": "linux", "platform_machine": "x86_64"},
}


def test_manifest_pyproject_and_lock_agree_on_the_version():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import release as release_script
    finally:
        sys.path.pop(0)
    found = release_script.versions(ROOT)
    assert len(set(found.values())) == 1, found


def test_manifest_lists_exactly_the_tools_the_extension_registers():
    # The update tools exist only inside the extension (KW_MCP_DISTRIBUTION=mcpb): ask a fresh process.
    code = ("import asyncio, json; from kw_mcp import server; "
            "print(json.dumps(sorted(t.name for t in asyncio.run(server.mcp.list_tools()))))")
    env = {**os.environ, "KW_MCP_DISTRIBUTION": "mcpb", "KW_CAMPUS_INVITE": ""}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True).stdout
    registered = set(json.loads(out.strip().splitlines()[-1]))
    listed = [t["name"] for t in MANIFEST["tools"]]
    assert len(listed) == len(set(listed))
    assert set(listed) == registered, (set(listed) - registered, registered - set(listed))
    assert all(t.get("description") for t in MANIFEST["tools"])


def test_manifest_runs_the_locked_environment_and_a_runnable_entry_point():
    config = MANIFEST["server"]["mcp_config"]
    assert config["command"] == "uv" and config["args"][:3] == ["run", "--frozen", "--no-dev"]
    assert config["env"]["KW_MCP_DISTRIBUTION"] == "mcpb"
    entry = MANIFEST["server"]["entry_point"]
    assert (ROOT / entry).is_file() and not release.bundle_extras([entry])
    assert "from kw_mcp import" in (ROOT / entry).read_text()  # absolute import: works when run as a file


def test_manifest_wording_matches_what_the_code_does():
    text = MANIFEST["long_description"]
    assert "2회를 넘거나" not in text  # the old, wrong promise
    assert "바꿀 때까지 다시 시도하지 않" in text and "서명" in text and "복사가 금지된 PDF" in text
    assert "요청할 때만" in text and "학습용" in text
    assert "새 버전 알림" in MANIFEST["user_config"]["campus_invite"]["description"]
    assert MANIFEST["license"] == "MIT" and (ROOT / "LICENSE").read_text().startswith("MIT License")
    assert PYPROJECT["project"]["license"] == "MIT"


def test_every_student_pc_gets_exactly_one_cryptography_with_a_wheel():
    pins = [Requirement(r) for r in PYPROJECT["project"]["dependencies"] if r.startswith("cryptography")]
    for name, env in STUDENT_PCS.items():
        chosen = [r for r in pins if r.marker is None or r.marker.evaluate(env)]
        assert len(chosen) == 1, name
    intel = next(r for r in pins if r.marker.evaluate(STUDENT_PCS["Intel Mac"]))
    arm = next(r for r in pins if r.marker.evaluate(STUDENT_PCS["Windows on ARM"]))
    assert intel.specifier.contains("48.0.1") and not intel.specifier.contains("49.0.0")  # last universal2 wheel
    assert arm.specifier.contains("46.0.3") and not arm.specifier.contains("46.0.4")  # last win_arm64 wheel
    required = [Marker(m) for m in PYPROJECT["tool"]["uv"]["required-environments"]]
    for name in ("Apple Silicon Mac", "Intel Mac", "Windows x64", "Windows on ARM"):
        assert any(m.evaluate(STUDENT_PCS[name]) for m in required), name


def test_every_dependency_has_a_major_version_ceiling():
    for spec in PYPROJECT["project"]["dependencies"]:
        req = Requirement(spec)
        if req.name == "tzdata":  # data only
            continue
        assert any(s.operator in ("<", "==") for s in req.specifier), spec
    assert not any(Requirement(s).extras for s in PYPROJECT["project"]["dependencies"])  # no unused mcp[cli]


def test_the_locked_cryptography_versions_have_wheels_for_their_platforms():
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    wheels = {p["version"]: [w["url"].rsplit("/", 1)[-1] for w in p.get("wheels", [])]
              for p in lock["package"] if p["name"] == "cryptography"}
    assert any("universal2" in w or "x86_64" in w for w in wheels["48.0.1"])
    assert any("win_arm64" in w for w in wheels["46.0.3"])
    newest = max(wheels, key=release.version_tuple)
    assert any("macosx_11_0_arm64" in w for w in wheels[newest]) and any("win_amd64" in w for w in wheels[newest])


def test_dev_folders_are_kept_out_of_a_hand_packed_bundle():
    ignored = (ROOT / ".mcpbignore").read_text().split()
    for folder in (".claude/", ".omc/", ".github/", "tests/", "docs/", "scripts/", "dist/", ".venv/"):
        assert folder in ignored, folder


def test_staging_copies_only_the_allow_list(tmp_path):
    (ROOT / ".claude" / "worktrees").exists()  # whatever is there must not matter
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import release as release_script
    finally:
        sys.path.pop(0)
    copied = release_script.stage_bundle(ROOT, tmp_path / "stage")
    assert {"manifest.json", "pyproject.toml", "uv.lock", "LICENSE", "README.md", "src/kw_mcp/server.py"} <= set(copied)
    on_disk = sorted(str(p.relative_to(tmp_path / "stage")).replace(os.sep, "/")
                     for p in (tmp_path / "stage").rglob("*") if p.is_file())
    assert on_disk == sorted(copied) and not release.bundle_extras(on_disk)
