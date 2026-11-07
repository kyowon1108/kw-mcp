"""Linking this PC for Claude on the web and phone, from inside the Claude Desktop extension.

The extension already holds the student's 학번·비밀번호 and invite (its settings, passed in as
KLAS_ID / KLAS_PASSWORD / KW_CAMPUS_INVITE). connect() does what `kw-mcp link` did in a terminal,
without asking anything:

1. the invite names the bridge; without a readable one, it says where to get one and where it goes;
2. KLAS accepts the login (one login, behind the same rejected-password guard as every other);
3. the login is copied into the keychain, where the PC agent reads it (it runs without the settings);
4. this PC registers with the bridge, or keeps the device it has there and the connectors bound to it;
5. the agent starts now and at every login, run by the extension's own Python (agent.agent_command)
   and marked so that it never installs releases itself: new versions come with the extension;
6. a one-time code, and the bridge's /connect page opened in the browser with it.

Also here: klas_status's web_connection, disconnect_app (list the connected apps, end one), and the
agent restart after an extension update. Nothing here prints: on the extension's stdio, stdout is the
MCP connection.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import webbrowser
from typing import Any
from urllib.parse import quote, urlparse

import httpx
import keyring
from keyring.errors import KeyringError

from . import agent, credentials, klas, release

log = logging.getLogger("kw_mcp.webconnect")

INVITE_ENV = "KW_CAMPUS_INVITE"
APPS_TIMEOUT_S = 4.0  # klas_status waits this long for the bridge's list of connected apps
RESTARTED_FILE = "extension-restarted"  # in agent.CONFIG_DIR: the version the agent was last restarted into
DEFAULT_CODE_S = 900  # the bridge's pairing codes last 15 minutes
SETTINGS = "Claude 설정 → 확장 → KW CAMPUS"
ASK_AGAIN = "다시 연결해 달라고 말해 주세요."
NEW_INVITE_STEPS = [
    "디스코드에서 '설치하기'를 눌러 초대 코드를 받아요.",
    f"{SETTINGS}의 초대 코드 칸에 넣어요.",
    ASK_AGAIN,
]
CODE_CAUTION = "코드는 남에게 보내지 마세요."
PAGE_OPENED = "브라우저에 연결 페이지를 열었어요. 안내대로 해 주세요."


class Failed(RuntimeError):
    """Linking stopped on something the student can't fix in the settings (network, keychain, clock,
    launchctl, the registry). The message says what didn't work and what to do."""


def invite() -> str:
    """The invite in the extension's settings, or "" (Claude Desktop passes an empty optional field
    through as the literal "${user_config.…}")."""
    value = (os.environ.get(INVITE_ENV) or "").strip()
    return "" if value.startswith("${") else value


async def check_login(creds: credentials.Credentials) -> None:
    """Log in to KLAS once. Raises what KLAS answered (KlasBadPassword, KlasLoginBlocked, ...) or an
    httpx error. A login KLAS already rejected on this PC is not sent again (the client's guard)."""
    async with klas.KlasClient(creds.login_id, creds.password, login_hint=credentials.login_hint(creds)) as client:
        await client.login()


def remember_login(creds: credentials.Credentials) -> bool:
    """Copy the extension's 학번·비밀번호 into the keychain, where the PC agent reads them (started at
    login, it has no extension settings). Only when missing or different; True if it saved."""
    if creds.source != credentials.ENV:
        return False
    saved_id = keyring.get_password(credentials.KEYRING_SERVICE, credentials.KEYRING_ID_KEY)
    if saved_id == creds.login_id and keyring.get_password(credentials.KEYRING_SERVICE, saved_id) == creds.password:
        return False
    credentials.save(creds.login_id, creds.password)
    credentials.mark_copied()  # disconnect_this_pc deletes this copy, never a login the student saved
    return True


