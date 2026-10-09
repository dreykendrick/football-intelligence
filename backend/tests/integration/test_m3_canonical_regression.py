import pytest
import sqlite3
import os
from datetime import datetime
import numpy as np

from app.models.baselines.attack_defense_poisson import AttackDefensePoissonModel
from app.models.dataset_dto import ModelingRowDTO
from app.models.evaluation import ModelEvaluator

@pytest.fixture(scope="module")
def canonical_dataset():
    conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), "../../football_dev.db"))
    c = conn.cursor()
    c.execute("""
        SELECT m.id, m.kickoff_utc, s.competition_id, m.home_team_id, m.away_team_id,
               m.home_score, m.away_score, s.id as season_id, s.season_year as season_name
        FROM matches m JOIN seasons s ON m.season_id = s.id
        WHERE m.status = 'FINISHED' 
          AND s.competition_id IN ('719f254248c84352af579f0b81a5562b', '2a1a49d9968240ba889c366a0608dd02', 'cec923468c38424e93ea78340321570e', 'ac2186e78b5e4cf0b03362c5a82c7c95')
        ORDER BY m.kickoff_utc ASC
    """)
    dev_rows, holdout_rows = [], []
    for r in c.fetchall():
        dto = ModelingRowDTO(
            match_id=r[0], kickoff_utc=datetime.fromisoformat(r[1].replace('Z', '+00:00')), 
            competition_id=r[2], season_id=r[7], home_team_id=r[3], away_team_id=r[4], 
            targets={"home_goals_v1": r[5], "away_goals_v1": r[6], "match_result_1x2_v1": 0 if r[5] > r[6] else (1 if r[5] == r[6] else 2)}, feature_set_fingerprint="dummy", dataset_release_key="dummy", dataset_release_fingerprint="dummy"
        )
        if '2023' in r[8] and '2024' in r[8]: holdout_rows.append(dto)
        else: dev_rows.append(dto)
    return dev_rows, holdout_rows

@pytest.mark.integration
def test_m3_canonical_regression(canonical_dataset):
    """
    Ensures that M3-DC produces the reconciled Log Loss = 0.9918 and Brier = 0.5920
    and does not regress to the corrupted 1.0914 state.
    """
    dev_rows, holdout_rows = canonical_dataset
    
    assert len(holdout_rows) == 1446
    
    m3 = AttackDefensePoissonModel(optimize_rho=True, regularization_gamma=0.2, min_matches_history=5)
    m3.fit(dev_rows)
    
    res = ModelEvaluator.evaluate_model(m3, holdout_rows).overall_metrics
    
    assert abs(res.log_loss - 0.9918) < 1e-3, f"M3 Log Loss drifted: {res.log_loss}"
    assert abs(res.brier_score - 0.5920) < 1e-3, f"M3 Brier Score drifted: {res.brier_score}"
