"""Unit tests for the offline mock agent clients (MOCK_MODE data sources)."""

from __future__ import annotations

import asyncio

import pytest

from agents.polymarket.mock_client import MockPolymarketClient
from agents.mma.mock_client import MockMMAClient


# ─── MockPolymarketClient ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_polymarket_mock_returns_markets_with_tokens():
    c = MockPolymarketClient(seed=7)
    markets = await c.get_markets()
    assert len(markets) >= 3
    for m in markets:
        assert m.condition_id
        assert m.tokens and 0.0 <= m.tokens[0].price <= 1.0


@pytest.mark.asyncio
async def test_polymarket_mock_prices_move_within_bounds():
    c = MockPolymarketClient(seed=7)
    ids = [m.condition_id for m in await c.get_markets()]
    first = {s.market_id: s.probability for s in await c.get_prices(ids)}
    moved = False
    for _ in range(10):
        for s in await c.get_prices(ids):
            assert 0.0 <= s.probability <= 1.0
            if abs(s.probability - first[s.market_id]) > 1e-9:
                moved = True
    assert moved, "probabilities should random-walk across polls"


@pytest.mark.asyncio
async def test_polymarket_mock_only_returns_requested_ids():
    c = MockPolymarketClient(seed=1)
    ids = [m.condition_id for m in await c.get_markets()]
    subset = ids[:1]
    snaps = await c.get_prices(subset)
    assert {s.market_id for s in snaps} == set(subset)


@pytest.mark.asyncio
async def test_polymarket_mock_is_deterministic_with_seed():
    a = MockPolymarketClient(seed=42)
    b = MockPolymarketClient(seed=42)
    ids = [m.condition_id for m in await a.get_markets()]
    await b.get_markets()
    pa = [s.probability for s in await a.get_prices(ids)]
    pb = [s.probability for s in await b.get_prices(ids)]
    assert pa == pb


# ─── MockMMAClient ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mma_mock_returns_in_progress_fights():
    c = MockMMAClient()
    events = await c.get_live_events()
    assert events and events[0].fights
    for f in events[0].fights:
        assert f.status == "in_progress"


@pytest.mark.asyncio
async def test_mma_mock_stats_increase_each_poll():
    c = MockMMAClient()
    fid = (await c.get_live_events())[0].fights[0].id
    s1 = await c.get_fight_stats(fid)
    s2 = await c.get_fight_stats(fid)
    assert s1 and s2
    assert s1[0].fighter_name  # non-empty (engine requires it)
    assert s2[0].significant_strikes > s1[0].significant_strikes


@pytest.mark.asyncio
async def test_mma_mock_unknown_fight_returns_empty():
    c = MockMMAClient()
    assert await c.get_fight_stats(999999) == []
