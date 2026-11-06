"""Low-level KLAS (klas.kw.ac.kr) HTTP client.

KLAS has no public API. The web UI (Vue + axios) talks to `*.do` endpoints that
take a JSON body and return JSON, guarded by a session cookie. This client logs
in the same way the login page does and re-logs in once when the session expires.

It identifies itself honestly (USER_AGENT) and paces itself: a token bucket, a cap per
10 minutes, at most MAX_PARALLEL requests in flight, and one shared back-off when KLAS is down.
A rejected password is never sent again until the saved login changes, across restarts too.
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
CONTACT_URL = "https://github.com/kyowon1108/kw-mcp"
CONTACT_EMAIL = "kyowon1108@gmail.com"


def package_version() -> str:
    try:
        return _package_version("kw-mcp")
    except PackageNotFoundError:
        return "0"


# Honest product token, so KLAS operators can tell this tool apart and reach its maintainer.
# Accepted by KLAS (tested 2026-11-06). If KLAS ever refuses it, the client stops
# (KlasClientRejected); it never falls back to a browser User-Agent.
USER_AGENT = f"kw-mcp/{package_version()} (+{CONTACT_URL}; contact {CONTACT_EMAIL})"

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
FINGERPRINT_ROUNDS = 100_000

_KST = ZoneInfo("Asia/Seoul")
# Markers of KLAS's login page. Other HTML (maintenance, error pages) is not an expired session.
_LOGIN_PAGE = re.compile(r"LoginForm\.do|LoginConfirm\.do|LoginSecurity\.do|loginPwd|name=[\"']?loginId", re.IGNORECASE)
_BAD_DOWNLOAD = re.compile(r"[\\?#]|%(?:2e|2f|5c)|(?:^|/)\.\.?(?:/|$)|//", re.IGNORECASE)
_TRANSIENT_STATUS = frozenset({429, 502, 503, 504})


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
    """KLAS rejected the id/password. Retrying with the same password only adds failures."""


class SessionExpired(KlasError):
    """KLAS answered with the login page instead of JSON."""


class KlasUnavailable(KlasError):
    """KLAS is down or in maintenance; requests pause for TRANSIENT_BACKOFF."""


class KlasRequestLimit(KlasError):
    """This client's own request cap (WINDOW_CAP per WINDOW_S) is used up."""


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


def _write_state(data: dict[str, Any]) -> None:
    """Best effort: a read-only home (e.g. a server) just means no memory across restarts."""
    try:
        LOGIN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        partial = LOGIN_STATE_FILE.with_name(f"{LOGIN_STATE_FILE.name}.{os.getpid()}.part")
        fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        partial.replace(LOGIN_STATE_FILE)
    except OSError:
        pass


def _fingerprint(login_id: str, password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", f"{login_id}\0{password}".encode(), bytes.fromhex(salt),
                               FINGERPRINT_ROUNDS).hex()


def rejected_login() -> dict[str, Any] | None:
    """When KLAS last rejected a saved login on this PC ({"at": ...}), or None. No KLAS request."""
    entry = _read_state().get("rejected")
    return {"at": entry.get("at"), "state_file": str(LOGIN_STATE_FILE)} if isinstance(entry, dict) else None


