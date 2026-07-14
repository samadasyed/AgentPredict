"""
Offline tests for the B-002 eval harness. Not on pytest's default testpaths —
run explicitly:  pytest RESEARCH/harness/test_harness.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from harness import (Capture, evaluate, grounding_score, load_capture,  # noqa: E402
                     outcome_consistency)


def _cycle(explanation: str, passed: bool = True, market_id: str = "mkt-1",
           prob: float = 0.65, delta: float = 0.05, ts_ms: int = 1_000_000) -> dict:
    return {
        "kind": "cycle", "ts_ms": ts_ms, "trigger_key": f"mkt:{market_id}",
        "trigger": {"market_event": {
            "market_id": market_id, "outcome": "Max Holloway",
            "title": "Max Holloway vs. Conor McGregor", "card_title": "UFC 329",
            "probability": prob, "delta": delta, "timestamp": str(ts_ms - 3000),
        }},
        "context_text": "fight='UFC 329: Max Holloway vs. Conor McGregor' prob=0.6500",
        "query": "Max Holloway vs. Conor McGregor on UFC 329",
        "evidence": [{"text": "Holloway landed a knockdown late in round 2.",
                      "source_ref": "fight_events", "score": 0.9}],
        "upserted": True,
        "raw_explanation": explanation, "raw_confidence": 0.8,
        "verified_explanation": explanation, "verified_confidence": 0.8,
        "passed": passed, "latency_ms": 1200,
    }


def _poll(market_id: str, pts: list[tuple[int, float]]) -> dict:
    return {"kind": "poll", "ts_ms": pts[-1][0], "n_selected": 1, "snapshots": [
        {"market_id": market_id, "token_id": "t", "outcome": "Max Holloway",
         "probability": p, "timestamp_ms": t, "action": "held", "delta": 0.001}
        for t, p in pts]}


def test_grounded_explanation_scores_high():
    score, ungrounded = grounding_score(_cycle(
        "Holloway's odds rose to 65% after the knockdown in round 2."))
    assert score == 1.0 and ungrounded == []


def test_hallucinated_name_and_number_lower_score():
    score, ungrounded = grounding_score(_cycle(
        "Khabib Nurmagomedov landed 47 takedowns, moving Holloway to 65%."))
    assert score is not None and score < 1.0
    assert any("Khabib" in u for u in ungrounded)
    assert "47.0" in ungrounded


def test_no_checkable_claims_returns_none():
    score, _ = grounding_score(_cycle("the odds moved for unclear reasons."))
    assert score is None


def test_outcome_continued_and_reverted():
    cap = Capture(polls=[_poll("mkt-1", [(1_060_000, 0.70)])])
    assert outcome_consistency(_cycle("x"), cap) == "continued"
    cap_rev = Capture(polls=[_poll("mkt-1", [(1_060_000, 0.58)])])
    assert outcome_consistency(_cycle("x"), cap_rev) == "reverted"


def test_evaluate_separation_and_roundtrip(tmp_path):
    day = tmp_path / "20260713"
    day.mkdir()
    (day / "rag.jsonl").write_text("\n".join(json.dumps(r) for r in [
        _cycle("Holloway's odds rose to 65% after the knockdown."),
        _cycle("Zebra Quagga surged 99 points.", passed=False),
        {"kind": "skip", "ts_ms": 1, "reason": "cooldown", "trigger_key": "mkt:mkt-1",
         "trigger": {}},
    ]) + "\n")
    (day / "polymarket_agent.jsonl").write_text(
        json.dumps(_poll("mkt-1", [(1_060_000, 0.70)])) + "\n")

    report = evaluate(load_capture(tmp_path))
    assert report["n_cycles"] == 2 and report["n_skips"] == 1
    assert report["grounding_mean_pass"] == 1.0
    assert report["grounding_mean_fail"] < 0.5
    assert report["separation"] > 0.5
    assert report["latency_ms_p50"] == 1200
    assert report["outcomes"]["continued"] >= 1


# ─── drift analyzer ──────────────────────────────────────────────────────────

def test_drift_analyzer_thresholds_and_excursion():
    from drift import analyze, _cum_triggers, _max_excursion

    # Path: 0.50 → drifts up 0.002/tick ×5 (cum +0.01) → one -0.015 tick
    probs = [0.50, 0.502, 0.504, 0.506, 0.508, 0.510, 0.495]
    assert _cum_triggers(probs, 0.01) == 2       # +0.01 crossed, then -0.015
    assert abs(_max_excursion(probs) - 0.015) < 1e-12

    polls = [_poll("mkt-d", [(1_000_000 + i * 5000, p)])
             for i, p in enumerate(probs)]
    cap = Capture(polls=polls)
    d = analyze(cap)[0]
    assert d.n_ticks == 7
    assert d.tick_emits[0.01] == 1               # only the -0.015 tick
    assert d.tick_emits[0.002] == 6              # every move
    assert d.cum_emits[0.01] == 2
    assert abs(d.total_variation - 0.025) < 1e-9
