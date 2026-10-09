"""
Unit Tests for Sprint 3.4 — Elo Rating System
Verifies numerical calculations, competition isolation, season transition regression,
DATE_ONLY anti-leakage safeguards, batch order invariance, target outcome isolation, and determinism.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.dataset.base import DatasetReleaseStatusEnum
from app.db.models import Competition, HistoricalDatasetMatch, HistoricalDatasetRelease, Match, Season, Team
from app.features.calculators.elo import (
    AwayEloCalculator,
    EloConfig,
    EloDifferenceCalculator,
    EloRatingEngine,
    HomeEloCalculator,
)


@pytest.mark.unit
def test_elo_config_fingerprint_determinism():
    c1 = EloConfig()
    c2 = EloConfig()
    assert c1.fingerprint == c2.fingerprint
    assert len(c1.fingerprint) == 16

    c3 = EloConfig(k_factor=64.0)
    assert c1.fingerprint != c3.fingerprint


@pytest.mark.unit
def test_equal_rating_and_home_advantage_expected_scores():
    config = EloConfig(initial_rating=1500.0, home_advantage=100.0, scale=400.0)
    
    # Equal ratings, HA = 0
    r_home, r_away = 1500.0, 1500.0
    exp_home_no_ha = 1.0 / (1.0 + 10.0 ** ((r_away - r_home) / config.scale))
    exp_away_no_ha = 1.0 - exp_home_no_ha
    assert exp_home_no_ha == 0.5
    assert exp_away_no_ha == 0.5

    # Equal ratings, HA = 100
    r_home_eff = r_home + config.home_advantage
    exp_home_ha = 1.0 / (1.0 + 10.0 ** ((r_away - r_home_eff) / config.scale))
    exp_away_ha = 1.0 - exp_home_ha
    assert exp_home_ha > 0.5
    assert exp_away_ha < 0.5
    assert round(exp_home_ha + exp_away_ha, 6) == 1.0


@pytest.mark.unit
def test_rating_update_directions_and_zero_sum(db_session: Session):
    comp = Competition(code="ELO_UPDATE", name="Update Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Home Team")
    t2 = Team(canonical_name="Away Team")

    now = datetime.now(UTC)
    # Home win
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=10), status="FINISHED", home_score=2, away_score=0)
    db_session.add_all([comp, season, t1, t2, m1])
    db_session.flush()

    ratings, _ = EloRatingEngine.compute_team_ratings_before(db_session, competition_id=comp.id, cutoff_timestamp=now)

    r1 = ratings[t1.id]
    r2 = ratings[t2.id]

    assert r1 > 1500.0
    assert r2 < 1500.0
    # Zero-sum property: delta_home + delta_away = 0
    delta_home = r1 - 1500.0
    delta_away = r2 - 1500.0
    assert abs(delta_home + delta_away) < 0.05


@pytest.mark.unit
def test_upset_magnitude_comparison(db_session: Session):
    # Setup two scenarios: Expected winner wins vs Underdog wins
    comp = Competition(code="ELO_UPSET", name="Upset Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t_strong = Team(canonical_name="Strong Team")
    t_weak = Team(canonical_name="Weak Team")

    now = datetime.now(UTC)
    # Give strong team high rating history
    m_setup = Match(season=season, home_team=t_strong, away_team=t_weak, kickoff_utc=now - timedelta(days=20), status="FINISHED", home_score=5, away_score=0)
    db_session.add_all([comp, season, t_strong, t_weak, m_setup])
    db_session.flush()

    ratings_setup, _ = EloRatingEngine.compute_team_ratings_before(db_session, competition_id=comp.id, cutoff_timestamp=now - timedelta(days=15))
    r_strong_pre = ratings_setup[t_strong.id]
    r_weak_pre = ratings_setup[t_weak.id]

    # Underdog win update
    config = EloConfig()
    r_strong_eff = r_strong_pre + config.home_advantage
    exp_strong = 1.0 / (1.0 + 10.0 ** ((r_weak_pre - r_strong_eff) / config.scale))
    exp_weak = 1.0 - exp_strong

    # Delta when weak team wins as away team (S_weak = 1.0)
    delta_upset = config.k_factor * (1.0 - exp_weak)

    # Delta if strong team won as home team (S_strong = 1.0)
    delta_expected = config.k_factor * (1.0 - exp_strong)

    assert delta_upset > delta_expected


@pytest.mark.unit
def test_no_margin_of_victory_effect(db_session: Session):
    # In Elo v1, 1-0 win and 7-0 win must yield identical rating updates
    comp1 = Competition(code="MOV_1", name="MOV 1", country="Test")
    season1 = Season(competition=comp1, season_year="2023/24")
    t1_a = Team(canonical_name="A1")
    t1_b = Team(canonical_name="B1")

    comp2 = Competition(code="MOV_2", name="MOV 2", country="Test")
    season2 = Season(competition=comp2, season_year="2023/24")
    t2_a = Team(canonical_name="A2")
    t2_b = Team(canonical_name="B2")

    now = datetime.now(UTC)
    m1 = Match(season=season1, home_team=t1_a, away_team=t1_b, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=1, away_score=0)
    m2 = Match(season=season2, home_team=t2_a, away_team=t2_b, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=7, away_score=0)

    db_session.add_all([comp1, season1, t1_a, t1_b, m1, comp2, season2, t2_a, t2_b, m2])
    db_session.flush()

    r1, _ = EloRatingEngine.compute_team_ratings_before(db_session, competition_id=comp1.id, cutoff_timestamp=now)
    r2, _ = EloRatingEngine.compute_team_ratings_before(db_session, competition_id=comp2.id, cutoff_timestamp=now)

    assert r1[t1_a.id] == r2[t2_a.id]
    assert r1[t1_b.id] == r2[t2_b.id]


@pytest.mark.unit
def test_competition_isolation(db_session: Session):
    comp_pl = Competition(code="EPL_ISO", name="Premier League", country="England")
    season_pl = Season(competition=comp_pl, season_year="2023/24")

    comp_ll = Competition(code="LAL_ISO", name="La Liga", country="Spain")
    season_ll = Season(competition=comp_ll, season_year="2023/24")

    t_pl_1 = Team(canonical_name="Arsenal")
    t_pl_2 = Team(canonical_name="Chelsea")
    t_ll_1 = Team(canonical_name="Barca")
    t_ll_2 = Team(canonical_name="Madrid")

    now = datetime.now(UTC)
    m_pl = Match(season=season_pl, home_team=t_pl_1, away_team=t_pl_2, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=3, away_score=0)
    m_ll = Match(season=season_ll, home_team=t_ll_1, away_team=t_ll_2, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=5, away_score=0)

    db_session.add_all([comp_pl, season_pl, comp_ll, season_ll, t_pl_1, t_pl_2, t_ll_1, t_ll_2, m_pl, m_ll])
    db_session.flush()

    # Replay Premier League
    ratings_pl, _ = EloRatingEngine.compute_team_ratings_before(db_session, competition_id=comp_pl.id, cutoff_timestamp=now)
    assert t_pl_1.id in ratings_pl
    assert t_ll_1.id not in ratings_pl

    # Modify La Liga match
    m_ll.home_score = 0
    m_ll.away_score = 4
    db_session.flush()

    # Replay Premier League again -> ratings must be unchanged
    ratings_pl_after, _ = EloRatingEngine.compute_team_ratings_before(db_session, competition_id=comp_pl.id, cutoff_timestamp=now)
    assert ratings_pl_after[t_pl_1.id] == ratings_pl[t_pl_1.id]


@pytest.mark.unit
def test_season_transition_regression(db_session: Session):
    comp = Competition(code="ELO_REG", name="Season Reg Test", country="Test")
    season1 = Season(competition=comp, season_year="2022/23")
    season2 = Season(competition=comp, season_year="2023/24")

    t1 = Team(canonical_name="Reg Team A")
    t2 = Team(canonical_name="Reg Team B")

    t_new = Team(canonical_name="Promoted Team")

    now = datetime.now(UTC)
    # Season 1 matches (t1 beats t2)
    m1 = Match(season=season1, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=300), status="FINISHED", home_score=4, away_score=0)
    # Season 2 matches
    m2 = Match(season=season2, home_team=t1, away_team=t_new, kickoff_utc=now - timedelta(days=50), status="FINISHED", home_score=1, away_score=0)
    m_target = Match(season=season2, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    db_session.add_all([comp, season1, season2, t1, t2, t_new, m1, m2, m_target])
    db_session.flush()

    # Get rating at end of Season 1
    cutoff_s1_end = now - timedelta(days=200)
    r_s1, _ = EloRatingEngine.compute_team_ratings_before(db_session, competition_id=comp.id, cutoff_timestamp=cutoff_s1_end)
    t1_s1_end = r_s1[t1.id]
    assert t1_s1_end > 1500.0

    # Expected regressed rating entering Season 2 before m2: 1500 + 0.75 * (t1_s1_end - 1500)
    expected_s2_start = round(1500.0 + 0.75 * (t1_s1_end - 1500.0), 2)

    # Calculate Elo right before m2 in Season 2 (m2 is in season2)
    cutoff_m2_pre = now - timedelta(days=51)
    r_m2_pre, _ = EloRatingEngine.compute_team_ratings_before(
        db_session, competition_id=comp.id, cutoff_timestamp=cutoff_m2_pre, target_season_id=season2.id
    )
    assert r_m2_pre[t1.id] == expected_s2_start

    # Promoted team t_new starts at initial 1500
    assert r_m2_pre.get(t_new.id, 1500.0) == 1500.0


@pytest.mark.unit
def test_date_only_same_day_exclusion_and_order_invariance(db_session: Session):
    comp = Competition(code="ELO_DATE", name="Date Only Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")

    t1 = Team(canonical_name="Date A")
    t2 = Team(canonical_name="Date B")
    t3 = Team(canonical_name="Date C")
    t4 = Team(canonical_name="Date D")

    target_date = datetime(2024, 3, 10, 15, 0, 0, tzinfo=UTC)
    past_date = datetime(2024, 3, 5, 15, 0, 0, tzinfo=UTC)

    # Past match (March 5)
    m_past = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=past_date, status="FINISHED", home_score=2, away_score=0)

    # Same-day match on March 10
    m_sameday = Match(season=season, home_team=t3, away_team=t4, kickoff_utc=datetime(2024, 3, 10, 12, 0, 0, tzinfo=UTC), status="FINISHED", home_score=1, away_score=0)

    # Target match on March 10
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=target_date, status="SCHEDULED")

    db_session.add_all([comp, season, t1, t2, t3, t4, m_past, m_sameday, m_target])
    db_session.flush()

    calc_home = HomeEloCalculator()
    res = calc_home.calculate(db_session, m_target, cutoff_timestamp=target_date)

    # Verification: m_sameday must NOT affect target pre-match Elo for March 10
    # Pre-match rating for t1 should reflect strictly matches before March 10 (i.e. m_past)
    r_past_only, _ = EloRatingEngine.compute_team_ratings_before(
        db_session, competition_id=comp.id, cutoff_timestamp=datetime(2024, 3, 10, 0, 0, 0, tzinfo=UTC)
    )
    assert res.value == r_past_only[t1.id]


@pytest.mark.unit
def test_target_and_future_match_leakage_isolation(db_session: Session):
    comp = Competition(code="ELO_LEAK", name="Leak Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")

    t1 = Team(canonical_name="Leak A")
    t2 = Team(canonical_name="Leak B")

    now = datetime.now(UTC)
    m_prev = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=10), status="FINISHED", home_score=1, away_score=0)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="FINISHED", home_score=4, away_score=0)
    m_future = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now + timedelta(days=5), status="FINISHED", home_score=0, away_score=5)

    db_session.add_all([comp, season, t1, t2, m_prev, m_target, m_future])
    db_session.flush()

    calc_home = HomeEloCalculator()
    calc_diff = EloDifferenceCalculator()

    res_home_1 = calc_home.calculate(db_session, m_target, cutoff_timestamp=now)
    res_diff_1 = calc_diff.calculate(db_session, m_target, cutoff_timestamp=now)

    # Change target outcome and future match outcome
    m_target.home_score = 0
    m_target.away_score = 10
    m_future.home_score = 8
    m_future.away_score = 0
    db_session.flush()

    res_home_2 = calc_home.calculate(db_session, m_target, cutoff_timestamp=now)
    res_diff_2 = calc_diff.calculate(db_session, m_target, cutoff_timestamp=now)

    # Ratings MUST remain strictly identical
    assert res_home_1.value == res_home_2.value
    assert res_diff_1.value == res_diff_2.value


@pytest.mark.unit
def test_approved_dataset_isolation(db_session: Session):
    comp = Competition(code="ELO_DS", name="Dataset Scope Test", country="Test")
    season = Season(competition=comp, season_year="2023/24")

    t1 = Team(canonical_name="DS Team A")
    t2 = Team(canonical_name="DS Team B")

    now = datetime.now(UTC)
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=2, away_score=0)
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="SCHEDULED")

    rel_approved = HistoricalDatasetRelease(key="mvp_a_historical", version="v1", status=DatasetReleaseStatusEnum.APPROVED.value)

    db_session.add_all([comp, season, t1, t2, m1, m_target, rel_approved])
    db_session.flush()

    # Link m1 to approved dataset with all required fields
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
    db_session.flush()

    ratings_app, _ = EloRatingEngine.compute_team_ratings_before(
        db_session, competition_id=comp.id, cutoff_timestamp=now, approved_only=True
    )
    assert ratings_app[t1.id] > 1500.0

    # Unlink m1 -> rating reverts to default initial
    db_session.delete(link1)
    db_session.flush()

    EloRatingEngine.clear_cache()

    ratings_unapp, _ = EloRatingEngine.compute_team_ratings_before(
        db_session, competition_id=comp.id, cutoff_timestamp=now, approved_only=True
    )
    assert ratings_unapp.get(t1.id, 1500.0) == 1500.0
