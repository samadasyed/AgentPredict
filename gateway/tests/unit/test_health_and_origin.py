"""
Unit tests for gateway production hardening:
  * /health reflects real subscriber state (503 degraded, not unconditional 200)
  * /ws origin allowlist
  * SubscriberHealth state transitions
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import gateway.server as server
from gateway.grpc_health import SubscriberHealth


@pytest.fixture
def client():
    # TestClient triggers lifespan (subscribers start + retry against nothing —
    # harmless for these assertions since we set health state explicitly).
    with TestClient(server.app) as c:
        yield c
    # Reset shared state so tests stay independent.
    server.engine_sub.health = SubscriberHealth()
    server.rag_sub.health = SubscriberHealth()


def _healthy(sub) -> None:
    sub.health.on_connect()
    sub.health.on_message()


def test_health_degraded_when_disconnected(client):
    # Fresh start: nothing connected yet → degraded, 503.
    server.engine_sub.health = SubscriberHealth()
    server.rag_sub.health = SubscriberHealth()
    resp = client.get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert any("engine" in p for p in body["problems"])
    assert any("rag" in p for p in body["problems"])


def test_health_ok_when_both_connected_and_flowing(client):
    _healthy(server.engine_sub)
    _healthy(server.rag_sub)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_degraded_when_engine_silent(client):
    _healthy(server.engine_sub)
    _healthy(server.rag_sub)
    # Engine connected but silent past the threshold.
    server.engine_sub.health.last_message_monotonic = (
        time.monotonic() - server._ENGINE_SILENCE_S - 1
    )
    resp = client.get("/health")
    assert resp.status_code == 503
    assert any("silent" in p for p in resp.json()["problems"])


def test_subscriber_health_error_flow():
    h = SubscriberHealth()
    h.on_connect()
    assert h.connected and h.consecutive_errors == 0
    h.on_error(RuntimeError("boom"))
    assert not h.connected
    assert h.consecutive_errors == 1
    assert "boom" in h.last_error
    h.on_connect()
    assert h.consecutive_errors == 0 and h.last_error == ""


# ─── Origin allowlist ─────────────────────────────────────────────────────────

def _ws_headers(origin: str | None):
    return {"origin": origin} if origin else {}


def test_origin_allowed_when_no_allowlist(monkeypatch):
    monkeypatch.setattr(server, "_ALLOWED_ORIGINS", set())
    ws = MagicMock()
    ws.headers = {"origin": "https://evil.example"}
    assert server._origin_allowed(ws) is True


def test_origin_enforced_when_allowlist_set(monkeypatch):
    monkeypatch.setattr(
        server, "_ALLOWED_ORIGINS", {"https://agentpredictmma.com"}
    )
    good = MagicMock(); good.headers = {"origin": "https://agentpredictmma.com"}
    trailing = MagicMock(); trailing.headers = {"origin": "https://agentpredictmma.com/"}
    upper = MagicMock(); upper.headers = {"origin": "HTTPS://AGENTPREDICTMMA.COM"}
    bad = MagicMock(); bad.headers = {"origin": "https://evil.example"}
    missing = MagicMock(); missing.headers = {}
    assert server._origin_allowed(good) is True
    assert server._origin_allowed(trailing) is True
    assert server._origin_allowed(upper) is True
    assert server._origin_allowed(bad) is False
    assert server._origin_allowed(missing) is False
