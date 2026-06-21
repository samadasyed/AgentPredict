"""
Live API tests for the BallDontLie MMA client.

Marked with pytest.mark.api — run with:
    pytest -m api agents/tests/api/test_mma_api.py

Requires BALLDONTLIE_API_KEY in the environment. Endpoints not included in your
plan return [] (the client maps 401/403 to an empty list), so every test asserts
the shape rather than non-emptiness.
"""

from __future__ import annotations

import pytest

from agents.mma.client import MMAClient
from agents.mma.models import Event, Fight, FightStat, Fighter


pytestmark = pytest.mark.api


@pytest.mark.asyncio
async def test_get_events_returns_list():
    async with MMAClient() as client:
        events = await client.get_events(year=2024)
    assert isinstance(events, list)
    assert all(isinstance(e, Event) for e in events)


@pytest.mark.asyncio
async def test_get_live_events_returns_list():
    async with MMAClient() as client:
        events = await client.get_live_events()
    assert isinstance(events, list)


@pytest.mark.asyncio
async def test_get_fighters_returns_list():
    async with MMAClient() as client:
        fighters = await client.get_fighters(search="Jones")
    assert isinstance(fighters, list)
    assert all(isinstance(f, Fighter) for f in fighters)


@pytest.mark.asyncio
async def test_get_fights_returns_list():
    """/fights is a real endpoint (no NotImplementedError); returns a list."""
    async with MMAClient() as client:
        fights = await client.get_fights(fighter_ids=[1])
    assert isinstance(fights, list)
    assert all(isinstance(f, Fight) for f in fights)


@pytest.mark.asyncio
async def test_get_fight_stats_returns_list():
    """/fight_stats is a real endpoint; returns a list (empty if plan-gated)."""
    async with MMAClient() as client:
        stats = await client.get_fight_stats(fight_id=1)
    assert isinstance(stats, list)
    assert all(isinstance(s, FightStat) for s in stats)
