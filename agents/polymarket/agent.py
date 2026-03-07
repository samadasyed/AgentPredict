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

# Key: (market_id, token_id) → last snapshot
_PriceCache = Dict[Tuple[str, str], PriceSnapshot]


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
        market_ids = [m.condition_id for m in markets]

        if not market_ids:
            logger.debug("[polymarket-agent] no active markets found")
            return

        snapshots = await self._client.get_prices(market_ids)

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


async def main() -> None:
    import logging
    logging.basicConfig(level=logging.INFO)
    agent = PolymarketAgent()
    try:
        await agent.run()
    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
