"""
Offline mock of PolymarketClient — no network, no API key.

Enabled when MOCK_MODE=1. Returns a synthetic UFC slate shaped EXACTLY like the
real client's events-by-tag output: one Market per fight (the winner moneyline),
outcome = fighter A's name with probability = P(A), plus matchup title, card
title, weight class / card segment, and volume. Tells the full lifecycle story:

  * one LIVE fight (started minutes ago) whose odds swing harder, paired with
    the MMA mock's in-progress fight so live stats flow alongside;
  * four UPCOMING fights (hours-to-days out) — each ships a week-long
    probability history so the dashboard can show the odds trend before the
    event, plus a scheduled start time for the countdown.

Fighter names match the MMA mock so the dashboard can fuse market odds with
live fight stats. Drop-in for the async interface the agent uses:
get_markets / get_prices / close.

Owner: Samad (demo/offline harness)
"""

from __future__ import annotations

import random
import time

from agents.polymarket.models import Market, PriceSnapshot, TokenPrice

_DAY_S = 86_400
_HISTORY_POINTS = 56          # ~8 readings/day over the last week
_HISTORY_SPAN_S = 7 * _DAY_S

# A full demo slate: one live main event + stacked upcoming fights with
# staggered countdowns. Names match the MMA mock so odds fuse with live stats.
# (condition_id, fighter A, fighter B, P(A), card, info, volume, phase, start offset s)
#   offset < 0 → already started (live);  offset > 0 → upcoming.
_SEED_MARKETS = [
    ("0xufc-jones-aspinall", "Jon Jones", "Tom Aspinall", 0.55,
     "UFC 999", "Heavyweight, Main Card", 1_450_000.0, "live", -15 * 60),
    ("0xufc-makhachev-tsarukyan", "Islam Makhachev", "Arman Tsarukyan", 0.68,
     "UFC 999", "Lightweight, Main Card", 610_000.0, "upcoming", 6 * 3600),
    ("0xufc-pereira-ankalaev", "Alex Pereira", "Magomed Ankalaev", 0.47,
     "UFC Fight Night", "Light Heavyweight, Main Card", 280_000.0, "upcoming", 2 * _DAY_S),
    ("0xufc-omalley-dvalishvili", "Sean O'Malley", "Merab Dvalishvili", 0.44,
     "UFC Fight Night", "Bantamweight, Main Card", 190_000.0, "upcoming", 5 * _DAY_S),
    ("0xufc-topuria-holloway", "Ilia Topuria", "Max Holloway", 0.61,
     "UFC 1000", "Lightweight, Main Card", 820_000.0, "upcoming", 9 * _DAY_S),
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
        for idx, (cid, _a, _b, p0, _card, _info, _vol, phase, offset) in enumerate(_SEED_MARKETS):
            self._probs[cid] = p0
            self._phase[cid] = phase
            self._event_start_ms[cid] = int((now_s + offset) * 1000)
            self._history[cid] = _synth_history(
                random.Random((seed + idx) if seed is not None else None), p0, now_s
            )

    # Live fights swing harder than markets that are still days away.
    def _step(self, cid: str) -> float:
        return 0.05 if self._phase[cid] == "live" else 0.02

    def _market(self, row: tuple) -> Market:
        cid, a, b, _p0, card, info, vol, _phase, _off = row
        p = self._probs[cid]
        return Market(
            condition_id=cid,
            # Mirrors the real Gamma event title — "UFC" in it so the default
            # POLYMARKET_QUERY="UFC" filter keeps it.
            question=f"{card}: {a} vs. {b} ({info})",
            tokens=[
                TokenPrice(token_id=f"{cid}-a", outcome=a, price=p),
                TokenPrice(token_id=f"{cid}-b", outcome=b, price=round(1.0 - p, 4)),
            ],
            accepting_orders=True,
            event_start_ms=self._event_start_ms[cid],
            phase=self._phase[cid],
            title=f"{a} vs. {b}",
            card_title=card,
            fight_info=" · ".join(part.strip() for part in info.split(",")),
            volume=vol,
            event_slug=cid.removeprefix("0x"),
        )

    async def get_markets(self, active_only: bool = True) -> list[Market]:
        return [self._market(row) for row in _SEED_MARKETS]

    async def get_prices(self, market_ids: list[str]) -> list[PriceSnapshot]:
        now = int(time.time() * 1000)
        snaps: list[PriceSnapshot] = []
        for row in _SEED_MARKETS:
            cid = row[0]
            if cid not in market_ids:
                continue
            drift = self._rng.uniform(-self._step(cid), self._step(cid))
            self._probs[cid] = _clamp(self._probs[cid] + drift)
            m = self._market(row)
            token = m.tokens[0]  # primary outcome only, like the real client
            snaps.append(
                PriceSnapshot(
                    market_id=cid,
                    token_id=token.token_id,
                    outcome=token.outcome,
                    probability=token.price,
                    timestamp_ms=now,
                    history=self._history[cid],
                    event_start_ms=m.event_start_ms,
                    phase=m.phase,
                    title=m.title,
                    card_title=m.card_title,
                    fight_info=m.fight_info,
                    volume=m.volume,
                    event_slug=m.event_slug,
                )
            )
        return snaps

    async def close(self) -> None:  # noqa: D401 - parity with real client
        return None
