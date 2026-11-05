"""Concurrency and lockout regressions, against a fake KLAS whose handlers yield to the event loop."""

import asyncio
import base64
import json

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from kw_mcp.klas import (
    LOGIN_CAPTCHA,
    LOGIN_CONFIRM,
    LOGIN_FORM,
    LOGIN_SECURITY,
    KlasClient,
    KlasError,
    KlasLoginError,
)

DATA = "/std/lis/evltn/TaskStdList.do"
OTHER_REDIRECT = "/std/cps/inqire/Somewhere.do"


class FakeKlas:
    def __init__(self, *, accept_password: bool = True) -> None:
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        der = private.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self.public_key = base64.b64encode(der).decode()
        self.accept_password = accept_password
        self.valid_sessions: set[str] = set()
        self.next_session = 0
        self.logins = 0
        self.failed_logins = 0
        self.data_requests = 0

    def expire_all(self) -> None:
        self.valid_sessions.clear()

    async def handle(self, request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.001)  # let other requests interleave, like a real network
        path = request.url.path
        session = request.headers.get("cookie", "").removeprefix("JSESSIONID=")
        if path == LOGIN_FORM:
            self.next_session += 1
            return httpx.Response(200, text="<html/>", headers={"set-cookie": f"JSESSIONID=s{self.next_session}; Path=/"})
        if path == LOGIN_SECURITY:
            return httpx.Response(200, json={"publicKey": self.public_key})
        if path == LOGIN_CAPTCHA:
            return httpx.Response(200, json=self.failed_logins)
        if path == LOGIN_CONFIRM:
            if not self.accept_password:
                self.failed_logins += 1
                return httpx.Response(200, json={"errorCount": 1, "error": {"message": "비밀번호 오류"}})
            self.logins += 1
            self.valid_sessions.add(session)
            return httpx.Response(200, json={"errorCount": 0, "response": {}})
        if path == OTHER_REDIRECT:
            return httpx.Response(302, headers={"location": "https://klas.kw.ac.kr/std/error.do"})
        if session not in self.valid_sessions:
            return httpx.Response(302, headers={"location": f"https://klas.kw.ac.kr{LOGIN_FORM}?redirectUrl={path}"})
        self.data_requests += 1
        return httpx.Response(200, json=[{"ok": json.loads(request.content)}])


def client_for(fake: FakeKlas) -> KlasClient:
    return KlasClient("id", "pw", transport=httpx.MockTransport(fake.handle))


async def test_cold_start_burst_logs_in_once():
    fake = FakeKlas()
    async with client_for(fake) as client:
        results = await asyncio.gather(*(client.post(DATA, {"n": i}) for i in range(8)))
    assert fake.logins == 1
    assert [r[0]["ok"]["n"] for r in results] == list(range(8))


async def test_expired_session_burst_logs_in_once():
    fake = FakeKlas()
    async with client_for(fake) as client:
        await client.post(DATA)
        fake.expire_all()
        await asyncio.gather(*(client.post(DATA, {"n": i}) for i in range(8)))
    assert fake.logins == 2
    assert fake.data_requests == 9


async def test_wrong_password_is_not_retried():
    fake = FakeKlas(accept_password=False)
    async with client_for(fake) as client:
        for _ in range(3):
            with pytest.raises(KlasLoginError, match="비밀번호 오류"):
                await asyncio.gather(client.post(DATA), client.post(DATA))
    assert fake.failed_logins == 1  # far below the captcha threshold


async def test_other_redirects_do_not_trigger_relogin():
    fake = FakeKlas()
    async with client_for(fake) as client:
        await client.post(DATA)
        with pytest.raises(KlasError, match="unexpected redirect"):
            await client.post(OTHER_REDIRECT)
    assert fake.logins == 1
