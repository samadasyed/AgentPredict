"""
Live API tests for Polymarket client.

Marked with pytest.mark.api — run with:
    pytest -m api agents/tests/api/test_polymarket_api.py

Requires internet access. No API key needed for public endpoints.
"""

from __future__ import annotations

import pytest

from agents.polymarket.client import PolymarketClient


pytestmark = pytest.mark.api


@pytest.mark.asyncio
async def test_get_markets_returns_non_empty_list():
    """Polymarket has active markets at all times."""
    async with PolymarketClient() as client:
        markets = await client.get_markets(active_only=True)
    assert len(markets) > 0, "Expected at least one active market"


@pytest.mark.asyncio
async def test_market_prices_in_valid_range():
    """All token prices must be in [0, 1]."""
    async with PolymarketClient() as client:
        markets = await client.get_markets(active_only=True)
        # Check the first 5 markets to keep the test fast.
        sample = markets[:5]
        market_ids = [m.condition_id for m in sample]
        snapshots = await client.get_prices(market_ids)

    for snap in snapshots:
        assert 0.0 <= snap.probability <= 1.0, (
            f"Probability out of range for {snap.market_id}/{snap.token_id}: "
            f"{snap.probability}"
        )


@pytest.mark.asyncio
async def test_rate_limit_respected_across_sequential_calls():
    """Multiple sequential calls should not raise 429 errors within normal usage."""
    async with PolymarketClient() as client:
        for _ in range(3):
            markets = await client.get_markets(active_only=True)
            assert isinstance(markets, list)
