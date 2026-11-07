"""Data updates without a release: signed data.json from the bridge, verified, cached, switched atomically, and
the loaders (knowledge, simulation.rules) reading the newer copy or falling back to the package's own."""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from kw_mcp import agent, datasync, knowledge, release, server, simulation

SERVER = "https://bridge.example"  # conftest makes it release.bridge_origin()
BUNDLED = 20261101000000
PACKAGE = Path(datasync.__file__).parent
QUESTION = "데이터동기화시험질문 크와크와"


@pytest.fixture
def key(monkeypatch):
    private = Ed25519PrivateKey.generate()  # throwaway: tests never touch the release key
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    monkeypatch.setattr(release, "PUBLIC_KEY", base64.b64encode(public).decode())
    return private


@pytest.fixture(autouse=True)
def on(monkeypatch):
    """datasync as in an installed copy: package data version BUNDLED, kw-mcp 1.2.0 (conftest turns it off)."""
    monkeypatch.setattr(datasync, "bundled_version", lambda: BUNDLED)
    monkeypatch.setattr(datasync, "app_version", lambda: "1.2.0")
    monkeypatch.setattr(datasync, "_seen", None)


def faq_with_extra_entry() -> bytes:
    faq = json.loads((PACKAGE / "knowledge" / "faq.json").read_text(encoding="utf-8"))
    extra = {**faq["entries"][0], "id": "test-datasync-entry", "questions": [QUESTION, "크와크와 질문", "동기화 시험"]}
    faq["entries"].append(extra)
    return json.dumps(faq, ensure_ascii=False).encode()


def graduation_built(when: str, name: str = "graduation") -> bytes:
    rules = json.loads((PACKAGE / "rules" / f"{name}.json").read_text(encoding="utf-8"))
    rules["version"]["built_at"] = when
    return json.dumps(rules, ensure_ascii=False).encode()


def make_release(folder: Path, private, version: int, files: dict[str, bytes], min_app="1.2.0", app="1.2") -> dict:
    """What scripts/release.sh data writes: the files under their package paths plus a signed data.json."""
    for name, data in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)
    manifest = release.sign_data(folder, list(files), version, app, min_app, private)
    (folder / release.DATA_MANIFEST_NAME).write_text(json.dumps(manifest))
    return manifest


def serve(mock, manifest: dict, files: dict[str, bytes]) -> dict[str, respx.Route]:
    mock.get(f"{SERVER}/dist/data/data.json").mock(return_value=httpx.Response(200, json=manifest))
    return {name: mock.get(f"{SERVER}/dist/data/{name}").mock(return_value=httpx.Response(200, content=data))
            for name, data in files.items()}


def root() -> Path:
    return agent.CONFIG_DIR / "data"


def versions() -> list[str]:
    return sorted(p.name for p in root().iterdir() if p.is_dir())


# --- manifest -----------------------------------------------------------------------------------

def test_signature_tampering_is_refused(tmp_path, key):
    m = make_release(tmp_path, key, BUNDLED + 1, {"knowledge/faq.json": b'{"entries": []}'})
    assert release.verify_data(m)
    entry = m["files"]["knowledge/faq.json"]
    for tampered in ({**m, "data_version": m["data_version"] + 1}, {**m, "min_app": "1.0.0"}, {**m, "app": "1.3"},
                     {**m, "files": {"knowledge/faq.json": {**entry, "sha256": "0" * 64}}},
                     {**m, "files": {**m["files"], "rules/graduation.json": entry}},
                     {**m, "note": "a phishing link"}):
        assert not release.verify_data(tampered)
    other = make_release(tmp_path / "other", Ed25519PrivateKey.generate(), BUNDLED + 1, {"rules/x.json": b"{}"})
    assert not release.verify_data(other)
    for bad in ("../secrets.json", "knowledge/../../x.json", "knowledge/faq.py", "knowledge/학과.json", "faq.json"):
        assert not release.verify_data({**m, "files": {bad: entry}}), bad
    assert not release.verify_data({k: v for k, v in m.items() if k != "app"})
    big = {**entry, "size": release.MAX_DATA_FILE_BYTES + 1}  # over what one Lambda response can carry
    assert release.MAX_DATA_FILE_BYTES == 5 * 1024 * 1024 and not release.verify_data({**m, "files": {"rules/a.json": big}})
    with respx.mock as mock:
        serve(mock, {**m, "data_version": m["data_version"] + 1}, {})
        assert datasync.sync() == "ignored: not signed by the release key"
    assert datasync.generation() == 0 and not (root() / datasync.POINTER).exists()


