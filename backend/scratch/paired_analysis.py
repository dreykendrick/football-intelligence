import sys, os, sqlite3, numpy as np
from datetime import datetime
sys.path.append('c:/Users/kibaj/FB/backend')
from app.models.dataset_dto import ModelingRowDTO
from app.models.baselines.attack_defense_poisson import AttackDefensePoissonModel
from app.models.engine import GoalDistributionEngine
from app.models.evaluation import ModelEvaluator

# Patch engine to skip independent BTTS check for Dixon-Coles
_orig_btts = GoalDistributionEngine.derive_btts
def _patched_btts(self, matrix, lh, la):
    try: return _orig_btts(self, matrix, lh, la)
    except ValueError:
        arr = np.array(matrix.matrix, dtype=np.float64)
        yes = float(np.sum(arr[1:, 1:]))
        from app.models.base import BTTSProbabilityDTO
        return BTTSProbabilityDTO(yes=min(1.0, max(0.0, yes)), no=min(1.0, max(0.0, 1.0 - yes)))
GoalDistributionEngine.derive_btts = _patched_btts

conn = sqlite3.connect('c:/Users/kibaj/FB/backend/football_dev.db')
c = conn.cursor()
c.execute('''
    SELECT m.id, m.kickoff_utc, s.competition_id, m.home_team_id, m.away_team_id,
           m.home_score, m.away_score, s.id as season_id, s.season_year as season_name
    FROM matches m JOIN seasons s ON m.season_id = s.id
    WHERE m.status = 'FINISHED' 
      AND s.competition_id IN ('719f254248c84352af579f0b81a5562b', '2a1a49d9968240ba889c366a0608dd02', 'cec923468c38424e93ea78340321570e', 'ac2186e78b5e4cf0b03362c5a82c7c95')
    ORDER BY m.kickoff_utc ASC
''')
dev_rows, holdout_rows = [], []
for r in c.fetchall():
    dto = ModelingRowDTO(
        match_id=r[0], kickoff_utc=datetime.fromisoformat(r[1].replace('Z', '+00:00')), 
        competition_id=r[2], season_id=r[7], home_team_id=r[3], away_team_id=r[4], 
        targets={"home_goals_v1": r[5], "away_goals_v1": r[6]}, feature_set_fingerprint="dummy", dataset_release_key="dummy", dataset_release_fingerprint="dummy"
    )
    if '2023' in r[8] and '2024' in r[8]: holdout_rows.append(dto)
    else: dev_rows.append(dto)

print("Training M1...")
m1 = AttackDefensePoissonModel(regularization_gamma=0.2, min_matches_history=5)
m1.fit(dev_rows)
print("Training M3...")
m3 = AttackDefensePoissonModel(optimize_rho=True, regularization_gamma=0.2, min_matches_history=5)
m3.fit(dev_rows)

y_true = []
ll1, ll3 = [], []
b1, b3 = [], []
for r in holdout_rows:
    h, a = r.targets["home_goals_v1"], r.targets["away_goals_v1"]
    y = 0 if h > a else (1 if h == a else 2)
    y_true.append(y)
    
    p1 = m1.predict_raw(r)
    p3 = m3.predict_raw(r)
    p1_probs = [p1.prob_home_win, p1.prob_draw, p1.prob_away_win]
    p3_probs = [p3.prob_home_win, p3.prob_draw, p3.prob_away_win]
    
    ll1.append(-np.log(max(1e-15, min(1-1e-15, p1_probs[y]))))
    ll3.append(-np.log(max(1e-15, min(1-1e-15, p3_probs[y]))))
    
    y_vec = [1 if y == i else 0 for i in range(3)]
    b1.append(sum((p1_probs[i] - y_vec[i])**2 for i in range(3)))
    b3.append(sum((p3_probs[i] - y_vec[i])**2 for i in range(3)))

ll1 = np.array(ll1); ll3 = np.array(ll3)
b1 = np.array(b1); b3 = np.array(b3)

delta_ll = ll3 - ll1
delta_b = b3 - b1

print("--- PAIRED ANALYSIS ---")
print(f"Mean LL delta (M3 - M1): {np.mean(delta_ll):.6f}")
print(f"Median LL delta: {np.median(delta_ll):.6f}")
print(f"Std LL delta: {np.std(delta_ll):.6f}")
print(f"Min LL delta: {np.min(delta_ll):.6f}")
print(f"Max LL delta: {np.max(delta_ll):.6f}")
print(f"M3 Better LL count: {np.sum(delta_ll < -1e-6)}")
print(f"M1 Better LL count: {np.sum(delta_ll > 1e-6)}")
print(f"Ties LL count: {np.sum(np.abs(delta_ll) <= 1e-6)}")

print(f"Mean Brier delta: {np.mean(delta_b):.6f}")
print(f"M3 Better B count: {np.sum(delta_b < -1e-6)}")
print(f"M1 Better B count: {np.sum(delta_b > 1e-6)}")
print(f"Ties B count: {np.sum(np.abs(delta_b) <= 1e-6)}")

print("--- BOOTSTRAP ---")
np.random.seed(42)
n_boot = 10000
boot_ll = np.zeros(n_boot)
boot_b = np.zeros(n_boot)
for i in range(n_boot):
    idx = np.random.randint(0, len(holdout_rows), len(holdout_rows))
    boot_ll[i] = np.mean(delta_ll[idx])
    boot_b[i] = np.mean(delta_b[idx])

print(f"95% CI LL: [{np.percentile(boot_ll, 2.5):.6f}, {np.percentile(boot_ll, 97.5):.6f}]")
print(f"95% CI Brier: [{np.percentile(boot_b, 2.5):.6f}, {np.percentile(boot_b, 97.5):.6f}]")
print(f"Fraction M3 better (LL): {np.mean(boot_ll < 0):.4f}")
print(f"Fraction M3 better (Brier): {np.mean(boot_b < 0):.4f}")
