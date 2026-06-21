"""
Offline mock of MMAClient — no network, no API key.

Enabled when MOCK_MODE=1. Exposes a synthetic in-progress UFC card so the agent
emits FIGHT_DISCOVERED events, and (with the demo's BALLDONTLIE_GOAT_TIER=1)
returns monotonically increasing per-fighter stats so live FightStatEvents flow
too. Drop-in for the async interface the agent uses.

Owner: Samad (demo/offline harness)
"""

from __future__ import annotations

from agents.mma.models import Event, Fight, FightStat

_EVENT_ID = 900
# (fight_id, fighter1, fighter2)
_SEED_FIGHTS = [
    (5001, "Jon Jones", "Tom Aspinall"),
    (5002, "Alex Pereira", "Magomed Ankalaev"),
    (5003, "Sean O'Malley", "Merab Dvalishvili"),
]


class MockMMAClient:
    """Synthetic BallDontLie source for offline/demo runs."""

    def __init__(self) -> None:
        # Per (fight_id, fighter) running stat totals, advanced on each stats poll.
        self._strikes: dict[tuple[int, str], int] = {}
        self._takedowns: dict[tuple[int, str], int] = {}

    async def get_live_events(self) -> list[Event]:
        fights = [
            Fight(id=fid, event_id=_EVENT_ID, status="in_progress", round=1)
            for fid, _, _ in _SEED_FIGHTS
        ]
        return [
            Event(
                id=_EVENT_ID,
                name="UFC 999: Mock Main Card",
                status="in_progress",
                fights=fights,
            )
        ]

    async def get_fight_stats(self, fight_id: int) -> list[FightStat]:
        """Return evolving aggregate stats for both fighters in a fight."""
        names = next(((a, b) for fid, a, b in _SEED_FIGHTS if fid == fight_id), None)
        if names is None:
            return []
        out: list[FightStat] = []
        for idx, name in enumerate(names):
            key = (fight_id, name)
            # Advance by a deterministic, fighter-specific increment each poll.
            self._strikes[key] = self._strikes.get(key, 0) + 3 + idx
            self._takedowns[key] = self._takedowns.get(key, 0) + (1 if idx == 0 else 0)
            out.append(
                FightStat(
                    fight_id=fight_id,
                    fighter_id=fight_id * 10 + idx,
                    fighter_name=name,
                    significant_strikes=self._strikes[key],
                    takedowns=self._takedowns[key],
                    knockdowns=0,
                )
            )
        return out

    async def get_round_stats(self, fight_id: int, round_num: int):
        return []

    async def close(self) -> None:
        return None
