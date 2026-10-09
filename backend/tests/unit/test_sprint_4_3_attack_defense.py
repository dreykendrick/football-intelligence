"""
Unit & Integration Test Suite for Sprint 4.3 — Team-Specific Attack-Defence Poisson Model
Verifies log-linear Poisson formulation, zero-sum identifiability constraints, L2 regularization,
synthetic parameter recovery, multi-competition parameter isolation, cold-start fallback policies,
team-sensitivity (perturbation, swap, variance), artifact serialization integrity, and ProbabilityEngine integration.
"""
import json
import math
import os
import tempfile
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import numpy as np
import pytest

from app.models.base import ModelCapabilityEnum, TrainedModelArtifact, TrainingWindow
from app.models.baselines.attack_defense_poisson import (
    AttackDefensePoissonModel,
    _fit_competition_poisson,
)
from app.models.dataset_dto import ModelingRowDTO
from app.models.engine import GoalDistributionEngine, ProbabilityInvariantValidator
from app.models.router import ProbabilityEngine


def _create_mock_match_row(
    comp_id: UUID,
    season_id: UUID,
    home_team_id: UUID,
    away_team_id: UUID,
    home_goals: int = 1,
    away_goals: int = 1,
    home_team_name: str | None = None,
    away_team_name: str | None = None,
    kickoff: datetime | None = None,
) -> ModelingRowDTO:
    f_names = [
        "league_home_goals_per_match_v1",
        "league_away_goals_per_match_v1",
        "home_attack_strength_v1",
        "home_defense_strength_v1",
        "away_attack_strength_v1",
        "away_defense_strength_v1",
    ]
    f_vals = [1.5, 1.2, 1.0, 1.0, 1.0, 1.0]
    return ModelingRowDTO(
        match_id=uuid4(),
        competition_id=comp_id,
        season_id=season_id,
        kickoff_utc=kickoff or datetime(2023, 1, 1, 15, 0, tzinfo=UTC),
        temporal_precision="EXACT_TIMESTAMP",
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        dataset_release_key="mvp_a_historical:v1",
        dataset_release_fingerprint="test_fp",
        feature_set_key="mvp_a_feature_set_v1",
        feature_set_fingerprint="fset_fp",
        ordered_feature_names=f_names,
        feature_values=f_vals,
        targets={
            "home_goals_v1": home_goals,
            "away_goals_v1": away_goals,
            "match_result_1x2_v1": 0 if home_goals > away_goals else (1 if home_goals == away_goals else 2),
            "over_under_2_5_v1": (home_goals + away_goals) >= 3,
            "btts_v1": (home_goals > 0) and (away_goals > 0),
        },
    )


# -----------------------------------------------------------------------------
# Test 01: Log-Linear Lambda Formula and Sign Directions
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_01_log_linear_lambda_formula_and_signs():
    comp_id = uuid4()
    t_a = uuid4()
    t_b = uuid4()
    t_c = uuid4()

    # Synthetic round-robin data
    rows = [
        _create_mock_match_row(comp_id, uuid4(), t_a, t_b, 3, 0),
        _create_mock_match_row(comp_id, uuid4(), t_b, t_c, 2, 1),
        _create_mock_match_row(comp_id, uuid4(), t_c, t_a, 0, 2),
        _create_mock_match_row(comp_id, uuid4(), t_b, t_a, 1, 3),
        _create_mock_match_row(comp_id, uuid4(), t_c, t_b, 1, 2),
        _create_mock_match_row(comp_id, uuid4(), t_a, t_c, 4, 0),
    ]

    model = AttackDefensePoissonModel(regularization_gamma=0.1)
    artifact = model.fit(rows)

    comp_weights = artifact.weights_payload["competitions"][str(comp_id)]
    alpha = comp_weights["team_attack_strengths"]
    delta = comp_weights["team_defense_strengths"]

    # Team A scored many goals and conceded few:
    # alpha(A) > alpha(B) > alpha(C)
    # delta(A) > delta(C)
    assert alpha[str(t_a)] > alpha[str(t_c)]
    assert delta[str(t_a)] > delta[str(t_c)]

    pred_ab = model.predict_raw(_create_mock_match_row(comp_id, uuid4(), t_a, t_b))
    pred_ba = model.predict_raw(_create_mock_match_row(comp_id, uuid4(), t_b, t_a))

    # Team A at home has much higher lambda than Team B at home
    assert pred_ab.predicted_home_goals > pred_ba.predicted_home_goals


