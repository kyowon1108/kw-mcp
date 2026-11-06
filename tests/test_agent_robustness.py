"""PC agent: clock skew, unlink, connections, answers under deadline, reconnects, notifications, uv, lock."""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime
from email.utils import formatdate

import httpx
import pytest
import respx
import websockets
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from websockets.datastructures import Headers
from websockets.http11 import Response

from kw_mcp import agent

SERVER = "https://bridge.example"
LINK = agent.Link(server=SERVER, ws_url="wss://ws.example/prod", uid="u_" + "a" * 22)


@pytest.fixture(autouse=True)
def config_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(agent, "LINK_FILE", tmp_path / "config" / "agent.json")
    return tmp_path / "config"


@pytest.fixture
def linked(monkeypatch, memory_keychain):
    """A linked PC: agent.json and a device key in the (in-memory) keychain."""
    key = agent.DeviceKey.generate()
    key.save()
    agent.save_link(LINK)
    monkeypatch.setattr(agent, "uninstall_autostart", lambda: None)
    return key


def verify(key: agent.DeviceKey, message: str, sig: str) -> None:
    jwk = key.public_jwk()
    public = ec.EllipticCurvePublicNumbers(int.from_bytes(agent.b64u_decode(jwk["x"]), "big"),
                                           int.from_bytes(agent.b64u_decode(jwk["y"]), "big"),
                                           ec.SECP256R1()).public_key()
    raw = agent.b64u_decode(sig)
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    public.verify(der, message.encode(), ec.ECDSA(hashes.SHA256()))


def date(offset_s: float = 0) -> str:
    return formatdate(time.time() + offset_s, usegmt=True)


# --- the PC clock -------------------------------------------------------------------

@respx.mock
def test_a_stale_timestamp_is_clock_skew_and_never_a_re_registration(linked):
    respx.post(f"{SERVER}/device/grants").mock(return_value=httpx.Response(
        401, json={"error": "stale_timestamp", "server_time": int(time.time()) - 9 * 3600}))
    with pytest.raises(agent.ClockSkew) as e:
        agent.linked_to(SERVER)
    assert "약 540분 빠릅니다" in str(e.value) and "시간" in str(e.value)
    respx.post(f"{SERVER}/device/pair").mock(return_value=httpx.Response(
        401, json={"error": "stale_timestamp", "server_time": int(time.time()) + 600}))
    with pytest.raises(agent.ClockSkew, match="느립니다"):
        agent.pair_code()


@respx.mock
def test_only_an_unknown_device_means_link_again(linked):
    route = respx.post(f"{SERVER}/device/grants")
    route.mock(return_value=httpx.Response(403, json={"error": "unknown_device"}))
    assert agent.linked_to(SERVER) is False
    route.mock(return_value=httpx.Response(403, json={"error": "bad_signature"}))
    with pytest.raises(agent.DeviceRefused, match="--relink"):
        agent.linked_to(SERVER)
    respx.post(f"{SERVER}/device/pair").mock(return_value=httpx.Response(403, json={"error": "invite_revoked"}))
    with pytest.raises(agent.DeviceRefused, match="철회"):
        agent.pair_code()


@respx.mock
def test_an_older_bridge_403_is_checked_against_its_date_header(linked):
    respx.post(f"{SERVER}/device/grants").mock(return_value=httpx.Response(404))  # no /device/grants yet
    pair = respx.post(f"{SERVER}/device/pair")
    pair.mock(return_value=httpx.Response(403, json={"error": "invalid_signature"}, headers={"Date": date(-3600)}))
    with pytest.raises(agent.ClockSkew):
        agent.linked_to(SERVER)
    pair.mock(return_value=httpx.Response(403, json={"error": "invalid_signature"}, headers={"Date": date()}))
    assert agent.linked_to(SERVER) is False


@respx.mock
def test_a_replayed_signature_is_retried_once_with_a_fresh_one(linked, monkeypatch):
    monkeypatch.setattr(agent.time, "sleep", lambda s: None)
    route = respx.post(f"{SERVER}/device/grants")
    route.side_effect = [httpx.Response(409, json={"error": "replayed"}), httpx.Response(200, json={"grants": []})]
    assert agent.grants() == []
    sigs = [json.loads(c.request.content)["sig"] for c in route.calls]
    assert len(sigs) == 2 and sigs[0] != sigs[1]


@respx.mock
def test_server_clock_check_uses_the_date_header():
    route = respx.get(f"{SERVER}/healthz")
    route.mock(return_value=httpx.Response(200, text="ok", headers={"Date": date(+900)}))
    with pytest.raises(agent.ClockSkew, match="느립니다"):
        agent.check_server_clock(SERVER)
    route.mock(return_value=httpx.Response(200, text="ok", headers={"Date": date(+30)}))
    agent.check_server_clock(SERVER)  # a few seconds off is fine


