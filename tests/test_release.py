import base64
import hashlib
import json
import zipfile
from pathlib import Path

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kw_mcp import agent, release

SERVER = "https://bridge.example"
PINS = "# kw-mcp 0.9.0\n# exclude-newer: 2026-11-01T00:00:00Z\nhttpx==0.28.1 \\\n    --hash=sha256:00\n"


@pytest.fixture(autouse=True)
def config_dir(tmp_path, monkeypatch):
    """Never touch the real ~/.config/kw-campus."""
    monkeypatch.setattr(agent, "CONFIG_DIR", tmp_path / "config")
    return tmp_path / "config"


@pytest.fixture
def key(monkeypatch):
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setattr(release, "PUBLIC_KEY", base64.b64encode(public).decode())
    return private


def wheel_file(folder, version="0.9.0", inside=None, code=b"print('hi')"):
    folder.mkdir(parents=True, exist_ok=True)
    wheel = folder / f"kw_mcp-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as z:
        z.writestr("kw_mcp/__init__.py", code)
        z.writestr(f"kw_mcp-{version}.dist-info/METADATA", f"Metadata-Version: 2.4\nName: kw-mcp\nVersion: {inside or version}\n")
    return wheel


def manifest_for(tmp_path, private, version="0.9.0"):
    """latest.json with a signed wheel and signed pins, plus the bytes the bridge serves."""
    wheel = wheel_file(tmp_path / "rel", version)
    pins = tmp_path / "rel" / release.constraints_name(version)
    pins.write_text(PINS.replace("0.9.0", version))
    m = release.sign(wheel, private)
    m["constraints"] = release.sign_constraints(pins, version, private)
    return m, wheel.read_bytes(), pins.read_bytes()


def test_signed_manifest_verifies_and_tampering_fails(tmp_path, key):
    m, wheel, _ = manifest_for(tmp_path, key)
    assert m["sha256"] == hashlib.sha256(wheel).hexdigest() and release.verify(m)
    assert not release.verify({**m, "sha256": "0" * 64})
    assert not release.verify({**m, "version": "9.9.9"})  # wheel name and version disagree
    assert not release.verify({**m, "wheel": "evil-9.9.9-py3-none-any.whl"})
    other = Ed25519PrivateKey.generate()
    assert not release.verify(manifest_for(tmp_path / "other", other)[0])
    assert not release.verify({})


def test_shipped_public_key_is_set():
    assert len(base64.b64decode(release.PUBLIC_KEY)) == 32


@respx.mock
async def test_fetch_update_takes_only_newer_signed_releases(tmp_path, key, monkeypatch, config_dir):
    monkeypatch.setattr(agent, "installed_version", lambda: "0.2.0")
    m, wheel_bytes, pins = manifest_for(tmp_path, key)
    respx.get(f"{SERVER}/dist/latest.json").mock(return_value=httpx.Response(200, json=m))
    respx.get(f"{SERVER}/dist/{m['wheel']}").mock(return_value=httpx.Response(200, content=wheel_bytes))
    respx.get(f"{SERVER}/dist/{m['constraints']['file']}").mock(return_value=httpx.Response(200, content=pins))
    async with httpx.AsyncClient() as http:
        found = await agent.fetch_update(http, SERVER)
        assert found and found[0]["version"] == "0.9.0" and found[1].read_bytes() == wheel_bytes
        assert found[2].read_bytes() == pins and found[1].parent == config_dir / "releases"  # kept for a rollback

        monkeypatch.setattr(agent, "installed_version", lambda: "0.9.0")
        assert await agent.fetch_update(http, SERVER) is None  # already current

        monkeypatch.setattr(agent, "installed_version", lambda: "0.2.0")
        respx.get(f"{SERVER}/dist/{m['wheel']}").mock(return_value=httpx.Response(200, content=b"tampered"))
        assert await agent.fetch_update(http, SERVER) is None  # download doesn't match the signed hash
        respx.get(f"{SERVER}/dist/{m['wheel']}").mock(return_value=httpx.Response(200, content=wheel_bytes))
        respx.get(f"{SERVER}/dist/{m['constraints']['file']}").mock(return_value=httpx.Response(200, content=b"x==1"))
        assert await agent.fetch_update(http, SERVER) is None  # pins don't match their signed hash
        unpinned = {k: v for k, v in m.items() if k != "constraints"}
        respx.get(f"{SERVER}/dist/latest.json").mock(return_value=httpx.Response(200, json=unpinned))
        assert await agent.fetch_update(http, SERVER) is None  # a release without signed pins

        respx.get(f"{SERVER}/dist/latest.json").mock(return_value=httpx.Response(200, json={**m, "signature": m["signature"][::-1]}))
        assert await agent.fetch_update(http, SERVER) is None  # forged manifest


def ok_run(ran):
    return lambda cmd, **kw: ran.append(cmd) or type("R", (), {"returncode": 0, "stderr": "", "stdout": ""})()


