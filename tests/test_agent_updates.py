"""Self-update safety: self-test, keeping the previous release, rollback after failed starts, no loops."""

from __future__ import annotations

import asyncio
import base64
import time
import zipfile

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kw_mcp import agent, release

SERVER = "https://bridge.example"
LINK = agent.Link(server=SERVER, ws_url="wss://ws.example/prod", uid="u_" + "a" * 22)
PINS = "# kw-mcp {v}\n# exclude-newer: 2026-11-01T00:00:00Z\nhttpx==0.28.1\n"


@pytest.fixture(autouse=True)
def config_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(agent, "LINK_FILE", tmp_path / "config" / "agent.json")
    monkeypatch.setattr(agent.os, "name", "posix")
    monkeypatch.setattr(agent, "in_uv_tool", lambda: True)
    monkeypatch.setattr(agent, "find_uv", lambda: "/opt/homebrew/bin/uv")
    return tmp_path / "config"


def saved_release(version: str) -> tuple:
    folder = agent.releases_dir()
    folder.mkdir(parents=True, exist_ok=True)
    wheel = folder / f"kw_mcp-{version}-py3-none-any.whl"
    wheel.write_bytes(b"PK")
    pins = folder / release.constraints_name(version)
    pins.write_text(PINS.format(v=version))
    return wheel, pins


class Uv:
    """Records uv and self-test runs; `fail` lists the argv markers that should fail."""

    def __init__(self, monkeypatch, fail=()):
        self.ran, self.fail = [], set(fail)
        monkeypatch.setattr(agent.subprocess, "run", self)

    def __call__(self, argv, **kwargs):
        self.ran.append(argv)
        joined = " ".join(map(str, argv))
        code = 1 if any(marker in joined for marker in self.fail) else 0
        return type("Done", (), {"returncode": code, "stderr": "boom" if code else "", "stdout": ""})()

    def installs(self) -> list[str]:
        return [a[-1].rsplit("/", 1)[-1] for a in self.ran if a[1:3] == ["tool", "install"]]

    def self_tests(self) -> list[str]:
        return [a[-1] for a in self.ran if "--expect" in a]


def test_a_new_version_that_fails_its_self_test_is_rolled_back_and_skipped(monkeypatch):
    monkeypatch.setattr(agent, "installed_version", lambda: "0.9.0")
    saved_release("0.9.0")
    new = saved_release("0.9.1")
    uv = Uv(monkeypatch, fail=["--expect 0.9.1"])
    assert agent.install_update(*new, "0.9.1") is False
    assert uv.installs() == ["kw_mcp-0.9.1-py3-none-any.whl", "kw_mcp-0.9.0-py3-none-any.whl"]
    assert agent.skipped("0.9.1") and agent.load_state()["skip"]["0.9.1"] == 0  # until a newer one exists
    assert "pending" not in agent.load_state()


def test_a_failed_install_is_skipped_for_a_day(monkeypatch):
    monkeypatch.setattr(agent, "installed_version", lambda: "0.9.0")
    uv = Uv(monkeypatch, fail=["kw_mcp-0.9.1-py3-none-any.whl"])
    assert agent.install_update(*saved_release("0.9.1"), "0.9.1") is False
    assert uv.self_tests() == [] and agent.skipped("0.9.1")
    assert agent.load_state()["skip"]["0.9.1"] > time.time() + 23 * 3600


def test_no_updates_from_outside_a_uv_tool_install(monkeypatch):
    monkeypatch.setattr(agent, "in_uv_tool", lambda: False)
    uv = Uv(monkeypatch)
    assert agent.install_update(*saved_release("0.9.1"), "0.9.1") is False and uv.ran == []

    async def check() -> None:
        await asyncio.wait_for(agent.update_loop(SERVER, first_delay=0), 0.1)

    with pytest.raises(TimeoutError):  # waits forever instead of reinstalling into another environment
        asyncio.run(check())


def test_two_crashed_starts_of_a_new_version_roll_it_back(monkeypatch):
    version = {"now": "0.9.1"}
    monkeypatch.setattr(agent, "installed_version", lambda: version["now"])
    saved_release("0.9.0")
    agent.save_state({"running": False, "pending": {"version": "0.9.1", "previous": "0.9.0", "failures": 0}})
    assert agent.note_start() == (False, None)  # first start after the update
    assert agent.note_start() == (True, None)  # crashed once
    crashed, failing = agent.note_start()  # crashed twice
    assert crashed and failing["version"] == "0.9.1" and "pending" not in agent.load_state()
    uv = Uv(monkeypatch)
    assert agent.roll_back(failing) is True
    assert uv.installs() == ["kw_mcp-0.9.0-py3-none-any.whl"] and uv.self_tests() == ["0.9.0"]
    assert agent.skipped("0.9.1")


def test_a_replaced_or_cleanly_stopped_run_is_not_a_crash(monkeypatch):
    monkeypatch.setattr(agent, "installed_version", lambda: "0.9.1")
    agent.save_state({"running": True, "pending": {"version": "0.9.1", "previous": "0.9.0", "failures": 1}})
    assert agent.note_start(replaced=True) == (False, None)
    agent.note_stop()
    assert agent.note_start() == (False, None) and agent.load_state()["pending"]["failures"] == 1


