"""
Unit tests for InferenceEngine — mocks Gemini API.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from rag.inference import InferenceEngine
from rag.retriever import EvidenceItem
from agents.generated import events_pb2  # type: ignore[import]


def _market_event() -> events_pb2.CanonicalEvent:
    ev = events_pb2.CanonicalEvent()
    ev.event_id = "ev-1"
    ev.source = events_pb2.SOURCE_POLYMARKET
    m = ev.market_event
    m.market_id = "mkt-abc"
    m.outcome = "Fighter A wins"
    m.probability = 0.7
    m.delta = 0.05
    m.timestamp = int(time.time() * 1000)
    return ev


def _evidence() -> list[EvidenceItem]:
    return [EvidenceItem(text="Fighter A landed a big punch.", source_ref="market_events/x", score=0.9)]


@pytest.fixture
def inference():
    with patch("rag.inference.genai") as mock_genai, \
         patch.dict("os.environ", {"GOOGLE_API_KEY": "fake"}):
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model
        engine = InferenceEngine()
        engine._model = mock_model
        yield engine


def test_explain_returns_explanation_and_confidence(inference):
    inference._model.generate_content.return_value = MagicMock(
        text="Odds moved because Fighter A landed a big combo.\nCONFIDENCE: 0.85"
    )
    result = inference.explain(_market_event(), "ctx", _evidence())
    assert "Fighter A" in result.explanation
    assert abs(result.confidence - 0.85) < 1e-6


def test_explain_parses_confidence_from_last_line(inference):
    inference._model.generate_content.return_value = MagicMock(
        text="Some explanation.\nAnother line.\nCONFIDENCE: 0.72"
    )
    result = inference.explain(_market_event(), "ctx", [])
    assert abs(result.confidence - 0.72) < 1e-6


def test_explain_confidence_clipped_to_one(inference):
    inference._model.generate_content.return_value = MagicMock(
        text="Great explanation.\nCONFIDENCE: 1.5"
    )
    result = inference.explain(_market_event(), "ctx", [])
    assert result.confidence <= 1.0


def test_explain_confidence_clipped_to_zero(inference):
    inference._model.generate_content.return_value = MagicMock(
        text="Explanation.\nCONFIDENCE: -0.1"
    )
    result = inference.explain(_market_event(), "ctx", [])
    assert result.confidence >= 0.0


def test_explain_missing_confidence_line_defaults_zero(inference):
    inference._model.generate_content.return_value = MagicMock(
        text="Only explanation, no confidence line."
    )
    result = inference.explain(_market_event(), "ctx", [])
    assert result.confidence == 0.0


def test_explain_raw_response_preserved(inference):
    raw = "Explanation text.\nCONFIDENCE: 0.6"
    inference._model.generate_content.return_value = MagicMock(text=raw)
    result = inference.explain(_market_event(), "ctx", [])
    assert result.raw_response == raw
