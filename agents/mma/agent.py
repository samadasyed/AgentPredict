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

_GOAT_TIER_NOTE = (
    "BallDontLie GOAT tier is NOT enabled. "
    "Live fight stats (strikes, takedowns) will NOT be streamed. "
    "Set BALLDONTLIE_API_KEY and upgrade to GOAT tier to enable."
)


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
        logger.warning("[mma-agent] %s", _GOAT_TIER_NOTE)

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

        # GOAT-tier stats polling would go here.
        # Intentionally omitted — see _GOAT_TIER_NOTE above.
        # TODO(Saify): when GOAT tier is active, call client.get_fight_stats()
        #              for each in-progress fight and emit FightStatEvents.

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
