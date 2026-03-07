"""
Confidence verifier and explanation sanity-checker.

- If confidence < MIN_CONFIDENCE, returns a neutral fallback message.
- Checks that the explanation mentions the triggering market_id or fighter_name
  to catch hallucinations that ignore the actual event.

Owner: FWS
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from agents.generated import events_pb2  # type: ignore[import]

logger = logging.getLogger(__name__)

MIN_CONFIDENCE: float = 0.5

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
        """Return True if explanation contains at least one key identifier from the event."""
        text = explanation.lower()
        if trigger_event.HasField("market_event"):
            m = trigger_event.market_event
            identifiers = [m.market_id.lower(), m.outcome.lower()]
        elif trigger_event.HasField("fight_event"):
            f = trigger_event.fight_event
            identifiers = [f.fight_id.lower(), f.fighter_name.lower()]
        else:
            return True  # Unknown payload — allow through

        return any(ident in text for ident in identifiers if ident)
