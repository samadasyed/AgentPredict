"""
Unit tests for InferenceEngine — mocks Gemini API.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from rag.inference import InferenceEngine, describe_trigger, _response_text
from rag.retriever import EvidenceItem
from agents.generated import events_pb2  # type: ignore[import]


def _market_event(**meta) -> events_pb2.CanonicalEvent:
    ev = events_pb2.CanonicalEvent()
    ev.event_id = "ev-1"
    ev.source = events_pb2.SOURCE_POLYMARKET
    m = ev.market_event
    m.market_id = "mkt-abc"
    m.outcome = "Fighter A wins"
    m.probability = 0.7
    m.delta = 0.05
    m.timestamp = int(time.time() * 1000)
    for key, value in meta.items():
        setattr(m, key, value)
    return ev


def _evidence() -> list[EvidenceItem]:
    return [EvidenceItem(text="Fighter A landed a big punch.", source_ref="market_events/x", score=0.9)]


def _gemini_response(text: str) -> MagicMock:
    """Response shaped like the real SDK object: candidates → content → parts."""
    part = MagicMock()
    part.text = text
    return MagicMock(candidates=[MagicMock(content=MagicMock(parts=[part]))])


@pytest.fixture
def inference():
    with patch("rag.inference.genai") as mock_genai, \
         patch.dict("os.environ", {"GOOGLE_API_KEY": "fake"}):
        # google.genai shape: client.models.generate_content(...)
        mock_genai.Client.return_value = MagicMock()
        engine = InferenceEngine()
        yield engine


def test_explain_returns_explanation_and_confidence(inference):
    inference._client.models.generate_content.return_value = _gemini_response(
        "Odds moved because Fighter A landed a big combo.\nCONFIDENCE: 0.85"
    )
    result = inference.explain(_market_event(), "ctx", _evidence())
    assert "Fighter A" in result.explanation
    assert abs(result.confidence - 0.85) < 1e-6


def test_explain_parses_confidence_from_last_line(inference):
    inference._client.models.generate_content.return_value = _gemini_response(
        "Some explanation.\nAnother line.\nCONFIDENCE: 0.72"
    )
    result = inference.explain(_market_event(), "ctx", [])
    assert abs(result.confidence - 0.72) < 1e-6


def test_explain_percent_confidence_scaled_down():
    # "CONFIDENCE: 85" means 85%, not maximum confidence.
    explanation, confidence = InferenceEngine._parse_response("Fine.\nCONFIDENCE: 85")
    assert abs(confidence - 0.85) < 1e-6
    assert explanation == "Fine."


def test_explain_confidence_clipped_to_one(inference):
    inference._client.models.generate_content.return_value = _gemini_response(
        "Great explanation.\nCONFIDENCE: 150"
    )
    result = inference.explain(_market_event(), "ctx", [])
    assert result.confidence <= 1.0


def test_explain_confidence_clipped_to_zero(inference):
    inference._client.models.generate_content.return_value = _gemini_response(
        "Explanation.\nCONFIDENCE: -0.1"
    )
    result = inference.explain(_market_event(), "ctx", [])
    assert result.confidence >= 0.0


def test_explain_missing_confidence_line_defaults_zero(inference):
    inference._client.models.generate_content.return_value = _gemini_response(
        "Only explanation, no confidence line."
    )
    result = inference.explain(_market_event(), "ctx", [])
    assert result.confidence == 0.0


def test_explain_raw_response_preserved(inference):
    raw = "Explanation text.\nCONFIDENCE: 0.6"
    inference._client.models.generate_content.return_value = _gemini_response(raw)
    result = inference.explain(_market_event(), "ctx", [])
    assert result.raw_response == raw


def test_explain_safety_block_raises_clean_error(inference):
    # No candidates (safety block / empty response) must raise RuntimeError,
    # not the SDK's ValueError from `response.text`.
    inference._client.models.generate_content.return_value = MagicMock(
        candidates=[], prompt_feedback="BLOCKED"
    )
    with pytest.raises(RuntimeError, match="no usable text"):
        inference.explain(_market_event(), "ctx", [])


def test_response_text_joins_parts():
    p1, p2 = MagicMock(), MagicMock()
    p1.text, p2.text = "Hello ", "world"
    resp = MagicMock(candidates=[MagicMock(content=MagicMock(parts=[p1, p2]))])
    assert _response_text(resp) == "Hello world"


def test_describe_trigger_uses_fight_metadata():
    ev = _market_event(
        outcome="Max Holloway",
        title="Max Holloway vs. Conor McGregor",
        card_title="UFC 329",
        fight_info="Welterweight · Main Card",
        phase="upcoming",
        probability=0.665,
        delta=0.03,
    )
    desc = describe_trigger(ev)
    assert "Max Holloway vs. Conor McGregor" in desc
    assert "UFC 329" in desc
    assert "66.5%" in desc
    # The raw hex market id should not lead the description anymore.
    assert not desc.startswith("Market 'mkt-abc'")


def test_describe_trigger_falls_back_to_outcome():
    desc = describe_trigger(_market_event())
    assert "Fighter A wins" in desc
