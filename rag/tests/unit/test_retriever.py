"""
Unit tests for Retriever — mocks Pinecone and Gemini.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from agents.generated import events_pb2  # type: ignore[import]


def _market_event(event_id: str = "ev-1") -> events_pb2.CanonicalEvent:
    ev = events_pb2.CanonicalEvent()
    ev.event_id = event_id
    ev.source = events_pb2.SOURCE_POLYMARKET
    m = ev.market_event
    m.market_id = "mkt-1"
    m.outcome = "Fighter A wins"
    m.probability = 0.7
    m.delta = 0.05
    m.timestamp = int(time.time() * 1000)
    return ev


@pytest.fixture
def retriever():
    with patch("rag.retriever.Pinecone") as mock_pc, \
         patch("rag.retriever.genai") as mock_genai, \
         patch.dict("os.environ", {"PINECONE_API_KEY": "fake", "GOOGLE_API_KEY": "fake"}):

        mock_pc.return_value.list_indexes.return_value = [MagicMock(name="agentpredict")]
        mock_pc.return_value.Index.return_value = MagicMock()
        mock_genai.embed_content.return_value = {"embedding": [0.1] * 768}

        from rag.retriever import Retriever
        r = Retriever()
        r._index = MagicMock()
        r._index.query.return_value = MagicMock(
            matches=[
                MagicMock(id="ev-old", score=0.9, metadata={"text": "Some old event"}),
                MagicMock(id="ev-older", score=0.7, metadata={"text": "Older event"}),
            ]
        )
        yield r


def test_upsert_calls_pinecone(retriever):
    ev = _market_event("new-event")
    retriever.upsert(ev)
    retriever._index.upsert.assert_called_once()


def test_retrieve_returns_evidence_items(retriever):
    from rag.retriever import EvidenceItem
    results = retriever.retrieve("Fighter A wins", top_k=5)
    assert len(results) > 0
    assert all(isinstance(r, EvidenceItem) for r in results)


def test_retrieve_scores_sorted_descending(retriever):
    results = retriever.retrieve("Fighter A wins")
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_source_ref_includes_namespace(retriever):
    results = retriever.retrieve("Fighter A wins")
    for r in results:
        assert "/" in r.source_ref  # e.g. "market_events/ev-old"


def test_upsert_fight_event_uses_fight_namespace(retriever):
    ev = events_pb2.CanonicalEvent()
    ev.event_id = "fight-ev-1"
    ev.source = events_pb2.SOURCE_MMA
    f = ev.fight_event
    f.fight_id = "fight-1"
    f.fighter_name = "Conor"
    f.stat_type = "significant_strikes"
    f.value = 10.0
    f.round = 2
    f.timestamp = int(time.time() * 1000)

    retriever.upsert(ev)
    call_kwargs = retriever._index.upsert.call_args[1]
    assert call_kwargs["namespace"] == "fight_events"
