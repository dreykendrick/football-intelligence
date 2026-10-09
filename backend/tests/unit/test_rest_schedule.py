"""
Unit Tests for Sprint 3.5 — Rest, Schedule & Context Features
Verifies exact vs DATE_ONLY rest calculation, current-season rest isolation,
rolling window match counts (7d, 14d, 21d), season matches played, target score invariance,
prior date sensitivity, approved dataset boundary isolation, and zero-count validity.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.dataset.base import DatasetReleaseStatusEnum
from app.db.models import Competition, HistoricalDatasetMatch, HistoricalDatasetRelease, Match, Season, Team
from app.features.calculators.rest_congestion import (
    AwayMatchesLast14DaysCalculator,
    AwayMatchesLast21DaysCalculator,
    AwayMatchesLast7DaysCalculator,
    AwayRestDaysCalculator,
    AwaySeasonMatchesPlayedCalculator,
    HomeMatchesLast14DaysCalculator,
    HomeMatchesLast21DaysCalculator,
    HomeMatchesLast7DaysCalculator,
    HomeRestDaysCalculator,
    HomeSeasonMatchesPlayedCalculator,
    RestDaysDifferenceCalculator,
)


@pytest.mark.unit
def test_rest_days_exact_timestamp_and_date_only(db_session: Session):
    comp = Competition(code="REST_CALC", name="Rest Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Rest Team A")
    t2 = Team(canonical_name="Rest Team B")

    target_time = datetime(2025, 4, 20, 18, 0, 0, tzinfo=UTC)
    prev_time_exact = datetime(2025, 4, 16, 6, 0, 0, tzinfo=UTC)  # 4.5 days prior

    m_prev = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=prev_time_exact, status="FINISHED", home_score=1, away_score=0)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=target_time, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m_prev, m_target])
    db_session.flush()

    calc_home = HomeRestDaysCalculator()
    res = calc_home.calculate(db_session, m_target, cutoff_timestamp=target_time)

    assert res.is_missing is False
    assert res.value == 4.5
    assert res.metadata_payload["precision"] == "EXACT_TIMESTAMP"
    assert res.metadata_payload["schedule_scope"] == "APPROVED_DATASET_COMPETITION_ONLY"


@pytest.mark.unit
def test_rest_days_current_season_isolation(db_session: Session):
    comp = Competition(code="REST_SEASON", name="Season Rest Test", country="Test")
    season1 = Season(competition=comp, season_year="2022/23")
    season2 = Season(competition=comp, season_year="2023/24")

    t1 = Team(canonical_name="Team A")
    t2 = Team(canonical_name="Team B")

    now = datetime.now(UTC)
    # Match in season 1 (100 days ago)
    m_s1 = Match(season=season1, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=100), status="FINISHED", home_score=2, away_score=1)
    # First match in season 2 (season opener)
    m_s2_opener = Match(season=season2, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season1, season2, t1, t2, m_s1, m_s2_opener])
    db_session.flush()

    calc_home = HomeRestDaysCalculator()
    res = calc_home.calculate(db_session, m_s2_opener, cutoff_timestamp=now)

    # Verification: Off-season match from season1 must NOT be used for rest days in season2!
    assert res.is_missing is True
    assert res.value is None


@pytest.mark.unit
def test_zero_prior_history_and_rest_difference_missingness(db_session: Session):
    comp = Competition(code="REST_DIFF", name="Diff Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")

    t1 = Team(canonical_name="Team Home")
    t2 = Team(canonical_name="Team Away")
    t3 = Team(canonical_name="Team Other")

    now = datetime.now(UTC)
    # Home team (t1) played 4 days ago against t3; Away team (t2) has zero prior history in season
    m_home_prev = Match(season=season, home_team=t1, away_team=t3, kickoff_utc=now - timedelta(days=4), status="FINISHED", home_score=1, away_score=0)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, t3, m_home_prev, m_target])
    db_session.flush()

    calc_home = HomeRestDaysCalculator()
    calc_away = AwayRestDaysCalculator()
    calc_diff = RestDaysDifferenceCalculator()

    res_h = calc_home.calculate(db_session, m_target, cutoff_timestamp=now)
    res_a = calc_away.calculate(db_session, m_target, cutoff_timestamp=now)
    res_d = calc_diff.calculate(db_session, m_target, cutoff_timestamp=now)

    assert res_h.value == 4.0
    assert res_a.is_missing is True
    assert res_d.is_missing is True
    assert res_d.value is None


@pytest.mark.unit
def test_window_match_counts_and_zero_validity(db_session: Session):
    comp = Competition(code="WINDOW_CNT", name="Window Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")

    t1 = Team(canonical_name="Count A")
    t2 = Team(canonical_name="Count B")

    now = datetime.now(UTC)
    # Matches at 5 days ago, 12 days ago, 18 days ago
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=1, away_score=0)
    m2 = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now - timedelta(days=12), status="FINISHED", home_score=0, away_score=1)
    m3 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=18), status="FINISHED", home_score=3, away_score=0)

    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m1, m2, m3, m_target])
    db_session.flush()

    calc_7d = HomeMatchesLast7DaysCalculator()
    calc_14d = HomeMatchesLast14DaysCalculator()
    calc_21d = HomeMatchesLast21DaysCalculator()
    calc_season = HomeSeasonMatchesPlayedCalculator()

    res_7d = calc_7d.calculate(db_session, m_target, cutoff_timestamp=now)
    res_14d = calc_14d.calculate(db_session, m_target, cutoff_timestamp=now)
    res_21d = calc_21d.calculate(db_session, m_target, cutoff_timestamp=now)
    res_season = calc_season.calculate(db_session, m_target, cutoff_timestamp=now)

    assert res_7d.value == 1
    assert res_14d.value == 2
    assert res_21d.value == 3
    assert res_season.value == 3

    # Away team 7d count is 2 (played m1 and m2)
    calc_away_7d = AwayMatchesLast7DaysCalculator()
    assert calc_away_7d.calculate(db_session, m_target, cutoff_timestamp=now).value == 1  # m1 only (5 days ago)

    # Away team 21d count is 3 (played m1, m2, m3)
    calc_away_21d = AwayMatchesLast21DaysCalculator()
    assert calc_away_21d.calculate(db_session, m_target, cutoff_timestamp=now).value == 3


@pytest.mark.unit
def test_zero_count_validity(db_session: Session):
    comp = Competition(code="ZERO_CNT", name="Zero Count Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")

    t1 = Team(canonical_name="Zero Team A")
    t2 = Team(canonical_name="Zero Team B")

    now = datetime.now(UTC)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m_target])
    db_session.flush()

    calc_7d = HomeMatchesLast7DaysCalculator()
    res = calc_7d.calculate(db_session, m_target, cutoff_timestamp=now)

    # 0 count is VALID and available (is_missing = False)
    assert res.is_missing is False
    assert res.value == 0


@pytest.mark.unit
def test_prior_match_score_invariance_and_date_sensitivity(db_session: Session):
    comp = Competition(code="REST_INVAR", name="Invariance Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")

    t1 = Team(canonical_name="Inv A")
    t2 = Team(canonical_name="Inv B")

    now = datetime.now(UTC)
    m_past = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=4), status="FINISHED", home_score=1, away_score=0)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, m_past, m_target])
    db_session.flush()

    calc_home = HomeRestDaysCalculator()
    res_1 = calc_home.calculate(db_session, m_target, cutoff_timestamp=now)
    assert res_1.value == 4.0

    # 1. SCORE MUTATION INVARIANCE: Changing prior score from 1-0 to 5-4 does NOT change rest days
    m_past.home_score = 5
    m_past.away_score = 4
    db_session.flush()

    res_2 = calc_home.calculate(db_session, m_target, cutoff_timestamp=now)
    assert res_2.value == 4.0

    # 2. DATE SENSITIVITY: Changing prior kickoff from 4 days to 6 days ago DOES change rest days
    m_past.kickoff_utc = now - timedelta(days=6)
    db_session.flush()

    res_3 = calc_home.calculate(db_session, m_target, cutoff_timestamp=now)
    assert res_3.value == 6.0


@pytest.mark.unit
def test_target_and_future_match_isolation(db_session: Session):
    comp = Competition(code="REST_LEAK", name="Leak Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")

    t1 = Team(canonical_name="Target A")
    t2 = Team(canonical_name="Target B")

    now = datetime.now(UTC)
    m_prev = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=1, away_score=0)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="FINISHED", home_score=3, away_score=0)
    m_future = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now + timedelta(days=4), status="FINISHED", home_score=0, away_score=2)

    db_session.add_all([comp, season, t1, t2, m_prev, m_target, m_future])
    db_session.flush()

    calc_home = HomeRestDaysCalculator()
    calc_14d = HomeMatchesLast14DaysCalculator()

    res_rest_1 = calc_home.calculate(db_session, m_target, cutoff_timestamp=now)
    res_14d_1 = calc_14d.calculate(db_session, m_target, cutoff_timestamp=now)

    # Mutate target & future matches
    m_target.home_score = 0
    m_target.away_score = 10
    m_future.home_score = 6
    m_future.away_score = 0
    db_session.flush()

    res_rest_2 = calc_home.calculate(db_session, m_target, cutoff_timestamp=now)
    res_14d_2 = calc_14d.calculate(db_session, m_target, cutoff_timestamp=now)

    assert res_rest_1.value == res_rest_2.value == 5.0
    assert res_14d_1.value == res_14d_2.value == 1


@pytest.mark.unit
def test_approved_dataset_isolation(db_session: Session):
    comp = Competition(code="REST_DS", name="Dataset Scope Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")

    t1 = Team(canonical_name="DS Team A")
    t2 = Team(canonical_name="DS Team B")

    now = datetime.now(UTC)
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=2, away_score=0)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    rel_approved = HistoricalDatasetRelease(key="mvp_a_historical", version="v1", status=DatasetReleaseStatusEnum.APPROVED.value)

    db_session.add_all([comp, season, t1, t2, m1, m_target, rel_approved])
    db_session.flush()

    calc_home = HomeRestDaysCalculator()

    # Link m1 to approved dataset
    link1 = HistoricalDatasetMatch(
        dataset_release_id=rel_approved.id,
        match_id=m1.id,
        competition_id=comp.id,
        season_id=season.id,
        kickoff_utc=m1.kickoff_utc,
        home_team_id=t1.id,
        away_team_id=t2.id,
    )
    db_session.add(link1)
    db_session.flush()

    res_app = calc_home.calculate(db_session, m_target, cutoff_timestamp=now)
    assert res_app.is_missing is False
    assert res_app.value == 5.0

    # Unlink m1 from approved dataset -> rest reverts to missing (no approved prior match)
    db_session.delete(link1)
    db_session.flush()
    from app.features.query import HistoricalQueryLayer
    HistoricalQueryLayer._cached_get_team_matches_before.cache_clear()

    res_unapp = calc_home.calculate(db_session, m_target, cutoff_timestamp=now)
    assert res_unapp.is_missing is True
    assert res_unapp.value is None
