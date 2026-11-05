"""Low-level KLAS (klas.kw.ac.kr) HTTP client.

KLAS has no public API. The web UI (Vue + axios) talks to `*.do` endpoints that
take a JSON body and return JSON, guarded by a session cookie. This client logs
in the same way the login page does and re-logs in once when the session expires.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_der_public_key

BASE_URL = "https://klas.kw.ac.kr"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
)

LOGIN_FORM = "/usr/cmn/login/LoginForm.do"
LOGIN_SECURITY = "/usr/cmn/login/LoginSecurity.do"
LOGIN_CAPTCHA = "/usr/cmn/login/LoginCaptcha.do"
LOGIN_CONFIRM = "/usr/cmn/login/LoginConfirm.do"
DOWNLOAD_PREFIX = "/common/file/DownloadFile/"

# The login page asks for a captcha once LoginCaptcha.do reports more than this many failures.
CAPTCHA_THRESHOLD = 2
# After a rejected login, fail fast for this long instead of retrying. Retries with a wrong
# password would push the account over the captcha threshold.
LOGIN_COOLDOWN = 600.0
# Upper bound on requests in flight to KLAS from this client.
MAX_PARALLEL = 4


class KlasError(Exception):
    """A KLAS request failed."""


class KlasLoginError(KlasError):
    """Login was rejected or needs a step this client cannot do (captcha, 2FA)."""


class KlasLoginBlocked(KlasLoginError):
    """KLAS wants a person at the keyboard (captcha, 2FA, password change); retrying won't help."""


class KlasBadPassword(KlasLoginError):
    """KLAS rejected the id/password. Retrying with the same password only adds failures."""


class SessionExpired(KlasError):
    """KLAS answered with the login page instead of JSON."""


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
        self._login_failure: tuple[float, KlasLoginError] | None = None

    async def __aenter__(self) -> KlasClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def login(self) -> None:
        """Log in now, even if a session exists."""
        await self._relogin(self._generation)

    async def post(self, path: str, body: dict[str, Any] | None = None, *, allow_empty: bool = False) -> Any:
        """POST a JSON body to a KLAS endpoint, logging in (again) when needed. An empty answer is an
        error unless allow_empty (then None): elsewhere it would read as "nothing due"."""
        generation = self._generation
        if generation == 0:
            await self._relogin(0)
            generation = self._generation
        try:
            return await self._raw_post(path, body or {}, allow_empty)
        except SessionExpired:
            await self._relogin(generation)
            return await self._raw_post(path, body or {}, allow_empty)

    async def download(self, path: str, max_bytes: int) -> bytes:
        """GET a file (attachment download), logging in again if the session expired."""
        if not path.startswith(DOWNLOAD_PREFIX):
            raise KlasError(f"refusing to fetch {path!r}: only attachment downloads are allowed")
        generation = self._generation
        if generation == 0:
            await self._relogin(0)
            generation = self._generation
        try:
            return await self._raw_download(path, max_bytes)
        except SessionExpired:
            await self._relogin(generation)
            return await self._raw_download(path, max_bytes)

    async def _raw_download(self, path: str, max_bytes: int) -> bytes:
        async with self._slots, self._http.stream("GET", path) as resp:
            if resp.is_redirect:
                if LOGIN_FORM in resp.headers.get("location", ""):
                    raise SessionExpired(f"{path}: redirected to the login page")
                raise KlasError(f"{path}: unexpected redirect")
            if resp.status_code >= 400:
                raise KlasError(f"{path}: HTTP {resp.status_code}")
            if "text/html" in resp.headers.get("content-type", ""):
                raise SessionExpired(f"{path}: got an HTML page instead of a file")
            chunks, total = [], 0
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise KlasError(f"파일이 너무 큽니다({max_bytes // (1024 * 1024)}MB 넘음).")
                chunks.append(chunk)
        return b"".join(chunks)

    async def _relogin(self, seen_generation: int) -> None:
        async with self._login_lock:
            if self._login_failure:
                failed_at, error = self._login_failure
                if time.monotonic() - failed_at < LOGIN_COOLDOWN:
                    raise error
                self._login_failure = None
            if self._generation != seen_generation:
                return  # another request already logged in while we waited
            try:
                await self._login()
            except KlasLoginError as e:
                self._login_failure = (time.monotonic(), e)
                raise
            self._generation += 1

    async def _login(self) -> None:
        self._http.cookies.clear()
        # Loading the form first gives us the session cookie the login calls are tied to.
        await self._http.get(LOGIN_FORM)

        security = await self._raw_post(LOGIN_SECURITY, {})
        public_key = security.get("publicKey") if isinstance(security, dict) else None
        if not public_key:
            raise KlasLoginError("KLAS did not return a login public key")
        token = encrypt_login(public_key, self._login_id, self._password)

        failures = await self._raw_post(LOGIN_CAPTCHA, {"loginToken": token, "captcha": ""})
        try:
            failures = int(failures)
        except (TypeError, ValueError):
            raise KlasLoginError("KLAS 로그인 응답 형식이 바뀌어 로그인을 중단했습니다.") from None
        if failures > CAPTCHA_THRESHOLD:
            raise KlasLoginBlocked(
                "로그인 실패가 누적되어 KLAS가 캡차를 요구합니다. "
                "브라우저에서 한 번 직접 로그인한 뒤 MCP 서버를 다시 시작하세요."
            )

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
                f"캡차가 걸리지 않도록 {int(LOGIN_COOLDOWN // 60)}분 동안 재시도하지 않습니다."
            )

        info = result.get("response") or {}
        if info.get("twoFactorAt") == "Y":
            # Since 2026-10-26 KLAS asks for 2FA on logins from IPs it treats as foreign
            # (notice DUID 53483); cloud servers and VPNs count. Never try to get around it.
            raise KlasLoginBlocked(
                "KLAS가 이 로그인에 2차 인증을 요구합니다(해외로 보이는 IP에서 로그인하면 요구함). "
                "국내 인터넷에 연결된 PC에서, VPN을 끄고 실행하세요."
            )
        if info.get("certOpt") == "Y":
            raise KlasLoginBlocked("KLAS 임시 비밀번호 상태입니다. 브라우저에서 비밀번호를 먼저 변경하세요.")
        if info.get("gradAt") == "Y":
            raise KlasLoginBlocked("졸업생 계정은 KLAS를 이용할 수 없습니다.")

    async def _raw_post(self, path: str, body: dict[str, Any], allow_empty: bool = False) -> Any:
        async with self._slots:
            resp = await self._http.post(
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
            raise KlasError(f"{path}: HTTP {resp.status_code}")
        if allow_empty and not resp.content.strip():
            return None  # LctreEvlTermCheck says "not the evaluation period" with an empty body
        try:
            data = resp.json()
        except ValueError:
            if "text/html" in resp.headers.get("content-type", ""):
                raise SessionExpired(f"{path}: got an HTML page instead of JSON") from None
            raise KlasError(f"{path}: response is not JSON") from None
        # To the site's own AJAX calls (our headers) a dead session isn't a 302 but 200 with
        # {"loginRequired": true, "redirect": true, "redirectUrl": "/usr/cmn/login/LoginForm.do?..."}
        # (checked 2026-11-06). Read as data it looks like "no courses, nothing due".
        if isinstance(data, dict) and data.get("loginRequired") is True:
            raise SessionExpired(f"{path}: KLAS asked to log in again")
        return data


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
