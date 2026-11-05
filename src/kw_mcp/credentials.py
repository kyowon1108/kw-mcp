"""Where the KLAS login comes from.

Order: KLAS_ID / KLAS_PASSWORD environment variables, then the OS keychain
(macOS Keychain via `keyring`), filled in by `kw-mcp setup`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import keyring
from keyring.errors import PasswordDeleteError

KEYRING_SERVICE = "kw-mcp"
KEYRING_ID_KEY = "klas_login_id"


class MissingCredentials(RuntimeError):
    pass


ENV = "env"  # the Claude Desktop extension's settings, passed in as KLAS_ID / KLAS_PASSWORD
KEYCHAIN = "keychain"  # saved by `kw-mcp setup`
FIX_IN_EXTENSION = "Claude 데스크톱 설정 → 확장 프로그램 → '광운대 KLAS (읽기 전용)' → 구성에서 학번과 비밀번호를 다시 입력하세요"
FIX_IN_KEYCHAIN = "터미널에서 `kw-mcp setup`을 실행해 학번과 비밀번호를 다시 저장하세요"
_HANGUL = re.compile(r"[\u3131-\u318e\uac00-\ud7a3]")
_PLACEHOLDER = re.compile(r"\$\{user_config\.\w+\}")


@dataclass(frozen=True)
class Credentials:
    login_id: str
    password: str = field(repr=False)
    source: str = KEYCHAIN


def _env(name: str) -> str:
    # Pasted values often carry a space or newline. Claude Desktop may also pass an unfilled
    # field through as the literal "${user_config.…}".
    value = (os.environ.get(name) or "").strip()
    return "" if _PLACEHOLDER.fullmatch(value) else value


def load() -> Credentials:
    env_id, env_password = _env("KLAS_ID"), _env("KLAS_PASSWORD")
    if env_id and env_password:
        return Credentials(env_id, env_password, ENV)
    # Either half may still come from the keychain (`kw-mcp setup`, then KLAS_ID or KLAS_PASSWORD set by hand).
    login_id = env_id or (keyring.get_password(KEYRING_SERVICE, KEYRING_ID_KEY) or "").strip()
    password = env_password or (keyring.get_password(KEYRING_SERVICE, login_id) if login_id else None)
    if not login_id or not password:
        fix = FIX_IN_EXTENSION if env_id or env_password else FIX_IN_KEYCHAIN
        raise MissingCredentials(f"KLAS 로그인 정보가 없습니다. {fix}.")
    return Credentials(login_id, password)


def login_hint(creds: Credentials) -> str:
    """What to check after KLAS rejects the login. Shows the ID masked; never the password."""
    login_id = creds.login_id
    # A 학번 (10 digits) shows its admission year and last two digits. Anything else may be a
    # password typed into the ID field, so it shows at most the first character.
    if len(login_id) == 10 and login_id.isdigit():
        shown = login_id[:4] + "****" + login_id[-2:]
    elif len(login_id) >= 3:
        shown = login_id[:1] + "*" * (len(login_id) - 1)
    else:
        shown = "*" * len(login_id)
    notes = [f"로그인한 아이디는 {shown}({len(login_id)}자리)입니다"]
    if not login_id.isdigit():
        notes.append("아이디에 숫자가 아닌 글자가 있습니다(학생은 학번 숫자만 입력)")
    if _HANGUL.search(creds.password):
        notes.append("비밀번호에 한글이 섞여 있습니다(한/영 전환 상태로 입력했을 수 있음)")
    notes.append(FIX_IN_EXTENSION if creds.source == ENV else FIX_IN_KEYCHAIN)
    return ". ".join(notes) + "."


def save(login_id: str, password: str) -> None:
    previous = keyring.get_password(KEYRING_SERVICE, KEYRING_ID_KEY)
    if previous and previous != login_id:
        _delete_quietly(previous)
    keyring.set_password(KEYRING_SERVICE, KEYRING_ID_KEY, login_id)
    keyring.set_password(KEYRING_SERVICE, login_id, password)


def delete() -> None:
    login_id = keyring.get_password(KEYRING_SERVICE, KEYRING_ID_KEY)
    if login_id:
        _delete_quietly(login_id)
    _delete_quietly(KEYRING_ID_KEY)


def _delete_quietly(username: str) -> None:
    try:
        keyring.delete_password(KEYRING_SERVICE, username)
    except PasswordDeleteError:
        pass
