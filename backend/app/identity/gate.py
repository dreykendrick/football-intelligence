"""
Identity Readiness Gate & Verifier
Provides assertion gates verifying team identity completeness, provider mapping uniqueness, and absence of identity conflicts.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import ProviderTeamMapping, Team
from app.identity.base import IdentityAuditSummaryDTO, ResolutionStatusEnum
from app.identity.normalizer import IdentityNormalizer
from app.identity.similarity import SimilarityEngine


class IdentityReadinessGateException(RuntimeError):
    """Exception raised when Identity Readiness Gate fails."""


class IdentityReadinessGate:
    """Football Identity Verification & Readiness Gate."""

    @classmethod
    def audit_database(cls, db: Session, similarity_threshold: float = 0.85) -> IdentityAuditSummaryDTO:
        teams = db.query(Team).filter_by(is_active=True).all()
        mappings = db.query(ProviderTeamMapping).all()

        warnings: list[str] = []

        # 1. Exact Duplicate Canonical Names
        name_counts: dict[str, list[Team]] = {}
        for t in teams:
            norm = IdentityNormalizer.normalize_name(t.canonical_name)
            name_counts.setdefault(norm, []).append(t)

        exact_duplicates = [norm for norm, t_list in name_counts.items() if len(t_list) > 1]
        if exact_duplicates:
            warnings.append(f"Found {len(exact_duplicates)} exact duplicate normalized canonical team name(s): {', '.join(exact_duplicates)}")

        # 2. Conflicting Provider Mappings (1 raw alias mapping to multiple teams)
        conflict_query = (
            db.query(ProviderTeamMapping.provider_id, ProviderTeamMapping.raw_alias, func.count(ProviderTeamMapping.team_id))
            .group_by(ProviderTeamMapping.provider_id, ProviderTeamMapping.raw_alias)
            .having(func.count(ProviderTeamMapping.team_id) > 1)
            .all()
        )
        if conflict_query:
            warnings.append(f"Found {len(conflict_query)} provider team mapping conflict(s) (single raw alias mapping to multiple teams).")

        # 3. High Similarity Candidates between Canonical Teams
        sim_engine = SimilarityEngine(default_review_threshold=similarity_threshold)
        team_tuples = [(t.id, t.canonical_name) for t in teams]
        potential_duplicates = 0

        for i, (_t1_id, t1_name) in enumerate(team_tuples):
            for _t2_id, t2_name in team_tuples[i + 1:]:
                score = sim_engine.calculate_similarity(t1_name, t2_name)
                if score >= similarity_threshold:
                    potential_duplicates += 1
                    if len(warnings) < 10:
                        warnings.append(f"Potential duplicate teams: '{t1_name}' vs '{t2_name}' (similarity {score:.2f})")

        status = ResolutionStatusEnum.RESOLVED_EXACT_NAME if not exact_duplicates and not conflict_query else ResolutionStatusEnum.CONFLICT

        return IdentityAuditSummaryDTO(
            canonical_teams_count=len(teams),
            provider_mappings_count=len(mappings),
            exact_duplicate_names_count=len(exact_duplicates),
            potential_duplicate_teams_count=potential_duplicates,
            mapping_conflicts_count=len(conflict_query),
            unresolved_identities_count=0,
            status=status,
            warnings=warnings,
        )

    @classmethod
    def evaluate_gate(cls, db: Session, similarity_threshold: float = 0.85):
        """Evaluates identity gate status returning structured readiness assessment."""
        audit = cls.audit_database(db, similarity_threshold=similarity_threshold)
        from app.quality.base import ReadinessStatusEnum

        if audit.exact_duplicate_names_count > 0 or audit.mapping_conflicts_count > 0:
            overall_status = ReadinessStatusEnum.NOT_READY
        elif audit.potential_duplicate_teams_count > 0:
            overall_status = ReadinessStatusEnum.READY_WITH_WARNINGS
        else:
            overall_status = ReadinessStatusEnum.READY

        class IdentityGateReport:
            def __init__(self, overall_status, audit):
                self.overall_status = overall_status
                self.audit = audit

        return IdentityGateReport(overall_status, audit)

    @classmethod
    def assert_identity_ready(cls, db: Session, similarity_threshold: float = 0.85) -> IdentityAuditSummaryDTO:
        audit = cls.audit_database(db, similarity_threshold=similarity_threshold)

        if audit.exact_duplicate_names_count > 0 or audit.mapping_conflicts_count > 0:
            err_msg = "Identity Readiness Gate FAILED!\n"
            if audit.exact_duplicate_names_count > 0:
                err_msg += f"  - Exact Duplicate Canonical Names: {audit.exact_duplicate_names_count}\n"
            if audit.mapping_conflicts_count > 0:
                err_msg += f"  - Conflicting Provider Mappings: {audit.mapping_conflicts_count}\n"
            for w in audit.warnings:
                err_msg += f"  - Warning: {w}\n"
            raise IdentityReadinessGateException(err_msg)

        return audit
