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
_MODEL_NAME     = "gemini-1.5-flash"

_SYSTEM_PROMPT = """\
You are a live UFC / Polymarket trading analyst. Your job is to explain, \
in plain language, why betting market odds have shifted during a live UFC fight.

Rules:
- Write 2–3 sentences maximum.
- Base your explanation ONLY on the event data and evidence provided.
- Do NOT speculate beyond the data.
- End your response with a single line: CONFIDENCE: <float between 0.0 and 1.0>
"""


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

        # Describe the triggering event
        if trigger_event.HasField("market_event"):
            m = trigger_event.market_event
            trigger_desc = (
                f"Market '{m.market_id}' outcome '{m.outcome}' moved from "
                f"{m.probability - m.delta:.4f} to {m.probability:.4f} "
                f"(delta {m.delta:+.4f})."
            )
        else:
            f = trigger_event.fight_event
            trigger_desc = (
                f"Fight stat: fight {f.fight_id}, fighter '{f.fighter_name}', "
                f"{f.stat_type} = {f.value} in round {f.round}."
            )

        user_prompt = f"""\
TRIGGERING EVENT:
{trigger_desc}

RECENT CONTEXT (last {_CONTEXT_LABEL} events):
{context_text}

RETRIEVED EVIDENCE:
{evidence_text}

Explain why the odds moved and assign a confidence score.
"""
        response = self._model.generate_content(user_prompt)
        raw = response.text.strip()

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
                confidence = max(0.0, min(1.0, confidence))
            except ValueError:
                pass
            # Strip the CONFIDENCE line from the explanation.
            explanation = raw[: match.start()].strip()

        return explanation, confidence


_CONTEXT_LABEL = "20"  # matches ContextBuilder._WINDOW_SIZE