# --- unlink -------------------------------------------------------------------------

def still_linked(config_dir) -> bool:
    return (config_dir / "agent.json").exists() and agent.keyring.get_password("kw-mcp", agent.KEYRING_DEVICE_KEY) is not None


@respx.mock
@pytest.mark.parametrize("answer", [
    httpx.Response(503),
    httpx.Response(200, json={"ok": False}),
    httpx.Response(403, json={"error": "bad_signature"}),
])
def test_unlink_keeps_the_key_unless_the_bridge_confirms(linked, config_dir, answer):
    respx.post(f"{SERVER}/device/unlink").mock(return_value=answer)
    with pytest.raises(agent.UnlinkFailed):
        agent.unlink()
    assert still_linked(config_dir)


@respx.mock
def test_unlink_keeps_the_key_when_offline_or_the_clock_is_off(linked, config_dir):
    route = respx.post(f"{SERVER}/device/unlink")
    route.mock(side_effect=httpx.ConnectError("offline"))
    with pytest.raises(agent.UnlinkFailed, match="연결하지 못해"):
        agent.unlink()
    route.mock(return_value=httpx.Response(401, json={"error": "stale_timestamp", "server_time": int(time.time()) + 4000}))
    with pytest.raises(agent.ClockSkew):
        agent.unlink()
    assert still_linked(config_dir)


@respx.mock
@pytest.mark.parametrize("answer", [httpx.Response(200, json={"ok": True}), httpx.Response(403, json={"error": "unknown_device"})])
def test_unlink_removes_local_state_once_the_bridge_has_no_record(linked, config_dir, answer):
    respx.post(f"{SERVER}/device/unlink").mock(return_value=answer)
    agent.unlink()
    assert not still_linked(config_dir) and not (config_dir / "agent.json").exists()


def test_unlink_force_skips_the_bridge(linked, config_dir):
    with respx.mock(assert_all_called=False) as mock:  # any request would fail the test
        agent.unlink(force=True)
        assert not mock.calls
    assert not still_linked(config_dir)


# --- connections ------------------------------------------------------------------------

@respx.mock
def test_grants_and_revoke_are_signed_device_requests(linked):
    grants = respx.post(f"{SERVER}/device/grants").mock(return_value=httpx.Response(200, json={"grants": [
        {"id": "g_abc", "client": "Claude" + chr(0x202E) + chr(7), "redirect_host": "claude.ai", "created": "2026-11-06T10:00:00+09:00",
         "last_used": None, "expires": "2027-05-05T10:00:00+09:00"}]}))
    rows = agent.grants()
    assert rows[0]["id"] == "g_abc" and rows[0]["client"] == "Claude"  # no control or bidi characters
    body = json.loads(grants.calls[0].request.content)
    verify(linked, f"kw-grants:{LINK.uid}:{body['ts']}", body["sig"])

    revoke = respx.post(f"{SERVER}/device/revoke").mock(return_value=httpx.Response(200, json={"ok": True}))
    agent.revoke("g_abc")
    body = json.loads(revoke.calls[0].request.content)
    assert body["grant_id"] == "g_abc"
    verify(linked, f"kw-revoke:g_abc:{LINK.uid}:{body['ts']}", body["sig"])

    revoke.mock(return_value=httpx.Response(404, json={"error": "unknown_grant"}))
    with pytest.raises(LookupError, match="g_abc"):
        agent.revoke("g_abc")
    with pytest.raises(ValueError):
        agent.revoke("g_abc:u_x")  # ':' would change what the signature covers
    assert revoke.call_count == 2


# --- answering ----------------------------------------------------------------------------

class Holder:
    def __init__(self, service):
        self._service = service

    async def service(self):
        return self._service


def request(key: bytes, **extra) -> dict:
    return {"type": "snapshot", "request_id": "r1", "key": agent.b64u(key), "result_url": f"{SERVER}/device/result", **extra}


def opened(route, key: bytes) -> dict:
    body = json.loads(route.calls[-1].request.content)
    return json.loads(AESGCM(key).decrypt(agent.b64u_decode(body["iv"]), agent.b64u_decode(body["ct"]), b"r1"))


@respx.mock
async def test_a_slow_klas_gets_an_answer_before_the_bridge_gives_up(monkeypatch):
    monkeypatch.setattr(agent, "ANSWER_DEADLINE_S", 0.05)

    class Slow:
        async def snapshot(self):
            await asyncio.sleep(5)

    route = respx.post(f"{SERVER}/device/result").mock(return_value=httpx.Response(202))
    key = AESGCM.generate_key(bit_length=256)
    async with httpx.AsyncClient() as http:
        await agent.answer(Holder(Slow()), LINK, request(key), http)
    assert opened(route, key)["error"] == "klas_slow"


