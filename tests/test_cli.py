"""The kw-mcp command line: readable errors instead of tracebacks, one re-entry of a wrong password,
a clock check before linking, connections listing, --version as the health check."""

from __future__ import annotations

import subprocess
import sys
from typing import ClassVar

import httpx
import pytest
from keyring.errors import KeyringError

import kw_mcp
from kw_mcp import agent, credentials
from kw_mcp.klas import KlasBadPassword

SERVER = "https://bridge.example"
INVITE = agent.make_invite(SERVER, "tok")


@pytest.fixture(autouse=True)
def config_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(agent, "LINK_FILE", tmp_path / "config" / "agent.json")


def run_cli(monkeypatch, *argv: str) -> SystemExit:
    monkeypatch.setattr(sys, "argv", ["kw-mcp", *argv])
    with pytest.raises(SystemExit) as e:
        kw_mcp.main()
    return e.value


@pytest.mark.parametrize(("error", "says"), [
    (KeyringError("locked"), "키체인"),
    (httpx.ConnectError("offline"), "연결하지 못했습니다(ConnectError)"),
    (agent.ClockSkew(3600), "60분 빠릅니다"),
    (subprocess.CalledProcessError(5, ["launchctl", "bootstrap"]), "자동 실행을 등록하지 못했습니다"),
    (agent.DeviceRefused("서명을 받아들이지 않습니다"), "서명을"),
    (ZeroDivisionError("x"), "KW_MCP_DEBUG"),
])
def test_errors_become_one_readable_line(monkeypatch, capsys, error, says):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(agent, "pair_code", fail)
    exit_ = run_cli(monkeypatch, "code")
    assert says in str(exit_.code) and "Traceback" not in capsys.readouterr().err


def test_a_wrong_clock_stops_link_before_anything_is_registered(monkeypatch):
    def skewed(server):
        raise agent.ClockSkew(-9 * 3600)

    registered = []
    monkeypatch.setattr(agent, "check_server_clock", skewed)
    monkeypatch.setattr(agent, "register", lambda *a: registered.append(a))
    exit_ = run_cli(monkeypatch, "link", INVITE)
    assert "시계" in str(exit_.code) and registered == []


def test_link_still_prints_the_code_when_autostart_fails(monkeypatch, capsys):
    monkeypatch.setattr(agent, "check_server_clock", lambda server: None)
    monkeypatch.setattr(agent, "remember_uv", lambda: None)
    monkeypatch.setattr(credentials, "load", lambda: credentials.Credentials("2022000000", "pw"))

    async def ok(retry=True):
        return 0

    monkeypatch.setattr(kw_mcp, "_login_ok", ok)
    monkeypatch.setattr(agent, "linked_to", lambda server: False)
    monkeypatch.setattr(agent, "register", lambda invite, server: (None, f"{SERVER}/mcp"))

    def no_launchd():
        raise subprocess.CalledProcessError(5, ["launchctl", "bootstrap"])

    monkeypatch.setattr(agent, "install_autostart", no_launchd)
    monkeypatch.setattr(agent, "pair_code", lambda: {"code": "ABCD-EFGH", "expires_in": 900})
    assert run_cli(monkeypatch, "link", INVITE).code == 0
    out = capsys.readouterr().out
    assert "자동 실행을 등록하지 못했습니다" in out and "ABCD-EFGH" in out


class FakeClient:
    attempts: ClassVar[list[str]] = []

    def __init__(self, login_id, password, login_hint=""):
        self.password = password

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def login(self):
        FakeClient.attempts.append(self.password)
        if self.password == "offline":
            raise httpx.ConnectTimeout("slow")
        if self.password != "right":
            raise KlasBadPassword("개인번호 또는 비밀번호가 일치하지 않습니다.")


@pytest.fixture
def klas(monkeypatch):
    import kw_mcp.klas

    FakeClient.attempts = []
    monkeypatch.setattr(kw_mcp.klas, "KlasClient", FakeClient)
    saved = {"password": "wrong"}
    monkeypatch.setattr(credentials, "load", lambda: credentials.Credentials("2022000000", saved["password"]))
    monkeypatch.setattr(credentials, "login_hint", lambda creds: "")
    return saved


async def test_a_rejected_password_is_asked_again_once_in_a_terminal(klas, monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(kw_mcp, "_setup", lambda: klas.update(password="still wrong"))
    assert await kw_mcp._login_ok() == 1
    assert FakeClient.attempts == ["wrong", "still wrong"]  # once more, never a loop
    klas["password"] = "wrong"
    FakeClient.attempts = []
    monkeypatch.setattr(kw_mcp, "_setup", lambda: klas.update(password="right"))
    assert await kw_mcp._login_ok() == 0 and FakeClient.attempts == ["wrong", "right"]


async def test_no_prompt_without_a_terminal_and_network_errors_are_explained(klas, monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    monkeypatch.setattr(kw_mcp, "_setup", lambda: pytest.fail("must not prompt"))
    assert await kw_mcp._login_ok() == 1 and FakeClient.attempts == ["wrong"]
    klas["password"] = "offline"
    assert await kw_mcp._login_ok() == 1
    assert "KLAS에 연결하지 못했습니다(ConnectTimeout)" in capsys.readouterr().out


def test_connections_are_listed_in_kst_with_their_ids(monkeypatch, capsys):
    monkeypatch.setattr(agent, "grants", lambda: [
        {"id": "g_abc", "client": "Claude", "redirect_host": "claude.ai", "created": "2026-11-06T10:00:00+09:00",
         "last_used": None, "expires": "2027-05-05T10:00:00+09:00"}])
    assert run_cli(monkeypatch, "connections").code == 0
    out = capsys.readouterr().out
    assert "g_abc  Claude  claude.ai" in out and "2026-11-06 10:00" in out and "아직 없음" in out
    assert "kw-mcp revoke" in out


def test_update_explains_why_it_cannot_run(monkeypatch, capsys):
    assert run_cli(monkeypatch, "update").code == 1
    assert "연결돼 있지 않아" in capsys.readouterr().out


def test_version_is_a_health_check(capsys):
    assert kw_mcp._version(None) == 0 and capsys.readouterr().out.startswith("kw-mcp ")
    assert kw_mcp._version("0.0.0-not-this") == 1
