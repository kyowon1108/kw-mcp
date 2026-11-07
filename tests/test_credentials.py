"""Where the login comes from, and what a rejected login tells the user to check."""

import pytest
import respx

from kw_mcp import credentials, holder
from kw_mcp.klas import BASE_URL, KlasBadPassword, KlasClient
from tests.test_klas import HOME, keypair, mock_login  # noqa: F401 (fixture)

REJECTED = {"fieldErrors": [{"field": "", "message": "개인번호 또는 비밀번호가 일치하지 않습니다."}],
            "response": {}, "errorCount": 1}


@pytest.fixture
def no_keychain(monkeypatch):
    saved = {}
    monkeypatch.setattr(credentials.keyring, "get_password", lambda service, user: saved.get(user))
    monkeypatch.delenv("KLAS_ID", raising=False)
    monkeypatch.delenv("KLAS_PASSWORD", raising=False)
    return saved


def test_extension_settings_are_trimmed_and_marked(no_keychain, monkeypatch):
    monkeypatch.setenv("KLAS_ID", " 2022123480\n")
    monkeypatch.setenv("KLAS_PASSWORD", "pw!\t")
    creds = credentials.load()
    assert (creds.login_id, creds.password, creds.source) == ("2022123480", "pw!", credentials.ENV)


def test_unfilled_extension_fields_count_as_missing(no_keychain, monkeypatch):
    monkeypatch.setenv("KLAS_ID", "${user_config.klas_id}")
    monkeypatch.setenv("KLAS_PASSWORD", "${user_config.klas_password}")
    with pytest.raises(credentials.MissingCredentials, match="웹이랑 폰에서도 쓰게 연결해 줘") as missing:
        credentials.load()
    assert "확장 설정" in str(missing.value) and "kw-mcp" not in str(missing.value)  # no terminal any more
    monkeypatch.setenv("KLAS_PASSWORD", "pw")
    with pytest.raises(credentials.MissingCredentials, match="확장 프로그램"):
        credentials.load()
    monkeypatch.setenv("KLAS_ID", "2022123480")
    monkeypatch.setenv("KLAS_PASSWORD", "${abc}xyz")  # a real password that merely starts with ${
    assert credentials.load().password == "${abc}xyz"


def test_keychain_login_and_mixed_sources(no_keychain, monkeypatch):
    no_keychain.update({credentials.KEYRING_ID_KEY: "2022123480", "2022123480": "pw"})
    assert credentials.load().source == credentials.KEYCHAIN
    monkeypatch.setenv("KLAS_PASSWORD", "other")  # ID from the keychain, password from the environment
    assert (credentials.load().login_id, credentials.load().password) == ("2022123480", "other")
    monkeypatch.delenv("KLAS_PASSWORD")
    monkeypatch.setenv("KLAS_ID", "2022123480")  # ID from the environment, password from the keychain
    assert credentials.load().password == "pw"


async def test_holder_starts_a_fresh_client_when_the_login_changes(monkeypatch):
    logins = iter([credentials.Credentials("2022123480", "old", credentials.ENV),
                   credentials.Credentials("2022123480", "old", credentials.ENV),
                   credentials.Credentials("2022123480", "new", credentials.ENV)])
    monkeypatch.setattr(credentials, "load", lambda: next(logins))
    h = holder.KlasHolder()
    first = await h.service()
    assert await h.service() is first and await h.service() is not first
    await h.aclose()


def test_hint_masks_the_id_and_flags_input_slips():
    hint = credentials.login_hint(credentials.Credentials("2022123480", "ㅔㅈ1234", credentials.ENV))
    # only the admission year and the length: the rest of the 학번 is not shown
    assert "2022******(10자리)" in hint and "80" not in hint.split("10자리")[0][4:]
    assert "한글" in hint and "확장 프로그램" in hint and "ㅔㅈ" not in hint
    other = credentials.login_hint(credentials.Credentials("kw2022", "pw", credentials.KEYCHAIN))
    assert "******(6자리)" in other and "숫자가 아닌" in other and "한글" not in other
    # the PC agent's keychain copy is fixed in the extension settings, then saved again by connect_other_devices
    assert "확장 설정" in other and "연결해 줘" in other and "kw-mcp" not in other
    assert "k" not in other.split("(6자리)")[0]
    # a password typed into the ID field shows nothing but its length
    assert "*****************(17자리)" in credentials.login_hint(credentials.Credentials("MyS3cretPassw0rd!", "x"))
    assert "*(1자리)" in credentials.login_hint(credentials.Credentials("1", "x"))


async def test_rejected_login_says_where_to_fix_it(keypair):  # noqa: F811
    _, public_b64 = keypair
    creds = credentials.Credentials("2022123480", "wrong", credentials.ENV)
    with respx.mock(base_url=BASE_URL) as router:
        mock_login(router, public_b64, confirm=REJECTED)
        async with KlasClient(creds.login_id, creds.password, login_hint=credentials.login_hint(creds)) as client:
            with pytest.raises(KlasBadPassword) as caught:
                await client.post(HOME)
    message = str(caught.value)
    assert "일치하지 않습니다" in message and "2022******" in message and "확장 프로그램" in message
    assert "kw-mcp setup" not in message and "wrong" not in message