@respx.mock
async def test_the_result_upload_is_retried_with_backoff_but_not_after_409(monkeypatch):
    sleeps = []

    async def no_wait(s):
        sleeps.append(s)

    monkeypatch.setattr(agent.asyncio, "sleep", no_wait)

    class Fine:
        async def snapshot(self):
            return {"when": datetime(2026, 11, 6), "text": "\ud83d broken surrogate"}  # neither is plain JSON

    route = respx.post(f"{SERVER}/device/result")
    route.side_effect = [httpx.ConnectError("blip"), httpx.Response(503), httpx.Response(202)]
    key = AESGCM.generate_key(bit_length=256)
    async with httpx.AsyncClient() as http:
        await agent.answer(Holder(Fine()), LINK, request(key), http)
        assert route.call_count == 3 and len(sleeps) == 2 and 0.25 <= sleeps[0] <= 0.75 and sleeps[1] <= 1.5
        assert opened(route, key)["when"].startswith("2026-11-06")
        route.side_effect = [httpx.Response(409, json={"ok": False})]
        await agent.answer(Holder(Fine()), LINK, request(key), http)
    assert route.call_count == 4  # a closed slot: stop


@respx.mock
async def test_a_failure_while_encoding_still_sends_an_error(monkeypatch):
    real, calls = agent.encrypt_result, []

    def flaky(key, request_id, data):
        calls.append(data)
        if len(calls) == 1:
            raise TypeError("not serializable")
        return real(key, request_id, data)

    monkeypatch.setattr(agent, "encrypt_result", flaky)

    class Fine:
        async def snapshot(self):
            return {}

    route = respx.post(f"{SERVER}/device/result").mock(return_value=httpx.Response(202))
    key = AESGCM.generate_key(bit_length=256)
    async with httpx.AsyncClient() as http:
        await agent.answer(Holder(Fine()), LINK, request(key), http)
    assert opened(route, key) == {"error": "klas_error", "message": calls[1]["message"]} and "보내지 못했습니다" in calls[1]["message"]


async def test_a_call_without_an_op_is_answered_as_unsupported():
    assert (await agent.build_result(Holder(object()), ""))["error"] == "unsupported"


class IdService:
    async def assignment_detail(self, course, title, task_id=None):
        return {"task_id": task_id}

    async def course_post(self, course, title, post_id=None):
        return {"post_id": post_id}

    async def read_attachment(self, course, title, file_name="", part="1", source="post", item_id=None, file_index=None):
        if title == "big":
            await asyncio.sleep(1)
        return {"item_id": item_id, "file_index": file_index, "part": part}


async def test_ids_from_the_lists_reach_the_service_under_its_own_names(monkeypatch):
    holder = Holder(IdService())
    assert await agent.build_result(holder, "assignment_detail", {"course": "a", "title": "b", "id": "T1"}) == {"result": {"task_id": "T1"}}
    assert await agent.build_result(holder, "course_post", {"course": "a", "title": "b", "id": "P9"}) == {"result": {"post_id": "P9"}}
    assert await agent.build_result(holder, "course_post", {"course": "a", "title": "b"}) == {"result": {"post_id": None}}
    out = await agent.build_result(holder, "read_attachment", {"course": "a", "title": "b", "id": "P9", "file_index": 2})
    assert out == {"result": {"item_id": "P9", "file_index": "2", "part": ""}}


async def test_a_big_attachment_answers_pending_and_keeps_downloading(monkeypatch):
    monkeypatch.setattr(agent, "ATTACHMENT_WAIT_S", 0.05)
    out = await agent.build_result(Holder(IdService()), "read_attachment", {"course": "a", "title": "big"})
    assert out["result"]["pending"] is True and "다시" in out["result"]["message"]
    assert len(agent._background) == 1  # still running, so the retry finds the text ready
    await asyncio.gather(*agent._background)


async def test_klas_maintenance_and_the_request_cap_are_explained():
    from kw_mcp.klas import KlasRequestLimit, KlasUnavailable

    for error in (KlasUnavailable("KLAS 점검 중입니다. 5분 뒤 다시"), KlasRequestLimit("요청이 많아 1분 쉽니다")):
        class Broken:
            async def snapshot(self, error=error):
                raise error

        assert await agent.build_result(Holder(Broken())) == {"error": "klas_error", "message": str(error)}


# --- reconnecting -------------------------------------------------------------------------

