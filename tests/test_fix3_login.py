"""Review 3, login group: a correct password is never locked out by a cookie race, only KLAS's
mismatch answer stops a password for good, saving the same login again lifts a running block, the
shared back-off stops queued requests and hanging answers, KLAS refusing the tool stops it at every
login step, stricter download paths, KlasFileTooLarge, a contact that works, and a lazy klas import."""

import asyncio
import json
import math
import random
import subprocess
import sys
import threading
import time
from collections import Counter

import httpx
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from kw_mcp import credentials, holder, klas, server
from kw_mcp.klas import (
    LOGIN_BLOCK_COOLDOWN,
    LOGIN_CAPTCHA,
    LOGIN_CONFIRM,
    LOGIN_FORM,
    LOGIN_SECURITY,
    MAX_PARALLEL,
    MAX_REJECTED,
    TRANSIENT_BACKOFF,
    KlasBadPassword,
    KlasClient,
    KlasClientRejected,
    KlasError,
    KlasFileTooLarge,
    KlasLoginBlocked,
    KlasLoginError,
    KlasUnavailable,
)
from kw_mcp.public_api import PublicApi
from tests.test_core_klas import DATA, FILE, OK, REJECTED, Klas, client
from tests.test_klas import LOGIN_REQUIRED, keypair  # noqa: F401 (fixture)

ID = "2022123480"
OTHER = "/std/cps/inqire/AtnlcScreSungjukInfo.do"
THIRD = "/std/lis/evltn/OnlineCntntsStdList.do"


def later(monkeypatch, seconds: float) -> None:
    real = time.monotonic
    monkeypatch.setattr(klas.time, "monotonic", lambda: real() + seconds)


def fast_pacing(monkeypatch) -> None:
    """Many logins in one test: lift this client's own pacing so the test is quick."""
    monkeypatch.setattr(klas, "RATE_PER_S", 1e6)
    monkeypatch.setattr(klas, "RATE_BURST", 10_000)
    monkeypatch.setattr(klas, "WINDOW_CAP", 100_000)


# -- B1: only the mismatch answer is permanent ---------------------------------------------------

@pytest.mark.parametrize("answer", [
    {"errorCount": 1, "fieldErrors": [{"field": "", "message": "세션 정보가 올바르지 않습니다."}]},
    {"errorCount": 1, "response": {}},
    {"errorCount": "2", "error": "로그인 키가 만료되었습니다"},
    {"response": {}},  # no errorCount at all
])
async def test_an_unknown_login_error_is_retried_after_the_cooldown_not_for_good(keypair, monkeypatch, answer):  # noqa: F811
    fake = Klas(keypair[1], confirm=answer)
    async with client(fake) as c:
        with pytest.raises(KlasLoginError, match="10분 뒤 다시 시도") as caught:
            await c.post(DATA)
        assert not isinstance(caught.value, KlasBadPassword)
        with pytest.raises(KlasLoginError):  # within the cooldown: nothing sent
            await c.post(DATA)
        assert fake.counts[LOGIN_CONFIRM] == 1
        assert klas.rejected_login() is None  # nothing written to disk
        fake.confirm = OK
        later(monkeypatch, LOGIN_BLOCK_COOLDOWN + 1)
        assert await c.post(DATA) == [{"ok": True}]
    assert fake.counts[LOGIN_CONFIRM] == 2


@pytest.mark.parametrize("message", ["개인번호 또는 비밀번호가 일치하지 않습니다.", "아이디 또는 비밀번호가 일치하지않습니다"])
async def test_the_mismatch_answer_still_stops_the_password_for_good(keypair, monkeypatch, message):  # noqa: F811
    fake = Klas(keypair[1], confirm={"errorCount": 1, "fieldErrors": [{"field": "", "message": message}]})
    async with client(fake) as c:
        with pytest.raises(KlasBadPassword, match="일치하지"):
            await c.post(DATA)
        later(monkeypatch, 24 * 3600.0)
        with pytest.raises(KlasBadPassword):
            await c.post(DATA)
    assert fake.counts[LOGIN_CONFIRM] == 1
    assert klas.rejected_login(ID, "pw")["at"]


def _cookie(request: httpx.Request, name: str) -> str | None:
    for part in request.headers.get("cookie", "").split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value
    return None


