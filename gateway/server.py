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
        # Keep the connection alive; browser sends pings, we pong via FastAPI.
        while True:
            # Wait for any client message (ping / close frame).
            data = await ws.receive_text()
            # TODO: handle client-side filter messages (e.g. {"action": "filter", "source": "pm"})
            logger.debug("[gateway] received from client: %s", data)
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.disconnect(ws)
