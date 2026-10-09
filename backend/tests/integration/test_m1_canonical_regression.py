import pytest
import sqlite3
import os
from datetime import datetime, timezone
import numpy as np

from app.models.baselines.attack_defense_poisson import AttackDefensePoissonModel
from app.models.dataset_dto import ModelingRowDTO
from app.models.evaluation import ModelEvaluator

def fetch_data():
    conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), "../../football_dev.db"))
    c = conn.cursor()
    c.execute("""
        SELECT 
            m.id, m.kickoff_utc, s.competition_id,
            m.home_team_id, m.away_team_id,
            m.home_score, m.away_score,
            s.id as season_id, s.season_year as season_name
        FROM matches m
        JOIN seasons s ON m.season_id = s.id
        WHERE m.status = 'FINISHED'
          AND s.competition_id IN ('719f254248c84352af579f0b81a5562b', '2a1a49d9968240ba889c366a0608dd02', 'cec923468c38424e93ea78340321570e', 'ac2186e78b5e4cf0b03362c5a82c7c95')
        ORDER BY m.kickoff_utc ASC
    """)
    rows = c.fetchall()
    
    dev_rows, holdout_rows = [], []
    for r in rows:
        match_id, kickoff_str, comp_id, h_id, a_id, h_goals, a_goals, s_id, s_name = r
        kickoff = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
        
        dto = ModelingRowDTO(
            match_id=match_id, kickoff_utc=kickoff, competition_id=comp_id, season_id=s_id,
            home_team_id=h_id, away_team_id=a_id, targets={"home_goals_v1": h_goals, "away_goals_v1": a_goals, "match_result_1x2_v1": 0 if h_goals > a_goals else (1 if h_goals == a_goals else 2)},
            feature_set_fingerprint="dummy", dataset_release_key="dummy", dataset_release_fingerprint="dummy"
        )
        if '2023' in s_name and '2024' in s_name:
            holdout_rows.append(dto)
        else:
            dev_rows.append(dto)
            
    return dev_rows, holdout_rows

@pytest.mark.integration
def test_m1_canonical_holdout_metrics_frozen():
    """
    Canonical M1 Regression Freeze
    Ensures that the exact model structure and evaluation logic 
    continues to produce LL = 0.9929 and Brier = 0.5928 on the N=1,446 holdout.
    """
    dev_rows, holdout_rows = fetch_data()
    assert len(holdout_rows) == 1446, "Holdout N must be exactly 1446"
    assert len(dev_rows) == 2892, "Dev training N must be exactly 2892"
    
    m1 = AttackDefensePoissonModel(regularization_gamma=0.2, min_matches_history=5)
    m1.fit(dev_rows)
    
    res = ModelEvaluator.evaluate_model(m1, holdout_rows)
    
    assert abs(res.overall_metrics.log_loss - 0.9929) < 0.0005, f"Log Loss drift detected! {res.overall_metrics.log_loss}"
    assert abs(res.overall_metrics.brier_score - 0.5928) < 0.0005, f"Brier Score drift detected! {res.overall_metrics.brier_score}"
