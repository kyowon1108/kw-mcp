"""Client for the kw-campus public JSON API (notices, cafeteria menu, academic calendar).

Configured by KW_CAMPUS_INVITE (the kwc_... invite code; the Claude Desktop extension passes
it), KW_CAMPUS_API_URL (e.g. https://<api>.execute-api.ap-northeast-2.amazonaws.com/c/<token>),
or the first line of ~/.config/kw-campus/api-url. Without any, the combined tools still
work and just leave the public parts empty. Nothing personal is sent: requests carry only
the access token in the path and generic filters (category, date range).

A configured API that fails (expired invite, server error, timeout) raises PublicUnavailable with
a reason, so callers can say the school data is missing instead of reporting "no notices". So does
an invite that can't be read (a partial copy): the reason then starts with "초대 코드 형식 오류".
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import httpx

CONFIG_FILE = Path.home() / ".config" / "kw-campus" / "api-url"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEADLINE_S = 10.0  # whole request: httpx timeouts are per read, so a trickling server could stall the tools


class PublicUnavailable(Exception):
    """The configured public API did not answer usefully; str() is the reason, in Korean."""


class PublicRequestError(ValueError):
    """HTTP 400: the server understood the request and refused an argument (category, source, date).
    Not "school data unavailable": the caller asked for something wrong and must hear what."""


class UnknownCategory(PublicRequestError):
    """The server doesn't know the notice category asked for (HTTP 400 with the valid labels)."""


def _reason(status: int) -> str:
    if status in (403, 404):
        return (f"초대 코드가 만료됐거나 철회됐습니다(HTTP {status}). 새 초대 코드를 받아 "
                "확장 설정(또는 KW_CAMPUS_INVITE)에 넣으세요.")
    if status == 429:
        return "학교 공개 정보 서버가 요청이 많아 잠시 거절했습니다(HTTP 429)."
    if status >= 500:
        return f"학교 공개 정보 서버에 오류가 났습니다(HTTP {status})."
    return f"학교 공개 정보 서버가 요청을 거절했습니다(HTTP {status})."


def _from_invite(invite: str) -> tuple[str | None, str | None]:
    """(base URL, None) for a good invite; (None, why not) for one that can't be read, or that names a
    server other than the KW CAMPUS bridge (its token is never sent there)."""
    from .agent import official_invite

    try:
        server, token = official_invite(invite)
    except ValueError as e:  # a partial copy, a pasted /setup link, another server, ...
        return None, f"초대 코드 형식 오류: {e} 확장 설정(또는 KW_CAMPUS_INVITE)의 초대 코드를 다시 붙여 넣으세요."
    return f"{server}/c/{token}", None


def _resolve() -> tuple[str | None, str | None]:
    """(base URL, None), or (None, why the invite can't be used) when nothing else gives a URL either."""
    invite = os.environ.get("KW_CAMPUS_INVITE", "").strip()
    url, problem = _from_invite(invite) if invite else (None, None)
    url = url or os.environ.get("KW_CAMPUS_API_URL")
    if not url and CONFIG_FILE.exists():
        lines = CONFIG_FILE.read_text().split()
        url = lines[0] if lines else None
    return (url.rstrip("/"), None) if url else (None, problem)


def base_url() -> str | None:
    return _resolve()[0]


