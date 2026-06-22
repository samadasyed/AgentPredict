"""
Offline mock of PolymarketClient — no network, no API key.

Enabled when MOCK_MODE=1. Returns a synthetic UFC card that tells the full
lifecycle story the product is about:

  * two UPCOMING fights (days out) — each ships a week-long probability history
    so the dashboard can show the odds trend and "why it's moving" before the
    event, plus a scheduled start time for the countdown;
  * one LIVE fight (started minutes ago) whose odds swing harder, paired with
    the MMA mock's in-progress fight so live stats flow alongside.

Outcome labels are head-to-head ("A def. B") and the fighter names match the MMA
mock, so the dashboard can fuse market odds with live fight stats. Drop-in for
the async interface the agent uses: get_markets / get_prices / close.

Owner: Samad (demo/offline harness)
"""

from __future__ import annotations

import random
import time

from agents.polymarket.models import Market, PriceSnapshot, TokenPrice

_DAY_S = 86_400
_HISTORY_POINTS = 56          # ~8 readings/day over the last week
_HISTORY_SPAN_S = 7 * _DAY_S

# (condition_id, outcome "A def. B", seed probability, phase, start offset seconds)
#   offset < 0 → already started (live);  offset > 0 → upcoming.
_SEED_MARKETS = [
    ("0xufc-jones-aspinall", "Jon Jones def. Tom Aspinall", 0.58, "upcoming", 2 * _DAY_S),
    ("0xufc-pereira-ankalaev", "Alex Pereira def. Magomed Ankalaev", 0.47, "upcoming", 5 * _DAY_S),
    ("0xufc-omalley-dvalishvili", "Sean O'Malley def. Merab Dvalishvili", 0.52, "live", -12 * 60),
]


def _clamp(p: float) -> float:
    return min(0.97, max(0.03, p))


def _synth_history(rng: random.Random, end_prob: float, now_s: float) -> list[tuple[int, float]]:
    """A plausible week-long walk that ENDS at `end_prob`, with one news-driven
    jump so the trend has a story the RAG layer can later 'explain'."""
    # Start somewhere near the final value, then walk toward it.
    prob = _clamp(end_prob + rng.uniform(-0.12, 0.12))
    jump_at = rng.randint(int(_HISTORY_POINTS * 0.4), int(_HISTORY_POINTS * 0.75))
    pts: list[tuple[int, float]] = []
    start_s = now_s - _HISTORY_SPAN_S
    step = _HISTORY_SPAN_S / (_HISTORY_POINTS - 1)
    for i in range(_HISTORY_POINTS):
        ts_ms = int((start_s + i * step) * 1000)
        if i == jump_at:                       # a sudden line move (injury news, weigh-in, etc.)
            prob = _clamp(prob + rng.uniform(-0.10, 0.10))
        # Drift gently toward the seed value plus a little noise.
        prob = _clamp(prob + (end_prob - prob) * 0.12 + rng.uniform(-0.015, 0.015))
        pts.append((ts_ms, round(prob, 4)))
    pts[-1] = (pts[-1][0], round(end_prob, 4))  # land exactly on the seed
    return pts


class MockPolymarketClient:
    """Synthetic Polymarket source for offline/demo runs."""

    def __init__(self, *, seed: int | None = 7) -> None:
        now_s = time.time()
        self._rng = random.Random(seed)
        self._probs: dict[str, float] = {}
        self._history: dict[str, list[tuple[int, float]]] = {}
        self._event_start_ms: dict[str, int] = {}
        self._phase: dict[str, str] = {}
        for idx, (cid, _outcome, p0, phase, offset) in enumerate(_SEED_MARKETS):
            self._probs[cid] = p0
            self._phase[cid] = phase
            self._event_start_ms[cid] = int((now_s + offset) * 1000)
            self._history[cid] = _synth_history(
                random.Random((seed + idx) if seed is not None else None), p0, now_s
            )

    # Live fights swing harder than markets that are still days away.
    def _step(self, cid: str) -> float:
        return 0.05 if self._phase[cid] == "live" else 0.02

    def _market(self, cid: str, outcome: str) -> Market:
        return Market(
            condition_id=cid,
            question=outcome,
            tokens=[TokenPrice(token_id=f"{cid}-yes", outcome=outcome, price=self._probs[cid])],
            accepting_orders=True,
            event_start_ms=self._event_start_ms[cid],
            phase=self._phase[cid],
        )

    async def get_markets(self, active_only: bool = True) -> list[Market]:
        return [self._market(cid, outcome) for cid, outcome, *_ in _SEED_MARKETS]

    async def get_prices(self, market_ids: list[str]) -> list[PriceSnapshot]:
        now = int(time.time() * 1000)
        snaps: list[PriceSnapshot] = []
        for cid, outcome, *_ in _SEED_MARKETS:
            if cid not in market_ids:
                continue
            drift = self._rng.uniform(-self._step(cid), self._step(cid))
            prob = _clamp(self._probs[cid] + drift)
            self._probs[cid] = prob
            snaps.append(
                PriceSnapshot(
                    market_id=cid,
                    token_id=f"{cid}-yes",
                    outcome=outcome,
                    probability=prob,
                    timestamp_ms=now,
                    history=self._history[cid],
                    event_start_ms=self._event_start_ms[cid],
                    phase=self._phase[cid],
                )
            )
        return snaps

    async def close(self) -> None:  # noqa: D401 - parity with real client
        return None
