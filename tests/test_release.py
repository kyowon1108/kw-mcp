import base64
import hashlib
import json
from pathlib import Path

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kw_mcp import agent, release

SERVER = "https://bridge.example"
WHEEL_BYTES = b"PK fake wheel 0.9.0"


@pytest.fixture
def key(monkeypatch):
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setattr(release, "PUBLIC_KEY", base64.b64encode(public).decode())
    return private


def manifest_for(tmp_path, private, version="0.9.0", data=WHEEL_BYTES):
    wheel = tmp_path / f"kw_mcp-{version}-py3-none-any.whl"
    wheel.write_bytes(data)
    return release.sign(wheel, private)


def test_signed_manifest_verifies_and_tampering_fails(tmp_path, key):
    m = manifest_for(tmp_path, key)
    assert m["sha256"] == hashlib.sha256(WHEEL_BYTES).hexdigest() and release.verify(m)
    assert not release.verify({**m, "sha256": "0" * 64})
    assert not release.verify({**m, "version": "9.9.9"})  # wheel name and version disagree
    assert not release.verify({**m, "wheel": "evil-9.9.9-py3-none-any.whl"})
    other = Ed25519PrivateKey.generate()
    assert not release.verify(manifest_for(tmp_path, other))
    assert not release.verify({})


def test_shipped_public_key_is_set():
    assert len(base64.b64decode(release.PUBLIC_KEY)) == 32


@respx.mock
async def test_fetch_update_takes_only_newer_signed_releases(tmp_path, key, monkeypatch):
    monkeypatch.setattr(agent, "installed_version", lambda: "0.2.0")
    m = manifest_for(tmp_path, key)
    respx.get(f"{SERVER}/dist/latest.json").mock(return_value=httpx.Response(200, json=m))
    respx.get(f"{SERVER}/dist/{m['wheel']}").mock(return_value=httpx.Response(200, content=WHEEL_BYTES))
    async with httpx.AsyncClient() as http:
        found = await agent.fetch_update(http, SERVER)
        assert found and found[0]["version"] == "0.9.0" and found[1].read_bytes() == WHEEL_BYTES

        monkeypatch.setattr(agent, "installed_version", lambda: "0.9.0")
        assert await agent.fetch_update(http, SERVER) is None  # already current

        monkeypatch.setattr(agent, "installed_version", lambda: "0.2.0")
        respx.get(f"{SERVER}/dist/{m['wheel']}").mock(return_value=httpx.Response(200, content=b"tampered"))
        assert await agent.fetch_update(http, SERVER) is None  # download doesn't match the signed hash

        respx.get(f"{SERVER}/dist/latest.json").mock(return_value=httpx.Response(200, json={**m, "signature": m["signature"][::-1]}))
        assert await agent.fetch_update(http, SERVER) is None  # forged manifest


def test_install_update_runs_uv_with_the_local_wheel(tmp_path, monkeypatch):
    wheel = tmp_path / "dl" / "kw_mcp-0.9.0-py3-none-any.whl"
    wheel.parent.mkdir()
    wheel.write_bytes(WHEEL_BYTES)
    ran = []
    monkeypatch.setattr(agent, "find_uv", lambda: "/usr/local/bin/uv")
    monkeypatch.setattr(agent.subprocess, "run",
                        lambda cmd, **kw: ran.append(cmd) or type("R", (), {"returncode": 0, "stderr": ""})())
    assert agent.install_update(wheel) is True
    assert ran[0][:4] == ["/usr/local/bin/uv", "tool", "install", "--force"]
    assert ran[0][-1] == f"kw-mcp @ {wheel.resolve().as_uri()}"
    assert not wheel.parent.exists()  # temp download removed
    monkeypatch.setattr(agent, "find_uv", lambda: None)
    assert agent.install_update(wheel) is False


def test_versions_compare_numerically():
    assert release.version_tuple("0.10.0") > release.version_tuple("0.9.9")
    assert json.dumps(release.version_tuple("0.2.0")) == "[0, 2, 0]"


def test_windows_update_command_is_one_verbatim_cmd_line():
    line = agent.windows_update_command(
        r"C:\Windows\system32\cmd.exe", r"C:\Users\Kim Lee\.local\bin\uv.exe",
        "kw-mcp @ file:///C:/Users/Kim%20Lee/AppData/Local/Temp/x/kw_mcp-0.9.0-py3-none-any.whl",
        Path(r"C:\Users\Kim Lee\AppData\Local\kw-campus\update.log"),
        [r"C:\Users\Kim Lee\AppData\Roaming\uv\tools\kw-mcp\Scripts\pythonw.exe", "-m", "kw_mcp", "agent", "--replace"])
    assert line.startswith(r'"C:\Windows\system32\cmd.exe" /s /c "ping -n 8 127.0.0.1 >nul & ')
    assert '\\"' not in line  # no backslash-escaped quotes: cmd.exe would choke on them
    assert r'"C:\Users\Kim Lee\.local\bin\uv.exe" tool install --force' in line
    assert r'>> "C:\Users\Kim Lee\AppData\Local\kw-campus\update.log" 2>&1' in line
    assert line.endswith(r'& "C:\Users\Kim Lee\AppData\Roaming\uv\tools\kw-mcp\Scripts\pythonw.exe" -m kw_mcp agent --replace"')


def test_install_update_accepts_a_relative_path(tmp_path, monkeypatch):
    (tmp_path / "w").mkdir()
    (tmp_path / "w" / "kw_mcp-0.9.0-py3-none-any.whl").write_bytes(b"x")
    monkeypatch.chdir(tmp_path)
    ran = []
    monkeypatch.setattr(agent, "find_uv", lambda: "uv")
    monkeypatch.setattr(agent.subprocess, "run",
                        lambda cmd, **kw: ran.append(cmd) or type("R", (), {"returncode": 0, "stderr": ""})())
    assert agent.install_update(Path("w/kw_mcp-0.9.0-py3-none-any.whl")) is True
    assert ran[0][-1].startswith("kw-mcp @ file:///")