def test_older_or_same_data_is_ignored(tmp_path, key):
    old = make_release(tmp_path / "old", key, BUNDLED, {"knowledge/faq.json": b'{"entries": []}'})
    with respx.mock as mock:
        serve(mock, old, {})
        assert datasync.sync() == "ignored: not newer than the package's data"
    files = {"rules/graduation.json": graduation_built("2099-01-02")}
    v2 = make_release(tmp_path / "v2", key, BUNDLED + 2, files)
    v1 = make_release(tmp_path / "v1", key, BUNDLED + 1, files)
    with respx.mock as mock:
        serve(mock, v2, files)
        assert datasync.sync(force=True) == f"updated to {BUNDLED + 2}"
    with respx.mock as mock:
        routes = serve(mock, v1, files)
        assert datasync.sync(force=True) == "up to date"
        assert not routes["rules/graduation.json"].called
    assert datasync.generation() == BUNDLED + 2


def test_data_for_a_newer_app_is_ignored(tmp_path, key):
    files = {"knowledge/faq.json": faq_with_extra_entry()}
    m = make_release(tmp_path, key, BUNDLED + 1, files, min_app="1.2.5")
    with respx.mock as mock:
        routes = serve(mock, m, files)
        assert datasync.sync() == "ignored: needs kw-mcp 1.2.5"
        assert not routes["knowledge/faq.json"].called
    assert datasync.generation() == 0


@pytest.mark.parametrize("app", ["1.1", "1.3", "2.2"])
def test_data_of_another_release_series_is_ignored(tmp_path, key, app):
    """Data signed from a 1.1 tree can't roll 1.2's data shape back (nor 1.3's run on 1.2), even though
    its min_app is low enough and its data_version is newer."""
    files = {"knowledge/faq.json": faq_with_extra_entry()}
    m = make_release(tmp_path, key, BUNDLED + 9, files, min_app="1.0.0", app=app)
    with respx.mock as mock:
        routes = serve(mock, m, files)
        assert datasync.sync() == f"ignored: made for kw-mcp {app}"
        assert not routes["knowledge/faq.json"].called
    make_release(tmp_path / "dir", key, BUNDLED + 9, files, min_app="1.0.0", app=app)  # nor from a folder
    (root() / str(BUNDLED + 9)).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "dir").rename(root() / str(BUNDLED + 9))
    (root() / datasync.POINTER).write_text(f"{BUNDLED + 9}\n")
    assert datasync.generation() == 0


def test_a_file_that_does_not_match_its_hash_is_refused(tmp_path, key):
    files = {"knowledge/faq.json": faq_with_extra_entry()}
    m = make_release(tmp_path, key, BUNDLED + 1, files)
    with respx.mock as mock:
        serve(mock, m, {"knowledge/faq.json": files["knowledge/faq.json"].replace(b"entries", b"entriez")})
        assert datasync.sync() == "failed: LookupError"
    with respx.mock as mock:  # longer than signed: stops reading at the signed size
        serve(mock, m, {"knowledge/faq.json": files["knowledge/faq.json"] + b" " * 10})
        assert datasync.sync(force=True) == "failed: LookupError"
    assert datasync.generation() == 0 and versions() == []


