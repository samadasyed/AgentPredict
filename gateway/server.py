"""
FastAPI WebSocket gateway.

Endpoints:
  GET  /health  — liveness check
  WS   /ws      — browser WebSocket connection

On startup: starts EngineSubscriber and RagSubscriber as async background tasks.
WS messages are JSON envelopes:
  {"type": "event",      "data": {...}}   — factual stream (Stream 1)
  {"type": "prediction", "data": {...}}   — RAG predictions (Stream 2)

Owner: Samad
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from gateway.broadcaster import Broadcaster
from gateway.engine_subscriber import EngineSubscriber
from gateway.rag_subscriber import RagSubscriber

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

broadcaster = Broadcaster()
engine_sub = EngineSubscriber(broadcaster)
rag_sub = RagSubscriber(broadcaster)

_background_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background gRPC subscriber tasks on startup; cancel on shutdown."""
    engine_task = asyncio.create_task(engine_sub.run(), name="engine-subscriber")
    rag_task = asyncio.create_task(rag_sub.run(), name="rag-subscriber")
    _background_tasks.extend([engine_task, rag_task])
    logger.info("[gateway] background subscribers started")

    yield

    # Shutdown
    logger.info("[gateway] shutting down subscribers")
    for task in _background_tasks:
        task.cancel()
    await asyncio.gather(*_background_tasks, return_exceptions=True)


app = FastAPI(title="AgentPredict Gateway", lifespan=lifespan)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "ws_clients": broadcaster.client_count,
    })


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    await broadcaster.connect(ws)
    try:
        # Keep the connection alive and handle client control messages.
        while True:
            raw = await ws.receive_text()
            await _handle_client_message(ws, raw)
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.disconnect(ws)


async def _handle_client_message(ws: WebSocket, raw: str) -> None:
    """Apply a client control frame; ignore pings / malformed input without dropping the socket.

    Supported:
      {"action": "filter", "source": "pm" | "polymarket" | "mma" | "all"}
        — narrow this client's Stream-1 events to one source ("all" clears it).
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        logger.debug("[gateway] ignoring non-JSON client frame: %.80s", raw)
        return
    # json.loads accepts bare numbers/strings/arrays too — guard before .get().
    if isinstance(data, dict) and data.get("action") == "filter":
        await broadcaster.set_filter(ws, data.get("source"))
    else:
        logger.debug("[gateway] unhandled client message: %.80s", raw)
