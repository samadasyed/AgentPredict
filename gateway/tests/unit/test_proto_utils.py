"""
Pins the protobuf -> dict wire contract used by the gateway subscribers.

Regression guard for the protobuf 5.x kwarg change: `including_default_value_fields`
was removed in protobuf 5.x (raises TypeError on the pinned 5.27.2) and replaced by
`always_print_fields_with_no_presence`. These tests fail loudly if the conversion
breaks or stops emitting the presence-less `source` field that the per-client filter
depends on.
"""

from __future__ import annotations

from agents.generated import events_pb2 as pb  # type: ignore[import]

from gateway.proto_utils import to_dict


def test_market_event_roundtrip_uses_snake_case_and_source():
    ev = pb.CanonicalEvent(event_id="e1", source=pb.SOURCE_POLYMARKET)
    ev.market_event.market_id = "0xMKT"
    ev.market_event.probability = 0.7
    ev.market_event.delta = 0.05

    d = to_dict(ev)

    assert d["event_id"] == "e1"
    assert d["source"] == "SOURCE_POLYMARKET"
    assert d["market_event"]["market_id"] == "0xMKT"  # snake_case preserved


def test_unknown_source_is_always_emitted():
    # source defaults to SOURCE_UNKNOWN(0); it must still appear so the filter can see it.
    d = to_dict(pb.CanonicalEvent(event_id="e2"))
    assert d["source"] == "SOURCE_UNKNOWN"


def test_rag_prediction_roundtrip():
    pred = pb.RagPrediction(explanation="why", confidence=0.81, trigger_event_id="e1")
    pred.evidence.add(text="passage", source_ref="market_events/x", score=0.92)

    d = to_dict(pred)

    assert d["explanation"] == "why"
    assert d["confidence"] == 0.81
    assert d["trigger_event_id"] == "e1"
    assert d["evidence"][0]["source_ref"] == "market_events/x"
