"""
Sprint 7.2 Competition, Team & Odds Isolation Policies
Enforces deterministic mapping for certified competitions (E0, SP1, I1, D1),
rejects unsupported leagues and fuzzy auto-matching, and guarantees strict odds exclusion.
"""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from app.automation.errors import ErrorCategory, OperationalException, Retryability

SUPPORTED_COMPETITIONS: dict[str, str] = {
    "E0": "Premier League",
    "SP1": "La Liga",
    "I1": "Serie A",
    "D1": "Bundesliga",
}

FORBIDDEN_ODDS_KEYS: set[str] = {
    "odds",
    "bookmakers",
    "bets",
    "betting",
    "markets",
    "prices",
    "lines",
    "spreads",
    "handicap",
    "b365",
    "bw",
    "iw",
    "ps",
    "wh",
    "vc",
    "market_max",
    "market_avg",
}


class UnsupportedCompetitionError(OperationalException):
    def __init__(self, raw_competition: str | int) -> None:
        super().__init__(
            ErrorCategory.DATA,
            Retryability.PERMANENT,
            "UNSUPPORTED_COMPETITION",
            f"Competition '{raw_competition}' is not within the certified domain (E0, SP1, I1, D1).",
            {"raw_competition": str(raw_competition)},
        )


class UnresolvedTeamMappingError(OperationalException):
    def __init__(self, provider_team_id: str, provider_team_name: str) -> None:
        super().__init__(
            ErrorCategory.DATA,
            Retryability.PERMANENT,
            "UNRESOLVED_TEAM_MAPPING",
            f"Team '{provider_team_name}' (ID: {provider_team_id}) cannot be mapped deterministically to a canonical entity.",
            {"provider_team_id": provider_team_id, "provider_team_name": provider_team_name},
        )


class ProviderCompetitionMapper:
    """Deterministic mapper from external provider league identifiers to canonical competition codes."""

    # Provider ID / Code to canonical code
    _EXPLICIT_MAPPING: dict[str, str] = {
        # Football-Data.org codes / IDs
        "2021": "E0",
        "PL": "E0",
        "PREMIER_LEAGUE": "E0",
        "PREMIER LEAGUE": "E0",
        "2014": "SP1",
        "PD": "SP1",
        "LA_LIGA": "SP1",
        "PRIMERA_DIVISION": "SP1",
        "LA LIGA": "SP1",
        "2019": "I1",
        "SA": "I1",
        "SERIE_A": "I1",
        "SERIE A": "I1",
        "2002": "D1",
        "BL1": "D1",
        "BUNDESLIGA": "D1",
        # Football-Data.co.uk codes
        "E0": "E0",
        "SP1": "SP1",
        "I1": "I1",
        "D1": "D1",
    }

    @classmethod
    def map_competition(cls, provider_competition_id_or_code: str | int) -> str:
        key = str(provider_competition_id_or_code).strip().upper()
        if key in cls._EXPLICIT_MAPPING:
            canonical = cls._EXPLICIT_MAPPING[key]
            if canonical in SUPPORTED_COMPETITIONS:
                return canonical
        raise UnsupportedCompetitionError(provider_competition_id_or_code)

    @classmethod
    def is_supported(cls, provider_competition_id_or_code: str | int) -> bool:
        key = str(provider_competition_id_or_code).strip().upper()
        return key in cls._EXPLICIT_MAPPING and cls._EXPLICIT_MAPPING[key] in SUPPORTED_COMPETITIONS


class ProviderTeamMapper:
    """
    Deterministic mapper for provider teams to canonical team entities.
    Strictly forbids fuzzy matching or silent auto-acceptance of unknown teams.
    """

    def __init__(self, explicit_mappings: dict[str, UUID] | None = None) -> None:
        # Key: "provider_name:provider_team_id" or "provider_team_id"
        self._mappings: dict[str, UUID] = dict(explicit_mappings or {})

    def register_mapping(self, provider_team_id: str, canonical_id: UUID) -> None:
        self._mappings[str(provider_team_id).strip()] = canonical_id

    def map_team(
        self,
        provider_team_id: str,
        provider_team_name: str,
        allow_unresolved: bool = False,
    ) -> UUID | None:
        """
        Deterministically resolve team identity.
        If unknown and allow_unresolved is False, raises UnresolvedTeamMappingError.
        """
        key = str(provider_team_id).strip()
        if key in self._mappings:
            return self._mappings[key]

        # Name fallback only if exact pre-registered alias exists (never fuzzy matching)
        clean_name = self._normalize_name(provider_team_name)
        if clean_name in self._mappings:
            return self._mappings[clean_name]

        if allow_unresolved:
            return None

        raise UnresolvedTeamMappingError(provider_team_id, provider_team_name)

    @staticmethod
    def _normalize_name(name: str) -> str:
        # Standard uppercase alphanumeric only
        return re.sub(r"[^A-Z0-9]", "", name.upper())


class OddsExclusionPolicy:
    """Audits raw payloads and ensures bookmaker odds are stripped and excluded from feature pipelines."""

    @classmethod
    def sanitize_payload(cls, raw_data: dict[str, Any]) -> dict[str, Any]:
        """Recursively removes any keys related to odds, betting markets, or bookmakers."""
        sanitized: dict[str, Any] = {}
        for k, v in raw_data.items():
            k_lower = k.lower()
            if any(forbidden in k_lower for forbidden in FORBIDDEN_ODDS_KEYS):
                continue
            if isinstance(v, dict):
                sanitized[k] = cls.sanitize_payload(v)
            elif isinstance(v, list):
                sanitized[k] = [cls.sanitize_payload(item) if isinstance(item, dict) else item for item in v]
            else:
                sanitized[k] = v
        return sanitized

    @classmethod
    def assert_no_odds(cls, payload: dict[str, Any]) -> None:
        for k in payload:
            k_lower = k.lower()
            if any(forbidden in k_lower for forbidden in FORBIDDEN_ODDS_KEYS):
                raise OperationalException(
                    ErrorCategory.SCIENTIFIC_INTEGRITY,
                    Retryability.PERMANENT,
                    "ODDS_CONTAMINATION_DETECTED",
                    f"Forbidden odds key '{k}' detected in sanitized provider observation.",
                )
