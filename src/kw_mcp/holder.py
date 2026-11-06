"""One KLAS session per process, rebuilt when the saved login changes.

Both the local MCP server and the PC agent use this, so fixing a password (`kw-mcp setup`, or the
Claude Desktop extension settings) takes effect on the next request instead of retrying the old
password until KLAS asks for a captcha.
"""

from __future__ import annotations

import asyncio
from typing import Any

from . import credentials
from .klas import KlasClient
from .service import KlasService

# A replaced client may still be serving requests (parallel tools, agent calls): close it only after
# the longest a request can take (20 s timeout, a re-login and the retry), not at once.
RETIRE_AFTER_S = 90.0


class KlasHolder:
    def __init__(self) -> None:
        self._creds: credentials.Credentials | None = None
        self._client: KlasClient | None = None
        self._service: KlasService | None = None
        self._lock = asyncio.Lock()
        self._retired: dict[asyncio.Task[None], KlasClient] = {}

    async def service(self) -> KlasService:
        # Keychain access can block on a macOS permission prompt; keep it off the event loop.
        creds = await asyncio.to_thread(credentials.load)
        async with self._lock:  # parallel first calls share one client (and one login)
            if creds != self._creds or self._service is None:
                self._retire()
                self._client = KlasClient(creds.login_id, creds.password, login_hint=credentials.login_hint(creds))
                self._service = KlasService(self._client)
                self._creds = creds
            return self._service

    def status(self) -> dict[str, Any]:
        """What this process knows without asking KLAS: where the login comes from and the last login."""
        if self._creds is None:
            return {"source": None, "login_id": None, "last_login": None, "requests_last_10_min": 0}
        return {"source": self._creds.source, "login_id": credentials.masked_id(self._creds.login_id),
                "last_login": self._client.last_login if self._client else None,
                "requests_last_10_min": self._client.recent_requests() if self._client else 0}

    def _retire(self) -> None:
        client = self._client
        self._client = self._service = None
        if client is None:
            return
        task = asyncio.create_task(self._close_later(client))
        self._retired[task] = client
        task.add_done_callback(lambda t: self._retired.pop(t, None))

    @staticmethod
    async def _close_later(client: KlasClient) -> None:
        await asyncio.sleep(RETIRE_AFTER_S)
        await client.aclose()

    async def aclose(self) -> None:
        async with self._lock:
            retired = list(self._retired.items())
            self._retired.clear()
            for task, client in retired:
                task.cancel()
                await client.aclose()
            if self._client:
                await self._client.aclose()
            self._client = self._service = None
