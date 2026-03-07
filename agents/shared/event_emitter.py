"""
gRPC client that sends CanonicalEvents to the C++ engine.

Single shared channel; instantiate once per agent process.
Reconnects automatically via gRPC channel resilience.
"""

from __future__ import annotations

import logging
import os
from typing import Iterable

import grpc

# Generated proto stubs — created by `protoc` from proto/events.proto.
# Run: python -m grpc_tools.protoc -I../../proto --python_out=. --grpc_python_out=. events.proto
# TODO: wire up codegen in Makefile / docker build step.
from agents.generated import events_pb2, events_pb2_grpc  # type: ignore[import]

logger = logging.getLogger(__name__)

_DEFAULT_ADDRESS = os.getenv("ENGINE_GRPC_ADDRESS", "localhost:50051")


class EventEmitter:
    """Thread-safe gRPC client wrapper for EventIngestion service."""

    def __init__(self, address: str = _DEFAULT_ADDRESS) -> None:
        self._address = address
        # Single channel reused across all calls.
        # gRPC channels are thread-safe and handle reconnection internally.
        self._channel = grpc.insecure_channel(
            address,
            options=[
                ("grpc.keepalive_time_ms", 10_000),
                ("grpc.keepalive_timeout_ms", 5_000),
                ("grpc.keepalive_permit_without_calls", True),
            ],
        )
        self._stub = events_pb2_grpc.EventIngestionStub(self._channel)
        logger.info("[emitter] connected to engine at %s", address)

    def emit(self, event: "events_pb2.CanonicalEvent") -> bool:
        """
        Send a single event. Returns True if engine accepted it.
        Logs and returns False on gRPC error (non-fatal — agent continues).
        """
        try:
            ack = self._stub.IngestEvent(event, timeout=5.0)
            if not ack.accepted:
                logger.warning(
                    "[emitter] engine rejected event %s: %s",
                    ack.event_id, ack.reason,
                )
            return ack.accepted
        except grpc.RpcError as exc:
            logger.error("[emitter] gRPC error emitting event: %s", exc)
            return False

    def emit_stream(self, events: Iterable["events_pb2.CanonicalEvent"]) -> bool:
        """
        Send a batch of events as a client-side stream.
        Returns True if engine acknowledged the whole stream.
        """
        try:
            ack = self._stub.IngestStream(iter(events), timeout=30.0)
            return ack.accepted
        except grpc.RpcError as exc:
            logger.error("[emitter] gRPC stream error: %s", exc)
            return False

    def close(self) -> None:
        self._channel.close()

    def __enter__(self) -> "EventEmitter":
        return self

    def __exit__(self, *_) -> None:
        self.close()
