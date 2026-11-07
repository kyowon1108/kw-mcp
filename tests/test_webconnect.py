"""connect_other_devices: linking this PC for Claude on the web and phone from inside the extension, with
no terminal; klas_status's web_connection; and the extension's agent never installing releases itself."""

from __future__ import annotations

import asyncio
import json
import plistlib
import subprocess
import sys

import httpx
import pytest
import respx
from mcp.server.mcpserver.exceptions import ToolError

import kw_mcp
from kw_mcp import agent, credentials, server, webconnect
from kw_mcp.klas import KlasBadPassword, KlasLoginBlocked
from kw_mcp.public_api import PublicApi

SERVER = "https://bridge.example"
INVITE = agent.make_invite(SERVER, "tok")
LINK = agent.Link(server=SERVER, ws_url="wss://ws.example/prod", uid="u_" + "a" * 22)
STUDENT_ID, PASSWORD = "2022123480", "s3cret-pw"
CODE = {"code": "ABCD-EFGH", "expires_in": 900, "mcp_url": f"{SERVER}/mcp"}
REAL_REGISTER = agent.register
REAL_PAIR_CODE = agent.pair_code


class Bridge:
    """Stands in for the bridge calls, autostart and the browser; records what ran, in order."""

    def __init__(self, monkeypatch, *, linked: bool = False, can_notify: bool = True) -> None:
        self.ran: list[str] = []
        self.opened: list[str] = []
        self.notified: list[tuple[str, str]] = []
        self.linked, self.can_notify = linked, can_notify
        monkeypatch.setattr(agent, "notify", self.notify)
        monkeypatch.setattr(agent, "check_server_clock", lambda s: self.ran.append("clock"))
        monkeypatch.setattr(agent, "linked_to", self.linked_to)
        monkeypatch.setattr(agent, "register", self.register)
        monkeypatch.setattr(agent, "pair_code", self.pair_code)
        monkeypatch.setattr(agent, "install_autostart", self.install_autostart)
        monkeypatch.setattr(webconnect.webbrowser, "open", self.open)

    def linked_to(self, server_url):
        self.ran.append("linked_to")
        return self.linked

    def register(self, invite, expected_server=None):
        self.ran.append("register")
        agent.save_link(LINK)
        return LINK, f"{SERVER}/mcp"

    def pair_code(self):
        self.ran.append("pair")
        return dict(CODE)

    def install_autostart(self):
        self.ran.append("autostart")
        return "로그인 항목(launchd)"

    def open(self, url):
        self.opened.append(url)
        return True

    def notify(self, title, text):
        self.notified.append((title, text))
        return self.can_notify


@pytest.fixture(autouse=True)
def extension(monkeypatch):
    """The extension's environment on a Mac: its settings in the environment, KLAS accepting the login."""
    monkeypatch.setattr(webconnect.sys, "platform", "darwin")
    monkeypatch.setenv("KLAS_ID", STUDENT_ID)
    monkeypatch.setenv("KLAS_PASSWORD", PASSWORD)
    monkeypatch.setenv("KW_CAMPUS_INVITE", INVITE)
    monkeypatch.setenv("KW_MCP_DISTRIBUTION", "mcpb")
    logins = []

    async def login_ok(creds):
        logins.append(creds.login_id)

    monkeypatch.setattr(webconnect, "check_login", login_ok)
    return logins


