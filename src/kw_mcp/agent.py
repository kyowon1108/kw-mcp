"""PC agent for the KW Campus bridge: Claude/ChatGPT connectors read KLAS through this PC.

  kw-mcp link <invite>   once: register this PC (public key only) and start the agent at login
  kw-mcp agent           keep a WebSocket open to the bridge; when a connector asks, read KLAS with
                         the keychain login (logging in again when the session has expired),
                         encrypt the result with that request's one-time key and post it back

The KLAS id/password and the device's private key stay in the OS keychain. The bridge only
gets the device's public key and per-request ciphertext.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import logging.handlers
import os
import plistlib
import random
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO
from urllib.parse import urlencode, urlparse

import httpx
import keyring
import websockets
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from keyring.errors import KeyringError, PasswordDeleteError

from . import credentials, release

if TYPE_CHECKING:  # the KLAS layer is imported when first used, so a bug there can't stop the updater
    from .holder import KlasHolder

log = logging.getLogger("kw_mcp.agent")

CONFIG_DIR = Path.home() / ".config" / "kw-campus"
LINK_FILE = CONFIG_DIR / "agent.json"
KEYRING_DEVICE_KEY = "bridge_device_key"
INVITE_PREFIX = "kwc_"
APP_PING_S = 300  # API Gateway closes WebSocket connections that are idle for 10 minutes
MAX_BACKOFF_S = 60.0
STABLE_CONNECTION_S = 60.0  # a connection that lasted this long resets the reconnect backoff
DENIED_BACKOFF_S = 600.0  # the bridge refused this PC (unlinked, clock far off): don't hammer it
CLOCK_SKEW_LIMIT_S = 240  # the bridge refuses device signatures more than 300 s off
LEGACY_LOCK_PORT = 47811  # agents up to 0.9.0 held this localhost port instead of the lock file
LAUNCHD_LABEL = "kr.kwcampus.agent"
WINDOWS_RUN_VALUE = "KWCampusAgent"
# Sent on connect so the bridge knows which requests this agent understands.
# 1: "snapshot" only. 2: also "call" with an op from CALLS.
PROTOCOL_VERSION = 2
# Single-item reads the bridge may ask for: op -> argument names. Each op is a read-only
# KlasService method taking those arguments as strings ("id" and "file_index" may be left out).
CALLS: dict[str, tuple[str, ...]] = {
    "assignment_detail": ("course", "title", "id"),
    "syllabus": ("course",),
    "course_post": ("course", "title", "id"),
    "search_course_posts": ("course", "keyword"),
    "grades": (),
    "read_attachment": ("course", "title", "file_name", "part", "source", "id", "file_index"),
    "attendance": ("course",),
    "exam_info": ("course",),
    "class_changes": ("days",),
    "graduation_progress": (),
    "deadlines": ("days",),
    "online_tests": ("course",),
    "surveys": ("course",),
    "discussions": ("course",),
    "course_evaluation": (),
    "application_windows": (),
    "course_overview": ("course",),
}
# The bridge says "id"; the service names it after what it identifies. The service only accepts
# ids its own lists handed out.
ARG_NAMES: dict[str, dict[str, str]] = {
    "assignment_detail": {"id": "task_id"},
    "course_post": {"id": "post_id"},
    "read_attachment": {"id": "item_id"},
}
OPTIONAL_ARGS = frozenset({"id", "file_index"})  # None when not given, not ""
MAX_ARG_CHARS = 100
ATTACHMENT_WAIT_S = 17.0  # a big attachment keeps downloading; the answer says "ask again shortly"
MAX_RESULT_CHARS = 300_000  # same cap as the bridge's /device/result
ANSWER_DEADLINE_S = 18.0  # the bridge waits 22 s; answer "KLAS is slow" before it gives up
RESULT_POST_BUDGET_S = 16.0  # retry the result upload for about this long
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
# Self-update: check the bridge's signed latest.json soon after start, then every few hours.
UPDATE_FIRST_CHECK_S = 600
UPDATE_AFTER_CRASH_S = (30.0, 60.0)  # sooner when the last run ended abnormally or an update is on trial
UPDATE_INTERVAL_S = 6 * 3600
HEALTHY_AFTER_S = 120  # a new version that connected and ran this long is kept
MAX_FAILED_STARTS = 2  # a new version that crashed this many times is rolled back
SKIP_FAILED_UPDATE_S = 24 * 3600
RESTART_EXIT_CODE = 75  # non-zero, so launchd (KeepAlive SuccessfulExit=false) starts the new version
_GRANT_ID = re.compile(r"[A-Za-z0-9_-]{1,100}")


class NotLinked(RuntimeError):
    pass


class ClockSkew(RuntimeError):
    """The PC clock is so far off that the bridge refuses this PC's signatures."""

    def __init__(self, offset_s: float) -> None:
        self.offset_s = offset_s
        minutes = max(1, round(abs(offset_s) / 60))
        direction = "빠릅니다" if offset_s > 0 else "느립니다"
        super().__init__(f"이 PC 시계가 중계 서버보다 약 {minutes}분 {direction}. 날짜·시간 설정에서 "
                         "'자동으로 시간 설정'을 켜고 다시 실행하세요(기기를 다시 등록할 필요는 없습니다).")


class UnlinkFailed(RuntimeError):
    pass


class DeviceRefused(RuntimeError):
    """The bridge knows this device but won't accept its signature, or its invite was withdrawn."""


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _config(name: str) -> Path:
    return CONFIG_DIR / name


def _private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


# --- invite, link file, device key ---------------------------------------------------

def make_invite(server: str, token: str) -> str:
    return INVITE_PREFIX + b64u(json.dumps({"s": server.rstrip("/"), "t": token}, separators=(",", ":")).encode())


