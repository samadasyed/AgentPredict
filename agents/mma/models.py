"""
Pydantic models mirroring the BallDontLie MMA API (https://api.balldontlie.io).

Shapes follow the official OpenAPI spec: https://www.balldontlie.io/openapi/mma.yml
List endpoints wrap results as {"data": [...], "meta": {"next_cursor", ...}}.
Events and fights are SEPARATE resources (a fight embeds its event/fighters as
nested objects; events do NOT embed fights). Extra response fields are ignored.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

# Extra fields the API may add are ignored rather than rejected.
_cfg = ConfigDict(extra="ignore")


class WeightClass(BaseModel):
    model_config = _cfg
    id: int | None = None
    name: str | None = None
    abbreviation: str | None = None
    weight_limit_lbs: int | None = None
    gender: str | None = None


class League(BaseModel):
    model_config = _cfg
    id: int | None = None
    name: str | None = None
    abbreviation: str | None = None


class Fighter(BaseModel):
    model_config = _cfg
    id: int
    name: str = ""
    first_name: str = ""
    last_name: str = ""
    nickname: str | None = None
    date_of_birth: str | None = None
    birth_place: str | None = None
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
        return self.name or f"{self.first_name} {self.last_name}".strip()

    @property
    def record(self) -> str:
        return f"{self.record_wins}-{self.record_losses}-{self.record_draws}"


class Event(BaseModel):
    model_config = _cfg
    id: int
    name: str
    short_name: str | None = None
    date: date | datetime | None = None
    venue_name: str | None = None
    venue_city: str | None = None
    venue_state: str | None = None
    venue_country: str | None = None
    status: str | None = None  # free-text per the spec (no documented enum)
    main_card_start_time: datetime | None = None
    prelims_start_time: datetime | None = None
    early_prelims_start_time: datetime | None = None
    league: League | None = None


class Fight(BaseModel):
    model_config = _cfg
    id: int
    event: Event | None = None              # nested object
    fighter1: Fighter | None = None         # nested object
    fighter2: Fighter | None = None         # nested object
    winner: Fighter | None = None           # nested object, null until decided
    weight_class: WeightClass | None = None
    is_main_event: bool = False
    is_title_fight: bool = False
    card_segment: str | None = None
    fight_order: int | None = None
    scheduled_rounds: int | None = None
    result_method: str | None = None
    result_method_detail: str | None = None
    result_round: int | None = None
    result_time: str | None = None
    status: str | None = None               # free-text per the spec


class FightStat(BaseModel):
    """Per-fighter aggregate stats for a fight (from /mma/v1/fight_stats)."""
    model_config = _cfg
    id: int | None = None
    fight_id: int
    fighter: Fighter | None = None          # nested object
    is_winner: bool | None = None
    knockdowns: int | None = 0
    significant_strikes_landed: int | None = 0
    significant_strikes_attempted: int | None = 0
    significant_strike_pct: float | None = None
    total_strikes_landed: int | None = 0
    takedowns_landed: int | None = 0
    takedowns_attempted: int | None = 0
    takedown_pct: float | None = None
    submissions_attempted: int | None = 0
    control_time_seconds: int | None = 0
    reversals: int | None = 0

    @property
    def fighter_name(self) -> str:
        return self.fighter.full_name if self.fighter else ""