def test_an_update_that_did_not_take_is_not_retried_at_once(monkeypatch):
    monkeypatch.setattr(agent, "installed_version", lambda: "0.9.0")  # Windows: uv failed after we exited
    agent.save_state({"running": False, "pending": {"version": "0.9.1", "previous": "0.9.0", "failures": 0}})
    assert agent.note_start() == (False, None)
    assert "pending" not in agent.load_state() and agent.skipped("0.9.1")


def test_no_rollback_without_a_saved_copy(monkeypatch):
    uv = Uv(monkeypatch)
    assert agent.roll_back({"version": "0.9.1", "previous": "0.8.0"}) is False and uv.ran == []


def test_a_healthy_new_version_is_kept_and_old_copies_pruned(monkeypatch):
    monkeypatch.setattr(agent, "installed_version", lambda: "0.9.1")
    monkeypatch.setattr(agent, "HEALTHY_AFTER_S", 0)
    for v in ("0.8.0", "0.9.0", "0.9.1"):
        saved_release(v)
    agent.save_state({"running": True, "pending": {"version": "0.9.1", "previous": "0.9.0", "failures": 0}})

    async def run() -> None:
        connected = asyncio.Event()
        connected.set()
        await agent._keep_if_healthy(connected, time.monotonic())

    asyncio.run(run())
    assert "pending" not in agent.load_state()
    assert sorted(p.name for p in agent.releases_dir().iterdir()) == [
        "kw_mcp-0.9.1-constraints.txt", "kw_mcp-0.9.1-py3-none-any.whl"]


@respx.mock
async def test_fetch_skips_a_version_that_failed_here(monkeypatch):
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setattr(release, "PUBLIC_KEY", base64.b64encode(public).decode())
    monkeypatch.setattr(agent, "installed_version", lambda: "0.9.0")
    folder = agent.CONFIG_DIR / "built"
    folder.mkdir(parents=True)
    wheel = folder / "kw_mcp-0.9.1-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as z:
        z.writestr("kw_mcp-0.9.1.dist-info/METADATA", "Version: 0.9.1\n")
    pins = folder / release.constraints_name("0.9.1")
    pins.write_text(PINS.format(v="0.9.1"))
    manifest = {**release.sign(wheel, private), "constraints": release.sign_constraints(pins, "0.9.1", private)}
    respx.get(f"{SERVER}/dist/latest.json").mock(return_value=httpx.Response(200, json=manifest))
    files = respx.get(url__regex=rf"{SERVER}/dist/kw_mcp-.*").mock(
        side_effect=lambda req: httpx.Response(200, content=(folder / req.url.path.rsplit("/", 1)[-1]).read_bytes()))
    agent.skip_version("0.9.1", None)
    async with httpx.AsyncClient() as http:
        assert await agent.fetch_update(http, SERVER) is None and files.call_count == 0
        agent.save_state({})
        found = await agent.fetch_update(http, SERVER)
    assert found and found[1].read_bytes() == wheel.read_bytes() and found[2].read_text() == pins.read_text()


def test_a_crashing_agent_looks_for_a_fixed_version_before_exiting(monkeypatch):
    monkeypatch.setattr(agent, "load_link", lambda: LINK)
    monkeypatch.setattr(agent, "installed_version", lambda: "0.9.1")

    async def broken(connected=None):
        raise NameError("bug in 0.9.1")

    async def idle(server, first_delay):
        await asyncio.sleep(3600)

    fixed = []

    async def update_once(http, server):
        fixed.append(server)
        return "0.9.2"

    monkeypatch.setattr(agent, "run_forever", broken)
    monkeypatch.setattr(agent, "update_loop", idle)
    monkeypatch.setattr(agent, "update_once", update_once)
    assert asyncio.run(agent.main()) == agent.RESTART_EXIT_CODE and fixed == [SERVER]
    assert agent.load_state()["running"] is False

    async def nothing(http, server):
        return None

    monkeypatch.setattr(agent, "update_once", nothing)
    assert asyncio.run(agent.main()) == 1  # launchd restarts it; the next start checks again


def test_after_an_abnormal_exit_the_first_check_comes_within_a_minute(monkeypatch):
    monkeypatch.setattr(agent, "load_link", lambda: LINK)
    agent.save_state({"running": True})  # the last run never said goodbye
    delays = []

    async def stop_soon(connected=None):
        await asyncio.sleep(0.01)

    async def record(server, first_delay):
        delays.append(first_delay)
        await asyncio.sleep(3600)

    monkeypatch.setattr(agent, "run_forever", stop_soon)
    monkeypatch.setattr(agent, "update_loop", record)
    asyncio.run(agent.main())
    asyncio.run(agent.main())
    assert 30 <= delays[0] <= 60 and delays[1] == agent.UPDATE_FIRST_CHECK_S
