"""
Ingestion Provider Abstraction & Data Transfer Objects
Protocols, DTOs, and status enumerations for historical and live data pipelines.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class IngestionStatusEnum(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class RawMatchRowDTO(BaseModel):
    """Normalized DTO emitted by raw provider adapters prior to domain normalization."""
    source_row_index: int
    competition_code: str
    season_year: str
    match_date: datetime
    date_precision: str = "DATE_ONLY"  # "DATE_ONLY" or "EXACT_TIME"

    home_team_raw: str = Field(..., min_length=1)
    away_team_raw: str = Field(..., min_length=1)

    full_time_home_goals: int = Field(..., ge=0)
    full_time_away_goals: int = Field(..., ge=0)
    full_time_result: str = Field(..., pattern="^[HDA]$")  # H=Home, D=Draw, A=Away

    half_time_home_goals: int | None = Field(None, ge=0)
    half_time_away_goals: int | None = Field(None, ge=0)
    half_time_result: str | None = Field(None, pattern="^[HDA]$")

    # Optional Match Statistics
    home_shots: int | None = Field(None, ge=0)
    away_shots: int | None = Field(None, ge=0)
    home_shots_on_target: int | None = Field(None, ge=0)
    away_shots_on_target: int | None = Field(None, ge=0)
    home_corners: int | None = Field(None, ge=0)
    away_corners: int | None = Field(None, ge=0)
    home_fouls: int | None = Field(None, ge=0)
    away_fouls: int | None = Field(None, ge=0)
    home_yellow_cards: int | None = Field(None, ge=0)
    away_yellow_cards: int | None = Field(None, ge=0)
    home_red_cards: int | None = Field(None, ge=0)
    away_red_cards: int | None = Field(None, ge=0)

    # Raw Payload Preservation (bookmaker odds & extra columns kept here ONLY)
    raw_payload: dict[str, Any]

    model_config = ConfigDict(arbitrary_types_allowed=True)


class HistoricalProviderBatchResultDTO(BaseModel):
    """Batch summary emitted after file parsing and provider adaptation."""
    provider_key: str
    source_reference: str
    checksum: str
    total_rows: int
    valid_rows: list[RawMatchRowDTO]
    invalid_rows: list[dict[str, Any]]
    validation_warnings: list[str]


class HistoricalFootballProvider(Protocol):
    """Abstract Protocol for Historical Football Data Providers."""
    provider_key: str

    def parse_file(
        self, file_path: str, competition_override: str | None = None, season_override: str | None = None
    ) -> HistoricalProviderBatchResultDTO:
        ...
