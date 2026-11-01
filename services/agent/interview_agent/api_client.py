"""Client for the session API's /internal endpoints. Every call is idempotent on the
server, so transient failures are retried."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

log = logging.getLogger("interview_agent.api")


class InternalApi:
    def __init__(
        self, base_url: str, token: str, session_id: str, client: httpx.AsyncClient | None = None
    ):
        self.session_id = session_id
        self._c = client or httpx.AsyncClient(
            base_url=base_url, headers={"authorization": f"Bearer {token}"}, timeout=8.0
        )

    async def aclose(self) -> None:
        await self._c.aclose()

    async def _req(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        retries: int = 3,
        ok_statuses: tuple[int, ...] = (),
    ) -> dict:
        url = f"/internal/sessions/{self.session_id}{path}"
        delay = 0.3
        for attempt in range(retries + 1):
            try:
                r = await self._c.request(method, url, json=json)
                if r.status_code < 400 or r.status_code in ok_statuses:
                    return r.json() if r.content else {}
                if r.status_code < 500:
                    raise ApiError(r.status_code, r.text)
            except (httpx.TransportError, httpx.TimeoutException) as e:
                log.warning("internal api %s %s failed: %r", method, path, e)
            if attempt < retries:
                await asyncio.sleep(delay)
                delay *= 2
        raise ApiError(503, f"{method} {path} failed after retries")

    async def config(self) -> dict:
        return await self._req("GET", "/config", retries=2)

    async def event(self, kind: str, payload: dict | None = None) -> dict:
        return await self._req("POST", "/events", json={"kind": kind, "payload": payload or {}})

    async def turns(self, turns: list[dict]) -> dict:
        return await self._req("POST", "/turns", json={"turns": turns})

    async def usage(self, events: list[dict]) -> dict:
        return await self._req("POST", "/usage", json={"events": events})

    async def finalize(self, reason: str) -> dict:
        return await self._req("POST", "/finalize", json={"reason": reason[:60]})

    async def transcript_complete(self) -> dict:
        return await self._req("POST", "/transcript-complete", ok_statuses=(409,))


class ApiError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"{status}: {body[:200]}")
        self.status = status
