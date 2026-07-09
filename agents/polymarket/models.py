"""
Pydantic models mirroring Polymarket API response shapes.

Reference: https://docs.polymarket.com/api-reference/introduction
Markets return prices as implied probabilities in [0, 1].
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class TokenPrice(BaseModel):
    """One outcome token within a market."""
    token_id: str
    outcome: str
    price: float = Field(ge=0.0, le=1.0, description="Implied probability [0, 1]")


class Market(BaseModel):
    """A single Polymarket market (condition)."""
    condition_id: str
    question: str
    tokens: list[TokenPrice]
    active: bool = True
    closed: bool = False
    accepting_orders: bool = False  # True only while the market is live & tradeable
    # Scheduled start of the underlying event (fight), unix millis. 0 = unknown.
    event_start_ms: int = 0
    # Lifecycle: "upcoming" | "live" | "final" | "" (unknown).
    phase: str = ""
    # ── Fight metadata (from the Gamma event object; empty for non-fight markets) ──
    title: str = ""        # headline matchup, e.g. "Max Holloway vs. Conor McGregor"
    card_title: str = ""   # the card, e.g. "UFC 329" / "UFC Fight Night"
    fight_info: str = ""   # e.g. "Welterweight · Main Card"
    volume: float = 0.0    # event volume (USDC) — proxy for fight prominence
    event_slug: str = ""   # Polymarket event slug → polymarket.com/event/<slug>

    @field_validator("tokens")
    @classmethod
    def at_least_one_token(cls, v: list[TokenPrice]) -> list[TokenPrice]:
        if not v:
            raise ValueError("Market must have at least one token")
        return v


class MarketsPage(BaseModel):
    """Paginated response from GET /markets."""
    data: list[Market]
    next_cursor: str | None = None
    count: int = 0


class PriceSnapshot(BaseModel):
    """
    Lightweight snapshot of a single token price used internally
    between poll cycles to compute deltas.
    """
    market_id: str    # condition_id
    token_id: str
    outcome: str
    probability: float
    timestamp_ms: int  # unix millis at time of snapshot
    # Recent probability trajectory as (timestamp_ms, probability) pairs, oldest
    # first. Carried so the dashboard can render history without back-dated events
    # (the engine rejects events whose timestamp is >60s from now).
    history: list[tuple[int, float]] = []
    # Scheduled start of the underlying event (fight), unix millis. 0 = unknown.
    event_start_ms: int = 0
    # Lifecycle: "upcoming" | "live" | "final" | "" (unknown).
    phase: str = ""
    # Fight metadata mirrored from Market (see Market for field docs).
    title: str = ""
    card_title: str = ""
    fight_info: str = ""
    volume: float = 0.0
    event_slug: str = ""
