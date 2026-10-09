"""
Feature Engineering Base Protocols & DTOs
Base classes, calculation result containers, missingness definitions, and exception classes for feature engineering.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.models import Competition, Match, Season, Team


class MissingnessReason(str, Enum):
    """Explicit scientific reasons for missing feature values."""
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    SOURCE_FIELD_UNAVAILABLE = "SOURCE_FIELD_UNAVAILABLE"
    DATE_PRECISION_LIMITATION = "DATE_PRECISION_LIMITATION"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FeatureCalculationResult(BaseModel):
    """Result object emitted by an individual feature calculator."""
    feature_key: str
    version: str = "1.0.0"
    value: float | int | None = None
    is_missing: bool = False
    missing_reason: MissingnessReason = MissingnessReason.AVAILABLE
    sample_size: int = 0
    metadata_payload: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class FeatureContext(BaseModel):
    """Context container for point-in-time feature computation."""
    target_match: Match
    home_team: Team
    away_team: Team
    competition: Competition
    season: Season
    dataset_release_id: UUID
    dataset_key: str = "mvp_a_historical"
    dataset_version: str = "v1"
    cutoff_timestamp: datetime
    config: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class FeatureSetDTO(BaseModel):
    """Data Transfer Object representing a versioned feature set."""
    name: str
    version: str
    description: str
    feature_keys: list[str]
    dataset_key: str = "mvp_a_historical"
    dataset_version: str = "v1"


class BaseFeatureCalculator(Protocol):
    """Abstract protocol for feature calculators."""
    feature_key: str
    version: str
    description: str

    def calculate(
        self, db: Session, match: Match, cutoff_timestamp: datetime, config: dict[str, Any] | None = None
    ) -> FeatureCalculationResult:
        ...


class LeakageViolationError(RuntimeError):
    """Raised when data leakage is detected during feature calculation."""


class InsufficientHistoryError(ValueError):
    """Raised when a feature calculator encounters insufficient history and cannot fallback."""


class FeatureCalculationError(RuntimeError):
    """Raised when a feature calculation encounters an unrecoverable operational error."""
