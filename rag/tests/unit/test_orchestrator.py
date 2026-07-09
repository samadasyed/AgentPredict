"""
Unit tests for RAG Orchestrator — mocks all external dependencies.
"""

from __future__ import annotations

import threading
import time
from queue import Empty
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from rag.orchestrator import Orchestrator, RagStreamServiceImpl, _is_meaningful
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


def _fight_event(stat_type: str = "significant_strikes", value: float = 10.0) -> events_pb2.CanonicalEvent:
    ev = events_pb2.CanonicalEvent()
    ev.event_id = "fight-event-id"
    ev.source = events_pb2.SOURCE_MMA
    f = ev.fight_event
    f.fight_id = "fight-1"
    f.fighter_name = "Fighter B"
    f.stat_type = stat_type
    f.value = value
    f.round = 0
    f.timestamp = int(time.time() * 1000)
    return ev


# ─── _is_meaningful ───────────────────────────────────────────────────────────

def test_is_meaningful_large_delta():
    assert _is_meaningful(_market_event(delta=0.05)) is True

def test_is_meaningful_small_delta():
    assert _is_meaningful(_market_event(delta=0.005)) is False

def test_is_meaningful_fight_event():
    assert _is_meaningful(_fight_event(stat_type="significant_strikes")) is True

def test_is_meaningful_fight_sentinels_skipped():
    # Schedule/discovery markers must not trigger inference (they're re-emitted).
    assert _is_meaningful(_fight_event(stat_type="FIGHT_UPCOMING", value=0.0)) is False
    assert _is_meaningful(_fight_event(stat_type="FIGHT_DISCOVERED", value=0.0)) is False

def test_is_meaningful_zero_delta():
    assert _is_meaningful(_market_event(delta=0.0)) is False


# ─── Orchestrator._handle_event ───────────────────────────────────────────────

async def _handle_and_settle(orch, ev) -> None:
    """Trigger the handler and wait for its fire-and-forget cycle task."""
    await orch._handle_event(ev)
    if orch._cycle_task is not None:
        await orch._cycle_task

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
    await _handle_and_settle(orch, ev)
    orch._rag_service.broadcast.assert_called_once()


@pytest.mark.asyncio
async def test_handle_non_meaningful_event_skips_rag(orchestrator_with_mocks):
    orch = orchestrator_with_mocks
    ev = _market_event(delta=0.001)
    await _handle_and_settle(orch, ev)
    orch._inference.explain.assert_not_called()
    orch._rag_service.broadcast.assert_not_called()


@pytest.mark.asyncio
async def test_handle_event_always_updates_context(orchestrator_with_mocks):
    orch = orchestrator_with_mocks
    ev = _market_event(delta=0.001)  # sub-threshold
    await _handle_and_settle(orch, ev)
    orch._context_builder.add.assert_called_once_with(ev)


@pytest.mark.asyncio
async def test_inference_error_does_not_crash(orchestrator_with_mocks):
    orch = orchestrator_with_mocks
    orch._inference.explain.side_effect = RuntimeError("Gemini unavailable")
    ev = _market_event(delta=0.05)
    # Should log but not raise
    await _handle_and_settle(orch, ev)
    orch._rag_service.broadcast.assert_not_called()


@pytest.mark.asyncio
async def test_market_cooldown_skips_second_cycle(orchestrator_with_mocks):
    orch = orchestrator_with_mocks
    await _handle_and_settle(orch, _market_event(delta=0.05))
    await orch._handle_event(_market_event(delta=0.05))  # same market, immediately
    # Only ONE paid inference ran; the second trigger was on cooldown.
    assert orch._inference.explain.call_count == 1


@pytest.mark.asyncio
async def test_different_markets_not_cross_cooled(orchestrator_with_mocks):
    orch = orchestrator_with_mocks
    ev1 = _market_event(delta=0.05)
    ev2 = _market_event(delta=0.05)
    ev2.market_event.market_id = "mkt-other"
    await _handle_and_settle(orch, ev1)
    await _handle_and_settle(orch, ev2)
    assert orch._inference.explain.call_count == 2


@pytest.mark.asyncio
async def test_failed_verification_not_broadcast(orchestrator_with_mocks):
    orch = orchestrator_with_mocks
    orch._verifier.verify.return_value = MagicMock(
        explanation="Insufficient confidence…", confidence=0.2, passed=False,
    )
    await _handle_and_settle(orch, _market_event(delta=0.05))
    orch._rag_service.broadcast.assert_not_called()


