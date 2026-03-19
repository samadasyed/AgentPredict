"""
BallDontLie MMA API client.

Free tier: event discovery (get_live_events).
GOAT tier: fight stats and round stats (STUBBED — raises NotImplementedError).

Owner: Saify
"""

from __future__ import annotations

import logging
import os
from typing import Any

import aiohttp

from agents.mma.models import Event, Fight, FightStat, RoundStat
from agents.shared.retry import retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.balldontlie.io/mma/v1"
_API_KEY = os.getenv("BALLDONTLIE_API_KEY", "")


class MMAClient:
    """Async client for BallDontLie MMA API."""

    def __init__(self, base_url: str = _BASE_URL, api_key: str = _API_KEY) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._session: aiohttp.ClientSession | None = None

    async def _session_(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {"Accept": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            )
        return self._session

    @retry(max_attempts=3, base_delay=1.0, retryable=(aiohttp.ClientError, TimeoutError))
    async def _get(self, path: str, params: dict | None = None) -> Any:
        session = await self._session_()
        url = f"{self._base_url}{path}"
        async with session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    # ─── Free tier ────────────────────────────────────────────────────────────

    async def get_live_events(self) -> list[Event]:
        """
        Returns currently live or upcoming events.
        Available on free tier.

        Endpoint path confirmed working on free tier (2026-03-19).
        """
        raw = await self._get("/events", params={"status": "in_progress"})
        events = []
        for item in raw.get("data", []):
            try:
                events.append(Event(**item))
            except Exception as exc:
                logger.warning("[mma-client] failed to parse event: %s — %s", item, exc)
        return events

    # ─── GOAT tier (STUBBED) ──────────────────────────────────────────────────

    async def get_fight_stats(self, fight_id: int) -> list[FightStat]:
        """
        Per-fighter aggregate stats for a fight.
        REQUIRES BallDontLie GOAT tier ($39.99/mo).
        """
        # GOAT tier required — do not remove this stub.
        raise NotImplementedError(
            "BallDontLie GOAT tier required to access fight stats. "
            "Upgrade at https://mma.balldontlie.io and set BALLDONTLIE_API_KEY."
        )

    async def get_round_stats(self, fight_id: int, round_num: int) -> list[RoundStat]:
        """
        Per-round stat breakdown for a fight.
        REQUIRES BallDontLie GOAT tier ($39.99/mo).
        """
        # GOAT tier required — do not remove this stub.
        raise NotImplementedError(
            "BallDontLie GOAT tier required to access round stats. "
            "Upgrade at https://mma.balldontlie.io and set BALLDONTLIE_API_KEY."
        )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self) -> "MMAClient":
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()
