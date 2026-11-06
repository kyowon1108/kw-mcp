"""Low-level KLAS (klas.kw.ac.kr) HTTP client.

KLAS has no public API. The web UI (Vue + axios) talks to `*.do` endpoints that
take a JSON body and return JSON, guarded by a session cookie. This client logs
in the same way the login page does and re-logs in once when the session expires.

It identifies itself honestly (USER_AGENT) and paces itself: a token bucket, a cap per
10 minutes, at most MAX_PARALLEL requests in flight, and one shared back-off when KLAS is down.
A password KLAS says doesn't match is never sent again until it is saved again or changed, across
restarts too. Data requests wait while a login runs, so nothing changes the session cookie that the
login handshake is tied to.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import math
import os
import re
import secrets
import time
from collections import deque
from datetime import datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version
from pathlib import Path
from typing import Any, NoReturn, Self
from zoneinfo import ZoneInfo

import httpx
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_der_public_key

BASE_URL = "https://klas.kw.ac.kr"
# The maintainer's address. The repositories are private, so no project URL goes in the
# User-Agent or in messages: a link a school admin or a student can't open is no contact.
CONTACT_EMAIL = "kyowon1108@gmail.com"
REPORT_TO = f"개발자 메일({CONTACT_EMAIL})로 알려 주세요"


def package_version() -> str:
    try:
        return _package_version("kw-mcp")
    except PackageNotFoundError:
        return "0"


# Honest product token, so KLAS operators can tell this tool apart and reach its maintainer.
# Accepted by KLAS (tested 2026-11-06). If KLAS ever refuses it, the client stops
# (KlasClientRejected); it never falls back to a browser User-Agent.
USER_AGENT = f"kw-mcp/{package_version()} (contact {CONTACT_EMAIL})"

LOGIN_FORM = "/usr/cmn/login/LoginForm.do"
LOGIN_SECURITY = "/usr/cmn/login/LoginSecurity.do"
LOGIN_CAPTCHA = "/usr/cmn/login/LoginCaptcha.do"
LOGIN_CONFIRM = "/usr/cmn/login/LoginConfirm.do"
DOWNLOAD_PREFIX = "/common/file/DownloadFile/"

# KLAS's login page asks for a captcha once LoginCaptcha.do reports more than this many failures.
# We stop before LoginConfirm as soon as the count reaches it, so our attempt is never the one
# that tips the account into the captcha.
CAPTCHA_THRESHOLD = 2
# How long a blocked login (captcha state, unknown login answer) is reported without asking KLAS
# again. Checking again is harmless: the check stops before the password is sent.
LOGIN_BLOCK_COOLDOWN = 600.0
TWO_FACTOR_COOLDOWN = 3600.0  # each attempt may send the student a 2FA prompt
SESSION_REFUSED_COOLDOWN = 300.0  # KLAS took the password but not the session right after
LOGIN_COOLDOWN = LOGIN_BLOCK_COOLDOWN  # older name
# KLAS down or in maintenance (5xx, HTML instead of the login API, no connection): every request
# fails fast for this long instead of each one logging in again.
TRANSIENT_BACKOFF = 30.0
# Upper bound on requests in flight to KLAS from this client.
MAX_PARALLEL = 4
# Pacing: about RATE_PER_S requests a second with bursts up to RATE_BURST, and no more than
# WINDOW_CAP requests in WINDOW_S; past that, a clear error instead of an endless queue.
RATE_PER_S = 8.0
RATE_BURST = 16
WINDOW_S = 600.0
WINDOW_CAP = 600
MAX_ERROR_BODY = 64 * 1024

# A rejected login is remembered here (salted PBKDF2 fingerprint of id + password and the time;
# never the password), so a restart or another kw-mcp process on this PC doesn't try it again.
LOGIN_STATE_FILE = Path.home() / ".config" / "kw-mcp" / "login-state.json"
# How klas_status names the file: the real path holds the OS user name, often the person's name.
STATE_FILE_SHOWN = "~/.config/kw-mcp/login-state.json"
FINGERPRINT_ROUNDS = 100_000
MAX_REJECTED = 5  # rejected logins remembered (one entry each; saving one again removes only that one)
# The only LoginConfirm answer known to mean "wrong id or password" ("개인번호 또는 비밀번호가 일치하지
# 않습니다."). Only this one stops a login for good; any other error answer may be a session or key
# mismatch of a correct password and is retried after LOGIN_BLOCK_COOLDOWN.
PASSWORD_MISMATCH = "일치하지않"
# KLAS refusing this client (e.g. its User-Agent): during the login handshake that stops it at once; on
# data requests, once this many different endpoints refused it with no normal answer in between.
_REFUSED_STATUS = frozenset({401, 403, 406})
REFUSED_ENDPOINTS_TO_STOP = 3

_KST = ZoneInfo("Asia/Seoul")
# Markers of KLAS's login page. Other HTML (maintenance, error pages) is not an expired session.
_LOGIN_PAGE = re.compile(r"LoginForm\.do|LoginConfirm\.do|LoginSecurity\.do|loginPwd|name=[\"']?loginId", re.IGNORECASE)
# Anything a servlet container could resolve outside the attachment folder: backslashes, query or
# fragment, ';' path parameters ('..;/'), encoded dots, slashes, backslashes, semicolons, '%' and NUL
# (double encoding), a '%' that isn't an escape (IIS-style '%u002e'), dot segments, '//', and any
# character outside printable ASCII.
_BAD_DOWNLOAD = re.compile(
    r"[\\?#;]|%(?:2e|2f|5c|3b|25|00)|%(?![0-9a-f]{2})|[^\x20-\x7e]|(?:^|/)\.\.?(?:/|$)|//", re.IGNORECASE)
_TRANSIENT_STATUS = frozenset({429, 502, 503, 504})
# Transport errors that mean KLAS is down or hanging: they start the shared back-off.
_DOWN_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ReadError,
                httpx.WriteTimeout, httpx.PoolTimeout, httpx.RemoteProtocolError)


class KlasError(Exception):
    """A KLAS request failed."""


class KlasLoginError(KlasError):
    """Login was rejected or needs a step this client cannot do (captcha, 2FA)."""


class KlasLoginBlocked(KlasLoginError):
    """KLAS wants a person at the keyboard (captcha, 2FA, password change); retrying won't help.

    retry_after: seconds before this client asks KLAS again (inf: not until the login changes).
    """

    def __init__(self, message: str, retry_after: float = math.inf) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class KlasClientRejected(KlasLoginBlocked):
    """KLAS refused this tool itself (e.g. its User-Agent). Stop; don't disguise and retry."""


