"""
Pinecone retriever with Gemini text-embedding-004 embeddings.

Namespaces:
  - "market_events"  for Polymarket CanonicalEvents
  - "fight_events"   for MMA CanonicalEvents

Owner: FWS
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import google.generativeai as genai
from pinecone import Pinecone, ServerlessSpec

from agents.generated import events_pb2  # type: ignore[import]

logger = logging.getLogger(__name__)

_PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
_PINECONE_INDEX  = os.getenv("PINECONE_INDEX_NAME", "agentpredict")
_GOOGLE_API_KEY  = os.getenv("GOOGLE_API_KEY", "")
_EMBEDDING_MODEL = "models/text-embedding-004"
_EMBEDDING_DIM   = 768  # text-embedding-004 output dimension
_TOP_K           = 5


@dataclass
class EvidenceItem:
    text: str
    source_ref: str  # e.g. "market_events/evt-uuid"
    score: float


def _event_to_text(event: "events_pb2.CanonicalEvent") -> str:
    """Convert a canonical event to a searchable text string for embedding."""
    if event.HasField("market_event"):
        m = event.market_event
        return (
            f"Polymarket: market {m.market_id} outcome '{m.outcome}' "
            f"probability {m.probability:.4f} delta {m.delta:+.4f}"
        )
    elif event.HasField("fight_event"):
        f = event.fight_event
        return (
            f"MMA: fight {f.fight_id} fighter '{f.fighter_name}' "
            f"stat {f.stat_type} value {f.value} round {f.round}"
        )
    return f"Event {event.event_id} source {event.source}"


class Retriever:
    """Pinecone-backed vector store for canonical events."""

    def __init__(self) -> None:
        if not _PINECONE_API_KEY:
            raise EnvironmentError("PINECONE_API_KEY not set")
        if not _GOOGLE_API_KEY:
            raise EnvironmentError("GOOGLE_API_KEY not set")

        genai.configure(api_key=_GOOGLE_API_KEY)

        self._pc = Pinecone(api_key=_PINECONE_API_KEY)
        self._index = self._get_or_create_index()

    def _get_or_create_index(self):
        existing = [idx.name for idx in self._pc.list_indexes()]
        if _PINECONE_INDEX not in existing:
            logger.info("[retriever] creating Pinecone index '%s'", _PINECONE_INDEX)
            self._pc.create_index(
                name=_PINECONE_INDEX,
                dimension=_EMBEDDING_DIM,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
        return self._pc.Index(_PINECONE_INDEX)

    def _embed(self, text: str) -> list[float]:
        result = genai.embed_content(
            model=_EMBEDDING_MODEL,
            content=text,
            task_type="retrieval_document",
        )
        return result["embedding"]

    def upsert(self, event: "events_pb2.CanonicalEvent") -> None:
        """
        Embed and upsert a canonical event into Pinecone.
        Called on every meaningful event to grow the knowledge base over time.
        """
        namespace = (
            "market_events" if event.HasField("market_event") else "fight_events"
        )
        text = _event_to_text(event)
        vector = self._embed(text)

        self._index.upsert(
            vectors=[{"id": event.event_id, "values": vector, "metadata": {"text": text}}],
            namespace=namespace,
        )
        logger.debug("[retriever] upserted %s into %s", event.event_id, namespace)

    def retrieve(
        self,
        query_text: str,
        namespace: Optional[str] = None,
        top_k: int = _TOP_K,
    ) -> list[EvidenceItem]:
        """
        Retrieve the top-k most similar events.

        Args:
            query_text: Natural language query (e.g. a CanonicalEvent description).
            namespace:  "market_events" | "fight_events" | None (searches both).
            top_k:      Number of results.

        Returns:
            List of EvidenceItem sorted by score descending.
        """
        query_vector = self._embed(query_text)
        namespaces = [namespace] if namespace else ["market_events", "fight_events"]

        all_results: list[EvidenceItem] = []
        for ns in namespaces:
            response = self._index.query(
                vector=query_vector,
                top_k=top_k,
                namespace=ns,
                include_metadata=True,
            )
            for match in response.matches:
                all_results.append(EvidenceItem(
                    text=match.metadata.get("text", ""),
                    source_ref=f"{ns}/{match.id}",
                    score=match.score,
                ))

        all_results.sort(key=lambda x: x.score, reverse=True)
        return all_results[:top_k]
