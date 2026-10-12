import pytest
import sqlite3
import os
from datetime import datetime
import numpy as np

from app.models.baselines.attack_defense_poisson import AttackDefensePoissonModel
from app.models.dataset_dto import ModelingRowDTO
from app.models.engine import GoalDistributionEngine
from app.models.evaluation import ModelEvaluator

@pytest.fixture(scope="module")
def canonical_dataset():
    db_file = os.path.join(os.path.dirname(__file__), "../../football_dev.db")
    if not os.path.exists(db_file):
        pytest.skip(f"Historical SQLite database {db_file} not found; skipping canonical holdout test.")
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    try:
        c.execute("""
            SELECT m.id, m.kickoff_utc, s.competition_id, m.home_team_id, m.away_team_id,
                   m.home_score, m.away_score, s.id as season_id, s.season_year as season_name
            FROM matches m JOIN seasons s ON m.season_id = s.id
            WHERE m.status = 'FINISHED' 
              AND s.competition_id IN ('719f254248c84352af579f0b81a5562b', '2a1a49d9968240ba889c366a0608dd02', 'cec923468c38424e93ea78340321570e', 'ac2186e78b5e4cf0b03362c5a82c7c95')
            ORDER BY m.kickoff_utc ASC
        """)
    except sqlite3.OperationalError as e:
        pytest.skip(f"Historical SQLite database does not contain matches table ({e}); skipping.")
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
def test_aggregation_consistency(canonical_dataset):
    """
    Guarantees future evaluators satisfy:
    direct overall Log Loss == weighted per-league Log Loss
    direct overall Brier == weighted per-league Brier
    """
    dev_rows, holdout_rows = canonical_dataset
    
    # We use M1 for this basic structural test
    m = AttackDefensePoissonModel(regularization_gamma=0.2, min_matches_history=5)
    m.fit(dev_rows)
    
    # Compute overall directly
    res_overall = ModelEvaluator.evaluate_model(m, holdout_rows).overall_metrics
    
    # Compute per league
    leagues = set(r.competition_id for r in holdout_rows)
    weighted_ll = 0.0
    weighted_brier = 0.0
    total_n = len(holdout_rows)
    
    for l_id in leagues:
        l_rows = [r for r in holdout_rows if r.competition_id == l_id]
        res = ModelEvaluator.evaluate_model(m, l_rows).overall_metrics
        weighted_ll += res.log_loss * len(l_rows)
        weighted_brier += res.brier_score * len(l_rows)
        
    weighted_ll /= total_n
    weighted_brier /= total_n
    
    assert abs(res_overall.log_loss - weighted_ll) < 1e-6, "Log loss aggregation mismatch"
    assert abs(res_overall.brier_score - weighted_brier) < 1e-6, "Brier score aggregation mismatch"
