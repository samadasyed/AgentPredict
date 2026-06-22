"""
Async Polymarket client (Gamma API — https://gamma-api.polymarket.com).

The CLOB `/markets` feed is a firehose dominated by old/closed markets and needs
an N+1 price fetch. The Gamma API returns currently-live markets (active, not
closed) ordered by 24h volume, WITH prices inline — so one request per poll gives
fresh, moving data. A browser User-Agent is required (the edge 403s default UAs).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

from agents.polymarket.models import Market, PriceSnapshot, TokenPrice
from agents.shared.retry import retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://gamma-api.polymarket.com"
# CLOB serves per-token price history (the Gamma list has only the current price).
_CLOB_URL = "https://clob.polymarket.com"
_USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_LIMIT = int(os.getenv("POLYMARKET_LIMIT", "80"))   # how many top-volume live markets to pull
# Window of price history to request for the pre-event odds-trend chart.
_HISTORY_INTERVAL = os.getenv("POLYMARKET_HISTORY_INTERVAL", "1w")
MARKET_CACHE_TTL_S: int = 300  # 5 minutes
_DEBUG_DUMP = os.getenv("DEBUG_DUMP", "0") == "1"
_DEBUG_DIR = Path("/tmp/polymarket_debug")


def _iso_to_ms(value: Any) -> int:
    """Parse an ISO-8601 timestamp (e.g. '2026-06-25T22:00:00Z') to unix millis.
    Returns 0 on anything unparseable."""
    if not value or not isinstance(value, str):
        return 0
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except (TypeError, ValueError):
        return 0

# Gamma returns currently-tradeable markets ordered by 24h volume.
_LIST_PARAMS = {
    "active": "true",
    "closed": "false",
    "order": "volume24hr",
    "ascending": "false",
    "limit": str(_LIMIT),
}


def _parse_market(obj: dict) -> Market | None:
    """Build a Market from a Gamma market object (outcomes/prices are JSON strings)."""
    try:
        outcomes = json.loads(obj.get("outcomes") or "[]")
        prices = json.loads(obj.get("outcomePrices") or "[]")
        token_ids = json.loads(obj.get("clobTokenIds") or "[]")
    except (TypeError, ValueError):
        return None
    if not outcomes or len(prices) != len(outcomes):
        return None

    cid = obj.get("conditionId") or obj.get("condition_id") or obj.get("id")
    if not cid:
        return None

    tokens: list[TokenPrice] = []
    for i, name in enumerate(outcomes):
        try:
            price = float(prices[i])
        except (TypeError, ValueError):
            continue
        tid = str(token_ids[i]) if i < len(token_ids) else f"{cid}-{i}"
        tokens.append(TokenPrice(token_id=tid, outcome=str(name), price=min(1.0, max(0.0, price))))
    if not tokens:
        return None

    closed = bool(obj.get("closed", False))

    # Scheduled start of the underlying event. Gamma uses several field names
    # depending on the market type; take the first that parses.
    event_start_ms = 0
    for key in ("gameStartTime", "startDate", "startTime", "eventStartTime"):
        event_start_ms = _iso_to_ms(obj.get(key))
        if event_start_ms:
            break

    # Lifecycle phase: closed → final; started but open → live; else upcoming.
    if closed:
        phase = "final"
    elif event_start_ms and event_start_ms <= int(time.time() * 1000):
        phase = "live"
    elif event_start_ms:
        phase = "upcoming"
    else:
        phase = ""  # unknown (no schedule on this market)

    return Market(
        condition_id=str(cid),
        question=obj.get("question", ""),
        tokens=tokens,
        active=bool(obj.get("active", True)),
        closed=closed,
        accepting_orders=not closed,
        event_start_ms=event_start_ms,
        phase=phase,
    )


class PolymarketClient:
    """Async wrapper around the Polymarket Gamma API."""

    def __init__(self, base_url: str = _BASE_URL) -> None:
        self._base_url = base_url.rstrip("/")
        self._session: aiohttp.ClientSession | None = None
        self._market_cache: list[Market] = []
        self._cache_loaded_at: float = 0.0
        # condition_id → recent (timestamp_ms, probability) trajectory, cached so
        # we hit the CLOB history endpoint at most once per market per TTL.
        self._history_cache: dict[str, list[tuple[int, float]]] = {}
        self._history_loaded_at: float = 0.0

    async def _session_(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Accept": "application/json", "User-Agent": _USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=10),
            )
        return self._session

    @retry(max_attempts=4, base_delay=1.0, retryable=(aiohttp.ClientError, TimeoutError))
    async def _get(self, path: str, params: dict | None = None) -> Any:
        session = await self._session_()
        async with session.get(f"{self._base_url}{path}", params=params) as resp:
            if resp.status == 429:
                retry_after = int(resp.headers.get("Retry-After", "5"))
                logger.warning("[polymarket] rate limited — backing off %ds", retry_after)
                await asyncio.sleep(retry_after)
                raise aiohttp.ClientError("rate limited")
            resp.raise_for_status()
            data = await resp.json()
            if _DEBUG_DUMP:
                _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                (_DEBUG_DIR / f"{path.strip('/').replace('/', '_')}_{int(time.time())}.json").write_text(
                    json.dumps(data, indent=2)[:200_000])
            return data

    async def _fetch_live(self) -> list[Market]:
        raw = await self._get("/markets", params=_LIST_PARAMS)
        items = raw if isinstance(raw, list) else raw.get("data", [])
        return [m for m in (_parse_market(o) for o in items) if m]

    async def _fetch_history(self, token_id: str) -> list[tuple[int, float]]:
        """Recent price history for one CLOB token, oldest first. Best-effort —
        returns [] on any failure so a missing history never breaks the poll."""
        try:
            session = await self._session_()
            params = {"market": token_id, "interval": _HISTORY_INTERVAL}
            async with session.get(f"{_CLOB_URL}/prices-history", params=params) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            logger.debug("[polymarket] history fetch failed for %s: %s", token_id, exc)
            return []
        rows = data.get("history", []) if isinstance(data, dict) else []
        out: list[tuple[int, float]] = []
        for row in rows:
            t, p = row.get("t"), row.get("p")
            if t is None or p is None:
                continue
            try:
                out.append((int(t) * 1000, min(1.0, max(0.0, float(p)))))  # CLOB `t` is epoch seconds
            except (TypeError, ValueError):
                continue
        return out

    async def get_markets(self, active_only: bool = True, max_pages: int | None = None) -> list[Market]:
        """Currently-live markets (top by 24h volume), cached for MARKET_CACHE_TTL_S."""
        now = time.monotonic()
        if self._market_cache and (now - self._cache_loaded_at) < MARKET_CACHE_TTL_S:
            return self._market_cache
        markets = await self._fetch_live()
        self._market_cache = markets
        self._cache_loaded_at = now
        logger.info("[polymarket] fetched %d live markets (cache refreshed)", len(markets))
        return markets

    async def get_prices(self, market_ids: list[str]) -> list[PriceSnapshot]:
        """Fresh prices for the given condition_ids (re-pulls the live list).
        The primary outcome of each market also carries its scheduled start,
        phase, and recent price history for the pre-event odds-trend chart."""
        wanted = set(market_ids)
        now_ms = int(time.time() * 1000)

        if time.monotonic() - self._history_loaded_at >= MARKET_CACHE_TTL_S:
            self._history_cache.clear()  # expire stale histories

        snapshots: list[PriceSnapshot] = []
        for m in await self._fetch_live():
            if m.condition_id not in wanted:
                continue
            for i, token in enumerate(m.tokens):
                # Fetch history once per market per TTL, for the primary outcome only.
                history: list[tuple[int, float]] = []
                if i == 0:
                    if m.condition_id not in self._history_cache:
                        self._history_cache[m.condition_id] = await self._fetch_history(token.token_id)
                        self._history_loaded_at = time.monotonic()
                    history = self._history_cache[m.condition_id]
                snapshots.append(PriceSnapshot(
                    market_id=m.condition_id,
                    token_id=token.token_id,
                    outcome=token.outcome,
                    probability=token.price,
                    timestamp_ms=now_ms,
                    history=history,
                    event_start_ms=m.event_start_ms,
                    phase=m.phase,
                ))
        return snapshots

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self) -> "PolymarketClient":
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()