# -----------------------------------------------------------------------------
# Test 02: Zero-Sum Identifiability Constraints
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_02_zero_sum_identifiability_constraints():
    comp_id = uuid4()
    teams = [uuid4() for _ in range(6)]
    rows = []
    np.random.seed(42)
    for i in range(len(teams)):
        for j in range(len(teams)):
            if i != j:
                hg = int(np.random.poisson(1.5 + (i - j) * 0.2))
                ag = int(np.random.poisson(1.1 + (j - i) * 0.2))
                rows.append(_create_mock_match_row(comp_id, uuid4(), teams[i], teams[j], max(0, hg), max(0, ag)))

    model = AttackDefensePoissonModel(regularization_gamma=0.2)
    artifact = model.fit(rows)

    comp_weights = artifact.weights_payload["competitions"][str(comp_id)]
    alphas = list(comp_weights["team_attack_strengths"].values())
    deltas = list(comp_weights["team_defense_strengths"].values())

    sum_alpha = sum(alphas)
    sum_delta = sum(deltas)

    assert abs(sum_alpha) < 1e-10, f"Identifiability violation: sum(alpha) = {sum_alpha}"
    assert abs(sum_delta) < 1e-10, f"Identifiability violation: sum(delta) = {sum_delta}"


# -----------------------------------------------------------------------------
# Test 03: L2 Regularization Shrinkage
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_03_l2_regularization_shrinkage():
    comp_id = uuid4()
    t_strong = uuid4()
    t_weak = uuid4()

    rows = [
        _create_mock_match_row(comp_id, uuid4(), t_strong, t_weak, 5, 0),
        _create_mock_match_row(comp_id, uuid4(), t_weak, t_strong, 0, 4),
        _create_mock_match_row(comp_id, uuid4(), t_strong, t_weak, 4, 1),
    ]

    m_low_reg = AttackDefensePoissonModel(regularization_gamma=0.01)
    art_low = m_low_reg.fit(rows)

    m_high_reg = AttackDefensePoissonModel(regularization_gamma=2.0)
    art_high = m_high_reg.fit(rows)

    alpha_low = abs(art_low.weights_payload["competitions"][str(comp_id)]["team_attack_strengths"][str(t_strong)])
    alpha_high = abs(art_high.weights_payload["competitions"][str(comp_id)]["team_attack_strengths"][str(t_strong)])

    assert alpha_high < alpha_low, "Higher L2 regularization must shrink team parameters toward zero"


