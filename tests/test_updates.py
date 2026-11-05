"""The Claude Desktop extension finds, verifies and saves its own new versions."""

import base64
import hashlib
import json
import zipfile

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kw_mcp import agent, release, server, updates

SERVER = "https://bridge.example"
NEW_MCPB = b"new extension bytes"


@pytest.fixture
def key(monkeypatch):
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setattr(release, "PUBLIC_KEY", base64.b64encode(public).decode())
    return private


@pytest.fixture
def extension(monkeypatch):
    monkeypatch.setenv("KW_MCP_DISTRIBUTION", "mcpb")
    monkeypatch.setenv("KW_CAMPUS_INVITE", agent.make_invite(SERVER, "tok"))
    monkeypatch.setattr(updates, "installed_version", lambda: "0.5.4")
    monkeypatch.setattr(updates, "_cache", None)


def entry(private, version="0.6.0", data=NEW_MCPB):
    sha256 = hashlib.sha256(data).hexdigest()
    signature = private.sign(release.mcpb_message(version, sha256))
    return {"version": version, "file": "kw-klas.mcpb", "sha256": sha256,
            "signature": base64.b64encode(signature).decode()}


def pack(path, version="0.6.0", shown=None, code=b"print('v1')"):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("pyproject.toml", f'[project]\nname = "kw-mcp"\nversion = "{version}"\n')
        z.writestr("manifest.json", json.dumps({"version": shown or version}))
        z.writestr("src/kw_mcp/server.py", code)
    return path


def wheel_with(tmp_path, version="0.6.0", code=b"print('v1')"):
    path = tmp_path / f"kw_mcp-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("kw_mcp/server.py", code)
    return path


def test_sign_mcpb_reads_the_packed_version(tmp_path, key):
    signed = release.sign_mcpb(pack(tmp_path / "kw-klas.mcpb"), key)
    assert signed["version"] == "0.6.0" and release.verify_mcpb(signed)
    assert not release.verify_mcpb({**signed, "version": "9.9.9"})
    assert not release.verify_mcpb({**signed, "file": "../evil.mcpb"})
    assert not release.verify_mcpb({**signed, "sha256": "0" * 64}) and not release.verify_mcpb({})


def test_only_a_bundle_of_the_released_code_gets_signed(tmp_path, key):
    bundle = pack(tmp_path / "kw-klas.mcpb")
    assert release.sign_mcpb(bundle, key, wheel_path=wheel_with(tmp_path))["version"] == "0.6.0"
    with pytest.raises(ValueError, match="repack"):  # stale bundle left in dist/
        (tmp_path / "v2").mkdir()
        release.sign_mcpb(bundle, key, wheel_path=wheel_with(tmp_path / "v2", code=b"print('v2')"))
    project = tmp_path / "project"
    project.mkdir()
    for name, data in (("pyproject.toml", '[project]\nname = "kw-mcp"\nversion = "0.6.0"\n'),
                       ("manifest.json", json.dumps({"version": "0.6.0"})), ("uv.lock", "old lock")):
        (project / name).write_text(data)
    with pytest.raises(KeyError):  # the bundle has no uv.lock at all
        release.sign_mcpb(bundle, key, project_dir=project)
    with zipfile.ZipFile(bundle, "a") as z:
        z.writestr("uv.lock", "old lock")
    assert release.sign_mcpb(bundle, key, project_dir=project)["version"] == "0.6.0"
    (project / "uv.lock").write_text("bumped lock")
    with pytest.raises(ValueError, match="older pyproject.toml, uv.lock"):
        release.sign_mcpb(bundle, key, project_dir=project)
    with pytest.raises(ValueError, match="manifest.json version"):
        release.sign_mcpb(pack(tmp_path / "a.mcpb", shown="0.7.9"), key)
    with pytest.raises(ValueError, match="plain numbers"):
        release.sign_mcpb(pack(tmp_path / "b.mcpb", version="0.6.0rc1"), key)


@respx.mock
async def test_newer_signed_version_is_offered_once_per_check_window(extension, key):
    route = respx.get(f"{SERVER}/dist/latest.json").mock(
        return_value=httpx.Response(200, json={"version": "0.6.0", "mcpb": entry(key)}))
    newer = await updates.latest()
    assert newer["version"] == "0.6.0" and newer["url"] == f"{SERVER}/dist/kw-klas.mcpb"
    assert await updates.latest() == newer and route.call_count == 1  # cached
    assert "download_update" in updates.notice(newer)["message"]