@pytest.mark.asyncio
async def test_slow_drift_accumulates_to_a_trigger(orchestrator_with_mocks):
    """Pre-event lines move a fraction of a point per tick. No single tick is
    meaningful, but once the CUMULATIVE move crosses the threshold, one
    explanation fires — with the total move as its delta."""
    orch = orchestrator_with_mocks
    # Four ticks of +0.5pt each: 0.650 → 0.665 (ref seeds at 0.645).
    for i, p in enumerate((0.650, 0.655, 0.660, 0.665)):
        ev = _market_event(delta=0.005, probability=p)
        await _handle_and_settle(orch, ev)
        if i < 3:
            orch._inference.explain.assert_not_called()
    assert orch._inference.explain.call_count == 1
    trigger = orch._inference.explain.call_args[0][0]
    assert abs(trigger.market_event.delta - 0.02) < 1e-9   # cumulative, not 0.005


@pytest.mark.asyncio
async def test_drift_ref_resets_after_explanation(orchestrator_with_mocks):
    orch = orchestrator_with_mocks
    await _handle_and_settle(orch, _market_event(delta=0.05, probability=0.65))
    assert orch._inference.explain.call_count == 1
    # Ref is now 0.65 — a small wiggle around it must NOT re-trigger,
    # even after the cooldown expires.
    orch._last_cycle_at.clear()
    await _handle_and_settle(orch, _market_event(delta=0.005, probability=0.655))
    assert orch._inference.explain.call_count == 1


@pytest.mark.asyncio
async def test_baseline_events_seed_but_never_trigger(orchestrator_with_mocks):
    """The agent re-emits delta-0 baselines every ~2min for visibility —
    a flat line must not generate predictions."""
    orch = orchestrator_with_mocks
    for _ in range(5):
        await _handle_and_settle(orch, _market_event(delta=0.0, probability=0.65))
    orch._inference.explain.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_budget_caps_writes(orchestrator_with_mocks):
    orch = orchestrator_with_mocks
    with patch("rag.orchestrator._MAX_UPSERTS_PER_HOUR", 2):
        for i in range(4):
            ev = _market_event(delta=0.05)
            ev.market_event.market_id = f"mkt-{i}"   # distinct → no cooldown skips
            await _handle_and_settle(orch, ev)
    assert orch._retriever.upsert.call_count == 2
    # Inference still ran every time — only the WRITE is budgeted.
    assert orch._inference.explain.call_count == 4


# ─── RagStreamServiceImpl ─────────────────────────────────────────────────────

def _prediction(confidence: float = 0.8) -> events_pb2.RagPrediction:
    pred = events_pb2.RagPrediction()
    pred.explanation = "test"
    pred.confidence = confidence
    pred.timestamp = int(time.time() * 1000)
    pred.trigger_event_id = "evt-1"
    return pred


def test_register_then_broadcast_delivers():
    svc = RagStreamServiceImpl()
    q = svc.register_subscriber()
    pred = _prediction()
    svc.broadcast(pred)
    assert q.get_nowait().explanation == "test"


def test_unregister_stops_delivery():
    svc = RagStreamServiceImpl()
    q = svc.register_subscriber()
    svc.unregister_subscriber(q)
    svc.broadcast(_prediction())
    with pytest.raises(Empty):
        q.get_nowait()


def test_broadcast_drops_silently_when_queue_full():
    svc = RagStreamServiceImpl()
    q = svc.register_subscriber()
    # Queue maxsize is 100 — overflow it. broadcast must not raise.
    for _ in range(150):
        svc.broadcast(_prediction())
    assert q.qsize() == 100  # capped, no exception leaked out


def test_concurrent_register_unregister_broadcast_no_crash():
    """register and unregister run on gRPC threadpool workers while
    broadcast runs on the asyncio loop — pound on all three from
    multiple threads to confirm threading.Lock makes it safe."""
    svc = RagStreamServiceImpl()
    stop = threading.Event()
    errors: list[BaseException] = []

    def churn():
        try:
            while not stop.is_set():
                q = svc.register_subscriber()
                svc.unregister_subscriber(q)
        except BaseException as e:
            errors.append(e)

    def broadcaster():
        try:
            while not stop.is_set():
                svc.broadcast(_prediction())
        except BaseException as e:
            errors.append(e)

    threads = [threading.Thread(target=churn) for _ in range(4)]
    threads += [threading.Thread(target=broadcaster) for _ in range(2)]
    for t in threads:
        t.start()
    time.sleep(0.2)
    stop.set()
    for t in threads:
        t.join(timeout=2.0)
    assert not errors, f"thread errors: {errors}"
