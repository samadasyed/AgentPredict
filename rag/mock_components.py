"""
Offline RAG components — no Pinecone, no Gemini, no API keys.

Enabled when MOCK_MODE=1. MockRetriever is an in-memory keyword store seeded with
plausible MMA/market evidence; MockInference produces a grounded, templated
explanation that references the triggering event (so the Verifier passes) with a
deterministic confidence. Both return the SAME dataclasses the real components do,
so the orchestrator and verifier are exercised unchanged.

Owner: Samad (demo/offline harness)
"""

from __future__ import annotations

import logging
from collections import deque

from rag.retriever import EvidenceItem, _event_to_text
from rag.inference import InferenceResult
from agents.generated import events_pb2  # type: ignore[import]

logger = logging.getLogger(__name__)

# Seed corpus: (text, source_ref). Retrieval is keyword-overlap scored.
_SEED_CORPUS: list[tuple[str, str]] = [
    ("Jon Jones has won 11 of his last 12 by finishing the fight in the championship rounds.",
     "fight_events/seed-jones-1"),
    ("Tom Aspinall averages 6.3 significant strikes per minute, among the highest in the division.",
     "fight_events/seed-aspinall-1"),
    ("Alex Pereira's knockout power has produced 4 first-round finishes in his last 6 fights.",
     "fight_events/seed-pereira-1"),
    ("Sean O'Malley's striking accuracy drops sharply when opponents close distance and clinch.",
     "fight_events/seed-omalley-1"),
    ("Islam Makhachev's grappling control time leads to large in-fight win-probability swings.",
     "fight_events/seed-makhachev-1"),
    ("Polymarket odds tend to overreact to a single significant-strike flurry before reverting.",
     "market_events/seed-flow-1"),
    ("Sharp money on Polymarket usually moves implied probability 3-5 points within minutes of a takedown.",
     "market_events/seed-flow-2"),
]


class MockRetriever:
    """In-memory keyword retriever standing in for the Pinecone-backed Retriever."""

    def __init__(self, top_k: int = 5) -> None:
        self._top_k = top_k
        # Seed + room for upserted events (bounded so a long demo can't grow unbounded).
        self._docs: deque[tuple[str, str]] = deque(_SEED_CORPUS, maxlen=500)

    def upsert(self, event: "events_pb2.CanonicalEvent") -> None:
        ns = "market_events" if event.HasField("market_event") else "fight_events"
        self._docs.append((_event_to_text(event), f"{ns}/{event.event_id}"))

    def retrieve(self, query_text: str, namespace=None, top_k: int | None = None) -> list[EvidenceItem]:
        k = top_k or self._top_k
        terms = {t for t in query_text.lower().split() if len(t) > 2}
        scored: list[EvidenceItem] = []
        for text, ref in self._docs:
            words = set(text.lower().split())
            overlap = len(terms & words)
            # Normalize to a (0,1]-ish pseudo-similarity so downstream formatting is sane.
            score = round(0.5 + 0.1 * overlap, 4) if overlap else 0.3
            scored.append(EvidenceItem(text=text, source_ref=ref, score=score))
        scored.sort(key=lambda e: e.score, reverse=True)
        return scored[:k]


class MockInference:
    """Templated explanation generator standing in for the Gemini InferenceEngine."""

    def __init__(self, confidence: float = 0.82) -> None:
        self._confidence = confidence

    def explain(self, trigger_event, context_text, evidence) -> InferenceResult:
        top = evidence[0].text if evidence else "recent live-fight signals"
        if trigger_event.HasField("market_event"):
            m = trigger_event.market_event
            fight = m.title or m.outcome
            # Mentions the outcome/fighters so the Verifier's identifier check passes.
            explanation = (
                f"{fight}: '{m.outcome}' moved {m.delta:+.1%} to an implied "
                f"{m.probability:.0%}. This shift is consistent with live momentum — {top}"
            )
        else:
            f = trigger_event.fight_event
            explanation = (
                f"Fighter {f.fighter_name} in fight {f.fight_id} registered {f.stat_type}="
                f"{f.value:g} in round {f.round}, nudging live win probability. Supporting context: {top}"
            )
        raw = f"{explanation}\nCONFIDENCE: {self._confidence}"
        return InferenceResult(explanation=explanation, confidence=self._confidence, raw_response=raw)
