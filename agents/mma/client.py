"""
BallDontLie MMA API client — https://api.balldontlie.io (spec: /openapi/mma.yml).

Auth is an API key passed RAW in the `Authorization` header (NOT `Bearer <key>`).
List endpoints return {"data": [...], "meta": {"next_cursor", "per_page"}}.
Endpoints are not stubbed by "tier": if your plan/key can't access one, the API
returns 401/403 and we degrade to an empty list rather than crashing.

Owner: Saify
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

import aiohttp

from agents.mma.models import Event, Fight, Fighter, FightStat
from agents.shared.retry import retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.balldontlie.io/mma/v1"
_API_KEY = os.getenv("BALLDONTLIE_API_KEY", "")
_PER_PAGE = 100
# Browser UA — some API edges reject the default aiohttp User-Agent.
_USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


class MMAClient:
    """Async client for the BallDontLie MMA API."""

    def __init__(self, base_url: str = _BASE_URL, api_key: str = _API_KEY) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._session: aiohttp.ClientSession | None = None

    async def _session_(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {"Accept": "application/json", "User-Agent": _USER_AGENT}
            if self._api_key:
                # BallDontLie expects the raw key, NOT an OAuth "Bearer <key>".
                headers["Authorization"] = self._api_key
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            )
        return self._session

    # Retry only transient network failures — never HTTP 4xx (those are surfaced
    # so _get_list can map 401/403 to a graceful empty result).
    @retry(max_attempts=3, base_delay=1.0,
           retryable=(aiohttp.ClientConnectionError, asyncio.TimeoutError, TimeoutError))
    async def _get(self, path: str, params: dict | None = None) -> Any:
        session = await self._session_()
        async with session.get(f"{self._base_url}{path}", params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _get_list(self, path: str, model: type, label: str,
                        params: dict | None = None) -> list:
        """GET a list endpoint; parse `data`; map auth/plan errors to []."""
        p = {"per_page": _PER_PAGE, **(params or {})}
        try:
            raw = await self._get(path, p)
        except aiohttp.ClientResponseError as exc:
            if exc.status in (401, 403, 429):
                logger.warning("[mma-client] %s -> HTTP %d (%s); check BALLDONTLIE_API_KEY/plan — returning []",
                               path, exc.status, exc.message)
                return []
            raise
        items = []
        for item in raw.get("data", []):
            try:
                items.append(model(**item))
            except Exception as exc:  # one malformed row shouldn't drop the batch
                logger.warning("[mma-client] failed to parse %s: %s", label, exc)
        return items

    # ─── Events ────────────────────────────────────────────────────────────────

    async def get_events(self, year: int | None = None, date: str | None = None) -> list[Event]:
        """List events, optionally filtered by `year` or `date` (YYYY-MM-DD)."""
        params: dict[str, Any] = {}
        if year:
            params["year"] = year
        if date:
            params["date"] = date
        return await self._get_list("/events", Event, "event", params or None)

    async def get_live_events(self) -> list[Event]:
        """Events happening today (the API has no server-side status filter)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return await self.get_events(date=today)

    # ─── Fighters ────────────────────────────────────────────────────────────────

    async def get_fighters(self, search: str | None = None,
                           fighter_ids: list[int] | None = None) -> list[Fighter]:
        params: dict[str, Any] = {}
        if search:
            params["search"] = search
        if fighter_ids:
            params["fighter_ids[]"] = fighter_ids
        return await self._get_list("/fighters", Fighter, "fighter", params or None)

    async def get_fighter(self, fighter_id: int) -> Fighter | None:
        try:
            raw = await self._get(f"/fighters/{fighter_id}")
        except aiohttp.ClientResponseError as exc:
            logger.warning("[mma-client] fighter %d -> HTTP %d", fighter_id, exc.status)
            return None
        data = raw.get("data", raw)
        return Fighter(**data)

    # ─── Fights ──────────────────────────────────────────────────────────────────

    async def get_fights(self, event_ids: list[int] | None = None,
                         fighter_ids: list[int] | None = None,
                         fight_ids: list[int] | None = None) -> list[Fight]:
        """List fights, filterable by event/fighter/fight ids."""
        params: dict[str, Any] = {}
        if event_ids:
            params["event_ids[]"] = event_ids
        if fighter_ids:
            params["fighter_ids[]"] = fighter_ids
        if fight_ids:
            params["fight_ids[]"] = fight_ids
        return await self._get_list("/fights", Fight, "fight", params or None)

    # ─── Fight stats ─────────────────────────────────────────────────────────────

    async def get_fight_stats(self, fight_id: int) -> list[FightStat]:
        """Per-fighter aggregate stats for one fight. Empty list if plan-gated."""
        return await self._get_list("/fight_stats", FightStat, "fight_stat",
                                    {"fight_ids[]": [fight_id]})

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self) -> "MMAClient":
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()