# -----------------------------------------------------------------------------
# Test 04: Synthetic Parameter Recovery
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_04_synthetic_parameter_recovery():
    # True data generating process: 4 teams with known strengths
    true_mu = 0.1
    true_h = 0.25
    true_alphas = [0.4, 0.1, -0.1, -0.4]  # Team 0 strongest, Team 3 weakest
    true_deltas = [0.3, 0.1, -0.1, -0.3]  # Team 0 best defence, Team 3 worst

    num_teams = 4
    n_rounds = 30
    np.random.seed(123)

    home_indices = []
    away_indices = []
    home_goals = []
    away_goals = []

    for _ in range(n_rounds):
        for i in range(num_teams):
            for j in range(num_teams):
                if i != j:
                    lh = math.exp(true_mu + true_h + true_alphas[i] - true_deltas[j])
                    la = math.exp(true_mu + true_alphas[j] - true_deltas[i])
                    gh = np.random.poisson(lh)
                    ga = np.random.poisson(la)
                    home_indices.append(i)
                    away_indices.append(j)
                    home_goals.append(gh)
                    away_goals.append(ga)

    res = _fit_competition_poisson(
        home_indices=np.array(home_indices),
        away_indices=np.array(away_indices),
        home_goals=np.array(home_goals),
        away_goals=np.array(away_goals),
        num_teams=num_teams,
        gamma=0.05,
    )

    assert res["success"] is True
    est_alphas = res["alpha"]
    est_deltas = res["delta"]

    # Parameter ordering preserved
    assert est_alphas[0] > est_alphas[1] > est_alphas[2] > est_alphas[3]
    assert est_deltas[0] > est_deltas[1] > est_deltas[2] > est_deltas[3]
    assert pytest.approx(res["home_advantage"], abs=0.15) == true_h


# -----------------------------------------------------------------------------
# Test 05: Multi-Competition Isolation
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_05_multi_competition_isolation():
    comp1 = uuid4()
    comp2 = uuid4()
    t1, t2 = uuid4(), uuid4()
    t3, t4 = uuid4(), uuid4()

    # Comp 1: High scoring league (avg 3.5 goals)
    rows_c1 = [
        _create_mock_match_row(comp1, uuid4(), t1, t2, 3, 2),
        _create_mock_match_row(comp1, uuid4(), t2, t1, 2, 3),
    ] * 5

    # Comp 2: Low scoring league (avg 1.0 goals)
    rows_c2 = [
        _create_mock_match_row(comp2, uuid4(), t3, t4, 1, 0),
        _create_mock_match_row(comp2, uuid4(), t4, t3, 0, 1),
    ] * 5

    model = AttackDefensePoissonModel()
    artifact = model.fit(rows_c1 + rows_c2)

    comps = artifact.weights_payload["competitions"]
    assert str(comp1) in comps
    assert str(comp2) in comps

    # High scoring comp must have larger baseline mu
    assert comps[str(comp1)]["goal_baseline_mu"] > comps[str(comp2)]["goal_baseline_mu"]


# -----------------------------------------------------------------------------
# Test 06: Cold-Start Unseen Team Policy
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_06_cold_start_unseen_team_policy():
    comp_id = uuid4()
    t_known1, t_known2 = uuid4(), uuid4()
    t_unseen = uuid4()

    rows = [
        _create_mock_match_row(comp_id, uuid4(), t_known1, t_known2, 2, 1),
        _create_mock_match_row(comp_id, uuid4(), t_known2, t_known1, 1, 1),
    ] * 5

    model = AttackDefensePoissonModel()
    model.fit(rows)

    # Predict match with unseen team
    pred_row = _create_mock_match_row(comp_id, uuid4(), t_unseen, t_known1)
    pred = model.predict_raw(pred_row)

    assert pred.raw_outputs["evidence_quality"]["quality_level"] == "COLD_START"
    assert pred.raw_outputs["evidence_quality"]["home_cold_start"] is True
    assert pred.raw_outputs["evidence_quality"]["away_cold_start"] is False
    assert pred.raw_outputs["team_strengths"]["home_attack"] == 0.0


# -----------------------------------------------------------------------------
# Test 07: Sparse History Team Policy
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_07_sparse_history_team_policy():
    comp_id = uuid4()
    t_sparse = uuid4()
    t_regular = uuid4()

    # t_sparse has only 1 match (< min_matches_history = 5)
    rows = [
        _create_mock_match_row(comp_id, uuid4(), t_sparse, t_regular, 1, 0),
    ] + [
        _create_mock_match_row(comp_id, uuid4(), t_regular, uuid4(), 2, 1) for _ in range(10)
    ]

    model = AttackDefensePoissonModel(min_matches_history=5)
    model.fit(rows)

    pred_row = _create_mock_match_row(comp_id, uuid4(), t_sparse, t_regular)
    pred = model.predict_raw(pred_row)

    assert pred.raw_outputs["evidence_quality"]["quality_level"] == "LIMITED_HISTORY"
    assert pred.raw_outputs["evidence_quality"]["home_history_count"] == 1


