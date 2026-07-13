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
        question="UFC: Who wins?",   # matches the default POLYMARKET_QUERY="UFC"
        tokens=[TokenPrice(token_id="tok-1", outcome=outcome, price=price)],
        accepting_orders=True,
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
async def test_first_poll_emits_baseline_snapshot(agent, mock_emitter):
    """First sighting emits a baseline snapshot (delta 0) so the market shows up
    in the dashboard even when nothing is moving (the pre-event case)."""
    await agent._poll_once()
    mock_emitter.emit.assert_called_once()
    ev = mock_emitter.emit.call_args[0][0]
    assert ev.market_event.delta == 0.0


@pytest.mark.asyncio
async def test_quiet_market_rebaselines_periodically(agent, mock_emitter):
    """A market that never moves re-emits a baseline once REBASELINE_S elapses,
    so late-joining clients (fresh tabs / restarted gateways) still see it."""
    await agent._poll_once()                       # first sighting → baseline
    await agent._poll_once()                       # quiet, within window → nothing
    assert mock_emitter.emit.call_count == 1

    # Age the last baseline past the window and poll again.
    for mid in agent._baseline_at:
        agent._baseline_at[mid] -= 10_000
    await agent._poll_once()
    assert mock_emitter.emit.call_count == 2
    assert mock_emitter.emit.call_args[0][0].market_event.delta == 0.0


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


# ─── Research flight recorder (RESEARCH/BETS.md B-001) ──────────────────────

@pytest.mark.asyncio
async def test_capture_records_held_ticks_and_history_once(
    tmp_path, monkeypatch, mock_client, mock_emitter
):
    """With RESEARCH_CAPTURE=1 every snapshot is recorded each poll — including
    sub-threshold ticks the emit gate discards — and a market's week-long
    history is captured only on first sighting."""
    import json

    monkeypatch.setenv("RESEARCH_CAPTURE", "1")
    monkeypatch.setenv("RESEARCH_CAPTURE_DIR", str(tmp_path))
    agent = PolymarketAgent(client=mock_client, emitter=mock_emitter)

    snap1 = _make_snapshot("mkt-1", "tok-1", "Fighter A wins", 0.65)
    snap1.history = [(1000, 0.60), (2000, 0.65)]
    mock_client.get_prices.return_value = [snap1]
    await agent._poll_once()  # first sighting → baseline

    snap2 = _make_snapshot("mkt-1", "tok-1", "Fighter A wins", 0.655)
    snap2.history = [(1000, 0.60), (2000, 0.655)]
    mock_client.get_prices.return_value = [snap2]
    await agent._poll_once()  # +0.005 — below DELTA_THRESHOLD, normally invisible

    files = list(tmp_path.rglob("polymarket_agent.jsonl"))
    assert len(files) == 1
    polls = [json.loads(l) for l in files[0].read_text().splitlines()]
    assert [p["kind"] for p in polls] == ["poll", "poll"]

    first, second = polls[0]["snapshots"][0], polls[1]["snapshots"][0]
    assert first["action"] == "baseline" and first["delta"] is None
    assert "history" in first  # week history captured on first sighting…
    assert second["action"] == "held"  # …sub-threshold tick still recorded
    assert abs(second["delta"] - 0.005) < 1e-9
    assert "history" not in second  # …and history not duplicated


@pytest.mark.asyncio
async def test_capture_disabled_writes_nothing(tmp_path, monkeypatch, mock_client, mock_emitter):
    monkeypatch.delenv("RESEARCH_CAPTURE", raising=False)
    monkeypatch.setenv("RESEARCH_CAPTURE_DIR", str(tmp_path))
    agent = PolymarketAgent(client=mock_client, emitter=mock_emitter)
    await agent._poll_once()
    assert list(tmp_path.rglob("*.jsonl")) == []
