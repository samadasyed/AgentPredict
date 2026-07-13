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
from agents.shared.flight_recorder import FlightRecorder
from agents.generated import events_pb2  # type: ignore[import]

logger = logging.getLogger(__name__)

POLL_INTERVAL_S: float = float(os.getenv("POLYMARKET_POLL_INTERVAL_S", "5"))
DELTA_THRESHOLD: float = float(os.getenv("POLYMARKET_DELTA_THRESHOLD", "0.01"))
# Prefer markets whose question contains this keyword (e.g. "UFC"); empty = no filter.
QUERY: str = os.getenv("POLYMARKET_QUERY", "UFC").strip()
# When the query matches nothing, fall back to ALL live markets (off-theme). Off by
# default so a UFC-focused view stays clean instead of showing e.g. World Cup futures.
FALLBACK_ALL: bool = os.getenv("POLYMARKET_FALLBACK_ALL", "0") == "1"
# Cap how many markets we price each poll (get_prices is one request per market).
MAX_MARKETS: int = int(os.getenv("POLYMARKET_MAX_MARKETS", "30"))
# Re-emit a baseline snapshot (delta 0) for EVERY tracked market this often.
# Late-joining clients (fresh browser tabs, restarted gateways) only see what's
# in the replay buffer — without re-baselining, a market that hasn't moved since
# agent startup is invisible to them. RAG ignores delta-0 events, so this is
# display-plane only.
REBASELINE_S: float = float(os.getenv("POLYMARKET_REBASELINE_S", "120"))

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
    m.event_start = snapshot.event_start_ms
    m.phase = snapshot.phase
    m.title = snapshot.title
    m.card_title = snapshot.card_title
    m.fight_info = snapshot.fight_info
    m.volume = snapshot.volume
    m.event_slug = snapshot.event_slug
    # Ship the recent trajectory as a snapshot (see PriceSnapshot.history).
    for ts, prob in snapshot.history:
        point = m.history.add()
        point.timestamp = ts
        point.probability = prob
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
        # market_id → monotonic time of the last baseline emitted for it.
        self._baseline_at: Dict[str, float] = {}
        # Research capture (RESEARCH_CAPTURE=1): every snapshot each poll —
        # including sub-threshold ticks the emit gate below discards.
        self._recorder = FlightRecorder("polymarket_agent")
        # Markets whose week-long history has already been captured once
        # (it barely changes poll-to-poll; re-recording it would be pure bloat).
        self._history_captured: set[str] = set()

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

        # Prefer on-theme markets (e.g. "UFC"). Only fall back to off-theme markets
        # when explicitly enabled — a UFC view should stay clean (and upcoming fights
        # are surfaced from BallDontLie even when no UFC market is trading yet).
        selected = [m for m in live if QUERY.lower() in m.question.lower()] if QUERY else live
        if not selected and FALLBACK_ALL:
            selected = live
        selected = selected[:MAX_MARKETS]

        if not selected:
            logger.info("[polymarket-agent] no on-theme (%s) markets trading right now", QUERY or "*")
            return

        snapshots = await self._client.get_prices([m.condition_id for m in selected])

        now = time.monotonic()
        capture_rows: list[dict] = []
        for snap in snapshots:
            key = (snap.market_id, snap.token_id)
            prev = self._price_cache.get(key)
            delta = (snap.probability - prev.probability) if prev is not None else None
            action = "held"

            if delta is not None and abs(delta) >= DELTA_THRESHOLD:
                # A real move — emit it (also refreshes the market's visibility).
                ev = _build_market_event(snap, delta)
                accepted = self._emitter.emit(ev)
                self._baseline_at[snap.market_id] = now
                action = "emitted"
                logger.debug(
                    "[polymarket-agent] emitted market=%s outcome=%s delta=%.4f accepted=%s",
                    snap.market_id, snap.outcome, delta, accepted,
                )
            elif prev is None or (now - self._baseline_at.get(snap.market_id, 0.0)) >= REBASELINE_S:
                # Baseline snapshot (delta 0): on first sighting AND periodically,
                # so late-joining clients (fresh tabs, restarted gateways) receive
                # the full slate within one REBASELINE_S window even when nothing
                # moves. RAG ignores |delta| < 0.02, so baselines don't trigger it.
                ev = _build_market_event(snap, 0.0)
                self._emitter.emit(ev)
                self._baseline_at[snap.market_id] = now
                action = "baseline"
                logger.debug("[polymarket-agent] baseline snapshot market=%s outcome=%s",
                             snap.market_id, snap.outcome)

            if self._recorder.enabled:
                row = snap.model_dump(exclude={"history"})
                row["delta"] = delta
                row["action"] = action
                if snap.history and snap.market_id not in self._history_captured:
                    row["history"] = snap.history
                    self._history_captured.add(snap.market_id)
                capture_rows.append(row)

            self._price_cache[key] = snap

        if capture_rows:
            self._recorder.record("poll", {"n_selected": len(selected),
                                           "snapshots": capture_rows})

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