# -----------------------------------------------------------------------------
# Test 08: Team Identity Perturbation Sensitivity
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_08_team_identity_perturbation_sensitivity():
    comp_id = uuid4()
    t_elite_att = uuid4()
    t_poor_att = uuid4()
    t_opponent = uuid4()

    rows = (
        [_create_mock_match_row(comp_id, uuid4(), t_elite_att, uuid4(), 4, 1) for _ in range(10)]
        + [_create_mock_match_row(comp_id, uuid4(), t_poor_att, uuid4(), 0, 2) for _ in range(10)]
        + [_create_mock_match_row(comp_id, uuid4(), t_opponent, uuid4(), 1, 1) for _ in range(10)]
    )

    model = AttackDefensePoissonModel()
    model.fit(rows)

    pred_elite = model.predict_raw(_create_mock_match_row(comp_id, uuid4(), t_elite_att, t_opponent))
    pred_poor = model.predict_raw(_create_mock_match_row(comp_id, uuid4(), t_poor_att, t_opponent))

    assert pred_elite.predicted_home_goals > pred_poor.predicted_home_goals + 0.3
    assert pred_elite.prob_home_win > pred_poor.prob_home_win + 0.1


# -----------------------------------------------------------------------------
# Test 09: Home / Away Swap Sensitivity
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_09_home_away_swap_sensitivity():
    comp_id = uuid4()
    t_a, t_b = uuid4(), uuid4()

    # Symmetric teams
    rows = [
        _create_mock_match_row(comp_id, uuid4(), t_a, t_b, 2, 1),
        _create_mock_match_row(comp_id, uuid4(), t_b, t_a, 2, 1),
    ] * 6

    model = AttackDefensePoissonModel()
    model.fit(rows)

    pred_ab = model.predict_raw(_create_mock_match_row(comp_id, uuid4(), t_a, t_b))
    pred_ba = model.predict_raw(_create_mock_match_row(comp_id, uuid4(), t_b, t_a))

    # Home team should have higher lambda in both fixtures due to home advantage
    assert pred_ab.predicted_home_goals > pred_ab.predicted_away_goals
    assert pred_ba.predicted_home_goals > pred_ba.predicted_away_goals
    assert pred_ab.prob_home_win == pytest.approx(pred_ba.prob_home_win, abs=1e-3)


# -----------------------------------------------------------------------------
# Test 10: No Fixed Lambda Constants
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_10_no_fixed_lambda_constants():
    comp_id = uuid4()
    teams = [uuid4() for _ in range(4)]
    rows = []
    for i in range(len(teams)):
        for j in range(len(teams)):
            if i != j:
                rows.append(_create_mock_match_row(comp_id, uuid4(), teams[i], teams[j], (i + 1), (j % 2)))

    model = AttackDefensePoissonModel()
    model.fit(rows)

    pred1 = model.predict_raw(_create_mock_match_row(comp_id, uuid4(), teams[0], teams[1]))
    pred2 = model.predict_raw(_create_mock_match_row(comp_id, uuid4(), teams[2], teams[3]))

    # Must NOT equal Sprint 4.2 constant demonstration lambdas (1.15, 1.85)
    assert pred1.predicted_home_goals != 1.15
    assert pred1.predicted_away_goals != 1.85
    assert (pred1.predicted_home_goals, pred1.predicted_away_goals) != (
        pred2.predicted_home_goals,
        pred2.predicted_away_goals,
    )


