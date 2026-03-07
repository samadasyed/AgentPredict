"""
Unit tests for RAG Orchestrator — mocks all external dependencies.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from rag.orchestrator import Orchestrator, _is_meaningful
from agents.generated import events_pb2  # type: ignore[import]


def _market_event(delta: float = 0.05, probability: float = 0.65) -> events_pb2.CanonicalEvent:
    ev = events_pb2.CanonicalEvent()
    ev.event_id = "test-event-id"
    ev.source = events_pb2.SOURCE_POLYMARKET
    m = ev.market_event
    m.market_id = "mkt-abc"
    m.outcome = "Fighter A wins"
    m.probability = probability
    m.delta = delta
    m.timestamp = int(time.time() * 1000)
    return ev


def _fight_event() -> events_pb2.CanonicalEvent:
    ev = events_pb2.CanonicalEvent()
    ev.event_id = "fight-event-id"
    ev.source = events_pb2.SOURCE_MMA
    f = ev.fight_event
    f.fight_id = "fight-1"
    f.fighter_name = "Fighter B"
    f.stat_type = "FIGHT_DISCOVERED"
    f.value = 0.0
    f.round = 0
    f.timestamp = int(time.time() * 1000)
    return ev


# ─── _is_meaningful ───────────────────────────────────────────────────────────

def test_is_meaningful_large_delta():
    assert _is_meaningful(_market_event(delta=0.05)) is True

def test_is_meaningful_small_delta():
    assert _is_meaningful(_market_event(delta=0.005)) is False

def test_is_meaningful_fight_event():
    assert _is_meaningful(_fight_event()) is True

def test_is_meaningful_zero_delta():
    assert _is_meaningful(_market_event(delta=0.0)) is False


# ─── Orchestrator._handle_event ───────────────────────────────────────────────

@pytest.fixture
def orchestrator_with_mocks():
    with patch("rag.orchestrator.Retriever"), \
         patch("rag.orchestrator.InferenceEngine"), \
         patch("rag.orchestrator.Verifier"), \
         patch("rag.orchestrator.ContextBuilder"):
        orch = Orchestrator()

        # Wire up mock return values
        orch._retriever.retrieve.return_value = []
        orch._retriever.upsert.return_value = None
        orch._context_builder.build_context.return_value = "ctx"
        orch._inference.explain.return_value = MagicMock(
            explanation="Odds moved because of a big punch.",
            confidence=0.8,
        )
        orch._verifier.verify.return_value = MagicMock(
            explanation="Odds moved because of a big punch.",
            confidence=0.8,
            passed=True,
        )
        orch._rag_service.broadcast = MagicMock()
        yield orch


@pytest.mark.asyncio
async def test_handle_meaningful_event_broadcasts(orchestrator_with_mocks):
    orch = orchestrator_with_mocks
    ev = _market_event(delta=0.05)
    await orch._handle_event(ev)
    orch._rag_service.broadcast.assert_called_once()


@pytest.mark.asyncio
async def test_handle_non_meaningful_event_skips_rag(orchestrator_with_mocks):
    orch = orchestrator_with_mocks
    ev = _market_event(delta=0.001)
    await orch._handle_event(ev)
    orch._inference.explain.assert_not_called()
    orch._rag_service.broadcast.assert_not_called()


@pytest.mark.asyncio
async def test_handle_event_always_updates_context(orchestrator_with_mocks):
    orch = orchestrator_with_mocks
    ev = _market_event(delta=0.001)  # sub-threshold
    await orch._handle_event(ev)
    orch._context_builder.add.assert_called_once_with(ev)


@pytest.mark.asyncio
async def test_inference_error_does_not_crash(orchestrator_with_mocks):
    orch = orchestrator_with_mocks
    orch._inference.explain.side_effect = RuntimeError("Gemini unavailable")
    ev = _market_event(delta=0.05)
    # Should log but not raise
    await orch._handle_event(ev)
    orch._rag_service.broadcast.assert_not_called()
