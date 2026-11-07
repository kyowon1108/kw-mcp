"""Shared test setup: nothing a test does may touch the real home directory."""

import keyring
import pytest
from keyring.backend import KeyringBackend

from kw_mcp import agent, klas


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


@pytest.fixture(autouse=True)
def agent_config_in_tmp(tmp_path, monkeypatch):
    """The PC agent's link file, lock and state go to a temporary folder, never ~/.config/kw-campus
    (klas_status reads the link; test modules may point it elsewhere again)."""
    monkeypatch.setattr(agent, "CONFIG_DIR", tmp_path / "kw-campus")
    monkeypatch.setattr(agent, "LINK_FILE", tmp_path / "kw-campus" / "agent.json")


@pytest.fixture(autouse=True)
def package_data_only(monkeypatch):
    """Loaders read the package's own data files and nothing syncs or reads ~/.config/kw-campus/data, as in a
    source checkout (no data_version file), whatever the folder the tests run in. test_datasync turns it on."""
    from kw_mcp import datasync

    monkeypatch.setattr(datasync, "bundled_version", lambda: None)
    monkeypatch.setattr(datasync, "_started", True)
    monkeypatch.delenv(datasync.DATA_DIR_ENV, raising=False)


TEST_BRIDGE = "https://bridge.example"
TEST_BRIDGE_WS = "wss://ws.example/prod"


@pytest.fixture(autouse=True)
def test_bridge_is_the_official_one(monkeypatch):
    """Tests talk to https://bridge.example and wss://ws.example/prod (mocked); they stand in for
    release.BRIDGE_ORIGIN and BRIDGE_WS_URL, the only bridge kw-mcp accepts. No developer's local
    bridge leaks in from the environment."""
    from kw_mcp import release

    monkeypatch.setattr(release, "BRIDGE_ORIGIN", TEST_BRIDGE)
    monkeypatch.setattr(release, "BRIDGE_WS_URL", TEST_BRIDGE_WS)
    monkeypatch.delenv(release.DEV_BRIDGE_ENV, raising=False)
    monkeypatch.delenv(release.DEV_BRIDGE_WS_ENV, raising=False)
