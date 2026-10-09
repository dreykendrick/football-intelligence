"""
Unit Tests for Sprint 3.2 - Team Form & Goal Performance Features
Verifies rolling form metrics, team perspective, window selection, partial windows, missingness, mathematical invariants, and leakage safety.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.dataset.base import DatasetReleaseStatusEnum
from app.db.models import (
    Competition,
    HistoricalDatasetMatch,
    HistoricalDatasetRelease,
    Match,
    Season,
    Team,
)
from app.features.base import MissingnessReason
from app.features.calculators.form_calculators import generate_form_calculators
from app.features.observations import (
    RollingFormAggregator,
    TeamMatchObservationBuilder,
)
from app.features.query import PointInTimeQueryService


@pytest.mark.unit
def test_basic_rolling_form_calculation(db_session: Session):
    comp = Competition(code="FORM_EPL", name="Premier League", country="England")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Arsenal Form")
    t2 = Team(canonical_name="Chelsea Form")

    now = datetime.now(UTC)
    # 5 prior matches for Arsenal Form (t1):
    # Match 1: 2-0 (Win, 3 pts, 2 GS, 0 GC, CS)
    # Match 2: 1-1 (Draw, 1 pt, 1 GS, 1 GC)
    # Match 3: 0-1 (Loss, 0 pts, 0 GS, 1 GC, FTS)
    # Match 4: 3-1 (Win, 3 pts, 3 GS, 1 GC)
    # Match 5: 1-0 (Win, 3 pts, 1 GS, 0 GC, CS)
    # Total: 10 pts, 3W 1D 1L, 7 GS, 3 GC, GD=+4, 2 CS, 1 FTS
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=25), status="FINISHED", home_score=2, away_score=0)
    m2 = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now - timedelta(days=20), status="FINISHED", home_score=1, away_score=1)
    m3 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=15), status="FINISHED", home_score=0, away_score=1)
    m4 = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now - timedelta(days=10), status="FINISHED", home_score=1, away_score=3)
    m5 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=1, away_score=0)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m1, m2, m3, m4, m5, m_target])
    db_session.commit()

    calcs = generate_form_calculators()

    res_pts = calcs["home_points_last_5_v1"].calculate(db_session, m_target, now)
    assert res_pts.value == 10
    assert res_pts.sample_size == 5

    res_ppg = calcs["home_ppg_last_5_v1"].calculate(db_session, m_target, now)
    assert res_ppg.value == 2.0

    res_wins = calcs["home_wins_last_5_v1"].calculate(db_session, m_target, now)
    assert res_wins.value == 3

    res_draws = calcs["home_draws_last_5_v1"].calculate(db_session, m_target, now)
    assert res_draws.value == 1

    res_losses = calcs["home_losses_last_5_v1"].calculate(db_session, m_target, now)
    assert res_losses.value == 1

    res_gs = calcs["home_goals_scored_last_5_v1"].calculate(db_session, m_target, now)
    assert res_gs.value == 7

    res_gc = calcs["home_goals_conceded_last_5_v1"].calculate(db_session, m_target, now)
    assert res_gc.value == 3

    res_gd = calcs["home_goal_difference_last_5_v1"].calculate(db_session, m_target, now)
    assert res_gd.value == 4

    res_cs = calcs["home_clean_sheets_last_5_v1"].calculate(db_session, m_target, now)
    assert res_cs.value == 2

    res_fts = calcs["home_failed_to_score_last_5_v1"].calculate(db_session, m_target, now)
    assert res_fts.value == 1


@pytest.mark.unit
def test_team_perspective_handling(db_session: Session):
    """Verifies goals and points are correctly attributed when target team plays as Away team."""
    comp = Competition(code="PERSP_EPL", name="Premier League", country="England")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Liverpool Persp")
    t2 = Team(canonical_name="Everton Persp")

    now = datetime.now(UTC)
    # Everton Persp (t2) vs Liverpool Persp (t1) -> Everton 1 - 4 Liverpool (Liverpool Away Win)
    m1 = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=1, away_score=4)
    m_target = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m1, m_target])
    db_session.commit()

    calcs = generate_form_calculators()
    res_gs = calcs["away_goals_scored_last_3_v1"].calculate(db_session, m_target, now)
    assert res_gs.value == 4

    res_gc = calcs["away_goals_conceded_last_3_v1"].calculate(db_session, m_target, now)
    assert res_gc.value == 1

    res_pts = calcs["away_points_last_3_v1"].calculate(db_session, m_target, now)
    assert res_pts.value == 3


@pytest.mark.unit
def test_partial_window_handling(db_session: Session):
    """Verifies that requested window=5 with only 2 prior matches returns sample_size=2 and divides by 2."""
    comp = Competition(code="PART_EPL", name="Premier League", country="England")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Team Part 1")
    t2 = Team(canonical_name="Team Part 2")

    now = datetime.now(UTC)
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=10), status="FINISHED", home_score=2, away_score=0)
    m2 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=1, away_score=1)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m1, m2, m_target])
    db_session.commit()

    calcs = generate_form_calculators()
    res_ppg = calcs["home_ppg_last_5_v1"].calculate(db_session, m_target, now)
    assert res_ppg.sample_size == 2
    assert res_ppg.is_missing is False
    # (3 + 1) / 2 = 2.0
    assert res_ppg.value == 2.0


@pytest.mark.unit
def test_zero_history_missingness(db_session: Session):
    """Verifies that zero prior matches returns value=None, is_missing=True, INSUFFICIENT_HISTORY, sample_size=0."""
    comp = Competition(code="ZERO_EPL", name="Premier League", country="England")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="New Team 1")
    t2 = Team(canonical_name="New Team 2")

    now = datetime.now(UTC)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m_target])
    db_session.commit()

    calcs = generate_form_calculators()
    res_ppg = calcs["home_ppg_last_5_v1"].calculate(db_session, m_target, now)
    assert res_ppg.value is None
    assert res_ppg.is_missing is True
    assert res_ppg.missing_reason == MissingnessReason.INSUFFICIENT_HISTORY
    assert res_ppg.sample_size == 0


@pytest.mark.unit
def test_adversarial_target_result_leakage(db_session: Session):
    """Verifies that altering target match result does NOT alter its pre-match form features."""
    comp = Competition(code="LK_TGT", name="Leak League", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Target Leak 1")
    t2 = Team(canonical_name="Target Leak 2")

    now = datetime.now(UTC)
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=2, away_score=1)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="FINISHED", home_score=0, away_score=0)

    db_session.add_all([comp, season, t1, t2, m1, m_target])
    db_session.commit()

    calcs = generate_form_calculators()
    val1 = calcs["home_ppg_last_5_v1"].calculate(db_session, m_target, now).value

    # Mutate target match score to blowout 10-0
    m_target.home_score = 10
    m_target.away_score = 0
    db_session.commit()

    val2 = calcs["home_ppg_last_5_v1"].calculate(db_session, m_target, now).value
    assert val1 == val2


@pytest.mark.unit
def test_form_invariants_and_bounds(db_session: Session):
    """Verifies mathematical invariants: W+D+L=sample_size, 0<=rates<=1, 0<=PPG<=3, GD=GS-GC."""
    comp = Competition(code="INV_EPL", name="Invariant League", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Inv Team 1")
    t2 = Team(canonical_name="Inv Team 2")

    now = datetime.now(UTC)
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=15), status="FINISHED", home_score=3, away_score=0)
    m2 = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now - timedelta(days=10), status="FINISHED", home_score=1, away_score=1)
    m3 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=0, away_score=2)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m1, m2, m3, m_target])
    db_session.commit()

    calcs = generate_form_calculators()

    w = calcs["home_wins_last_5_v1"].calculate(db_session, m_target, now).value
    d = calcs["home_draws_last_5_v1"].calculate(db_session, m_target, now).value
    l = calcs["home_losses_last_5_v1"].calculate(db_session, m_target, now).value
    sample = calcs["home_points_last_5_v1"].calculate(db_session, m_target, now).sample_size

    assert w + d + l == sample == 3

    wr = calcs["home_win_rate_last_5_v1"].calculate(db_session, m_target, now).value
    dr = calcs["home_draw_rate_last_5_v1"].calculate(db_session, m_target, now).value
    lr = calcs["home_loss_rate_last_5_v1"].calculate(db_session, m_target, now).value

    assert 0.0 <= wr <= 1.0
    assert 0.0 <= dr <= 1.0
    assert 0.0 <= lr <= 1.0
    assert abs((wr + dr + lr) - 1.0) < 0.001

    ppg = calcs["home_ppg_last_5_v1"].calculate(db_session, m_target, now).value
    assert 0.0 <= ppg <= 3.0

    gs = calcs["home_goals_scored_last_5_v1"].calculate(db_session, m_target, now).value
    gc = calcs["home_goals_conceded_last_5_v1"].calculate(db_session, m_target, now).value
    gd = calcs["home_goal_difference_last_5_v1"].calculate(db_session, m_target, now).value
    assert gd == gs - gc
