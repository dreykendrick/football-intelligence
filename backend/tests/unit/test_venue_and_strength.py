"""
Unit Tests for Sprint 3.3 - Home/Away & Strength Features
Verifies venue filtering, point-in-time league baselines, attack/defense strength ratios, zero-denominator safety, and final-season contamination isolation.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.db.models import Competition, Match, Season, Team
from app.features.base import MissingnessReason
from app.features.calculators.attack_defense import (
    AwayAttackStrengthCalculator,
    AwayDefenseStrengthCalculator,
    HomeAttackStrengthCalculator,
    HomeDefenseStrengthCalculator,
    LeagueAwayGoalsAvgCalculator,
    LeagueHomeGoalsAvgCalculator,
)
from app.features.calculators.venue_calculators import generate_venue_form_calculators


@pytest.mark.unit
def test_venue_filtering(db_session: Session):
    """Verifies that home venue calculators filter ONLY home matches and away venue calculators filter ONLY away matches."""
    comp = Competition(code="VFILT_EPL", name="Premier League", country="England")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Arsenal Venue")
    t2 = Team(canonical_name="Chelsea Venue")

    now = datetime.now(UTC)
    # t1 Home matches: 2-0, 3-1, 1-0 (3 matches, 6 GS, 1 GC, 9 pts)
    m_h1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=25), status="FINISHED", home_score=2, away_score=0)
    m_h2 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=20), status="FINISHED", home_score=3, away_score=1)
    m_h3 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=15), status="FINISHED", home_score=1, away_score=0)

    # t1 Away matches: 0-3, 1-2 (2 matches, 1 GS, 5 GC, 0 pts)
    m_a1 = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now - timedelta(days=10), status="FINISHED", home_score=3, away_score=0)
    m_a2 = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=2, away_score=1)

    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m_h1, m_h2, m_h3, m_a1, m_a2, m_target])
    db_session.commit()

    venue_calcs = generate_venue_form_calculators()

    # Home team (t1) venue goals scored: should be 6 (from 3 home matches only, ignoring 2 away matches)
    res_h_gs = venue_calcs["home_venue_goals_scored_last_5_v1"].calculate(db_session, m_target, now)
    assert res_h_gs.value == 6
    assert res_h_gs.sample_size == 3

    # Home team (t1) venue PPG: (3+3+3)/3 = 3.0
    res_h_ppg = venue_calcs["home_venue_ppg_last_5_v1"].calculate(db_session, m_target, now)
    assert res_h_ppg.value == 3.0
    assert res_h_ppg.sample_size == 3

    # Target as Away (t1 as away): away venue goals scored should be 1 (from 2 away matches only)
    m_target_away = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now, status="SCHEDULED")
    db_session.add(m_target_away)
    db_session.commit()

    res_a_gs = venue_calcs["away_venue_goals_scored_last_5_v1"].calculate(db_session, m_target_away, now)
    assert res_a_gs.value == 1
    assert res_a_gs.sample_size == 2


@pytest.mark.unit
def test_point_in_time_league_baseline(db_session: Session):
    """Verifies empirical point-in-time calculation of league home and away goal averages."""
    comp = Competition(code="BASE_EPL", name="Premier League", country="England")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Base Team 1")
    t2 = Team(canonical_name="Base Team 2")

    now = datetime.now(UTC)
    # 4 league matches: (2-1), (1-0), (3-2), (0-0)
    # Total home goals = 2 + 1 + 3 + 0 = 6  -> avg = 6 / 4 = 1.5
    # Total away goals = 1 + 0 + 2 + 0 = 3  -> avg = 3 / 4 = 0.75
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=20), status="FINISHED", home_score=2, away_score=1)
    m2 = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now - timedelta(days=15), status="FINISHED", home_score=1, away_score=0)
    m3 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=10), status="FINISHED", home_score=3, away_score=2)
    m4 = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=0, away_score=0)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m1, m2, m3, m4, m_target])
    db_session.commit()

    calc_h = LeagueHomeGoalsAvgCalculator()
    calc_a = LeagueAwayGoalsAvgCalculator()

    res_h = calc_h.calculate(db_session, m_target, now)
    assert res_h.value == 1.5
    assert res_h.sample_size == 4

    res_a = calc_a.calculate(db_session, m_target, now)
    assert res_a.value == 0.75
    assert res_a.sample_size == 4


@pytest.mark.unit
def test_attack_and_defense_strength_ratios(db_session: Session):
    """Verifies attack and defense strength ratios relative to empirical league baselines."""
    comp = Competition(code="STR_EPL", name="Premier League", country="England")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Str Team 1")
    t2 = Team(canonical_name="Str Team 2")

    now = datetime.now(UTC)
    # League matches before cutoff:
    # m1: t1 vs t2 -> 3-0
    # m2: t2 vs t1 -> 1-1
    # League home goals = 3 + 1 = 4 -> avg = 4/2 = 2.0
    # League away goals = 0 + 1 = 1 -> avg = 1/2 = 0.5
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=10), status="FINISHED", home_score=3, away_score=0)
    m2 = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=1, away_score=1)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m1, m2, m_target])
    db_session.commit()

    # t1 home scoring avg = 3.0 / 1 = 3.0. League home avg = 2.0. -> Home Attack Strength = 3.0 / 2.0 = 1.5
    calc_ha = HomeAttackStrengthCalculator()
    res_ha = calc_ha.calculate(db_session, m_target, now)
    assert res_ha.value == 1.5

    # t1 home conceded avg = 0.0 / 1 = 0.0. League away avg = 0.5. -> Home Defense Strength = 0.0 / 0.5 = 0.0
    calc_hd = HomeDefenseStrengthCalculator()
    res_hd = calc_hd.calculate(db_session, m_target, now)
    assert res_hd.value == 0.0


@pytest.mark.unit
def test_zero_denominator_safety(db_session: Session):
    """Verifies that 0 league matches returns is_missing=True, INSUFFICIENT_HISTORY without Inf or NaN."""
    comp = Competition(code="ZERO_DEN", name="Zero League", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Zero Team 1")
    t2 = Team(canonical_name="Zero Team 2")

    now = datetime.now(UTC)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m_target])
    db_session.commit()

    calc_ha = HomeAttackStrengthCalculator()
    res = calc_ha.calculate(db_session, m_target, now)

    assert res.value is None
    assert res.is_missing is True
    assert res.missing_reason == MissingnessReason.INSUFFICIENT_HISTORY


@pytest.mark.unit
def test_adversarial_final_season_contamination(db_session: Session):
    """Adversarial test: adding future matchdays (4-38) after target cutoff does NOT change target Matchday 3 features."""
    comp = Competition(code="ADV_CONTAM", name="Leakage League", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Contam Team 1")
    t2 = Team(canonical_name="Contam Team 2")

    t_m1 = datetime(2024, 9, 1, 15, 0, tzinfo=UTC)
    t_m2 = datetime(2024, 9, 8, 15, 0, tzinfo=UTC)
    t_target = datetime(2024, 9, 15, 15, 0, tzinfo=UTC)  # Matchday 3 cutoff
    t_future = datetime(2024, 9, 22, 15, 0, tzinfo=UTC)  # Matchday 4

    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=t_m1, status="FINISHED", home_score=2, away_score=1)
    m2 = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=t_m2, status="FINISHED", home_score=1, away_score=0)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=t_target, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m1, m2, m_target])
    db_session.commit()

    calc_h = LeagueHomeGoalsAvgCalculator()
    val_before = calc_h.calculate(db_session, m_target, t_target).value

    # Add future Matchday 4 with high scoring 10-10
    m_future = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=t_future, status="FINISHED", home_score=10, away_score=10)
    db_session.add(m_future)
    db_session.commit()

    val_after = calc_h.calculate(db_session, m_target, t_target).value
    assert val_before == val_after
