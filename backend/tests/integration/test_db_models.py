"""
Integration Tests for Database ORM Entities & Relationships
Validates creation of Competitions, Seasons, Teams, Matches, Models, FeatureSnapshots, and Predictions.
"""
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.db.models import (
    Competition,
    FeatureSet,
    FeatureSnapshot,
    Match,
    Model,
    ModelVersion,
    PredictionSnapshot,
    Season,
    Team,
)


@pytest.mark.integration
def test_competition_season_relationship(db_session: Session):
    comp = Competition(code="LALIGA", name="La Liga", country="Spain")
    db_session.add(comp)
    db_session.flush()

    season = Season(competition_id=comp.id, season_year="2023/24", start_year=2023, end_year=2024)
    db_session.add(season)
    db_session.commit()

    saved_comp = db_session.query(Competition).filter_by(code="LALIGA").first()
    assert saved_comp is not None
    assert len(saved_comp.seasons) == 1
    assert saved_comp.seasons[0].season_year == "2023/24"


@pytest.mark.integration
def test_match_creation_and_teams(db_session: Session):
    comp = Competition(code="SERIEA", name="Serie A", country="Italy")
    db_session.add(comp)
    db_session.flush()

    season = Season(competition_id=comp.id, season_year="2023/24")
    team_home = Team(canonical_name="Juventus", short_name="Juve")
    team_away = Team(canonical_name="Inter Milan", short_name="Inter")
    db_session.add_all([season, team_home, team_away])
    db_session.flush()

    match = Match(
        season_id=season.id,
        home_team_id=team_home.id,
        away_team_id=team_away.id,
        kickoff_utc=datetime.now(UTC),
        status="FINISHED",
        home_score=1,
        away_score=0,
    )
    db_session.add(match)
    db_session.commit()

    saved_match = db_session.query(Match).filter_by(id=match.id).first()
    assert saved_match is not None
    assert saved_match.home_team.canonical_name == "Juventus"
    assert saved_match.away_team.canonical_name == "Inter Milan"
    assert saved_match.home_score == 1
    assert saved_match.away_score == 0


@pytest.mark.integration
def test_prediction_snapshot_chain(db_session: Session):
    comp = Competition(code="BL1", name="Bundesliga", country="Germany")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name="Bayern Munich")
    t2 = Team(canonical_name="Borussia Dortmund")
    match = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=datetime.now(UTC))

    fset = FeatureSet(name="bl_feature_set", version="1.0.0")
    model = Model(model_key="poisson_decoupled", name="Decoupled Poisson")
    mver = ModelVersion(model=model, version="1.0.0", feature_set=fset, lifecycle_status="VALIDATED")

    fsnap = FeatureSnapshot(
        match=match,
        feature_set=fset,
        snapshot_type="FINAL",
        cutoff_timestamp=datetime.now(UTC),
        feature_values={"home_attack": 2.1, "away_defense": 1.1},
    )

    pred = PredictionSnapshot(
        match=match,
        model_version=mver,
        feature_snapshot=fsnap,
        snapshot_type="FINAL",
        target_kickoff_timestamp=match.kickoff_utc,
        prob_home_win=0.55000,
        prob_draw=0.25000,
        prob_away_win=0.20000,
        predicted_home_goals=2.10,
        predicted_away_goals=1.05,
    )

    db_session.add_all([comp, season, t1, t2, match, fset, model, mver, fsnap, pred])
    db_session.commit()

    saved_pred = db_session.query(PredictionSnapshot).filter_by(id=pred.id).first()
    assert saved_pred is not None
    assert float(saved_pred.prob_home_win) == 0.55
    assert float(saved_pred.prob_draw) == 0.25
    assert float(saved_pred.prob_away_win) == 0.20
    assert saved_pred.model_version.version == "1.0.0"
    assert saved_pred.feature_snapshot.feature_values["home_attack"] == 2.1