def no_bridge(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("nothing may be registered, started or opened")

    for name in ("check_server_clock", "linked_to", "register", "pair_code", "install_autostart"):
        monkeypatch.setattr(agent, name, fail)
    monkeypatch.setattr(webconnect.webbrowser, "open", fail)


# --- settings that are missing --------------------------------------------------------------------

@pytest.mark.parametrize("value", [None, "", "  ", "${user_config.campus_invite}"])
async def test_without_an_invite_it_only_says_where_to_get_one(monkeypatch, extension, value):
    if value is None:
        monkeypatch.delenv("KW_CAMPUS_INVITE")
    else:
        monkeypatch.setenv("KW_CAMPUS_INVITE", value)
    no_bridge(monkeypatch)
    out = await webconnect.connect()
    assert out["connected"] is False and out["missing"] == "invite"
    steps = " ".join(out["next"])
    assert out["message"] == "초대 코드가 없어요." and len(out["next"]) <= 3
    assert "디스코드" in steps and "설치하기" in steps and "초대 코드 칸" in steps
    assert extension == []  # not even KLAS was asked
    assert not credentials.keyring.get_password(credentials.KEYRING_SERVICE, credentials.KEYRING_ID_KEY)


@pytest.mark.parametrize("value", ["kwc_not-base64!", "https://bridge.example/setup#kwc_abc",
                                   agent.make_invite("http://evil.example", "tok")])
async def test_an_unreadable_invite_is_the_same_guidance(monkeypatch, extension, value):
    monkeypatch.setenv("KW_CAMPUS_INVITE", value)
    no_bridge(monkeypatch)
    out = await webconnect.connect()
    assert out["connected"] is False and out["missing"] == "invite" and out["message"] == "초대 코드가 맞지 않아요."
    assert extension == []


async def test_without_a_login_anywhere_it_says_to_fill_in_the_settings(monkeypatch, extension):
    monkeypatch.setenv("KLAS_ID", "${user_config.klas_id}")
    monkeypatch.delenv("KLAS_PASSWORD")
    no_bridge(monkeypatch)
    out = await webconnect.connect()
    assert out["connected"] is False and out["missing"] == "credentials"
    assert out["message"] == "학번·비밀번호가 비어 있어요." and "확장" in out["next"][0]


async def test_linux_is_told_it_isnt_supported_before_anything_runs(monkeypatch, extension):
    monkeypatch.setattr(webconnect.sys, "platform", "linux")
    monkeypatch.setattr(webconnect.os, "name", "posix")
    no_bridge(monkeypatch)
    out = await webconnect.connect()
    assert out["problem"] == "unsupported_os" and extension == []


# --- KLAS refusing the login ----------------------------------------------------------------------

@pytest.mark.parametrize(("error", "says"), [
    (KlasBadPassword("개인번호 또는 비밀번호가 일치하지 않습니다. — 로그인한 아이디는 2022******(10자리)입니다."),
     "학번이나 비밀번호가 맞지 않아요"),
    (KlasLoginBlocked("KLAS가 이 로그인에 2차 인증을 요구합니다."), "추가 확인"),
    (httpx.ConnectTimeout("slow"), "KLAS에 연결하지 못했어요"),
])
async def test_a_refused_login_stops_before_linking_with_the_reason(monkeypatch, error, says):
    async def refused(creds):
        raise error

    monkeypatch.setattr(webconnect, "check_login", refused)
    no_bridge(monkeypatch)
    out = await webconnect.connect()
    assert out["connected"] is False and out["problem"] == "klas_login" and says in out["message"]
    assert PASSWORD not in json.dumps(out, ensure_ascii=False) and len(out["next"]) <= 3
    if isinstance(error, KlasLoginBlocked):  # the cause varies (2FA, captcha count, a password change)
        assert "브라우저에서 KLAS" in out["next"][0] and out["detail"] == str(error)
    else:
        assert "detail" not in out
    # a login KLAS didn't accept is never copied for the PC agent
    assert not credentials.keyring.get_password(credentials.KEYRING_SERVICE, STUDENT_ID)


# --- linking ----------------------------------------------------------------------------------------

async def test_first_link_saves_the_login_registers_starts_the_agent_and_opens_the_page(monkeypatch, extension):
    bridge = Bridge(monkeypatch)
    out = await webconnect.connect()
    assert extension == [STUDENT_ID]  # KLAS checked once
    assert bridge.ran == ["clock", "linked_to", "register", "pair", "autostart"]
    assert bridge.opened == [f"{SERVER}/connect#ABCD-EFGH"]
    assert out["connected"] is True and out["already_linked"] is False and "note" not in out
    assert out["browser_opened"] is True and out["mcp_url"] == f"{SERVER}/mcp"
    # the code went to the browser and a desktop notification only: the answer (which the model reads) lacks it
    assert out["connect_url"] == f"{SERVER}/connect"
    assert out["next"] == ["브라우저에 연결 페이지를 열었어요. 안내대로 해 주세요.", "자동 연결이 안 되면 알림에 뜬 코드를 넣어 주세요."]
    assert "code" not in out and "caution" not in out and "ABCD-EFGH" not in json.dumps(out)
    assert bridge.notified == [("KW CAMPUS 연결 코드", "자동 연결이 안 되면 이 코드를 넣어 주세요: ABCD-EFGH")]
    # the PC agent (started without the extension's settings) reads the login from the keychain
    assert credentials.keyring.get_password(credentials.KEYRING_SERVICE, credentials.KEYRING_ID_KEY) == STUDENT_ID
    assert credentials.keyring.get_password(credentials.KEYRING_SERVICE, STUDENT_ID) == PASSWORD
    text = json.dumps(out, ensure_ascii=False)
    assert PASSWORD not in text and STUDENT_ID not in text


async def test_an_already_linked_pc_keeps_its_device_and_only_gets_a_new_code(monkeypatch):
    agent.save_link(LINK)
    bridge = Bridge(monkeypatch, linked=True)
    out = await webconnect.connect()
    assert "register" not in bridge.ran and bridge.ran == ["clock", "linked_to", "pair", "autostart"]
    assert out["connected"] is True and out["already_linked"] is True
    assert out["note"] == "이미 연결돼 있어요. 기존 커넥터는 그대로 쓰면 돼요." and out["mcp_url"] == f"{SERVER}/mcp"


async def test_the_browser_gets_exactly_the_connect_page_with_the_code(monkeypatch):
    bridge = Bridge(monkeypatch)
    monkeypatch.setattr(agent, "pair_code", lambda: {"code": "WXYZ-2345", "expires_in": 600})
    out = await webconnect.connect()
    assert bridge.opened == [f"{SERVER}/connect#WXYZ-2345"] and "WXYZ-2345" not in json.dumps(out)
    assert out["mcp_url"] == f"{SERVER}/mcp"  # from the registration when the code doesn't carry it


async def test_a_browser_that_does_not_open_still_gives_the_link(monkeypatch):
    bridge = Bridge(monkeypatch)

    def no_browser(url):
        raise OSError("no display")

    monkeypatch.setattr(webconnect.webbrowser, "open", no_browser)
    out = await webconnect.connect()
    assert out["connected"] is True and out["browser_opened"] is False and "autostart" in bridge.ran
    # Claude has to show the code now: the link with it, the code for other devices, one caution line
    assert out["code"] == "ABCD-EFGH" and out["expires_in_minutes"] == 15
    assert out["connect_url"] == f"{SERVER}/connect#ABCD-EFGH" and out["connect_url"] in out["next"][0]
    assert out["next"][1] == "다른 기기에서는 연결 코드 ABCD-EFGH를 넣어요." and len(out["next"]) == 2
    assert out["caution"] == "코드는 남에게 보내지 마세요."


async def test_the_keychain_is_written_only_when_the_login_is_missing_or_different(monkeypatch, memory_keychain):
    Bridge(monkeypatch)
    writes = []
    real = credentials.save
    monkeypatch.setattr(credentials, "save", lambda i, p: writes.append(i) or real(i, p))
    await webconnect.connect()
    await webconnect.connect()  # the same login: nothing to save
    monkeypatch.setenv("KLAS_PASSWORD", "changed-pw")
    await webconnect.connect()
    assert writes == [STUDENT_ID, STUDENT_ID]
    assert memory_keychain.get_password(credentials.KEYRING_SERVICE, STUDENT_ID) == "changed-pw"


@respx.mock
async def test_the_bridge_refusing_the_invite_says_to_get_a_new_one(monkeypatch):
    bridge = Bridge(monkeypatch)
    monkeypatch.setattr(agent, "register", REAL_REGISTER)  # the real one, against a mocked bridge
    respx.post(f"{SERVER}/device/register").mock(return_value=httpx.Response(403, json={"error": "invalid_invite"}))
    out = await webconnect.connect()
    assert out["connected"] is False and out["problem"] == "invite_refused"
    assert out["message"] == "이 초대 코드로는 연결이 안 돼요." and "디스코드" in out["next"][0]
    assert "autostart" not in bridge.ran and bridge.opened == []
    with pytest.raises(agent.NotLinked):
        agent.load_link()  # nothing half-registered


@respx.mock
async def test_too_many_pcs_on_one_invite_is_explained(monkeypatch):
    bridge = Bridge(monkeypatch)
    monkeypatch.setattr(agent, "register", REAL_REGISTER)
    respx.post(f"{SERVER}/device/register").mock(return_value=httpx.Response(
        409, json={"error": "too_many_devices", "limit": 5, "message": "`kw-mcp unlink`로 연결을 해제하거나"}))
    out = await webconnect.connect()
    assert out["problem"] == "invite_refused" and out["message"] == "이 초대 코드로 연결한 PC가 이미 5대예요."
    assert "kw-mcp" not in json.dumps(out, ensure_ascii=False)  # the bridge's terminal advice isn't passed on
    assert bridge.opened == []


async def test_a_withdrawn_invite_registers_again_with_the_one_in_the_settings(monkeypatch):
    agent.save_link(LINK)
    bridge = Bridge(monkeypatch, linked=True)
    codes = iter([agent.InviteRevoked("철회"), dict(CODE)])

    def pair():
        bridge.ran.append("pair")
        answer = next(codes)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(agent, "pair_code", pair)
    out = await webconnect.connect()
    assert bridge.ran == ["clock", "linked_to", "pair", "register", "pair", "autostart"]
    assert out["connected"] is True and out["already_linked"] is False and "다시 연결해 주세요" in out["note"]


async def test_a_device_key_the_bridge_rejects_is_relinked_only_when_asked(monkeypatch):
    agent.save_link(LINK)
    bridge = Bridge(monkeypatch, linked=True)

    def bad_signature(server_url):
        bridge.ran.append("linked_to")
        raise agent.DeviceRefused("중계 서버가 이 PC의 서명을 받아 주지 않아요. 이 PC를 새로 등록해야 해요.")

    monkeypatch.setattr(agent, "linked_to", bad_signature)
    out = await webconnect.connect()
    assert out["connected"] is False and out["problem"] == "device_key_mismatch" and out["can_relink"] is True
    assert "register" not in bridge.ran and bridge.opened == []
    out = await webconnect.connect(relink=True)
    assert out["connected"] is True and bridge.ran[-3:] == ["register", "pair", "autostart"]


@pytest.mark.parametrize(("error", "says"), [
    (httpx.ConnectError("offline"), "서버에 연결하지 못했어요"),
    (agent.ClockSkew(3600), "60분 빨라요"),
])
async def test_network_and_clock_failures_are_tool_errors_with_a_reason(monkeypatch, error, says):
    bridge = Bridge(monkeypatch)

    def fail(server_url):
        raise error

    monkeypatch.setattr(agent, "check_server_clock", fail)
    with pytest.raises(ToolError, match=says.replace("(", r"\(").replace(")", r"\)")):
        await server.connect_other_devices()
    assert bridge.ran == [] and bridge.opened == []


@pytest.mark.parametrize("error", [subprocess.CalledProcessError(5, ["launchctl", "bootstrap"]),
                                   PermissionError("registry")])
async def test_an_autostart_failure_says_to_ask_again_later(monkeypatch, error):
    bridge = Bridge(monkeypatch)

    def fail():
        raise error

    monkeypatch.setattr(agent, "install_autostart", fail)
    with pytest.raises(ToolError) as caught:
        await server.connect_other_devices()
    message = str(caught.value)
    assert message == "자동 실행 등록이 안 됐어요. 잠시 뒤 다시 연결해 달라고 말해 주세요."
    assert bridge.opened == []


async def test_the_tool_answers_with_the_result(monkeypatch):
    Bridge(monkeypatch)
    result = await server.mcp.call_tool("connect_other_devices", {})
    assert not result.is_error and result.structured_content["connect_url"] == f"{SERVER}/connect"


# --- the agent the extension starts -------------------------------------------------------------

def test_the_extension_starts_the_agent_with_its_own_python_marked_as_the_extensions(monkeypatch):
    command = agent.agent_command()
    assert command[:4] == [sys.executable, "-m", "kw_mcp", "agent"] and command[-1] == "--from-extension"
    assert plistlib.loads(agent.launchd_plist())["ProgramArguments"] == command
    monkeypatch.delenv("KW_MCP_DISTRIBUTION")  # an agent installed the old way: unchanged
    assert "--from-extension" not in agent.agent_command()


def test_a_started_agent_reads_the_keychain_not_the_extension_settings():
    env = agent._agent_env()
    assert "KLAS_ID" not in env and "KLAS_PASSWORD" not in env and env["KW_MCP_DISTRIBUTION"] == "mcpb"


def test_the_agent_command_line_marks_the_process(monkeypatch):
    monkeypatch.delenv("KW_MCP_DISTRIBUTION")
    seen = []
    monkeypatch.setattr(kw_mcp, "_agent", lambda log_file, replace: seen.append(agent.from_extension()))
    monkeypatch.setattr(sys, "argv", ["kw-mcp", "agent", "--log-file", "x.log", "--from-extension"])
    kw_mcp.main()
    assert seen == [True]


def test_the_extensions_agent_never_installs_a_release(monkeypatch, tmp_path):
    monkeypatch.setattr(agent, "in_uv_tool", lambda: True)  # even if it looked like a uv tool install
    monkeypatch.setattr(agent, "find_uv", lambda: "/opt/homebrew/bin/uv")
    monkeypatch.setattr(agent.subprocess, "run", lambda *a, **k: pytest.fail("no uv run"))
    assert agent.self_updates() is False
    wheel, pins = tmp_path / "kw_mcp-9.9.9-py3-none-any.whl", tmp_path / "pins.txt"
    assert agent.install_update(wheel, pins, "9.9.9") is False
    assert agent.roll_back({"version": "9.9.9", "previous": "1.0.0"}) is False

    async def fetch(*args):
        pytest.fail("the extension's agent doesn't look for wheels")

    monkeypatch.setattr(agent, "fetch_update", fetch)

    async def loop():
        await asyncio.wait_for(agent.update_loop(SERVER, first_delay=0), 0.1)

    with pytest.raises(TimeoutError):  # waits forever, never checks
        asyncio.run(loop())
    monkeypatch.delenv("KW_MCP_DISTRIBUTION")
    assert agent.self_updates() is True  # a uv tool agent installed the old way still updates itself


# --- klas_status -----------------------------------------------------------------------------------

async def test_status_of_a_pc_that_isnt_linked_says_how_to_link():
    out = await webconnect.status()
    assert out["linked"] is False and "연결해 줘" in out["next"]


async def test_status_of_a_linked_pc_lists_its_apps_by_redirect_host(monkeypatch):
    agent.save_link(LINK)
    monkeypatch.setattr(agent, "autostart_installed", lambda: True)
    monkeypatch.setattr(agent, "agent_running", lambda: True)
    monkeypatch.setattr(agent, "grants", lambda: [
        {"id": "g_x", "client": "Claude", "redirect_host": "claude.ai", "created": "2026-11-06T10:00:00+09:00",
         "last_used": None, "expires": None},
        {"id": "", "client": "Totally Claude", "redirect_host": "evil.example", "created": None, "last_used": None,
         "expires": None}])
    out = await webconnect.status()
    assert out["linked"] is True and out["server"] == "bridge.example"
    assert out["autostart_installed"] is True and out["agent_running"] is True and "next" not in out
    assert out["disconnect"] == "이 PC 연결을 끊으려면 '이 PC 연결 끊어 줘'라고 말해 주세요."
    assert [a["app"] for a in out["connected_apps"]] == ["Claude", "evil.example"]  # never the self-chosen name


async def test_status_never_fails_and_never_waits_long(monkeypatch):
    agent.save_link(LINK)
    monkeypatch.setattr(agent, "autostart_installed", lambda: False)
    monkeypatch.setattr(agent, "agent_running", lambda: False)

    def offline():
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(agent, "grants", offline)
    out = await webconnect.status()
    assert out["connected_apps"] is None and out["apps_note"] == "연결한 앱 목록을 못 가져왔어요."
    assert out["next"].startswith("에이전트가 꺼져 있어요.")

    def slow():
        import time

        time.sleep(0.5)
        return []

    monkeypatch.setattr(agent, "grants", slow)
    out = await webconnect.status(timeout=0.05)
    assert out["connected_apps"] is None and out["apps_note"] == "연결한 앱 목록을 못 가져왔어요."

    def broken():
        raise RuntimeError("disk")

    monkeypatch.setattr(agent, "load_link", broken)
    assert (await webconnect.status())["linked"] is None


async def test_klas_status_has_a_web_connection_section(monkeypatch):
    monkeypatch.setattr(credentials, "load", lambda: credentials.Credentials(STUDENT_ID, PASSWORD, credentials.ENV))
    monkeypatch.delenv("KW_MCP_DISTRIBUTION")
    server.set_public(PublicApi(""))
    try:
        out = await server.klas_status()
    finally:
        server.set_public(None)
    assert out["web_connection"]["linked"] is False and "연결해 줘" in out["web_connection"]["next"]


# --- disconnect_app --------------------------------------------------------------------------------

GRANT = "g_AbC123-_xyz9"
GRANTS = [
    {"id": GRANT, "client": "Claude", "redirect_host": "claude.ai", "created": "2026-11-06T10:00:00+09:00",
     "last_used": "2026-11-07T08:30:00+09:00", "expires": None},
    {"id": "g_ZZZ999-_abc1", "client": "Totally Claude", "redirect_host": "chatgpt.com", "created": 1762390800,
     "last_used": None, "expires": None},
]


@pytest.fixture
def never_unlinked(monkeypatch):
    monkeypatch.setattr(agent, "unlink", lambda **kw: pytest.fail("disconnect_app never unlinks the PC"))
    monkeypatch.setattr(agent, "uninstall_autostart", lambda: pytest.fail("the agent keeps running"))


async def test_without_an_id_it_lists_the_connected_apps(monkeypatch, never_unlinked):
    monkeypatch.setattr(agent, "grants", lambda: [dict(g) for g in GRANTS])
    monkeypatch.setattr(agent, "revoke", lambda grant_id: pytest.fail("listing ends nothing"))
    out = await server.disconnect_app()
    assert out["linked"] is True and out["next"] == "끊을 앱을 골라 주세요."
    assert out["apps"] == [
        {"app": "Claude", "host": "claude.ai", "connected": "2026-11-06 10:00", "last_used": "2026-11-07 08:30",
         "id": GRANT},
        {"app": "ChatGPT", "host": "chatgpt.com", "connected": "2025-11-06 10:00", "last_used": "아직 없음",
         "id": "g_ZZZ999-_abc1"},  # named by its redirect host, never by its self-chosen name
    ]
    monkeypatch.setattr(agent, "grants", list)
    assert (await server.disconnect_app())["message"] == "연결된 앱이 없어요."


async def test_with_an_id_it_ends_only_that_connection(monkeypatch, never_unlinked):
    ended = []
    monkeypatch.setattr(agent, "grants", lambda: [dict(g) for g in GRANTS])
    monkeypatch.setattr(agent, "revoke", ended.append)
    out = await server.disconnect_app(f" {GRANT} ")
    assert ended == [GRANT] and out["disconnected"] is True and out["app"] == "Claude"
    assert out["message"] == "Claude 연결을 끊었어요."
    assert [a["id"] for a in out["apps"]] == ["g_ZZZ999-_abc1"]


@respx.mock
async def test_ending_a_connection_signs_one_revoke_for_that_id(monkeypatch, never_unlinked):
    agent.DeviceKey.generate().save()
    agent.save_link(LINK)
    respx.post(f"{SERVER}/device/grants").mock(return_value=httpx.Response(200, json={"grants": GRANTS}))
    revoke = respx.post(f"{SERVER}/device/revoke")
    revoke.mock(return_value=httpx.Response(200, json={"ok": True}))
    out = await server.disconnect_app(GRANT)
    assert out["disconnected"] is True and json.loads(revoke.calls[0].request.content)["grant_id"] == GRANT
    revoke.mock(return_value=httpx.Response(404, json={"error": "not_found"}))
    with pytest.raises(ToolError, match="찾지 못했어요"):
        await server.disconnect_app("g_gone0000000")
    with pytest.raises(ToolError, match="연결 ID가 맞지 않아요"):
        await server.disconnect_app("g_x; rm -rf ~")
    assert len(revoke.calls) == 2  # the malformed id never reached the bridge
    assert agent.load_link() == LINK  # the PC is still linked


async def test_disconnect_on_a_pc_that_isnt_linked_or_is_offline(monkeypatch):
    out = await server.disconnect_app()
    assert out["linked"] is False and out["apps"] == [] and "연결해 줘" in out["message"]

    def offline():
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(agent, "grants", offline)
    with pytest.raises(ToolError, match="서버에 연결하지 못했어요"):
        await server.disconnect_app(GRANT)


# --- restarting the agent after an extension update ---------------------------------------------

@pytest.fixture
def updated(monkeypatch, tmp_path):
    """A linked PC whose extension-installed agent runs 1.0.0 while the extension is now 1.1.0."""
    agent.save_link(LINK)
    plist = tmp_path / "kr.kwcampus.agent.plist"
    monkeypatch.setattr(agent, "launchd_plist_path", lambda: plist)
    plist.write_bytes(agent.launchd_plist())  # what connect_other_devices installed: this command, flagged
    monkeypatch.setattr(agent, "installed_version", lambda: "1.1.0")
    monkeypatch.setattr(agent, "agent_running", lambda: True)
    agent.save_state({"running": True, "version": "1.0.0"})
    restarts = []
    monkeypatch.setattr(agent, "install_autostart", lambda: restarts.append("restart") or "launchd")
    return restarts


def test_an_outdated_extension_agent_is_restarted_once_per_version(updated):
    assert webconnect.restart_outdated_agent() is True and updated == ["restart"]
    assert (agent.CONFIG_DIR / webconnect.RESTARTED_FILE).read_text() == "1.1.0"
    # it didn't come up as 1.1.0 (no new version recorded): not restarted again at every server start
    assert webconnect.restart_outdated_agent() is False and updated == ["restart"]


def test_an_agent_from_before_versions_were_recorded_is_restarted_too(updated):
    agent.save_state({"running": True})
    assert webconnect.restart_outdated_agent() is True


@pytest.mark.parametrize("situation", ["same version", "not running", "not linked", "old-way agent", "outside the extension",
                                       "no autostart"])
def test_nothing_else_is_restarted(monkeypatch, updated, situation):
    if situation == "same version":
        agent.save_state({"running": True, "version": "1.1.0"})
    elif situation == "not running":
        monkeypatch.setattr(agent, "agent_running", lambda: False)
    elif situation == "not linked":
        agent.LINK_FILE.unlink()
    elif situation == "old-way agent":  # a uv tool install's autostart: no --from-extension, another Python
        monkeypatch.delenv("KW_MCP_DISTRIBUTION")
        agent.launchd_plist_path().write_bytes(agent.launchd_plist())
        monkeypatch.setenv("KW_MCP_DISTRIBUTION", "mcpb")
    elif situation == "outside the extension":
        monkeypatch.delenv("KW_MCP_DISTRIBUTION")
    else:
        agent.launchd_plist_path().unlink()
    assert webconnect.restart_outdated_agent() is False and updated == []


def test_a_failing_restart_never_raises_and_isnt_retried(monkeypatch, updated):
    def broken():
        raise subprocess.CalledProcessError(5, ["launchctl", "bootstrap"])

    monkeypatch.setattr(agent, "install_autostart", broken)
    assert webconnect.restart_outdated_agent() is False
    assert (agent.CONFIG_DIR / webconnect.RESTARTED_FILE).read_text() == "1.1.0"


def test_an_agent_records_the_version_it_started_as(monkeypatch):
    monkeypatch.setattr(agent, "installed_version", lambda: "1.1.0")
    agent.note_start()
    assert agent.load_state()["version"] == "1.1.0"


def test_server_start_does_not_wait_for_the_restart(monkeypatch):
    import threading

    release, started = threading.Event(), []

    def slow_restart():
        started.append(True)
        release.wait(5)
        return True

    monkeypatch.setattr(webconnect, "restart_outdated_agent", slow_restart)
    monkeypatch.setattr(server.mcp, "run", lambda transport: started.append(transport))
    server.run()  # returns while the restart is still going
    assert "stdio" in started and not release.is_set()
    release.set()
    for thread in threading.enumerate():
        if thread.name == "kw-agent-restart":
            thread.join(5)


# --- disconnect_this_pc --------------------------------------------------------------------------------

@pytest.fixture
def linked_pc(monkeypatch, memory_keychain):
    """A linked PC with a device key; removing the autostart is recorded instead of run."""
    agent.DeviceKey.generate().save()
    agent.save_link(LINK)
    removed = []
    monkeypatch.setattr(agent, "uninstall_autostart", lambda: removed.append("autostart"))
    return removed


def saved_login(memory_keychain) -> str | None:
    return memory_keychain.get_password(credentials.KEYRING_SERVICE, STUDENT_ID)


@respx.mock
async def test_disconnecting_this_pc_frees_it_on_the_bridge_and_clears_the_copied_login(linked_pc, memory_keychain):
    credentials.save(STUDENT_ID, PASSWORD)
    credentials.mark_copied()  # what connect_other_devices does
    unlink = respx.post(f"{SERVER}/device/unlink").mock(return_value=httpx.Response(200, json={"ok": True}))
    out = await server.disconnect_this_pc()
    assert out == {"disconnected": True, "login_removed": True, "message": "이 PC의 웹·폰 연결을 끊었어요."}
    assert unlink.called and linked_pc == ["autostart"] and not agent.LINK_FILE.exists()
    assert memory_keychain.get_password(credentials.KEYRING_SERVICE, agent.KEYRING_DEVICE_KEY) is None
    assert saved_login(memory_keychain) is None
    assert memory_keychain.get_password(credentials.KEYRING_SERVICE, credentials.KEYRING_COPY_KEY) is None


@respx.mock
async def test_a_login_the_student_saved_themselves_is_kept(linked_pc, memory_keychain):
    credentials.save(STUDENT_ID, PASSWORD)  # `kw-mcp setup` from the terminal days: not a copy
    respx.post(f"{SERVER}/device/unlink").mock(return_value=httpx.Response(200, json={"ok": True}))
    out = await server.disconnect_this_pc()
    assert out["disconnected"] is True and out["login_removed"] is False and saved_login(memory_keychain) == PASSWORD


async def test_only_connect_other_devices_marks_its_copy(monkeypatch, memory_keychain):
    Bridge(monkeypatch)
    await webconnect.connect()
    mark = (credentials.KEYRING_SERVICE, credentials.KEYRING_COPY_KEY)
    assert memory_keychain.get_password(*mark) == credentials.COPIED_FROM_EXTENSION
    credentials.save(STUDENT_ID, "typed-in-a-terminal")  # saving it by hand makes it the student's own
    assert memory_keychain.get_password(*mark) is None


async def test_disconnecting_a_pc_that_isnt_linked_still_removes_the_autostart(monkeypatch, memory_keychain):
    removed = []
    monkeypatch.setattr(agent, "autostart_installed", lambda: True)
    monkeypatch.setattr(agent, "uninstall_autostart", lambda: removed.append("autostart"))
    out = await server.disconnect_this_pc()
    assert out["disconnected"] is False and out["message"] == "이 PC는 연결돼 있지 않아요." and removed == ["autostart"]


@respx.mock
async def test_an_unreachable_bridge_keeps_the_key_for_a_retry(linked_pc, memory_keychain):
    respx.post(f"{SERVER}/device/unlink").mock(side_effect=httpx.ConnectError("offline"))
    with pytest.raises(ToolError, match="연결하지 못해 끊지 못했어요"):
        await server.disconnect_this_pc()
    assert agent.LINK_FILE.exists()
    assert memory_keychain.get_password(credentials.KEYRING_SERVICE, agent.KEYRING_DEVICE_KEY)


@respx.mock
async def test_a_bridge_that_refuses_this_device_still_lets_this_pc_be_cleared(linked_pc, memory_keychain):
    respx.post(f"{SERVER}/device/unlink").mock(return_value=httpx.Response(403, json={"error": "invite_revoked"}))
    out = await server.disconnect_this_pc()
    assert out["disconnected"] is True and not agent.LINK_FILE.exists()
    assert memory_keychain.get_password(credentials.KEYRING_SERVICE, agent.KEYRING_DEVICE_KEY) is None


async def test_too_many_codes_in_an_hour_says_when_to_try_again(monkeypatch):
    agent.save_link(LINK)
    bridge = Bridge(monkeypatch, linked=True)

    def pair():
        bridge.ran.append("pair")
        raise agent.TooManyCodes()

    monkeypatch.setattr(agent, "pair_code", pair)
    with pytest.raises(webconnect.Failed, match="한 시간쯤 뒤에"):
        await webconnect.connect()
    assert bridge.opened == []


def answer_429(body):
    return lambda *a: httpx.Response(429, json=body, request=httpx.Request("POST", f"{SERVER}/device/pair"))


def test_only_the_bridges_own_hourly_cap_is_too_many_codes(monkeypatch):
    monkeypatch.setattr(agent, "_device_call", answer_429({"error": "too_many_codes"}))
    with pytest.raises(agent.TooManyCodes, match="한 시간쯤 뒤에"):
        agent.pair_code()
    monkeypatch.setattr(agent, "_device_call", answer_429({"message": "Too Many Requests"}))  # API Gateway throttling
    with pytest.raises(httpx.HTTPStatusError):
        agent.pair_code()


async def test_a_throttled_bridge_says_to_try_again_shortly(monkeypatch):
    agent.save_link(LINK)
    bridge = Bridge(monkeypatch, linked=True)
    monkeypatch.setattr(agent, "_device_call", answer_429({"message": "Too Many Requests"}))
    monkeypatch.setattr(agent, "pair_code", REAL_PAIR_CODE)
    with pytest.raises(webconnect.Failed) as caught:
        await webconnect.connect()
    assert str(caught.value) == "요청이 많아요. 잠시 뒤에 다시 해 주세요." and bridge.opened == []


async def test_without_a_notification_the_code_comes_back_with_the_caution(monkeypatch):
    bridge = Bridge(monkeypatch, can_notify=False)  # e.g. Linux without notify-send
    out = await webconnect.connect()
    assert bridge.opened == [f"{SERVER}/connect#ABCD-EFGH"] and out["browser_opened"] is True
    assert out["code"] == "ABCD-EFGH" and out["caution"] == "코드는 남에게 보내지 마세요."
    assert out["next"] == ["브라우저에 연결 페이지를 열었어요. 안내대로 해 주세요.",
                           "자동 연결이 안 되면 연결 코드 ABCD-EFGH를 넣어 주세요."]


async def test_no_notification_when_the_browser_did_not_open(monkeypatch):
    bridge = Bridge(monkeypatch)
    monkeypatch.setattr(webconnect.webbrowser, "open", lambda url: False)
    out = await webconnect.connect()
    assert bridge.notified == [] and out["code"] == "ABCD-EFGH"


@pytest.mark.parametrize(("platform", "os_name", "which", "shown"), [
    ("darwin", "posix", None, True), ("linux", "posix", "/usr/bin/notify-send", True), ("linux", "posix", None, False)])
def test_notify_says_whether_it_could_show_anything(monkeypatch, platform, os_name, which, shown):
    launched = []
    monkeypatch.setattr(agent.sys, "platform", platform)
    monkeypatch.setattr(agent.os, "name", os_name)
    monkeypatch.setattr(agent.shutil, "which", lambda name: which)
    monkeypatch.setattr(agent.subprocess, "Popen", lambda argv, **kw: launched.append(kw))
    assert agent.notify("KW CAMPUS 연결 코드", "ABCD-EFGH") is shown
    assert len(launched) == int(shown)
    assert all(kw["stdin"] is kw["stdout"] is agent.subprocess.DEVNULL for kw in launched)  # never the MCP stdio
