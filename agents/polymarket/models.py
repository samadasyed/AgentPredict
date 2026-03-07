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
