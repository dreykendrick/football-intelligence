import pytest
import numpy as np
import math
from datetime import datetime
from uuid import uuid4
from app.models.dataset_dto import ModelingRowDTO
from app.models.baselines.multinomial_logistic import MultinomialLogistic1X2Model
from app.models.baselines.gradient_boosted_tree import GradientBoosted1X2Model
from app.models.baselines.poisson_features import FeatureGoalRegressorModel
from app.models.baselines.hybrid_model import HybridStructuralFeatureModel
import os

def create_mock_rows(n=50):
    rows = []
    np.random.seed(42)
    fixed_comp = uuid4()
    teams = [uuid4() for _ in range(5)]
    for _ in range(n):
        fvals = np.random.randn(10).tolist()
        # Ensure some separation
        h_goals = int(np.random.poisson(max(0.1, 1.5 + fvals[0])))
        a_goals = int(np.random.poisson(max(0.1, 1.0 - fvals[0])))
        if h_goals > a_goals:
            res = 0
        elif h_goals == a_goals:
            res = 1
        else:
            res = 2
            
        r = ModelingRowDTO(
            match_id=uuid4(),
            competition_id=fixed_comp,
            home_team_id=np.random.choice(teams),
            away_team_id=np.random.choice(teams),
            season_id=uuid4(),
            kickoff_utc=datetime.utcnow(),
            dataset_release_key="test",
            feature_set_key="mvp_a_feature_set_v1",
            ordered_feature_names=[f"f_{i}" for i in range(10)],
            feature_values=fvals,
            targets={
                "match_result_1x2_v1": res,
                "home_goals_v1": h_goals,
                "away_goals_v1": a_goals
            }
        )
        rows.append(r)
    return rows

@pytest.fixture
def mock_dataset():
    return create_mock_rows(100)

def test_c1_logistic(mock_dataset, tmp_path):
    model = MultinomialLogistic1X2Model(C=1.0)
    model.fit(mock_dataset)
    pred = model.predict_raw(mock_dataset[0])
    assert abs(pred.prob_home_win + pred.prob_draw + pred.prob_away_win - 1.0) < 1e-4
    
    path = str(tmp_path / "c1.json")
    model.save_artifact(path)
    model2 = MultinomialLogistic1X2Model()
    model2.load_artifact(path)
    pred2 = model2.predict_raw(mock_dataset[0])
    assert abs(pred.prob_home_win - pred2.prob_home_win) < 1e-6

def test_c2_gbdt(mock_dataset, tmp_path):
    model = GradientBoosted1X2Model(max_iter=5)
    model.fit(mock_dataset)
    pred = model.predict_raw(mock_dataset[0])
    assert abs(pred.prob_home_win + pred.prob_draw + pred.prob_away_win - 1.0) < 1e-4
    
    path = str(tmp_path / "c2.json")
    model.save_artifact(path)
    model2 = GradientBoosted1X2Model()
    model2.load_artifact(path)
    pred2 = model2.predict_raw(mock_dataset[0])
    assert abs(pred.prob_home_win - pred2.prob_home_win) < 1e-6

def test_c3_poisson_features(mock_dataset, tmp_path):
    model = FeatureGoalRegressorModel(max_iter=5)
    model.fit(mock_dataset)
    pred = model.predict_raw(mock_dataset[0])
    assert pred.predicted_home_goals > 0
    assert pred.predicted_away_goals > 0
    assert abs(pred.prob_home_win + pred.prob_draw + pred.prob_away_win - 1.0) < 1e-4
    
    path = str(tmp_path / "c3.json")
    model.save_artifact(path)
    model2 = FeatureGoalRegressorModel()
    model2.load_artifact(path)
    pred2 = model2.predict_raw(mock_dataset[0])
    assert abs(pred.predicted_home_goals - pred2.predicted_home_goals) < 1e-6

def test_c4_hybrid(mock_dataset, tmp_path):
    model = HybridStructuralFeatureModel(max_iter=5)
    model.fit(mock_dataset)
    pred = model.predict_raw(mock_dataset[0])
    assert abs(pred.prob_home_win + pred.prob_draw + pred.prob_away_win - 1.0) < 1e-4
    
    path = str(tmp_path / "c4.json")
    model.save_artifact(path)
    model2 = HybridStructuralFeatureModel()
    model2.load_artifact(path)
    pred2 = model2.predict_raw(mock_dataset[0])
    assert abs(pred.prob_home_win - pred2.prob_home_win) < 1e-6
