"""Unit tests for the offline RAG components (MOCK_MODE: no Pinecone/Gemini)."""

from __future__ import annotations

import time

from rag.mock_components import MockRetriever, MockInference
from rag.retriever import EvidenceItem
from rag.inference import InferenceResult
from rag.verifier import Verifier
from agents.generated import events_pb2  # type: ignore[import]


def _market_event() -> events_pb2.CanonicalEvent:
    ev = events_pb2.CanonicalEvent(event_id="e1", source=events_pb2.SOURCE_POLYMARKET)
    ev.market_event.market_id = "0xufc-jones-aspinall"
    ev.market_event.outcome = "Jon Jones def. Tom Aspinall"
    ev.market_event.probability = 0.61
    ev.market_event.delta = 0.04
    ev.market_event.timestamp = int(time.time() * 1000)
    return ev


def _fight_event() -> events_pb2.CanonicalEvent:
    ev = events_pb2.CanonicalEvent(event_id="f1", source=events_pb2.SOURCE_MMA)
    ev.fight_event.fight_id = "5001"
    ev.fight_event.fighter_name = "Jon Jones"
    ev.fight_event.stat_type = "significant_strikes"
    ev.fight_event.value = 12
    ev.fight_event.round = 2
    ev.fight_event.timestamp = int(time.time() * 1000)
    return ev


# ─── MockRetriever ────────────────────────────────────────────────────────────

def test_retriever_returns_evidence_items_capped_at_top_k():
    r = MockRetriever(top_k=3)
    out = r.retrieve("Jon Jones takedown")
    assert 0 < len(out) <= 3
    assert all(isinstance(e, EvidenceItem) for e in out)
    assert all(0.0 <= e.score <= 1.0 for e in out)


def test_retriever_ranks_keyword_overlap_first():
    r = MockRetriever(top_k=5)
    out = r.retrieve("Pereira knockout power")
    assert "Pereira" in out[0].text  # best keyword overlap ranked first


def test_retriever_upsert_then_retrieve_includes_new_doc():
    r = MockRetriever(top_k=10)
    ev = _market_event()
    r.upsert(ev)
    texts = " ".join(e.text for e in r.retrieve("Jones Aspinall probability"))
    assert "jones-aspinall" in texts.lower() or "Jon Jones" in texts


# ─── MockInference (+ Verifier integration) ───────────────────────────────────

def test_inference_returns_inference_result_for_market():
    res = MockInference().explain(_market_event(), "ctx", [])
    assert isinstance(res, InferenceResult)
    assert res.confidence >= 0.5
    assert "CONFIDENCE:" in res.raw_response


def test_inference_market_explanation_passes_verifier():
    ev = _market_event()
    res = MockInference().explain(ev, "ctx", MockRetriever().retrieve(ev.market_event.outcome))
    verified = Verifier().verify(res.explanation, res.confidence, ev)
    assert verified.passed, "mock explanation must reference the trigger and clear confidence"


def test_inference_fight_explanation_passes_verifier():
    ev = _fight_event()
    res = MockInference().explain(ev, "ctx", [])
    verified = Verifier().verify(res.explanation, res.confidence, ev)
    assert verified.passed
