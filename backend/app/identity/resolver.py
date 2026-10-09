"""
Football Identity Resolver Pipeline
Multi-stage resolution pipeline executing explicit mappings, exact normalized name matches, alias lookups, and similarity candidate generation.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Provider, ProviderTeamMapping, Team, TeamAliasMapping
from app.identity.base import (
    IdentityCandidateDTO,
    IdentityResolutionResultDTO,
    ResolutionMethodEnum,
    ResolutionStatusEnum,
)
from app.identity.normalizer import IdentityNormalizer
from app.identity.similarity import SimilarityEngine


class FootballIdentityResolver:
    """Multi-Stage Football Identity Resolution Pipeline."""

    def __init__(self, db_session: Session, review_threshold: float = 0.70) -> None:
        self.db = db_session
        self.similarity_engine = SimilarityEngine(default_review_threshold=review_threshold)

    def resolve_team_identity(
        self,
        provider_key: str,
        external_name: str,
        country_context: str | None = None,
        auto_create_if_unambiguous: bool = True,
    ) -> IdentityResolutionResultDTO:
        clean_name = external_name.strip()
        norm_name = IdentityNormalizer.normalize_name(clean_name)

        if not clean_name:
            return IdentityResolutionResultDTO(
                provider_key=provider_key,
                external_identity=external_name,
                normalized_identity="",
                status=ResolutionStatusEnum.CONFLICT,
                message="External team name is empty or invalid.",
            )

        # Get or resolve Provider Record safely
        provider_id = None
        all_teams: list[Team] = []
        try:
            provider = self.db.query(Provider).filter_by(provider_key=provider_key).first()
            provider_id = provider.id if provider else None
            all_teams = self.db.query(Team).filter_by(is_active=True).all()
        except Exception:
            pass

        # STAGE 1: Explicit Provider Mapping Lookup
        if provider_id:
            try:
                existing_mapping = (
                    self.db.query(ProviderTeamMapping)
                    .filter_by(provider_id=provider_id, raw_alias=clean_name)
                    .first()
                )
                if existing_mapping and existing_mapping.team:
                    return IdentityResolutionResultDTO(
                        provider_key=provider_key,
                        external_identity=clean_name,
                        normalized_identity=norm_name,
                        canonical_id=existing_mapping.team.id,
                        canonical_name=existing_mapping.team.canonical_name,
                        status=ResolutionStatusEnum.RESOLVED_EXPLICIT_MAPPING,
                        resolution_method=ResolutionMethodEnum.EXPLICIT_PROVIDER_MAPPING,
                        message="Resolved via existing explicit provider mapping.",
                    )
            except Exception:
                pass

        # STAGE 2: Exact Canonical Normalized Name Match
        exact_matches = [
            t for t in all_teams
            if IdentityNormalizer.normalize_name(t.canonical_name) == norm_name
        ]

        if len(exact_matches) == 1:
            team = exact_matches[0]
            return IdentityResolutionResultDTO(
                provider_key=provider_key,
                external_identity=clean_name,
                normalized_identity=norm_name,
                canonical_id=team.id,
                canonical_name=team.canonical_name,
                status=ResolutionStatusEnum.RESOLVED_EXACT_NAME,
                resolution_method=ResolutionMethodEnum.EXACT_CANONICAL_NAME,
                message="Resolved via exact normalized canonical team name match.",
            )
        elif len(exact_matches) > 1:
            candidates = [
                IdentityCandidateDTO(
                    canonical_id=t.id,
                    canonical_name=t.canonical_name,
                    similarity_score=1.0,
                    match_reason="Exact normalized name conflict",
                )
                for t in exact_matches
            ]
            return IdentityResolutionResultDTO(
                provider_key=provider_key,
                external_identity=clean_name,
                normalized_identity=norm_name,
                status=ResolutionStatusEnum.CONFLICT,
                candidates=candidates,
                message="Ambiguous exact matches found across multiple canonical teams.",
            )

        # STAGE 3: Exact Known Alias Match
        try:
            alias_mapping = (
                self.db.query(TeamAliasMapping)
                .filter(TeamAliasMapping.raw_alias == clean_name)
                .first()
            )
            if alias_mapping and alias_mapping.team:
                return IdentityResolutionResultDTO(
                    provider_key=provider_key,
                    external_identity=clean_name,
                    normalized_identity=norm_name,
                    canonical_id=alias_mapping.team.id,
                    canonical_name=alias_mapping.team.canonical_name,
                    status=ResolutionStatusEnum.RESOLVED_ALIAS,
                    resolution_method=ResolutionMethodEnum.EXACT_ALIAS,
                    message="Resolved via exact known team alias mapping.",
                )
        except Exception:
            pass

        # STAGE 4: Similarity Candidate Generation
        team_tuples = [(t.id, t.canonical_name) for t in all_teams]
        candidates = self.similarity_engine.find_candidates(clean_name, team_tuples)

        if candidates:
            return IdentityResolutionResultDTO(
                provider_key=provider_key,
                external_identity=clean_name,
                normalized_identity=norm_name,
                status=ResolutionStatusEnum.REVIEW_REQUIRED,
                resolution_method=ResolutionMethodEnum.CANDIDATE_SIMILARITY,
                candidates=candidates,
                message=f"Similarity candidates found ({len(candidates)} candidates). Review required.",
            )

        # STAGE 5: New Canonical Entity Creation (if unambiguous & allowed)
        if auto_create_if_unambiguous:
            try:
                new_team = Team(
                    canonical_name=clean_name,
                    short_name=clean_name,
                    country=country_context or "Unknown",
                    is_active=True,
                )
                self.db.add(new_team)
                self.db.flush()

                if provider_id:
                    mapping = ProviderTeamMapping(
                        provider_id=provider_id,
                        team_id=new_team.id,
                        raw_alias=clean_name,
                        normalized_alias=norm_name,
                    )
                    self.db.add(mapping)
                    self.db.flush()

                return IdentityResolutionResultDTO(
                    provider_key=provider_key,
                    external_identity=clean_name,
                    normalized_identity=norm_name,
                    canonical_id=new_team.id,
                    canonical_name=new_team.canonical_name,
                    status=ResolutionStatusEnum.NEW_CANONICAL_ENTITY,
                    resolution_method=ResolutionMethodEnum.NEW_ENTITY_CREATED,
                    message="No existing candidate found; created new canonical team entity.",
                )
            except Exception as e:
                return IdentityResolutionResultDTO(
                    provider_key=provider_key,
                    external_identity=clean_name,
                    normalized_identity=norm_name,
                    status=ResolutionStatusEnum.CONFLICT,
                    message=f"Failed to create new canonical team: {e}",
                )

        return IdentityResolutionResultDTO(
            provider_key=provider_key,
            external_identity=clean_name,
            normalized_identity=norm_name,
            status=ResolutionStatusEnum.REVIEW_REQUIRED,
            message="No candidates found and auto-creation disabled.",
        )
