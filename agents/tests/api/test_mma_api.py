"""
Live API tests for BallDontLie MMA client.

Marked with pytest.mark.api — run with:
    pytest -m api agents/tests/api/test_mma_api.py

Requires BALLDONTLIE_API_KEY in environment for authenticated endpoints.
Free-tier tests pass without a key.
"""

from __future__ import annotations

import pytest

from agents.mma.client import MMAClient


pytestmark = pytest.mark.api


@pytest.mark.asyncio
async def test_get_live_events_returns_list():
    """Free tier: live events endpoint responds and returns a list (possibly empty)."""
    async with MMAClient() as client:
        events = await client.get_live_events()
    assert isinstance(events, list)


@pytest.mark.asyncio
async def test_get_fight_stats_raises_not_implemented():
    """GOAT-tier method must raise NotImplementedError — never silently do nothing."""
    async with MMAClient() as client:
        with pytest.raises(NotImplementedError, match="GOAT tier"):
            await client.get_fight_stats(fight_id=1)


@pytest.mark.asyncio
async def test_get_round_stats_raises_not_implemented():
    """GOAT-tier method must raise NotImplementedError."""
    async with MMAClient() as client:
        with pytest.raises(NotImplementedError, match="GOAT tier"):
            await client.get_round_stats(fight_id=1, round_num=1)