class ClosingSocket:
    """Accepted, then closed at once by the bridge."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration

    async def send(self, data):
        pass


class Stop(Exception):
    pass


def run_reconnects(monkeypatch, connect, count=5) -> list[float]:
    sleeps: list[float] = []

    async def fake_sleep(s):
        sleeps.append(s)
        if len(sleeps) >= count:
            raise Stop

    monkeypatch.setattr(agent, "load_link", lambda: LINK)
    monkeypatch.setattr(agent.DeviceKey, "load", classmethod(lambda cls: agent.DeviceKey.generate()))
    monkeypatch.setattr(agent.websockets, "connect", connect)
    monkeypatch.setattr(agent.asyncio, "sleep", fake_sleep)
    with pytest.raises(Stop):
        asyncio.run(agent.run_forever())
    return sleeps


def test_a_bridge_that_closes_at_once_keeps_backing_off_with_jitter(monkeypatch):
    sleeps = run_reconnects(monkeypatch, lambda *a, **k: ClosingSocket())
    for s, ceiling in zip(sleeps, (1, 2, 4, 8, 16), strict=True):
        assert ceiling / 2 <= s <= ceiling  # doubling, never reset by a connection that didn't hold


def test_a_connection_that_held_resets_the_backoff(monkeypatch):
    monkeypatch.setattr(agent, "STABLE_CONNECTION_S", 0.0)
    sleeps = run_reconnects(monkeypatch, lambda *a, **k: ClosingSocket())
    assert all(0.5 <= s <= 1 for s in sleeps) and len(set(sleeps)) > 1


def test_a_refused_pc_waits_long_and_says_when_its_clock_is_off(monkeypatch, caplog):
    def refuse(*a, **k):
        raise websockets.InvalidStatus(Response(401, "Unauthorized", Headers({"Date": date(-7200)})))

    sleeps = run_reconnects(monkeypatch, refuse, count=3)
    assert all(480 <= s <= 720 for s in sleeps) and len(set(sleeps)) > 1
    assert "clock is 120 minutes ahead" in caplog.text


def test_the_connect_signature_covers_the_protocol_version():
    key = agent.DeviceKey.generate()
    from urllib.parse import parse_qs, urlparse

    q = {k: v[0] for k, v in parse_qs(urlparse(agent._connect_url(LINK, key)).query).items()}
    verify(key, f"kw-connect:{LINK.uid}:{q['ts']}:{agent.PROTOCOL_VERSION}", q["sig"])
    with pytest.raises(InvalidSignature):  # the old, unversioned form is not what we sign any more
        verify(key, f"kw-connect:{LINK.uid}:{q['ts']}", q["sig"])


# --- notifications ----------------------------------------------------------------------------

def test_a_new_connection_shows_a_notification_with_the_text_as_data(monkeypatch):
    launched = []
    monkeypatch.setattr(agent.sys, "platform", "darwin")
    monkeypatch.setattr(agent.subprocess, "Popen", lambda argv, **kw: launched.append(argv))
    agent._paired({"type": "paired", "app": 'Claude" & do shell script "rm', "grant_id": "g_abc", "redirect_host": "claude.ai"})
    argv = launched[0]
    assert argv[0] == "osascript" and argv[-2] == "KW Campus"
    assert argv[-1].startswith('새 연결: Claude" & do shell script "rm') and "kw-mcp revoke g_abc" in argv[-1]
    assert not any("rm" in part for part in argv[:-2])  # the name is an argument, never part of the script
    assert "$env:KW_NOTIFY_TEXT" in agent._BALLOON  # on Windows the text travels in the environment


# --- uv under launchd -----------------------------------------------------------------------

def test_uv_recorded_at_link_time_is_found_first(config_dir, tmp_path, monkeypatch):
    fake = tmp_path / "homebrew" / "bin" / "uv"
    fake.parent.mkdir(parents=True)
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake.parent))
    assert agent.remember_uv() == str(fake)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")  # launchd's bare PATH
    assert agent.find_uv() == str(fake)
    names = [str(p) for p in agent.uv_candidates()]
    if os.name != "nt":
        assert "/opt/homebrew/bin/uv" in names and "/usr/local/bin/uv" in names


# --- one agent per user ---------------------------------------------------------------------

def test_replace_stops_this_users_agent_and_another_user_has_their_own_lock(config_dir, tmp_path, monkeypatch):
    first = agent.single_instance()
    killed = []
    monkeypatch.setattr(agent, "_running_pid", lambda: 4242)
    monkeypatch.setattr(agent, "_ask_legacy_agent_to_exit", lambda: None)
    monkeypatch.setattr(agent.os, "kill", lambda pid, sig: killed.append(pid) or first.close())  # it exits on SIGTERM
    second = agent.single_instance(replace=True)
    try:
        assert killed == [4242] and second.replaced and agent.agent_running()
        monkeypatch.setattr(agent, "CONFIG_DIR", tmp_path / "other-user")
        assert not agent.agent_running()  # a lock file per user, not a port per machine
        agent.single_instance().close()
    finally:
        second.close()