# -----------------------------------------------------------------------------
# Test 11: Artifact Save / Load Roundtrip Equivalence
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_11_artifact_save_load_roundtrip_equivalence():
    comp_id = uuid4()
    t1, t2 = uuid4(), uuid4()
    rows = [_create_mock_match_row(comp_id, uuid4(), t1, t2, 2, 1)] * 5

    m1 = AttackDefensePoissonModel()
    m1.fit(rows)

    test_row = _create_mock_match_row(comp_id, uuid4(), t1, t2)
    p1 = m1.predict_raw(test_row)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "ad_model.json")
        m1.save_artifact(path)

        m2 = AttackDefensePoissonModel()
        m2.load_artifact(path)
        p2 = m2.predict_raw(test_row)

        assert p1.predicted_home_goals == p2.predicted_home_goals
        assert p1.predicted_away_goals == p2.predicted_away_goals
        assert p1.prob_home_win == p2.prob_home_win
        assert p1.model_artifact_fingerprint == p2.model_artifact_fingerprint


# -----------------------------------------------------------------------------
# Test 12: Artifact Tamper Detection
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_12_artifact_tamper_detection():
    comp_id = uuid4()
    t1, t2 = uuid4(), uuid4()
    rows = [_create_mock_match_row(comp_id, uuid4(), t1, t2, 2, 1)] * 5

    m = AttackDefensePoissonModel()
    m.fit(rows)

    # Tamper with weights
    m.artifact.weights_payload["default_goal_baseline_mu"] = 99.99
    assert m.artifact.verify_integrity() is False


# -----------------------------------------------------------------------------
# Test 13: ProbabilityEngine Integration
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_13_probability_engine_integration():
    comp_id = uuid4()
    t1, t2 = uuid4(), uuid4()
    rows = [_create_mock_match_row(comp_id, uuid4(), t1, t2, 2, 1)] * 5

    model = AttackDefensePoissonModel()
    model.fit(rows)

    engine = ProbabilityEngine()
    test_row = _create_mock_match_row(comp_id, uuid4(), t1, t2)
    pred = engine.predict(model, test_row)

    assert pred.lambda_home is not None and pred.lambda_home > 0
    assert pred.lambda_away is not None and pred.lambda_away > 0
    assert pred.one_x_two.home_win + pred.one_x_two.draw + pred.one_x_two.away_win == pytest.approx(1.0, abs=1e-5)
    assert pred.btts is not None
    assert pred.over_under_2_5 is not None
    assert pred.most_likely_score is not None


# -----------------------------------------------------------------------------
# Test 14: Legacy Feature Strength Fallback
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_14_legacy_feature_strength_fallback():
    row = ModelingRowDTO(
        match_id=uuid4(),
        competition_id=uuid4(),
        season_id=uuid4(),
        kickoff_utc=datetime.now(UTC),
        ordered_feature_names=[
            "league_home_goals_per_match_v1",
            "league_away_goals_per_match_v1",
            "home_attack_strength_v1",
            "home_defense_strength_v1",
            "away_attack_strength_v1",
            "away_defense_strength_v1",
        ],
        feature_values=[1.5, 1.2, 1.2, 0.8, 0.9, 1.1],
        targets={},
    )

    model = AttackDefensePoissonModel()
    model.fit([row])
    pred = model.predict_raw(row)

    # 1.5 * 1.2 * 1.1 = 1.98
    # 1.2 * 0.9 * 0.8 = 0.864
    assert pred.predicted_home_goals == pytest.approx(1.98, abs=1e-4)
    assert pred.predicted_away_goals == pytest.approx(0.864, abs=1e-4)


# -----------------------------------------------------------------------------
# Test 15: Extreme Lambda Safety Bounds
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_15_extreme_lambda_safety_bounds():
    comp_id = uuid4()
    t1, t2 = uuid4(), uuid4()

    # Extreme scoring
    rows = [_create_mock_match_row(comp_id, uuid4(), t1, t2, 10, 0)] * 5
    model = AttackDefensePoissonModel()
    model.fit(rows)

    pred = model.predict_raw(_create_mock_match_row(comp_id, uuid4(), t1, t2))
    assert 0.01 <= pred.predicted_home_goals <= 15.0
    assert 0.01 <= pred.predicted_away_goals <= 15.0


