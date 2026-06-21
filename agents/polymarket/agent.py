"""
Polymarket polling agent.

Polls active markets every POLL_INTERVAL_S seconds.
Emits a MarketEvent to the C++ engine whenever a token's probability changes
by more than DELTA_THRESHOLD.

Owner: Saify
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Dict, Tuple

from agents.polymarket.client import PolymarketClient
from agents.polymarket.models import PriceSnapshot
from agents.shared.event_emitter import EventEmitter
from agents.generated import events_pb2  # type: ignore[import]

logger = logging.getLogger(__name__)

POLL_INTERVAL_S: float = float(os.getenv("POLYMARKET_POLL_INTERVAL_S", "5"))
DELTA_THRESHOLD: float = float(os.getenv("POLYMARKET_DELTA_THRESHOLD", "0.01"))
# Prefer markets whose question contains this keyword (e.g. "UFC"); empty = no filter.
QUERY: str = os.getenv("POLYMARKET_QUERY", "UFC").strip()
# Cap how many markets we price each poll (get_prices is one request per market).
MAX_MARKETS: int = int(os.getenv("POLYMARKET_MAX_MARKETS", "30"))

# Key: (market_id, token_id) → last snapshot
_PriceCache = Dict[Tuple[str, str], PriceSnapshot]


def _is_tradeable(market) -> bool:
    """True if the market is currently accepting orders (live) — Polymarket's
    `active=true` feed also includes closed/settled markets, so filter on this."""
    return getattr(market, "accepting_orders", False) and not market.closed


def _build_market_event(snapshot: PriceSnapshot, delta: float) -> "events_pb2.CanonicalEvent":
    ev = events_pb2.CanonicalEvent()
    ev.source = events_pb2.SOURCE_POLYMARKET
    m = ev.market_event
    m.market_id = snapshot.market_id
    m.outcome = snapshot.outcome
    m.probability = snapshot.probability
    m.delta = delta
    m.timestamp = snapshot.timestamp_ms
    return ev


class PolymarketAgent:
    """Polls Polymarket and emits meaningful price changes to the engine."""

    def __init__(
        self,
        client: PolymarketClient | None = None,
        emitter: EventEmitter | None = None,
    ) -> None:
        self._client = client or PolymarketClient()
        self._emitter = emitter or EventEmitter()
        self._price_cache: _PriceCache = {}

    async def run(self) -> None:
        """Main polling loop. Runs indefinitely; cancel via asyncio cancellation."""
        logger.info(
            "[polymarket-agent] starting — interval=%.1fs delta_threshold=%.3f",
            POLL_INTERVAL_S, DELTA_THRESHOLD,
        )
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                logger.info("[polymarket-agent] shutting down")
                break
            except Exception as exc:
                logger.exception("[polymarket-agent] unexpected error: %s", exc)
            await asyncio.sleep(POLL_INTERVAL_S)

    async def _poll_once(self) -> None:
        markets = await self._client.get_markets(active_only=True)
        live = [m for m in markets if _is_tradeable(m)]

        # Prefer on-theme markets (e.g. "UFC"); fall back to any live market so the
        # feed isn't empty when no themed market is currently trading.
        selected = [m for m in live if QUERY.lower() in m.question.lower()] if QUERY else []
        if not selected:
            selected = live
        selected = selected[:MAX_MARKETS]

        if not selected:
            logger.debug("[polymarket-agent] no live markets to track")
            return

        snapshots = await self._client.get_prices([m.condition_id for m in selected])

        for snap in snapshots:
            key = (snap.market_id, snap.token_id)
            prev = self._price_cache.get(key)

            delta = snap.probability - (prev.probability if prev else snap.probability)
            if abs(delta) >= DELTA_THRESHOLD:
                ev = _build_market_event(snap, delta)
                accepted = self._emitter.emit(ev)
                logger.debug(
                    "[polymarket-agent] emitted market=%s outcome=%s delta=%.4f accepted=%s",
                    snap.market_id, snap.outcome, delta, accepted,
                )

            self._price_cache[key] = snap

    async def close(self) -> None:
        await self._client.close()
        self._emitter.close()


def _make_client() -> "PolymarketClient":
    """Real client, or the offline synthetic source when MOCK_MODE=1 (no API needed)."""
    if os.getenv("MOCK_MODE", "0") == "1":
        from agents.polymarket.mock_client import MockPolymarketClient
        logger.info("[polymarket-agent] MOCK_MODE on — emitting synthetic markets (no API)")
        return MockPolymarketClient()  # type: ignore[return-value]
    return PolymarketClient()


async def main() -> None:
    import logging
    logging.basicConfig(level=logging.INFO)
    agent = PolymarketAgent(client=_make_client())
    try:
        await agent.run()
    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
