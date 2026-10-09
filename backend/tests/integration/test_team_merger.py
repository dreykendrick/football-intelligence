"""
Integration Tests for Team Identity Merger Utility
Verifies reference migration, conflict detection, and transactional rollback on merge.
"""
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.db.models import Competition, Match, Provider, ProviderTeamMapping, Season, Team
from app.identity.merger import TeamIdentityMerger, TeamMergeConflictException


@pytest.mark.integration
def test_successful_team_merge_migrates_references(db_session: Session):
    provider = Provider(provider_key="football_data_co_uk", display_name="Football Data")
    comp = Competition(code="EPL", name="English Premier League", country="England")
    db_session.add_all([provider, comp])
    db_session.flush()

    season = Season(competition_id=comp.id, season_year="2023/2024")
    team_a = Team(canonical_name="Manchester United", country="England")
    team_b = Team(canonical_name="Man United", country="England")  # Duplicate
    opponent = Team(canonical_name="Chelsea", country="England")
    db_session.add_all([season, team_a, team_b, opponent])
    db_session.flush()

    match_b = Match(
        season_id=season.id,
        home_team_id=team_b.id,
        away_team_id=opponent.id,
        kickoff_utc=datetime.now(UTC),
        status="FINISHED",
    )
    mapping_b = ProviderTeamMapping(provider_id=provider.id, team_id=team_b.id, raw_alias="Man Utd")
    db_session.add_all([match_b, mapping_b])
    db_session.flush()

    merger = TeamIdentityMerger(db_session)
    res = merger.merge_teams(team_b.id, team_a.id, reason="Deduplication test")
    db_session.flush()

    assert res["home_matches_migrated"] == 1
    assert match_b.home_team_id == team_a.id
    assert team_b.is_active is False
    assert team_b.short_code == "MERGED"


@pytest.mark.integration
def test_team_merge_aborts_on_direct_head_to_head_conflict(db_session: Session):
    comp = Competition(code="EPL", name="English Premier League", country="England")
    db_session.add(comp)
    db_session.flush()

    season = Season(competition_id=comp.id, season_year="2023/2024")
    team_a = Team(canonical_name="Manchester United", country="England")
    team_b = Team(canonical_name="Man United", country="England")
    db_session.add_all([season, team_a, team_b])
    db_session.flush()

    # Direct match between team_a and team_b (invalid merge!)
    conflict_match = Match(
        season_id=season.id,
        home_team_id=team_a.id,
        away_team_id=team_b.id,
        kickoff_utc=datetime.now(UTC),
        status="FINISHED",
    )
    db_session.add(conflict_match)
    db_session.flush()

    merger = TeamIdentityMerger(db_session)
    with pytest.raises(TeamMergeConflictException, match="direct head-to-head match"):
        merger.merge_teams(team_b.id, team_a.id)
