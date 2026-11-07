"""Newer academic data without a new release: the knowledge base (knowledge/) and the graduation and
다전공 rules (rules/), fetched from the bridge and signed with the release key.

The package carries its own copy of these files and their version in `data_version` (written by
scripts/release.sh: the release commit's UTC time as YYYYMMDDHHMMSS). To fix data without a release, the
owner runs `scripts/release.sh data`; the bridge then serves /dist/data/data.json (format in release.py)
and the files it lists, under their package paths.

sync(), at most once a day in a background thread (the MCP server when it has an invite, and the PC agent),
reads data.json from release.bridge_origin() and takes it only if it is signed by the release key, its
min_app is not above this version and its data_version is above both the package's and the cached one.
Then it fetches only the files that changed (each checked against its signed size and sha256, and parsed
as JSON: data is never executed), copies the unchanged ones from the data in use, writes them all to
~/.config/kw-campus/data/<data_version>/ and only then switches the `current` pointer file there. A
failure anywhere leaves the pointer, and so the data in use, as it was. Two versions are kept.

read(name, snap) is how the loaders (knowledge, simulation.rules) get a file like "knowledge/faq.json": from
the snapshot's folder if it lists the file (hashed again against its signed entry on every read), else the
package's own. snapshot() is the verified data in use (active(): verified again, signature, versions and
every file, each time the pointer changes, which it stats on every call), and the loaders cache per snapshot,
so a running process takes newer data on its next load without a restart. One tool call never mixes two
versions: the MCP server's tool wrapper and the PC agent's answer to a bridge call run inside pinned(), so
every load in it reads the snapshot taken when the call began; a switch meanwhile applies from the next call.

A source checkout (no data_version file) uses its own files and never syncs. In the bridge's Lambda,
KW_DATA_DIR names the bundle's static/data folder (kw-campus build_lambda.sh copies a checked data release
there, run.sh sets the variable): it is verified the same way and nothing is downloaded.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import random
import shutil
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import release

log = logging.getLogger("kw_mcp.datasync")

PACKAGE_DIR = Path(__file__).parent
DATA_DIR_ENV = "KW_DATA_DIR"
# The lowest kw-mcp whose loaders read data shaped like this checkout's; `scripts/release.sh data` writes it
# as min_app. Raise it with a data change older loaders would misread (a renamed or newly required field).
MIN_APP = "1.2.0"
CHECK_EVERY_S = 24 * 3600
DEADLINE_S = 120.0  # one whole sync: a server trickling bytes can't hold the thread
MAX_MANIFEST_BYTES = 512 * 1024
KEEP_VERSIONS = 2
POINTER = "current"
STATE = "state.json"
RAW = {"Accept-Encoding": "identity"}  # the caps count bytes received, so no decompression
KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class Active:
    """A verified data version: equal (and hashed, as the loaders' cache key) by folder, version and files."""
    version: int
    folder: Path
    files: frozenset[str]
    signed: dict[str, tuple[str, int]] = field(compare=False, hash=False, repr=False)  # name -> (sha256, size)


_lock = threading.Lock()
_seen: tuple[Any, Active | None] | None = None  # (the pointer's stat, the verified data it named)
_started = False
_UNPINNED: Any = object()
_pin: ContextVar[Any] = ContextVar("kw_mcp_data_pin", default=_UNPINNED)


@functools.cache
def bundled_version() -> int | None:
    """The version of the package's own data files, or None in a source checkout."""
    try:
        text = (PACKAGE_DIR / release.DATA_VERSION_FILE).read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return int(text) if text.isdigit() else None


def app_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("kw-mcp")
    except PackageNotFoundError:
        return "0"


def data_root() -> Path:
    from . import agent  # its CONFIG_DIR, read when called (tests point it elsewhere)

    return agent.CONFIG_DIR / "data"


def _fixed_dir() -> Path | None:
    value = os.environ.get(DATA_DIR_ENV, "").strip()
    return Path(value) if value else None


def _unusable(manifest: Any) -> str | None:
    """Why this data.json can't be used here, or None."""
    if not release.verify_data(manifest):
        return "not signed by the release key"
    if manifest["app"] != release.app_series(app_version()):  # another series' data shape, older or newer
        return f"made for kw-mcp {manifest['app']}"
    if release.version_tuple(manifest["min_app"]) > release.version_tuple(app_version()):
        return f"needs kw-mcp {manifest['min_app']}"
    bundled = bundled_version()
    if bundled is None or manifest["data_version"] <= bundled:
        return "not newer than the package's data"
    return None


def _digest(path: Path) -> tuple[str, int]:
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def _verified(folder: Path) -> Active | None:
    """The data in folder if its data.json is usable here and every file matches it, else None."""
    try:
        manifest = json.loads((folder / release.DATA_MANIFEST_NAME).read_text(encoding="utf-8"))
        if problem := _unusable(manifest):
            log.warning("not using the data in %s: %s", folder, problem)
            return None
        for name, entry in manifest["files"].items():
            if _digest(folder / name) != (entry["sha256"], entry["size"]):
                log.warning("not using the data in %s: %s does not match data.json", folder, name)
                return None
    except (OSError, ValueError) as e:
        log.warning("not using the data in %s (%s)", folder, e.__class__.__name__)
        return None
    signed = {name: (entry["sha256"], entry["size"]) for name, entry in manifest["files"].items()}
    return Active(manifest["data_version"], folder, frozenset(signed), signed)


def _pointed(root: Path) -> Path | None:
    try:
        name = (root / POINTER).read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return root / name if name.isdigit() else None


def active() -> Active | None:
    """The verified data used instead of the package's, or None. Verified again whenever the pointer
    (or KW_DATA_DIR's data.json) changes."""
    global _seen
    if bundled_version() is None:
        return None
    fixed = _fixed_dir()
    marker = fixed / release.DATA_MANIFEST_NAME if fixed else data_root() / POINTER
    try:
        st = marker.stat()
        key: Any = (str(marker), st.st_ino, st.st_mtime_ns, st.st_size)
    except OSError:
        key = (str(marker), None)
    seen = _seen
    if seen is not None and seen[0] == key:
        return seen[1]
    with _lock:
        if _seen is None or _seen[0] != key:
            folder = fixed if fixed else _pointed(marker.parent)
            _seen = (key, _verified(folder) if key[1] is not None and folder else None)
        return _seen[1]


def generation() -> int:
    """The version of the data in use (0: the package's own)."""
    found = active()
    return found.version if found else 0


def snapshot() -> Active | None:
    """The data a load reads now (None: the package's own): the one pinned for this call, else active()."""
    pinned_now = _pin.get()
    return active() if pinned_now is _UNPINNED else pinned_now


@contextmanager
def pinned() -> Iterator[Active | None]:
    """Run one tool call on one data version: every load inside (tasks and to_thread too, which copy the
    context) reads the snapshot taken here, even if sync switches meanwhile. Nested, the outer one holds."""
    token = _pin.set(snapshot())
    try:
        yield _pin.get()
    finally:
        _pin.reset(token)


def path(name: str, snap: Any = _UNPINNED) -> Path:
    """Where a data file like "knowledge/faq.json" is: in the snapshot (default: snapshot()) if it lists
    the file, else in the package."""
    snap = snapshot() if snap is _UNPINNED else snap
    return snap.folder / name if snap is not None and name in snap.files else PACKAGE_DIR / name


def read(name: str, snap: Active | None) -> bytes:
    """A data file's bytes from the snapshot (None: the package's own). A downloaded copy is hashed against
    its signed entry first; one changed on disk since it was verified is refused, and the next snapshot is
    verified again (so it falls back to the package's data)."""
    data = path(name, snap).read_bytes()
    if snap is not None and name in snap.files:
        sha256, size = snap.signed[name]
        if len(data) != size or hashlib.sha256(data).hexdigest() != sha256:
            global _seen
            _seen = None
            log.warning("%s in %s changed after it was verified; not using it", name, snap.folder)
            raise LookupError(f"{name} 자료 파일이 확인한 뒤에 바뀌었어요. 다시 물어봐 주세요.")
    return data


# --- sync --------------------------------------------------------------------------------------

def _state() -> dict[str, Any]:
    try:
        state = json.loads((data_root() / STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return state if isinstance(state, dict) else {}


def _save_state(**fields: Any) -> None:
    root = data_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    partial = root / f"{STATE}.{os.getpid()}.tmp"
    partial.write_text(json.dumps({**_state(), **fields}), encoding="utf-8")
    os.replace(partial, root / STATE)


def _due() -> float:
    """Seconds until the next check (0: now). Shared by every process on this PC through state.json."""
    checked = _state().get("last_checked")
    if not isinstance(checked, (int, float)):
        return 0.0
    left = checked + CHECK_EVERY_S - time.time()
    return 0.0 if left > CHECK_EVERY_S else max(0.0, left)  # a clock set back counts as due


def _get(client: Any, url: str, cap: int, deadline: float) -> bytes | None:
    """The body (None on 404), refusing more than cap bytes or a reply past the deadline."""
    with client.stream("GET", url, headers=RAW) as response:
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise LookupError(f"HTTP {response.status_code}")
        chunks, total = [], 0
        for chunk in response.iter_raw():
            total += len(chunk)
            if total > cap:
                raise LookupError("larger than its signed size")
            if time.monotonic() > deadline:
                raise TimeoutError
            chunks.append(chunk)
    return b"".join(chunks)


def _local_copy(name: str, entry: dict[str, Any], current: Active | None) -> bytes | None:
    """The file's signed bytes if the data in use or the package already has them."""
    for folder in ([current.folder] if current and name in current.files else []) + [PACKAGE_DIR]:
        try:
            data = (folder / name).read_bytes()
        except OSError:
            continue
        if len(data) == entry["size"] and hashlib.sha256(data).hexdigest() == entry["sha256"]:
            return data
    return None


def _download(client: Any, base: str, name: str, entry: dict[str, Any], deadline: float) -> bytes:
    data = _get(client, f"{base}/dist/data/{name}?sha256={entry['sha256']}", entry["size"], deadline)
    if data is None or len(data) != entry["size"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise LookupError(f"{name} is missing or does not match its signed hash")
    json.loads(data)  # JSON only
    return data


def _prune(root: Path, current: int) -> None:
    """Keep the current version and the newest other one; drop partial copies older than a sync."""
    versions = sorted((int(p.name) for p in root.iterdir() if p.is_dir() and p.name.isdigit()), reverse=True)
    keep = {current, *[v for v in versions if v != current][:KEEP_VERSIONS - 1]}
    for v in versions:
        if v not in keep:
            shutil.rmtree(root / str(v), ignore_errors=True)
    for p in root.glob("*.partial-*"):
        if p.is_dir() and time.time() - p.stat().st_mtime > 2 * DEADLINE_S:
            shutil.rmtree(p, ignore_errors=True)


def _install(client: Any, base: str, manifest: dict[str, Any], current: Active | None, deadline: float) -> str:
    root = data_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    version = manifest["data_version"]
    final = root / str(version)
    if not (final.is_dir() and _verified(final)):  # not already there from another process or an earlier try
        work = Path(tempfile.mkdtemp(prefix=f"{version}.partial-", dir=root))
        try:
            fetched = 0
            for name, entry in sorted(manifest["files"].items()):
                data = _local_copy(name, entry, current)
                if data is None:
                    data, fetched = _download(client, base, name, entry, deadline), fetched + 1
                (work / name).parent.mkdir(parents=True, exist_ok=True)
                (work / name).write_bytes(data)
            (work / release.DATA_MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
            if _verified(work) is None:
                raise LookupError("the new data did not verify")
            if not (final.is_dir() and _verified(final)):
                shutil.rmtree(final, ignore_errors=True)
                work.rename(final)
            log.info("data %s: fetched %d of %d files", version, fetched, len(manifest["files"]))
        finally:
            shutil.rmtree(work, ignore_errors=True)
    partial = root / f"{POINTER}.{os.getpid()}.tmp"
    partial.write_text(f"{version}\n", encoding="ascii")
    os.replace(partial, root / POINTER)  # the switch: atomic, and only after the folder is complete
    _prune(root, version)
    return f"updated to {version}"


def _sync(http: Any) -> str:
    import httpx

    base = release.bridge_origin()
    deadline = time.monotonic() + DEADLINE_S
    client = http or httpx.Client(timeout=httpx.Timeout(10.0))
    try:
        body = _get(client, f"{base}/dist/data/{release.DATA_MANIFEST_NAME}", MAX_MANIFEST_BYTES, deadline)
        if body is None:
            return "no data release on the server"
        manifest = json.loads(body)
        if problem := _unusable(manifest):
            return f"ignored: {problem}"
        current = active()
        if current is not None and manifest["data_version"] <= current.version:
            return "up to date"
        return _install(client, base, manifest, current, deadline)
    finally:
        if http is None:
            client.close()


def sync(http: Any = None, *, force: bool = False) -> str:
    """One check of the bridge for newer data, unless one ran in the last 24 hours (force: check anyway).
    Returns what happened; never raises. Off in a source checkout and where KW_DATA_DIR is set."""
    if bundled_version() is None or _fixed_dir() is not None:
        return "off"
    try:
        if not force and _due() > 0:
            return "not due"
        _save_state(last_checked=time.time())  # first, so another process starting now waits its turn
        result = _sync(http)
    except Exception as e:  # noqa: BLE001 -- whatever the server or the disk does, the tools keep working
        result = f"failed: {e.__class__.__name__}"
    try:
        _save_state(last_result=result)
    except OSError:
        pass
    log.info("data check: %s", result)
    return result


def _loop() -> None:
    while True:
        sync()
        try:
            wait = _due()
        except Exception:  # noqa: BLE001
            wait = CHECK_EVERY_S
        time.sleep(max(wait, 60.0) + random.uniform(0, 600))


def start_background_sync() -> bool:
    """sync() now and then every 24 hours in a daemon thread, so no tool call waits for it. False when
    this copy doesn't sync (a source checkout, KW_DATA_DIR) or the thread already runs."""
    global _started
    if _started or bundled_version() is None or _fixed_dir() is not None:
        return False
    try:
        threading.Thread(target=_loop, name="kw-data-sync", daemon=True).start()
    except RuntimeError:
        return False
    _started = True
    return True


def status() -> dict[str, Any]:
    """klas_status's data line: the package's and the server's data versions, which is in use, the last check."""
    bundled = bundled_version()
    if bundled is None:
        return {"using": "내장 자료(소스 체크아웃: 서버 자료를 확인하지 않음)", "bundled": None, "server": None}
    found = active()
    out: dict[str, Any] = {"using": f"서버 자료 {found.version}" if found else "내장 자료",
                           "bundled": bundled, "server": found.version if found else None}
    if _fixed_dir() is not None:
        return out
    state = _state()
    checked = state.get("last_checked")
    out["last_checked"] = (datetime.fromtimestamp(checked, UTC).astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
                           if isinstance(checked, (int, float)) else "확인한 적 없음")
    if isinstance(state.get("last_result"), str):
        out["last_result"] = state["last_result"]
    return out
