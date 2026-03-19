"""
Async Polymarket HTTP client.

- Caches market IDs; refreshes every MARKET_CACHE_TTL_S seconds.
- Respects 429 Retry-After headers.
- Saves raw JSON responses to /tmp/polymarket_debug/ when DEBUG_DUMP=1.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import asyncio

import aiohttp

from agents.polymarket.models import Market, MarketsPage, PriceSnapshot
from agents.shared.retry import retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://clob.polymarket.com"
MARKET_CACHE_TTL_S: int = 300  # 5 minutes
_DEBUG_DUMP = os.getenv("DEBUG_DUMP", "0") == "1"
_DEBUG_DIR = Path("/tmp/polymarket_debug")


class PolymarketClient:
    """Thin async wrapper around the Polymarket CLOB API."""

    def __init__(self, base_url: str = _BASE_URL) -> None:
        self._base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None
        self._market_cache: list[Market] = []
        self._cache_loaded_at: float = 0.0

    async def _session_(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            )
        return self._session

    @retry(max_attempts=4, base_delay=1.0, retryable=(aiohttp.ClientError, TimeoutError))
    async def _get(self, path: str, params: dict | None = None) -> Any:
        session = await self._session_()
        url = f"{self._base_url}{path}"
        async with session.get(url, params=params) as resp:
            if resp.status == 429:
                retry_after = int(resp.headers.get("Retry-After", "5"))
                logger.warning("[polymarket] rate limited — backing off %ds", retry_after)
                await asyncio.sleep(retry_after)
                raise aiohttp.ClientError("rate limited")
            resp.raise_for_status()
            data = await resp.json()
            if _DEBUG_DUMP:
                _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                dump_path = _DEBUG_DIR / f"{path.replace('/', '_')}_{int(time.time())}.json"
                dump_path.write_text(json.dumps(data, indent=2))
            return data

    async def get_markets(self, active_only: bool = True) -> list[Market]:
        """
        Fetch all markets (paginates automatically).
        Results are cached for MARKET_CACHE_TTL_S seconds.
        """
        now = time.monotonic()
        if self._market_cache and (now - self._cache_loaded_at) < MARKET_CACHE_TTL_S:
            return self._market_cache

        markets: list[Market] = []
        next_cursor: str | None = None

        while True:
            params: dict = {}
            if next_cursor:
                params["next_cursor"] = next_cursor
            if active_only:
                params["active"] = "true"

            raw = await self._get("/markets", params=params)
            page = MarketsPage(**raw)
            markets.extend(page.data)

            if not page.next_cursor:
                break
            next_cursor = page.next_cursor

        self._market_cache = markets
        self._cache_loaded_at = now
        logger.info("[polymarket] fetched %d markets (cache refreshed)", len(markets))
        return markets

    async def get_prices(self, market_ids: list[str]) -> list[PriceSnapshot]:
        """
        Fetch current token prices for the given market condition_ids.
        Returns a flat list of PriceSnapshots (one per token per market).

        NOTE: No batch prices endpoint exists on Polymarket CLOB API (verified 2026-03-19).
              /price and /midpoint require active orderbooks. N+1 via GET /markets/{id} is correct.
              Future: evaluate websocket feed for lower latency.
        """
        snapshots: list[PriceSnapshot] = []
        now_ms = int(time.time() * 1000)

        for market_id in market_ids:
            raw = await self._get(f"/markets/{market_id}")
            market = Market(**raw)
            for token in market.tokens:
                snapshots.append(PriceSnapshot(
                    market_id=market_id,
                    token_id=token.token_id,
                    outcome=token.outcome,
                    probability=token.price,
                    timestamp_ms=now_ms,
                ))

        return snapshots

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self) -> "PolymarketClient":
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()
