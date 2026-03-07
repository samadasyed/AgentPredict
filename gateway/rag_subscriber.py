"""
gRPC client that subscribes to the Python RAG RagStream service.
Converts RagPrediction proto → JSON-serializable dict and pushes to Broadcaster.
"""

from __future__ import annotations

import asyncio
import logging
import os

import grpc
from google.protobuf.json_format import MessageToDict

from gateway.broadcaster import Broadcaster
from agents.generated import events_pb2, events_pb2_grpc  # type: ignore[import]

logger = logging.getLogger(__name__)

_RAG_GRPC_ADDRESS = os.getenv("RAG_GRPC_ADDRESS", "localhost:50052")


class RagSubscriber:
    """Reads from the RAG RagStream and fans predictions to the broadcaster."""

    def __init__(self, broadcaster: Broadcaster, min_confidence: float = 0.0) -> None:
        self._broadcaster = broadcaster
        self._min_confidence = min_confidence
        self._running = False

    async def run(self) -> None:
        """Connect to RAG orchestrator, stream predictions, broadcast. Reconnects on error."""
        self._running = True
        logger.info("[rag-sub] connecting to RAG at %s", _RAG_GRPC_ADDRESS)

        while self._running:
            try:
                await self._stream_predictions()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[rag-sub] stream error: %s — reconnecting in 5s", exc)
                await asyncio.sleep(5)

    async def _stream_predictions(self) -> None:
        channel = grpc.aio.insecure_channel(_RAG_GRPC_ADDRESS)
        try:
            stub = events_pb2_grpc.RagStreamStub(channel)
            request = events_pb2.RagSubscribeRequest(min_confidence=self._min_confidence)

            async for prediction in stub.SubscribePredictions(request):
                data = MessageToDict(
                    prediction,
                    preserving_proto_field_name=True,
                    including_default_value_fields=True,
                )
                await self._broadcaster.broadcast({"type": "prediction", "data": data})
        finally:
            await channel.close()

    def stop(self) -> None:
        self._running = False
