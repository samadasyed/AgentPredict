"""
RAG Orchestrator.

Responsibilities:
1. Subscribe to the C++ engine EventStream (as a gRPC client).
2. For each meaningful event, run the agentic RAG loop:
   context_builder → retriever → inference → verifier → emit RagPrediction
3. Serve the RagStream gRPC service so the gateway can subscribe to predictions.

Owner: FWS
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from concurrent import futures
from queue import Queue, Empty
from typing import Iterator

import grpc

from rag.context_builder import ContextBuilder
from rag.inference import InferenceEngine
from rag.retriever import Retriever
from rag.verifier import Verifier

from agents.generated import events_pb2, events_pb2_grpc  # type: ignore[import]

logger = logging.getLogger(__name__)

_ENGINE_GRPC_ADDRESS = os.getenv("ENGINE_GRPC_ADDRESS", "localhost:50051")
_RAG_GRPC_ADDRESS    = os.getenv("RAG_GRPC_ADDRESS", "0.0.0.0:50052")

# Minimum absolute probability delta to trigger a RAG cycle.
# Events below this are consumed by context_builder but not sent to inference.
_MEANINGFUL_DELTA_THRESHOLD = 0.02


def _is_meaningful(event: "events_pb2.CanonicalEvent") -> bool:
    """Decide whether an event warrants a full RAG inference cycle."""
    if event.HasField("market_event"):
        return abs(event.market_event.delta) >= _MEANINGFUL_DELTA_THRESHOLD
    if event.HasField("fight_event"):
        # All fight stat events are considered meaningful (they're rare on free tier).
        return True
    return False


def _build_rag_prediction(
    explanation: str,
    confidence: float,
    evidence: list,
    trigger_event: "events_pb2.CanonicalEvent",
) -> "events_pb2.RagPrediction":
    pred = events_pb2.RagPrediction()
    pred.explanation = explanation
    pred.confidence = confidence
    pred.timestamp = int(time.time() * 1000)
    pred.trigger_event_id = trigger_event.event_id

    for item in evidence:
        ev_item = pred.evidence.add()
        ev_item.text = item.text
        ev_item.source_ref = item.source_ref
        ev_item.score = item.score

    return pred


# ─── RagStream gRPC service impl ─────────────────────────────────────────────

class RagStreamServiceImpl(events_pb2_grpc.RagStreamServicer):
    """
    gRPC server — gateway subscribes here for a stream of RagPredictions.
    Predictions are fanned out to all active subscriber queues.
    """

    def __init__(self) -> None:
        self._subscribers: list[Queue] = []
        self._lock = asyncio.Lock()  # NOTE: used from sync context via run_coroutine_threadsafe

    def register_subscriber(self) -> Queue:
        q: Queue = Queue(maxsize=100)
        self._subscribers.append(q)
        return q

    def unregister_subscriber(self, q: Queue) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    def broadcast(self, prediction: "events_pb2.RagPrediction") -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(prediction)
            except Exception:
                pass  # Full queue — drop for this subscriber

    def SubscribePredictions(
        self,
        request: "events_pb2.RagSubscribeRequest",
        context: grpc.ServicerContext,
    ) -> Iterator["events_pb2.RagPrediction"]:
        q = self.register_subscriber()
        try:
            while not context.is_active() is False:
                try:
                    pred = q.get(timeout=1.0)
                    if pred.confidence >= request.min_confidence:
                        yield pred
                except Empty:
                    continue
                except Exception:
                    break
        finally:
            self.unregister_subscriber(q)


# ─── Main orchestrator ────────────────────────────────────────────────────────

class Orchestrator:
    """Wires together all RAG components and manages the event subscription loop."""

    def __init__(self) -> None:
        self._context_builder = ContextBuilder()
        self._retriever = Retriever()
        self._inference = InferenceEngine()
        self._verifier = Verifier()
        self._rag_service = RagStreamServiceImpl()

    async def run(self) -> None:
        """
        Start the RAG gRPC server and subscribe to the engine EventStream.
        Both run concurrently.
        """
        grpc_server_task = asyncio.get_event_loop().run_in_executor(
            None, self._start_grpc_server
        )
        event_loop_task = asyncio.create_task(self._subscribe_and_process())

        logger.info("[orchestrator] started")
        await asyncio.gather(grpc_server_task, event_loop_task)

    def _start_grpc_server(self) -> None:
        """Blocking — runs gRPC server in a thread pool."""
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        events_pb2_grpc.add_RagStreamServicer_to_server(self._rag_service, server)
        server.add_insecure_port(_RAG_GRPC_ADDRESS)
        server.start()
        logger.info("[orchestrator] RagStream gRPC server on %s", _RAG_GRPC_ADDRESS)
        server.wait_for_termination()

    async def _subscribe_and_process(self) -> None:
        """Connect to engine EventStream and process events."""
        channel = grpc.insecure_channel(_ENGINE_GRPC_ADDRESS)
        stub = events_pb2_grpc.EventStreamStub(channel)

        request = events_pb2.SubscribeRequest()  # start from latest
        logger.info("[orchestrator] subscribing to engine at %s", _ENGINE_GRPC_ADDRESS)

        while True:
            try:
                for event in stub.Subscribe(request):
                    await self._handle_event(event)
            except grpc.RpcError as exc:
                logger.error("[orchestrator] engine stream error: %s — reconnecting in 5s", exc)
                await asyncio.sleep(5)

    async def _handle_event(self, event: "events_pb2.CanonicalEvent") -> None:
        """Process a single canonical event through the agentic RAG loop."""
        # Always add to context window
        self._context_builder.add(event)

        if not _is_meaningful(event):
            return

        logger.debug("[orchestrator] meaningful event %s — running RAG", event.event_id)

        try:
            # 1. Build context string
            context_text = self._context_builder.build_context()

            # 2. Retrieve evidence
            query = (
                event.market_event.outcome if event.HasField("market_event")
                else event.fight_event.stat_type
            )
            evidence = self._retriever.retrieve(query_text=query)

            # 3. Upsert event for future retrieval
            self._retriever.upsert(event)

            # 4. Inference
            result = self._inference.explain(event, context_text, evidence)

            # 5. Verify
            verified = self._verifier.verify(result.explanation, result.confidence, event)

            # 6. Build and broadcast RagPrediction
            prediction = _build_rag_prediction(
                explanation=verified.explanation,
                confidence=verified.confidence,
                evidence=evidence,
                trigger_event=event,
            )
            self._rag_service.broadcast(prediction)

            logger.info(
                "[orchestrator] prediction emitted for %s (confidence=%.3f passed=%s)",
                event.event_id, verified.confidence, verified.passed,
            )

        except Exception as exc:
            logger.exception("[orchestrator] RAG cycle failed for %s: %s", event.event_id, exc)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    orchestrator = Orchestrator()
    await orchestrator.run()


if __name__ == "__main__":
    asyncio.run(main())
