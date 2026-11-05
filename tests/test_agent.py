import json
import plistlib
from datetime import datetime

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from kw_mcp import agent, credentials
from kw_mcp.klas import KlasLoginBlocked, KlasLoginError
from kw_mcp.service import KST, SNAPSHOT_FIELDS, KlasService
from tests.test_service import FakeClient

SERVER = "https://bridge.example"
LINK = agent.Link(server=SERVER, ws_url="wss://ws.example/prod", uid="u_test")


class FixedHolder:
    def __init__(self, service=None, error=None):
        self._service, self._error = service, error

    async def service(self):
        if self._error:
            raise self._error
        return self._service


def service() -> KlasService:
    return KlasService(FakeClient(), now=lambda: datetime(2026, 11, 5, 12, 0, tzinfo=KST))


async def test_snapshot_sends_only_whitelisted_fields():
    snap = await service().snapshot()
    text = json.dumps(snap, ensure_ascii=False)
    assert "홍길동" not in text and "2022000000" not in text  # extra fields KLAS might add never leave the PC
    assert snap["semester"] == "2026,2" and snap["fetched_at"].startswith("2026-11-05T12:00")
    assert set(snap["courses"][0]) == set(SNAPSHOT_FIELDS["courses"])
    assert set(snap["sections"]) == {"U2026A", "U2026B"}
    hw = {t["title"]: t for t in snap["sections"]["U2026A"]["tasks"]}
    assert hw["HW3"]["expiredate"] == "2026-11-07 23:59:59" and set(hw["HW3"]) == set(SNAPSHOT_FIELDS["tasks"])
    assert snap["course_posts"][0]["title"] == "10주차 자료"


def test_device_signature_is_raw_r_s_over_the_message():
    key = agent.DeviceKey.generate()
    jwk = key.public_jwk()
    signed = key.signed("u_1", "connect")
    raw = agent.b64u_decode(signed["sig"])
    assert len(raw) == 64
    public = ec.EllipticCurvePublicNumbers(int.from_bytes(agent.b64u_decode(jwk["x"]), "big"),
                                           int.from_bytes(agent.b64u_decode(jwk["y"]), "big"),
                                           ec.SECP256R1()).public_key()
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    public.verify(der, f"kw-connect:u_1:{signed['ts']}".encode(), ec.ECDSA(hashes.SHA256()))


def test_invite_round_trip_and_garbage():
    assert agent.parse_invite(agent.make_invite(SERVER + "/", "tok") + "\n") == (SERVER, "tok")
    with pytest.raises(ValueError):
        agent.parse_invite("not-an-invite")
    with pytest.raises(ValueError):
        agent.parse_invite("kwc_!!!")


@respx.mock
async def test_answer_posts_ciphertext_only_to_its_own_bridge():
    route = respx.post(f"{SERVER}/device/result").mock(return_value=httpx.Response(202, json={"ok": True}))
    key = AESGCM.generate_key(bit_length=256)
    message = {"type": "snapshot", "request_id": "r1", "key": agent.b64u(key), "result_url": f"{SERVER}/device/result"}
    async with httpx.AsyncClient() as http:
        await agent.answer(FixedHolder(service()), LINK, message, http)
        await agent.answer(FixedHolder(service()), LINK, {**message, "result_url": "https://evil.example/x"}, http)
    assert route.call_count == 1
    body = json.loads(route.calls[0].request.content)
    assert "데이터마이닝" not in route.calls[0].request.content.decode()
    plain = AESGCM(key).decrypt(agent.b64u_decode(body["iv"]), agent.b64u_decode(body["ct"]), b"r1")
    assert json.loads(plain)["courses"][0]["subjNm"] == "데이터마이닝"


@pytest.mark.parametrize(("error", "code"), [
    (KlasLoginBlocked("captcha"), "klas_blocked"),
    (KlasLoginError("wrong password"), "klas_login_required"),
    (credentials.MissingCredentials("no login"), "klas_login_required"),
])
async def test_login_problems_become_error_codes(error, code):
    result = await agent.build_result(FixedHolder(error=error))
    assert result["error"] == code and result["message"]


def test_launchd_job_runs_the_agent_module():
    job = plistlib.loads(agent.launchd_plist())
    assert job["Label"] == agent.LAUNCHD_LABEL and job["RunAtLoad"] is True
    assert job["ProgramArguments"][1:4] == ["-m", "kw_mcp", "agent"]
    assert job["KeepAlive"] == {"SuccessfulExit": False}


def test_only_one_agent_holds_the_lock(monkeypatch):
    monkeypatch.setattr(agent, "LOCK_PORT", 47899)
    lock = agent.single_instance()
    try:
        assert agent.agent_running()
        with pytest.raises(agent.AlreadyRunning):
            agent.single_instance()
    finally:
        lock.close()
    assert not agent.agent_running()


def test_public_api_url_comes_from_the_invite(monkeypatch):
    from kw_mcp import public_api

    monkeypatch.setenv("KW_CAMPUS_INVITE", agent.make_invite(SERVER, "tok"))
    monkeypatch.delenv("KW_CAMPUS_API_URL", raising=False)
    assert public_api.base_url() == f"{SERVER}/c/tok"
    monkeypatch.setenv("KW_CAMPUS_INVITE", "garbage")
    monkeypatch.setenv("KW_CAMPUS_API_URL", "https://x.example/c/t/")
    assert public_api.base_url() == "https://x.example/c/t"


def test_invite_must_point_at_a_plain_https_server():
    for bad in ("http://evil.example", "https://user@evil.example", "https://bridge.example/x"):
        with pytest.raises(ValueError):
            agent.parse_invite(agent.make_invite(bad, "tok"))
    assert agent.parse_invite(agent.make_invite("http://localhost:8080", "t"))[0] == "http://localhost:8080"
    with pytest.raises(ValueError):
        agent.register(agent.make_invite("https://other.example", "tok"), expected_server=SERVER)


class CallService:
    async def assignment_detail(self, course, title):
        if title == "missing":
            raise LookupError("'missing'와 일치하는 과제가 없습니다.")
        return {"course": course, "title": title}


async def test_calls_run_only_allowlisted_ops_with_clean_args():
    holder = FixedHolder(CallService())
    ok = await agent.build_result(holder, "assignment_detail", {"course": "데이터", "title": "HW3", "extra": "x"})
    assert ok == {"result": {"course": "데이터", "title": "HW3"}}
    long = await agent.build_result(holder, "assignment_detail", {"course": "c" * 500, "title": None})
    assert long["result"] == {"course": "c" * agent.MAX_ARG_CHARS, "title": ""}
    assert (await agent.build_result(holder, "assignment_detail", {"course": "a", "title": "missing"}))["error"] == "not_found"
    assert (await agent.build_result(holder, "delete_everything", {}))["error"] == "unsupported"
    assert (await agent.build_result(holder, "syllabus", {"course": "a"}))["error"] == "unsupported"  # not implemented here


def test_connect_url_announces_protocol_version():
    url = agent._connect_url(LINK, agent.DeviceKey.generate())
    assert url.startswith(LINK.ws_url + "?") and f"v={agent.PROTOCOL_VERSION}" in url
