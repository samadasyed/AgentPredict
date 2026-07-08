"""
Unit tests for the Broadcaster: connection tracking, replay buffer, per-client
source filtering, and dead-client cleanup.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.broadcaster import Broadcaster, _normalize_source


@pytest.fixture
def broadcaster():
    return Broadcaster()


def _mock_ws(fail_on_send: bool = False) -> MagicMock:
    """A fake WebSocket that records every payload it is sent (or always fails)."""
    ws = MagicMock()
    ws.sent = []
    if fail_on_send:
        ws.send_text = AsyncMock(side_effect=RuntimeError("connection closed"))
    else:
        async def _send(payload: str) -> None:
            ws.sent.append(payload)
        ws.send_text = AsyncMock(side_effect=_send)
    return ws


def _types(ws) -> list[str]:
    return [json.loads(p)["type"] for p in ws.sent]


def _event(source: str | None = None, **data) -> dict:
    payload = dict(data)
    if source is not None:
        payload["source"] = source
    return {"type": "event", "data": payload}


# ─── Connection tracking ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_connect_adds_client(broadcaster):
    await broadcaster.connect(_mock_ws())
    assert broadcaster.client_count == 1


@pytest.mark.asyncio
async def test_disconnect_removes_client(broadcaster):
    ws = _mock_ws()
    await broadcaster.connect(ws)
    await broadcaster.disconnect(ws)
    assert broadcaster.client_count == 0


@pytest.mark.asyncio
async def test_disconnect_unknown_client_is_no_op(broadcaster):
    await broadcaster.disconnect(_mock_ws())  # never connected — must not raise


@pytest.mark.asyncio
async def test_multiple_disconnects_idempotent(broadcaster):
    ws = _mock_ws()
    await broadcaster.connect(ws)
    await broadcaster.disconnect(ws)
    await broadcaster.disconnect(ws)
    assert broadcaster.client_count == 0


# ─── Broadcast fan-out ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_broadcast_sends_to_all_clients(broadcaster):
    ws1, ws2 = _mock_ws(), _mock_ws()
    await broadcaster.connect(ws1)
    await broadcaster.connect(ws2)

    msg = {"type": "event", "data": {"foo": "bar"}}
    await broadcaster.broadcast(msg)

    assert ws1.sent == [json.dumps(msg)]
    assert ws2.sent == [json.dumps(msg)]


@pytest.mark.asyncio
async def test_broadcast_to_no_clients_is_no_op(broadcaster):
    await broadcaster.broadcast({"type": "event", "data": {}})  # must not raise


@pytest.mark.asyncio
async def test_broadcast_removes_dead_client(broadcaster):
    good_ws = _mock_ws()
    dead_ws = _mock_ws(fail_on_send=True)
    await broadcaster.connect(good_ws)
    await broadcaster.connect(dead_ws)
    assert broadcaster.client_count == 2

    await broadcaster.broadcast({"type": "event", "data": {}})

    assert broadcaster.client_count == 1
    assert len(good_ws.sent) == 1


@pytest.mark.asyncio
async def test_broadcast_middle_client_dead_no_iteration_error(broadcaster):
    # Regression: iterating a dict while removing must not raise RuntimeError.
    a, dead, c = _mock_ws(), _mock_ws(fail_on_send=True), _mock_ws()
    for ws in (a, dead, c):
        await broadcaster.connect(ws)

    await broadcaster.broadcast({"type": "event", "data": {}})

    assert broadcaster.client_count == 2
    assert len(a.sent) == 1 and len(c.sent) == 1


# ─── Replay buffer ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_replay_on_connect(broadcaster):
    # Messages broadcast before a client connects are replayed on connect.
    await broadcaster.broadcast(_event("SOURCE_POLYMARKET", market_id="a"))
    await broadcaster.broadcast(_event("SOURCE_MMA", fight_id="b"))
    await broadcaster.broadcast({"type": "prediction", "data": {"confidence": 0.9}})

    late = _mock_ws()
    await broadcaster.connect(late)

    types = _types(late)
    assert types.count("event") == 2
    assert types.count("prediction") == 1


@pytest.mark.asyncio
async def test_replay_buffer_caps_at_buffer_size(broadcaster):
    from gateway.broadcaster import _BUFFER_SIZE

    overflow = 10
    for i in range(_BUFFER_SIZE + overflow):
        await broadcaster.broadcast(_event("SOURCE_POLYMARKET", i=i))

    late = _mock_ws()
    await broadcaster.connect(late)

    events = [json.loads(p) for p in late.sent]
    assert len(events) == _BUFFER_SIZE                     # only the last N retained
    assert events[0]["data"]["i"] == overflow              # oldest retained
    assert events[-1]["data"]["i"] == _BUFFER_SIZE + overflow - 1  # newest


@pytest.mark.asyncio
async def test_no_replay_to_existing_client_on_new_broadcast(broadcaster):
    ws = _mock_ws()
    await broadcaster.connect(ws)          # nothing buffered yet
    await broadcaster.broadcast(_event("SOURCE_MMA", x=1))
    assert len(ws.sent) == 1               # exactly-once, not replayed again


# ─── Per-client source filter ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_filter_blocks_other_source(broadcaster):
    ws = _mock_ws()
    await broadcaster.connect(ws)
    await broadcaster.set_filter(ws, "mma")

    await broadcaster.broadcast(_event("SOURCE_POLYMARKET", market_id="a"))
    assert ws.sent == []  # polymarket dropped for an MMA-filtered client

    await broadcaster.broadcast(_event("SOURCE_MMA", fight_id="b"))
    assert len(ws.sent) == 1


@pytest.mark.asyncio
async def test_filter_delivers_unclassified_events(broadcaster):
    ws = _mock_ws()
    await broadcaster.connect(ws)
    await broadcaster.set_filter(ws, "pm")

    await broadcaster.broadcast(_event("SOURCE_UNKNOWN", x=1))  # unknown source
    await broadcaster.broadcast(_event(None, y=2))              # missing source key
    assert len(ws.sent) == 2  # unclassified events are never silently dropped


@pytest.mark.asyncio
async def test_predictions_bypass_filter(broadcaster):
    ws = _mock_ws()
    await broadcaster.connect(ws)
    await broadcaster.set_filter(ws, "mma")

    await broadcaster.broadcast({"type": "prediction", "data": {"confidence": 0.8}})
    assert len(ws.sent) == 1  # predictions carry no source and always deliver


@pytest.mark.asyncio
async def test_set_filter_all_clears(broadcaster):
    ws = _mock_ws()
    await broadcaster.connect(ws)
    await broadcaster.set_filter(ws, "pm")
    await broadcaster.set_filter(ws, "all")  # clear

    await broadcaster.broadcast(_event("SOURCE_MMA", fight_id="b"))
    assert len(ws.sent) == 1


@pytest.mark.asyncio
async def test_set_filter_unknown_client_is_no_op(broadcaster):
    await broadcaster.set_filter(_mock_ws(), "mma")  # not connected — must not raise


def test_normalize_source_aliases():
    assert _normalize_source("pm") == "SOURCE_POLYMARKET"
    assert _normalize_source("POLYMARKET") == "SOURCE_POLYMARKET"
    assert _normalize_source("mma") == "SOURCE_MMA"
    assert _normalize_source("all") is None
    assert _normalize_source(None) is None
    assert _normalize_source("garbage") is None  # unknown -> no filter (show all)