def parse_invite(invite: str) -> tuple[str, str]:
    invite = invite.strip()
    try:
        if not invite.startswith(INVITE_PREFIX):
            raise ValueError
        data = json.loads(b64u_decode(invite[len(INVITE_PREFIX):]))
        server, token = str(data["s"]).rstrip("/"), str(data["t"])
    except (ValueError, KeyError, TypeError):
        raise ValueError("초대 코드 형식이 아닙니다(kwc_로 시작하는 코드를 그대로 붙여 넣으세요).") from None
    parsed = urlparse(server)
    if not (parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"))) \
            or parsed.username or parsed.path not in ("", "/"):
        raise ValueError("초대 코드 안의 서버 주소가 올바르지 않습니다.")
    return server, token


@dataclass(frozen=True)
class Link:
    server: str
    ws_url: str
    uid: str


def save_link(link: Link) -> None:
    _private_dir(CONFIG_DIR)
    LINK_FILE.write_text(json.dumps(asdict(link), indent=2))
    LINK_FILE.chmod(0o600)


def load_link() -> Link:
    try:
        return Link(**json.loads(LINK_FILE.read_text()))
    except (OSError, ValueError, TypeError):
        raise NotLinked("이 PC가 아직 연결되지 않았습니다. `kw-mcp link <초대코드>`를 먼저 실행하세요.") from None


class DeviceKey:
    """ECDSA P-256 key; signatures are raw r||s like WebCrypto, which the bridge verifies."""

    def __init__(self, key: ec.EllipticCurvePrivateKey) -> None:
        self._key = key

    @classmethod
    def generate(cls) -> DeviceKey:
        return cls(ec.generate_private_key(ec.SECP256R1()))

    @classmethod
    def load(cls) -> DeviceKey:
        pem = keyring.get_password(credentials.KEYRING_SERVICE, KEYRING_DEVICE_KEY)
        if not pem:
            raise NotLinked("키체인에 기기 키가 없습니다. `kw-mcp link <초대코드>`를 다시 실행하세요.")
        key = serialization.load_pem_private_key(pem.encode(), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise NotLinked("키체인의 기기 키 형식이 올바르지 않습니다. `kw-mcp link`를 다시 실행하세요.")
        return cls(key)

    def save(self) -> None:
        pem = self._key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()).decode()
        keyring.set_password(credentials.KEYRING_SERVICE, KEYRING_DEVICE_KEY, pem)

    def public_jwk(self) -> dict[str, str]:
        nums = self._key.public_key().public_numbers()
        return {"kty": "EC", "crv": "P-256", "x": b64u(nums.x.to_bytes(32, "big")), "y": b64u(nums.y.to_bytes(32, "big"))}

    def sign(self, message: str) -> str:
        r, s = decode_dss_signature(self._key.sign(message.encode(), ec.ECDSA(hashes.SHA256())))
        return b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))

    def signed(self, uid: str, purpose: str) -> dict[str, str]:
        """Body for a signed device call: the signature covers `kw-<purpose>:<uid>:<ts>`."""
        ts = str(int(time.time()))
        return {"uid": uid, "ts": ts, "sig": self.sign(f"kw-{purpose}:{uid}:{ts}")}


def _delete_device_key() -> None:
    try:
        keyring.delete_password(credentials.KEYRING_SERVICE, KEYRING_DEVICE_KEY)
    except PasswordDeleteError:
        pass


# --- the PC clock -----------------------------------------------------------------------

def clock_offset(headers: Any) -> float | None:
    """Seconds this PC's clock is ahead of the server's, from an HTTP Date header."""
    value = headers.get("date") if headers is not None else None
    if not value:
        return None
    try:
        return time.time() - parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def check_clock(headers: Any) -> None:
    offset = clock_offset(headers)
    if offset is not None and abs(offset) > CLOCK_SKEW_LIMIT_S:
        raise ClockSkew(offset)


def check_server_clock(server: str) -> None:
    """Raise ClockSkew before anything is signed, so a wrong clock never looks like 'device unknown'."""
    check_clock(httpx.get(f"{server}/healthz", timeout=10).headers)


def _explain_refusal(server: str, response: httpx.Response) -> None:
    """A bridge without error codes refused a signed call (403): raise ClockSkew if the clock is why."""
    headers = response.headers
    if "date" not in headers:
        try:
            headers = httpx.get(f"{server}/healthz", timeout=10).headers
        except httpx.HTTPError:
            return
    check_clock(headers)


def _error_body(r: httpx.Response) -> dict[str, Any]:
    try:
        body = r.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


_NOT_LINKED = "중계 서버가 이 PC를 알아보지 못했습니다. `kw-mcp link <초대코드>`를 다시 실행하세요."


def _raise_refusal(server: str, r: httpx.Response) -> None:
    """Turn the bridge's refusal of a signed call into the matching error. Only unknown_device means
    "register again"; a stale clock or a bad signature must never lead to a re-registration."""
    body = _error_body(r)
    code = str(body.get("error", ""))
    if r.status_code == 401 and code == "stale_timestamp":
        try:
            offset = time.time() - float(body["server_time"])
        except (KeyError, TypeError, ValueError):
            offset = clock_offset(r.headers) or CLOCK_SKEW_LIMIT_S + 1
        raise ClockSkew(offset)
    if r.status_code != 403:
        return
    if code == "invite_revoked":
        raise DeviceRefused("이 PC를 연결한 초대가 철회돼 새 연결 코드를 받을 수 없습니다. 초대해 준 사람에게 새 초대를 받으세요.")
    if code == "bad_signature":
        raise DeviceRefused("중계 서버가 이 PC의 서명을 받아들이지 않습니다(키체인의 기기 키가 등록한 것과 다릅니다). "
                            "`kw-mcp link <초대코드> --relink`로 다시 등록하세요(기존 커넥터는 다시 연결해야 합니다).")
    if code != "unknown_device":  # an older bridge: one 403 for every cause, so look at the clock
        _explain_refusal(server, r)
    raise NotLinked(_NOT_LINKED)


# --- talking to the bridge (one-off calls) ----------------------------------------------

def register(invite: str, expected_server: str | None = None) -> tuple[Link, str]:
    """Register this PC with a fresh key. Returns the link and the connector (MCP) URL.

    The installer passes the server it was downloaded from as expected_server, so a doctored
    invite can't point this PC at someone else's bridge.
    """
    server, token = parse_invite(invite)
    if expected_server and server != expected_server.rstrip("/"):
        raise ValueError(f"초대 코드의 서버({server})가 설치한 곳({expected_server})과 다릅니다. 받은 링크를 다시 확인하세요.")
    key = DeviceKey.generate()
    # Register first: if the network or the bridge fails here, the current link stays as it was.
    r = httpx.post(f"{server}/device/register", json={"invite": token, "public_key": key.public_jwk()}, timeout=20)
    if r.status_code == 403:
        raise ValueError("초대 코드가 유효하지 않습니다. 받은 코드를 다시 확인하세요.")
    r.raise_for_status()
    data = r.json()
    _forget_previous_device()
    key.save()
    link = Link(server=server, ws_url=data["ws_url"], uid=data["uid"])
    save_link(link)
    return link, data["mcp_url"]


