import sys, os, sqlite3, numpy as np, json
from datetime import datetime, timezone
from uuid import uuid4

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.baselines.attack_defense_poisson import AttackDefensePoissonModel
from app.models.baselines.league_average import LeagueAveragePoissonModel
from app.models.calibration import ProbabilityCalibrator
from app.models.baselines.calibrated_model import CalibratedPredictionModel
from app.models.evaluation import ModelEvaluator
from app.models.dataset_dto import ModelingRowDTO

PRIMARY_LEAGUES = {
    "719f254248c84352af579f0b81a5562b": "Premier League",
    "2a1a49d9968240ba889c366a0608dd02": "La Liga",
    "cec923468c38424e93ea78340321570e": "Serie A",
    "ac2186e78b5e4cf0b03362c5a82c7c95": "Bundesliga"
}

print("--- 1. FETCHING DATA ---")
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
        home_team_id=h_id, away_team_id=a_id, targets={"home_goals_v1": h_goals, "away_goals_v1": a_goals},
        feature_set_fingerprint="dummy", dataset_release_key="dummy", dataset_release_fingerprint="dummy"
    )
    if '2023' in s_name and '2024' in s_name: holdout_rows.append(dto)
    else: dev_rows.append(dto)


from app.models.engine import GoalDistributionEngine
# Patch engine to skip independent BTTS check for Dixon-Coles
_orig_btts = GoalDistributionEngine.derive_btts
def _patched_btts(self, matrix, lh, la):
    try:
        return _orig_btts(self, matrix, lh, la)
    except ValueError:
        arr = np.array(matrix.matrix, dtype=np.float64)
        yes = float(np.sum(arr[1:, 1:]))
        from app.models.base import BTTSProbabilityDTO
        return BTTSProbabilityDTO(yes=min(1.0, max(0.0, yes)), no=min(1.0, max(0.0, 1.0 - yes)))
GoalDistributionEngine.derive_btts = _patched_btts
def evaluate(model, test_rows):
    y_true, y_probs = [], []
    for r in test_rows:
        h, a = r.targets["home_goals_v1"], r.targets["away_goals_v1"]
        y_true.append(0 if h > a else (1 if h == a else 2))
        pred = model.predict_raw(r)
        y_probs.append([pred.prob_home_win, pred.prob_draw, pred.prob_away_win])
    metrics = ModelEvaluator.compute_metric_summary(y_true, y_probs)
    return metrics, y_true, y_probs

print("Fitting M0...")
m0 = LeagueAveragePoissonModel(); m0.fit(dev_rows)
print("Fitting M1...")
m1 = AttackDefensePoissonModel(regularization_gamma=0.2, min_matches_history=5); m1.fit(dev_rows)
print("Fitting M2...")
m2 = AttackDefensePoissonModel(time_decay_half_life_days=365.0, regularization_gamma=0.2, min_matches_history=5); m2.fit(dev_rows)
print("Fitting M3-DC...")
m3 = AttackDefensePoissonModel(optimize_rho=True, regularization_gamma=0.2, min_matches_history=5); m3.fit(dev_rows)

print("Fitting M4...")
dev_train = [r for r in dev_rows if r.kickoff_utc.replace(tzinfo=None) < datetime(2022, 8, 1)]
dev_val = [r for r in dev_rows if r.kickoff_utc.replace(tzinfo=None) >= datetime(2022, 8, 1)]
m1_calib = AttackDefensePoissonModel(regularization_gamma=0.2, min_matches_history=5)
m1_calib.fit(dev_train)
_, val_y, val_probs = evaluate(m1_calib, dev_val)
calibrator = ProbabilityCalibrator()
calibrator.fit(np.array(val_probs), np.array(val_y))
m4 = CalibratedPredictionModel(raw_model=m1)
m4.calibrator = calibrator
m4.artifact = m1.artifact
models = {"M0": m0, "M1": m1, "M2": m2, "M3-DC": m3, "M4": m4}

def calc_classwise_ece(y_true, y_probs):
    def class_ece(k):
        probs = np.array([p[k] for p in y_probs])
        labels = np.array([1 if y == k else 0 for y in y_true])
        bins = np.linspace(0, 1, 11)
        ece = 0.0
        for i in range(10):
            mask = (probs >= bins[i]) & (probs < bins[i+1]) if i<9 else (probs >= bins[i]) & (probs <= bins[i+1])
            if np.sum(mask) > 0: ece += (np.sum(mask) / len(y_true)) * abs(np.mean(labels[mask]) - np.mean(probs[mask]))
        return ece
    return class_ece(0), class_ece(1), class_ece(2)

