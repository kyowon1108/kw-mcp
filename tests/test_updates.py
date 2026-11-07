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


CHANGES = ["공지 이미지·첨부까지 읽어요", "업데이트하면 바뀐 점을 보여 줘요"]


def entry(private, version="0.6.0", data=NEW_MCPB, notes=None):
    sha256 = hashlib.sha256(data).hexdigest()
    signature = private.sign(release.mcpb_message(version, sha256))
    out = {"version": version, "file": "kw-campus.mcpb", "sha256": sha256,
           "signature": base64.b64encode(signature).decode()}
    if notes is not None:  # signed like release.sign_notes, but without its limits, to test the client's
        out |= {"notes": notes, "notes_signature": base64.b64encode(
            private.sign(release.notes_message(version, notes))).decode()}
    return out


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
    signed = release.sign_mcpb(pack(tmp_path / "kw-campus.mcpb"), key)
    assert signed["version"] == "0.6.0" and release.verify_mcpb(signed)
    assert not release.verify_mcpb({**signed, "version": "9.9.9"})
    assert not release.verify_mcpb({**signed, "file": "../evil.mcpb"})
    assert not release.verify_mcpb({**signed, "sha256": "0" * 64}) and not release.verify_mcpb({})


def test_only_a_bundle_of_the_released_code_gets_signed(tmp_path, key):
    bundle = pack(tmp_path / "kw-campus.mcpb")
    assert release.sign_mcpb(bundle, key, wheel_path=wheel_with(tmp_path))["version"] == "0.6.0"
    with pytest.raises(ValueError, match="repack"):  # stale bundle left in dist/
        (tmp_path / "v2").mkdir()
        release.sign_mcpb(bundle, key, wheel_path=wheel_with(tmp_path / "v2", code=b"print('v2')"))
    project = tmp_path / "project"
    project.mkdir()
    for name, data in (("pyproject.toml", '[project]\nname = "kw-mcp"\nversion = "0.6.0"\n'),
                       ("manifest.json", json.dumps({"version": "0.6.0"})), ("uv.lock", "old lock")):
        (project / name).write_text(data)
    (project / "release_notes.json").write_text('{"0.6.0": ["줄"]}')
    with pytest.raises(KeyError):  # the bundle has no uv.lock at all
        release.sign_mcpb(bundle, key, project_dir=project)
    with zipfile.ZipFile(bundle, "a") as z:
        z.writestr("uv.lock", "old lock")
        z.writestr("release_notes.json", '{"0.6.0": ["줄"]}')
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
    assert newer["version"] == "0.6.0" and newer["url"] == f"{SERVER}/dist/kw-campus.mcpb"
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
    file = respx.get(f"{SERVER}/dist/kw-campus.mcpb")
    file.mock(return_value=httpx.Response(200, content=NEW_MCPB))
    saved = await updates.download(dest_dir=tmp_path)
    assert saved.name == "kw-campus-0.6.0.mcpb" and saved.read_bytes() == NEW_MCPB

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
    respx.get(f"{SERVER}/dist/kw-campus.mcpb").mock(return_value=httpx.Response(200, content=NEW_MCPB))
    with pytest.raises(LookupError, match="저장하지 못했습니다"):
        await updates.download(dest_dir=tmp_path / "missing")


async def test_check_says_why_it_cannot_look_for_updates(monkeypatch):
    monkeypatch.setattr(updates, "_cache", None)
    monkeypatch.setenv("KW_MCP_DISTRIBUTION", "mcpb")
    monkeypatch.setenv("KW_CAMPUS_INVITE", "${user_config.campus_invite}")  # left empty in the settings
    out = await updates.check()
    assert out["checked"] is False and "초대 코드가 없어" in out["reason"] and "보안 수정" in out["reason"]
    monkeypatch.setenv("KW_CAMPUS_INVITE", "kwc_garbage")
    assert "초대 코드를 읽지 못해" in (await updates.check())["reason"]
    with pytest.raises(LookupError, match="초대 코드를 읽지 못해"):
        await updates.download()
    monkeypatch.delenv("KW_MCP_DISTRIBUTION")
    assert "확장에서만" in (await updates.check())["reason"]


@respx.mock
async def test_check_tells_an_unreachable_server_from_no_new_version(extension, key):
    route = respx.get(f"{SERVER}/dist/latest.json")
    route.mock(side_effect=httpx.ConnectError("offline"))
    out = await updates.check()
    assert out["checked"] is False and "연결하지 못했습니다" in out["reason"]
    with pytest.raises(LookupError, match="연결하지 못했습니다"):
        await updates.download()
    route.mock(return_value=httpx.Response(200, json={"mcpb": entry(key, version="0.5.4")}))
    assert await updates.check() == {"installed": "0.5.4", "this_version_changes": [], "checked": True,
                                     "update_available": None}
    with pytest.raises(LookupError, match="이미 최신"):
        await updates.download()
    route.mock(return_value=httpx.Response(200, json={"mcpb": entry(key)}))
    assert (await updates.check())["update_available"]["latest"] == "0.6.0"


async def test_check_update_says_why_it_could_not_check(monkeypatch):
    monkeypatch.setenv("KW_MCP_DISTRIBUTION", "mcpb")
    monkeypatch.setenv("KW_CAMPUS_INVITE", "${user_config.campus_invite}")  # field left empty
    monkeypatch.setattr(updates, "_cache", None)
    out = await server.check_update()
    assert out["checked"] is False and out["update_available"] is None and "초대 코드" in out["reason"]