@respx.mock
@pytest.mark.parametrize("body", [
    {"mcpb": "not a dict"},
    {},  # older server without the extension entry
    ["unexpected"],
])
async def test_missing_or_odd_entries_offer_nothing(extension, key, body):
    respx.get(f"{SERVER}/dist/latest.json").mock(return_value=httpx.Response(200, json=body))
    assert await updates.latest() is None


@respx.mock
async def test_unsigned_older_or_unreachable_offers_nothing(extension, key):
    route = respx.get(f"{SERVER}/dist/latest.json")
    route.mock(return_value=httpx.Response(200, json={"mcpb": entry(Ed25519PrivateKey.generate())}))
    assert await updates.latest(force=True) is None  # someone else's key
    route.mock(return_value=httpx.Response(200, json={"mcpb": entry(key, version="0.5.4")}))
    assert await updates.latest(force=True) is None  # same version
    route.mock(side_effect=httpx.ConnectError("offline"))
    assert await updates.latest(force=True) is None


async def test_outside_the_extension_nothing_is_checked(monkeypatch):
    monkeypatch.delenv("KW_MCP_DISTRIBUTION", raising=False)
    monkeypatch.setattr(updates, "_cache", None)
    assert await updates.latest() is None
    monkeypatch.setenv("KW_MCP_DISTRIBUTION", "mcpb")
    monkeypatch.setenv("KW_CAMPUS_INVITE", "${user_config.campus_invite}")  # no invite given
    assert await updates.latest() is None


@respx.mock
async def test_download_saves_only_the_signed_file(extension, key, tmp_path):
    respx.get(f"{SERVER}/dist/latest.json").mock(return_value=httpx.Response(200, json={"mcpb": entry(key)}))
    file = respx.get(f"{SERVER}/dist/kw-klas.mcpb")
    file.mock(return_value=httpx.Response(200, content=NEW_MCPB))
    saved = await updates.download(dest_dir=tmp_path)
    assert saved.name == "kw-klas-0.6.0.mcpb" and saved.read_bytes() == NEW_MCPB

    file.mock(return_value=httpx.Response(200, content=b"tampered"))
    with pytest.raises(LookupError, match="해시"):
        await updates.download(dest_dir=tmp_path / "x")
    assert not (tmp_path / "x").exists()


@respx.mock
async def test_combined_tools_mention_the_update(extension, key, monkeypatch):
    respx.get(f"{SERVER}/dist/latest.json").mock(return_value=httpx.Response(200, json={"mcpb": entry(key)}))

    async def answer():
        return {"items": []}

    out = await server.with_update_notice(answer())
    assert out["update_available"]["latest"] == "0.6.0" and json.dumps(out, ensure_ascii=False)


@respx.mock
async def test_a_hostile_manifest_never_breaks_or_slows_the_tools(extension, key, monkeypatch):
    respx.get(f"{SERVER}/dist/latest.json").mock(return_value=httpx.Response(200, content=b"[" * 200_000))
    assert await updates.latest() is None  # RecursionError inside json, swallowed
    assert updates._cache[1] == updates.RETRY_AFTER_FAILURE_S

    monkeypatch.setattr(updates, "_cache", None)
    respx.get(f"{SERVER}/dist/latest.json").mock(return_value=httpx.Response(200, content=b" " * 100_000))
    assert await updates.latest() is None  # over the size cap

    monkeypatch.setattr(updates, "_cache", None)
    respx.get(f"{SERVER}/dist/latest.json").mock(return_value=httpx.Response(503))
    assert await updates.latest() is None and updates._cache[1] == updates.RETRY_AFTER_FAILURE_S


async def test_answer_waits_at_most_briefly_for_a_slow_check(monkeypatch):
    import asyncio
    import time

    async def slow(*args, **kwargs):
        await asyncio.sleep(5)

    monkeypatch.setattr(updates, "latest", slow)
    monkeypatch.setattr(server, "UPDATE_WAIT_S", 0.05)

    async def answer():
        return {"items": []}

    started = time.monotonic()
    assert await server.with_update_notice(answer()) == {"items": []}
    assert time.monotonic() - started < 1

    async def failing():
        raise LookupError("KLAS down")

    with pytest.raises(LookupError, match="KLAS down"):  # the tool's own error is what surfaces
        await server.with_update_notice(failing())


@respx.mock
async def test_download_reports_an_unwritable_folder(extension, key, tmp_path):
    respx.get(f"{SERVER}/dist/latest.json").mock(return_value=httpx.Response(200, json={"mcpb": entry(key)}))
    respx.get(f"{SERVER}/dist/kw-klas.mcpb").mock(return_value=httpx.Response(200, content=NEW_MCPB))
    with pytest.raises(LookupError, match="저장하지 못했습니다"):
        await updates.download(dest_dir=tmp_path / "missing")
