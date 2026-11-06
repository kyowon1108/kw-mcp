"""KLAS client after review 1: honest User-Agent, rejected logins that stay rejected, a shared
back-off when KLAS is down, request pacing, stricter expiry and download checks."""

import asyncio
import json
import math
import time
from collections import Counter

import httpx
import pytest

from kw_mcp import credentials, holder, klas
from kw_mcp.klas import (
    CAPTCHA_THRESHOLD,
    LOGIN_CAPTCHA,
    LOGIN_CONFIRM,
    LOGIN_FORM,
    LOGIN_SECURITY,
    TWO_FACTOR_COOLDOWN,
    KlasBadPassword,
    KlasClient,
    KlasClientRejected,
    KlasError,
    KlasLoginBlocked,
    KlasRequestLimit,
    KlasUnavailable,
)
from tests.test_klas import LOGIN_PAGE_HTML, LOGIN_REQUIRED, keypair  # noqa: F401 (fixture)

DATA = "/std/lis/evltn/TaskStdList.do"
FILE = "/common/file/DownloadFile/F1/1"
OK = {"errorCount": 0, "response": {"twoFactorAt": "N", "certOpt": "N", "gradAt": "N"}}
REJECTED = {"fieldErrors": [{"field": "", "message": "개인번호 또는 비밀번호가 일치하지 않습니다."}],
            "response": {}, "errorCount": 1}


class Klas:
    """A fake KLAS whose answers each test sets; counts every path and the User-Agents it saw."""

    def __init__(self, public_key: str, *, confirm: dict | None = None, failures: int = 0) -> None:
        self.public_key = public_key
        self.confirm = confirm or OK
        self.failures = failures
        self.counts: Counter[str] = Counter()
        self.agents: set[str] = set()
        self.form = lambda: httpx.Response(200, text="<html/>")
        self.security = lambda: httpx.Response(200, json={"publicKey": self.public_key})
        self.data = lambda request: httpx.Response(200, json=[{"ok": True}])

    async def handle(self, request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.001)  # let parallel requests interleave
        path = request.url.path
        self.counts[path] += 1
        self.agents.add(request.headers.get("user-agent", ""))
        if path == LOGIN_FORM:
            return self.form()
        if path == LOGIN_SECURITY:
            return self.security()
        if path == LOGIN_CAPTCHA:
            return httpx.Response(200, json=self.failures)
        if path == LOGIN_CONFIRM:
            return httpx.Response(200, json=self.confirm)
        return self.data(request)


def client(fake: Klas, login_id: str = "2022123480", password: str = "pw") -> KlasClient:
    return KlasClient(login_id, password, transport=httpx.MockTransport(fake.handle))


# -- identity ------------------------------------------------------------------------------------

async def test_user_agent_names_the_tool_its_version_and_a_contact(keypair):  # noqa: F811
    fake = Klas(keypair[1])
    async with client(fake) as c:
        await c.post(DATA)
    assert klas.USER_AGENT == (f"kw-mcp/{klas.package_version()} "
                               "(+https://github.com/kyowon1108/kw-mcp; contact kyowon1108@gmail.com)")
    assert fake.agents == {klas.USER_AGENT}  # every request, login included
    assert "Mozilla" not in klas.USER_AGENT and "Chrome" not in klas.USER_AGENT


async def test_klas_refusing_the_tool_stops_it_without_a_disguise(keypair):  # noqa: F811
    fake = Klas(keypair[1])
    fake.form = lambda: httpx.Response(403, text="forbidden")
    async with client(fake) as c:
        for _ in range(3):
            with pytest.raises(KlasClientRejected, match="거부"):
                await c.post(DATA)
    assert fake.counts[LOGIN_FORM] == 1 and fake.counts[LOGIN_CONFIRM] == 0
    assert fake.agents == {klas.USER_AGENT}  # never retried as a browser


# -- rejected passwords --------------------------------------------------------------------------