def _forget_previous_device() -> None:
    """Best effort: ask the bridge to drop this PC's previous device after a new one registered."""
    try:
        old, old_key = load_link(), DeviceKey.load()
        r = httpx.post(f"{old.server}/device/unlink", json=old_key.signed(old.uid, "unlink"), timeout=20)
        if r.status_code != 200:
            log.warning("the bridge kept the previous device record (HTTP %s)", r.status_code)
    except (NotLinked, httpx.HTTPError, KeyringError, ValueError):
        pass


def _device_call(path: str, purpose: str, **extra: str) -> httpx.Response:
    """POST a signed device request. Refusals raise ClockSkew, NotLinked or DeviceRefused; any other
    answer is returned for the caller to read."""
    link, key = load_link(), DeviceKey.load()
    for attempt in range(2):
        r = httpx.post(f"{link.server}/device/{path}", json={**key.signed(link.uid, purpose), **extra}, timeout=20)
        if r.status_code == 409 and _error_body(r).get("error") == "replayed" and attempt == 0:
            time.sleep(1)  # a fresh ts and signature
            continue
        break
    _raise_refusal(link.server, r)
    return r


def linked_to(server: str) -> bool:
    """True if this PC is already registered with `server` and the bridge still knows it.

    Only "not linked here" or "the bridge doesn't know this device" (unknown_device) count as
    False. A network error, a wrong PC clock or a refused signature is raised, so none of them ever
    triggers a re-registration (which would orphan the Claude/ChatGPT connections bound to this device).
    """
    try:
        link = load_link()
        if link.server != server.rstrip("/"):
            return False
        try:
            grants()  # a signed request that creates nothing
        except LookupError:  # a bridge without /device/grants: the pairing call checks the device as well
            pair_code()
        return True
    except NotLinked:
        return False


def pair_code() -> dict[str, Any]:
    """A one-time code (15 minutes) to type on the connector's approval page."""
    r = _device_call("pair", "pair")
    r.raise_for_status()
    return r.json()


def _text(value: Any, limit: int = 100) -> str:
    """Bridge-supplied text (an app's self-chosen name) for a terminal or a notification."""
    return "".join(c for c in str(value if value is not None else "") if c.isprintable())[:limit]


def grants() -> list[dict[str, Any]]:
    """The apps (Claude, ChatGPT, ...) connected to this PC with its codes."""
    r = _device_call("grants", "grants")
    if r.status_code == 404:
        raise LookupError("중계 서버가 아직 연결 목록을 지원하지 않습니다.")
    r.raise_for_status()
    rows = r.json().get("grants")
    if not isinstance(rows, list):
        raise LookupError("중계 서버의 연결 목록 형식이 예상과 다릅니다.")  # noqa: TRY004 -- callers treat it as "no list"
    return [{"id": _text(g.get("id")), "client": _text(g.get("client")), "redirect_host": _text(g.get("redirect_host")),
             "created": g.get("created"), "last_used": g.get("last_used"), "expires": g.get("expires")}
            for g in rows if isinstance(g, dict)]


def revoke(grant_id: str) -> None:
    """Disconnect one app; this PC and the other apps stay connected."""
    grant_id = grant_id.strip()
    if not _GRANT_ID.fullmatch(grant_id):
        raise ValueError("연결 ID 형식이 아닙니다. `kw-mcp connections`에 나온 ID를 그대로 넣으세요.")
    r = _device_call("revoke", f"revoke:{grant_id}", grant_id=grant_id)
    if r.status_code == 404:
        raise LookupError(f"'{grant_id}' 연결이 없습니다. `kw-mcp connections`로 ID를 확인하세요.")
    r.raise_for_status()
    if r.json().get("ok") is not True:
        raise LookupError("중계 서버가 연결을 끊었다고 확인하지 않았습니다. 잠시 뒤 다시 실행하세요.")


def unlink(*, force: bool = False) -> None:
    """Forget this PC on the bridge (its connectors stop working) and remove local state.

    The device key is deleted only after the bridge confirms, or when it no longer knows the
    device: without the key the record could never be removed. force=True skips the bridge.
    """
    load_link()
    uninstall_autostart()  # the PC stops answering either way
    if not force:
        keep = "다시 시도할 수 있게 이 PC의 키는 남겨 두었습니다."
        try:
            r = _device_call("unlink", "unlink")  # ClockSkew keeps the key: fix the clock, then retry
        except NotLinked:
            r = None  # the bridge no longer knows this device (or there is no key): only local state is left
        except DeviceRefused as e:
            raise UnlinkFailed(f"{e} 이 PC의 설정만 지우려면 `kw-mcp unlink --force`.") from None
        except httpx.HTTPError as e:
            raise UnlinkFailed(f"중계 서버에 연결하지 못해 서버의 기기 기록을 지우지 못했습니다({e.__class__.__name__}). "
                               f"인터넷을 확인하고 `kw-mcp unlink`를 다시 실행하세요. {keep}") from None
        if r is not None and (r.status_code != 200 or not _confirmed(r)):
            raise UnlinkFailed(f"중계 서버가 기기 기록을 지웠다고 확인하지 않았습니다(HTTP {r.status_code}). "
                               f"잠시 뒤 `kw-mcp unlink`를 다시 실행하세요. {keep}")
    _delete_device_key()
    LINK_FILE.unlink(missing_ok=True)


def _confirmed(r: httpx.Response) -> bool:
    try:
        return r.json().get("ok") is True
    except (ValueError, AttributeError):
        return False


# --- answering requests -------------------------------------------------------------

_background: set[asyncio.Task[Any]] = set()


def _keep_running(task: asyncio.Task[Any]) -> None:
    """Let a read finish after its answer went out (it warms the cache for the retry)."""
    _background.add(task)
    task.add_done_callback(_background.discard)
    task.add_done_callback(lambda t: t.cancelled() or t.exception())  # retrieved: no "never retrieved" warning


def call_args(op: str, args: dict[str, Any] | None) -> dict[str, str | None]:
    """The bridge's arguments for `op`, cut to size and renamed to the service's parameter names."""
    renamed, out = ARG_NAMES.get(op, {}), {}
    for name in CALLS[op]:
        value = str((args or {}).get(name) or "")[:MAX_ARG_CHARS]
        out[renamed.get(name, name)] = None if name in OPTIONAL_ARGS and not value else value
    return out


