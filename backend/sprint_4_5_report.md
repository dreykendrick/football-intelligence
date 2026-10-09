# SPRINT 4.5 SCIENTIFIC CERTIFICATION REPORT & AUDIT

## 1. SPRINT OBJECTIVE
Evaluate feature-based machine-learning challengers (C1-C4) against the frozen structural Phase 4 Champion (M1 — Attack-Defense Poisson).

## 2. ENGINEERING EXECUTION

### 2.1 Feature Audit & Missingness (FS1)
- The raw dataset (`mvp_a_historical_v1`) contains 4,338 matches. 
- The manifest specifies exactly 251 point-in-time features.
- We discovered that `app.models.builder.ModelingDatasetBuilder` dynamically computes features per match via `FeatureSetAssembler` unless `feature_snapshots` are pre-cached.

### 2.2 Infrastructure Blocker Identified
- Benchmarks showed that evaluating the 251 features per match takes approximately **~5 seconds per row** in an uncached SQLite `football_dev.db`.
- Total computation time for 4,338 matches without cache: **~6.0 hours**.
- The `app/features/cli.py build` command fails consistently with `sqlite3.OperationalError: database is locked` due to heavy transaction overhead when run on this instance.
- **Therefore, instantaneous metric generation on the exact 1,446 holdout fixtures was computationally impossible during this session.**

### 2.3 Model Implementations
Despite the data extraction bottleneck, all four challenger models have been fully implemented, rigorously typed, and regression-tested via dummy mock datasets in `test_sprint_4_5_ml_models.py`.

- **C1 — Multinomial Logistic Regression (`multinomial_logistic.py`)**: Strict `1X2` targets, optimized with L-BFGS, serializes to JSON weights.
- **C2 — Gradient Boosted Tree (`gradient_boosted_tree.py`)**: Leverages `HistGradientBoostingClassifier`, explicitly ignores missing values via native tree handling.
- **C3 — Poisson Feature Regressor (`poisson_features.py`)**: Uses `HistGradientBoostingRegressor` with `loss='poisson'` to predict exact `lambda_home` and `lambda_away`, routing them through the `GoalDistributionEngine` to retain all probability distribution capabilities (`1X2`, `BTTS`, Exact Score).
- **C4 — Hybrid Structural/ML (`hybrid_model.py`)**: Dynamically computes strictly out-of-fold `M1` structural expected goals (to prevent target stacking leakage) and horizontally stacks them with the 251 raw features into a `HistGradientBoostingClassifier`.

## 3. CERTIFICATION GATE EVALUATION

**Is Sprint 4.5 COMPLETE?**
> **FAIL**

**Reasoning:**
The Sprint 4.5 Definition of Done strictly mandates:
- "Run validation after each."
- "Produce the exact comparison vs M1 using identical 1,446 holdout fixtures."
- "All values must come from actual execution."

Because the database was not pre-cached with feature snapshots, we could not evaluate the holdout rows to populate the canonical LL/Brier evaluation matrix. The code is complete, but the scientific evaluation is blocked.

**Action Required:**
Before proceeding, the engineering team must run `app/features/cli.py build` asynchronously in isolated batches (to prevent DB lock issues) until all 4,338 matches exist in `feature_snapshots`. Once cached, `sprint_4_5_eval.py` can execute in seconds.

## 4. NEXT STEPS
- Sprint 4.5 remains **BLOCKED / INCOMPLETE**.
- Sprint 4.6 cannot be started.
- The evaluation script `scratch/sprint_4_5_eval.py` is ready to run the moment the snapshot cache is hydrated.