# --- switching, partial downloads, pruning -------------------------------------------------------

def test_only_changed_files_are_downloaded_and_hashed_urls_are_asked_for(tmp_path, key):
    unchanged = (PACKAGE / "rules" / "multi_major.json").read_bytes()
    files = {"knowledge/faq.json": faq_with_extra_entry(), "rules/multi_major.json": unchanged}
    m = make_release(tmp_path, key, BUNDLED + 1, files)
    with respx.mock as mock:
        routes = serve(mock, m, files)
        assert datasync.sync() == f"updated to {BUNDLED + 1}"
        assert not routes["rules/multi_major.json"].called  # the package already has these bytes
        asked = routes["knowledge/faq.json"].calls.last.request.url
        assert asked.params["sha256"] == m["files"]["knowledge/faq.json"]["sha256"]
    current = root() / str(BUNDLED + 1)
    assert datasync.path("rules/multi_major.json") == current / "rules" / "multi_major.json"
    assert datasync.path("rules/graduation.json") == PACKAGE / "rules" / "graduation.json"  # not in this release
    assert (root() / datasync.POINTER).read_text().strip() == str(BUNDLED + 1)


def test_a_partial_download_leaves_the_old_data_in_place(tmp_path, key):
    v1_files = {"rules/graduation.json": graduation_built("2099-01-01")}
    v1 = make_release(tmp_path / "v1", key, BUNDLED + 1, v1_files)
    with respx.mock as mock:
        serve(mock, v1, v1_files)
        assert datasync.sync() == f"updated to {BUNDLED + 1}"
    v2_files = {"rules/graduation.json": graduation_built("2099-02-02"), "knowledge/faq.json": faq_with_extra_entry()}
    v2 = make_release(tmp_path / "v2", key, BUNDLED + 2, v2_files)
    with respx.mock as mock:
        serve(mock, v2, {"rules/graduation.json": v2_files["rules/graduation.json"]})
        mock.get(f"{SERVER}/dist/data/knowledge/faq.json").mock(side_effect=httpx.ReadError("cut off"))
        assert datasync.sync(force=True) == "failed: ReadError"
    assert (root() / datasync.POINTER).read_text().strip() == str(BUNDLED + 1)
    assert versions() == [str(BUNDLED + 1)]  # no half-written version, no partial folder
    assert datasync.generation() == BUNDLED + 1
    assert simulation.rules("graduation")["version"]["built_at"] == "2099-01-01"


def test_at_most_two_versions_are_kept(tmp_path, key):
    for n in (1, 2, 3):
        files = {"rules/graduation.json": graduation_built(f"2099-01-0{n}")}
        m = make_release(tmp_path / str(n), key, BUNDLED + n, files)
        with respx.mock as mock:
            serve(mock, m, files)
            assert datasync.sync(force=True) == f"updated to {BUNDLED + n}"
    assert versions() == [str(BUNDLED + 2), str(BUNDLED + 3)]
    assert simulation.rules("graduation")["version"]["built_at"] == "2099-01-03"


def test_a_check_runs_at_most_once_a_day_and_never_raises(tmp_path, key):
    with respx.mock as mock:
        mock.get(f"{SERVER}/dist/data/data.json").mock(return_value=httpx.Response(503))
        assert datasync.sync() == "failed: LookupError"
        assert datasync.sync() == "not due"
        mock.get(f"{SERVER}/dist/data/data.json").mock(side_effect=httpx.ConnectError("offline"))
        assert datasync.sync(force=True) == "failed: ConnectError"
        mock.get(f"{SERVER}/dist/data/data.json").mock(return_value=httpx.Response(200, content=b"not json"))
        assert datasync.sync(force=True) == "failed: JSONDecodeError"
        mock.get(f"{SERVER}/dist/data/data.json").mock(return_value=httpx.Response(404))
        assert datasync.sync(force=True) == "no data release on the server"
    status = datasync.status()
    assert status["using"] == "내장 자료" and status["bundled"] == BUNDLED and status["server"] is None
    assert status["last_checked"].endswith("KST") and status["last_result"] == "no data release on the server"


