"""
Gemini Flash inference layer.

Generates a plain-text explanation of why market odds moved,
grounded in canonical event data and retrieved evidence.

Owner: FWS
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

import google.generativeai as genai

from rag.retriever import EvidenceItem
from agents.generated import events_pb2  # type: ignore[import]

logger = logging.getLogger(__name__)

_GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
_MODEL_NAME     = "gemini-2.5-flash"

_SYSTEM_PROMPT = """\
You are a UFC betting-market analyst for AgentPredict. Your job is to explain, \
in plain language for fight fans, why a Polymarket fight market's odds are \
where they are — both in the days before a fight (line moves from news, \
weigh-ins, sharp money) and live during a fight (damage, takedowns, momentum).

Rules:
- Write 2–3 sentences maximum, referring to fighters by name.
- Base your explanation ONLY on the event data and evidence provided.
- If the data doesn't support a causal story, say the move looks like normal \
market noise or repricing — do NOT invent injuries, news, or fight action.
- End your response with a single line: CONFIDENCE: <float between 0.0 and 1.0>
"""


def describe_trigger(trigger_event: "events_pb2.CanonicalEvent") -> str:
    """Human-readable one-liner for the event that triggered this RAG cycle.
    Shared with the retriever so the query text matches what we explain."""
    if trigger_event.HasField("market_event"):
        m = trigger_event.market_event
        fight = m.title or m.outcome
        card = f" on {m.card_title}" if m.card_title else ""
        info = f" ({m.fight_info})" if m.fight_info else ""
        phase = f" [{m.phase}]" if m.phase else ""
        return (
            f"{fight}{card}{info}{phase}: '{m.outcome}' win probability moved "
            f"from {m.probability - m.delta:.1%} to {m.probability:.1%} "
            f"(delta {m.delta:+.1%})."
        )
    f = trigger_event.fight_event
    return (
        f"Live fight stat: {f.fighter_name}, {f.stat_type} = {f.value:g}"
        f"{f' in round {f.round}' if f.round else ''} (fight {f.fight_id})."
    )


@dataclass
class InferenceResult:
    explanation: str
    confidence: float
    raw_response: str


class InferenceEngine:
    """Wraps Gemini Flash to generate grounded explanations."""

    def __init__(self) -> None:
        if not _GOOGLE_API_KEY:
            raise EnvironmentError("GOOGLE_API_KEY not set")
        genai.configure(api_key=_GOOGLE_API_KEY)
        self._model = genai.GenerativeModel(
            model_name=_MODEL_NAME,
            system_instruction=_SYSTEM_PROMPT,
        )

    def explain(
        self,
        trigger_event: "events_pb2.CanonicalEvent",
        context_text: str,
        evidence: list[EvidenceItem],
    ) -> InferenceResult:
        """
        Generate an explanation for a triggering event.

        Args:
            trigger_event:  The canonical event that triggered the RAG cycle.
            context_text:   Compact serialized sliding-window context.
            evidence:       Top-k retrieved EvidenceItems from Pinecone.

        Returns:
            InferenceResult with explanation and parsed confidence.
        """
        evidence_text = "\n".join(
            f"[{i+1}] (score={e.score:.3f}) {e.text}"
            for i, e in enumerate(evidence)
        ) or "(no evidence retrieved)"

        user_prompt = f"""\
TRIGGERING EVENT:
{describe_trigger(trigger_event)}

RECENT CONTEXT (last {_CONTEXT_LABEL} events):
{context_text}

RETRIEVED EVIDENCE:
{evidence_text}

Explain why the odds moved and assign a confidence score.
"""
        response = self._model.generate_content(user_prompt)
        raw = _response_text(response)

        explanation, confidence = self._parse_response(raw)
        return InferenceResult(
            explanation=explanation,
            confidence=confidence,
            raw_response=raw,
        )

    @staticmethod
    def _parse_response(raw: str) -> tuple[str, float]:
        """
        Splits the model response into explanation text and confidence float.
        Falls back to confidence=0.0 if the CONFIDENCE line is malformed.
        """
        confidence = 0.0
        explanation = raw

        match = re.search(r"CONFIDENCE:\s*([0-9]*\.?[0-9]+)", raw, re.IGNORECASE)
        if match:
            try:
                confidence = float(match.group(1))
            except ValueError:
                confidence = 0.0
            # Models sometimes answer in percent ("CONFIDENCE: 85") — a bare
            # clamp would award that maximum confidence.
            if 1.0 < confidence <= 100.0:
                confidence /= 100.0
            confidence = max(0.0, min(1.0, confidence))
            # Strip the CONFIDENCE line from the explanation.
            explanation = raw[: match.start()].strip()

        return explanation, confidence


def _response_text(response) -> str:
    """Extract text from a Gemini response without tripping the ValueError that
    `response.text` raises on safety blocks / empty candidates."""
    candidates = getattr(response, "candidates", None) or []
    for cand in candidates:
        parts = getattr(getattr(cand, "content", None), "parts", None) or []
        text = "".join(getattr(p, "text", "") for p in parts).strip()
        if text:
            return text
    feedback = getattr(response, "prompt_feedback", None)
    raise RuntimeError(f"Gemini returned no usable text (feedback={feedback!r})")


_CONTEXT_LABEL = "20"  # matches ContextBuilder._WINDOW_SIZE
