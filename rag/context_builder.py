"""
Sliding-window context builder.

Maintains a deque of the last N CanonicalEvents per source.
Serializes them into compact text lines for injection into the LLM prompt.

Owner: FWS
"""

from __future__ import annotations

from collections import deque
from typing import Dict

# Generated proto stubs
from agents.generated import events_pb2  # type: ignore[import]

# Maximum events retained per source.
_WINDOW_SIZE = 20


class ContextBuilder:
    """Thread-safe (via GIL) sliding window over recent canonical events."""

    def __init__(self, window_size: int = _WINDOW_SIZE) -> None:
        self._window_size = window_size
        self._windows: Dict[int, deque] = {
            events_pb2.SOURCE_POLYMARKET: deque(maxlen=window_size),
            events_pb2.SOURCE_MMA: deque(maxlen=window_size),
        }

    def add(self, event: "events_pb2.CanonicalEvent") -> None:
        """Add an event to the appropriate window."""
        window = self._windows.get(event.source)
        if window is not None:
            window.append(event)

    def build_context(self) -> str:
        """
        Serializes the current sliding windows into a compact text block
        suitable for prompt injection.

        Format:
            [POLYMARKET]
            market_id=<id> outcome=<outcome> prob=<p> delta=<d> ts=<ts>
            ...
            [MMA]
            fight_id=<id> fighter=<name> stat=<type> val=<v> round=<r> ts=<ts>
            ...
        """
        lines: list[str] = []

        # Polymarket events
        pm_events = list(self._windows[events_pb2.SOURCE_POLYMARKET])
        if pm_events:
            lines.append("[POLYMARKET]")
            for ev in pm_events:
                m = ev.market_event
                lines.append(
                    f"market_id={m.market_id} outcome={m.outcome!r} "
                    f"prob={m.probability:.4f} delta={m.delta:+.4f} ts={m.timestamp}"
                )

        # MMA events
        mma_events = list(self._windows[events_pb2.SOURCE_MMA])
        if mma_events:
            lines.append("[MMA]")
            for ev in mma_events:
                f = ev.fight_event
                lines.append(
                    f"fight_id={f.fight_id} fighter={f.fighter_name!r} "
                    f"stat={f.stat_type} val={f.value} round={f.round} ts={f.timestamp}"
                )

        return "\n".join(lines) if lines else "(no recent events)"

    def clear(self) -> None:
        for window in self._windows.values():
            window.clear()
