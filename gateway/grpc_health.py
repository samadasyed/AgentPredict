"""
Shared gRPC-subscriber plumbing for the gateway.

* keepalive channel options — without client keepalive a half-open TCP
  connection (peer died without RST: host reboot, NAT/conntrack expiry on an
  idle stream) leaves `async for ... in stub.X()` blocked forever with no
  exception, so the reconnect loop never runs and the feed silently freezes.
* SubscriberHealth — the state /health reports so a dead data plane cannot
  hide behind an unconditional 200 (that exact incident happened once with a
  MessageToDict kwarg: every message errored, /health stayed green).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

# Ping every 30s even with no data; declare the peer dead if a ping goes
# unanswered for 10s. This turns a silent half-open connection into an
# exception the reconnect loop can see within ~40s.
KEEPALIVE_CHANNEL_OPTIONS = [
    ("grpc.keepalive_time_ms", 30_000),
    ("grpc.keepalive_timeout_ms", 10_000),
    ("grpc.keepalive_permit_without_calls", 1),
    ("grpc.http2.max_pings_without_data", 0),
]


@dataclass
class SubscriberHealth:
    """Liveness state one subscriber exposes to /health."""
    connected: bool = False
    consecutive_errors: int = 0
    last_message_monotonic: float = field(default_factory=time.monotonic)
    last_error: str = ""

    def on_connect(self) -> None:
        self.connected = True
        self.consecutive_errors = 0
        self.last_error = ""
        self.last_message_monotonic = time.monotonic()

    def on_message(self) -> None:
        self.last_message_monotonic = time.monotonic()

    def on_error(self, exc: BaseException) -> None:
        self.connected = False
        self.consecutive_errors += 1
        self.last_error = f"{type(exc).__name__}: {exc}"[:300]

    def seconds_since_message(self) -> float:
        return time.monotonic() - self.last_message_monotonic

    def summary(self) -> dict:
        return {
            "connected": self.connected,
            "consecutive_errors": self.consecutive_errors,
            "seconds_since_last_message": round(self.seconds_since_message(), 1),
            "last_error": self.last_error,
        }
