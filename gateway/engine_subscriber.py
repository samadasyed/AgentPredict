"""
gRPC client that subscribes to the C++ engine EventStream.
Converts proto messages → JSON-serializable dicts and pushes to Broadcaster.
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

_ENGINE_GRPC_ADDRESS = os.getenv("ENGINE_GRPC_ADDRESS", "localhost:50051")


class EngineSubscriber:
    """Reads from the engine's EventStream and fans events to the broadcaster."""

    def __init__(self, broadcaster: Broadcaster) -> None:
        self._broadcaster = broadcaster
        self._running = False

    async def run(self) -> None:
        """Connect to engine, stream events, and broadcast. Reconnects on error."""
        self._running = True
        logger.info("[engine-sub] connecting to engine at %s", _ENGINE_GRPC_ADDRESS)

        while self._running:
            try:
                await self._stream_events()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("[engine-sub] stream error: %s — reconnecting in 5s", exc)
                await asyncio.sleep(5)

    async def _stream_events(self) -> None:
        channel = grpc.aio.insecure_channel(_ENGINE_GRPC_ADDRESS)
        try:
            stub = events_pb2_grpc.EventStreamStub(channel)
            request = events_pb2.SubscribeRequest()

            async for event in stub.Subscribe(request):
                data = MessageToDict(
                    event,
                    preserving_proto_field_name=True,
                    including_default_value_fields=True,
                )
                await self._broadcaster.broadcast({"type": "event", "data": data})
        finally:
            await channel.close()

    def stop(self) -> None:
        self._running = False