class KlasBadPassword(KlasLoginError):
    """KLAS said the id/password don't match. Retrying with the same password only adds failures."""


class SessionExpired(KlasError):
    """KLAS answered with the login page instead of JSON."""


class KlasUnavailable(KlasError):
    """KLAS is down or in maintenance; requests pause for TRANSIENT_BACKOFF."""


class KlasRequestLimit(KlasError):
    """This client's own request cap (WINDOW_CAP per WINDOW_S) is used up."""


class KlasFileTooLarge(KlasError):
    """An attachment turned out bigger than the download limit (KLAS's fileSize was missing or wrong).
    Downloading it again gives the same answer."""


def encrypt_login(public_key_b64: str, login_id: str, password: str) -> str:
    """Build `loginToken` exactly like the login page's JSEncrypt call.

    JSEncrypt uses RSA PKCS#1 v1.5 and returns base64. The key KLAS hands out is a
    base64 DER SubjectPublicKeyInfo.
    """
    key = load_der_public_key(base64.b64decode(public_key_b64))
    if not isinstance(key, RSAPublicKey):
        raise KlasLoginError("KLAS public key is not an RSA key")
    payload = json.dumps(
        {"loginId": login_id, "loginPwd": password, "storeIdYn": "N"},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return base64.b64encode(key.encrypt(payload, padding.PKCS1v15())).decode()


# -- the rejected-login marker -----------------------------------------------------------------

def _read_state() -> dict[str, Any]:
    try:
        data = json.loads(LOGIN_STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_state(data: dict[str, Any]) -> bool:
    """Best effort: a read-only home (e.g. a server) just means no memory across restarts (False)."""
    try:
        LOGIN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        partial = LOGIN_STATE_FILE.with_name(f"{LOGIN_STATE_FILE.name}.{os.getpid()}.part")
        fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        partial.replace(LOGIN_STATE_FILE)
    except OSError:
        return False
    return True


def _fingerprint(login_id: str, password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", f"{login_id}\0{password}".encode(), bytes.fromhex(salt),
                               FINGERPRINT_ROUNDS).hex()


def _salt(state: dict[str, Any]) -> str | None:
    salt = state.get("salt")
    if not isinstance(salt, str):
        return None
    try:
        bytes.fromhex(salt)
    except ValueError:
        return None
    return salt


def _rejections(state: dict[str, Any]) -> list[dict[str, Any]]:
    """The rejected logins in the state file, oldest first (before 1.0 there was one dict, not a list)."""
    entries = state.get("rejected")
    if isinstance(entries, dict):
        entries = [entries]
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def _entry_for(state: dict[str, Any], login_id: str, password: str) -> dict[str, Any] | None:
    entries, salt = _rejections(state), _salt(state)
    if not entries or salt is None:
        return None
    fingerprint = _fingerprint(login_id, password, salt)
    return next((e for e in reversed(entries) if e.get("fingerprint") == fingerprint), None)


def rejected_login(login_id: str | None = None, password: str | None = None) -> dict[str, Any] | None:
    """When KLAS last rejected this login on this PC ({"at": ..., "state_file": ...}), or None.
    Without a login: the latest rejection of any login. No KLAS request, but with a login it runs
    PBKDF2: call it off the event loop."""
    state = _read_state()
    if login_id is None or password is None:
        entries = _rejections(state)
        entry = entries[-1] if entries else None
    else:
        entry = _entry_for(state, login_id, password)
    return {"at": entry.get("at"), "state_file": STATE_FILE_SHOWN} if entry else None


def forget_rejected_login(login_id: str | None = None, password: str | None = None) -> None:
    """Called when a login is saved again (`kw-mcp setup`): the next request with it may try once more.
    Removes only that login's entry; without a login (the saved login is deleted) every entry."""
    state = _read_state()
    if "rejected" not in state:
        return
    entries, salt = _rejections(state), _salt(state)
    if login_id is None or password is None or salt is None:
        keep: list[dict[str, Any]] = []  # without a salt no entry can ever match
    else:
        fingerprint = _fingerprint(login_id, password, salt)
        keep = [e for e in entries if e.get("fingerprint") != fingerprint]
    if keep == entries and isinstance(state.get("rejected"), list):
        return
    if keep:
        state["rejected"] = keep
    else:
        state.pop("rejected")
    _write_state(state)


def _now_text() -> str:
    return datetime.now(_KST).strftime("%Y-%m-%d %H:%M")


class KlasClient:
    def __init__(
        self,
        login_id: str,
        password: str,
        *,
        base_url: str = BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
        login_hint: str = "",
    ) -> None:
        self._login_id = login_id
        self._password = password
        self._login_hint = login_hint  # where this login came from and how to fix it
        self._http = httpx.AsyncClient(
            base_url=base_url,
            transport=transport,
            follow_redirects=False,
            timeout=httpx.Timeout(20.0, connect=10.0),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"},
        )
        self._login_lock = asyncio.Lock()
        self._slots = asyncio.Semaphore(MAX_PARALLEL)
        # Bumped on every successful login. A request remembers the generation it was sent
        # under, so concurrent requests that all hit an expired session trigger one login.
        self._generation = 0
        # (until monotonic time, error): login attempts are refused until then. inf = until the
        # saved login changes (KlasHolder then builds a new client) or, for a rejected password,
        # until its marker is gone from the state file (saved again).
        self._login_failure: tuple[float, KlasLoginError] | None = None
        self._unavailable: tuple[float, KlasError] | None = None
        # True while this login's rejection is known to be in the state file. Only then does the
        # file losing it lift the block: a marker that could not be written keeps the block on.
        self._rejection_on_disk = False
        self._fp: tuple[str, str] | None = None  # (salt, fingerprint)
        # The cookie jar is shared: KLAS may answer a request on an expired session with a new
        # session cookie, which would replace the one a login handshake is tied to. So a login waits
        # for the data requests already sent (_on_wire) and holds new ones (_jar_free) until it's done.
        self._jar_free = asyncio.Event()
        self._jar_free.set()
        self._wire_idle = asyncio.Event()
        self._wire_idle.set()
        self._on_wire = 0
        # Endpoints that answered 401/403/406 since the last normal answer to a data request.
        self._refused: set[str] = set()
        self._rate_lock = asyncio.Lock()
        self._tokens = float(RATE_BURST)
        self._refilled = time.monotonic()
        self._sent: deque[float] = deque()
        # What klas_status shows: {"at": "YYYY-MM-DD HH:MM", "ok": bool, "error": message or None}
        self.last_login: dict[str, Any] | None = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    def recent_requests(self) -> int:
        """Requests sent to KLAS in the last WINDOW_S seconds (klas_status shows it)."""
        now = time.monotonic()
        return sum(1 for sent in self._sent if now - sent < WINDOW_S)

    async def login(self) -> None:
        """Log in now, even if a session exists."""
        await self._relogin(self._generation)

    async def post(self, path: str, body: dict[str, Any] | None = None, *, allow_empty: bool = False) -> Any:
        """POST a JSON body to a KLAS endpoint, logging in (again) when needed. An empty answer is an
        error unless allow_empty (then None): elsewhere it would read as "nothing due". So is an
        answer that reports an error (errorCount > 0)."""
        data = await self._with_session(lambda: self._raw_post(path, body or {}, allow_empty))
        if isinstance(data, dict) and ((_int(data.get("errorCount")) or 0) > 0 or data.get("fieldErrors")):
            raise KlasError(f"{path}: KLAS가 오류를 알렸습니다({_error_message(data) or 'errorCount'}).")
        return data

    async def download(self, path: str, max_bytes: int) -> bytes:
        """GET a file (attachment download), logging in again if the session expired.
        KlasFileTooLarge when it is bigger than max_bytes."""
        self._download_request(path)  # refuse before logging in
        return await self._with_session(lambda: self._raw_download(path, max_bytes))

    def _download_request(self, path: str) -> httpx.Request:
        """Only plain attachment paths: httpx resolves "..", so check before and after building the URL."""
        refused = KlasError(f"refusing to fetch {path!r}: only attachment downloads are allowed")
        if not path.startswith(DOWNLOAD_PREFIX) or _BAD_DOWNLOAD.search(path):
            raise refused
        request = self._http.build_request("GET", path)
        if (request.url.host != self._http.base_url.host or not request.url.path.startswith(DOWNLOAD_PREFIX)
                or request.url.query):
            raise refused
        return request

    async def _with_session(self, send: Any) -> Any:
        await self._recheck_rejection()
        self._raise_if_paused()
        generation = self._generation
        fresh = generation == 0
        if fresh:
            await self._relogin(0)
            generation = self._generation
        try:
            return await send()
        except SessionExpired:
            if fresh:
                self._session_refused()
        await self._relogin(generation)
        try:
            return await send()
        except SessionExpired:
            self._session_refused()

    def _session_refused(self) -> NoReturn:
        """The session expired right after a login made for this call: logging in again won't help."""
        error = KlasLoginBlocked(
            "KLAS가 로그인 직후의 세션을 받아 주지 않습니다(비밀번호 변경·동의 같은 안내 화면이 있을 수 있음). "
            "브라우저에서 KLAS에 한 번 로그인해 안내 화면을 확인하세요. "
            f"{int(SESSION_REFUSED_COOLDOWN // 60)}분 동안은 다시 로그인하지 않습니다.",
            retry_after=SESSION_REFUSED_COOLDOWN)
        self._generation = 0
        # Through _fail_login: a stop for good that other answers set meanwhile (a third screen
        # refusing the tool) stays, and this call reports that stop instead.
        raise self._fail_login(error, SESSION_REFUSED_COOLDOWN)

    def _raise_if_paused(self) -> None:
        now = time.monotonic()
        if self._login_failure:
            until, error = self._login_failure
            if now < until:
                raise error
            self._login_failure = None
        if self._unavailable:
            until, error = self._unavailable
            if now < until:
                raise error
            self._unavailable = None

    def _pause(self, error: KlasError) -> KlasUnavailable:
        paused = error if isinstance(error, KlasUnavailable) else KlasUnavailable(str(error))
        self._unavailable = (time.monotonic() + TRANSIENT_BACKOFF, KlasUnavailable(
            f"{paused} KLAS가 잠시 응답하지 않아(점검·장애일 수 있음) {int(TRANSIENT_BACKOFF)}초 동안 요청을 멈춥니다."))
        return paused

    async def _relogin(self, seen_generation: int) -> None:
        async with self._login_lock:
            await self._recheck_rejection()
            self._raise_if_paused()
            if self._generation != seen_generation:
                return  # another request already logged in while we waited
            # Before every login, not once per client: another kw-mcp process on this PC (the MCP
            # server and the PC agent) may have had this same login rejected in the meantime.
            await self._check_marker()
            try:
                await self._login()
            except (KlasError, httpx.HTTPError) as e:
                if self._in_force(e):
                    # A back-off or a stop that an answer started while this login waited for the
                    # wire: already recorded, so it is neither extended nor written over.
                    raise
                await self._login_failed(e)
            self._generation += 1
            self.last_login = {"at": _now_text(), "ok": True, "error": None}
            await self._forget_rejection()

    def _in_force(self, error: BaseException) -> bool:
        """error is the login block or the back-off this client already holds (_raise_if_paused raised it)."""
        return any(held is not None and held[1] is error for held in (self._login_failure, self._unavailable))

    async def _login_failed(self, e: KlasError | httpx.HTTPError) -> NoReturn:
        """Record why the login failed and raise what the caller should see."""
        if isinstance(e, KlasBadPassword):
            error = self._fail_login(e, math.inf)
            await self._remember_rejection()
            raise error
        if isinstance(e, KlasLoginBlocked):
            raise self._fail_login(e, e.retry_after)
        if isinstance(e, KlasLoginError):
            raise self._fail_login(e, LOGIN_BLOCK_COOLDOWN)
        if isinstance(e, KlasRequestLimit):
            raise e
        # Maintenance pages, 5xx, no connection: one shared back-off, so the requests
        # queued on this lock don't each run the whole handshake again.
        error = self._pause(e if isinstance(e, KlasUnavailable) else
                            KlasUnavailable(f"KLAS에 로그인하지 못했습니다({_describe(e)})."))
        self.last_login = {"at": _now_text(), "ok": False, "error": str(error)}
        raise error from e

    def _fail_login(self, error: KlasLoginError, retry_after: float) -> KlasLoginError:
        """Refuse logins for retry_after seconds; returns the error now in force. A stop for good
        (KLAS refused the tool, the password was rejected, a graduate account) is never replaced: a
        shorter block written over it would send the client back to KLAS when that one ran out."""
        held = self._login_failure
        if held is not None and held[0] == math.inf:
            return held[1]
        self._login_failure = (time.monotonic() + retry_after, error)
        self.last_login = {"at": _now_text(), "ok": False, "error": str(error)}
        return error

    # -- the on-disk marker (blocking file and PBKDF2 work runs in a thread) ----------------------

    def _fingerprint_sync(self, salt: str) -> str:
        if self._fp is None or self._fp[0] != salt:
            self._fp = (salt, _fingerprint(self._login_id, self._password, salt))
        return self._fp[1]

    async def _fingerprint(self, salt: str) -> str:
        return await asyncio.to_thread(self._fingerprint_sync, salt)

    async def _marked(self) -> dict[str, Any] | None:
        """This login's entry in the rejected-login marker, or None."""
        state = await asyncio.to_thread(_read_state)
        entries, salt = _rejections(state), _salt(state)
        if not entries or salt is None:
            return None
        fingerprint = await self._fingerprint(salt)
        return next((e for e in reversed(entries) if e.get("fingerprint") == fingerprint), None)

    async def _check_marker(self) -> None:
        entry = await self._marked()
        if entry is None:
            return
        self._rejection_on_disk = True
        hint = self._login_hint or "학번과 비밀번호를 다시 저장하세요."
        error = KlasBadPassword(
            f"KLAS가 이 학번·비밀번호를 거부했습니다({entry.get('at') or '이전'}). — {hint} "
            "같은 비밀번호는 다시 보내지 않습니다(보안문자 방지). 고치면 다음 요청에서 바로 로그인합니다. "
            f"KLAS 웹에서 이 비밀번호로 로그인이 되는데도 이 오류가 계속되면 {STATE_FILE_SHOWN} 파일을 지우고 "
            "Claude(또는 PC 에이전트)를 다시 시작하세요.")
        self._fail_login(error, math.inf)
        raise error

    async def _recheck_rejection(self) -> None:
        """A rejected password blocks this client for good, but only while its marker is on disk:
        `kw-mcp setup` saving the same pair again removes it, and the next request tries once more
        without restarting the MCP server or the PC agent."""
        failure = self._login_failure
        if (failure is None or failure[0] != math.inf or not isinstance(failure[1], KlasBadPassword)
                or not self._rejection_on_disk):
            return
        if await self._marked() is None and self._login_failure is failure:
            self._login_failure = None
            self._rejection_on_disk = False

    async def _remember_rejection(self) -> None:
        def write() -> bool:
            state = _read_state()
            salt = _salt(state)
            entries = _rejections(state) if salt else []  # a new salt: old fingerprints can't match
            salt = salt or secrets.token_hex(16)
            fingerprint = self._fingerprint_sync(salt)
            entries = [e for e in entries if e.get("fingerprint") != fingerprint]
            entries.append({"fingerprint": fingerprint, "at": _now_text()})
            return _write_state({**state, "salt": salt, "rejected": entries[-MAX_REJECTED:]})

        with contextlib.suppress(OSError, ValueError):
            self._rejection_on_disk = await asyncio.to_thread(write)

    async def _forget_rejection(self) -> None:
        if await self._marked() is not None:
            await asyncio.to_thread(forget_rejected_login, self._login_id, self._password)

    # -- requests --------------------------------------------------------------------------------

    async def _throttle(self) -> float:
        """Wait for this request's turn; returns its time stamp in the 10-minute window."""
        async with self._rate_lock:
            now = time.monotonic()
            while self._sent and now - self._sent[0] >= WINDOW_S:
                self._sent.popleft()
            if len(self._sent) >= WINDOW_CAP:
                wait = max(1, math.ceil((WINDOW_S - (now - self._sent[0])) / 60))
                raise KlasRequestLimit(
                    f"최근 {int(WINDOW_S // 60)}분 동안 KLAS에 {WINDOW_CAP}번 요청해 학교 서버 보호를 위해 멈췄습니다. "
                    f"약 {wait}분 뒤 다시 시도하세요.")
            self._tokens = min(float(RATE_BURST), self._tokens + (now - self._refilled) * RATE_PER_S)
            self._refilled = now
            if self._tokens < 1:
                await asyncio.sleep((1 - self._tokens) / RATE_PER_S)
                now = time.monotonic()
                self._tokens = min(float(RATE_BURST), self._tokens + (now - self._refilled) * RATE_PER_S)
                self._refilled = now
            self._tokens -= 1
            self._sent.append(now)
            return now

    def _not_sent(self, stamp: float) -> None:
        """A request that got its turn but was stopped before sending: it doesn't count as sent."""
        with contextlib.suppress(ValueError):
            self._sent.remove(stamp)
        self._tokens = min(float(RATE_BURST), self._tokens + 1)

    def _raise_if_paused_before_sending(self, stamp: float) -> None:
        # Again right before sending: a back-off or a failed login that started while this request
        # was queued stops it here instead of sending it anyway.
        try:
            self._raise_if_paused()
        except KlasError:
            self._not_sent(stamp)
            raise

    def _status_error(self, path: str, status: int, *, login: bool = False) -> KlasError:
        if status in _TRANSIENT_STATUS:
            return self._pause(KlasUnavailable(f"{path}: HTTP {status}"))
        if status in _REFUSED_STATUS:
            if login:  # a login step refused: KLAS doesn't want this client (e.g. its User-Agent)
                return KlasClientRejected(self._refusal_text(f"HTTP {status}"))
            self._refused.add(DOWNLOAD_PREFIX if path.startswith(DOWNLOAD_PREFIX) else path)
            if len(self._refused) >= REFUSED_ENDPOINTS_TO_STOP:
                # Different screens all refused with nothing working in between: a block of this
                # tool rolled out mid-session, not one screen this student may not open.
                error = KlasClientRejected(self._refusal_text(f"HTTP {status}, 서로 다른 요청 {len(self._refused)}곳"))
                self._fail_login(error, math.inf)
                return error
        return KlasError(f"{path}: HTTP {status}")

    @staticmethod
    def _refusal_text(detail: str) -> str:
        return (f"KLAS가 이 도구(kw-mcp)의 접속을 거부했습니다({detail}). 위장해서 다시 시도하지 않고 멈춥니다. "
                f"브라우저에서 KLAS를 이용하고, {REPORT_TO}.")

    def _transport_down(self, error: httpx.HTTPError) -> None:
        """KLAS can't be reached or stopped answering: one shared back-off instead of every request
        waiting out its own timeout."""
        name = error.__class__.__name__
        reason = (f"KLAS에 연결하지 못했습니다({name})." if isinstance(error, (httpx.ConnectError, httpx.ConnectTimeout))
                  else f"KLAS가 제때 응답하지 않았습니다({name}).")
        self._pause(KlasUnavailable(reason))

    async def _wait_for_login(self) -> None:
        """A data request waits while a login runs, then counts as on the wire until answered."""
        while not self._jar_free.is_set():
            await self._jar_free.wait()
        self._on_wire += 1
        self._wire_idle.clear()

    def _answered(self) -> None:
        """A data request's answer (and any cookie it set) is in: a waiting login may start."""
        self._on_wire -= 1
        if self._on_wire <= 0:
            self._on_wire = 0
            self._wire_idle.set()

    async def _send(self, method: str, path: str, *, login: bool = False, **kwargs: Any) -> httpx.Response:
        stamp = await self._throttle()
        if login:  # a login step: _login already holds the data requests back
            async with self._slots:
                try:
                    return await self._http.request(method, path, **kwargs)
                except _DOWN_ERRORS as e:
                    self._transport_down(e)
                    raise
        await self._wait_for_login()
        try:
            async with self._slots:
                self._raise_if_paused_before_sending(stamp)
                try:
                    resp = await self._http.request(method, path, **kwargs)
                except _DOWN_ERRORS as e:
                    self._transport_down(e)
                    raise
        finally:
            self._answered()
        if resp.status_code < 400 and not resp.is_redirect:
            self._refused.clear()
        return resp

    async def _login(self) -> None:
        self._jar_free.clear()  # data requests sent from now on wait for this login
        try:
            await self._wire_idle.wait()  # and the ones already sent are answered (and set their cookies) first
            # Those answers may have paused or stopped this client (a 503 or a hanging KLAS: the
            # back-off; a third screen refusing the tool: the stop). Then no login and no password go out.
            self._raise_if_paused()
            self._http.cookies.clear()
            await self._handshake()
        finally:
            self._jar_free.set()

    async def _handshake(self) -> None:
        # Loading the form first gives us the session cookie the login calls are tied to.
        form = await self._send("GET", LOGIN_FORM, login=True)
        if form.status_code >= 400:
            raise self._status_error(LOGIN_FORM, form.status_code, login=True)

        try:
            security = await self._raw_post(LOGIN_SECURITY, {}, login=True)
        except SessionExpired as e:
            raise KlasUnavailable("KLAS 로그인 페이지가 응답하지 않습니다(점검 중일 수 있음).") from e
        public_key = security.get("publicKey") if isinstance(security, dict) else None
        if not public_key:
            raise KlasLoginError("KLAS did not return a login public key")
        token = encrypt_login(public_key, self._login_id, self._password)

        failures = await self._raw_post(LOGIN_CAPTCHA, {"loginToken": token, "captcha": ""}, login=True)
        try:
            failures = int(failures)
        except (TypeError, ValueError):
            raise KlasLoginError("KLAS 로그인 응답 형식이 바뀌어 로그인을 중단했습니다.") from None
        if failures >= CAPTCHA_THRESHOLD:
            raise KlasLoginBlocked(
                f"이 계정은 KLAS 로그인 실패가 {failures}회 쌓여 있어 비밀번호를 보내지 않았습니다(더 틀리면 보안문자(캡차)가 걸림). "
                "브라우저에서 KLAS에 직접 한 번 로그인해 횟수를 초기화하세요. "
                f"{int(LOGIN_BLOCK_COOLDOWN // 60)}분 뒤 다시 확인합니다.",
                retry_after=LOGIN_BLOCK_COOLDOWN)

        result = await self._raw_post(
            LOGIN_CONFIRM,
            {"loginToken": token, "captcha": "", "redirectUrl": "", "redirectTabUrl": ""},
            login=True,
        )
        if not isinstance(result, dict):
            raise KlasLoginError("Unexpected login response from KLAS")
        if _int(result.get("errorCount")) != 0:
            message = _error_message(result)
            hint = self._login_hint or "학번과 비밀번호를 다시 저장하세요."
            if message and PASSWORD_MISMATCH in re.sub(r"\s+", "", message):
                raise KlasBadPassword(
                    f"{message} — {hint} 고치면 다음 요청에서 바로 다시 로그인합니다. 그대로 두면 "
                    "보안문자가 걸리지 않도록 같은 비밀번호로는 다시 로그인하지 않습니다."
                )
            # Any other error answer (a session or key mismatch, a new message): not proof that the
            # password is wrong, so not a permanent stop. The LoginCaptcha check above still keeps a
            # retry from tipping the account into the captcha.
            raise KlasLoginError(
                f"KLAS가 로그인을 받아 주지 않았습니다({message or '이유 없음'}). — {hint} "
                f"{int(LOGIN_BLOCK_COOLDOWN // 60)}분 뒤 다시 시도합니다."
            )

        info = result.get("response")
        info = info if isinstance(info, dict) else {}
        if info.get("twoFactorAt") == "Y":
            # Since 2026-10-26 KLAS asks for 2FA on logins from IPs it treats as foreign
            # (notice DUID 53483); cloud servers and VPNs count. Never try to get around it.
            raise KlasLoginBlocked(
                "KLAS가 이 로그인에 2차 인증을 요구합니다(해외로 보이는 IP에서 로그인하면 요구함). "
                "국내 인터넷에 연결된 PC에서, VPN을 끄고 실행하세요. "
                f"{int(TWO_FACTOR_COOLDOWN // 3600)}시간 뒤에 다시 시도합니다.",
                retry_after=TWO_FACTOR_COOLDOWN)
        if info.get("certOpt") == "Y":
            raise KlasLoginBlocked("KLAS 임시 비밀번호 상태입니다. 브라우저에서 비밀번호를 먼저 변경하고, "
                                   "바꾼 비밀번호를 다시 저장하세요.")
        if info.get("frstPwdAt") == "Y":
            raise KlasLoginBlocked("KLAS가 비밀번호 변경을 요구합니다. 브라우저에서 KLAS에 로그인해 비밀번호를 바꾸고, "
                                   "바꾼 비밀번호를 다시 저장하세요.")
        if info.get("gradAt") == "Y":
            raise KlasLoginBlocked("졸업생 계정은 KLAS를 이용할 수 없습니다.")

    async def _raw_post(self, path: str, body: dict[str, Any], allow_empty: bool = False, *,
                        login: bool = False) -> Any:
        resp = await self._send(
            "POST",
            path,
            login=login,
            content=json.dumps(body, ensure_ascii=False).encode(),
            # Same headers as the site's jQuery calls.
            headers={"Content-Type": "application/json; charset=UTF-8", "X-Requested-With": "XMLHttpRequest"},
        )
        if resp.is_redirect:
            location = resp.headers.get("location", "")
            if LOGIN_FORM in location:
                raise SessionExpired(f"{path}: redirected to the login page")
            raise KlasError(f"{path}: unexpected redirect to {location or '?'}")
        if resp.status_code >= 400:
            raise self._status_error(path, resp.status_code, login=login)
        if allow_empty and not resp.content.strip():
            return None  # LctreEvlTermCheck says "not the evaluation period" with an empty body
        try:
            data = resp.json()
        except ValueError:
            if "text/html" in resp.headers.get("content-type", ""):
                if _LOGIN_PAGE.search(resp.text):
                    raise SessionExpired(f"{path}: got the login page instead of JSON") from None
                raise KlasError(f"{path}: KLAS가 데이터 대신 웹 페이지를 보냈습니다(점검 중일 수 있음).") from None
            raise KlasError(f"{path}: response is not JSON") from None
        # To the site's own AJAX calls (our headers) a dead session isn't a 302 but 200 with
        # {"loginRequired": true, "redirect": true, "redirectUrl": "/usr/cmn/login/LoginForm.do?..."}
        # (checked 2026-11-06). Read as data it looks like "no courses, nothing due".
        if isinstance(data, dict) and data.get("loginRequired") is True:
            raise SessionExpired(f"{path}: KLAS asked to log in again")
        return data

    async def _raw_download(self, path: str, max_bytes: int) -> bytes:
        too_large = f"파일이 너무 큽니다({max_bytes // (1024 * 1024)}MB 넘음). KLAS에서 직접 내려받아 주세요."
        stamp = await self._throttle()
        await self._wait_for_login()
        answered = False
        try:
            async with self._slots:
                self._raise_if_paused_before_sending(stamp)
                # Built only now: httpx copies the cookies into a request when it is built, and a
                # request built before a login would carry the old session (its answer could then
                # replace the new session cookie).
                request = self._download_request(path)
                try:
                    resp = await self._http.send(request, stream=True)
                except _DOWN_ERRORS as e:
                    self._transport_down(e)
                    raise
                finally:
                    answered = True
                    self._answered()  # the headers (and cookies) are in; the body doesn't touch the jar
                try:
                    if resp.is_redirect:
                        if LOGIN_FORM in resp.headers.get("location", ""):
                            raise SessionExpired(f"{path}: redirected to the login page")
                        raise KlasError(f"{path}: unexpected redirect")
                    if resp.status_code >= 400:
                        raise self._status_error(path, resp.status_code)
                    self._refused.clear()
                    if (_int(resp.headers.get("content-length")) or 0) > max_bytes:
                        raise KlasFileTooLarge(too_large)
                    kind = resp.headers.get("content-type", "")
                    is_file = "attachment" in resp.headers.get("content-disposition", "").lower()
                    if not is_file and ("text/html" in kind or "application/json" in kind):
                        self._check_download_page(path, await _read_capped(resp, MAX_ERROR_BODY), kind)
                    chunks, total = [], 0
                    async for chunk in resp.aiter_bytes():
                        total += len(chunk)
                        if total > max_bytes:
                            raise KlasFileTooLarge(too_large)
                        chunks.append(chunk)
                except _DOWN_ERRORS as e:  # KLAS stopped sending the body
                    self._transport_down(e)
                    raise
                finally:
                    await resp.aclose()
        finally:
            if not answered:
                self._answered()
        return b"".join(chunks)

    @staticmethod
    def _check_download_page(path: str, head: bytes, kind: str) -> None:
        """An answer that is a page or JSON instead of a file: an expired session or an error."""
        text = head.decode("utf-8", errors="replace")
        if "json" in kind:
            try:
                data = json.loads(text)
            except ValueError:
                data = None
            if isinstance(data, dict) and data.get("loginRequired") is True:
                raise SessionExpired(f"{path}: KLAS asked to log in again")
            raise KlasError(f"{path}: 파일 대신 KLAS 응답이 왔습니다({(_error_message(data) if isinstance(data, dict) else None) or 'JSON'}).")
        if _LOGIN_PAGE.search(text):
            raise SessionExpired(f"{path}: got the login page instead of a file")
        raise KlasError(f"{path}: 파일 대신 웹 페이지가 왔습니다(삭제됐거나 점검 중일 수 있음).")


async def _read_capped(resp: httpx.Response, cap: int) -> bytes:
    chunks, total = [], 0
    async for chunk in resp.aiter_bytes():
        chunks.append(chunk)
        total += len(chunk)
        if total >= cap:
            break
    return b"".join(chunks)[:cap]


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _describe(error: BaseException) -> str:
    return str(error) if isinstance(error, KlasError) else error.__class__.__name__


def _error_message(result: dict[str, Any]) -> str | None:
    # axboot responses carry validation messages in fieldErrors, e.g.
    # {"fieldErrors": [{"field": "", "message": "개인번호 또는 비밀번호가 일치하지 않습니다."}], "errorCount": 1}
    messages = [
        e["message"] for e in result.get("fieldErrors") or [] if isinstance(e, dict) and e.get("message")
    ]
    if messages:
        return " ".join(messages)
    error = result.get("error")
    if isinstance(error, dict):
        return error.get("message") or error.get("msg")
    if isinstance(error, str):
        return error
    return result.get("message")
