"""
Live API tests for Gemini Flash inference.

Marked with pytest.mark.api — run with:
    pytest -m api rag/tests/api/test_gemini_api.py

Requires GOOGLE_API_KEY in environment.
"""

from __future__ import annotations

import os
import time

import pytest

pytestmark = [
    pytest.mark.api,
    pytest.mark.skipif(
        not os.getenv("GOOGLE_API_KEY"),
        reason="GOOGLE_API_KEY required",
    ),
]

from rag.inference import InferenceEngine, InferenceResult
from rag.retriever import EvidenceItem
from agents.generated import events_pb2  # type: ignore[import]


@pytest.fixture(scope="module")
def engine():
    return InferenceEngine()


def _market_event() -> events_pb2.CanonicalEvent:
    ev = events_pb2.CanonicalEvent()
    ev.event_id = "live-test-event"
    ev.source = events_pb2.SOURCE_POLYMARKET
    m = ev.market_event
    m.market_id = "mkt-test-123"
    m.outcome = "Fighter A wins"
    m.probability = 0.72
    m.delta = 0.08
    m.timestamp = int(time.time() * 1000)
    return ev


def test_gemini_returns_inference_result(engine):
    """Live call — Gemini should respond with an explanation."""
    evidence = [EvidenceItem(text="Fighter A landed 3 consecutive jabs.", source_ref="x/y", score=0.9)]
    result = engine.explain(_market_event(), context_text="[POLYMARKET]\nmarket_id=mkt-test-123", evidence=evidence)

    assert isinstance(result, InferenceResult)
    assert len(result.explanation) > 0
    assert 0.0 <= result.confidence <= 1.0


def test_gemini_explanation_is_not_empty(engine):
    result = engine.explain(_market_event(), context_text="(no recent events)", evidence=[])
    assert result.explanation.strip() != ""


def test_gemini_confidence_is_valid_float(engine):
    result = engine.explain(_market_event(), context_text="ctx", evidence=[])
    assert isinstance(result.confidence, float)
    assert 0.0 <= result.confidence <= 1.0
