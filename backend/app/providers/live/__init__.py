"""
Live Football Data Provider Module (Sprint 7.2)
Exposes protocols, clients, mappers, and pipeline adapters for live shadow operations.
"""
from app.providers.live.adapter import LiveIngestionAdapter
from app.providers.live.base import (
    LiveFixtureDTO,
    LiveFixtureStatus,
    LiveFootballDataProvider,
    LiveResultDTO,
    ProviderRateLimitState,
    compute_payload_fingerprint,
)
from app.providers.live.client import DEFAULT_BASE_URL, LiveFootballDataClient
from app.providers.live.mapping import (
    SUPPORTED_COMPETITIONS,
    OddsExclusionPolicy,
    ProviderCompetitionMapper,
    ProviderTeamMapper,
    UnresolvedTeamMappingError,
    UnsupportedCompetitionError,
)

__all__ = [
    "LiveFootballDataProvider",
    "LiveFixtureDTO",
    "LiveResultDTO",
    "LiveFixtureStatus",
    "ProviderRateLimitState",
    "compute_payload_fingerprint",
    "LiveFootballDataClient",
    "DEFAULT_BASE_URL",
    "LiveIngestionAdapter",
    "SUPPORTED_COMPETITIONS",
    "ProviderCompetitionMapper",
    "ProviderTeamMapper",
    "UnsupportedCompetitionError",
    "UnresolvedTeamMappingError",
    "OddsExclusionPolicy",
]
