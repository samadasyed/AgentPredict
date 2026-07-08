"""
Confidence verifier and explanation sanity-checker.

- If confidence < MIN_CONFIDENCE, returns a neutral fallback message.
- Checks that the explanation mentions the triggering market_id or fighter_name
  to catch hallucinations that ignore the actual event.

Owner: FWS
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from agents.generated import events_pb2  # type: ignore[import]

logger = logging.getLogger(__name__)

MIN_CONFIDENCE: float = 0.5

# Tokens too generic to prove the explanation is about THIS event ("yes"/"no"
# outcomes, matchup filler, the promotion name — every explanation says "UFC").
_GENERIC_TOKENS = {"yes", "the", "and", "will", "win", "wins", "fight", "over", "under", "ufc"}

_NEUTRAL_EXPLANATION = (
    "Insufficient confidence to provide a reliable explanation for this odds movement."
)


@dataclass
class VerifiedResult:
    explanation: str
    confidence: float
    passed: bool   # True if explanation passed all checks


class Verifier:
    """Validates inference results before they are emitted as RagPredictions."""

    def __init__(self, min_confidence: float = MIN_CONFIDENCE) -> None:
        self._min_confidence = min_confidence

    def verify(
        self,
        explanation: str,
        confidence: float,
        trigger_event: "events_pb2.CanonicalEvent",
    ) -> VerifiedResult:
        """
        Validate an inference result.

        Checks:
        1. confidence >= min_confidence
        2. Explanation text mentions at least one identifier from the trigger event
           (prevents fully hallucinated responses that ignore the event data).

        Returns a VerifiedResult; if failed, explanation is replaced with
        a neutral fallback message.
        """
        if confidence < self._min_confidence:
            logger.info(
                "[verifier] confidence %.3f < %.3f — issuing neutral message",
                confidence, self._min_confidence,
            )
            return VerifiedResult(
                explanation=_NEUTRAL_EXPLANATION,
                confidence=confidence,
                passed=False,
            )

        if not self._mentions_trigger(explanation, trigger_event):
            logger.warning(
                "[verifier] explanation does not reference trigger identifiers — "
                "possible hallucination. confidence=%.3f", confidence,
            )
            return VerifiedResult(
                explanation=_NEUTRAL_EXPLANATION,
                confidence=confidence,
                passed=False,
            )

        return VerifiedResult(
            explanation=explanation,
            confidence=confidence,
            passed=True,
        )

    @staticmethod
    def _mentions_trigger(
        explanation: str,
        trigger_event: "events_pb2.CanonicalEvent",
    ) -> bool:
        """Return True if explanation contains at least one key identifier from
        the event. Matching is per name-token so "Jones" counts for a trigger
        about "Jon Jones" — analysts don't repeat hex market ids or full names."""
        text = explanation.lower()
        if trigger_event.HasField("market_event"):
            m = trigger_event.market_event
            # card_title is intentionally excluded — "UFC 329" appears in
            # explanations about ANY fight on the card, so it proves nothing.
            sources = [m.outcome, m.title, m.market_id]
        elif trigger_event.HasField("fight_event"):
            f = trigger_event.fight_event
            sources = [f.fighter_name, f.fight_id]
        else:
            return True  # Unknown payload — allow through

        tokens = {
            tok
            for src in sources if src
            for tok in re.split(r"[^a-z0-9']+", src.lower())
            # Skip generic short tokens ("vs", "yes", "no", "ufc" is fine to
            # count — it's on-topic) but keep real name fragments.
            if len(tok) >= 3 and tok not in _GENERIC_TOKENS
        }
        return any(tok in text for tok in tokens)
