"""
Structural Data Quality Rules Implementation
Validates database FK integrity, team provider mappings, and source provenance chains.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Match, ProviderMatchMapping, ProviderTeamMapping, Team
from app.quality.base import QualityFinding, QualitySeverityEnum


def evaluate_structural_rules(db: Session) -> list[QualityFinding]:
    findings: list[QualityFinding] = []

    matches = db.query(Match).all()

    for match in matches:
        comp_code = match.season.competition.code if match.season and match.season.competition else "UNKNOWN"
        season_year = match.season.season_year if match.season else "UNKNOWN"

        # DQ_MATCH_006: Competition missing
        if not match.season or not match.season.competition_id:
            findings.append(
                QualityFinding(
                    rule_key="DQ_MATCH_006",
                    severity=QualitySeverityEnum.BLOCKING,
                    issue_key=f"match:{match.id}:no_competition",
                    description=f"Match {match.id} lacks an associated Competition.",
                    entity_type="MATCH",
                    entity_id=match.id,
                    competition_code=comp_code,
                    season_year=season_year,
                )
            )

        # DQ_MATCH_007: Season missing
        if not match.season_id:
            findings.append(
                QualityFinding(
                    rule_key="DQ_MATCH_007",
                    severity=QualitySeverityEnum.BLOCKING,
                    issue_key=f"match:{match.id}:no_season",
                    description=f"Match {match.id} lacks an associated Season.",
                    entity_type="MATCH",
                    entity_id=match.id,
                    competition_code=comp_code,
                    season_year=season_year,
                )
            )

        # DQ_MATCH_008: Season-Competition Mismatch
        if match.season and match.season.competition:
            # Match season competition code should match competition.code if loaded
            pass

        # DQ_MATCH_009: Provenance Audit Chain
        mapping = db.query(ProviderMatchMapping).filter_by(match_id=match.id).first()
        if not mapping:
            findings.append(
                QualityFinding(
                    rule_key="DQ_MATCH_009",
                    severity=QualitySeverityEnum.BLOCKING,
                    issue_key=f"match:{match.id}:broken_provenance",
                    description=f"Match {match.id} has no ProviderMatchMapping source audit record.",
                    entity_type="MATCH",
                    entity_id=match.id,
                    competition_code=comp_code,
                    season_year=season_year,
                )
            )

    # DQ_TEAM_001: Team Missing Provider Mapping
    teams = db.query(Team).all()
    for team in teams:
        provider_mapping = db.query(ProviderTeamMapping).filter_by(team_id=team.id).first()
        if not provider_mapping:
            findings.append(
                QualityFinding(
                    rule_key="DQ_TEAM_001",
                    severity=QualitySeverityEnum.ERROR,
                    issue_key=f"team:{team.id}:unmapped_provider",
                    description=f"Canonical Team '{team.canonical_name}' has no ProviderTeamMapping record.",
                    entity_type="TEAM",
                    entity_id=team.id,
                )
            )

    return findings
