"""
MMA polling agent.

Free tier: discovers live events and emits synthetic FIGHT_DISCOVERED events.
GOAT tier: fight stat polling is disabled — logs a clear message.

Owner: Saify
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from agents.mma.client import MMAClient
from agents.mma.models import Event
from agents.shared.event_emitter import EventEmitter
from agents.generated import events_pb2  # type: ignore[import]

logger = logging.getLogger(__name__)

POLL_INTERVAL_S: float = float(os.getenv("MMA_POLL_INTERVAL_S", "30"))
_GOAT_TIER_ENABLED: bool = os.getenv("BALLDONTLIE_GOAT_TIER", "0") == "1"

_GOAT_TIER_NOTE = (
    "BallDontLie GOAT tier is NOT enabled. "
    "Live fight stats (strikes, takedowns) will NOT be streamed. "
    "Set BALLDONTLIE_API_KEY and BALLDONTLIE_GOAT_TIER=1 to enable."
)


def _build_fight_stat_event(
    fight_id: int, fighter_name: str, stat_type: str, value: float, round_num: int,
) -> "events_pb2.CanonicalEvent":
    """Build a CanonicalEvent from a GOAT-tier fight stat."""
    canonical = events_pb2.CanonicalEvent()
    canonical.source = events_pb2.SOURCE_MMA
    f = canonical.fight_event
    f.fight_id = str(fight_id)
    f.fighter_name = fighter_name
    f.stat_type = stat_type
    f.value = value
    f.round = round_num
    f.timestamp = int(time.time() * 1000)
    return canonical


def _build_fight_discovered_event(event: Event, fight_id: int) -> "events_pb2.CanonicalEvent":
    """
    Emits a synthetic FightStatEvent with stat_type='FIGHT_DISCOVERED'.
    This lets downstream components know a live fight is in progress even
    when GOAT-tier stats are unavailable.
    """
    canonical = events_pb2.CanonicalEvent()
    canonical.source = events_pb2.SOURCE_MMA
    f = canonical.fight_event
    f.fight_id = str(fight_id)
    f.fighter_name = "unknown"   # populated when GOAT tier is active
    f.stat_type = "FIGHT_DISCOVERED"
    f.value = 0.0
    f.round = 0
    f.timestamp = int(time.time() * 1000)
    return canonical


class MMAAgent:
    """Polls BallDontLie MMA API and emits events to the engine."""

    def __init__(
        self,
        client: MMAClient | None = None,
        emitter: EventEmitter | None = None,
    ) -> None:
        self._client = client or MMAClient()
        self._emitter = emitter or EventEmitter()
        self._known_fight_ids: set[int] = set()
        self._completed_fight_ids: set[int] = set()
        self._last_stats: dict[tuple[int, str, str], float] = {}  # (fight_id, fighter, stat) → value
        if not _GOAT_TIER_ENABLED:
            logger.warning("[mma-agent] %s", _GOAT_TIER_NOTE)
        else:
            logger.info("[mma-agent] GOAT tier enabled — live fight stats active")

    async def run(self) -> None:
        """Main polling loop. Runs indefinitely."""
        logger.info("[mma-agent] starting — interval=%.1fs", POLL_INTERVAL_S)
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                logger.info("[mma-agent] shutting down")
                break
            except Exception as exc:
                logger.exception("[mma-agent] unexpected error: %s", exc)
            await asyncio.sleep(POLL_INTERVAL_S)

    async def _poll_once(self) -> None:
        events = await self._client.get_live_events()
        if not events:
            logger.debug("[mma-agent] no live events found")
            return

        for ufc_event in events:
            for fight in ufc_event.fights:
                if fight.id not in self._known_fight_ids:
                    self._known_fight_ids.add(fight.id)
                    ev = _build_fight_discovered_event(ufc_event, fight.id)
                    self._emitter.emit(ev)
                    logger.info(
                        "[mma-agent] new fight discovered: fight_id=%d event=%s",
                        fight.id, ufc_event.name,
                    )

        # GOAT-tier stats polling
        if _GOAT_TIER_ENABLED:
            await self._poll_fight_stats(events)

    async def _poll_fight_stats(self, events: list[Event]) -> None:
        """Poll per-fighter stats for in-progress fights (GOAT tier only)."""
        for ufc_event in events:
            for fight in ufc_event.fights:
                if fight.id in self._completed_fight_ids:
                    continue

                if fight.status == "completed":
                    self._completed_fight_ids.add(fight.id)
                    logger.info("[mma-agent] fight %d completed — stopping stat polling", fight.id)
                    continue

                if fight.status != "in_progress":
                    continue

                try:
                    stats = await self._client.get_fight_stats(fight.id)
                except NotImplementedError:
                    # Stubs still in place — GOAT tier not actually active
                    logger.debug("[mma-agent] get_fight_stats not implemented yet")
                    return

                for stat in stats:
                    for stat_type in ("significant_strikes", "takedowns", "knockdowns"):
                        value = getattr(stat, stat_type, 0)
                        key = (fight.id, stat.fighter_name, stat_type)
                        prev = self._last_stats.get(key, 0)
                        if value != prev:
                            ev = _build_fight_stat_event(
                                fight.id, stat.fighter_name, stat_type, float(value), fight.round or 0,
                            )
                            self._emitter.emit(ev)
                            self._last_stats[key] = value
                            logger.info(
                                "[mma-agent] stat change: fight=%d %s %s=%s (was %s)",
                                fight.id, stat.fighter_name, stat_type, value, prev,
                            )

    async def close(self) -> None:
        await self._client.close()
        self._emitter.close()


async def main() -> None:
    import logging
    logging.basicConfig(level=logging.INFO)
    agent = MMAAgent()
    try:
        await agent.run()
    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