def ensure_device(invite: str, *, relink: bool = False, expected_server: str | None = None) -> str | None:
    """Register this PC with the invite's bridge unless it is registered there already. Returns the
    connector (MCP) URL when it registered now; None when it kept its device, and with it the
    connectors bound to it.

    A device whose invite was withdrawn registers again with `invite`: its connectors stopped working
    anyway, and the bridge refuses a withdrawn invite. A wrong clock or a device key the bridge doesn't
    accept is raised, never answered with a re-registration (relink=True asks for one)."""
    server, _ = agent.official_invite(invite)
    if not relink:
        try:
            if agent.linked_to(server):
                return None
        except agent.InviteRevoked:
            pass
    _, mcp_url = agent.register(invite, expected_server)
    return mcp_url


def _pair(invite: str, mcp_url: str | None) -> tuple[dict[str, Any], str | None]:
    """A one-time code. A kept device whose invite was withdrawn registers again with `invite` first."""
    try:
        return agent.pair_code(), mcp_url
    except agent.InviteRevoked:
        if mcp_url is not None:  # registered a moment ago and refused already: nothing to retry
            raise
    _, mcp_url = agent.register(invite)
    return agent.pair_code(), mcp_url


def _friendly(e: BaseException) -> str:
    from . import friendly_error

    return friendly_error(e)


def _not_connected(message: str, steps: list[str], **why: Any) -> dict[str, Any]:
    return {"connected": False, **why, "message": message, "next": steps}


def _login_problem(e: BaseException) -> dict[str, Any]:
    why: dict[str, Any] = {"problem": "klas_login"}
    if isinstance(e, klas.KlasBadPassword):
        message, steps = "학번이나 비밀번호가 맞지 않아요.", [f"{SETTINGS}에서 다시 넣어요.", ASK_AGAIN]
    elif isinstance(e, klas.KlasClientRejected):
        message, steps = "KLAS가 KW CAMPUS 접속을 막았어요.", [f"{klas.REPORT_TO}."]
    elif isinstance(e, klas.KlasLoginBlocked):  # captcha count, 2FA, a password change, ...: the cause in detail
        message, steps = "KLAS가 추가 확인을 요구해요.", ["브라우저에서 KLAS에 한 번 로그인해 주세요.", ASK_AGAIN]
        why["detail"] = str(e)
    elif isinstance(e, httpx.HTTPError):
        message, steps = "KLAS에 연결하지 못했어요.", ["인터넷을 확인하고 VPN은 꺼 주세요.", ASK_AGAIN]
    else:  # maintenance, a hanging KLAS, our own request cap
        message, steps = "KLAS에 로그인하지 못했어요.", ["잠시 뒤 " + ASK_AGAIN]
    return _not_connected(message, steps, **why)


async def connect(relink: bool = False) -> dict[str, Any]:
    """Everything connect_other_devices does. Settings the student has to fill in, or KLAS refusing
    the login, come back as {"connected": False, "missing" or "problem", "message", "next"}; other
    failures raise Failed with a message to relay."""
    code = invite()
    if not code:
        return _not_connected("초대 코드가 없어요.", NEW_INVITE_STEPS, missing="invite")
    try:
        server, _ = agent.official_invite(code)
    except agent.ForeignBridge as e:  # a look-alike invite: nothing is sent anywhere
        return _not_connected(str(e), NEW_INVITE_STEPS[1:], problem="invite_refused")
    except ValueError:
        return _not_connected("초대 코드가 맞지 않아요.", NEW_INVITE_STEPS, missing="invite")
    if sys.platform != "darwin" and os.name != "nt":
        return _not_connected("웹·폰 연결은 macOS와 Windows에서만 돼요.", [], problem="unsupported_os")
    try:
        creds = await asyncio.to_thread(credentials.load)
    except credentials.MissingCredentials:
        return _not_connected("학번·비밀번호가 비어 있어요.", [f"{SETTINGS}에서 넣어요.", ASK_AGAIN],
                              missing="credentials")
    except KeyringError as e:
        raise Failed(_friendly(e)) from e
    try:
        await check_login(creds)
    except (klas.KlasError, httpx.HTTPError) as e:
        return _login_problem(e)
    try:
        await asyncio.to_thread(remember_login, creds)
    except KeyringError as e:
        raise Failed(_friendly(e)) from e
    return await asyncio.to_thread(_link_and_open, code, server, relink)