class SessionKlas:
    """A fake KLAS with real sessions, Spring-style: LoginForm opens a session, LoginSecurity ties the
    key to it, and LoginConfirm on any other session gives the mismatch answer (the worst case). A
    data request on an unknown or expired session gets loginRequired AND a new session cookie."""

    def __init__(self, public_key: str, seed: int) -> None:
        self.public_key = public_key
        self.rng = random.Random(seed)
        self.sessions: dict[str, str] = {}  # id -> "open" | "keyed" | "auth"
        self.issued = 0
        self.counts: Counter[str] = Counter()
        self.mismatches = 0
        self.events: list[tuple[str, str]] = []

    def expire_all(self) -> None:
        self.sessions.clear()

    def _open(self) -> tuple[str, dict[str, str]]:
        self.issued += 1
        sid = f"S{self.issued}"
        self.sessions[sid] = "open"
        return sid, {"set-cookie": f"SESSION={sid}; Path=/"}

    async def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.counts[path] += 1
        self.events.append(("start", path))
        try:
            await asyncio.sleep(self.rng.uniform(0, 0.004))
            return self._answer(request, path)
        finally:
            self.events.append(("end", path))

    def _answer(self, request: httpx.Request, path: str) -> httpx.Response:
        sid = _cookie(request, "SESSION")
        state = self.sessions.get(sid or "")
        if path == LOGIN_FORM:
            _, headers = self._open()
            return httpx.Response(200, text="<html/>", headers=headers)
        if path == LOGIN_SECURITY:
            headers = {}
            if state is None:
                sid, headers = self._open()
            self.sessions[sid] = "keyed"
            return httpx.Response(200, json={"publicKey": self.public_key}, headers=headers)
        if path == LOGIN_CAPTCHA:
            return httpx.Response(200, json=0)
        if path == LOGIN_CONFIRM:
            if state != "keyed":  # the key was issued to another session
                self.mismatches += 1
                return httpx.Response(200, json=REJECTED)
            self.sessions[sid] = "auth"
            return httpx.Response(200, json=OK)
        if state == "auth":
            return httpx.Response(200, json=[{"ok": True}])
        _, headers = self._open()
        return httpx.Response(200, json=LOGIN_REQUIRED, headers=headers)


@pytest.mark.parametrize("width", [MAX_PARALLEL, 2 * MAX_PARALLEL])
async def test_a_burst_at_session_expiry_never_locks_out_a_correct_password(keypair, monkeypatch, width):  # noqa: F811
    fast_pacing(monkeypatch)
    fake = SessionKlas(keypair[1], seed=width)
    rounds = 25
    async with client(fake) as c:
        assert await c.post(DATA) == [{"ok": True}]
        for _ in range(rounds):
            fake.expire_all()
            results = await asyncio.gather(*(c.post(DATA) for _ in range(width)), return_exceptions=True)
            assert results == [[{"ok": True}]] * width
    assert fake.mismatches == 0 and klas.rejected_login() is None
    assert fake.counts[LOGIN_CONFIRM] == rounds + 1  # one login per expiry, however wide the burst
    # No data request was on the wire while a login handshake ran.
    in_login, overlaps = False, 0
    for event, path in fake.events:
        if (event, path) == ("start", LOGIN_FORM):
            in_login = True
        elif (event, path) == ("end", LOGIN_CONFIRM):
            in_login = False
        elif path == DATA and in_login:
            overlaps += 1
    assert overlaps == 0


async def test_data_requests_wait_for_a_running_login_and_a_cancelled_login_lets_them_go(keypair):  # noqa: F811
    fake = Klas(keypair[1])
    stall = asyncio.Event()  # set: LoginSecurity hangs until the test lets it go
    release = asyncio.Event()

    async def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == LOGIN_SECURITY and stall.is_set():
            await release.wait()
        return await fake.handle(request)

    answers = iter([httpx.Response(200, json=LOGIN_REQUIRED)])
    async with KlasClient(ID, "pw", transport=httpx.MockTransport(handle)) as c:
        assert await c.post(DATA) == [{"ok": True}]
        fake.data = lambda request: next(answers, None) or httpx.Response(200, json=[{"ok": True}])
        stall.set()
        relogin = asyncio.create_task(c.post(DATA))  # the session expired: a login starts and hangs
        for _ in range(500):
            if fake.counts[LOGIN_FORM] == 2:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.01)  # LoginForm answered; LoginSecurity is now hanging
        assert fake.counts[LOGIN_FORM] == 2 and fake.counts[DATA] == 2
        waiting = asyncio.create_task(c.post(DATA))  # has a session, but must wait for the login
        await asyncio.sleep(0.05)
        assert fake.counts[DATA] == 2 and not waiting.done()
        relogin.cancel()
        with pytest.raises(asyncio.CancelledError):
            await relogin
        assert await asyncio.wait_for(waiting, 5) == [{"ok": True}]
        stall.clear()
        release.set()
        assert await asyncio.wait_for(c.post(DATA), 5) == [{"ok": True}]


