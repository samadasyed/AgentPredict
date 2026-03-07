"""
WebSocket broadcaster — fan-out messages to all connected browser clients.

Thread-safe via asyncio.Lock.
TODO: buffer last 50 events for late-joining clients.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

_BUFFER_SIZE = 50  # TODO: implement replay buffer for late-joining clients


class Broadcaster:
    """Manages the set of active WebSocket connections and fans out messages."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        """Register a new WebSocket client after it has been accepted."""
        async with self._lock:
            self._clients.add(ws)
        logger.info("[broadcaster] client connected — total=%d", len(self._clients))

    async def disconnect(self, ws: WebSocket) -> None:
        """Unregister a WebSocket client."""
        async with self._lock:
            self._clients.discard(ws)
        logger.info("[broadcaster] client disconnected — total=%d", len(self._clients))

    async def broadcast(self, message: dict[str, Any]) -> None:
        """
        Send a JSON-encoded message to all connected clients.
        Clients that fail to receive are silently removed.
        """
        payload = json.dumps(message)
        async with self._lock:
            dead: list[WebSocket] = []
            for ws in self._clients:
                try:
                    await ws.send_text(payload)
                except Exception as exc:
                    logger.debug("[broadcaster] send failed (%s) — dropping client", exc)
                    dead.append(ws)
            for ws in dead:
                self._clients.discard(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)
