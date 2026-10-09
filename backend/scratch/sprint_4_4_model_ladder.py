import sys
import os
import sqlite3
import numpy as np
from datetime import datetime
from uuid import uuid4

# Append project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.models.dataset_dto import ModelingRowDTO
from app.models.baselines.league_average import LeagueAveragePoissonModel
from app.models.baselines.attack_defense_poisson import AttackDefensePoissonModel
from app.models.calibration import ProbabilityCalibrator
from app.models.baselines.calibrated_model import CalibratedPredictionModel
from app.models.evaluation import ModelEvaluator
from app.models.targets import INT_TO_1X2_MAP

def fetch_data():
    conn = sqlite3.connect(os.path.join(os.path.dirname(__file__), "..", "football_dev.db"))
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
        ORDER BY m.kickoff_utc ASC
    """)
    rows = c.fetchall()
    
    dev_rows = []
    holdout_rows = []
    
    for r in rows:
        match_id, kickoff_str, comp_id, h_id, a_id, h_goals, a_goals, s_id, s_name = r
        kickoff = datetime.fromisoformat(kickoff_str.replace('Z', '+00:00'))
        
        dto = ModelingRowDTO(
            match_id=match_id,
            kickoff_utc=kickoff,
            competition_id=comp_id,
            season_id=s_id,
            home_team_id=h_id,
            away_team_id=a_id,
            targets={"home_goals_v1": h_goals, "away_goals_v1": a_goals},
            feature_set_fingerprint="dummy",
            dataset_release_key="dummy",
            dataset_release_fingerprint="dummy"
        )
        
        if '2023' in s_name and '2024' in s_name:
            holdout_rows.append(dto)
        else:
            dev_rows.append(dto)
            
    return dev_rows, holdout_rows

def evaluate_model(model, test_rows):
    y_true = []
    y_probs = []
    
    for r in test_rows:
        h = r.targets["home_goals_v1"]
        a = r.targets["away_goals_v1"]
        if h > a: y = 0
        elif h == a: y = 1
        else: y = 2
        y_true.append(y)
        
        try:
            pred = model.predict_raw(r)
            y_probs.append([pred.prob_home_win, pred.prob_draw, pred.prob_away_win])
        except Exception as e:
            y_probs.append([1/3, 1/3, 1/3])
            
    metrics = ModelEvaluator.compute_metric_summary(y_true, y_probs)
    return metrics, y_probs, y_true

print("Loading data...")
dev_rows, holdout_rows = fetch_data()
print(f"Dev rows: {len(dev_rows)}, Holdout rows: {len(holdout_rows)}")

results = {}

print("Training M0...")
m0 = LeagueAveragePoissonModel()
m0.fit(dev_rows)
res0, _, _ = evaluate_model(m0, holdout_rows)
results["M0"] = res0

print("Training M1...")
m1 = AttackDefensePoissonModel()
m1.fit(dev_rows)
res1, _, _ = evaluate_model(m1, holdout_rows)
results["M1"] = res1

print("Training M2...")
m2 = AttackDefensePoissonModel(time_decay_half_life_days=365.0)
m2.fit(dev_rows)
res2, _, _ = evaluate_model(m2, holdout_rows)
results["M2"] = res2

print("Training M3...")
m3 = AttackDefensePoissonModel(optimize_rho=True)
m3.fit(dev_rows)
res3, _, _ = evaluate_model(m3, holdout_rows)
results["M3"] = res3

print("Training M4 (Calibration)...")
# Make threshold offset-naive to match DB output if needed, or enforce UTC
threshold = datetime(2022, 8, 1)

dev_train = [r for r in dev_rows if r.kickoff_utc.replace(tzinfo=None) < threshold]
dev_val = [r for r in dev_rows if r.kickoff_utc.replace(tzinfo=None) >= threshold]

m1_calib = AttackDefensePoissonModel()
m1_calib.fit(dev_train)
_, val_probs, val_y = evaluate_model(m1_calib, dev_val)

calibrator = ProbabilityCalibrator()
calibrator.fit(np.array(val_probs), np.array(val_y))

m4 = CalibratedPredictionModel(raw_model=m1)
m4.calibrator = calibrator
m4.artifact = m1.artifact
res4, _, _ = evaluate_model(m4, holdout_rows)
results["M4"] = res4

with open(os.path.join(os.path.dirname(__file__), "sprint4_4_results.txt"), "w") as f:
    for name, res in results.items():
        print(f"\n{name} Results:")
        print(f"Log Loss: {res.log_loss:.4f}")
        print(f"Brier Score: {res.brier_score:.4f}")
        print(f"ECE: {res.expected_calibration_error:.4f}")
        
        f.write(f"{name} Results:\n")
        f.write(f"Log Loss: {res.log_loss:.4f}\n")
        f.write(f"Brier Score: {res.brier_score:.4f}\n")
        f.write(f"ECE: {res.expected_calibration_error:.4f}\n\n")
