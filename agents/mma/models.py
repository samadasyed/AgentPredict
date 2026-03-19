"""
Pydantic models mirroring BallDontLie MMA API response shapes.

Free tier provides: live event discovery.
GOAT tier ($39.99/mo) provides: fight stats, round stats.

Reference: https://mma.balldontlie.io
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class Fighter(BaseModel):
    id: int
    first_name: str
    last_name: str
    nickname: str | None = None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class Fight(BaseModel):
    id: int
    event_id: int
    fighter1: Fighter
    fighter2: Fighter
    status: str  # e.g. "scheduled", "in_progress", "completed"
    round: int | None = None
    winner_id: int | None = None


class Event(BaseModel):
    id: int
    name: str
    date: date
    location: str | None = None
    fights: list[Fight] = Field(default_factory=list)


# ─── GOAT-tier shapes (defined but never populated on free tier) ──────────────

class FightStat(BaseModel):
    """Per-fighter stat aggregate. GOAT tier only."""
    fight_id: int
    fighter_id: int
    fighter_name: str
    significant_strikes: int = 0
    takedowns: int = 0
    knockdowns: int = 0
    submission_attempts: int = 0
    total_strikes: int = 0


class RoundStat(BaseModel):
    """Per-round breakdown. GOAT tier only."""
    fight_id: int
    fighter_id: int
    round: int
    significant_strikes: int = 0
    takedowns: int = 0
    knockdowns: int = 0
    submission_attempts: int = 0
    total_strikes: int = 0
