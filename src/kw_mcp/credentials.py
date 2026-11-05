"""Where the KLAS login comes from.

Order: KLAS_ID / KLAS_PASSWORD environment variables, then the OS keychain
(macOS Keychain via `keyring`), filled in by `kw-mcp setup`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import keyring
from keyring.errors import PasswordDeleteError

KEYRING_SERVICE = "kw-mcp"
KEYRING_ID_KEY = "klas_login_id"


class MissingCredentials(RuntimeError):
    pass


@dataclass(frozen=True)
class Credentials:
    login_id: str
    password: str = field(repr=False)


def load() -> Credentials:
    login_id = os.environ.get("KLAS_ID") or keyring.get_password(KEYRING_SERVICE, KEYRING_ID_KEY)
    password = os.environ.get("KLAS_PASSWORD")
    if login_id and not password:
        password = keyring.get_password(KEYRING_SERVICE, login_id)
    if not login_id or not password:
        raise MissingCredentials(
            "KLAS 로그인 정보가 없습니다. 터미널에서 `uv run kw-mcp setup`을 실행해 키체인에 저장하세요."
        )
    return Credentials(login_id, password)


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