def test_install_update_runs_uv_with_the_local_wheel_and_its_pins(tmp_path, monkeypatch):
    wheel = wheel_file(tmp_path / "dl")
    pins = tmp_path / "dl" / release.constraints_name("0.9.0")
    pins.write_text(PINS)
    ran = []
    monkeypatch.setattr(agent, "find_uv", lambda: "/usr/local/bin/uv")
    monkeypatch.setattr(agent, "in_uv_tool", lambda: True)
    monkeypatch.setattr(agent.os, "name", "posix")
    monkeypatch.setattr(agent.subprocess, "run", ok_run(ran))
    assert agent.install_update(wheel, pins, "0.9.0") is True
    assert ran[0][:4] == ["/usr/local/bin/uv", "tool", "install", "--force"]
    assert ran[0][-1] == f"kw-mcp @ {wheel.resolve().as_uri()}"
    assert ran[0][ran[0].index("--constraints") + 1] == str(pins.resolve())
    assert ran[0][ran[0].index("--exclude-newer") + 1] == "2026-11-01T00:00:00Z" and "--no-build" in ran[0]
    # uv tool install ignores the pins' hashes: every dependency is reinstalled with them checked
    assert ran[1][1:3] == ["pip", "install"] and ran[1][ran[1].index("--python") + 1] == str(agent._tool_python())
    assert {"--require-hashes", "--no-deps", "--reinstall", "--no-build"} <= set(ran[1])
    assert ran[1][-2:] == ["-r", str(pins.resolve())]
    assert ran[2][-3:] == ["--version", "--expect", "0.9.0"]  # the self-test of the new install
    assert agent.load_state()["pending"]["version"] == "0.9.0"
    monkeypatch.setattr(agent, "find_uv", lambda: None)
    assert agent.install_update(wheel, pins, "0.9.0") is False


def test_versions_compare_numerically():
    assert release.version_tuple("0.10.0") > release.version_tuple("0.9.9")
    assert json.dumps(release.version_tuple("0.2.0")) == "[0, 2, 0, 0]"
    assert release.version_tuple("0.6") == release.version_tuple("0.6.0")  # no spurious update


def test_windows_update_command_is_one_verbatim_cmd_line(monkeypatch):
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    home = r"C:\Users\Tom&Jerry (Kim)"
    uv = home + r"\.local\bin\uv.exe"
    line = agent.windows_update_command(
        r"C:\Windows\system32\cmd.exe", pid=4242,
        install=[[uv, "tool", "install", "--force", "kw-mcp @ file:///C:/Users/Tom&Jerry%20(Kim)/x/kw_mcp-0.9.1-py3-none-any.whl"],
                 [uv, "pip", "install", "--require-hashes", "-r", home + r"\x\kw_mcp-0.9.1-constraints.txt"]],
        check=[home + r"\uv\tools\kw-mcp\Scripts\python.exe", "-I", "-m", "kw_mcp", "--version", "--expect", "0.9.1"],
        rollback=[[uv, "tool", "install", "--force", "kw-mcp @ file:///C:/x/kw_mcp-0.9.0-py3-none-any.whl"]],
        log_file=Path(home + r"\AppData\Local\kw-campus\update.log"),
        restart=[home + r"\uv\tools\kw-mcp\Scripts\pythonw.exe", "-m", "kw_mcp", "agent", "--replace"],
        marker=Path(home + r"\.config\kw-campus\update-self-test-failed"), version="0.9.1")
    assert line.startswith(r'"C:\Windows\system32\cmd.exe" /s /c "')
    assert "Wait-Process -Id 4242" in line  # waits for the agent itself, not a fixed delay
    assert '\\"' not in line  # no backslash-escaped quotes: cmd.exe would choke on them
    # Every token quoted, so cmd.exe can't split "Tom&Jerry" at the & or trip on the parentheses.
    assert f'"{uv}" "tool" "install" "--force"' in line
    assert r'>> "C:\Users\Tom&Jerry (Kim)\AppData\Local\kw-campus\update.log" 2>&1' in line
    assert '"--expect" "0.9.1"' in line and " && " in line and " || " in line  # self-test, rollback on failure
    assert line.endswith(r'& "C:\Users\Tom&Jerry (Kim)\uv\tools\kw-mcp\Scripts\pythonw.exe" "-m" "kw_mcp" "agent" "--replace""')
    steps = line.split(" /s /c \"", 1)[1][:-1]  # what cmd.exe runs once /s strips the outer quotes
    outside = steps.split('"')[::2]  # text outside quotes, where & ( ) are cmd syntax
    assert not any("Tom&Jerry" in part or "(Kim)" in part for part in outside)


def test_install_update_accepts_a_relative_path(tmp_path, monkeypatch):
    wheel_file(tmp_path / "w")
    (tmp_path / "w" / release.constraints_name("0.9.0")).write_text(PINS)
    monkeypatch.chdir(tmp_path)
    ran = []
    monkeypatch.setattr(agent, "find_uv", lambda: "uv")
    monkeypatch.setattr(agent, "in_uv_tool", lambda: True)
    monkeypatch.setattr(agent.os, "name", "posix")
    monkeypatch.setattr(agent.subprocess, "run", ok_run(ran))
    assert agent.install_update(Path("w/kw_mcp-0.9.0-py3-none-any.whl"), Path("w/kw_mcp-0.9.0-constraints.txt"), "0.9.0")
    assert ran[0][-1].startswith("kw-mcp @ file:///")
