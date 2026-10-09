"""
Core Entity Pydantic Schemas
Validation DTOs for Competitions, Seasons, Teams, and Matches.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompetitionBase(BaseModel):
    code: str = Field(..., max_length=20)
    name: str = Field(..., max_length=100)
    country: str = Field(..., max_length=50)
    competition_type: str = "DOMESTIC_LEAGUE"
    is_active: bool = True

class CompetitionCreate(CompetitionBase):
    pass

class CompetitionResponse(CompetitionBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SeasonBase(BaseModel):
    season_year: str = Field(..., max_length=20)
    start_year: int | None = None
    end_year: int | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    is_current: bool = False

class SeasonCreate(SeasonBase):
    competition_id: UUID

class SeasonResponse(SeasonBase):
    id: UUID
    competition_id: UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class TeamBase(BaseModel):
    canonical_name: str = Field(..., max_length=100)
    short_name: str | None = Field(None, max_length=50)
    short_code: str | None = Field(None, max_length=10)
    country: str | None = Field(None, max_length=50)
    is_active: bool = True

class TeamCreate(TeamBase):
    pass

class TeamResponse(TeamBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class MatchBase(BaseModel):
    kickoff_utc: datetime
    status: str = "SCHEDULED"
    home_score: int | None = None
    away_score: int | None = None
    half_time_home_score: int | None = None
    half_time_away_score: int | None = None

class MatchCreate(MatchBase):
    season_id: UUID
    home_team_id: UUID
    away_team_id: UUID

class MatchResponse(MatchBase):
    id: UUID
    season_id: UUID
    home_team_id: UUID
    away_team_id: UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
