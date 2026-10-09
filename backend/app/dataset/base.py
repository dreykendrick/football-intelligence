"""
Dataset Domain Enums, Exceptions, and Data Transfer Objects.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class DatasetReleaseStatusEnum(str, Enum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"
    RETIRED = "RETIRED"
    FAILED = "FAILED"


class DatasetSelectionPolicyEnum(str, Enum):
    MVP_A_RECENT_3_USABLE_SEASONS_V1 = "mvp_a_recent_3_usable_seasons_v1"
    EXPLICIT_OVERRIDE = "explicit_override"


# --- Typed Domain Exceptions ---

class DatasetAssemblyError(RuntimeError):
    """Base exception for all historical dataset release assembly errors."""


class InsufficientCoverageError(DatasetAssemblyError):
    """Raised when target competition season count is below minimum required threshold (e.g. < 3)."""


class BlockedSeasonError(DatasetAssemblyError):
    """Raised when an attempt is made to include a season with BLOCKED quality status into an official dataset release."""


class SourceIntegrityError(DatasetAssemblyError):
    """Raised when raw source file checksum fails verification against historical source catalog."""


class DatasetValidationError(DatasetAssemblyError):
    """Raised when dataset candidate fails validation rules prior to approval."""


class DatasetFingerprintMismatchError(DatasetAssemblyError):
    """Raised when dataset release re-computed fingerprint does not match locked fingerprint."""


class DatasetAlreadyApprovedError(DatasetAssemblyError):
    """Raised when attempting to approve an already approved dataset release."""


class ImmutableDatasetError(DatasetAssemblyError):
    """Raised when an illegal mutation attempt is performed on an APPROVED dataset release."""


# --- Pydantic Data Transfer Objects ---

class DatasetSeasonDTO(BaseModel):
    id: UUID | None = None
    competition_id: UUID
    season_id: UUID
    competition_code: str
    season_year: str
    readiness_status: str
    match_count: int
    expected_matches: int | None = None
    source_provider_key: str | None = None
    source_reference: str | None = None
    source_checksum: str | None = None
    metadata_payload: dict | None = None


class DatasetMatchDTO(BaseModel):
    id: UUID | None = None
    match_id: UUID
    competition_id: UUID
    season_id: UUID
    kickoff_utc: datetime
    home_team_id: UUID
    away_team_id: UUID
    ingestion_batch_id: UUID | None = None
    raw_source_checksum: str | None = None


class DatasetExclusionDTO(BaseModel):
    id: UUID | None = None
    match_id: UUID
    competition_code: str
    season_year: str
    exclusion_reason: str
    quality_rule_key: str | None = None
    metadata_payload: dict | None = None


class DatasetReleaseDTO(BaseModel):
    id: UUID
    key: str
    version: str
    description: str | None = None
    status: DatasetReleaseStatusEnum
    selection_policy_key: str
    selection_policy_version: str
    total_competitions: int
    total_seasons: int
    total_matches: int
    dataset_fingerprint: str | None = None
    quality_run_id: UUID | None = None
    quality_status: str
    identity_readiness_status: str
    warning_acceptances: dict | None = None
    metadata_payload: dict | None = None
    approved_at: datetime | None = None
    supersedes_dataset_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    seasons: list[DatasetSeasonDTO] = Field(default_factory=list)


class DatasetCoverageMatrixRow(BaseModel):
    competition_code: str
    competition_name: str
    season_year: str
    matches: int
    expected_matches: int | None = None
    quality_status: str
    source_checksum: str | None = None
    included: bool


class DatasetBuildReport(BaseModel):
    dataset_key: str
    version: str
    status: DatasetReleaseStatusEnum
    selection_policy_key: str
    total_competitions: int
    total_seasons: int
    total_matches: int
    total_excluded_matches: int
    fingerprint: str | None = None
    quality_status: str
    identity_readiness_status: str
    coverage_matrix: list[DatasetCoverageMatrixRow] = Field(default_factory=list)
    warnings_accepted: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)


class DatasetValidationReport(BaseModel):
    dataset_key: str
    version: str
    is_valid: bool
    status: DatasetReleaseStatusEnum
    target_competitions_count: int
    total_seasons_count: int
    total_matches_count: int
    checks_passed: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
