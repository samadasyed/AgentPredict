"""
Live API tests for Pinecone connectivity.

Marked with pytest.mark.api — run with:
    pytest -m api rag/tests/api/test_pinecone_api.py

Requires PINECONE_API_KEY and GOOGLE_API_KEY in environment.
"""

from __future__ import annotations

import os
import time

import pytest

pytestmark = pytest.mark.api

# Skip entire module if API keys are absent.
pytestmark = [
    pytest.mark.api,
    pytest.mark.skipif(
        not os.getenv("PINECONE_API_KEY") or not os.getenv("GOOGLE_API_KEY"),
        reason="PINECONE_API_KEY and GOOGLE_API_KEY required",
    ),
]

from rag.retriever import Retriever, EvidenceItem
from agents.generated import events_pb2  # type: ignore[import]


@pytest.fixture(scope="module")
def retriever():
    return Retriever()


def _market_event(event_id: str) -> events_pb2.CanonicalEvent:
    ev = events_pb2.CanonicalEvent()
    ev.event_id = event_id
    ev.source = events_pb2.SOURCE_POLYMARKET
    m = ev.market_event
    m.market_id = "test-market"
    m.outcome = "Test fighter wins"
    m.probability = 0.5
    m.delta = 0.1
    m.timestamp = int(time.time() * 1000)
    return ev


def test_pinecone_index_accessible(retriever):
    """Pinecone index can be queried without error."""
    results = retriever.retrieve("test query", top_k=1)
    assert isinstance(results, list)


def test_upsert_and_retrieve_roundtrip(retriever):
    """Upsert an event and retrieve it back."""
    import uuid
    unique_id = str(uuid.uuid4())
    ev = _market_event(unique_id)
    retriever.upsert(ev)

    # Allow time for Pinecone to index the vector.
    time.sleep(2)

    results = retriever.retrieve("Test fighter wins", top_k=10)
    ids = [r.source_ref.split("/")[-1] for r in results]
    assert unique_id in ids, f"Upserted event {unique_id} not found in results: {ids}"


def test_evidence_items_have_valid_scores(retriever):
    results = retriever.retrieve("fighter probability odds", top_k=5)
    for r in results:
        assert 0.0 <= r.score <= 1.0, f"Invalid score: {r.score}"
