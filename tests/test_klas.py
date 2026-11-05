import base64
import json

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from kw_mcp.klas import (
    BASE_URL,
    LOGIN_CAPTCHA,
    LOGIN_CONFIRM,
    LOGIN_FORM,
    LOGIN_SECURITY,
    KlasClient,
    KlasError,
    KlasLoginError,
    encrypt_login,
)

HOME = "/std/cmn/frame/StdHome.do"


@pytest.fixture(scope="module")
def keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    der = private.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private, base64.b64encode(der).decode()


def test_encrypt_login_matches_jsencrypt_format(keypair):
    private, public_b64 = keypair
    assert len(public_b64) == 392  # same size as the key KLAS serves

    token = encrypt_login(public_b64, "2022000000", "pä$$")
    plain = private.decrypt(base64.b64decode(token), padding.PKCS1v15())

    assert json.loads(plain) == {"loginId": "2022000000", "loginPwd": "pä$$", "storeIdYn": "N"}


def mock_login(router, public_b64, confirm=None, failures=0):
    router.get(LOGIN_FORM).respond(200, text="<html></html>")
    router.post(LOGIN_SECURITY).respond(200, json={"publicKey": public_b64})
    router.post(LOGIN_CAPTCHA).respond(200, json=failures)
    return router.post(LOGIN_CONFIRM).respond(
        200, json=confirm or {"errorCount": 0, "response": {"twoFactorAt": "N", "certOpt": "N", "gradAt": "N"}}
    )


async def test_post_logs_in_first_and_sends_json(keypair):
    private, public_b64 = keypair
    with respx.mock(base_url=BASE_URL, assert_all_called=True) as router:
        confirm = mock_login(router, public_b64)
        home = router.post(HOME).respond(200, json={"yearhakgi": "2026,2"})

        async with KlasClient("id", "pw") as client:
            assert await client.post(HOME, {"searchYearhakgi": "2026,2"}) == {"yearhakgi": "2026,2"}

        sent = json.loads(confirm.calls.last.request.content)
        assert set(sent) == {"loginToken", "captcha", "redirectUrl", "redirectTabUrl"}
        assert json.loads(private.decrypt(base64.b64decode(sent["loginToken"]), padding.PKCS1v15()))["loginId"] == "id"
        assert json.loads(home.calls.last.request.content) == {"searchYearhakgi": "2026,2"}
        assert home.calls.last.request.headers["content-type"].startswith("application/json")
        assert home.calls.last.request.headers["x-requested-with"] == "XMLHttpRequest"


async def test_relogs_in_once_when_session_expires(keypair):
    _, public_b64 = keypair
    with respx.mock(base_url=BASE_URL) as router:
        confirm = mock_login(router, public_b64)
        router.post(HOME).mock(
            side_effect=[
                httpx.Response(200, json={"n": 1}),
                httpx.Response(302, headers={"location": f"{BASE_URL}{LOGIN_FORM}"}),
                httpx.Response(200, json={"n": 2}),
            ]
        )

        async with KlasClient("id", "pw") as client:
            assert await client.post(HOME) == {"n": 1}
            assert await client.post(HOME) == {"n": 2}

        assert confirm.call_count == 2


async def test_html_login_page_counts_as_expired(keypair):
    _, public_b64 = keypair
    with respx.mock(base_url=BASE_URL) as router:
        confirm = mock_login(router, public_b64)
        router.post(HOME).mock(
            side_effect=[
                httpx.Response(200, text="<html>login</html>", headers={"content-type": "text/html"}),
                httpx.Response(200, json=[]),
            ]
        )
        async with KlasClient("id", "pw") as client:
            # first post logs in, gets HTML, logs in again, retries
            assert await client.post(HOME) == []
        assert confirm.call_count == 2


@pytest.mark.parametrize(
    ("confirm", "message"),
    [
        ({"errorCount": 1, "error": {"message": "비밀번호가 틀렸습니다"}}, "비밀번호가 틀렸습니다"),
        # actual KLAS response for a wrong ID/password
        ({"redirectUrl": "", "fieldErrors": [{"field": "", "message": "개인번호 또는 비밀번호가 일치하지 않습니다."}],
          "responseText": "", "response": {}, "errorCount": 1, "loginRequired": False, "redirect": False},
         "개인번호 또는 비밀번호가 일치하지 않습니다"),
        ({"errorCount": 0, "response": {"twoFactorAt": "Y"}}, "2차 인증"),
        ({"errorCount": 0, "response": {"certOpt": "Y"}}, "임시 비밀번호"),
    ],
)
async def test_login_rejections(keypair, confirm, message):
    _, public_b64 = keypair
    with respx.mock(base_url=BASE_URL) as router:
        mock_login(router, public_b64, confirm=confirm)
        async with KlasClient("id", "pw") as client:
            with pytest.raises(KlasLoginError, match=message):
                await client.post(HOME)


async def test_captcha_required_stops_before_confirm(keypair):
    _, public_b64 = keypair
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        confirm = mock_login(router, public_b64, failures=3)
        async with KlasClient("id", "pw") as client:
            with pytest.raises(KlasLoginError, match="캡차"):
                await client.login()
        assert confirm.call_count == 0


LOGIN_REQUIRED = {"redirect": True, "redirectUrl": "/usr/cmn/login/LoginForm.do?redirectUrl=/std/cmn/frame/StdHome.do",
                  "fieldErrors": [], "responseText": "", "response": None, "loginRequired": True, "errorCount": 0}


async def test_a_json_login_required_answer_logs_in_again(keypair):
    # What KLAS really sends an AJAX call once the session is gone (2026-11-06): 200 + JSON, no redirect.
    _, public_b64 = keypair
    with respx.mock(base_url=BASE_URL) as router:
        confirm = mock_login(router, public_b64)
        router.post(HOME).mock(side_effect=[httpx.Response(200, json={"n": 1}),
                                            httpx.Response(200, json=LOGIN_REQUIRED),
                                            httpx.Response(200, json={"n": 2})])
        async with KlasClient("id", "pw") as client:
            assert await client.post(HOME) == {"n": 1}
            assert await client.post(HOME) == {"n": 2}  # not the login-required dict
        assert confirm.call_count == 2


async def test_login_required_right_after_logging_in_is_an_error(keypair):
    _, public_b64 = keypair
    with respx.mock(base_url=BASE_URL) as router:
        confirm = mock_login(router, public_b64)
        router.post(HOME).respond(200, json=LOGIN_REQUIRED)
        async with KlasClient("id", "pw") as client:
            with pytest.raises(KlasError, match="log in again"):
                await client.post(HOME)
        assert confirm.call_count == 2  # one fresh login, one retry; no loop
