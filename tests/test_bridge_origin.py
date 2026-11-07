"""Only the KW CAMPUS bridge: an invite or a link for any other server is refused everywhere it would be
used, before anything (a device key, the public-data token, a signed request) goes out."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from pathlib import Path

import httpx
import pytest
import respx

import kw_mcp
from kw_mcp import agent, public_api, release, updates, webconnect
from kw_mcp.public_api import PublicApi, PublicUnavailable
from tests.conftest import TEST_BRIDGE, TEST_BRIDGE_WS

ROOT = Path(__file__).resolve().parent.parent
REAL = "https://l9doaodgw6.execute-api.ap-northeast-2.amazonaws.com"
LOCAL = "http://localhost:8787"
LOOK_ALIKES = [
    "https://evil.example",
    "https://l9doaodgw7.execute-api.ap-northeast-2.amazonaws.com",  # another API Gateway, one letter off
    "https://l9doaodgw6.execute-api.us-east-1.amazonaws.com",
    "https://l9doaodgw6.execute-api.ap-northeast-2.amazonaws.com.evil.example",
]


def invite(server: str) -> str:
    return agent.make_invite(server, "tok")


def test_the_origin_is_written_down_once_and_matches_the_manifest_and_ci():
    source = (ROOT / "src" / "kw_mcp" / "release.py").read_text(encoding="utf-8")
    assert re.findall(r'^BRIDGE_ORIGIN = "([^"]+)"$', source, re.MULTILINE) == [REAL]
    privacy = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))["privacy_policies"][0]
    assert privacy == f"{REAL}/privacy"
    # agent-install.yml installs this commit directly now: no workflow carries a second copy of the origin.
    for workflow in (ROOT / ".github" / "workflows").glob("*.yml"):
        text = workflow.read_text(encoding="utf-8")
        assert "l9doaodgw6" not in text or f"BRIDGE: {REAL}" in text, workflow.name
    for name in ("agent.py", "webconnect.py", "public_api.py", "updates.py", "__init__.py"):  # no second copy
        assert "l9doaodgw6" not in (ROOT / "src" / "kw_mcp" / name).read_text(encoding="utf-8")


def test_the_real_invite_passes_with_the_real_origin(monkeypatch):
    monkeypatch.setattr(release, "BRIDGE_ORIGIN", REAL)
    assert agent.official_invite(invite(REAL)) == (REAL, "tok")
    with pytest.raises(agent.ForeignBridge):
        agent.official_invite(invite(TEST_BRIDGE))


@pytest.mark.parametrize("server", LOOK_ALIKES)
def test_a_look_alike_invite_is_not_ours(server):
    with pytest.raises(agent.ForeignBridge, match="KW CAMPUS 초대 코드가 아니에요"):
        agent.official_invite(invite(server))


@pytest.mark.parametrize("value", ["https://evil.example", "http://localhost.evil.example", "https://localhost:8787",
                                   "http://10.0.0.5:8787", "http://localhost:8787/x", "http://127.0.0.1@evil.example"])
def test_only_a_bridge_on_this_pc_may_replace_it_for_development(monkeypatch, value):
    assert release.bridge_origin() == TEST_BRIDGE
    monkeypatch.setenv(release.DEV_BRIDGE_ENV, value)
    assert release.bridge_origin() == TEST_BRIDGE  # ignored
    for local in (LOCAL, "http://127.0.0.1:9000", "http://localhost"):
        monkeypatch.setenv(release.DEV_BRIDGE_ENV, local + "/")
        assert release.bridge_origin() == local


def test_a_local_bridge_works_only_with_the_development_variable(monkeypatch):
    with pytest.raises(agent.ForeignBridge):
        agent.official_invite(invite(LOCAL))
    monkeypatch.setenv(release.DEV_BRIDGE_ENV, LOCAL)
    monkeypatch.setenv(release.DEV_BRIDGE_WS_ENV, "ws://localhost:8787/ws")
    assert agent.official_invite(invite(LOCAL))[0] == LOCAL
    with respx.mock:
        respx.post(f"{LOCAL}/device/register").mock(return_value=httpx.Response(
            201, json={"uid": "u_local", "ws_url": "ws://localhost:8787/ws", "mcp_url": f"{LOCAL}/mcp"}))
        link, mcp_url = agent.register(invite(LOCAL))
    assert link.server == LOCAL and mcp_url == f"{LOCAL}/mcp"
    with pytest.raises(agent.ForeignBridge):  # the official bridge is not used meanwhile
        agent.official_invite(invite(TEST_BRIDGE))


# --- every place that would use the invite or the link ------------------------------------------------

@respx.mock(assert_all_called=False)
def test_register_sends_nothing_to_another_server():
    with pytest.raises(agent.ForeignBridge):
        agent.register(invite(LOOK_ALIKES[1]))
    with pytest.raises(agent.ForeignBridge):  # however the caller passes it
        agent.register(invite(LOOK_ALIKES[1]), expected_server=LOOK_ALIKES[1])
    assert respx.calls.call_count == 0 and not agent.LINK_FILE.exists()


async def test_connect_other_devices_refuses_a_look_alike_invite(monkeypatch):
    monkeypatch.setenv("KW_CAMPUS_INVITE", invite(LOOK_ALIKES[1]))
    monkeypatch.setenv("KLAS_ID", "2022123480")
    monkeypatch.setenv("KLAS_PASSWORD", "pw")

    def fail(*args, **kwargs):
        pytest.fail("nothing may run for a look-alike invite")

    monkeypatch.setattr(webconnect, "check_login", fail)
    for name in ("check_server_clock", "linked_to", "register", "pair_code", "install_autostart"):
        monkeypatch.setattr(agent, name, fail)
    out = await webconnect.connect()
    assert out["connected"] is False and out["problem"] == "invite_refused"
    assert out["message"] == "KW CAMPUS 초대 코드가 아니에요. 디스코드 #설치-안내에서 다시 받아 주세요."


async def test_the_public_data_token_never_goes_to_another_server(monkeypatch, tmp_path):
    monkeypatch.setenv("KW_CAMPUS_INVITE", invite("https://evil.example"))
    monkeypatch.delenv("KW_CAMPUS_API_URL", raising=False)
    monkeypatch.setattr(public_api, "CONFIG_FILE", tmp_path / "none")

    def handler(request):
        pytest.fail(f"no request may go out: {request.url}")

    api = PublicApi(transport=httpx.MockTransport(handler))
    try:
        assert public_api.base_url() is None and api.configured
        assert api.invalid_reason.startswith("초대 코드 형식 오류") and "KW CAMPUS 초대 코드가 아니에요" in api.invalid_reason
        with pytest.raises(PublicUnavailable, match="초대 코드 형식 오류"):
            await api.notices(category=None, limit=5, query=None)
    finally:
        await api.aclose()


def test_update_checks_go_only_to_the_bridge(monkeypatch):
    monkeypatch.setenv("KW_MCP_DISTRIBUTION", "mcpb")
    monkeypatch.setenv("KW_CAMPUS_INVITE", invite(LOOK_ALIKES[0]))
    assert updates.server() is None and "KW CAMPUS 초대 코드가 아니에요" in updates.unavailable_reason()
    monkeypatch.setenv("KW_CAMPUS_INVITE", invite(TEST_BRIDGE))
    assert updates.server() == TEST_BRIDGE


@respx.mock(assert_all_called=False)
def test_a_link_to_another_server_gets_no_signed_request(memory_keychain):
    agent.DeviceKey.generate().save()
    agent.save_link(agent.Link(server="https://evil.example", ws_url="wss://evil.example/ws", uid="u_x"))
    for call in (agent.pair_code, agent.grants):
        with pytest.raises(agent.NotLinked, match="KW CAMPUS가 아닌 서버"):
            call()
    assert agent.linked_to(TEST_BRIDGE) is False  # so connect_other_devices registers with the bridge instead
    agent._forget_previous_device()  # and doesn't tell the other server anything either
    assert respx.calls.call_count == 0


def test_the_agent_does_not_connect_to_another_server(monkeypatch, caplog):
    agent.save_link(agent.Link(server=LOOK_ALIKES[1], ws_url="wss://evil.example/ws", uid="u_x"))

    async def never(*args, **kwargs):
        pytest.fail("the agent may not connect or look for updates there")

    monkeypatch.setattr(agent, "run_forever", never)
    monkeypatch.setattr(agent, "update_loop", never)
    with caplog.at_level(logging.ERROR, logger="kw_mcp.agent"):
        assert asyncio.run(agent.main()) == 0  # a clean exit: launchd leaves it down
    lines = [r.getMessage() for r in caplog.records if r.name == "kw_mcp.agent"]
    assert len(lines) == 1 and "not the KW CAMPUS bridge" in lines[0]


def test_the_command_line_link_refuses_another_server(monkeypatch, capsys):
    def fail(*args, **kwargs):
        pytest.fail("nothing may run for a look-alike invite")

    monkeypatch.setattr(agent, "check_server_clock", fail)
    monkeypatch.setattr(agent, "register", fail)
    monkeypatch.setattr(sys, "argv", ["kw-mcp", "link", invite(LOOK_ALIKES[1])])
    with pytest.raises(SystemExit) as exit_:
        kw_mcp.main()
    assert exit_.value.code == 1 and "KW CAMPUS 초대 코드가 아니에요" in capsys.readouterr().out


# --- the WebSocket URL the agent connects to -----------------------------------------------------

def test_the_websocket_url_is_written_down_once():
    source = (ROOT / "src" / "kw_mcp" / "release.py").read_text(encoding="utf-8")
    assert re.findall(r'^BRIDGE_WS_URL = "([^"]+)"', source, re.MULTILINE) == [
        "wss://dyhc58k3rj.execute-api.ap-northeast-2.amazonaws.com/prod"]


@pytest.mark.parametrize("value", ["ws://evil.example/ws", "wss://localhost:8787/ws", "ws://10.0.0.5/ws",
                                   "ws://localhost.evil.example/ws", "ws://127.0.0.1@evil.example/ws"])
def test_only_a_websocket_on_this_pc_may_replace_it_for_development(monkeypatch, value):
    monkeypatch.setenv(release.DEV_BRIDGE_WS_ENV, value)
    assert release.bridge_ws_url() == TEST_BRIDGE_WS
    monkeypatch.setenv(release.DEV_BRIDGE_WS_ENV, "ws://127.0.0.1:8788/prod")
    assert release.bridge_ws_url() == "ws://127.0.0.1:8788/prod"


@pytest.mark.parametrize("ws_url", ["ws://evil.example/ws", "wss://evil.example/prod", f"{TEST_BRIDGE_WS}/x"])
@respx.mock
def test_register_refuses_a_websocket_url_that_isnt_the_bridges(memory_keychain, ws_url):
    respx.post(f"{TEST_BRIDGE}/device/register").mock(return_value=httpx.Response(
        201, json={"uid": "u_new", "ws_url": ws_url, "mcp_url": f"{TEST_BRIDGE}/mcp"}))
    with pytest.raises(agent.ForeignBridge, match="KW CAMPUS가 아닌 주소"):
        agent.register(invite(TEST_BRIDGE))
    assert not agent.LINK_FILE.exists()  # nothing saved: no link, no device key
    assert memory_keychain.get_password("kw-mcp", agent.KEYRING_DEVICE_KEY) is None


@respx.mock
async def test_connect_other_devices_stops_on_a_foreign_websocket_url(monkeypatch):
    monkeypatch.setattr(webconnect.sys, "platform", "darwin")
    monkeypatch.setenv("KW_CAMPUS_INVITE", invite(TEST_BRIDGE))
    monkeypatch.setenv("KLAS_ID", "2022123480")
    monkeypatch.setenv("KLAS_PASSWORD", "pw")

    async def login_ok(creds):
        return None

    monkeypatch.setattr(webconnect, "check_login", login_ok)
    monkeypatch.setattr(agent, "check_server_clock", lambda server: None)
    monkeypatch.setattr(agent, "install_autostart", lambda: pytest.fail("no agent for a foreign WebSocket"))
    respx.post(f"{TEST_BRIDGE}/device/register").mock(return_value=httpx.Response(
        201, json={"uid": "u_new", "ws_url": "ws://evil.example/ws", "mcp_url": f"{TEST_BRIDGE}/mcp"}))
    with pytest.raises(webconnect.Failed, match="KW CAMPUS가 아닌 주소"):
        await webconnect.connect()
    assert not agent.LINK_FILE.exists()


def test_the_agent_does_not_connect_to_a_saved_foreign_websocket(monkeypatch, caplog):
    agent.save_link(agent.Link(server=TEST_BRIDGE, ws_url="ws://evil.example/ws", uid="u_x"))

    async def never(*args, **kwargs):
        pytest.fail("the agent may not connect or look for updates")

    monkeypatch.setattr(agent, "run_forever", never)
    monkeypatch.setattr(agent, "update_loop", never)
    with caplog.at_level(logging.ERROR, logger="kw_mcp.agent"):
        assert asyncio.run(agent.main()) == 0
    lines = [r.getMessage() for r in caplog.records if r.name == "kw_mcp.agent"]
    assert len(lines) == 1 and "not the KW CAMPUS bridge" in lines[0] and "ws://evil.example/ws" in lines[0]


async def test_a_saved_foreign_websocket_counts_as_not_linked(monkeypatch):
    agent.save_link(agent.Link(server=TEST_BRIDGE, ws_url="ws://evil.example/ws", uid="u_x"))
    monkeypatch.setattr(agent, "grants", lambda: pytest.fail("no signed request needed to know"))
    assert agent.linked_to(TEST_BRIDGE) is False  # connect_other_devices registers again
    assert (await webconnect.status())["linked"] is False
