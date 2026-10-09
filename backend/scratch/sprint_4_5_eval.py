import sys
import os
import math
import json
import numpy as np
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, r"c:\Users\kibaj\FB\backend")

from app.db.session import SessionLocal
from app.db.models import Season, Competition
from app.models.builder import ModelingDatasetBuilder
from app.models.baselines.multinomial_logistic import MultinomialLogistic1X2Model
from app.models.baselines.gradient_boosted_tree import GradientBoosted1X2Model
from app.models.baselines.poisson_features import FeatureGoalRegressorModel
from app.models.baselines.hybrid_model import HybridStructuralFeatureModel
from app.models.baselines.attack_defense_poisson import AttackDefensePoissonModel
from app.models.evaluation import ModelEvaluator
from app.models.dataset_dto import ModelingRowDTO

def main():
    print("Loading canonical dataset...")
    db = SessionLocal()
    try:
        # Load dataset
        builder = ModelingDatasetBuilder(dataset_key="mvp_a_historical_v1", version="v1")
        manifest, rows = builder.build_modeling_dataset(db, limit=None)
        
        # Mapping seasons and competitions
        seasons = db.query(Season).all()
        comps = db.query(Competition).all()
        smap = {s.id: s.season_year or s.year_label for s in seasons}
        cmap = {c.id: c.code for c in comps}
        
        train_rows, val_rows, holdout_rows = [], [], []
        for r in rows:
            yr = smap.get(r.season_id)
            if yr == "2021/2022":
                train_rows.append(r)
            elif yr == "2022/2023":
                val_rows.append(r)
            elif yr == "2023/2024":
                holdout_rows.append(r)
                
        print(f"Total Rows: {len(rows)}")
        print(f"Train (21/22): {len(train_rows)}")
        print(f"Val (22/23): {len(val_rows)}")
        print(f"Holdout (23/24): {len(holdout_rows)}")
        
        dev_rows = train_rows + val_rows
        
        # --- Evaluate C1 (Logistic) ---
        print("\n--- Training C1 (Multinomial Logistic Regression) ---")
        c1 = MultinomialLogistic1X2Model(C=0.1)
        c1.fit(dev_rows)
        c1.save_artifact("c1_artifact.json")
        
        # --- Evaluate C2 (GBDT) ---
        print("\n--- Training C2 (Gradient Boosted Tree) ---")
        c2 = GradientBoosted1X2Model(learning_rate=0.05, max_iter=150)
        c2.fit(dev_rows)
        c2.save_artifact("c2_artifact.json")
        
        # --- Evaluate C3 (Goal Regressor) ---
        print("\n--- Training C3 (Poisson Feature Regressor) ---")
        c3 = FeatureGoalRegressorModel(learning_rate=0.05, max_iter=150)
        c3.fit(dev_rows)
        c3.save_artifact("c3_artifact.json")
        
        # --- Evaluate C4 (Hybrid) ---
        print("\n--- Training C4 (Hybrid Structural + ML) ---")
        c4 = HybridStructuralFeatureModel(learning_rate=0.05, max_iter=150)
        c4.fit(dev_rows)
        c4.save_artifact("c4_artifact.json")
        
        print("\n--- Holdout Evaluation ---")
        evaluator = ModelEvaluator()
        
        models = [
            ("M1", AttackDefensePoissonModel(), "m1_artifact.json"),
            ("C1", c1, None),
            ("C2", c2, None),
            ("C3", c3, None),
            ("C4", c4, None),
        ]
        
        models[0][1].fit(dev_rows)
        models[0][1].save_artifact(models[0][2])
        
        results = {}
        for name, m, _ in models:
            metrics = evaluator.evaluate_model(m, holdout_rows)
            results[name] = metrics
            print(f"{name} | N={report.overall_metrics.sample_size} | LL={report.overall_metrics.log_loss:.4f} | Brier={report.overall_metrics.brier_score:.4f} | Acc={report.overall_metrics.accuracy:.4f} | ECE={report.overall_metrics.expected_calibration_error:.4f}")
            
        print("\n--- Per League Evaluation ---")
        for code in ["E0", "SP1", "I1", "D1"]:
            print(f"\\nLeague: {code}")
            l_rows = [r for r in holdout_rows if cmap.get(r.competition_id) == code]
            for name, m, _ in models:
                metrics = evaluator.evaluate_model(m, l_rows)
                print(f"  {name} | N={report.overall_metrics.sample_size} | LL={report.overall_metrics.log_loss:.4f} | Brier={report.overall_metrics.brier_score:.4f}")

        # --- Bootstrap against M1 ---
        print("\n--- Bootstrap Robustness against M1 ---")
        np.random.seed(42)
        n_boot = 1000
        n_test = len(holdout_rows)
        
        # Precompute individual log losses
        m1_preds = [models[0][1].predict_proba(r) for r in holdout_rows]
        m1_ll = []
        for i, r in enumerate(holdout_rows):
            tgt = r.targets["match_result_1x2_v1"]
            p = m1_preds[i][tgt]
            m1_ll.append(-math.log(max(1e-15, p)))
        m1_ll = np.array(m1_ll)
        
        for name, m, _ in models[1:]:
            c_preds = [m.predict_proba(r) for r in holdout_rows]
            c_ll = []
            for i, r in enumerate(holdout_rows):
                tgt = r.targets["match_result_1x2_v1"]
                p = c_preds[i][tgt]
                c_ll.append(-math.log(max(1e-15, p)))
            c_ll = np.array(c_ll)
            
            diff = c_ll - m1_ll
            
            # Bootstrap
            means = []
            for _ in range(n_boot):
                idx = np.random.randint(0, n_test, n_test)
                means.append(diff[idx].mean())
            
            pct_beat = (np.array(means) < 0).mean()
            lower = np.percentile(means, 2.5)
            upper = np.percentile(means, 97.5)
            print(f"{name} vs M1 | Delta LL: {diff.mean():.4f} | 95% CI: [{lower:.4f}, {upper:.4f}] | Win Rate: {pct_beat:.4f}")

    finally:
        db.close()

if __name__ == "__main__":
    main()
