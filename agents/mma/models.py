"""
Pydantic models mirroring BallDontLie MMA API response shapes.

Free tier provides: events, fighters, leagues.
ALL-STAR tier ($9.99/mo) provides: fights, rankings.
GOAT tier ($39.99/mo) provides: fight stats, betting odds.

Reference: https://mma.balldontlie.io
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


# ─── Free-tier models ─────────────────────────────────────────────────────────


class WeightClass(BaseModel):
    id: int
    name: str  # e.g. "Lightweight"
    abbreviation: str  # e.g. "LW"
    weight_limit_lbs: int | None = None
    gender: str | None = None


class League(BaseModel):
    id: int
    name: str  # e.g. "UFC"
    abbreviation: str  # e.g. "UFC"


class Fighter(BaseModel):
    id: int
    name: str = ""
    first_name: str = ""
    last_name: str = ""
    nickname: str | None = None
    nationality: str | None = None
    stance: str | None = None
    reach_inches: int | None = None
    height_inches: int | None = None
    weight_lbs: int | None = None
    record_wins: int = 0
    record_losses: int = 0
    record_draws: int = 0
    record_no_contests: int = 0
    active: bool = True
    weight_class: WeightClass | None = None

    @property
    def full_name(self) -> str:
        if self.name:
            return self.name
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def record(self) -> str:
        return f"{self.record_wins}-{self.record_losses}-{self.record_draws}"


class Event(BaseModel):
    id: int
    name: str
    short_name: str | None = None
    date: date | datetime | None = None
    venue_name: str | None = None
    venue_city: str | None = None
    venue_state: str | None = None
    venue_country: str | None = None
    status: str | None = None  # e.g. "scheduled", "in_progress", "completed"
    league: League | None = None
    fights: list[Fight] = []  # populated only with ALL-STAR tier; empty on free tier


# ─── ALL-STAR-tier models (defined for future use) ────────────────────────────


class Fight(BaseModel):
    id: int
    event_id: int
    fighter1: Fighter | None = None
    fighter2: Fighter | None = None
    status: str  # e.g. "scheduled", "in_progress", "completed"
    round: int | None = None
    winner_id: int | None = None


# Resolve forward reference: Event.fights -> Fight
Event.model_rebuild()


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
