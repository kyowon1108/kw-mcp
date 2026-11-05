"""Client for the kw-campus public JSON API (notices, cafeteria menu, academic calendar).

Configured by KW_CAMPUS_INVITE (the kwc_... invite code; the Claude Desktop extension passes
it), KW_CAMPUS_API_URL (e.g. https://<api>.execute-api.ap-northeast-2.amazonaws.com/c/<token>),
or the first line of ~/.config/kw-campus/api-url. Without any, the combined tools still
work and just leave the public parts empty. Nothing personal is sent: requests carry only
the access token in the path and generic filters (category, date range).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

CONFIG_FILE = Path.home() / ".config" / "kw-campus" / "api-url"


def _from_invite(invite: str) -> str | None:
    from .agent import parse_invite

    try:
        server, token = parse_invite(invite)
    except ValueError:
        return None
    return f"{server}/c/{token}"


def base_url() -> str | None:
    invite = os.environ.get("KW_CAMPUS_INVITE", "").strip()
    url = (_from_invite(invite) if invite else None) or os.environ.get("KW_CAMPUS_API_URL")
    if not url and CONFIG_FILE.exists():
        lines = CONFIG_FILE.read_text().split()
        url = lines[0] if lines else None
    return url.rstrip("/") if url else None


class PublicApi:
    def __init__(self, url: str | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._url = url if url is not None else base_url()
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(10.0), transport=transport)

    @property
    def configured(self) -> bool:
        return bool(self._url)

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        if not self._url:
            return None
        try:
            response = await self._http.get(f"{self._url}{path}", params={k: v for k, v in params.items() if v is not None})
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            return None  # public data is a bonus; personal tools must keep working without it

    async def notices(self, category: str | None = None, limit: int = 10, query: str | None = None,
                      since: str | None = None, pinned: bool = True) -> list[dict[str, Any]]:
        data = await self._get("/api/notices", {"category": category, "limit": limit, "q": query,
                                                "since": since, "pinned": "true" if pinned else "false"})
        return (data or {}).get("notices", [])

    async def menu(self, day: str | None = None) -> dict[str, Any] | None:
        return await self._get("/api/menu", {"date": day})

    async def calendar(self, start: str | None = None, end: str | None = None) -> list[dict[str, Any]]:
        data = await self._get("/api/calendar", {"from": start, "to": end})
        return (data or {}).get("events", [])

    async def aclose(self) -> None:
        await self._http.aclose()