async def build_result(klas: KlasHolder, op: str | None = None, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """The snapshot (op None) or one CALLS read, as a dict the bridge decrypts; errors as {"error": code}."""
    from .klas import (
        KlasError,
        KlasLoginBlocked,
        KlasLoginError,
        KlasRequestLimit,
        KlasUnavailable,
    )

    try:
        service = await klas.service()
        if op is None:
            return await service.snapshot()
        if op not in CALLS or not hasattr(service, op):
            return {"error": "unsupported", "message": f"이 에이전트는 '{op}' 요청을 모릅니다."}
        read = getattr(service, op)(**call_args(op, args))
        if op != "read_attachment":
            return {"result": await read}
        task = asyncio.ensure_future(read)
        try:
            return {"result": await asyncio.wait_for(asyncio.shield(task), ATTACHMENT_WAIT_S)}
        except TimeoutError:
            _keep_running(task)
            return {"result": {"pending": True, "message": "첨부 파일을 아직 받아 읽는 중입니다. 잠시 뒤 같은 요청을 다시 하세요."}}
    except LookupError as e:
        return {"error": "not_found", "message": str(e)}
    except (credentials.MissingCredentials, KeyringError) as e:
        return {"error": "klas_login_required", "message": str(e)}
    except KlasLoginBlocked as e:
        return {"error": "klas_blocked", "message": str(e)}
    except KlasLoginError as e:
        return {"error": "klas_login_required", "message": str(e)}
    except (KlasUnavailable, KlasRequestLimit) as e:  # maintenance, or our own request cap: say when to retry
        return {"error": "klas_error", "message": str(e)}
    except (KlasError, httpx.HTTPError) as e:
        log.warning("KLAS read failed: %s", e.__class__.__name__)
        return {"error": "klas_error"}
    except Exception:  # always answer: otherwise the connector waits out its timeout and blames sleep
        log.exception("unexpected error while answering %s", op or "snapshot")
        return {"error": "klas_error", "message": "PC 에이전트에서 예상하지 못한 오류가 났습니다."}


def encrypt_result(key: bytes, request_id: str, data: dict[str, Any]) -> dict[str, str]:
    """AES-256-GCM with the request id as associated data (the bridge checks both)."""
    iv = os.urandom(12)
    # default=str and errors="replace": a stray date or an unpaired surrogate from a document
    # still produces an answer instead of an exception and a timeout.
    plain = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8", "replace")
    ct = AESGCM(key).encrypt(iv, plain, request_id.encode())
    return {"request_id": request_id, "iv": b64u(iv), "ct": b64u(ct)}


async def _post_result(http: httpx.AsyncClient, url: str, body: dict[str, str]) -> str:
    """Upload the answer, retrying network errors, 429 and 5xx with jittered backoff for a few seconds."""
    deadline = time.monotonic() + RESULT_POST_BUDGET_S
    delay = 0.5
    while True:
        remaining = deadline - time.monotonic()
        try:
            r = await http.post(url, json=body, timeout=max(1.0, min(10.0, remaining)))
            outcome = f"HTTP {r.status_code}"
            if r.status_code not in RETRY_STATUSES:
                return outcome
        except httpx.HTTPError as e:
            outcome = e.__class__.__name__
        wait = delay * random.uniform(0.5, 1.5)
        if time.monotonic() + wait >= deadline:
            return outcome
        await asyncio.sleep(wait)
        delay = min(delay * 2, 4.0)


async def answer(klas: KlasHolder, link: Link, message: dict[str, Any], http: httpx.AsyncClient) -> None:
    request_id, result_url = str(message.get("request_id", "")), str(message.get("result_url", ""))
    if not request_id or result_url != f"{link.server}/device/result":
        log.warning("ignored a request with an unexpected result address")
        return
    try:
        key = b64u_decode(str(message.get("key", "")))
        if len(key) != 32:
            raise ValueError
    except ValueError:
        log.warning("ignored a request without a valid key")
        return
    started = time.monotonic()
    op = str(message.get("op") or "") if message.get("type") == "call" else None
    args = message.get("args") if isinstance(message.get("args"), dict) else None
    try:
        async with asyncio.timeout(ANSWER_DEADLINE_S):
            data = await build_result(klas, op, args)
    except TimeoutError:
        # The reads keep going in the background (the service shares them), so a retry is faster.
        data = {"error": "klas_slow", "message": "KLAS 응답이 느립니다. 잠시 뒤 다시 물어보세요."}
    try:
        body = encrypt_result(key, request_id, data)
    except Exception:  # never leave the connector waiting
        log.exception("could not encode the answer to %s", op or "snapshot")
        data = {"error": "klas_error", "message": "PC 에이전트가 결과를 보내지 못했습니다. 잠시 뒤 다시 물어보세요."}
        body = encrypt_result(key, request_id, data)
    if len(body["ct"]) > MAX_RESULT_CHARS:  # the bridge would refuse it; say why instead of timing out
        data = {"error": "too_large", "message": "결과가 너무 큽니다. 과목이나 기간을 좁혀서 다시 물어보세요."}
        body = encrypt_result(key, request_id, data)
    outcome = await _post_result(http, result_url, body)
    log.info("answered a %s request in %.1fs (%s, %s)", op or "snapshot", time.monotonic() - started,
             data.get("error", "ok"), outcome)


# --- desktop notification -----------------------------------------------------------------

def _powershell() -> str:
    return str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")


_BALLOON = ("Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; "
            "$n = New-Object System.Windows.Forms.NotifyIcon; $n.Icon = [System.Drawing.SystemIcons]::Information; "
            "$n.BalloonTipTitle = $env:KW_NOTIFY_TITLE; $n.BalloonTipText = $env:KW_NOTIFY_TEXT; $n.Visible = $true; "
            "$n.ShowBalloonTip(15000); Start-Sleep -Seconds 16; $n.Dispose()")


def notify(title: str, text: str) -> None:
    """Best-effort desktop notification. The text comes from the bridge, so it is passed as data
    (argv, environment), never pasted into a script."""
    title, text = _text(title, 60), _text(text, 240)
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["osascript", "-e", "on run argv", "-e",
                              "display notification (item 2 of argv) with title (item 1 of argv)", "-e", "end run",
                              title, text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif os.name == "nt":
            script = base64.b64encode(_BALLOON.encode("utf-16-le")).decode()
            subprocess.Popen([_powershell(), "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                              "-EncodedCommand", script], env={**os.environ, "KW_NOTIFY_TITLE": title, "KW_NOTIFY_TEXT": text},
                             creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif shutil.which("notify-send"):
            subprocess.Popen(["notify-send", title, text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        log.warning("could not show a notification (%s)", e.__class__.__name__)


def _paired(message: dict[str, Any]) -> None:
    """A code from this PC was just used: say so on screen, so a leaked code doesn't go unnoticed."""
    app = _text(message.get("app") or message.get("client_name"), 60) or "이름 없는 앱"
    host, grant = _text(message.get("redirect_host")), _text(message.get("grant_id"))
    log.info("a new app was connected with this PC's code: %s (%s, %s)", app, host, grant)
    notify("KW Campus", f"새 연결: {app}" + (f" ({host})" if host and host not in app else "")
           + f". 내가 연결한 게 아니면 `kw-mcp revoke {grant or '<ID>'}`로 끊으세요.")


# --- the long-running agent -------------------------------------------------------------

def _connect_url(link: Link, key: DeviceKey) -> str:
    # The signature covers the protocol version too, so nobody can replay it with another v.
    ts = str(int(time.time()))
    sig = key.sign(f"kw-connect:{link.uid}:{ts}:{PROTOCOL_VERSION}")
    return f"{link.ws_url}?{urlencode({'uid': link.uid, 'ts': ts, 'sig': sig, 'v': PROTOCOL_VERSION})}"


async def _serve(ws: Any, klas: KlasHolder, link: Link, http: httpx.AsyncClient) -> None:
    tasks: set[asyncio.Task[None]] = set()

    async def keep_alive() -> None:
        while True:
            await asyncio.sleep(APP_PING_S)
            await ws.send('{"action":"ping"}')

    async def safe_answer(message: dict[str, Any]) -> None:
        try:
            await answer(klas, link, message, http)
        except Exception:  # one bad request must not take the agent down
            log.exception("failed to answer a request")

    pinger = asyncio.create_task(keep_alive())
    try:
        async for raw in ws:
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            if isinstance(message, dict) and message.get("type") == "paired":
                _paired(message)
            elif isinstance(message, dict) and message.get("type") in ("snapshot", "call"):
                task = asyncio.create_task(safe_answer(message))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
    finally:
        pinger.cancel()


def _backoff_sleep(backoff: float) -> float:
    """Half fixed, half random: agents that lost the bridge together don't come back in lockstep."""
    return backoff / 2 + random.uniform(0, backoff / 2)


async def _refused(http: httpx.AsyncClient, link: Link, headers: Any) -> None:
    offset = clock_offset(headers)
    if offset is None:
        try:
            offset = clock_offset((await http.get(f"{link.server}/healthz")).headers)
        except httpx.HTTPError:
            offset = None
    if offset is not None and abs(offset) > CLOCK_SKEW_LIMIT_S:
        log.error("the bridge refused this PC: its clock is %d minutes %s the server's. Turn on automatic time "
                  "sync; the agent retries on its own", round(abs(offset) / 60), "ahead of" if offset > 0 else "behind")
    else:
        log.error("the bridge refused this PC. If it was unlinked, run `kw-mcp link` again")


async def run_forever(connected: asyncio.Event | None = None) -> None:
    from .holder import KlasHolder

    link, key = load_link(), DeviceKey.load()
    klas = KlasHolder()
    backoff = 1.0
    async with httpx.AsyncClient(timeout=20) as http:
        try:
            while True:
                opened: float | None = None
                try:
                    async with websockets.connect(_connect_url(link, key), open_timeout=20, ping_interval=30,
                                                  ping_timeout=20, max_size=2**20) as ws:
                        opened = time.monotonic()
                        log.info("connected to the bridge")
                        if connected is not None:
                            connected.set()
                        await _serve(ws, klas, link, http)
                    log.info("bridge closed the connection")
                except websockets.InvalidStatus as e:
                    status = e.response.status_code
                    if status in (401, 403):
                        await _refused(http, link, e.response.headers)
                        await asyncio.sleep(DENIED_BACKOFF_S * random.uniform(0.8, 1.2))
                        continue
                    log.warning("bridge answered HTTP %s", status)
                except (OSError, TimeoutError, websockets.WebSocketException) as e:
                    log.warning("connection lost (%s)", e.__class__.__name__)
                except Exception:  # keep running whatever happens; this is a background service
                    log.exception("unexpected error in the connection loop")
                # Only a connection that held for a while proves the bridge is back. One that is
                # accepted and closed at once keeps backing off.
                if opened is not None and time.monotonic() - opened >= STABLE_CONNECTION_S:
                    backoff = 1.0
                await asyncio.sleep(_backoff_sleep(backoff))
                backoff = min(backoff * 2, MAX_BACKOFF_S)
        finally:
            await klas.aclose()


# --- self-update -----------------------------------------------------------------------
#
# The agent installs only releases signed by the release key (release.py): the wheel, and the
# dependency pins (constraints exported from uv.lock), so nothing untested comes from PyPI.
# Before restarting it checks that the new version imports and reports its version, and keeps
# the version it replaced in CONFIG_DIR/releases. A new version that then fails to start twice
# is replaced by that one again. Versions that failed are skipped, so it never loops.

def installed_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("kw-mcp")
    except PackageNotFoundError:
        return "0"


def remember_uv() -> str | None:
    """Record the uv the installer used: launchd and the Run key start us with a bare PATH."""
    uv = shutil.which("uv")
    if uv:
        _private_dir(CONFIG_DIR)
        _config("uv-path").write_text(str(Path(uv).absolute()), encoding="utf-8")  # not resolved: Homebrew's Cellar path changes
    return uv


def uv_candidates() -> list[Path]:
    exe = "uv.exe" if os.name == "nt" else "uv"
    home = Path.home()
    found: list[Path] = []
    try:
        recorded = _config("uv-path").read_text(encoding="utf-8").strip()
        if recorded:
            found.append(Path(recorded))
    except OSError:
        pass
    if which := shutil.which("uv"):
        found.append(Path(which))
    found += [Path(os.environ[v]) / exe for v in ("UV_INSTALL_DIR", "XDG_BIN_HOME") if os.environ.get(v)]
    found += [home / ".local" / "bin" / exe, home / ".cargo" / "bin" / exe]
    if os.name == "nt":
        if os.environ.get("LOCALAPPDATA"):
            found.append(Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WinGet" / "Links" / exe)
        found.append(home / "scoop" / "shims" / exe)
    else:  # Homebrew (Apple Silicon, Intel), MacPorts
        found += [Path("/opt/homebrew/bin/uv"), Path("/usr/local/bin/uv"), Path("/opt/local/bin/uv")]
    return found


def find_uv() -> str | None:
    for candidate in uv_candidates():
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def in_uv_tool() -> bool:
    """Updates replace the uv tool environment. Run from anywhere else (a dev checkout), they
    would install into the tool and restart into the same old code every few minutes."""
    return (Path(sys.prefix) / "uv-receipt.toml").is_file()


def _tool_python() -> Path:
    return Path(sys.prefix) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _uv_env() -> dict[str, str]:
    # launchd drops XDG_DATA_HOME / UV_TOOL_DIR: point uv at the tool directory we run from.
    return {**os.environ, "UV_TOOL_DIR": str(Path(sys.prefix).parent)}


def install_argv(uv: str, wheel: Path, constraints: Path) -> list[str]:
    """`uv tool install` of a release, with every dependency pinned by its constraints file,
    nothing uploaded after the release, and no source builds."""
    argv = [uv, "tool", "install", "--force", "--quiet", "--python", "3.13", "--no-build",
            "--constraints", str(constraints.resolve())]
    if cutoff := release.exclude_newer(constraints.read_text(encoding="utf-8")):
        argv += ["--exclude-newer", cutoff]
    return [*argv, f"kw-mcp @ {wheel.resolve().as_uri()}"]  # a file:// URI needs an absolute path


def self_test_argv(python: Path | str, version: str) -> list[str]:
    """Imports every module and fails unless the installed version is `version`."""
    return [str(python), "-I", "-m", "kw_mcp", "--version", "--expect", version]


def releases_dir() -> Path:
    return _config("releases")


def release_files(version: str) -> tuple[Path, Path] | None:
    """The saved wheel and pins of `version`, if this PC still has them."""
    wheel = releases_dir() / f"kw_mcp-{version}-py3-none-any.whl"
    pins = releases_dir() / release.constraints_name(version)
    return (wheel, pins) if wheel.is_file() and pins.is_file() else None


def _keep_release(manifest: dict[str, Any], wheel: bytes, pins: bytes) -> tuple[Path, Path]:
    folder = _private_dir(releases_dir())
    paths = folder / manifest["wheel"], folder / manifest["constraints"]["file"]
    for path, data in zip(paths, (wheel, pins), strict=True):
        partial = path.with_name(path.name + ".part")
        partial.write_bytes(data)
        partial.replace(path)
    return paths


def prune_releases(keep: set[str]) -> None:
    """Delete saved releases except the given versions."""
    names = {f"kw_mcp-{v}-py3-none-any.whl" for v in keep} | {release.constraints_name(v) for v in keep}
    for path in releases_dir().glob("kw_mcp-*"):
        if path.name not in names:
            path.unlink(missing_ok=True)


def load_state() -> dict[str, Any]:
    try:
        state = json.loads(_config("agent-state.json").read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state: dict[str, Any]) -> None:
    path = _private_dir(CONFIG_DIR) / "agent-state.json"
    partial = path.with_name(path.name + ".part")
    partial.write_text(json.dumps(state, indent=2), encoding="utf-8")
    partial.replace(path)


def skip_version(version: str, seconds: float | None) -> None:
    """Don't offer `version` again (for `seconds`, or until a newer one exists when None)."""
    state = load_state()
    state.setdefault("skip", {})[version] = 0 if seconds is None else int(time.time() + seconds)
    save_state(state)


def skipped(version: str) -> bool:
    until = load_state().get("skip", {}).get(version)
    return until is not None and (until == 0 or until > time.time())


async def fetch_update(http: httpx.AsyncClient, server: str) -> tuple[dict[str, Any], Path, Path] | None:
    """Download a newer release if the bridge offers one signed by the release key, wheel and pins.
    Returns its manifest and the saved wheel and constraints (in releases_dir())."""
    r = await http.get(f"{server}/dist/latest.json")
    if r.status_code != 200:
        return None
    manifest = r.json()
    if not release.verify(manifest):
        log.warning("ignored an update whose signature does not match the release key")
        return None
    if not release.verify_constraints(manifest):
        log.warning("ignored an update without signed dependency pins")
        return None
    version = manifest["version"]
    if release.version_tuple(version) <= release.version_tuple(installed_version()):
        return None
    if skipped(version):
        log.info("skipping %s: it failed to install or start on this PC", version)
        return None
    downloads = []
    for name, sha256 in ((manifest["wheel"], manifest["sha256"]),
                         (manifest["constraints"]["file"], manifest["constraints"]["sha256"])):
        got = await http.get(f"{server}/dist/{name}")
        if got.status_code != 200 or hashlib.sha256(got.content).hexdigest() != sha256:
            log.warning("ignored an update whose download does not match the signed hash")
            return None
        downloads.append(got.content)
    return manifest, *_keep_release(manifest, *downloads)


def _quote(argv: list[str]) -> str:
    # Every token quoted: inside quotes cmd.exe takes & ^ ( ) | < > literally ("Tom&Jerry"'s profile).
    # Windows paths and our arguments never contain a double quote.
    return " ".join(f'"{a}"' for a in argv)


def windows_update_command(shell: str, *, pid: int, install: list[str], check: list[str],
                           rollback: list[str] | None, log_file: Path, restart: list[str]) -> str:
    """One command line for CreateProcess, as is. A list would be re-quoted with \\" escapes that
    cmd.exe doesn't understand; /s /c "..." runs the inner line verbatim.

    Waits until the agent (pid) has exited, installs, runs the self-test, puts the previous version
    back if either fails, and starts the agent again. `timeout` needs a console and fails at once in
    a windowless process, so PowerShell's Wait-Process does the waiting."""
    out = f'>> "{log_file}" 2>&1'
    wait = (f'"{_powershell()}" -NoProfile -NonInteractive -Command "Wait-Process -Id {int(pid)} -Timeout 120 '
            f'-ErrorAction SilentlyContinue" & ping -n 3 127.0.0.1 >nul')
    undo = f"{_quote(rollback)} {out}" if rollback else f"echo update failed; no saved previous version {out}"
    steps = f"{wait} & ({_quote(install)} {out} && {_quote(check)} {out} || {undo}) & {_quote(restart)}"
    return f'"{shell}" /s /c "{steps}"'


def _run_uv(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=900, env=_uv_env(), check=False)


def self_test(python: Path | str, version: str) -> bool:
    try:
        done = subprocess.run(self_test_argv(python, version), capture_output=True, text=True, timeout=180,
                              cwd=str(Path.home()), check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("the self-test of %s did not run (%s)", version, e.__class__.__name__)
        return False
    if done.returncode != 0:
        log.warning("the self-test of %s failed: %s", version, (done.stderr or done.stdout).strip()[-300:])
    return done.returncode == 0


def _spawn_windows(command: str) -> None:
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    subprocess.Popen(command, creationflags=flags, close_fds=True, env=_uv_env())


def _windows_swap(uv: str, files: tuple[Path, Path], version: str, back: tuple[Path, Path] | None) -> None:
    """Windows can't replace the interpreter that is running us: a detached shell waits for us to
    exit, installs, then starts the agent again."""
    _spawn_windows(windows_update_command(
        os.environ.get("ComSpec", "cmd.exe"), pid=os.getpid(), install=install_argv(uv, *files),
        check=self_test_argv(_tool_python(), version), rollback=install_argv(uv, *back) if back else None,
        log_file=default_log_file().with_name("update.log"), restart=[*agent_command(), "--replace"]))


def install_update(wheel: Path, constraints: Path, version: str) -> bool:
    """Install a verified release. True means: exit now so the new version starts."""
    uv = find_uv()
    if not uv:
        log.warning("uv not found; skipping the update (run `kw-mcp link` again from a terminal to record it)")
        return False
    if not in_uv_tool():
        log.warning("not running from a uv tool install (%s); skipping the update", sys.prefix)
        return False
    previous = installed_version()
    back = release_files(previous)
    state = load_state()
    state["pending"] = {"version": version, "previous": previous, "failures": 0, "at": int(time.time())}
    if os.name == "nt":
        save_state(state)  # the next start checks whether the install took
        _windows_swap(uv, (wheel, constraints), version, back)
        return True
    done = _run_uv(install_argv(uv, wheel, constraints))
    if done.returncode != 0:
        log.warning("installing %s failed: %s", version, done.stderr.strip()[-300:])
        skip_version(version, SKIP_FAILED_UPDATE_S)
        return False
    if not self_test(_tool_python(), version):
        log.error("%s does not start; going back to %s", version, previous)
        skip_version(version, None)
        if back is None:
            log.error("no saved copy of %s to go back to; run the install command from the setup page", previous)
        elif _run_uv(install_argv(uv, *back)).returncode != 0:
            log.error("reinstalling %s failed as well; run the install command from the setup page", previous)
        return False
    save_state(state)
    return True


def roll_back(pending: dict[str, Any]) -> bool:
    """Put back the version that ran before an update that keeps failing. True: exit now."""
    bad, previous = str(pending.get("version")), str(pending.get("previous"))
    skip_version(bad, None)
    back, uv = release_files(previous), find_uv()
    if back is None or uv is None:
        log.error("%s keeps failing, but %s can't be reinstalled (%s)", bad, previous,
                  "no saved copy" if back is None else "uv not found")
        return False
    log.error("%s failed to start %d times; going back to %s", bad, MAX_FAILED_STARTS, previous)
    if os.name == "nt":
        _windows_swap(uv, back, previous, None)
        return True
    done = _run_uv(install_argv(uv, *back))
    if done.returncode != 0 or not self_test(_tool_python(), previous):
        log.error("going back to %s failed: %s", previous, done.stderr.strip()[-300:])
        return False
    return True


def note_start(replaced: bool = False) -> tuple[bool, dict[str, Any] | None]:
    """Record that the agent started. Returns (the previous run ended abnormally, the pending update
    to roll back now). A start after a crash counts against a version that is still on trial."""
    state = load_state()
    crashed = bool(state.get("running")) and not replaced
    state.update(running=True, pid=os.getpid(), started=int(time.time()))
    pending, rollback = state.get("pending"), None
    if isinstance(pending, dict):
        if release.version_tuple(installed_version()) != release.version_tuple(str(pending.get("version"))):
            log.warning("the update to %s did not install; trying again in a day at the earliest", pending.get("version"))
            state.setdefault("skip", {})[str(pending.get("version"))] = int(time.time() + SKIP_FAILED_UPDATE_S)
            state.pop("pending")
        elif crashed:
            pending["failures"] = int(pending.get("failures", 0)) + 1
            if pending["failures"] >= MAX_FAILED_STARTS:
                rollback = state.pop("pending")
    save_state(state)
    return crashed, rollback


def note_stop() -> None:
    state = load_state()
    state["running"] = False
    save_state(state)


async def _keep_if_healthy(connected: asyncio.Event, started: float) -> None:
    """A version that reached the bridge and stayed up is kept; older saved releases go."""
    await connected.wait()
    await asyncio.sleep(max(0.0, HEALTHY_AFTER_S - (time.monotonic() - started)))
    state = load_state()
    if pending := state.pop("pending", None):
        log.info("version %s is running fine", pending.get("version"))
        save_state(state)
    prune_releases({installed_version()})  # the rollback target for the next update


async def update_once(http: httpx.AsyncClient, server: str) -> str | None:
    """Install a newer signed release if there is one. Returns its version when the caller should exit."""
    found = await fetch_update(http, server)
    if not found:
        return None
    manifest, wheel, constraints = found
    if await asyncio.to_thread(install_update, wheel, constraints, manifest["version"]):
        return str(manifest["version"])
    return None


async def update_loop(server: str, first_delay: float = UPDATE_FIRST_CHECK_S) -> None:
    """Returns once a newer signed version is installed (the caller then exits to restart)."""
    if not in_uv_tool():
        log.info("not running from a uv tool install (%s); automatic updates are off", sys.prefix)
        await asyncio.Event().wait()
    await asyncio.sleep(first_delay)
    async with httpx.AsyncClient(timeout=120) as http:
        while True:
            try:
                before = installed_version()
                if version := await update_once(http, server):
                    log.info("updated %s -> %s; restarting", before, version)
                    return
            except Exception:  # never let the updater take the agent down
                log.exception("update check failed")
            await asyncio.sleep(UPDATE_INTERVAL_S * random.uniform(0.9, 1.1))


# --- one agent per user ---------------------------------------------------------------------

class AlreadyRunning(RuntimeError):
    pass


class InstanceLock:
    """An exclusive lock on CONFIG_DIR/agent.lock, held while the agent runs. It lives in the
    user's own folder, so another account on the same PC has its own; the OS drops it when the
    process dies."""

    def __init__(self, handle: BinaryIO, replaced: bool) -> None:
        self._handle, self.replaced = handle, replaced

    def close(self) -> None:
        if self._handle.closed:
            return
        try:
            if _config("agent.pid").read_text().strip() == str(os.getpid()):
                _config("agent.pid").unlink()
        except OSError:
            pass
        _unlock(self._handle)
        self._handle.close()


def _open_lock() -> BinaryIO:
    _private_dir(CONFIG_DIR)
    return open(_config("agent.lock"), "a+b")  # held for the agent's lifetime


def _try_lock(handle: BinaryIO) -> bool:
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(handle: BinaryIO) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def _running_pid() -> int | None:
    try:
        pid = int(_config("agent.pid").read_text().strip())
    except (OSError, ValueError):
        return None
    return pid if pid > 0 and pid != os.getpid() else None


def _ask_legacy_agent_to_exit() -> None:
    """Agents up to 0.9.0 listen on a localhost port for "exit"."""
    import socket

    try:
        with socket.create_connection(("127.0.0.1", LEGACY_LOCK_PORT), timeout=2) as other:
            other.sendall(b"exit\n")
    except OSError:
        pass


def stop_running_agent() -> bool:
    """Ask this user's running agent to exit (SIGTERM; on Windows it is terminated). True if one was."""
    handle = _open_lock()
    try:
        if _try_lock(handle):
            _unlock(handle)
            return False
    finally:
        handle.close()
    pid = _running_pid()  # written by the lock holder, so it is this user's agent
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    return True


def single_instance(replace: bool = False) -> InstanceLock:
    """Take the per-user lock; with replace=True, stop a running agent first."""
    handle = _open_lock()
    replaced = False
    if not _try_lock(handle):
        if not replace:
            handle.close()
            raise AlreadyRunning("에이전트가 이미 실행 중입니다.")
        replaced = stop_running_agent()
        deadline = time.monotonic() + 10
        while not _try_lock(handle):
            if time.monotonic() > deadline:
                handle.close()
                raise AlreadyRunning("실행 중인 에이전트가 끝나지 않습니다.")
            time.sleep(0.3)
    if replace:
        _ask_legacy_agent_to_exit()
    _config("agent.pid").write_text(str(os.getpid()))
    return InstanceLock(handle, replaced)


def agent_running() -> bool:
    handle = _open_lock()
    try:
        if _try_lock(handle):
            _unlock(handle)
            return False
        return True
    finally:
        handle.close()


async def main(replace: bool = False) -> int:
    """Run until stopped or replaced (0), updated (RESTART_EXIT_CODE), or broken (1)."""
    lock = single_instance(replace)
    try:
        server = load_link().server
        crashed, failing = note_start(replaced=lock.replaced)
        if failing and roll_back(failing):
            return RESTART_EXIT_CODE
        started, connected, stop = time.monotonic(), asyncio.Event(), asyncio.Event()
        if os.name != "nt":
            asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop.set)
        on_trial = "pending" in load_state()
        first = random.uniform(*UPDATE_AFTER_CRASH_S) if crashed or on_trial else UPDATE_FIRST_CHECK_S
        runner = asyncio.create_task(run_forever(connected))
        updater = asyncio.create_task(update_loop(server, first))
        stopper = asyncio.create_task(stop.wait())
        keeper = asyncio.create_task(_keep_if_healthy(connected, started))
        done, pending = await asyncio.wait({runner, updater, stopper}, return_when=asyncio.FIRST_COMPLETED)
        for task in (*pending, keeper):
            task.cancel()
        error = runner.exception() if runner in done else None
        if error is not None and not isinstance(error, (NotLinked, KeyringError)):
            # Don't just crash into a restart loop: a fixed version may already be out.
            log.error("the agent stopped unexpectedly; checking for a fixed version", exc_info=error)
            try:
                async with httpx.AsyncClient(timeout=120) as http:
                    if in_uv_tool() and await update_once(http, server):
                        return RESTART_EXIT_CODE
            except Exception:
                log.exception("update check failed")
            return 1
        for task in done:
            task.result()
        return RESTART_EXIT_CODE if updater in done else 0
    finally:
        note_stop()
        lock.close()


def configure_logging(log_file: str | None) -> None:
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=512_000, backupCount=2,
                                                                        encoding="utf-8")
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    for noisy in ("httpx", "httpcore", "websockets"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# --- start at login ---------------------------------------------------------------------

def default_log_file() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "kw-campus-agent.log"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "kw-campus" / "agent.log"
    return CONFIG_DIR / "agent.log"


def agent_command() -> list[str]:
    python = Path(sys.executable)
    if os.name == "nt" and python.with_name("pythonw.exe").exists():
        python = python.with_name("pythonw.exe")  # no console window
    return [str(python), "-m", "kw_mcp", "agent", "--log-file", str(default_log_file())]


def launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


def launchd_plist() -> bytes:
    return plistlib.dumps({
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": agent_command(),
        "RunAtLoad": True,
        # Restart after a crash; a clean exit (stopped, or another agent already running) stays down.
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 30,
        "ProcessType": "Background",
    })


def install_autostart() -> str:
    """Start the agent now and at every login. Returns a short description of what was set up."""
    if sys.platform == "darwin":
        path, domain = launchd_plist_path(), f"gui/{os.getuid()}"
        subprocess.run(["launchctl", "bootout", f"{domain}/{LAUNCHD_LABEL}"], capture_output=True, check=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(launchd_plist())
        for attempt in range(5):  # bootout returns before the job is gone: bootstrap can say "error 5" at first
            done = subprocess.run(["launchctl", "bootstrap", domain, str(path)], capture_output=True, text=True,
                                  check=False)
            if done.returncode == 0:
                break
            time.sleep(1 + attempt)
        else:
            raise subprocess.CalledProcessError(done.returncode, done.args, done.stdout, done.stderr)
        return f"로그인 항목(launchd): {path}"
    if os.name == "nt":
        import winreg

        # CreateKeyEx opens the Run key, or creates it on profiles that don't have one yet.
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                                winreg.KEY_SET_VALUE) as run_key:
            winreg.SetValueEx(run_key, WINDOWS_RUN_VALUE, 0, winreg.REG_SZ, _quote(agent_command()))
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        subprocess.Popen([*agent_command(), "--replace"], creationflags=flags, close_fds=True)
        return "Windows 시작 프로그램(HKCU\\...\\Run)"
    raise NotImplementedError("자동 실행은 macOS와 Windows만 지원합니다. `kw-mcp agent`를 직접 실행해 두세요.")


def restart_autostarted_agent() -> bool:
    """Restart the login-item agent so it runs the version just installed. True if one was restarted."""
    if sys.platform == "darwin" and launchd_plist_path().exists():
        return subprocess.run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{LAUNCHD_LABEL}"],
                              capture_output=True, check=False).returncode == 0
    return False


def uninstall_autostart() -> None:
    if sys.platform == "darwin":
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LAUNCHD_LABEL}"], capture_output=True, check=False)
        launchd_plist_path().unlink(missing_ok=True)
    elif os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                                winreg.KEY_SET_VALUE) as run_key:
                winreg.DeleteValue(run_key, WINDOWS_RUN_VALUE)
        except OSError:
            pass
    stop_running_agent()
    _ask_legacy_agent_to_exit()


def autostart_installed() -> bool:
    if sys.platform == "darwin":
        return launchd_plist_path().exists()
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as run_key:
                winreg.QueryValueEx(run_key, WINDOWS_RUN_VALUE)
            return True
        except OSError:
            return False
    return False
