"""
FastAPI WebSocket gateway.

Endpoints:
  GET  /health  — data-plane health: 200 only while both gRPC subscribers are
                  actually connected (and the engine stream is not silent);
                  503 "degraded" otherwise. An unconditional 200 once masked a
                  completely dead feed for days — never again.
  WS   /ws      — browser WebSocket connection (origin-checked, capped).

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
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from gateway.broadcaster import Broadcaster
from gateway.engine_subscriber import EngineSubscriber
from gateway.rag_subscriber import RagSubscriber

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Browser origins allowed to open /ws (comma-separated). Empty = allow any —
# fine for local dev; PRODUCTION MUST SET THIS (same-origin policy does NOT
# stop cross-site WebSockets, and CORSMiddleware doesn't apply to WS handshakes).
_ALLOWED_ORIGINS = {
    o.strip().rstrip("/").lower()
    for o in os.getenv("GATEWAY_ALLOWED_ORIGINS", "").split(",") if o.strip()
}
# Hard cap on concurrent WS clients — each costs a replay + a fan-out slot.
_MAX_WS_CLIENTS = int(os.getenv("GATEWAY_MAX_WS_CLIENTS", "200"))
# Engine events flow at least every agent poll interval (~30s in real mode:
# MMA re-emits upcoming cards each cycle). Longer silence while "connected"
# means the stream is wedged — report degraded so monitors see it.
_ENGINE_SILENCE_S = float(os.getenv("GATEWAY_ENGINE_SILENCE_S", "180"))

broadcaster = Broadcaster()
engine_sub = EngineSubscriber(broadcaster)
rag_sub = RagSubscriber(broadcaster)

_background_tasks: list[asyncio.Task] = []


def _task_watchdog(task: asyncio.Task) -> None:
    """A subscriber task must never finish — if it does, scream in the logs."""
    if task.cancelled():
        return
    exc = task.exception()
    logger.critical("[gateway] background task %s EXITED (%s) — data plane down",
                    task.get_name(), exc or "no exception")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background gRPC subscriber tasks on startup; cancel on shutdown."""
    engine_task = asyncio.create_task(engine_sub.run(), name="engine-subscriber")
    rag_task = asyncio.create_task(rag_sub.run(), name="rag-subscriber")
    for t in (engine_task, rag_task):
        t.add_done_callback(_task_watchdog)
    # Replace (not extend): a restarted lifespan must not try to cancel tasks
    # from a previous event loop.
    _background_tasks[:] = [engine_task, rag_task]
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
    engine = engine_sub.health
    rag = rag_sub.health

    problems: list[str] = []
    if not engine.connected:
        problems.append("engine subscriber disconnected")
    elif engine.seconds_since_message() > _ENGINE_SILENCE_S:
        problems.append(f"engine stream silent > {_ENGINE_SILENCE_S:.0f}s")
    if not rag.connected:
        # Predictions are sparse by nature — connectedness is the only
        # meaningful liveness signal for the RAG stream.
        problems.append("rag subscriber disconnected")

    body = {
        "status": "degraded" if problems else "ok",
        "problems": problems,
        "ws_clients": broadcaster.client_count,
        "engine": engine.summary(),
        "rag": rag.summary(),
    }
    return JSONResponse(body, status_code=503 if problems else 200)


def _origin_allowed(ws: WebSocket) -> bool:
    if not _ALLOWED_ORIGINS:
        return True
    origin = (ws.headers.get("origin") or "").rstrip("/").lower()
    # No Origin header = not a browser (curl, probes, watch scripts). The check
    # exists to stop CROSS-SITE BROWSER pages; non-browser clients could fake
    # any origin anyway, so rejecting them adds nothing and breaks tooling.
    if not origin:
        return True
    return origin in _ALLOWED_ORIGINS


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    if not _origin_allowed(ws):
        logger.warning("[gateway] rejected WS from origin %r", ws.headers.get("origin"))
        await ws.close(code=4403)  # policy violation: bad origin
        return
    if broadcaster.client_count >= _MAX_WS_CLIENTS:
        logger.warning("[gateway] rejected WS — client cap %d reached", _MAX_WS_CLIENTS)
        await ws.close(code=1013)  # try again later
        return

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
    if len(raw) > 4096:  # control frames are tiny; don't json.loads megabytes
        logger.debug("[gateway] ignoring oversized client frame (%d bytes)", len(raw))
        return
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