# -----------------------------------------------------------------------------
# Test 16: Analytical Gradient Finite Differences Verification
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_16_analytical_gradient_finite_differences():
    from scipy.optimize import approx_fprime

    num_teams = 3
    gamma = 0.2
    home_indices = np.array([0, 1, 2, 0, 1], dtype=np.int32)
    away_indices = np.array([1, 2, 0, 2, 0], dtype=np.int32)
    home_goals = np.array([2.0, 1.0, 0.0, 3.0, 1.0], dtype=np.float64)
    away_goals = np.array([1.0, 1.0, 2.0, 0.0, 2.0], dtype=np.float64)

    n_params = 2 + 2 * num_teams
    theta_test = np.array([0.1, 0.2, 0.3, -0.1, -0.2, -0.1, 0.2, -0.1], dtype=np.float64)

    def obj_only(theta):
        mu = theta[0]
        h = theta[1]
        alpha = theta[2 : 2 + num_teams]
        delta = theta[2 + num_teams : 2 + 2 * num_teams]
        log_lh = np.clip(mu + h + alpha[home_indices] - delta[away_indices], -10.0, 10.0)
        log_la = np.clip(mu + alpha[away_indices] - delta[home_indices], -10.0, 10.0)
        lh = np.exp(log_lh)
        la = np.exp(log_la)
        nll = float(np.sum(lh - home_goals * log_lh + la - away_goals * log_la))
        reg = float(0.5 * gamma * (np.sum(alpha**2) + np.sum(delta**2)))
        return nll + reg

    def grad_only(theta):
        mu = theta[0]
        h = theta[1]
        alpha = theta[2 : 2 + num_teams]
        delta = theta[2 + num_teams : 2 + 2 * num_teams]
        log_lh = np.clip(mu + h + alpha[home_indices] - delta[away_indices], -10.0, 10.0)
        log_la = np.clip(mu + alpha[away_indices] - delta[home_indices], -10.0, 10.0)
        lh = np.exp(log_lh)
        la = np.exp(log_la)
        r_h = lh - home_goals
        r_a = la - away_goals
        grad = np.zeros_like(theta)
        grad[0] = np.sum(r_h + r_a)
        grad[1] = np.sum(r_h)
        np.add.at(grad[2 : 2 + num_teams], home_indices, r_h)
        np.add.at(grad[2 : 2 + num_teams], away_indices, r_a)
        grad[2 : 2 + num_teams] += gamma * alpha
        np.add.at(grad[2 + num_teams : 2 + 2 * num_teams], away_indices, -r_h)
        np.add.at(grad[2 + num_teams : 2 + 2 * num_teams], home_indices, -r_a)
        grad[2 + num_teams : 2 + 2 * num_teams] += gamma * delta
        return grad

    analytic_grad = grad_only(theta_test)
    num_grad = approx_fprime(theta_test, obj_only, 1e-7)

    np.testing.assert_allclose(analytic_grad, num_grad, rtol=1e-4, atol=1e-4)


# -----------------------------------------------------------------------------
# Test 17: Anti-Leakage Target Result Mutation Invariance
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_17_anti_leakage_target_score_mutation_invariance():
    comp_id = uuid4()
    t1, t2 = uuid4(), uuid4()
    train_rows = [_create_mock_match_row(comp_id, uuid4(), t1, t2, 2, 1)] * 5

    model = AttackDefensePoissonModel()
    model.fit(train_rows)

    test_row1 = _create_mock_match_row(comp_id, uuid4(), t1, t2, home_goals=0, away_goals=0)
    test_row2 = _create_mock_match_row(comp_id, uuid4(), t1, t2, home_goals=5, away_goals=4)

    pred1 = model.predict_raw(test_row1)
    pred2 = model.predict_raw(test_row2)

    assert pred1.predicted_home_goals == pred2.predicted_home_goals
    assert pred1.predicted_away_goals == pred2.predicted_away_goals
    assert pred1.prob_home_win == pred2.prob_home_win
    assert pred1.prob_draw == pred2.prob_draw
    assert pred1.prob_away_win == pred2.prob_away_win


