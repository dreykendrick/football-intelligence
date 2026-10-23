"""
Sprint 7.2 Live Football Data Provider Base Protocol & DTOs
Defines data contracts, transfer containers, rate limit states, and provider protocols
for unattended live fixture and result ingestion.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID


class LiveFixtureStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    TIMED = "TIMED"
    IN_PLAY = "IN_PLAY"
    PAUSED = "PAUSED"
    FINISHED = "FINISHED"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"
    SUSPENDED = "SUSPENDED"


@dataclass(frozen=True)
class ProviderRateLimitState:
    """Tracks provider quota usage and reset countdowns."""
    remaining: int | None = None
    reset_seconds: int | None = None
    limit: int | None = None
    last_checked_at: datetime | None = None

    @property
    def is_rate_limited(self) -> bool:
        return self.remaining is not None and self.remaining <= 0


@dataclass
class LiveFixtureDTO:
    """Canonical DTO for a live upcoming or updated fixture retrieved from external provider."""
    provider_fixture_id: str
    provider_name: str
    provider_competition_id: str
    competition_code: str  # E0, SP1, I1, D1
    season_year: str
    provider_home_team_id: str
    provider_home_team_name: str
    provider_away_team_id: str
    provider_away_team_name: str
    canonical_home_team_id: UUID | None
    canonical_away_team_id: UUID | None
    kickoff_utc: datetime
    status: LiveFixtureStatus
    retrieved_at_utc: datetime
    payload_fingerprint: str
    provider_updated_at: datetime | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class LiveResultDTO:
    """Canonical DTO for a finalized or corrected match outcome."""
    provider_fixture_id: str
    provider_name: str
    status: LiveFixtureStatus
    home_score: int | None
    away_score: int | None
    is_final: bool
    result_version: int
    retrieved_at_utc: datetime
    payload_fingerprint: str
    raw_payload: dict[str, Any] = field(default_factory=dict)


def compute_payload_fingerprint(payload: dict[str, Any] | list[Any] | str) -> str:
    """Deterministic SHA-256 hash of raw provider observation."""
    if isinstance(payload, (dict, list)):
        payload_bytes = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    else:
        payload_bytes = str(payload).encode("utf-8")
    return hashlib.sha256(payload_bytes).hexdigest()


class LiveFootballDataProvider(Protocol):
    """Abstract protocol for live football data provider adapters."""

    @property
    def provider_name(self) -> str:
        ...

    @property
    def api_key(self) -> str | None:
        ...

    def get_upcoming_fixtures(
        self,
        competition_codes: list[str] | None = None,
        days_ahead: int = 7,
    ) -> list[LiveFixtureDTO]:
        """Fetch real upcoming fixtures for supported competitions."""
        ...

    def get_fixture_results(
        self,
        provider_fixture_ids: list[str],
    ) -> list[LiveResultDTO]:
        """Fetch finalized or updated match scores."""
        ...

    def get_rate_limit_state(self) -> ProviderRateLimitState:
        """Return current known rate limit quota state."""
        ...

    def health_check(self) -> dict[str, Any]:
        """Perform non-destructive connectivity and authentication verification."""
        ...
