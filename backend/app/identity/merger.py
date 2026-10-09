"""
Team Identity Merger Utility
Safely merges duplicate canonical teams with full match reference migration, conflict prevention, and audit tracking.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import (
    Match,
    MatchStatistic,
    ProviderTeamMapping,
    SystemAuditLog,
    Team,
    TeamAliasMapping,
)


class TeamMergeConflictException(RuntimeError):
    """Exception raised when a team merge operation encounters a safety conflict."""


class TeamIdentityMerger:
    """Safe Transactional Team Merge Engine."""

    def __init__(self, db_session: Session) -> None:
        self.db = db_session

    def merge_teams(
        self, source_team_id: UUID, target_team_id: UUID, reason: str = "Manual deduplication merge"
    ) -> dict[str, int]:
        if source_team_id == target_team_id:
            raise TeamMergeConflictException("Source team ID and target team ID must be distinct.")

        source_team = self.db.query(Team).filter_by(id=source_team_id).first()
        target_team = self.db.query(Team).filter_by(id=target_team_id).first()

        if not source_team or not target_team:
            raise TeamMergeConflictException("Source or target team record not found.")

        # 1. Safety Assertion: Check for matches where home and away are source & target
        direct_conflicts = (
            self.db.query(Match)
            .filter(
                ((Match.home_team_id == source_team_id) & (Match.away_team_id == target_team_id))
                | ((Match.home_team_id == target_team_id) & (Match.away_team_id == source_team_id))
            )
            .count()
        )
        if direct_conflicts > 0:
            raise TeamMergeConflictException(
                f"Merge aborted! Source team '{source_team.canonical_name}' and target team '{target_team.canonical_name}' have {direct_conflicts} direct head-to-head match(es)."
            )

        # 2. Migrate Match Home Team References
        home_matches = self.db.query(Match).filter_by(home_team_id=source_team_id).all()
        for m in home_matches:
            m.home_team_id = target_team_id

        # 3. Migrate Match Away Team References
        away_matches = self.db.query(Match).filter_by(away_team_id=source_team_id).all()
        for m in away_matches:
            m.away_team_id = target_team_id

        # 4. Migrate Match Statistics References
        stats = self.db.query(MatchStatistic).filter_by(team_id=source_team_id).all()
        for s in stats:
            s.team_id = target_team_id

        # 5. Migrate Provider Team Mappings
        provider_mappings = self.db.query(ProviderTeamMapping).filter_by(team_id=source_team_id).all()
        migrated_mappings_count = 0
        for pm in provider_mappings:
            existing = (
                self.db.query(ProviderTeamMapping)
                .filter_by(provider_id=pm.provider_id, team_id=target_team_id, raw_alias=pm.raw_alias)
                .first()
            )
            if not existing:
                pm.team_id = target_team_id
                migrated_mappings_count += 1
            else:
                self.db.delete(pm)

        # 6. Migrate Team Alias Mappings
        alias_mappings = self.db.query(TeamAliasMapping).filter_by(team_id=source_team_id).all()
        for am in alias_mappings:
            existing = (
                self.db.query(TeamAliasMapping)
                .filter_by(provider_name=am.provider_name, team_id=target_team_id, raw_alias=am.raw_alias)
                .first()
            )
            if not existing:
                am.team_id = target_team_id
            else:
                self.db.delete(am)

        # 7. Add Alias mapping for source canonical name on target team
        canonical_alias = (
            self.db.query(TeamAliasMapping)
            .filter_by(provider_name="canonical_merge", raw_alias=source_team.canonical_name)
            .first()
        )
        if not canonical_alias:
            self.db.add(
                TeamAliasMapping(
                    team_id=target_team_id,
                    provider_name="canonical_merge",
                    raw_alias=source_team.canonical_name,
                )
            )

        # 8. Deactivate Source Team (Soft Merge - Preserving History)
        source_team.is_active = False
        source_team.short_code = "MERGED"

        # 9. Audit Log Entry
        audit = SystemAuditLog(
            event_type="TEAM_MERGE",
            description=f"Merged team '{source_team.canonical_name}' ({source_team.id}) into '{target_team.canonical_name}' ({target_team.id}). Reason: {reason}",
        )
        self.db.add(audit)

        self.db.flush()

        return {
            "home_matches_migrated": len(home_matches),
            "away_matches_migrated": len(away_matches),
            "statistics_migrated": len(stats),
            "provider_mappings_migrated": migrated_mappings_count,
        }