async def test_a_rejected_password_is_not_sent_again_even_hours_later(keypair, monkeypatch):  # noqa: F811
    fake = Klas(keypair[1], confirm=REJECTED)
    async with client(fake) as c:
        with pytest.raises(KlasBadPassword, match="일치하지 않습니다"):
            await c.post(DATA)
        shift = [0.0]
        real = time.monotonic
        monkeypatch.setattr(klas.time, "monotonic", lambda: real() + shift[0])
        shift[0] = 6 * 3600.0  # the old 10-minute cooldown is long gone
        for _ in range(3):
            with pytest.raises(KlasBadPassword):
                await c.post(DATA)
        assert c.last_login["ok"] is False
    assert fake.counts[LOGIN_CONFIRM] == 1


async def test_a_rejection_survives_a_restart_until_the_login_changes(keypair, login_state_in_tmp):  # noqa: F811
    fake = Klas(keypair[1], confirm=REJECTED)
    async with client(fake, password="wrong") as c:
        with pytest.raises(KlasBadPassword):
            await c.post(DATA)
    saved = login_state_in_tmp.read_text()
    assert "wrong" not in saved and "2022123480" not in saved  # a salted fingerprint, no password, no id
    assert klas.rejected_login()["at"]

    async with client(fake, password="wrong") as c:  # a restart: same login, nothing sent to KLAS
        with pytest.raises(KlasBadPassword, match="거부"):
            await c.post(DATA)
    assert fake.counts[LOGIN_FORM] == 1 and fake.counts[LOGIN_CONFIRM] == 1

    fake.confirm = OK
    async with client(fake, password="right") as c:  # a fixed password logs in at once
        await c.post(DATA)
    assert fake.counts[LOGIN_CONFIRM] == 2


async def test_logging_in_with_the_rejected_login_after_saving_it_again_clears_the_record(
        keypair, login_state_in_tmp, monkeypatch):  # noqa: F811
    fake = Klas(keypair[1], confirm=REJECTED)
    async with client(fake) as c:
        with pytest.raises(KlasBadPassword):
            await c.post(DATA)
    saved = {}
    monkeypatch.setattr(credentials.keyring, "get_password", lambda service, user: saved.get(user))
    monkeypatch.setattr(credentials.keyring, "set_password", lambda service, user, value: saved.update({user: value}))
    credentials.save("2022123480", "pw")  # `kw-mcp setup` (e.g. after changing the password back in KLAS)
    assert klas.rejected_login() is None
    fake.confirm = OK
    async with client(fake) as c:
        await c.post(DATA)
    assert fake.counts[LOGIN_CONFIRM] == 2


async def test_login_stops_before_the_password_once_failures_reach_the_threshold(keypair):  # noqa: F811
    fake = Klas(keypair[1], failures=CAPTCHA_THRESHOLD)
    async with client(fake) as c:
        with pytest.raises(KlasLoginBlocked, match="캡차"):
            await c.post(DATA)
    assert fake.counts[LOGIN_CAPTCHA] == 1 and fake.counts[LOGIN_CONFIRM] == 0


@pytest.mark.parametrize(("response", "message", "retry_after"), [
    ({"frstPwdAt": "Y"}, "비밀번호 변경", math.inf),
    ({"twoFactorAt": "Y"}, "2차 인증", TWO_FACTOR_COOLDOWN),
    ({"certOpt": "Y"}, "임시 비밀번호", math.inf),
])
async def test_blocked_logins_wait_for_a_person(keypair, response, message, retry_after):  # noqa: F811
    fake = Klas(keypair[1], confirm={"errorCount": 0, "response": response})
    async with client(fake) as c:
        with pytest.raises(KlasLoginBlocked, match=message) as caught:
            await c.post(DATA)
        with pytest.raises(KlasLoginBlocked):
            await c.post(DATA)
    assert caught.value.retry_after == retry_after
    assert fake.counts[LOGIN_CONFIRM] == 1