# -- r1 #52 test gaps: gradAt, a download 302, transport errors during login ----------------------

async def test_a_graduate_account_stops_without_retrying(keypair):  # noqa: F811
    fake = Klas(keypair[1], confirm={"errorCount": 0, "response": {"gradAt": "Y"}})
    async with client(fake) as c:
        with pytest.raises(KlasLoginBlocked, match="졸업생") as caught:
            await c.post(DATA)
        with pytest.raises(KlasLoginBlocked):
            await c.post(DATA)
    assert caught.value.retry_after == float("inf") and fake.counts[LOGIN_CONFIRM] == 1


async def test_a_download_redirected_to_the_login_page_logs_in_again(keypair):  # noqa: F811
    fake = Klas(keypair[1])
    answers = iter([httpx.Response(302, headers={"location": f"{klas.BASE_URL}{LOGIN_FORM}?redirectUrl=x"}),
                    httpx.Response(200, content=b"%PDF-1.4 x", headers={"content-disposition": "attachment"})])
    fake.data = lambda request: httpx.Response(200, json=[]) if request.url.path == DATA else next(answers)
    async with client(fake) as c:
        await c.post(DATA)
        assert await c.download(FILE, 1000) == b"%PDF-1.4 x"
    assert fake.counts[LOGIN_CONFIRM] == 2 and fake.counts[FILE] == 2


async def test_a_download_redirected_elsewhere_is_an_error_not_a_login(keypair):  # noqa: F811
    fake = Klas(keypair[1])
    fake.data = lambda request: httpx.Response(302, headers={"location": "https://klas.kw.ac.kr/std/error.do"})
    async with client(fake) as c:
        with pytest.raises(KlasError, match="unexpected redirect"):
            await c.download(FILE, 1000)
    assert fake.counts[LOGIN_CONFIRM] == 1 and fake.counts[FILE] == 1


@pytest.mark.parametrize(("step", "error", "text"), [
    (LOGIN_FORM, httpx.ConnectError("refused"), "ConnectError"),
    (LOGIN_SECURITY, httpx.ConnectTimeout("slow"), "ConnectTimeout"),
    (LOGIN_CAPTCHA, httpx.ReadTimeout("hang"), "ReadTimeout"),
    (LOGIN_CONFIRM, httpx.RemoteProtocolError("closed"), "RemoteProtocolError"),
])
async def test_transport_errors_during_login_are_one_shared_pause_never_a_rejection(keypair, step, error, text):  # noqa: F811
    fake = Klas(keypair[1])
    sent: Counter[str] = Counter()

    async def handle(request: httpx.Request) -> httpx.Response:
        sent[request.url.path] += 1
        if request.url.path == step:
            raise error
        return await fake.handle(request)

    async with KlasClient(ID, "pw", transport=httpx.MockTransport(handle)) as c:
        results = await asyncio.gather(*(c.post(DATA) for _ in range(6)), return_exceptions=True)
        assert all(isinstance(r, KlasUnavailable) for r in results), results
        with pytest.raises(KlasUnavailable, match=text):
            await c.post(DATA)
    assert sent[step] == 1 and sent[DATA] == 0  # one handshake for the burst, then the pause
    assert klas.rejected_login() is None


# -- S01: the back-off also stops requests already queued ----------------------------------------

async def test_a_503_stops_the_requests_queued_behind_it(keypair):  # noqa: F811
    fake = Klas(keypair[1])
    fake.data = lambda request: httpx.Response(503)
    async with client(fake) as c:
        results = await asyncio.gather(*(c.post(DATA) for _ in range(20)), return_exceptions=True)
        assert c.recent_requests() == sum(fake.counts.values())  # the stopped ones don't count as sent
    assert all(isinstance(r, KlasUnavailable) for r in results)
    assert fake.counts[DATA] <= MAX_PARALLEL


