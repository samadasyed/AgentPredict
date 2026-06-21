"""
Offline mock of MMAClient — no network, no API key.

Enabled when MOCK_MODE=1. Mirrors the real (spec-accurate) client interface:
get_live_events() returns events (no embedded fights), get_fights() returns the
card, and get_fight_stats() returns monotonically increasing per-fighter stats so
live FightStatEvents flow under the demo's BALLDONTLIE_GOAT_TIER=1.

Owner: Samad (demo/offline harness)
"""

from __future__ import annotations

from agents.mma.models import Event, Fight, Fighter, FightStat

_EVENT_ID = 900
# (fight_id, fighter1 name, fighter2 name)
_SEED_FIGHTS = [
    (5001, "Jon Jones", "Tom Aspinall"),
    (5002, "Alex Pereira", "Magomed Ankalaev"),
    (5003, "Sean O'Malley", "Merab Dvalishvili"),
]


def _fighter(fid: int, name: str) -> Fighter:
    return Fighter(id=fid, name=name)


class MockMMAClient:
    """Synthetic BallDontLie source for offline/demo runs."""

    def __init__(self) -> None:
        # Per (fight_id, fighter) running totals, advanced on each stats poll.
        self._strikes: dict[tuple[int, str], int] = {}
        self._takedowns: dict[tuple[int, str], int] = {}

    async def get_live_events(self) -> list[Event]:
        return [Event(id=_EVENT_ID, name="UFC 999: Mock Main Card", status="in_progress")]

    async def get_fights(self, event_ids=None, fighter_ids=None, fight_ids=None) -> list[Fight]:
        return [
            Fight(
                id=fid,
                status="in_progress",
                scheduled_rounds=3,
                fighter1=_fighter(fid * 10, a),
                fighter2=_fighter(fid * 10 + 1, b),
            )
            for fid, a, b in _SEED_FIGHTS
        ]

    async def get_fight_stats(self, fight_id: int) -> list[FightStat]:
        """Return evolving aggregate stats for both fighters in a fight."""
        names = next(((a, b) for fid, a, b in _SEED_FIGHTS if fid == fight_id), None)
        if names is None:
            return []
        out: list[FightStat] = []
        for idx, name in enumerate(names):
            key = (fight_id, name)
            self._strikes[key] = self._strikes.get(key, 0) + 3 + idx
            self._takedowns[key] = self._takedowns.get(key, 0) + (1 if idx == 0 else 0)
            out.append(
                FightStat(
                    fight_id=fight_id,
                    fighter=_fighter(fight_id * 10 + idx, name),
                    significant_strikes_landed=self._strikes[key],
                    takedowns_landed=self._takedowns[key],
                    knockdowns=0,
                )
            )
        return out

    async def close(self) -> None:
        return None
