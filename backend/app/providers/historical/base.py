"""
Historical Data Provider Base Protocol & DTOs
Abstract interfaces, status enumerations, and data transfer containers for historical data acquisition.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class SourceStatusEnum(StrEnum):
    DECLARED = "DECLARED"
    AVAILABLE = "AVAILABLE"
    DOWNLOADING = "DOWNLOADING"
    ACQUIRED = "ACQUIRED"
    VALIDATED = "VALIDATED"
    FAILED = "FAILED"
    CHANGED = "CHANGED"
    UNCHANGED = "UNCHANGED"


class SourceSpecification(BaseModel):
    """Declarative specification for an intended historical source dataset."""
    provider_key: str
    competition_code: str
    season_year: str
    provider_competition_code: str
    provider_season_code: str
    source_url: str
    is_required: bool = True
    expected_sha256: str | None = None

    model_config = ConfigDict(frozen=True)

    @property
    def relative_path(self) -> str:
        return f"{self.provider_key}/{self.competition_code}/{self.season_year}/{self.provider_competition_code}.csv"


class SourceValidationResult(BaseModel):
    """Result emitted by source file structural validation."""
    is_valid: bool
    error_message: str | None = None
    file_size_bytes: int = 0
    header_columns: list[str] = Field(default_factory=list)
    schema_fingerprint: str | None = None


class AcquisitionResult(BaseModel):
    """Result object emitted following a source acquisition operation."""
    specification: SourceSpecification
    status: SourceStatusEnum
    local_path: str | None = None
    sha256_checksum: str | None = None
    file_size_bytes: int = 0
    message: str = ""
    metadata_payload: dict[str, Any] = Field(default_factory=dict)


class HistoricalDataProvider(Protocol):
    """Abstract protocol for historical data source providers."""
    provider_key: str
    display_name: str

    def resolve_source_url(self, competition_code: str, season_year: str) -> str:
        ...

    def validate_source_file(self, file_path: str) -> SourceValidationResult:
        ...