async def test_requests_queued_behind_a_failed_login_are_not_sent(keypair):  # noqa: F811
    fake = Klas(keypair[1], confirm=REJECTED)
    async with client(fake) as c:
        results = await asyncio.gather(*(c.post(DATA) for _ in range(10)), return_exceptions=True)
    assert all(isinstance(r, KlasBadPassword) for r in results)
    assert fake.counts[DATA] == 0 and fake.counts[LOGIN_CONFIRM] == 1


# -- S02: saving the same login again lifts a running block; one entry per login ------------------

async def test_a_running_holder_tries_once_more_after_the_same_login_is_saved_again(keypair, monkeypatch):  # noqa: F811
    fake = Klas(keypair[1], confirm=REJECTED)
    creds = credentials.Credentials(ID, "pw", credentials.KEYCHAIN)
    monkeypatch.setattr(credentials, "load", lambda: creds)
    monkeypatch.setattr(holder, "KlasClient",
                        lambda *a, **k: KlasClient(*a, transport=httpx.MockTransport(fake.handle), **k))
    h = holder.KlasHolder()
    try:
        running = (await h.service())._client
        for _ in range(2):
            with pytest.raises(KlasBadPassword):
                await running.post(DATA)
        assert fake.counts[LOGIN_CONFIRM] == 1
        credentials.save(ID, "pw")  # `kw-mcp setup` with the same pair (changed back in KLAS)
        fake.confirm = OK
        assert (await h.service())._client is running  # same login: no new client
        assert await running.post(DATA) == [{"ok": True}]
        assert fake.counts[LOGIN_CONFIRM] == 2 and klas.rejected_login() is None
    finally:
        await h.aclose()


async def test_saving_again_allows_exactly_one_more_try(keypair):  # noqa: F811
    fake = Klas(keypair[1], confirm=REJECTED)
    async with client(fake) as c:
        with pytest.raises(KlasBadPassword):
            await c.post(DATA)
        credentials.save(ID, "pw")
        with pytest.raises(KlasBadPassword, match="일치하지"):  # still wrong: sent once more
            await c.post(DATA)
        for _ in range(3):
            with pytest.raises(KlasBadPassword):
                await c.post(DATA)
    assert fake.counts[LOGIN_CONFIRM] == 2 and klas.rejected_login(ID, "pw")


async def test_a_marker_that_could_not_be_written_keeps_the_block(keypair, tmp_path, monkeypatch):  # noqa: F811
    not_a_folder = tmp_path / "file"
    not_a_folder.write_text("")
    monkeypatch.setattr(klas, "LOGIN_STATE_FILE", not_a_folder / "login-state.json")
    fake = Klas(keypair[1], confirm=REJECTED)
    async with client(fake) as c:
        for _ in range(3):  # no marker on disk, but that is no reason to send the password again
            with pytest.raises(KlasBadPassword):
                await c.post(DATA)
    assert fake.counts[LOGIN_CONFIRM] == 1


async def test_a_rejection_by_another_process_is_seen_before_the_next_login(keypair):  # noqa: F811
    agent_side = Klas(keypair[1])
    async with client(agent_side) as running:
        await running.post(DATA)  # e.g. the PC agent, logged in
        server_side = Klas(keypair[1], confirm=REJECTED)
        async with client(server_side) as other:  # the MCP server, same pair, rejected
            with pytest.raises(KlasBadPassword):
                await other.post(DATA)
        agent_side.data = lambda request: httpx.Response(200, json=LOGIN_REQUIRED)  # the session expires
        with pytest.raises(KlasBadPassword, match="거부"):
            await running.post(DATA)
    assert agent_side.counts[LOGIN_FORM] == 1 and agent_side.counts[LOGIN_CONFIRM] == 1


async def test_rejections_are_kept_per_login_and_cleared_one_at_a_time(keypair, login_state_in_tmp):  # noqa: F811
    # a 0.9-era file: one dict, not a list
    klas._write_state({"salt": "00", "rejected": {"fingerprint": klas._fingerprint(ID, "old", "00"),
                                                   "at": "2026-11-01 09:00"}})
    assert klas.rejected_login(ID, "old")["at"] == "2026-11-01 09:00"
    fake = Klas(keypair[1], confirm=REJECTED)
    async with client(fake, password="new") as c:
        with pytest.raises(KlasBadPassword):
            await c.post(DATA)
    assert klas.rejected_login(ID, "old") and klas.rejected_login(ID, "new")
    assert klas.rejected_login(ID, "other") is None
    credentials.save(ID, "old")  # saving one login removes only its own record
    assert klas.rejected_login(ID, "old") is None and klas.rejected_login(ID, "new")
    saved = login_state_in_tmp.read_text()
    assert "new" not in saved and ID not in saved
    credentials.delete()  # no saved login any more: no record either
    assert klas.rejected_login() is None


