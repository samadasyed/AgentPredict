"""
Unit tests for the Broadcaster.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.broadcaster import Broadcaster


@pytest.fixture
def broadcaster():
    return Broadcaster()


def _mock_ws(fail_on_send: bool = False) -> MagicMock:
    ws = MagicMock()
    if fail_on_send:
        ws.send_text = AsyncMock(side_effect=RuntimeError("connection closed"))
    else:
        ws.send_text = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_connect_adds_client(broadcaster):
    ws = _mock_ws()
    await broadcaster.connect(ws)
    assert broadcaster.client_count == 1


@pytest.mark.asyncio
async def test_disconnect_removes_client(broadcaster):
    ws = _mock_ws()
    await broadcaster.connect(ws)
    await broadcaster.disconnect(ws)
    assert broadcaster.client_count == 0


@pytest.mark.asyncio
async def test_broadcast_sends_to_all_clients(broadcaster):
    ws1, ws2 = _mock_ws(), _mock_ws()
    await broadcaster.connect(ws1)
    await broadcaster.connect(ws2)

    msg = {"type": "event", "data": {"foo": "bar"}}
    await broadcaster.broadcast(msg)

    ws1.send_text.assert_awaited_once_with(json.dumps(msg))
    ws2.send_text.assert_awaited_once_with(json.dumps(msg))


@pytest.mark.asyncio
async def test_broadcast_removes_dead_client(broadcaster):
    good_ws = _mock_ws(fail_on_send=False)
    dead_ws = _mock_ws(fail_on_send=True)

    await broadcaster.connect(good_ws)
    await broadcaster.connect(dead_ws)
    assert broadcaster.client_count == 2

    await broadcaster.broadcast({"type": "event", "data": {}})

    # Dead client should have been removed; good client still present.
    assert broadcaster.client_count == 1
    good_ws.send_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_broadcast_to_no_clients_is_no_op(broadcaster):
    # Should not raise
    await broadcaster.broadcast({"type": "event", "data": {}})


@pytest.mark.asyncio
async def test_disconnect_unknown_client_is_no_op(broadcaster):
    ws = _mock_ws()
    # Never connected — should not raise
    await broadcaster.disconnect(ws)


@pytest.mark.asyncio
async def test_multiple_disconnects_idempotent(broadcaster):
    ws = _mock_ws()
    await broadcaster.connect(ws)
    await broadcaster.disconnect(ws)
    await broadcaster.disconnect(ws)  # second call — no error
    assert broadcaster.client_count == 0
