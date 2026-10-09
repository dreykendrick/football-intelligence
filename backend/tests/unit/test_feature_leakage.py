"""
Unit Tests for Data Leakage Prevention & Cutoff Safety
Verifies target match outcome isolation, same-day DATE_ONLY exclusion, future match addition isolation, and past match responsiveness.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.db.models import Competition, Match, Season, Team
from app.features.query import PointInTimeQueryService


@pytest.mark.unit
def test_target_outcome_isolation(db_session: Session):
    """Verifies that target match result changes do not affect pre-match historical queries."""
    comp = Competition(code="LK_EPL", name="Premier League", country="England")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Arsenal LK")
    t2 = Team(canonical_name="Chelsea LK")

    now = datetime.now(UTC)
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=10), status="FINISHED", home_score=2, away_score=0)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="FINISHED", home_score=5, away_score=5)

    db_session.add_all([comp, season, t1, t2, m1, m_target])
    db_session.commit()

    service = PointInTimeQueryService(db_session, approved_only=False, enforce_date_only_precision=False)
    matches_before = service.get_team_matches_before(t1.id, cutoff_timestamp=now, target_match_id=m_target.id)

    assert len(matches_before) == 1
    assert matches_before[0].id == m1.id

    # Modify target score
    m_target.home_score = 0
    m_target.away_score = 1
    db_session.commit()

    matches_after = service.get_team_matches_before(t1.id, cutoff_timestamp=now, target_match_id=m_target.id)
    assert len(matches_after) == 1
    assert matches_after[0].id == m1.id


@pytest.mark.unit
def test_same_day_date_only_exclusion(db_session: Session):
    """Verifies that matches played on the exact same date as cutoff are excluded when enforce_date_only_precision=True."""
    comp = Competition(code="LK_SD", name="Same Day League", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Team SD 1")
    t2 = Team(canonical_name="Team SD 2")

    today = datetime(2024, 5, 1, 15, 0, tzinfo=UTC)
    m_earlier_today = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=today - timedelta(hours=3), status="FINISHED", home_score=1, away_score=0)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=today, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m_earlier_today, m_target])
    db_session.commit()

    service = PointInTimeQueryService(db_session, approved_only=False, enforce_date_only_precision=True)
    matches = service.get_team_matches_before(t1.id, cutoff_timestamp=today, target_match_id=m_target.id)

    # Same day match must be conservatively excluded under DATE_ONLY rule
    assert len(matches) == 0


@pytest.mark.unit
def test_future_match_addition_isolation(db_session: Session):
    """Verifies that matches scheduled in the future after cutoff are strictly excluded."""
    comp = Competition(code="LK_FUT", name="Future League", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Team Fut 1")
    t2 = Team(canonical_name="Team Fut 2")

    cutoff = datetime.now(UTC)
    m_past = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=cutoff - timedelta(days=5), status="FINISHED", home_score=1, away_score=1)
    m_future = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=cutoff + timedelta(days=5), status="FINISHED", home_score=3, away_score=0)

    db_session.add_all([comp, season, t1, t2, m_past, m_future])
    db_session.commit()

    service = PointInTimeQueryService(db_session, approved_only=False, enforce_date_only_precision=False)
    matches = service.get_team_matches_before(t1.id, cutoff_timestamp=cutoff)

    assert len(matches) == 1
    assert matches[0].id == m_past.id
