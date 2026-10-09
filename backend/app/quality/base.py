"""
Quality Framework Base Classes & Data Transfer Objects
Enumerations, finding models, rule specifications, readiness statuses, and quality reports.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class QualitySeverityEnum(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    BLOCKING = "BLOCKING"


class QualityCategoryEnum(StrEnum):
    STRUCTURAL = "STRUCTURAL"
    DOMAIN = "DOMAIN"
    ANALYTICAL = "ANALYTICAL"


class FindingResolutionStatusEnum(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    ACCEPTED_LIMITATION = "ACCEPTED_LIMITATION"


class ReadinessStatusEnum(StrEnum):
    READY = "READY"
    READY_WITH_WARNINGS = "READY_WITH_WARNINGS"
    BLOCKED = "BLOCKED"
    NOT_READY = "NOT_READY"


class QualityRule(BaseModel):
    """Specification of a deterministic Data Quality Rule."""
    rule_key: str
    name: str
    category: QualityCategoryEnum
    severity: QualitySeverityEnum
    description: str
    rationale: str
    blocks_feature_engineering: bool = False

    model_config = ConfigDict(frozen=True)


class QualityFinding(BaseModel):
    """Container for a single detected data quality issue or finding."""
    rule_key: str
    severity: QualitySeverityEnum
    issue_key: str
    description: str
    entity_type: str  # "MATCH", "TEAM", "SEASON", "COMPETITION", "PROVENANCE"
    entity_id: UUID | None = None
    competition_code: str | None = None
    season_year: str | None = None
    quality_score: float | None = None
    metadata_payload: dict[str, Any] = Field(default_factory=dict)
    resolution_status: FindingResolutionStatusEnum = FindingResolutionStatusEnum.OPEN
    resolution_reason: str | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


class SeasonCompletenessReport(BaseModel):
    """Per-Season Coverage & Integrity Diagnostic Summary."""
    competition_code: str
    season_year: str
    total_matches: int
    expected_matches: int | None = None
    unique_teams: int
    matches_with_scores: int
    matches_missing_scores: int
    earliest_match: datetime | None = None
    latest_match: datetime | None = None
    blocking_findings_count: int = 0
    warning_findings_count: int = 0
    readiness_status: ReadinessStatusEnum = ReadinessStatusEnum.NOT_READY

    model_config = ConfigDict(arbitrary_types_allowed=True)


class FeatureReadinessReport(BaseModel):
    """Assessment of Source Data Availability for Upcoming Model Feature Modules."""
    feature_module_key: str
    feature_module_name: str
    prerequisites: list[str]
    status: ReadinessStatusEnum
    coverage_percentage: float
    limitations: list[str] = Field(default_factory=list)


class GlobalQualityReport(BaseModel):
    """System-wide Data Quality & MVP-A Readiness Assessment Summary."""
    total_competitions: int
    total_seasons: int
    total_matches: int
    total_teams: int
    total_findings: int
    blocking_count: int
    warning_count: int
    info_count: int
    global_status: ReadinessStatusEnum
    completeness_score: float
    chronology_score: float
    mapping_score: float
    integrity_score: float
    overall_quality_score: float
    season_reports: list[SeasonCompletenessReport] = Field(default_factory=list)
    feature_readiness: list[FeatureReadinessReport] = Field(default_factory=list)
