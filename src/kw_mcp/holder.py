"""One KLAS session per process, rebuilt when the saved login changes.

Both the local MCP server and the PC agent use this, so fixing a password (`kw-mcp setup`, or the
Claude Desktop extension settings) takes effect on the next request instead of retrying the old
password until KLAS asks for a captcha.
"""

from __future__ import annotations

import asyncio

from . import credentials
from .klas import KlasClient
from .service import KlasService


class KlasHolder:
    def __init__(self) -> None:
        self._creds: credentials.Credentials | None = None
        self._client: KlasClient | None = None
        self._service: KlasService | None = None
        self._lock = asyncio.Lock()

    async def service(self) -> KlasService:
        # Keychain access can block on a macOS permission prompt; keep it off the event loop.
        creds = await asyncio.to_thread(credentials.load)
        async with self._lock:  # parallel first calls share one client (and one login)
            if creds != self._creds or self._service is None:
                await self._close()
                self._client = KlasClient(creds.login_id, creds.password)
                self._service = KlasService(self._client)
                self._creds = creds
            return self._service

    async def _close(self) -> None:
        if self._client:
            await self._client.aclose()
        self._client = self._service = None

    async def aclose(self) -> None:
        async with self._lock:
            await self._close()