def _has_link() -> bool:
    try:
        agent.load_link()
    except agent.NotLinked:
        return False
    return True


def _minutes(seconds: Any) -> int:
    try:
        return max(1, int(seconds) // 60)
    except (TypeError, ValueError):
        return DEFAULT_CODE_S // 60


def _open_browser(url: str) -> bool:
    try:
        return bool(webbrowser.open(url))
    except (webbrowser.Error, OSError):  # no browser is fine: the link is in the answer
        return False


def _link_and_open(invite: str, server: str, relink: bool) -> dict[str, Any]:
    had_device = _has_link()
    try:
        agent.check_server_clock(server)
        mcp_url = ensure_device(invite, relink=relink, expected_server=release.bridge_origin())
        code, mcp_url = _pair(invite, mcp_url)
        text = code["code"]
        if not isinstance(text, str) or not text:
            raise ValueError("no pairing code")
    except agent.ForeignBridge as e:  # the invite was ours: the registration answer named another WebSocket
        raise Failed(f"{e} 계속되면 {klas.REPORT_TO}.") from e
    except agent.InviteRefused as e:
        return _not_connected(str(e), NEW_INVITE_STEPS, problem="invite_refused")
    except agent.InviteRevoked:  # a device registered a moment ago is refused too
        return _not_connected("이 초대 코드로는 연결이 안 돼요.", NEW_INVITE_STEPS, problem="invite_refused")
    except agent.DeviceRefused as e:  # the keychain's device key isn't the one the bridge registered
        return _not_connected(str(e), ["새로 등록하려면 '웹·폰 연결 새로 등록해 줘'라고 말해 주세요."],
                              problem="device_key_mismatch", can_relink=True)
    except agent.TooManyCodes as e:
        raise Failed(str(e)) from e
    except (agent.ClockSkew, agent.NotLinked, KeyringError, httpx.HTTPError) as e:
        raise Failed(_friendly(e)) from e
    except (ValueError, KeyError, TypeError) as e:  # an answer not in the bridge's format
        raise Failed(f"연결 서버 응답이 이상해요. 잠시 뒤 {ASK_AGAIN}") from e
    try:
        agent.install_autostart()
    except (subprocess.CalledProcessError, OSError, NotImplementedError) as e:
        detail = (f"{' '.join(map(str, e.cmd[:2]))}: {e.returncode}" if isinstance(e, subprocess.CalledProcessError)
                  else e.__class__.__name__)
        log.warning("could not install the agent's autostart (%s)", detail)
        raise Failed(f"자동 실행 등록이 안 됐어요. 잠시 뒤 {ASK_AGAIN}") from e
    page = f"{server}/connect"
    opened = _open_browser(f"{page}#{quote(text, safe='')}")
    kept = mcp_url is None
    out: dict[str, Any] = {"connected": True, "already_linked": kept, "browser_opened": opened,
                           "mcp_url": code.get("mcp_url") or mcp_url}
    # The page signs this browser in only when it reaches the bridge from this PC's address (not over
    # iCloud Private Relay or a VPN); then it asks for the code. With the browser open, the code goes to
    # a desktop notification rather than through the model, which shows it only when there is none.
    if opened and agent.notify("KW CAMPUS 연결 코드", f"자동 연결이 안 되면 이 코드를 넣어 주세요: {text}"):
        out.update(connect_url=page, next=[PAGE_OPENED, "자동 연결이 안 되면 알림에 뜬 코드를 넣어 주세요."])
    elif opened:
        out.update(connect_url=page, code=text, expires_in_minutes=_minutes(code.get("expires_in")),
                   next=[PAGE_OPENED, f"자동 연결이 안 되면 연결 코드 {text}를 넣어 주세요."], caution=CODE_CAUTION)
    else:  # Claude has to show it
        link = f"{page}#{quote(text, safe='')}"
        out.update(connect_url=link, code=text, expires_in_minutes=_minutes(code.get("expires_in")),
                   next=[f"{link} 을 열고 안내대로 해 주세요.", f"다른 기기에서는 연결 코드 {text}를 넣어요."],
                   caution=CODE_CAUTION)
    if kept:
        out["note"] = "이미 연결돼 있어요. 기존 커넥터는 그대로 쓰면 돼요."
    elif had_device:
        out["note"] = "새로 등록했어요. 기존 커넥터는 다시 연결해 주세요."
    return out


# --- klas_status -------------------------------------------------------------------------------

def _local_status() -> dict[str, Any]:
    try:
        link = agent.load_link()
    except agent.NotLinked:
        return {"linked": False, "next": f"웹·폰에서 쓰려면 {agent.ASK_TO_CONNECT}."}
    if link.server != release.bridge_origin() or link.ws_url != release.bridge_ws_url():
        return {"linked": False, "next": agent.FOREIGN_LINK}
    running = agent.agent_running()
    out: dict[str, Any] = {"linked": True, "server": urlparse(link.server).hostname,
                           "autostart_installed": agent.autostart_installed(), "agent_running": running,
                           "disconnect": "이 PC 연결을 끊으려면 '이 PC 연결 끊어 줘'라고 말해 주세요."}
    if not running:
        out["next"] = f"에이전트가 꺼져 있어요. {agent.ASK_TO_CONNECT}."
    try:
        configured = agent.official_invite(invite())[0] if invite() else None
    except ValueError:
        configured = None
    if configured and configured != link.server:
        out["note"] = f"초대 코드가 바뀌었어요. {agent.ASK_TO_CONNECT}."
    return out


def _app(grant: dict[str, Any]) -> dict[str, Any]:
    from . import _when  # KST "YYYY-MM-DD HH:MM", like `kw-mcp connections`

    host = grant.get("redirect_host") or ""
    # Named by its redirect host like the bridge's approval page; the app's self-chosen name is never shown.
    # The id is "" (None here) unless it is in the bridge's own format, so it can't be revoked by mistake.
    return {"app": agent._app_label(host), "host": host or None, "connected": _when(grant.get("created")),
            "last_used": _when(grant.get("last_used")) if grant.get("last_used") else "아직 없음",
            "id": grant.get("id") or None}


async def status(timeout: float = APPS_TIMEOUT_S) -> dict[str, Any]:
    """klas_status's web_connection: linked or not, the bridge's host, autostart, whether the agent
    runs on this PC, and the apps connected with this PC's codes. Never raises. Only the app list asks
    the bridge, and klas_status waits for it at most `timeout` seconds."""
    try:
        out = await asyncio.to_thread(_local_status)
    except Exception as e:  # noqa: BLE001 -- the status must always answer
        log.warning("could not read the web connection's state (%s)", e.__class__.__name__)
        return {"linked": None, "error": "웹·폰 연결 상태를 못 읽었어요."}
    if not out.get("linked"):
        return out
    try:
        rows = await asyncio.wait_for(asyncio.to_thread(agent.grants), timeout)
        out["connected_apps"] = [_app(g) for g in rows]
    except TimeoutError:
        out["connected_apps"] = None
        out["apps_note"] = "연결한 앱 목록을 못 가져왔어요."
    except (agent.NotLinked, agent.DeviceRefused, agent.ClockSkew, LookupError) as e:
        out["connected_apps"] = None
        out["apps_note"] = str(e)
    except Exception as e:  # noqa: BLE001 -- offline, keychain, a bridge error
        log.warning("could not list the connected apps (%s)", e.__class__.__name__)
        out["connected_apps"] = None
        out["apps_note"] = "연결한 앱 목록을 못 가져왔어요."
    return out


# --- disconnect_app ------------------------------------------------------------------------------

def disconnect(app_id: str | None = None) -> dict[str, Any]:
    """disconnect_app. Without app_id: the apps connected with this PC's codes. With one: end that one
    connection; this PC stays linked and the other apps stay connected. A wrong id raises ValueError or
    LookupError (their text says what to do); network, clock and keychain failures raise Failed."""
    wanted = (app_id or "").strip()
    try:
        rows = agent.grants()
    except agent.NotLinked as e:
        return {"linked": False, "apps": [], "message": str(e)}
    except LookupError:
        if not wanted:
            raise
        rows = []  # a bridge without the list can still end a connection by its id
    except (agent.DeviceRefused, agent.ClockSkew, KeyringError, httpx.HTTPError) as e:
        raise Failed(_friendly(e)) from e
    apps = [_app(g) for g in rows]
    if not wanted:
        if not apps:
            return {"linked": True, "apps": [], "message": "연결된 앱이 없어요."}
        return {"linked": True, "apps": apps, "next": "끊을 앱을 골라 주세요."}
    try:
        agent.revoke(wanted)
    except (agent.NotLinked, agent.DeviceRefused, agent.ClockSkew, KeyringError, httpx.HTTPError) as e:
        raise Failed(_friendly(e)) from e
    gone = next((a for a in apps if a["id"] == wanted), None)
    return {"disconnected": True, "id": wanted, "app": gone["app"] if gone else None,
            "message": f"{gone['app'] if gone else '그 앱'} 연결을 끊었어요.",
            "apps": [a for a in apps if a["id"] != wanted]}


# --- disconnect_this_pc -----------------------------------------------------------------------------

def disconnect_pc() -> dict[str, Any]:
    """disconnect_this_pc: forget this PC on the bridge (its connectors stop, its place on the invite is
    freed), remove the autostart and stop the agent, and delete the keychain login only if
    connect_other_devices copied it there. When the bridge won't hear from this device any more (a
    withdrawn invite, another device key), this PC is cleared all the same."""
    try:
        try:
            agent.unlink()  # removes the autostart first, so the agent stops answering either way
            linked = True
        except agent.NotLinked:
            linked = False
            if agent.autostart_installed():
                agent.uninstall_autostart()
        except agent.UnlinkFailed as e:
            if not e.refused:
                raise Failed(str(e)) from e
            agent.unlink(force=True)
            linked = True
        removed = credentials.delete_copy()
    except (agent.ClockSkew, KeyringError, httpx.HTTPError) as e:
        raise Failed(_friendly(e)) from e
    return {"disconnected": linked, "login_removed": removed,
            "message": "이 PC의 웹·폰 연결을 끊었어요." if linked else "이 PC는 연결돼 있지 않아요."}


# --- after an extension update -----------------------------------------------------------------------

def restart_outdated_agent() -> bool:
    """Run once in the background when the extension's MCP server starts. Claude Desktop replaced the
    extension's files under an agent it started earlier, which keeps running the old code: restart it
    into this version the way connect_other_devices started it. True if it restarted the agent.

    Only the extension's own agent (its autostart runs exactly this environment's command, with
    --from-extension), only when the running agent started as another version (it records its version
    at start; agents before that record none), and at most once per version: an agent that doesn't come
    up isn't restarted again at every start. Best effort: never raises."""
    try:
        return _restart_outdated_agent()
    except Exception:  # the MCP server runs on regardless (logged with the traceback)
        log.warning("could not check or restart the PC agent after an update", exc_info=True)
        return False


def _restart_outdated_agent() -> bool:
    if not agent.from_extension() or not _has_link() or not agent.autostart_runs_this_agent():
        return False
    version = agent.installed_version()
    if agent.load_state().get("version") == version or not agent.agent_running():
        return False
    marker = agent.CONFIG_DIR / RESTARTED_FILE
    try:
        if marker.read_text(encoding="utf-8").strip() == version:
            return False
    except OSError:
        pass
    marker.write_text(version, encoding="utf-8")  # before the restart: a failing one isn't retried
    agent.install_autostart()
    log.info("restarted the PC agent into %s", version)
    return True