def forget_rejected_login() -> None:
    """Called when the login is saved again (`kw-mcp setup`): the next request may try once more."""
    state = _read_state()
    if state.pop("rejected", None) is not None:
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
        # saved login changes (KlasHolder then builds a new client).
        self._login_failure: tuple[float, KlasLoginError] | None = None
        self._unavailable: tuple[float, KlasError] | None = None
        self._marker_checked = False
        self._fp: tuple[str, str] | None = None  # (salt, fingerprint)
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
        """GET a file (attachment download), logging in again if the session expired."""
        self._download_request(path)  # refuse before logging in
        # A fresh request per attempt: httpx puts the cookies in when the request is built.
        return await self._with_session(lambda: self._raw_download(self._download_request(path), max_bytes))

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
        self._login_failure = (time.monotonic() + SESSION_REFUSED_COOLDOWN, error)
        self._generation = 0
        self.last_login = {"at": _now_text(), "ok": False, "error": str(error)}
        raise error

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
            self._raise_if_paused()
            if self._generation != seen_generation:
                return  # another request already logged in while we waited
            if not self._marker_checked:
                await self._check_marker()
            try:
                await self._login()
            except KlasBadPassword as e:
                self._fail_login(e, math.inf)
                await self._remember_rejection()
                raise
            except KlasLoginBlocked as e:
                self._fail_login(e, e.retry_after)
                raise
            except KlasLoginError as e:
                self._fail_login(e, LOGIN_BLOCK_COOLDOWN)
                raise
            except KlasRequestLimit:
                raise
            except (KlasError, httpx.HTTPError) as e:
                # Maintenance pages, 5xx, no connection: one shared back-off, so the requests
                # queued on this lock don't each run the whole handshake again.
                error = self._pause(e if isinstance(e, KlasUnavailable) else
                                    KlasUnavailable(f"KLAS에 로그인하지 못했습니다({_describe(e)})."))
                self.last_login = {"at": _now_text(), "ok": False, "error": str(error)}
                raise error from e
            self._generation += 1
            self.last_login = {"at": _now_text(), "ok": True, "error": None}
            await self._forget_rejection()

    def _fail_login(self, error: KlasLoginError, retry_after: float) -> None:
        self._login_failure = (time.monotonic() + retry_after, error)
        self.last_login = {"at": _now_text(), "ok": False, "error": str(error)}

    # -- the on-disk marker (blocking file and PBKDF2 work runs in a thread) ----------------------

    def _fingerprint_sync(self, salt: str) -> str:
        if self._fp is None or self._fp[0] != salt:
            self._fp = (salt, _fingerprint(self._login_id, self._password, salt))
        return self._fp[1]

    async def _fingerprint(self, salt: str) -> str:
        return await asyncio.to_thread(self._fingerprint_sync, salt)

    async def _check_marker(self) -> None:
        state = await asyncio.to_thread(_read_state)
        entry, salt = state.get("rejected"), state.get("salt")
        self._marker_checked = True
        if not isinstance(entry, dict) or not isinstance(salt, str):
            return
        if await self._fingerprint(salt) != entry.get("fingerprint"):
            return
        hint = self._login_hint or "학번과 비밀번호를 다시 저장하세요."
        error = KlasBadPassword(
            f"KLAS가 이 학번·비밀번호를 거부했습니다({entry.get('at') or '이전'}). — {hint} "
            "같은 비밀번호는 다시 보내지 않습니다(보안문자 방지). 고치면 다음 요청에서 바로 로그인합니다.")
        self._fail_login(error, math.inf)
        raise error

    async def _remember_rejection(self) -> None:
        def write() -> None:
            state = _read_state()
            salt = state.get("salt") if isinstance(state.get("salt"), str) else secrets.token_hex(16)
            rejected = {"fingerprint": self._fingerprint_sync(salt), "at": _now_text()}
            _write_state({**state, "salt": salt, "rejected": rejected})

        with contextlib.suppress(OSError, ValueError):
            await asyncio.to_thread(write)

    async def _forget_rejection(self) -> None:
        state = await asyncio.to_thread(_read_state)
        entry, salt = state.get("rejected"), state.get("salt")
        if isinstance(entry, dict) and isinstance(salt, str) and await self._fingerprint(salt) == entry.get("fingerprint"):
            await asyncio.to_thread(forget_rejected_login)

    # -- requests --------------------------------------------------------------------------------

    async def _throttle(self) -> None:
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

    def _status_error(self, path: str, status: int) -> KlasError:
        if status in _TRANSIENT_STATUS:
            return self._pause(KlasUnavailable(f"{path}: HTTP {status}"))
        return KlasError(f"{path}: HTTP {status}")

    async def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        await self._throttle()
        async with self._slots:
            try:
                return await self._http.request(method, path, **kwargs)
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                self._pause(KlasUnavailable(f"KLAS에 연결하지 못했습니다({e.__class__.__name__})."))
                raise

    async def _login(self) -> None:
        self._http.cookies.clear()
        # Loading the form first gives us the session cookie the login calls are tied to.
        form = await self._send("GET", LOGIN_FORM)
        if form.status_code in (401, 403, 406):
            raise KlasClientRejected(
                f"KLAS가 이 도구(kw-mcp)의 접속을 거부했습니다(HTTP {form.status_code}). 위장해서 다시 시도하지 않고 "
                f"멈춥니다. 브라우저에서 KLAS를 이용하고, {CONTACT_URL} 에 알려 주세요.")
        if form.status_code >= 400:
            raise self._status_error(LOGIN_FORM, form.status_code)

        try:
            security = await self._raw_post(LOGIN_SECURITY, {})
        except SessionExpired as e:
            raise KlasUnavailable("KLAS 로그인 페이지가 응답하지 않습니다(점검 중일 수 있음).") from e
        public_key = security.get("publicKey") if isinstance(security, dict) else None
        if not public_key:
            raise KlasLoginError("KLAS did not return a login public key")
        token = encrypt_login(public_key, self._login_id, self._password)

        failures = await self._raw_post(LOGIN_CAPTCHA, {"loginToken": token, "captcha": ""})
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
        )
        if not isinstance(result, dict):
            raise KlasLoginError("Unexpected login response from KLAS")
        if result.get("errorCount", 1) != 0:
            message = _error_message(result) or "KLAS 로그인 실패 (아이디/비밀번호 확인)"
            hint = self._login_hint or "학번과 비밀번호를 다시 저장하세요."
            raise KlasBadPassword(
                f"{message} — {hint} 고치면 다음 요청에서 바로 다시 로그인합니다. 그대로 두면 "
                "보안문자가 걸리지 않도록 같은 비밀번호로는 다시 로그인하지 않습니다."
            )

        info = result.get("response") or {}
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

    async def _raw_post(self, path: str, body: dict[str, Any], allow_empty: bool = False) -> Any:
        resp = await self._send(
            "POST",
            path,
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
            raise self._status_error(path, resp.status_code)
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

    async def _raw_download(self, request: httpx.Request, max_bytes: int) -> bytes:
        path = request.url.path
        too_large = KlasError(f"파일이 너무 큽니다({max_bytes // (1024 * 1024)}MB 넘음). KLAS에서 직접 내려받아 주세요.")
        await self._throttle()
        async with self._slots:
            try:
                resp = await self._http.send(request, stream=True)
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                self._pause(KlasUnavailable(f"KLAS에 연결하지 못했습니다({e.__class__.__name__})."))
                raise
            try:
                if resp.is_redirect:
                    if LOGIN_FORM in resp.headers.get("location", ""):
                        raise SessionExpired(f"{path}: redirected to the login page")
                    raise KlasError(f"{path}: unexpected redirect")
                if resp.status_code >= 400:
                    raise self._status_error(path, resp.status_code)
                if (_int(resp.headers.get("content-length")) or 0) > max_bytes:
                    raise too_large
                kind = resp.headers.get("content-type", "")
                is_file = "attachment" in resp.headers.get("content-disposition", "").lower()
                if not is_file and ("text/html" in kind or "application/json" in kind):
                    self._check_download_page(path, await _read_capped(resp, MAX_ERROR_BODY), kind)
                chunks, total = [], 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise too_large
                    chunks.append(chunk)
            finally:
                await resp.aclose()
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