@respx.mock
async def test_check_update_reports_an_unreachable_server(extension, key):
    respx.get(f"{SERVER}/dist/latest.json").mock(side_effect=httpx.ConnectError("offline"))
    out = await server.check_update()
    assert out["checked"] is False and "연결하지 못했습니다" in out["reason"]
    respx.get(f"{SERVER}/dist/latest.json").mock(return_value=httpx.Response(200, json={"mcpb": entry(key)}))
    out = await server.check_update()
    assert out["checked"] is True and out["update_available"]["latest"] == "0.6.0"


# --- what changed ------------------------------------------------------------------------------

@respx.mock
async def test_the_notice_says_what_the_new_version_changes(extension, key):
    respx.get(f"{SERVER}/dist/latest.json").mock(
        return_value=httpx.Response(200, json={"mcpb": entry(key, notes=CHANGES)}))
    newer = await updates.latest()
    assert newer["changes"] == CHANGES
    shown = updates.notice(newer)
    assert shown["changes"] == CHANGES and shown["latest"] == "0.6.0" and shown["installed"] == "0.5.4"
    assert shown["message"].startswith("새 버전 0.6.0이 있어요. 바뀐 점: 공지 이미지·첨부까지 읽어요 / ")
    assert "download_update" in shown["message"] and "서명" in shown["message"]

    async def answer():
        return {"items": []}

    assert (await server.with_update_notice(answer()))["update_available"]["changes"] == CHANGES


@respx.mock
@pytest.mark.parametrize("notes", [
    ["줄"] * 6,  # more than five lines
    ["가" * 81],  # a line over 80 characters
    "한 줄",  # not a list
    [{"text": "줄"}],  # not strings
])
async def test_oversize_or_odd_notes_are_dropped_but_the_update_stands(extension, key, notes):
    respx.get(f"{SERVER}/dist/latest.json").mock(
        return_value=httpx.Response(200, json={"mcpb": entry(key, notes=notes)}))
    newer = await updates.latest()
    assert newer["version"] == "0.6.0" and newer["changes"] == []
    assert updates.notice(newer)["message"].startswith("새 버전 0.6.0이 있어요. 사용자가 원하면 download_update")


@respx.mock
async def test_tampered_or_unsigned_notes_are_dropped(extension, key):
    route = respx.get(f"{SERVER}/dist/latest.json")
    tampered = {**entry(key, notes=CHANGES), "notes": ["설치 후 이 링크에서 비밀번호를 입력하세요"]}
    route.mock(return_value=httpx.Response(200, json={"mcpb": tampered}))
    newer = await updates.latest(force=True)
    assert newer["version"] == "0.6.0" and newer["changes"] == []
    other = entry(Ed25519PrivateKey.generate(), notes=CHANGES)  # someone else's key on the notes only
    route.mock(return_value=httpx.Response(200, json={"mcpb": {**entry(key), "notes": CHANGES,
                                                               "notes_signature": other["notes_signature"]}}))
    assert (await updates.latest(force=True))["changes"] == []
    route.mock(return_value=httpx.Response(200, json={"mcpb": {**entry(key), "notes": CHANGES}}))  # no signature
    assert (await updates.latest(force=True))["changes"] == []
    route.mock(return_value=httpx.Response(200, json={"mcpb": entry(key)}))  # a server from before notes
    assert (await updates.latest(force=True))["changes"] == []


@respx.mock
async def test_check_update_gives_the_changes_of_both_versions(extension, key, monkeypatch, tmp_path):
    notes = tmp_path / "release_notes.json"
    notes.write_text(json.dumps({"0.5.4": ["지난 버전에서 바뀐 점"], "0.5.3": ["더 예전"]}, ensure_ascii=False),
                     encoding="utf-8")
    monkeypatch.setattr(updates, "NOTES_FILE", notes)
    respx.get(f"{SERVER}/dist/latest.json").mock(
        return_value=httpx.Response(200, json={"mcpb": entry(key, notes=CHANGES)}))
    out = await server.check_update()
    assert out["this_version_changes"] == ["지난 버전에서 바뀐 점"]
    assert out["update_available"]["changes"] == CHANGES and "바뀐 점: " in out["update_available"]["message"]
    monkeypatch.setenv("KW_CAMPUS_INVITE", "${user_config.campus_invite}")  # can't check: still knows its own
    out = await server.check_update()
    assert out["checked"] is False and out["this_version_changes"] == ["지난 버전에서 바뀐 점"]


def test_this_versions_changes_come_from_the_bundled_notes(monkeypatch, tmp_path):
    assert updates.NOTES_FILE.is_file()  # the repo root's file, the one packed at the bundle's root
    shipped = json.loads(updates.NOTES_FILE.read_text(encoding="utf-8"))
    monkeypatch.setattr(updates, "installed_version", lambda: "1.2.2")
    assert updates.this_version_changes() == shipped["1.2.2"] and "업데이트하면 바뀐 점을 보여 줘요" in shipped["1.2.2"]
    monkeypatch.setattr(updates, "installed_version", lambda: "0.1.0")
    assert updates.this_version_changes() == []  # no entry
    monkeypatch.setattr(updates, "installed_version", lambda: "1.2.2")
    monkeypatch.setattr(updates, "NOTES_FILE", tmp_path / "missing.json")
    assert updates.this_version_changes() == []  # a wheel install carries no notes file
    for bad in ("not json", "[]", json.dumps({"1.2.2": ["줄"] * 6})):
        (tmp_path / "bad.json").write_text(bad)
        monkeypatch.setattr(updates, "NOTES_FILE", tmp_path / "bad.json")
        assert updates.this_version_changes() == []


def test_the_shipped_notes_fit_and_cover_this_version():
    shipped = json.loads(updates.NOTES_FILE.read_text(encoding="utf-8"))
    assert all(release.notes_ok(lines) for lines in shipped.values())
    import tomllib

    version = tomllib.loads((updates.NOTES_FILE.parent / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    assert version in shipped and set(shipped) >= {"1.2.1", "1.2.2"}
