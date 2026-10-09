"""
Unit Tests for MVP-A Feature Calculators
Verifies numerical logic for goal rates, attack/defense strength, recent form, baseline Elo, and rest days.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.db.models import Competition, Match, Season, Team
from app.features.calculators.elo import EloRatingEngine
from app.features.calculators.form import HomeRecentPPGCalculator
from app.features.calculators.goals import HomeGoalsScoredAvgCalculator
from app.features.calculators.rest_congestion import HomeRestDaysCalculator


@pytest.mark.unit
def test_home_goals_scored_avg_calculator(db_session: Session):
    comp = Competition(code="GOAL_C", name="Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Home Team G")
    t2 = Team(canonical_name="Away Team G")

    now = datetime.now(UTC)
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=10), status="FINISHED", home_score=3, away_score=0)
    m2 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=1, away_score=1)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m1, m2, m_target])
    db_session.flush()

    calc = HomeGoalsScoredAvgCalculator()
    res = calc.calculate(db_session, m_target, cutoff_timestamp=now)

    assert res.is_missing is False
    assert res.value == 2.0  # (3 + 1) / 2
    assert res.sample_size == 2


@pytest.mark.unit
def test_recent_form_ppg_calculator(db_session: Session):
    comp = Competition(code="FORM_C", name="Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Form Team A")
    t2 = Team(canonical_name="Form Team B")

    now = datetime.now(UTC)
    # Win (3 pts), Draw (1 pt), Loss (0 pts) -> 4 pts / 3 games = 1.3333
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=15), status="FINISHED", home_score=2, away_score=0)
    m2 = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now - timedelta(days=10), status="FINISHED", home_score=1, away_score=1)
    m3 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=0, away_score=1)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m1, m2, m3, m_target])
    db_session.flush()

    calc = HomeRecentPPGCalculator()
    res = calc.calculate(db_session, m_target, cutoff_timestamp=now)

    assert res.is_missing is False
    assert res.value == 1.3333
    assert res.sample_size == 3


@pytest.mark.unit
def test_elo_rating_engine_chronological_update(db_session: Session):
    comp = Competition(code="ELO_C", name="Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Elo Team A")
    t2 = Team(canonical_name="Elo Team B")

    now = datetime.now(UTC)
    # Match 1: t1 wins at home -> t1 rating increases from 1500
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=2, away_score=0)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m1, m_target])
    db_session.flush()

    ratings, _ = EloRatingEngine.compute_team_ratings_before(
        db_session, competition_id=comp.id, cutoff_timestamp=now
    )
    assert ratings[t1.id] > 1500.0
    assert ratings[t2.id] < 1500.0


@pytest.mark.unit
def test_rest_days_calculator(db_session: Session):
    comp = Competition(code="REST_C", name="Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Rest Team A")
    t2 = Team(canonical_name="Rest Team B")

    now = datetime.now(UTC)
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=4), status="FINISHED", home_score=1, away_score=0)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m1, m_target])
    db_session.flush()

    calc = HomeRestDaysCalculator()
    res = calc.calculate(db_session, m_target, cutoff_timestamp=now)

    assert res.is_missing is False
    assert res.value == 4.0
