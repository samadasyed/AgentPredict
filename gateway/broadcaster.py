"""
WebSocket broadcaster — fan-out messages to all connected browser clients.

Responsibilities:
  * Track the set of active WebSocket connections (thread-safe via asyncio.Lock).
  * Keep a bounded replay buffer of the most recent events and predictions so a
    client that connects (or reconnects) mid-stream immediately sees recent
    history instead of a blank screen.
  * Optionally narrow a client's Stream-1 (factual events) feed to a single
    source via a {"action": "filter", "source": ...} control message. Stream-2
    predictions carry no source and are always delivered.

Exactly-once on connect: the buffer snapshot and client registration happen in a
single critical section that is mutually exclusive with broadcast()'s
"append-to-buffer + snapshot-targets" critical section. So every buffered message
reaches a connecting client exactly once — via replay if it predates
registration, or live if it arrives afterwards. Replay sends happen OUTSIDE the
lock so a slow newcomer cannot stall live fan-out to existing clients. (The only
relaxation is ordering: a live message may interleave with the tail of a replay;
events and predictions render in separate columns and the UI keys predictions to
events by trigger_event_id, so this is cosmetic and self-correcting.)

Owner: Samad
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Per-stream replay depth (events and predictions buffered separately). Sized so
# a full fight slate (dozens of market baselines) survives the periodic
# FIGHT_UPCOMING/baseline re-emits between a client's connect and the next
# re-baseline cycle. Matches the dashboard's own event cap.
_BUFFER_SIZE = 200
_SEND_TIMEOUT_S = 5.0  # bound a single send so one stalled socket can't hang replay/fan-out

# Map client-supplied filter values to the canonical EventSource names emitted by
# MessageToDict(preserving_proto_field_name=True). Unknown values fall through to
# None (= no filter), i.e. "show everything", which is the safe default.
_SOURCE_ALIASES = {
    "pm": "SOURCE_POLYMARKET",
    "polymarket": "SOURCE_POLYMARKET",
    "source_polymarket": "SOURCE_POLYMARKET",
    "mma": "SOURCE_MMA",
    "source_mma": "SOURCE_MMA",
}

# Event sources that bypass per-client filtering (always delivered): unclassified
# events should never be silently dropped just because a client picked a filter.
_UNCLASSIFIED = (None, "SOURCE_UNKNOWN")


def _normalize_source(value: str | None) -> str | None:
    """Resolve a client filter value to a canonical source name, or None for 'all'."""
    if not value:
        return None
    key = value.strip().lower()
    if key in ("all", "any", "*", ""):
        return None
    return _SOURCE_ALIASES.get(key)  # unrecognized -> None (no filter)


@dataclass
class _ClientState:
    # None means "deliver all event sources"; otherwise a canonical EventSource name.
    source_filter: str | None = None


class Broadcaster:
    """Manages active WebSocket connections, replay buffers, and message fan-out."""

    def __init__(self) -> None:
        self._clients: dict[WebSocket, _ClientState] = {}
        self._lock = asyncio.Lock()
        self._event_buffer: deque[dict[str, Any]] = deque(maxlen=_BUFFER_SIZE)
        self._prediction_buffer: deque[dict[str, Any]] = deque(maxlen=_BUFFER_SIZE)

    async def connect(self, ws: WebSocket) -> None:
        """Register an (already-accepted) client and replay recent history to it."""
        async with self._lock:
            # Snapshot + register atomically w.r.t. broadcast() for exactly-once.
            snapshot = list(self._event_buffer) + list(self._prediction_buffer)
            self._clients[ws] = _ClientState()
        logger.info(
            "[broadcaster] client connected — total=%d, replaying=%d",
            len(self._clients), len(snapshot),
        )
        # Replay outside the lock so a slow client can't block live fan-out.
        for message in snapshot:
            if not await self._safe_send(ws, message):
                await self.disconnect(ws)
                await self._safe_close(ws)
                return

    async def disconnect(self, ws: WebSocket) -> None:
        """Unregister a WebSocket client (idempotent)."""
        async with self._lock:
            self._clients.pop(ws, None)
        logger.info("[broadcaster] client disconnected — total=%d", len(self._clients))

    async def set_filter(self, ws: WebSocket, source: str | None) -> None:
        """Apply a per-client Stream-1 source filter from a client control message."""
        normalized = _normalize_source(source)
        async with self._lock:
            state = self._clients.get(ws)
            if state is not None:
                state.source_filter = normalized
        logger.debug("[broadcaster] filter for client set: %r -> %r", source, normalized)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Buffer the message for replay and fan it out to matching clients.

        Serialization happens once per message (not per client), and sends run
        concurrently — one slow client costs at most _SEND_TIMEOUT_S total, not
        _SEND_TIMEOUT_S × position-in-list for everyone behind it."""
        async with self._lock:
            # Buffering and target snapshot share broadcast()'s critical section so
            # they are atomic relative to connect()'s snapshot+register (exactly-once).
            self._buffer(message)
            targets = list(self._clients.items())

        text = json.dumps(message)
        matching = [ws for ws, state in targets if _matches(state, message)]
        results = await asyncio.gather(
            *(self._safe_send_text(ws, text) for ws in matching))
        dead = [ws for ws, ok in zip(matching, results) if not ok]

        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.pop(ws, None)
            for ws in dead:
                await self._safe_close(ws)

    def _buffer(self, message: dict[str, Any]) -> None:
        msg_type = message.get("type")
        if msg_type == "event":
            self._event_buffer.append(message)
        elif msg_type == "prediction":
            self._prediction_buffer.append(message)

    async def _safe_send(self, ws: WebSocket, message: dict[str, Any]) -> bool:
        """Send one message; return False (instead of raising) if the client is dead."""
        return await self._safe_send_text(ws, json.dumps(message))

    async def _safe_send_text(self, ws: WebSocket, text: str) -> bool:
        try:
            await asyncio.wait_for(ws.send_text(text), timeout=_SEND_TIMEOUT_S)
            return True
        except Exception as exc:  # noqa: BLE001 — any send failure means "drop client"
            logger.debug("[broadcaster] send failed (%s) — dropping client", exc)
            return False

    @staticmethod
    async def _safe_close(ws: WebSocket) -> None:
        """Actively close a dropped socket so the browser sees the disconnect
        (and reconnects) instead of holding a silently frozen connection."""
        try:
            await asyncio.wait_for(ws.close(code=1011), timeout=1.0)
        except Exception:  # noqa: BLE001 — already gone is fine
            pass

    @property
    def client_count(self) -> int:
        return len(self._clients)


def _matches(state: _ClientState, message: dict[str, Any]) -> bool:
    """True if `message` should be delivered to a client in `state`."""
    if message.get("type") != "event":
        return True  # predictions (and any non-event) bypass the source filter
    if state.source_filter is None:
        return True
    source = message.get("data", {}).get("source")
    # Deliver matching source, plus unclassified events (never silently drop them).
    return source in _UNCLASSIFIED or source == state.source_filter
