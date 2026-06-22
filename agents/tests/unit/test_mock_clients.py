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
async def test_polymarket_mock_snapshots_carry_history_and_schedule():
    """Pre-event context: each snapshot ships a week of history, a scheduled
    start, and a phase — and exactly one fight on the card is live."""
    c = MockPolymarketClient(seed=7)
    ids = [m.condition_id for m in await c.get_markets()]
    snaps = await c.get_prices(ids)
    assert snaps
    for s in snaps:
        assert len(s.history) >= 2
        assert all(0.0 <= p <= 1.0 for _ts, p in s.history)
        # history is chronological (oldest first)
        assert [ts for ts, _ in s.history] == sorted(ts for ts, _ in s.history)
        assert s.event_start_ms > 0
        assert s.phase in {"upcoming", "live"}
    assert sum(1 for s in snaps if s.phase == "live") == 1


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
async def test_mma_mock_card_has_live_and_scheduled_fights():
    """The card mixes one live fight with scheduled ones — the lifecycle story."""
    c = MockMMAClient()
    events = await c.get_live_events()
    assert events
    fights = await c.get_fights(event_ids=[events[0].id])
    assert fights
    for f in fights:
        assert f.fighter1 and f.fighter2
    statuses = {f.status for f in fights}
    assert "in_progress" in statuses   # at least one live fight
    assert "scheduled" in statuses     # at least one upcoming fight


@pytest.mark.asyncio
async def test_mma_mock_only_live_fight_emits_stats():
    """Live (in_progress) fights tick stats; scheduled fights produce none."""
    c = MockMMAClient()
    events = await c.get_live_events()
    fights = await c.get_fights(event_ids=[events[0].id])
    live = next(f for f in fights if f.status == "in_progress")
    scheduled = next(f for f in fights if f.status == "scheduled")

    s1 = await c.get_fight_stats(live.id)
    s2 = await c.get_fight_stats(live.id)
    assert s1 and s2
    assert s1[0].fighter_name  # non-empty (engine requires it)
    assert s2[0].significant_strikes_landed > s1[0].significant_strikes_landed

    assert await c.get_fight_stats(scheduled.id) == []  # scheduled → no live stats


@pytest.mark.asyncio
async def test_mma_mock_unknown_fight_returns_empty():
    c = MockMMAClient()
    assert await c.get_fight_stats(999999) == []
