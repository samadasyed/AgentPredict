"""
MMA polling agent.

Discovers today's fights (BallDontLie /events -> /fights) and emits a
FIGHT_DISCOVERED event per new fight. When BALLDONTLIE_GOAT_TIER=1, it also polls
/fight_stats for active fights and emits per-fighter stat changes (significant
strikes, takedowns, knockdowns, control time). If the key's plan can't access
fight stats, the client returns [] and the agent simply emits no stat events.

Owner: Saify
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

from agents.mma.client import MMAClient
from agents.mma.models import Fight
from agents.shared.event_emitter import EventEmitter
from agents.generated import events_pb2  # type: ignore[import]

logger = logging.getLogger(__name__)

POLL_INTERVAL_S: float = float(os.getenv("MMA_POLL_INTERVAL_S", "30"))
_GOAT_TIER_ENABLED: bool = os.getenv("BALLDONTLIE_GOAT_TIER", "0") == "1"

_GOAT_TIER_NOTE = (
    "Fight-stat polling disabled (BALLDONTLIE_GOAT_TIER != 1). "
    "Only FIGHT_DISCOVERED events will be emitted. "
    "Set BALLDONTLIE_GOAT_TIER=1 (with a plan that includes fight stats) to enable."
)

# Status strings that mean "don't poll stats anymore". The API's status is free
# text (no documented enum), so match defensively, case-insensitively.
_FINISHED_STATUSES = {"completed", "final", "finished", "cancelled", "canceled", "no_contest"}

# (emitted stat_type, FightStat attribute) pairs we surface as stat events.
_TRACKED_STATS = [
    ("significant_strikes", "significant_strikes_landed"),
    ("takedowns", "takedowns_landed"),
    ("knockdowns", "knockdowns"),
    ("control_time_seconds", "control_time_seconds"),
]


def _is_finished(status: str | None) -> bool:
    return bool(status) and status.lower() in _FINISHED_STATUSES


def _matchup(fight: Fight) -> str:
    names = [f.full_name for f in (fight.fighter1, fight.fighter2) if f and f.full_name]
    return " vs ".join(names) if names else "unknown"


def _build_fight_stat_event(
    fight_id: int, fighter_name: str, stat_type: str, value: float, round_num: int,
) -> "events_pb2.CanonicalEvent":
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


def _build_fight_discovered_event(fight: Fight) -> "events_pb2.CanonicalEvent":
    """Signal that a fight exists on today's card (downstream cares even without stats)."""
    canonical = events_pb2.CanonicalEvent()
    canonical.source = events_pb2.SOURCE_MMA
    f = canonical.fight_event
    f.fight_id = str(fight.id)
    f.fighter_name = _matchup(fight)
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
        if _GOAT_TIER_ENABLED:
            logger.info("[mma-agent] fight-stat polling enabled")
        else:
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
            logger.debug("[mma-agent] no events today")
            return

        # Events no longer embed fights — fetch them per event.
        fights = await self._client.get_fights(event_ids=[e.id for e in events])
        if not fights:
            logger.debug("[mma-agent] no fights for today's events")
            return

        for fight in fights:
            if fight.id not in self._known_fight_ids:
                self._known_fight_ids.add(fight.id)
                self._emitter.emit(_build_fight_discovered_event(fight))
                logger.info("[mma-agent] new fight discovered: fight_id=%d (%s)",
                            fight.id, _matchup(fight))

        if _GOAT_TIER_ENABLED:
            await self._poll_fight_stats(fights)

    async def _poll_fight_stats(self, fights: list[Fight]) -> None:
        """Poll per-fighter stats for active fights and emit changes."""
        for fight in fights:
            if fight.id in self._completed_fight_ids:
                continue
            if _is_finished(fight.status):
                self._completed_fight_ids.add(fight.id)
                logger.info("[mma-agent] fight %d finished — stopping stat polling", fight.id)
                continue

            stats = await self._client.get_fight_stats(fight.id)
            for stat in stats:
                fighter_name = stat.fighter_name
                if not fighter_name:
                    continue  # engine requires a non-empty fighter_name
                for stat_type, attr in _TRACKED_STATS:
                    value = getattr(stat, attr, 0) or 0
                    key = (fight.id, fighter_name, stat_type)
                    prev = self._last_stats.get(key, 0)
                    if value != prev:
                        self._emitter.emit(_build_fight_stat_event(
                            fight.id, fighter_name, stat_type, float(value), fight.result_round or 0,
                        ))
                        self._last_stats[key] = value
                        logger.info("[mma-agent] stat: fight=%d %s %s=%s (was %s)",
                                    fight.id, fighter_name, stat_type, value, prev)

    async def close(self) -> None:
        await self._client.close()
        self._emitter.close()


def _make_client() -> "MMAClient":
    """Real client, or the offline synthetic source when MOCK_MODE=1 (no API needed)."""
    if os.getenv("MOCK_MODE", "0") == "1":
        from agents.mma.mock_client import MockMMAClient
        logger.info("[mma-agent] MOCK_MODE on — emitting synthetic fights/stats (no API)")
        return MockMMAClient()  # type: ignore[return-value]
    return MMAClient()


async def main() -> None:
    import logging
    logging.basicConfig(level=logging.INFO)
    agent = MMAAgent(client=_make_client())
    try:
        await agent.run()
    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
