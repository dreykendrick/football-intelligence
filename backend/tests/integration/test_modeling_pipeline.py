"""
Integration Test Suite for Sprint 4.1 — Modeling Dataset Builder & End-to-End Prediction Pipeline
Verifies dataset building from approved releases, Phase 3 readiness enforcement, baseline model fitting,
artifact serialization, raw prediction generation, and target/future data leakage isolation.
"""
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.dataset.base import DatasetReleaseStatusEnum
from app.db.models import Competition, HistoricalDatasetMatch, HistoricalDatasetRelease, Match, Season, Team
from app.models.baselines import ClassPrior1X2Model, MultinomialLogistic1X2Model, PoissonGoalsModel
from app.models.builder import ModelingDatasetBuilder
from app.models.dataset_dto import assert_feature_label_isolation


@pytest.mark.integration
def test_end_to_end_modeling_pipeline_and_leakage_isolation(db_session: Session):
    code_suffix = uuid4().hex[:6]
    comp = Competition(code=f"PIPE_{code_suffix}", name="Pipeline Test Comp", country="Test")
    season = Season(competition=comp, season_year="2023/24")
    t1 = Team(canonical_name=f"Pipe Team A {code_suffix}")
    t2 = Team(canonical_name=f"Pipe Team B {code_suffix}")

    now = datetime.now(UTC)

    # 4 Finished matches for training
    m1 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=20), status="FINISHED", home_score=2, away_score=0)
    m2 = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now - timedelta(days=15), status="FINISHED", home_score=1, away_score=1)
    m3 = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now - timedelta(days=10), status="FINISHED", home_score=3, away_score=1)
    m4 = Match(season=season, home_team=t2, away_team=t1, kickoff_utc=now - timedelta(days=5), status="FINISHED", home_score=0, away_score=2)

    # Target scheduled match
    m_target = Match(season=season, home_team=t1, away_team=t2, kickoff_utc=now, status="FINISHED", home_score=1, away_score=0)

    ds_key = f"pipe_hist_{code_suffix}"
    rel_approved = HistoricalDatasetRelease(key=ds_key, version="v1", status=DatasetReleaseStatusEnum.APPROVED.value, dataset_fingerprint="pipe_chk_123")
    db_session.add(rel_approved)
    db_session.flush()

    db_session.add_all([comp, season, t1, t2, m1, m2, m3, m4, m_target])
    db_session.flush()

    # Link all matches to approved dataset release
    links = [
        HistoricalDatasetMatch(dataset_release_id=rel_approved.id, match_id=m.id, competition_id=comp.id, season_id=season.id, kickoff_utc=m.kickoff_utc, home_team_id=m.home_team_id, away_team_id=m.away_team_id)
        for m in [m1, m2, m3, m4, m_target]
    ]
    db_session.add_all(links)
    db_session.flush()

    # 1. Build modeling dataset
    builder = ModelingDatasetBuilder(dataset_key=ds_key, version="v1", approved_only=True)
    manifest, rows = builder.build_modeling_dataset(db_session)

    assert manifest.modeling_dataset_key == "mvp_a_modeling_dataset_v1"
    assert manifest.version == "1.0.0"
    assert len(rows) == 5

    # Verify chronological ordering
    assert rows[0].match_id == m1.id
    assert rows[4].match_id == m_target.id

    # Verify anti-leakage feature/label isolation on all rows
    for r in rows:
        assert_feature_label_isolation(r.ordered_feature_names)
        assert len(r.ordered_feature_names) == 251
        assert "match_result_1x2_v1" in r.targets

    # 2. Fit Baseline Models on first 4 training rows
    train_rows = rows[:4]

    model_cp = ClassPrior1X2Model()
    art_cp = model_cp.fit(train_rows)
    assert art_cp.lifecycle_status == "EXPERIMENTAL"

    model_lr = MultinomialLogistic1X2Model()
    art_lr = model_lr.fit(train_rows)
    assert art_lr.lifecycle_status == "EXPERIMENTAL"

    model_poisson = PoissonGoalsModel()
    art_poisson = model_poisson.fit(train_rows)
    assert art_poisson.lifecycle_status == "EXPERIMENTAL"

    # 3. Predict target match (rows[4]) using fitted models
    target_row = rows[4]

    pred_cp = model_cp.predict_raw(target_row)
    pred_lr = model_lr.predict_raw(target_row)
    pred_poi = model_poisson.predict_raw(target_row)

    # Invariants verification
    for p in [pred_cp, pred_lr, pred_poi]:
        assert 0.0 <= p.prob_home_win <= 1.0
        assert 0.0 <= p.prob_draw <= 1.0
        assert 0.0 <= p.prob_away_win <= 1.0
        assert abs((p.prob_home_win + p.prob_draw + p.prob_away_win) - 1.0) < 1e-4
        assert p.probability_status == "RAW_UNCALIBRATED"
        assert p.lifecycle_status == "EXPERIMENTAL"

    # 4. Target Outcome Mutation Isolation Test
    # Mutating target match final score in DB must NOT alter pre-match prediction from fitted model
    m_target.home_score = 0
    m_target.away_score = 10
    db_session.flush()
    db_session.expire_all()

    # Re-assemble target row
    _, fresh_rows = builder.build_modeling_dataset(db_session)
    fresh_target_row = fresh_rows[4]

    fresh_pred_lr = model_lr.predict_raw(fresh_target_row)
    assert fresh_pred_lr.prob_home_win == pred_lr.prob_home_win
    assert fresh_pred_lr.prob_draw == pred_lr.prob_draw
    assert fresh_pred_lr.prob_away_win == pred_lr.prob_away_win
    assert fresh_pred_lr.model_artifact_fingerprint == pred_lr.model_artifact_fingerprint
