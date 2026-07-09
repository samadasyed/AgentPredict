"""
RAG Orchestrator.

Responsibilities:
1. Subscribe to the C++ engine EventStream (as an async gRPC client).
2. For each meaningful event, run the agentic RAG loop:
   context_builder → retriever → inference → verifier → emit RagPrediction
3. Serve the RagStream gRPC service so the gateway can subscribe to predictions.

Production behavior:
* The RAG cycle (Gemini + Pinecone, all blocking SDKs) runs in a worker thread —
  the event-stream consumer keeps draining while inference is in flight.
* Single-flight with per-market cooldown: at most one cycle at a time, at most
  one explanation per market per RAG_MARKET_COOLDOWN_S. During a live fight a
  market ticks every few seconds; without this every tick is a paid API call.
* Only predictions that PASS verification are broadcast — the neutral
  "insufficient confidence" fallback is logged, not shown to users.

Owner: FWS
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from concurrent import futures
from queue import Queue, Empty
from typing import Iterator

import grpc

from rag.context_builder import ContextBuilder
from rag.inference import InferenceEngine, describe_trigger
from rag.retriever import Retriever
from rag.verifier import Verifier

from agents.generated import events_pb2, events_pb2_grpc  # type: ignore[import]

logger = logging.getLogger(__name__)

_ENGINE_GRPC_ADDRESS = os.getenv("ENGINE_GRPC_ADDRESS", "localhost:50051")
_RAG_GRPC_ADDRESS    = os.getenv("RAG_GRPC_ADDRESS", "0.0.0.0:50052")

# Minimum absolute probability delta to trigger a RAG cycle.
# Events below this are consumed by context_builder but not sent to inference.
_MEANINGFUL_DELTA_THRESHOLD = 0.02

# Schedule/discovery markers carry no analyzable change — never run inference on them
# (they're also re-emitted periodically, which would spam the model).
_SENTINEL_STATS = {"FIGHT_UPCOMING", "FIGHT_DISCOVERED"}

# One explanation per market per cooldown window — a human reads predictions,
# not a tick stream. Each skipped cycle is a saved Gemini generation.
_MARKET_COOLDOWN_S = float(os.getenv("RAG_MARKET_COOLDOWN_S", "90"))

# The Pinecone index has no TTL — cap writes so it can't grow without bound.
# Retrieval quality degrades gracefully once the hourly budget is spent.
_MAX_UPSERTS_PER_HOUR = int(os.getenv("RAG_MAX_UPSERTS_PER_HOUR", "500"))

# Client keepalive so a half-open engine connection raises instead of hanging
# the subscription forever (mirrors the gateway's channel options).
_KEEPALIVE_OPTIONS = [
    ("grpc.keepalive_time_ms", 30_000),
    ("grpc.keepalive_timeout_ms", 10_000),
    ("grpc.keepalive_permit_without_calls", 1),
    ("grpc.http2.max_pings_without_data", 0),
]


def _is_meaningful(event: "events_pb2.CanonicalEvent") -> bool:
    """Decide whether an event warrants a full RAG inference cycle."""
    if event.HasField("market_event"):
        return abs(event.market_event.delta) >= _MEANINGFUL_DELTA_THRESHOLD
    if event.HasField("fight_event"):
        # Real per-fighter stat changes are meaningful; sentinels are not.
        return event.fight_event.stat_type not in _SENTINEL_STATS
    return False


def _trigger_key(event: "events_pb2.CanonicalEvent") -> str:
    """Cooldown bucket: one per market / per fighter."""
    if event.HasField("market_event"):
        return f"mkt:{event.market_event.market_id}"
    f = event.fight_event
    return f"fight:{f.fight_id}:{f.fighter_name}"


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
        # threading.Lock — register/unregister run on gRPC thread pool workers,
        # broadcast runs on the asyncio loop thread. Both must serialize.
        self._lock = threading.Lock()

    def register_subscriber(self) -> Queue:
        q: Queue = Queue(maxsize=100)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unregister_subscriber(self, q: Queue) -> None:
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def broadcast(self, prediction: "events_pb2.RagPrediction") -> None:
        with self._lock:
            snapshot = list(self._subscribers)
        for q in snapshot:
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
            while context.is_active():
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


def _build_retriever():
    """Pinecone-backed Retriever, or an in-memory mock when MOCK_MODE=1 (no keys)."""
    if os.getenv("MOCK_MODE", "0") == "1":
        from rag.mock_components import MockRetriever
        logger.info("[orchestrator] MOCK_MODE on — using in-memory retriever (no Pinecone)")
        return MockRetriever()
    return Retriever()


def _build_inference():
    """Gemini InferenceEngine, or a templated mock when MOCK_MODE=1 (no keys)."""
    if os.getenv("MOCK_MODE", "0") == "1":
        from rag.mock_components import MockInference
        logger.info("[orchestrator] MOCK_MODE on — using templated inference (no Gemini)")
        return MockInference()
    return InferenceEngine()


class Orchestrator:
    """Wires together all RAG components and manages the event subscription loop."""

    def __init__(self) -> None:
        self._context_builder = ContextBuilder()
        self._retriever = _build_retriever()
        self._inference = _build_inference()
        self._verifier = Verifier()
        self._rag_service = RagStreamServiceImpl()
        # Single-flight: while one RAG cycle runs in its worker thread, further
        # triggers are skipped (the next meaningful tick re-triggers anyway).
        # The task reference doubles as the busy flag.
        self._cycle_task: asyncio.Task | None = None
        # trigger key → monotonic time of last completed cycle.
        self._last_cycle_at: dict[str, float] = {}
        # market_id → probability at the last explanation (or first sighting).
        # Pre-event lines drift a fraction of a point per tick — no single tick
        # crosses the threshold, but the CUMULATIVE move does. Triggering on
        # |current − ref| lets slow drifts earn an explanation too; the ref
        # resets only when a cycle actually runs, so skipped triggers (busy /
        # cooldown) keep accumulating instead of being forgotten.
        self._ref_prob: dict[str, float] = {}
        # Sliding-hour upsert budget.
        self._upsert_times: list[float] = []

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
        server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=16),
            options=[
                # Server-side keepalive: reap streams whose peer vanished, so
                # unclean gateway disconnects can't pin workers forever.
                ("grpc.keepalive_time_ms", 30_000),
                ("grpc.keepalive_timeout_ms", 10_000),
                ("grpc.http2.max_pings_without_data", 0),
            ],
        )
        events_pb2_grpc.add_RagStreamServicer_to_server(self._rag_service, server)
        server.add_insecure_port(_RAG_GRPC_ADDRESS)
        server.start()
        logger.info("[orchestrator] RagStream gRPC server on %s", _RAG_GRPC_ADDRESS)
        server.wait_for_termination()

    async def _subscribe_and_process(self) -> None:
        """Connect to engine EventStream and process events (async channel —
        the loop stays responsive while RAG cycles run in worker threads)."""
        while True:
            channel = grpc.aio.insecure_channel(_ENGINE_GRPC_ADDRESS, options=_KEEPALIVE_OPTIONS)
            try:
                stub = events_pb2_grpc.EventStreamStub(channel)
                request = events_pb2.SubscribeRequest()  # start from latest
                logger.info("[orchestrator] subscribing to engine at %s", _ENGINE_GRPC_ADDRESS)
                async for event in stub.Subscribe(request):
                    await self._handle_event(event)
            except grpc.RpcError as exc:
                logger.error("[orchestrator] engine stream error: %s — reconnecting in 5s", exc)
                await asyncio.sleep(5)
            finally:
                await channel.close()

    def _market_trigger(self, event: "events_pb2.CanonicalEvent"):
        """Cumulative-drift gate for market events.

        Returns a trigger event whose delta is the move since the last
        explanation (None if the move is still below threshold). The reference
        seeds at first sight as the pre-move price, so a big single tick
        triggers immediately, while a slow pre-event drift triggers once its
        total crosses the same threshold."""
        m = event.market_event
        ref = self._ref_prob.setdefault(m.market_id, m.probability - m.delta)
        cum = m.probability - ref
        if abs(cum) < _MEANINGFUL_DELTA_THRESHOLD:
            return None
        if abs(cum - m.delta) < 1e-12:
            return event  # per-tick delta IS the cumulative move
        trigger = events_pb2.CanonicalEvent()
        trigger.CopyFrom(event)
        trigger.market_event.delta = cum
        return trigger

    def _should_run_cycle(self, event: "events_pb2.CanonicalEvent") -> bool:
        """Cost gate: not busy + trigger key off cooldown."""
        if self._cycle_task is not None and not self._cycle_task.done():
            logger.debug("[orchestrator] cycle busy — skipping %s", event.event_id)
            return False
        key = _trigger_key(event)
        last = self._last_cycle_at.get(key, 0.0)
        if time.monotonic() - last < _MARKET_COOLDOWN_S:
            logger.debug("[orchestrator] %s on cooldown — skipping", key)
            return False
        return True

    def _upsert_budget_ok(self) -> bool:
        now = time.monotonic()
        self._upsert_times = [t for t in self._upsert_times if now - t < 3600]
        if len(self._upsert_times) >= _MAX_UPSERTS_PER_HOUR:
            return False
        self._upsert_times.append(now)
        return True

    async def _handle_event(self, event: "events_pb2.CanonicalEvent") -> None:
        """Process a single canonical event through the agentic RAG loop."""
        # Always add to context window
        self._context_builder.add(event)

        # Meaningfulness: market events pass the cumulative-drift gate (the
        # trigger's delta becomes the total move since last explanation);
        # fight events pass unless they're schedule sentinels.
        if event.HasField("market_event"):
            trigger = self._market_trigger(event)
        elif event.HasField("fight_event") and _is_meaningful(event):
            trigger = event
        else:
            trigger = None
        if trigger is None or not self._should_run_cycle(trigger):
            return

        logger.debug("[orchestrator] meaningful event %s — running RAG", event.event_id)
        # Fire-and-forget: the stream consumer keeps draining (context stays
        # fresh) while the blocking SDK calls run in a worker thread. The task
        # reference is the single-flight guard checked by _should_run_cycle.
        self._cycle_task = asyncio.create_task(self._cycle_wrapper(trigger))

    async def _cycle_wrapper(self, event: "events_pb2.CanonicalEvent") -> None:
        try:
            prediction = await asyncio.to_thread(self._run_cycle, event)
            if prediction is not None:
                self._rag_service.broadcast(prediction)
        except Exception as exc:
            logger.exception("[orchestrator] RAG cycle failed for %s: %s", event.event_id, exc)
        finally:
            self._last_cycle_at[_trigger_key(event)] = time.monotonic()
            if event.HasField("market_event"):
                # Drift accumulates from the price we just explained.
                m = event.market_event
                self._ref_prob[m.market_id] = m.probability

    def _run_cycle(self, event: "events_pb2.CanonicalEvent") -> "events_pb2.RagPrediction | None":
        """One full RAG cycle (blocking; called via to_thread)."""
        # 1. Build context string
        context_text = self._context_builder.build_context()

        # 2. Retrieve evidence — query with the full trigger description
        # (fight, card, outcome, move) so results are about THIS fight, not
        # whichever market shares a bare stat keyword.
        query = describe_trigger(event)
        evidence = self._retriever.retrieve(query_text=query)

        # 3. Upsert event for future retrieval (budgeted)
        if self._upsert_budget_ok():
            self._retriever.upsert(event)
        else:
            logger.warning("[orchestrator] hourly upsert budget spent — skipping upsert")

        # 4. Inference
        result = self._inference.explain(event, context_text, evidence)

        # 5. Verify — only predictions that PASS reach users
        verified = self._verifier.verify(result.explanation, result.confidence, event)
        if not verified.passed:
            logger.info(
                "[orchestrator] prediction for %s failed verification (confidence=%.3f) — not broadcast",
                event.event_id, verified.confidence,
            )
            return None

        # 6. Build the RagPrediction
        prediction = _build_rag_prediction(
            explanation=verified.explanation,
            confidence=verified.confidence,
            evidence=evidence,
            trigger_event=event,
        )
        logger.info(
            "[orchestrator] prediction emitted for %s (confidence=%.3f)",
            event.event_id, verified.confidence,
        )
        return prediction


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    orchestrator = Orchestrator()
    await orchestrator.run()


if __name__ == "__main__":
    asyncio.run(main())