# --- loaders ----------------------------------------------------------------------------------

def test_loaders_fall_back_to_the_package_files(tmp_path, key, monkeypatch):
    assert datasync.path("knowledge/faq.json") == PACKAGE / "knowledge" / "faq.json"
    files = {"rules/graduation.json": graduation_built("2099-03-03")}
    m = make_release(tmp_path, key, BUNDLED + 1, files)
    with respx.mock as mock:
        serve(mock, m, files)
        datasync.sync()
    assert simulation.rules("graduation")["version"]["built_at"] == "2099-03-03"
    cached = root() / str(BUNDLED + 1) / "rules" / "graduation.json"
    cached.write_bytes(cached.read_bytes().replace(b"2099-03-03", b"2099-03-04"))  # corrupted on disk
    (root() / datasync.POINTER).write_text(f"{BUNDLED + 1}\n")  # noticed when the pointer changes
    assert datasync.generation() == 0
    assert simulation.rules("graduation") == json.loads((PACKAGE / "rules" / "graduation.json").read_text())
    (root() / datasync.POINTER).write_text("../../elsewhere\n")
    assert datasync.path("rules/graduation.json") == PACKAGE / "rules" / "graduation.json"
    monkeypatch.setattr(datasync, "bundled_version", lambda: None)  # a source checkout: its own files only
    assert datasync.sync(force=True) == "off" and datasync.generation() == 0


async def test_knowledge_search_sees_new_data_after_the_switch(tmp_path, key):
    assert all(h["id"] != "test-datasync-entry" for h in knowledge.search(QUESTION))
    before = knowledge.load()
    files = {"knowledge/faq.json": faq_with_extra_entry(), "rules/graduation.json": graduation_built("2099-04-04")}
    m = make_release(tmp_path, key, BUNDLED + 1, files)
    with respx.mock as mock:
        serve(mock, m, files)
        assert datasync.sync() == f"updated to {BUNDLED + 1}"
    assert knowledge.search(QUESTION)[0]["id"] == "test-datasync-entry"  # no restart, no cache_clear
    assert knowledge.load() is not before and knowledge.entry("test-datasync-entry")
    assert simulation.rules("graduation")["version"]["built_at"] == "2099-04-04"
    year = knowledge.load()["curricula_index"]["departments"][0]
    assert knowledge.curriculum(year["department"], year["admission_years"][0])  # not in the release: the package's
    out = await server.klas_status()
    assert out["data"]["using"] == f"서버 자료 {BUNDLED + 1}" and out["data"]["bundled"] == BUNDLED


def test_the_lambda_reads_a_verified_data_dir_and_never_syncs(tmp_path, key, monkeypatch):
    files = {"rules/graduation.json": graduation_built("2099-05-05")}
    make_release(tmp_path / "static" / "data", key, BUNDLED + 1, files)
    monkeypatch.setenv(datasync.DATA_DIR_ENV, str(tmp_path / "static" / "data"))
    assert datasync.path("rules/graduation.json") == tmp_path / "static" / "data" / "rules" / "graduation.json"
    assert simulation.rules("graduation")["version"]["built_at"] == "2099-05-05"
    assert datasync.sync(force=True) == "off" and not datasync.start_background_sync()
    unsigned = tmp_path / "unsigned"
    make_release(unsigned, Ed25519PrivateKey.generate(), BUNDLED + 1, files)
    monkeypatch.setenv(datasync.DATA_DIR_ENV, str(unsigned))
    assert datasync.path("rules/graduation.json") == PACKAGE / "rules" / "graduation.json"


# --- the data release and build_lambda's check ---------------------------------------------------

