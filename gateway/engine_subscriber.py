"""
gRPC client that subscribes to the C++ engine EventStream.
Converts proto messages → JSON-serializable dicts and pushes to Broadcaster.
"""

from __future__ import annotations

import asyncio
import logging
import os

import grpc

from gateway.broadcaster import Broadcaster
from gateway.grpc_health import KEEPALIVE_CHANNEL_OPTIONS, SubscriberHealth
from gateway.proto_utils import to_dict
from agents.generated import events_pb2, events_pb2_grpc  # type: ignore[import]

logger = logging.getLogger(__name__)

_ENGINE_GRPC_ADDRESS = os.getenv("ENGINE_GRPC_ADDRESS", "localhost:50051")


class EngineSubscriber:
    """Reads from the engine's EventStream and fans events to the broadcaster."""

    def __init__(self, broadcaster: Broadcaster) -> None:
        self._broadcaster = broadcaster
        self._running = False
        self.health = SubscriberHealth()

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
                self.health.on_error(exc)
                logger.error("[engine-sub] stream error: %s — reconnecting in 5s", exc)
                await asyncio.sleep(5)

    async def _stream_events(self) -> None:
        channel = grpc.aio.insecure_channel(
            _ENGINE_GRPC_ADDRESS, options=KEEPALIVE_CHANNEL_OPTIONS)
        try:
            stub = events_pb2_grpc.EventStreamStub(channel)
            # Subscribe at the live tail (empty cursor). We intentionally do NOT
            # resume with cursor="0" on reconnect: that would re-replay the engine's
            # whole retained ring to every browser on each blip. The broadcaster's
            # own replay buffer covers fresh browser connects, and clients dedup on
            # event_id. (Engine-level gap-free resume needs a per-event sequence.)
            request = events_pb2.SubscribeRequest()

            self.health.on_connect()
            async for event in stub.Subscribe(request):
                self.health.on_message()
                data = to_dict(event)
                await self._broadcaster.broadcast({"type": "event", "data": data})
        finally:
            await channel.close()

    def stop(self) -> None:
        self._running = False
