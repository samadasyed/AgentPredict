"""
Offline mock of PolymarketClient — no network, no API key.

Enabled when MOCK_MODE=1. Returns a small set of synthetic UFC markets whose
implied probabilities random-walk on every poll, so the agent computes real
deltas and emits a steady, lifelike stream of MarketEvents. Drop-in for the
async interface the agent uses: get_markets / get_prices / close.

Owner: Samad (demo/offline harness)
"""

from __future__ import annotations

import random
import time

from agents.polymarket.models import Market, PriceSnapshot, TokenPrice

# (condition_id, outcome label, starting probability)
_SEED_MARKETS = [
    ("0xufc-jones-aspinall", "Jon Jones def. Tom Aspinall", 0.58),
    ("0xufc-pereira-ankalaev", "Alex Pereira wins by KO/TKO", 0.47),
    ("0xufc-omalley-dvalishvili", "Sean O'Malley retains title", 0.52),
    ("0xufc-makhachev-tsarukyan", "Islam Makhachev def. Tsarukyan", 0.64),
]


class MockPolymarketClient:
    """Synthetic Polymarket source for offline/demo runs."""

    def __init__(self, *, step: float = 0.035, seed: int | None = None) -> None:
        self._step = step
        self._rng = random.Random(seed)
        self._probs: dict[str, float] = {cid: p for cid, _, p in _SEED_MARKETS}

    async def get_markets(self, active_only: bool = True) -> list[Market]:
        return [
            Market(
                condition_id=cid,
                question=outcome,
                tokens=[TokenPrice(token_id=f"{cid}-yes", outcome=outcome, price=self._probs[cid])],
                accepting_orders=True,
            )
            for cid, outcome, _ in _SEED_MARKETS
        ]

    async def get_prices(self, market_ids: list[str]) -> list[PriceSnapshot]:
        now = int(time.time() * 1000)
        snaps: list[PriceSnapshot] = []
        for cid, outcome, _ in _SEED_MARKETS:
            if cid not in market_ids:
                continue
            # Random walk, clamped to a realistic (0.02, 0.98) band.
            drift = self._rng.uniform(-self._step, self._step)
            prob = min(0.98, max(0.02, self._probs[cid] + drift))
            self._probs[cid] = prob
            snaps.append(
                PriceSnapshot(
                    market_id=cid,
                    token_id=f"{cid}-yes",
                    outcome=outcome,
                    probability=prob,
                    timestamp_ms=now,
                )
            )
        return snaps

    async def close(self) -> None:  # noqa: D401 - parity with real client
        return None