# -- KLAS down, maintenance, expiry --------------------------------------------------------------

async def test_klas_down_means_one_login_for_a_burst_and_a_shared_pause(keypair):  # noqa: F811
    fake = Klas(keypair[1])
    fake.security = lambda: httpx.Response(503)
    async with client(fake) as c:
        results = await asyncio.gather(*(c.post(DATA) for _ in range(8)), return_exceptions=True)
        assert all(isinstance(r, KlasUnavailable) for r in results)
        assert fake.counts[LOGIN_FORM] == 1 and fake.counts[LOGIN_SECURITY] == 1
        with pytest.raises(KlasUnavailable, match="30초"):  # within the pause: no request at all
            await c.post(DATA)
        assert sum(fake.counts.values()) == 2
        fake.security = lambda: httpx.Response(200, json={"publicKey": fake.public_key})
        c._unavailable = (0.0, c._unavailable[1])  # the pause is over
        assert await c.post(DATA) == [{"ok": True}]
    assert fake.counts[LOGIN_CONFIRM] == 1


async def test_a_maintenance_page_at_login_is_not_retried_by_every_request(keypair):  # noqa: F811
    fake = Klas(keypair[1])
    fake.security = lambda: httpx.Response(200, text="<html>시스템 점검 중</html>", headers={"content-type": "text/html"})
    async with client(fake) as c:
        results = await asyncio.gather(*(c.post(DATA) for _ in range(8)), return_exceptions=True)
    assert all(isinstance(r, KlasUnavailable) for r in results)
    assert fake.counts[LOGIN_SECURITY] == 1


async def test_a_503_on_data_pauses_the_next_requests(keypair):  # noqa: F811
    fake = Klas(keypair[1])
    fake.data = lambda request: httpx.Response(503)
    async with client(fake) as c:
        with pytest.raises(KlasUnavailable, match="503"):
            await c.post(DATA)
        with pytest.raises(KlasUnavailable, match="멈춥니다"):
            await c.post(DATA)
    assert fake.counts[DATA] == 1


async def test_html_that_is_not_the_login_page_is_an_error_not_an_expired_session(keypair):  # noqa: F811
    fake = Klas(keypair[1])
    fake.data = lambda request: httpx.Response(200, text="<html>오류</html>", headers={"content-type": "text/html"})
    async with client(fake) as c:
        with pytest.raises(KlasError, match="웹 페이지"):
            await c.post(DATA)
    assert fake.counts[LOGIN_CONFIRM] == 1  # no second login


async def test_an_error_shaped_answer_is_an_error(keypair):  # noqa: F811
    fake = Klas(keypair[1])
    fake.data = lambda request: httpx.Response(200, json={"errorCount": 1, "fieldErrors": [{"message": "권한이 없습니다"}]})
    async with client(fake) as c:
        with pytest.raises(KlasError, match="권한이 없습니다"):
            await c.post(DATA)


# -- pacing --------------------------------------------------------------------------------------

async def test_requests_stop_at_the_ten_minute_cap(keypair, monkeypatch):  # noqa: F811
    monkeypatch.setattr(klas, "WINDOW_CAP", 6)  # 4 login requests + 2 reads
    fake = Klas(keypair[1])
    async with client(fake) as c:
        await c.post(DATA)
        await c.post(DATA)
        assert c.recent_requests() == 6
        for _ in range(2):  # stays a clear limit error, not a "KLAS is down" pause
            with pytest.raises(KlasRequestLimit, match="학교 서버 보호"):
                await c.post(DATA)
    assert fake.counts[DATA] == 2


