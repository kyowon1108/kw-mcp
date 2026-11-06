"""New versions of the Claude Desktop extension.

Claude Desktop does not update an extension installed from a file. So the extension reads the
server's latest.json itself (its "mcpb" entry, signed on the release machine; see release.py),
mentions a newer version in the combined tools' answers, and on request saves the new file after
checking the signature and the hash. A compromised server can't make it offer a file we didn't sign.

Only inside the extension (KW_MCP_DISTRIBUTION=mcpb) and only with an invite, which names the server.
Without one, check() says so instead of quietly reporting "no new version".
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from . import release
from .agent import installed_version, parse_invite

__all__ = ["check", "download", "enabled", "installed_version", "latest", "notice", "server", "unavailable_reason"]

CHECK_EVERY_S = 6 * 3600
RETRY_AFTER_FAILURE_S = 600
CHECK_DEADLINE_S = 8.0  # whole request, not per read: a server trickling bytes can't hold us
DOWNLOAD_DEADLINE_S = 120.0
MAX_MANIFEST_BYTES = 64 * 1024
MAX_MCPB_BYTES = 20 * 1024 * 1024
RAW = {"Accept-Encoding": "identity"}  # caps count bytes received, so no decompression

_cache: tuple[float, float, dict[str, Any] | None] | None = None  # (checked_at, valid_for, newer)
_last_ok = True  # whether the latest check reached the server and read its manifest
_lock: asyncio.Lock | None = None


def enabled() -> bool:
    return os.environ.get("KW_MCP_DISTRIBUTION") == "mcpb"


def _invite() -> str:
    invite = os.environ.get("KW_CAMPUS_INVITE", "").strip()
    return "" if invite.startswith("${") else invite  # Claude Desktop passes an empty field through as "${user_config.…}"


def server() -> str | None:
    invite = _invite()
    try:
        return parse_invite(invite)[0] if invite else None
    except ValueError:
        return None


def unavailable_reason() -> str | None:
    """Why this copy can't look for new versions, or None if it can."""
    if not enabled():
        return "새 버전 확인은 Claude 데스크톱 확장에서만 합니다. PC 에이전트는 스스로 업데이트합니다(`kw-mcp update`)."
    invite = _invite()
    if not invite:
        return ("초대 코드가 없어 새 버전을 확인할 수 없습니다(보안 수정 포함). Claude 데스크톱 설정 → 확장 프로그램 → "
                "KW CAMPUS (광운 캠퍼스) → 구성에 초대 코드를 넣거나, 초대해 준 사람에게 최신 파일을 받으세요.")
    try:
        parse_invite(invite)
    except ValueError as e:
        return f"초대 코드를 읽지 못해 새 버전을 확인할 수 없습니다: {e} 확장 설정에서 초대 코드를 다시 붙여 넣으세요."
    return None


async def latest(http: httpx.AsyncClient | None = None, *, force: bool = False) -> dict[str, Any] | None:
    """The newer signed extension release, or None (up to date, can't check, or the check failed)."""
    global _cache, _lock, _last_ok
    base = server() if enabled() else None
    if not base:
        return None
    _lock = _lock or asyncio.Lock()
    async with _lock:
        if _cache and not force and time.monotonic() - _cache[0] < _cache[1]:
            return _cache[2]
        newer, _last_ok = await _fetch(base, http)
        _cache = (time.monotonic(), CHECK_EVERY_S if _last_ok else RETRY_AFTER_FAILURE_S, newer)
        return newer


async def check(http: httpx.AsyncClient | None = None) -> dict[str, Any]:
    """What check_update answers: the installed version, a newer signed one if any, and when the
    check could not run, the reason (no invite, a malformed one, the server unreachable)."""
    out: dict[str, Any] = {"installed": installed_version(), "checked": False, "update_available": None}
    if reason := unavailable_reason():
        return {**out, "reason": reason}
    newer = await latest(http, force=True)
    if not _last_ok:
        return {**out, "reason": "업데이트 서버에 연결하지 못했습니다. 잠시 뒤 다시 확인하세요."}
    return {**out, "checked": True, "update_available": notice(newer) if newer else None}


