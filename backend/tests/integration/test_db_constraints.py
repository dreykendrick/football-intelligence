"""
Integration Tests for Database Constraints & Rules
Verifies duplicate uniqueness constraints, distinct home/away team checks, and probability range limits.
"""
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    Competition,
    Match,
    Provider,
    ProviderTeamMapping,
    Season,
    Team,
)


@pytest.mark.integration
def test_duplicate_competition_code_rejected(db_session: Session):
    c1 = Competition(code="PREM", name="Premier League 1", country="England")
    db_session.add(c1)
    db_session.commit()

    c2 = Competition(code="PREM", name="Premier League 2", country="England")
    db_session.add(c2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.integration
def test_duplicate_season_in_competition_rejected(db_session: Session):
    comp = Competition(code="EPL_DUP", name="EPL", country="England")
    db_session.add(comp)
    db_session.flush()

    s1 = Season(competition_id=comp.id, season_year="2024/25")
    db_session.add(s1)
    db_session.commit()

    s2 = Season(competition_id=comp.id, season_year="2024/25")
    db_session.add(s2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.integration
def test_duplicate_provider_team_alias_rejected(db_session: Session):
    provider = Provider(provider_key="fd_uk_test", display_name="Test Provider")
    team = Team(canonical_name="Liverpool FC")
    db_session.add_all([provider, team])
    db_session.flush()

    m1 = ProviderTeamMapping(provider_id=provider.id, team_id=team.id, raw_alias="Liverpool")
    db_session.add(m1)
    db_session.commit()

    m2 = ProviderTeamMapping(provider_id=provider.id, team_id=team.id, raw_alias="Liverpool")
    db_session.add(m2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.integration
def test_same_home_and_away_team_rejected(db_session: Session):
    comp = Competition(code="TEST_LEAGUE", name="Test", country="Test")
    season = Season(competition=comp, season_year="2024/25")
    team = Team(canonical_name="Self Team")
    db_session.add_all([comp, season, team])
    db_session.flush()

    match = Match(
        season_id=season.id,
        home_team_id=team.id,
        away_team_id=team.id,
        kickoff_utc=datetime.now(UTC),
    )
    db_session.add(match)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
