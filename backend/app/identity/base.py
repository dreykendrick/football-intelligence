"""
Football Identity Resolution DTOs & Enumerations
Data structures, resolution statuses, resolution methods, and candidate containers.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ResolutionStatusEnum(StrEnum):
    RESOLVED_EXPLICIT_MAPPING = "RESOLVED_EXPLICIT_MAPPING"
    RESOLVED_EXACT_NAME = "RESOLVED_EXACT_NAME"
    RESOLVED_ALIAS = "RESOLVED_ALIAS"
    NEW_CANONICAL_ENTITY = "NEW_CANONICAL_ENTITY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    CONFLICT = "CONFLICT"


class ResolutionMethodEnum(StrEnum):
    EXPLICIT_PROVIDER_MAPPING = "EXPLICIT_PROVIDER_MAPPING"
    EXACT_CANONICAL_NAME = "EXACT_CANONICAL_NAME"
    EXACT_ALIAS = "EXACT_ALIAS"
    MANUAL_MAPPING = "MANUAL_MAPPING"
    NEW_ENTITY_CREATED = "NEW_ENTITY_CREATED"
    CANDIDATE_SIMILARITY = "CANDIDATE_SIMILARITY"


class IdentityCandidateDTO(BaseModel):
    """Candidate canonical entity proposed during similarity matching."""
    canonical_id: UUID
    canonical_name: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    match_reason: str

    model_config = ConfigDict(frozen=True)


class IdentityResolutionResultDTO(BaseModel):
    """Resolution outcome container for a provider identity."""
    provider_key: str
    external_identity: str
    normalized_identity: str
    canonical_id: UUID | None = None
    canonical_name: str | None = None
    status: ResolutionStatusEnum
    resolution_method: ResolutionMethodEnum | None = None
    candidates: list[IdentityCandidateDTO] = Field(default_factory=list)
    message: str = ""
    metadata_payload: dict[str, Any] = Field(default_factory=dict)


class IdentityAuditSummaryDTO(BaseModel):
    """Human-readable identity audit summary container."""
    canonical_teams_count: int = 0
    provider_mappings_count: int = 0
    exact_duplicate_names_count: int = 0
    potential_duplicate_teams_count: int = 0
    mapping_conflicts_count: int = 0
    unresolved_identities_count: int = 0
    status: ResolutionStatusEnum = ResolutionStatusEnum.RESOLVED_EXACT_NAME
    warnings: list[str] = Field(default_factory=list)
