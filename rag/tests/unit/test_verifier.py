"""
Unit tests for the Verifier's token-based hallucination check.
"""

from __future__ import annotations

import time

from rag.verifier import Verifier
from agents.generated import events_pb2  # type: ignore[import]


def _market_event(outcome: str = "Max Holloway",
                  title: str = "Max Holloway vs. Conor McGregor",
                  card: str = "UFC 329") -> events_pb2.CanonicalEvent:
    ev = events_pb2.CanonicalEvent()
    ev.event_id = "ev-1"
    ev.source = events_pb2.SOURCE_POLYMARKET
    m = ev.market_event
    m.market_id = "0xc851deadbeef"
    m.outcome = outcome
    m.title = title
    m.card_title = card
    m.probability = 0.66
    m.delta = 0.04
    m.timestamp = int(time.time() * 1000)
    return ev


def _fight_event(fighter: str = "Jon Jones") -> events_pb2.CanonicalEvent:
    ev = events_pb2.CanonicalEvent()
    ev.event_id = "ev-2"
    ev.source = events_pb2.SOURCE_MMA
    f = ev.fight_event
    f.fight_id = "5001"
    f.fighter_name = fighter
    f.stat_type = "significant_strikes"
    f.value = 12
    f.timestamp = int(time.time() * 1000)
    return ev


def test_surname_only_mention_passes():
    v = Verifier()
    # Analysts shorten "Max Holloway" to "Holloway" — must not be flagged.
    out = v.verify("Holloway's line firmed after the weigh-in.", 0.8, _market_event())
    assert out.passed is True
    assert "Holloway" in out.explanation


def test_opponent_mention_passes():
    v = Verifier()
    out = v.verify("Money keeps coming in on McGregor to pull the upset.", 0.8, _market_event())
    assert out.passed is True


def test_unrelated_text_fails():
    v = Verifier()
    out = v.verify("The weather in Las Vegas is lovely today.", 0.9, _market_event())
    assert out.passed is False
    assert "Insufficient confidence" in out.explanation


def test_generic_tokens_do_not_count():
    v = Verifier()
    # "will", "win", "fight" are too generic to prove grounding.
    out = v.verify("Someone will win the fight.", 0.9, _market_event())
    assert out.passed is False


def test_fight_event_surname_passes():
    v = Verifier()
    out = v.verify("Jones is pouring on the pressure this round.", 0.8, _fight_event())
    assert out.passed is True


def test_low_confidence_fails_regardless_of_mention():
    v = Verifier()
    out = v.verify("Holloway's odds moved.", 0.2, _market_event())
    assert out.passed is False