print("\n--- 2. PER-LEAGUE METRICS ---")
for comp_id, league_name in PRIMARY_LEAGUES.items():
    comp_holdout = [r for r in holdout_rows if str(r.competition_id).replace("-", "") == comp_id]
    print(f"\n{league_name} (N={len(comp_holdout)})")
    for m_name, m in models.items():
        res, yt, yp = evaluate(m, comp_holdout)
        e0, e1, e2 = calc_classwise_ece(yt, yp)
        print(f"  {m_name}: LL={res.log_loss:.4f} Brier={res.brier_score:.4f} Acc={res.accuracy:.4f} ECE_Avg={(e0+e1+e2)/3.0:.4f}")

print("\n--- 3. ESS CALCULATION ---")
for comp_id, league_name in PRIMARY_LEAGUES.items():
    comp_dev = [r for r in dev_rows if str(r.competition_id).replace("-", "") == comp_id]
    n = len(comp_dev)
    if n > 0:
        max_dt = max(r.kickoff_utc for r in comp_dev)
        weights = [2.0 ** (-((max_dt - r.kickoff_utc).total_seconds() / 86400.0) / 365.0) for r in comp_dev]
        sum_w, sum_w2 = sum(weights), sum(w*w for w in weights)
        ess = (sum_w * sum_w) / sum_w2
        print(f"{league_name} | Raw N={n} | Sum W={sum_w:.1f} | ESS={ess:.1f} | ESS/N={ess/n:.3f}")

print("\n--- 4. M3-DC DIAGNOSTICS ---")
for comp_id, cd in list(m3.artifact.weights_payload["competitions"].items()):
    clean_id = comp_id.replace("-", "")
    if clean_id in PRIMARY_LEAGUES:
        diag = cd.get("diagnostics", {})
        print(f"{PRIMARY_LEAGUES[clean_id]}: rho={cd.get('dixon_coles_rho',0):.4f}, initial={diag.get('initial_rho')}, "
              f"success={diag.get('optimizer_success')}, iter={diag.get('n_iter')}, nfev={diag.get('n_fev')}, "
              f"ini_obj={diag.get('initial_objective')}, fin_obj={diag.get('final_objective')}")

print("\n--- 5. RELIABILITY TABLES ---")
def print_rel(y_true, y_probs, name):
    print(f"\nReliability Table for {name}")
    for k, cname in enumerate(["HOME", "DRAW", "AWAY"]):
        probs, labels = np.array([p[k] for p in y_probs]), np.array([1 if y==k else 0 for y in y_true])
        bins = np.linspace(0, 1, 11)
        print(f"  {cname}:")
        for i in range(10):
            mask = (probs >= bins[i]) & (probs < bins[i+1]) if i<9 else (probs >= bins[i]) & (probs <= bins[i+1])
            if np.sum(mask) > 0:
                print(f"    [{bins[i]:.1f}, {bins[i+1]:.1f}) N={np.sum(mask):4d} | P={np.mean(probs[mask]):.4f} | Obs={np.mean(labels[mask]):.4f} | Gap={abs(np.mean(labels[mask])-np.mean(probs[mask])):.4f}")

_, yt, yp1 = evaluate(m1, holdout_rows)
_, yt, yp4 = evaluate(m4, holdout_rows)
print_rel(yt, yp1, "M1")
print_rel(yt, yp4, "M4")

print("\n--- 6. DC MULTI-START (Premier League Only) ---")
from app.models.preprocessing import ModelPreprocessor
from scipy.optimize import minimize
import app.models.baselines.attack_defense_poisson as adp
pl_id = "719f254248c84352af579f0b81a5562b"
dev_pl = [r for r in dev_rows if str(r.competition_id).replace("-", "") == pl_id]
h_ids, a_ids, h_goals, a_goals, h_counts, a_counts, _, _ = ModelPreprocessor.prepare_poisson_vectors(dev_pl)
team_idx = {t: i for i, t in enumerate(set(h_ids).union(a_ids))}
num_teams = len(team_idx)
h_idx = np.array([team_idx[t] for t in h_ids])
a_idx = np.array([team_idx[t] for t in a_ids])
home_goals_arr, away_goals_arr = np.array(h_goals, dtype=float), np.array(a_goals, dtype=float)

bounds = [(None, None)] * (2 + 2 * num_teams) + [(-0.2, 0.2)]
for r_start in [0.0, 0.05, -0.05]:
    theta0 = np.zeros(2 + 2 * num_teams + 1)
    theta0[0] = 0.05; theta0[1] = 0.25; theta0[-1] = r_start
    res = minimize(adp._poisson_nll_objective, theta0, args=(h_idx, a_idx, home_goals_arr, away_goals_arr, num_teams, 0.2, None, True),
                   method='L-BFGS-B', jac=True, bounds=bounds, options={'maxiter': 100})
    print(f"Start {r_start}: success={res.success} final_rho={res.x[-1]:.4f} obj={res.fun:.4f}")