async def test_only_the_latest_rejections_are_kept(keypair, login_state_in_tmp):  # noqa: F811
    fake = Klas(keypair[1], confirm=REJECTED)
    for n in range(MAX_REJECTED + 2):
        async with client(fake, password=f"pw{n}") as c:
            with pytest.raises(KlasBadPassword):
                await c.post(DATA)
    assert len(json.loads(login_state_in_tmp.read_text())["rejected"]) == MAX_REJECTED
    assert klas.rejected_login(ID, "pw0") is None and klas.rejected_login(ID, f"pw{MAX_REJECTED + 1}")


# -- S03: klas_status reports only this login's record, without the home path --------------------

async def _status(monkeypatch, creds_or_error) -> dict:
    def load():
        if isinstance(creds_or_error, Exception):
            raise creds_or_error
        return creds_or_error

    monkeypatch.setattr(credentials, "load", load)
    monkeypatch.delenv("KW_MCP_DISTRIBUTION", raising=False)
    server.set_public(PublicApi(""))
    try:
        return await server.klas_status()
    finally:
        server.set_public(None)


async def test_klas_status_ignores_a_record_of_another_login(monkeypatch):
    klas._write_state({"salt": "00", "rejected": [{"fingerprint": klas._fingerprint(ID, "typo", "00"),
                                                    "at": "2026-11-06 10:00"}]})
    fixed = credentials.Credentials(ID, "fixed", credentials.ENV)  # the typo was fixed in the settings
    assert (await _status(monkeypatch, fixed))["rejected_login"] is None
    missing = credentials.MissingCredentials("KLAS 로그인 정보가 없습니다.")
    assert (await _status(monkeypatch, missing))["rejected_login"] is None


async def test_klas_status_matches_the_record_off_the_event_loop(monkeypatch):
    klas._write_state({"salt": "00", "rejected": [{"fingerprint": klas._fingerprint(ID, "typo", "00"),
                                                    "at": "2026-11-06 10:00"}]})
    threads = []
    real = klas.rejected_login

    def spy(*args):
        threads.append(threading.current_thread() is threading.main_thread())
        return real(*args)

    monkeypatch.setattr(klas, "rejected_login", spy)
    out = await _status(monkeypatch, credentials.Credentials(ID, "typo", credentials.ENV))
    assert threads == [False]
    assert out["rejected_login"]["at"] == "2026-11-06 10:00"
    assert out["rejected_login"]["state_file"] == "~/.config/kw-mcp/login-state.json"
    text = json.dumps(out, ensure_ascii=False)
    assert str(klas.LOGIN_STATE_FILE) not in text and "typo" not in text and ID not in text


# -- S04: KLAS refusing the tool is honored at every login step and on data calls ----------------

@pytest.mark.parametrize("status", [401, 403, 406])
@pytest.mark.parametrize("step", [LOGIN_SECURITY, LOGIN_CAPTCHA, LOGIN_CONFIRM])
async def test_a_refusal_at_any_login_step_stops_the_client(keypair, step, status):  # noqa: F811
    fake = Klas(keypair[1])
    sent: Counter[str] = Counter()

    async def handle(request: httpx.Request) -> httpx.Response:
        sent[request.url.path] += 1
        if request.url.path == step:
            return httpx.Response(status, text="forbidden")
        return await fake.handle(request)

    async with KlasClient(ID, "pw", transport=httpx.MockTransport(handle)) as c:
        with pytest.raises(KlasClientRejected, match="거부") as caught:
            await c.post(DATA)
        total = sum(sent.values())
        for _ in range(3):
            with pytest.raises(KlasClientRejected):
                await c.post(DATA)
    assert caught.value.retry_after == float("inf") and sum(sent.values()) == total
    assert sent[step] == 1 and sent[DATA] == 0
    assert klas.CONTACT_EMAIL in str(caught.value) and "github" not in str(caught.value)