# -----------------------------------------------------------------------------
# Test 18: Team Variance and Unique Predictions
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_18_team_variance_and_unique_predictions():
    comp_id = uuid4()
    teams = [uuid4() for _ in range(5)]
    rows = []
    np.random.seed(99)
    for i in range(len(teams)):
        for j in range(len(teams)):
            if i != j:
                hg = int(np.random.poisson(max(0.1, 1.0 + 0.3 * i - 0.2 * j)))
                ag = int(np.random.poisson(max(0.1, 0.8 + 0.2 * j - 0.3 * i)))
                rows.append(_create_mock_match_row(comp_id, uuid4(), teams[i], teams[j], hg, ag))

    model = AttackDefensePoissonModel()
    model.fit(rows)

    predictions = []
    lambda_homes = []
    lambda_aways = []
    for i in range(len(teams)):
        for j in range(len(teams)):
            if i != j:
                p = model.predict_raw(_create_mock_match_row(comp_id, uuid4(), teams[i], teams[j]))
                predictions.append((p.prob_home_win, p.prob_draw, p.prob_away_win))
                lambda_homes.append(p.predicted_home_goals)
                lambda_aways.append(p.predicted_away_goals)

    # Variance must be strictly positive
    var_lh = float(np.var(lambda_homes))
    var_la = float(np.var(lambda_aways))
    assert var_lh > 0.01, f"Expected positive home lambda variance, got {var_lh}"
    assert var_la > 0.01, f"Expected positive away lambda variance, got {var_la}"

    unique_probs = set(predictions)
    assert len(unique_probs) > 10, f"Expected distinct predictions across matchups, got {len(unique_probs)}"


# -----------------------------------------------------------------------------
# Test 19: Reproducibility and Fingerprint Determinism
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_19_reproducibility_fingerprint_determinism():
    comp_id = uuid4()
    t1, t2 = uuid4(), uuid4()
    rows = [_create_mock_match_row(comp_id, uuid4(), t1, t2, 2, 1)] * 5

    m1 = AttackDefensePoissonModel(regularization_gamma=0.2)
    art1 = m1.fit(rows)

    m2 = AttackDefensePoissonModel(regularization_gamma=0.2)
    art2 = m2.fit(rows)

    assert art1.artifact_fingerprint == art2.artifact_fingerprint
    assert art1.compute_fingerprint() == art2.compute_fingerprint()


# -----------------------------------------------------------------------------
# Test 20: Real Dataset Training & Four League Predictions Smoke
# -----------------------------------------------------------------------------
@pytest.mark.unit
def test_20_real_dataset_training_and_four_league_predictions_smoke():
    from app.db.session import SessionLocal
    from app.models.builder import ModelingDatasetBuilder

    db = SessionLocal()
    try:
        builder = ModelingDatasetBuilder(dataset_key="mvp_a_historical", version="v1")
        manifest, rows = builder.build_modeling_dataset(db, limit=200)

        if not rows:
            pytest.skip("No database rows available for smoke test.")

        model = AttackDefensePoissonModel()
        art = model.fit(rows)

        assert art.artifact_fingerprint != ""
        assert len(art.weights_payload["competitions"]) > 0

        # Predict first 4 rows
        for r in rows[:4]:
            pred = model.predict_raw(r)
            assert pred.predicted_home_goals > 0
            assert pred.predicted_away_goals > 0
            assert abs((pred.prob_home_win + pred.prob_draw + pred.prob_away_win) - 1.0) < 1e-4
    finally:
        db.close()

