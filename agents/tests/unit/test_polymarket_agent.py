"""
Unit tests for Polymarket agent — mocks HTTP client and gRPC emitter.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.polymarket.agent import PolymarketAgent, DELTA_THRESHOLD
from agents.polymarket.models import Market, PriceSnapshot, TokenPrice


def _make_snapshot(market_id: str, token_id: str, outcome: str, prob: float) -> PriceSnapshot:
    return PriceSnapshot(
        market_id=market_id,
        token_id=token_id,
        outcome=outcome,
        probability=prob,
        timestamp_ms=int(time.time() * 1000),
    )


def _make_market(condition_id: str, outcome: str = "Fighter A wins", price: float = 0.6) -> Market:
    return Market(
        condition_id=condition_id,
        question="Who wins?",
        tokens=[TokenPrice(token_id="tok-1", outcome=outcome, price=price)],
    )


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.get_markets.return_value = [_make_market("mkt-1")]
    client.get_prices.return_value = [
        _make_snapshot("mkt-1", "tok-1", "Fighter A wins", 0.65)
    ]
    return client


@pytest.fixture
def mock_emitter():
    emitter = MagicMock()
    emitter.emit.return_value = True
    return emitter


@pytest.fixture
def agent(mock_client, mock_emitter):
    return PolymarketAgent(client=mock_client, emitter=mock_emitter)


@pytest.mark.asyncio
async def test_first_poll_does_not_emit(agent, mock_emitter):
    """On the first poll there is no previous price, so delta = 0 — nothing emitted."""
    await agent._poll_once()
    mock_emitter.emit.assert_not_called()


@pytest.mark.asyncio
async def test_significant_delta_emits_event(agent, mock_client, mock_emitter):
    """A delta exceeding DELTA_THRESHOLD should produce exactly one emit."""
    # First poll — baseline
    await agent._poll_once()
    mock_emitter.emit.reset_mock()

    # Second poll — price moved by 0.05 (above threshold)
    mock_client.get_prices.return_value = [
        _make_snapshot("mkt-1", "tok-1", "Fighter A wins", 0.70)
    ]
    await agent._poll_once()

    mock_emitter.emit.assert_called_once()


@pytest.mark.asyncio
async def test_sub_threshold_delta_does_not_emit(agent, mock_client, mock_emitter):
    """A delta below DELTA_THRESHOLD should not emit."""
    await agent._poll_once()
    mock_emitter.emit.reset_mock()

    tiny_delta = DELTA_THRESHOLD * 0.5
    mock_client.get_prices.return_value = [
        _make_snapshot("mkt-1", "tok-1", "Fighter A wins", 0.65 + tiny_delta)
    ]
    await agent._poll_once()

    mock_emitter.emit.assert_not_called()


@pytest.mark.asyncio
async def test_no_active_markets_skips_gracefully(agent, mock_client, mock_emitter):
    mock_client.get_markets.return_value = []
    mock_client.get_prices.return_value = []
    await agent._poll_once()
    mock_emitter.emit.assert_not_called()


@pytest.mark.asyncio
async def test_emitted_event_has_correct_fields(agent, mock_client, mock_emitter):
    """Verify the CanonicalEvent proto fields match the snapshot data."""
    await agent._poll_once()  # baseline
    mock_client.get_prices.return_value = [
        _make_snapshot("mkt-1", "tok-1", "Fighter A wins", 0.80)
    ]
    await agent._poll_once()

    call_args = mock_emitter.emit.call_args
    ev = call_args[0][0]  # first positional arg

    from agents.generated import events_pb2  # type: ignore[import]
    assert ev.source == events_pb2.SOURCE_POLYMARKET
    assert ev.market_event.market_id == "mkt-1"
    assert ev.market_event.outcome == "Fighter A wins"
    assert abs(ev.market_event.probability - 0.80) < 1e-9
    assert ev.market_event.delta > 0