async def test_refusals_on_several_endpoints_stop_the_client(keypair):  # noqa: F811
    fake = Klas(keypair[1])
    fake.data = lambda request: httpx.Response(403, text="forbidden")
    async with client(fake) as c:
        for path in (DATA, OTHER):
            with pytest.raises(KlasError, match="HTTP 403") as caught:
                await c.post(path)
            assert not isinstance(caught.value, KlasClientRejected)
        with pytest.raises(KlasClientRejected, match="서로 다른 요청 3곳"):
            await c.post(THIRD)
        sent = sum(fake.counts.values())
        with pytest.raises(KlasClientRejected):
            await c.post(DATA)
        with pytest.raises(KlasClientRejected):
            await c.download(FILE, 1000)
    assert sum(fake.counts.values()) == sent


async def test_one_screen_that_refuses_does_not_stop_the_client(keypair):  # noqa: F811
    fake = Klas(keypair[1])
    fake.data = lambda request: (httpx.Response(200, json=[{"ok": True}]) if request.url.path == DATA
                                 else httpx.Response(403, text="forbidden"))
    async with client(fake) as c:
        for _ in range(5):  # the same screen again and again
            with pytest.raises(KlasError, match="HTTP 403"):
                await c.post(OTHER)
        for _ in range(3):  # two screens, but something works in between
            with pytest.raises(KlasError, match="HTTP 403"):
                await c.post(OTHER)
            with pytest.raises(KlasError, match="HTTP 403"):
                await c.post(THIRD)
            assert await c.post(DATA) == [{"ok": True}]
    assert fake.counts[OTHER] == 8 and fake.counts[THIRD] == 3


# -- S05: a hanging KLAS starts the shared back-off too ------------------------------------------

@pytest.mark.parametrize("error", [httpx.ReadTimeout("hang"), httpx.PoolTimeout("pool"),
                                   httpx.RemoteProtocolError("closed"), httpx.ConnectError("refused")])
async def test_a_hanging_answer_pauses_the_next_requests(keypair, error):  # noqa: F811
    fake = Klas(keypair[1])

    def hang(request: httpx.Request) -> httpx.Response:
        raise error

    fake.data = hang
    async with client(fake) as c:
        with pytest.raises(type(error)):
            await c.post(DATA)
        with pytest.raises(KlasUnavailable, match="30초"):
            await c.post(DATA)
        with pytest.raises(KlasUnavailable):
            await c.download(FILE, 1000)
    assert fake.counts[DATA] == 1 and fake.counts[FILE] == 0