def test_check_data_refuses_a_bad_signature_a_changed_file_or_an_unlisted_one(tmp_path, key):
    public = release.PUBLIC_KEY
    m = make_release(tmp_path, key, BUNDLED + 1, {"knowledge/faq.json": b'{"entries": []}', "rules/a.json": b"{}"})
    assert release.check_data(tmp_path, public)["data_version"] == BUNDLED + 1
    (tmp_path / "rules" / "a.json").write_bytes(b"[]")
    with pytest.raises(ValueError, match="rules/a.json"):
        release.check_data(tmp_path)
    (tmp_path / "rules" / "a.json").write_bytes(b"{}")
    (tmp_path / "rules" / "extra.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="does not list: rules/extra.json"):
        release.check_data(tmp_path)
    (tmp_path / "rules" / "extra.json").unlink()
    (tmp_path / "data.json").write_text(json.dumps({**m, "signature": m["signature"][::-1]}))
    with pytest.raises(ValueError, match="not signed"):
        release.check_data(tmp_path)
    # what build_lambda.sh runs: the shipped key, so a throwaway-signed (dry-run) folder fails too
    (tmp_path / "data.json").write_text(json.dumps(m))
    done = subprocess.run([sys.executable, "-m", "kw_mcp.release", "check-data", str(tmp_path)],
                          capture_output=True, text=True, check=False)
    assert done.returncode != 0 and "data check failed" in done.stderr


def test_sign_data_takes_json_data_files_only(tmp_path, key):
    (tmp_path / "rules").mkdir()
    (tmp_path / "rules" / "a.json").write_text("not json")
    with pytest.raises(ValueError):
        release.sign_data(tmp_path, ["rules/a.json"], BUNDLED, "1.2", "1.2.0", key)
    with pytest.raises(ValueError, match="not a data file path"):
        release.sign_data(tmp_path, ["../rules/a.json"], BUNDLED, "1.2", "1.2.0", key)
    assert release.data_version_at(datetime(2026, 11, 7, 12, 30, 5, tzinfo=UTC)) == 20261107123005


def test_the_extension_carries_its_data_version():
    assert release.bundle_extras(["src/kw_mcp/data_version"]) == []
    assert release.bundle_extras(["src/kw_mcp/data_version.txt", "src/kw_mcp/data/x.json"]) != []


def test_the_data_release_takes_every_knowledge_and_rules_file(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    try:
        import release as release_script
    finally:
        sys.path.pop(0)
    names = release_script.data_files(PACKAGE)
    assert "knowledge/faq.json" in names and "rules/graduation.json" in names
    assert all(release.DATA_FILE.fullmatch(n) for n in names)
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge" / "notes.md").write_text("x")
    with pytest.raises(release_script.ReleaseError, match="notes.md"):
        release_script.data_files(tmp_path)


# --- one data version per tool call -----------------------------------------------------------------

def switch_to(tmp_path, private, n: int) -> None:
    """A sync that installs version BUNDLED + n of graduation.json and multi_major.json (built_at 2099-0n-0n)."""
    when = f"2099-0{n}-0{n}"
    files = {"rules/graduation.json": graduation_built(when), "rules/multi_major.json": graduation_built(when, "multi_major")}
    m = make_release(tmp_path / str(n), private, BUNDLED + n, files)
    with respx.mock as mock:
        serve(mock, m, files)
        assert datasync.sync(force=True) == f"updated to {BUNDLED + n}"


def test_a_call_never_mixes_two_data_versions(tmp_path, key):
    switch_to(tmp_path, key, 1)
    with datasync.pinned() as snap:
        assert simulation.rules("graduation")["version"]["built_at"] == "2099-01-01"
        switch_to(tmp_path, key, 2)  # the daily switch, in the middle of a graduation_outlook
        assert simulation.rules("multi_major")["version"]["built_at"] == "2099-01-01"  # not v2's
        assert knowledge.load() is knowledge._load(snap) and datasync.snapshot() == snap
    assert simulation.rules("multi_major")["version"]["built_at"] == "2099-02-02"  # the next call
    assert simulation.rules("graduation")["version"]["built_at"] == "2099-02-02"


async def test_server_tools_and_agent_answers_are_pinned(tmp_path, key, monkeypatch):
    switch_to(tmp_path, key, 1)
    seen = []

    def guide(question, category=None):
        seen.append(datasync.snapshot())
        switch_to(tmp_path, key, len(seen) + 1)
        seen.append(datasync.snapshot())
        return {"answers": []}

    monkeypatch.setattr(knowledge, "guide", guide)
    result = await server.mcp.call_tool("school_guide", {"question": "x"})
    assert not result.is_error and seen[0] == seen[1] and seen[0].version == BUNDLED + 1

    class Service:
        async def graduation_outlook(self):
            before = datasync.snapshot()
            switch_to(tmp_path, key, 3)
            return {"same": before == datasync.snapshot(), "version": before.version}

    class Holder:
        async def service(self):
            return Service()

    sent = []
    monkeypatch.setattr(agent, "encrypt_result", lambda key, request_id, data: sent.append(data) or {"ct": ""})

    async def posted(http, url, body):
        return "202"

    monkeypatch.setattr(agent, "_post_result", posted)
    link = agent.Link(SERVER, "wss://ws.example/prod", "u1")
    message = {"type": "call", "op": "graduation_outlook", "request_id": "r1", "key": agent.b64u(b"k" * 32),
               "result_url": f"{SERVER}/device/result"}
    await agent.answer(Holder(), link, message, None)
    assert sent == [{"result": {"same": True, "version": BUNDLED + 2}}]
    assert datasync.snapshot().version == BUNDLED + 3


def test_a_cached_file_changed_after_it_was_verified_is_not_read(tmp_path, key):
    switch_to(tmp_path, key, 1)
    snap = datasync.snapshot()
    cached = root() / str(BUNDLED + 1) / "rules" / "graduation.json"
    cached.write_bytes(cached.read_bytes().replace(b"2099-01-01", b"2099-01-09"))  # pointer unchanged
    with pytest.raises(LookupError):
        datasync.read("rules/graduation.json", snap)
    assert datasync.snapshot() is None  # verified again: the package's data from now on
    assert simulation.rules("graduation") == json.loads((PACKAGE / "rules" / "graduation.json").read_text())


def test_data_is_cut_only_from_the_latest_released_version(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    try:
        import release as release_script
    finally:
        sys.path.pop(0)
    repo = tmp_path / "repo"
    repo.mkdir()
    for name, text in {"pyproject.toml": '[project]\nname = "kw-mcp"\nversion = "1.2.0"\n',
                       "manifest.json": json.dumps({"version": "1.2.0"}),
                       "uv.lock": 'version = 1\n\n[[package]]\nname = "kw-mcp"\nversion = "1.2.0"\n'}.items():
        (repo / name).write_text(text)
    for args in (["init", "-q"], ["add", "."], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
                 ["tag", "v1.1.0"]):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    with pytest.raises(release_script.ReleaseError, match="latest release is 1.1.0"):
        release_script.build_data(repo, tmp_path / "out")  # 1.2.0 isn't released yet
    subprocess.run(["git", "tag", "v1.3.0"], cwd=repo, check=True, capture_output=True)
    with pytest.raises(release_script.ReleaseError, match="latest release is 1.3.0"):
        release_script.build_data(repo, tmp_path / "out")  # an older tree than the latest release
    (repo / "dist" / "release").mkdir(parents=True)
    (repo / "dist" / "release" / "latest.json").write_text(json.dumps({"version": "1.4.0"}))
    assert release_script.latest_release(repo) == "1.4.0"
    assert release.app_series("1.2.10") == "1.2" and not (tmp_path / "out").exists()