class PublicApi:
    def __init__(self, url: str | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._url, self._invalid = (url, None) if url is not None else _resolve()
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(10.0), transport=transport)

    @property
    def configured(self) -> bool:
        """An API URL or an invite is set. An invite that can't be read counts: every call then raises
        PublicUnavailable with invalid_reason, so answers say "초대 코드 형식 오류", not "not set up"."""
        return bool(self._url or self._invalid)

    @property
    def invalid_reason(self) -> str | None:
        """'초대 코드 형식 오류: …' when the invite is the only setting and can't be read; else None."""
        return self._invalid

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        """The JSON answer; None when no API is configured. PublicUnavailable when it fails."""
        if self._invalid:
            raise PublicUnavailable(self._invalid)
        if not self._url:
            return None
        query = {k: v for k, v in params.items() if v is not None}
        try:
            async with asyncio.timeout(DEADLINE_S), \
                    self._http.stream("GET", f"{self._url}{path}", params=query) as response:
                if response.status_code == 400:
                    raise _bad_request(params, await _head(response))
                if response.status_code != 200:
                    raise PublicUnavailable(_reason(response.status_code))
                chunks, total = [], 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > MAX_RESPONSE_BYTES:
                        raise PublicUnavailable("학교 공개 정보 응답이 너무 커서 읽지 않았습니다.")
                    chunks.append(chunk)
            data = json.loads(b"".join(chunks))
        except (PublicUnavailable, PublicRequestError):
            raise
        except TimeoutError as e:
            raise PublicUnavailable(f"학교 공개 정보 서버가 {int(DEADLINE_S)}초 안에 답하지 않았습니다.") from e
        except ValueError as e:
            raise PublicUnavailable("학교 공개 정보 응답 형식이 잘못됐습니다.") from e
        except Exception as e:  # public data is a bonus: any failure becomes a reason, personal tools keep working
            raise PublicUnavailable(f"학교 공개 정보 서버에 연결하지 못했습니다({e.__class__.__name__}).") from e
        if not isinstance(data, dict):
            raise PublicUnavailable("학교 공개 정보 응답 형식이 잘못됐습니다.")
        return data

    async def notices(self, category: str | None = None, limit: int = 10, query: str | None = None,
                      since: str | None = None, pinned: bool = True,
                      source: str | list[str] | None = None) -> list[dict[str, Any]]:
        """source: only these boards, filtered by the server before the limit ("kw-notice" is the main
        board); a list sends the parameter once per board."""
        data = await self._get("/api/notices", {"category": category, "limit": limit, "q": query,
                                                "since": since, "pinned": "true" if pinned else "false",
                                                "source": source or None})
        return _rows(data, "notices")

    async def menu(self, day: str | None = None) -> dict[str, Any] | None:
        return await self._get("/api/menu", {"date": day})

    async def calendar(self, start: str | None = None, end: str | None = None) -> list[dict[str, Any]]:
        data = await self._get("/api/calendar", {"from": start, "to": end})
        return _rows(data, "events")

    async def aclose(self) -> None:
        await self._http.aclose()


def _rows(data: dict[str, Any] | None, key: str) -> list[dict[str, Any]]:
    if data is None:
        return []
    rows = data.get(key)
    if not isinstance(rows, list):
        raise PublicUnavailable("학교 공개 정보 응답 형식이 잘못됐습니다.")
    return [r for r in rows if isinstance(r, dict)]


async def _head(response: httpx.Response, cap: int = 64 * 1024) -> bytes:
    chunks, total = [], 0
    async for chunk in response.aiter_bytes():
        chunks.append(chunk)
        total += len(chunk)
        if total >= cap:
            break
    return b"".join(chunks)[:cap]


def _bad_request(params: dict[str, Any], body: bytes) -> PublicRequestError:
    """The server's 400 answers: unknown_category / unknown_source (with the valid names), bad_date."""
    try:
        data = json.loads(body)
    except ValueError:
        data = None
    data = data if isinstance(data, dict) else {}
    error, valid = data.get("error"), data.get("valid")
    names = ", ".join(map(str, valid[:60])) if isinstance(valid, list) else ""
    if error == "unknown_category":
        return UnknownCategory(f"'{data.get('category') or params.get('category')}'는 없는 공지 분류입니다."
                               + (f" 쓸 수 있는 분류: {names}" if names else ""))
    if error == "unknown_source":
        return PublicRequestError(f"없는 게시판 이름입니다({params.get('source')})." + (f" 쓸 수 있는 이름: {names}" if names else ""))
    if error == "bad_date":
        return PublicRequestError(f"날짜 형식이 잘못됐습니다. {data.get('expected') or 'YYYY-MM-DD'} 형식으로 주세요.")
    return PublicRequestError("학교 공개 정보 서버가 요청 값을 거절했습니다(HTTP 400).")