async def _read_capped(response: httpx.Response, cap: int) -> bytes:
    chunks, total = [], 0
    async for chunk in response.aiter_raw():
        total += len(chunk)
        if total > cap:
            raise LookupError("응답이 예상보다 큽니다.")
        chunks.append(chunk)
    return b"".join(chunks)


async def _fetch(base: str, http: httpx.AsyncClient | None) -> tuple[dict[str, Any] | None, bool]:
    """(newer release or None, whether the check itself worked)."""
    client = http or httpx.AsyncClient(timeout=httpx.Timeout(5.0))
    try:
        async with asyncio.timeout(CHECK_DEADLINE_S):
            async with client.stream("GET", f"{base}/dist/latest.json", headers=RAW) as response:
                if response.status_code != 200:
                    return None, False  # 5xx or throttled: try again soon, not in 6 hours
                body = await _read_capped(response, MAX_MANIFEST_BYTES)
        entry = json.loads(body).get("mcpb")
    except Exception:  # noqa: BLE001 -- whatever the server sends, the KLAS tools must keep working
        return None, False
    finally:
        if http is None:
            await client.aclose()
    if not isinstance(entry, dict) or not release.verify_mcpb(entry):
        return None, True
    current = installed_version()
    if release.version_tuple(entry["version"]) <= release.version_tuple(current):
        return None, True
    return {"version": entry["version"], "installed": current, "sha256": entry["sha256"],
            "url": f"{base}/dist/{entry['file']}"}, True


def notice(newer: dict[str, Any]) -> dict[str, str]:
    """What the combined tools add to their answer when a newer version exists."""
    # No link here: a file fetched by hand skips the signature check that download_update does.
    return {"installed": newer["installed"], "latest": newer["version"],
            "message": "KW CAMPUS 확장의 새 버전이 있습니다. 사용자가 원하면 download_update 도구로 받으세요"
                       "(서명을 확인한 파일만 다운로드 폴더에 저장합니다)."}


def downloads_dir() -> Path:
    downloads = Path.home() / "Downloads"
    return downloads if downloads.is_dir() else Path.home()


async def download(http: httpx.AsyncClient | None = None, dest_dir: Path | None = None) -> Path:
    """Save the newer extension after checking it against the signed hash. Returns the file."""
    if reason := unavailable_reason():
        raise LookupError(reason)
    newer = await latest(http, force=True)
    if not newer:
        if not _last_ok:
            raise LookupError("업데이트 서버에 연결하지 못했습니다. 잠시 뒤 다시 시도하세요.")
        raise LookupError("받을 새 버전이 없습니다. 이미 최신 버전입니다.")
    client = http or httpx.AsyncClient(timeout=httpx.Timeout(30.0))
    try:
        async with asyncio.timeout(DOWNLOAD_DEADLINE_S):
            async with client.stream("GET", newer["url"], headers=RAW) as response:
                if response.status_code != 200:
                    raise LookupError(f"새 버전 파일을 받지 못했습니다(HTTP {response.status_code}).")
                data = await _read_capped(response, MAX_MCPB_BYTES)
    except (httpx.HTTPError, TimeoutError) as e:
        raise LookupError(f"새 버전 파일을 받지 못했습니다({e.__class__.__name__}).") from e
    finally:
        if http is None:
            await client.aclose()
    if hashlib.sha256(data).hexdigest() != newer["sha256"]:
        raise LookupError("받은 파일이 서명된 해시와 달라 저장하지 않았습니다.")
    folder = dest_dir or downloads_dir()
    path = folder / f"kw-campus-{newer['version']}.mcpb"
    partial = path.with_suffix(".part")
    try:
        partial.write_bytes(data)
        partial.replace(path)
    except OSError as e:
        with contextlib.suppress(OSError):  # a folder we can't write may not let us look either
            partial.unlink(missing_ok=True)
        raise LookupError(f"{folder}에 저장하지 못했습니다({e.strerror or e}). Claude에 그 폴더 접근 권한이 있는지 확인하세요.") from e
    return path