class _StallingBody(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b"%PDF-1.4 "
        raise httpx.ReadTimeout("stalled")


async def test_a_download_that_stalls_mid_file_pauses_too(keypair):  # noqa: F811
    fake = Klas(keypair[1])
    fake.data = lambda request: httpx.Response(200, stream=_StallingBody(), headers={"content-disposition": "attachment"})
    async with client(fake) as c:
        with pytest.raises(httpx.ReadTimeout):
            await c.download(FILE, 1000)
        with pytest.raises(KlasUnavailable, match="제때 응답하지"):
            await c.download(FILE, 1000)
    assert fake.counts[FILE] == 1


# -- S06: a normal attachment path still works ----------------------------------------------------

@pytest.mark.parametrize("path", ["/common/file/DownloadFile/F1/1", "/common/file/DownloadFile/A_b-9.x/2%2B3"])
async def test_plain_attachment_paths_are_still_fetched(keypair, path):  # noqa: F811
    fake = Klas(keypair[1])
    fake.data = lambda request: httpx.Response(200, content=b"data", headers={"content-disposition": "attachment"})
    async with client(fake) as c:
        assert await c.download(path, 1000) == b"data"


# -- S07: a file over the limit is its own error -------------------------------------------------

async def test_a_file_without_a_length_that_grows_too_large_is_klas_file_too_large(keypair):  # noqa: F811
    async def chunks():
        for _ in range(10):
            yield b"x" * 10

    fake = Klas(keypair[1])
    fake.data = lambda request: httpx.Response(200, content=chunks(), headers={"content-disposition": "attachment"})
    async with client(fake) as c:
        with pytest.raises(KlasFileTooLarge, match="너무 큽니다") as caught:
            await c.download(FILE, 50)
    assert isinstance(caught.value, KlasError) and fake.counts[FILE] == 1
    assert "content-length" not in httpx.Response(200, content=chunks()).headers  # really no length given


async def test_a_declared_length_over_the_limit_is_klas_file_too_large(keypair):  # noqa: F811
    fake = Klas(keypair[1])
    fake.data = lambda request: httpx.Response(200, content=b"x" * 100, headers={"content-disposition": "attachment"})
    async with client(fake) as c:
        with pytest.raises(KlasFileTooLarge):
            await c.download(FILE, 10)


# -- S28: a contact that outsiders can use ------------------------------------------------------

def test_the_unexpected_error_text_names_the_e_mail_not_a_private_repository():
    with pytest.raises(ToolError) as caught, server.expected_errors():
        raise ValueError("x")
    assert klas.CONTACT_EMAIL in str(caught.value) and "github" not in str(caught.value)
    assert "github" not in klas.USER_AGENT and klas.CONTACT_EMAIL in klas.USER_AGENT


# -- S34: credentials (and so the agent's updater) import without klas ---------------------------

def test_credentials_and_the_agent_import_even_if_klas_is_broken():
    code = ("import sys; sys.modules['kw_mcp.klas'] = None; "
            "import kw_mcp.credentials, kw_mcp.agent; print('imported')")
    done = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0 and "imported" in done.stdout, done.stderr[-2000:]


# -- second pass: a back-off or a stop that starts while a login waits for the wire ----------------

FOURTH = "/std/lis/evltn/SelectSurveyStdList.do"
TEMPORARY = {"errorCount": 1, "error": "세션 정보가 올바르지 않습니다"}


async def _until(check, timeout: float = 5.0) -> None:
    for _ in range(int(timeout / 0.01)):
        if check():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("timed out")


class WireKlas(Klas):
    """After expire(): DATA answers loginRequired once every slow path is on the wire, and each slow
    path answers (or raises) only when the test opens its gate. A successful login ends the expiry."""

    def __init__(self, public_key: str, slow: dict, **kwargs) -> None:
        super().__init__(public_key, **kwargs)
        self.slow = slow
        self.gates = {path: asyncio.Event() for path in slow}
        self.on_wire: set[str] = set()
        self.all_on_wire = asyncio.Event()
        self.expired = False

    async def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if self.expired and path in self.slow:
            self.counts[path] += 1
            self.on_wire.add(path)
            if self.on_wire == set(self.slow):
                self.all_on_wire.set()
            await self.gates[path].wait()
            answer = self.slow[path]
            if isinstance(answer, Exception):
                raise answer
            return answer
        if self.expired and path == DATA:
            await self.all_on_wire.wait()
            self.counts[path] += 1
            return httpx.Response(200, json=LOGIN_REQUIRED)
        response = await super().handle(request)
        if path == LOGIN_CONFIRM and self.confirm is OK:
            self.expired = False
        return response


async def _expiry_while_others_are_on_the_wire(c: KlasClient, fake: WireKlas, confirm: dict = OK) -> list:
    """The session expires while DATA and the slow paths are in flight; DATA's login has to wait
    for the slow ones, which then answer one by one. confirm: what a login would get from then on."""
    assert await c.post(DATA) == [{"ok": True}]
    fake.confirm = confirm
    fake.expired = True
    tasks = [asyncio.create_task(c.post(DATA)), *(asyncio.create_task(c.post(p)) for p in fake.slow)]
    await _until(lambda: not c._jar_free.is_set())  # DATA's login is waiting for the wire
    assert fake.counts[LOGIN_FORM] == 1
    for path in fake.slow:
        fake.gates[path].set()
        await asyncio.sleep(0.01)
    return await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.parametrize("confirm", [OK, TEMPORARY], ids=["login-would-pass", "login-would-fail"])
async def test_a_stop_decided_while_a_login_waits_for_the_wire_sends_no_login(keypair, monkeypatch, confirm):  # noqa: F811
    refused = httpx.Response(403, text="forbidden")
    fake = WireKlas(keypair[1], {OTHER: refused, THIRD: refused, FOURTH: refused})
    async with KlasClient(ID, "pw", transport=httpx.MockTransport(fake.handle)) as c:
        waited, second, third, fourth = await _expiry_while_others_are_on_the_wire(c, fake, confirm)
        # The first two refusals are about one screen each; the third stops the client.
        for result in (second, third):
            assert isinstance(result, KlasError) and not isinstance(result, KlasLoginError), result
            assert "HTTP 403" in str(result)
        until, stop = c._login_failure
        assert isinstance(stop, KlasClientRejected) and until == math.inf
        assert waited is stop and fourth is stop
        assert fake.counts[LOGIN_FORM] == 1 and fake.counts[LOGIN_CONFIRM] == 1  # no handshake after the stop
        assert c.last_login["ok"] is False and "거부" in c.last_login["error"]
        sent = sum(fake.counts.values())
        assert sent == 4 + 1 + 4  # the first login and DATA, then DATA and the three slow ones
        later(monkeypatch, 24 * 3600.0)  # a stop for good: nothing goes out a day later either
        with pytest.raises(KlasClientRejected):
            await c.post(DATA)
        with pytest.raises(KlasClientRejected):
            await c.login()
        assert sum(fake.counts.values()) == sent and c._login_failure[0] == math.inf


@pytest.mark.parametrize("answer", [httpx.Response(503, text="busy"), httpx.ReadTimeout("hang")],
                         ids=["503", "ReadTimeout"])
async def test_a_pause_that_starts_while_a_login_waits_for_the_wire_sends_no_login(keypair, monkeypatch, answer):  # noqa: F811
    fake = WireKlas(keypair[1], {OTHER: answer})
    async with KlasClient(ID, "pw", transport=httpx.MockTransport(fake.handle)) as c:
        waited, slow = await _expiry_while_others_are_on_the_wire(c, fake)
        assert isinstance(slow, KlasUnavailable if isinstance(answer, httpx.Response) else httpx.ReadTimeout)
        assert isinstance(waited, KlasUnavailable)
        assert waited is c._unavailable[1]  # the pause in force, raised as is: not paused again
        assert str(waited).count("동안 요청을 멈춥니다") == 1
        assert fake.counts[LOGIN_FORM] == 1 and fake.counts[LOGIN_CONFIRM] == 1
        assert c.last_login["ok"] is True and c._login_failure is None  # the earlier login; no new attempt
        later(monkeypatch, TRANSIENT_BACKOFF + 1)  # the pause is over: the next call logs in again
        assert await c.post(DATA) == [{"ok": True}]
    assert fake.counts[LOGIN_FORM] == 2 and fake.counts[LOGIN_CONFIRM] == 2


async def test_a_session_refused_after_a_stop_keeps_the_stop(keypair, monkeypatch):  # noqa: F811
    fake = Klas(keypair[1])
    holder_of: dict[str, KlasClient] = {}

    async def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in (OTHER, THIRD, FOURTH):
            fake.counts[path] += 1
            return httpx.Response(403, text="forbidden")
        if path == DATA:  # answers only once the three refusals have stopped the client
            await _until(lambda: holder_of["c"]._login_failure is not None)
            fake.counts[path] += 1
            return httpx.Response(200, json=LOGIN_REQUIRED)
        return await fake.handle(request)

    async with KlasClient(ID, "pw", transport=httpx.MockTransport(handle)) as c:
        holder_of["c"] = c
        # All four start before the first login: DATA logs in, the session is refused right after.
        results = await asyncio.gather(*(c.post(p) for p in (DATA, OTHER, THIRD, FOURTH)), return_exceptions=True)
        until, stop = c._login_failure
        assert isinstance(stop, KlasClientRejected) and until == math.inf
        assert results[0] is stop and results[3] is stop  # not the 5-minute session block written over it
        later(monkeypatch, 24 * 3600.0)
        sent = sum(fake.counts.values())
        with pytest.raises(KlasClientRejected):
            await c.post(DATA)
        assert sum(fake.counts.values()) == sent
    assert fake.counts[LOGIN_CONFIRM] == 1


async def test_a_stop_for_good_is_never_replaced_by_a_shorter_block():
    async with KlasClient(ID, "pw", transport=httpx.MockTransport(lambda request: httpx.Response(500))) as c:
        stop = KlasClientRejected("거부")
        assert c._fail_login(stop, math.inf) is stop
        assert c._fail_login(KlasLoginError("잠시 뒤"), LOGIN_BLOCK_COOLDOWN) is stop
        assert c._fail_login(KlasBadPassword("일치하지 않습니다"), math.inf) is stop
        assert c._login_failure == (math.inf, stop) and c.last_login["error"] == "거부"
        with pytest.raises(KlasClientRejected):
            await c.post(DATA)
    fresh = KlasClient(ID, "pw", transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    async with fresh:  # a finite block is still replaced by the next one
        short = KlasLoginError("잠시 뒤")
        assert fresh._fail_login(short, LOGIN_BLOCK_COOLDOWN) is short
        blocked = KlasLoginBlocked("2차 인증", retry_after=3600.0)
        assert fresh._fail_login(blocked, blocked.retry_after) is blocked and fresh._login_failure[1] is blocked
