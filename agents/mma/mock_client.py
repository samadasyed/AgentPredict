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
# (fight_id, fighter1, fighter2, status). Only the live fight ("in_progress")
# emits stats; the others are "scheduled" — they appear as upcoming fights but
# produce no live play-by-play yet. Names match the Polymarket mock card so the
# dashboard can fuse market odds with live fight stats.
_SEED_FIGHTS = [
    (5001, "Jon Jones", "Tom Aspinall", "in_progress"),
    (5002, "Islam Makhachev", "Arman Tsarukyan", "scheduled"),
    (5003, "Alex Pereira", "Magomed Ankalaev", "scheduled"),
    (5004, "Sean O'Malley", "Merab Dvalishvili", "scheduled"),
    (5005, "Ilia Topuria", "Max Holloway", "scheduled"),
]
_LIVE_FIGHT_ID = 5001
_LIVE_STATUSES = {"in_progress", "live"}


def _fighter(fid: int, name: str) -> Fighter:
    return Fighter(id=fid, name=name)


class MockMMAClient:
    """Synthetic BallDontLie source for offline/demo runs."""

    def __init__(self) -> None:
        # Per (fight_id, fighter) running totals, advanced on each stats poll.
        self._strikes: dict[tuple[int, str], int] = {}
        self._takedowns: dict[tuple[int, str], int] = {}
        self._knockdowns: dict[tuple[int, str], int] = {}
        self._control: dict[tuple[int, str], int] = {}
        self._polls = 0
        self._status: dict[int, str] = {fid: status for fid, _a, _b, status in _SEED_FIGHTS}

    async def get_events(self, year: int | None = None, date: str | None = None) -> list[Event]:
        # Upcoming-card discovery is driven by the Polymarket mock in MOCK_MODE
        # (markets carry the schedule), so the MMA mock returns no scheduled events.
        return []

    async def get_live_events(self) -> list[Event]:
        return [Event(id=_EVENT_ID, name="UFC 999: Jones vs. Aspinall", status="in_progress")]

    async def get_fights(self, event_ids=None, fighter_ids=None, fight_ids=None) -> list[Fight]:
        return [
            Fight(
                id=fid,
                status=status,
                scheduled_rounds=5 if fid == _LIVE_FIGHT_ID else 3,
                fighter1=_fighter(fid * 10, a),
                fighter2=_fighter(fid * 10 + 1, b),
            )
            for fid, a, b, status in _SEED_FIGHTS
        ]

    async def get_fight_stats(self, fight_id: int) -> list[FightStat]:
        """Evolving aggregate stats — only for the live (in_progress) fight.

        Fighter 1 is the busier grappler (more takedowns + control time); both
        trade significant strikes, with the occasional knockdown to keep the
        play-by-play lively."""
        if self._status.get(fight_id) not in _LIVE_STATUSES:
            return []  # scheduled/finished fights have no live stats
        names = next(((a, b) for fid, a, b, _s in _SEED_FIGHTS if fid == fight_id), None)
        if names is None:
            return []

        self._polls += 1
        out: list[FightStat] = []
        for idx, name in enumerate(names):
            key = (fight_id, name)
            self._strikes[key] = self._strikes.get(key, 0) + (6 if idx == 0 else 5)
            self._takedowns[key] = self._takedowns.get(key, 0) + (1 if idx == 0 and self._polls % 2 == 0 else 0)
            self._control[key] = self._control.get(key, 0) + (14 if idx == 0 else 6)
            # A knockdown for the aggressor every so often.
            if idx == 0 and self._polls % 7 == 0:
                self._knockdowns[key] = self._knockdowns.get(key, 0) + 1
            out.append(
                FightStat(
                    fight_id=fight_id,
                    fighter=_fighter(fight_id * 10 + idx, name),
                    significant_strikes_landed=self._strikes[key],
                    takedowns_landed=self._takedowns[key],
                    knockdowns=self._knockdowns.get(key, 0),
                    control_time_seconds=self._control[key],
                )
            )
        return out

    async def close(self) -> None:
        return None
