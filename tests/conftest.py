"""Shared test setup: nothing a test does may touch the real home directory."""

import keyring
import pytest
from keyring.backend import KeyringBackend

from kw_mcp import klas


class MemoryKeyring(KeyringBackend):
    """Stands in for the OS keychain: a test that forgets to stub it must never read or write the
    developer's real KLAS password or device key (or hang on a macOS access prompt)."""

    priority = 1

    def __init__(self) -> None:
        super().__init__()
        self.items: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.items.get((service, username))

    def set_password(self, service, username, password):
        self.items[(service, username)] = password

    def delete_password(self, service, username):
        from keyring.errors import PasswordDeleteError

        if self.items.pop((service, username), None) is None:
            raise PasswordDeleteError(username)


@pytest.fixture(autouse=True)
def memory_keychain():
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    try:
        yield backend
    finally:
        keyring.set_keyring(previous)


@pytest.fixture(autouse=True)
def login_state_in_tmp(tmp_path, monkeypatch):
    """The rejected-login marker goes to a temporary file, never ~/.config/kw-mcp."""
    path = tmp_path / "login-state.json"
    monkeypatch.setattr(klas, "LOGIN_STATE_FILE", path)
    return path