async def test_requests_are_paced_by_a_token_bucket(keypair, monkeypatch):  # noqa: F811
    monkeypatch.setattr(klas, "RATE_BURST", 1)
    monkeypatch.setattr(klas, "RATE_PER_S", 40.0)
    fake = Klas(keypair[1])
    async with client(fake) as c:
        started = time.monotonic()
        await asyncio.gather(*(c.post(DATA) for _ in range(5)))
        elapsed = time.monotonic() - started
    assert elapsed >= 0.15  # 9 requests at 40/s after a burst of 1: at least 8 waits of 25 ms


# -- downloads -----------------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/common/file/DownloadFile/../../../usr/cmn/login/Logout.do",
    "/common/file/DownloadFile/%2e%2e/%2E%2E/std/cmn/frame/StdHome.do",
    "/common/file/DownloadFile/F1/1?next=/usr/cmn/login/Logout.do",
    "/common/file/DownloadFile/F1/./1",
    "/common/file/DownloadFile//klas.example/x",
    "/common/file/DownloadFile/F1\\..\\..\\x",
])
async def test_download_refuses_paths_that_leave_the_attachment_folder(path):
    def no_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"sent {request.url}")

    async with KlasClient("id", "pw", transport=httpx.MockTransport(no_request)) as c:
        with pytest.raises(KlasError, match="only attachment downloads"):
            await c.download(path, 1000)


@pytest.mark.parametrize("expired", [
    httpx.Response(200, json=LOGIN_REQUIRED),
    httpx.Response(200, text=LOGIN_PAGE_HTML, headers={"content-type": "text/html"}),
])
async def test_an_expired_session_on_a_download_logs_in_again(keypair, expired):  # noqa: F811
    fake = Klas(keypair[1])
    answers = iter([expired, httpx.Response(200, content=b"%PDF-1.4 data",
                                            headers={"content-disposition": "attachment; filename=a.pdf"})])
    fake.data = lambda request: httpx.Response(200, json=[]) if request.url.path == DATA else next(answers)
    async with client(fake) as c:
        await c.post(DATA)
        assert await c.download(FILE, 1000) == b"%PDF-1.4 data"
    assert fake.counts[LOGIN_CONFIRM] == 2 and fake.counts[FILE] == 2


async def test_an_attachment_that_is_itself_html_is_still_a_file(keypair):  # noqa: F811
    fake = Klas(keypair[1])
    fake.data = lambda request: httpx.Response(200, text=LOGIN_PAGE_HTML, headers={
        "content-type": "text/html", "content-disposition": "attachment; filename=week1.html"})
    async with client(fake) as c:
        assert b"loginForm" in await c.download(FILE, 10_000)
    assert fake.counts[LOGIN_CONFIRM] == 1


async def test_a_file_over_the_limit_is_refused(keypair):  # noqa: F811
    fake = Klas(keypair[1])
    fake.data = lambda request: httpx.Response(200, content=b"x" * 100, headers={"content-disposition": "attachment"})
    async with client(fake) as c:
        with pytest.raises(KlasError, match="너무 큽니다"):
            await c.download(FILE, 10)


# -- login id masking and the holder --------------------------------------------------------------

def test_masked_id_shows_only_the_admission_year_and_length():
    assert credentials.masked_id("2022123480") == "2022******(10자리)"
    assert credentials.masked_id("MyS3cretPassw0rd!") == "*****************(17자리)"
    assert credentials.masked_id("kw2022") == "******(6자리)"


async def test_a_login_change_does_not_close_the_client_still_in_use(monkeypatch):
    logins = iter([credentials.Credentials("2022123480", "old", credentials.ENV),
                   credentials.Credentials("2022123480", "new", credentials.ENV)])
    monkeypatch.setattr(credentials, "load", lambda: next(logins))
    h = holder.KlasHolder()
    first = await h.service()
    old_client = first._client
    second = await h.service()
    assert second is not first and not old_client._http.is_closed  # in-flight requests can finish
    assert h.status()["login_id"] == "2022******(10자리)" and "new" not in json.dumps(h.status())
    await h.aclose()
    assert old_client._http.is_closed and second._client._http.is_closed
