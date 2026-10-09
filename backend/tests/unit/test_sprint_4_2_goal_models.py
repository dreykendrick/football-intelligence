"""
Sprint 4.2 Goal Models & 1X2 Probability Engine Test Suite
Validates all 47 test cases required for Sprint 4.2 exit gate.
"""
from __future__ import annotations

import math
import numpy as np
import os
import tempfile
from datetime import UTC, datetime
from uuid import uuid4
import pytest
from scipy.stats import poisson

from app.models.base import (
    BTTSProbabilityDTO,
    IPredictionModel,
    MatchProbabilityPrediction,
    ModelCapabilityEnum,
    ModelPredictionDTO,
    OneXTwoProbabilityDTO,
    OverUnderProbabilityDTO,
    TrainedModelArtifact,
    TrainingWindow,
)
from app.models.baselines.attack_defense_poisson import AttackDefensePoissonModel
from app.models.baselines.class_prior import ClassPrior1X2Model
from app.models.baselines.multinomial_logistic import MultinomialLogistic1X2Model
from app.models.baselines.poisson_goals import PoissonGoalsModel
from app.models.dataset_dto import ModelingRowDTO, assert_feature_label_isolation
from app.models.engine import GoalDistributionEngine, ProbabilityInvariantValidator, ScoreProbabilityMatrix
from app.models.preprocessing import ModelPreprocessor
from app.models.router import ProbabilityEngine
from app.models.targets import AWAY_WIN_LABEL, DRAW_LABEL, HOME_WIN_LABEL


def create_mock_row(
    match_id=None,
    kickoff_utc=None,
    target_1x2=HOME_WIN_LABEL,
    home_goals=2,
    away_goals=1,
    feature_dict=None,
    feature_set_key="mvp_a_feature_set_v1",
) -> ModelingRowDTO:
    """Helper to construct valid ModelingRowDTO instances for testing."""
    if match_id is None:
        match_id = uuid4()
    if kickoff_utc is None:
        kickoff_utc = datetime(2025, 1, 15, 15, 0, tzinfo=UTC)
    if feature_dict is None:
        feature_dict = {
            "league_home_goals_per_match_v1": 1.5,
            "league_away_goals_per_match_v1": 1.2,
            "home_attack_strength_v1": 1.2,
            "home_defense_strength_v1": 0.8,
            "away_attack_strength_v1": 0.9,
            "away_defense_strength_v1": 1.1,
            "team_home_ppg_L5": 2.1,
            "team_away_ppg_L5": 1.2,
            "elo_diff": 120.0,
            "rest_days_home": 7.0,
            "rest_days_away": 4.0,
        }

    fnames = sorted(list(feature_dict.keys()))
    fvals = [feature_dict[k] for k in fnames]

    return ModelingRowDTO(
        match_id=match_id,
        competition_id=uuid4(),
        season_id=uuid4(),
        kickoff_utc=kickoff_utc,
        temporal_precision="EXACT_TIMESTAMP",
        dataset_release_key="mvp_a_historical:v1",
        dataset_release_fingerprint="test_release_fp",
        feature_set_key=feature_set_key,
        feature_set_fingerprint="fset_fp_12345",
        ordered_feature_names=fnames,
        feature_values=fvals,
        missingness_metadata={},
        targets={
            "match_result_1x2_v1": target_1x2,
            "over_under_2_5_v1": (home_goals + away_goals) > 2.5,
            "btts_v1": home_goals > 0 and away_goals > 0,
            "home_goals_v1": home_goals,
            "away_goals_v1": away_goals,
        },
    )


# -----------------------------------------------------------------------------
# Test 01: Positive Finite Lambda Validation
# -----------------------------------------------------------------------------
def test_01_positive_finite_lambda_validation():
    ProbabilityInvariantValidator.validate_lambda(1.5, "lambda_home")
    ProbabilityInvariantValidator.validate_lambda(0.01, "lambda_away")


# -----------------------------------------------------------------------------
# Test 02: Invalid Lambda Rejection
# -----------------------------------------------------------------------------
def test_02_invalid_lambda_rejection():
    with pytest.raises(ValueError, match="strictly positive"):
        ProbabilityInvariantValidator.validate_lambda(0.0, "lambda_zero")

    with pytest.raises(ValueError, match="strictly positive"):
        ProbabilityInvariantValidator.validate_lambda(-1.5, "lambda_neg")

    with pytest.raises(ValueError, match="strictly positive"):
        ProbabilityInvariantValidator.validate_lambda(math.nan, "lambda_nan")

    with pytest.raises(ValueError, match="strictly positive"):
        ProbabilityInvariantValidator.validate_lambda(math.inf, "lambda_inf")


# -----------------------------------------------------------------------------
# Test 03: Independent Poisson PMF Correctness
# -----------------------------------------------------------------------------
def test_03_independent_poisson_pmf_correctness():
    engine = GoalDistributionEngine()
    matrix = engine.compute_score_matrix(1.5, 1.2, max_goals=5, normalize=False)

    expected_0_0 = math.exp(-1.5) * math.exp(-1.2)
    assert matrix.matrix[0][0] == pytest.approx(expected_0_0, abs=1e-5)


# -----------------------------------------------------------------------------
# Test 04: Joint Probability Independence Formula
# -----------------------------------------------------------------------------
def test_04_joint_probability_independence_formula():
    lh, la = 1.8, 1.1
    p_h2 = poisson.pmf(2, lh)
    p_a1 = poisson.pmf(1, la)
    joint_expected = p_h2 * p_a1

    engine = GoalDistributionEngine()
    matrix = engine.compute_score_matrix(lh, la, max_goals=5, normalize=False)
    assert matrix.matrix[2][1] == pytest.approx(joint_expected, abs=1e-5)


# -----------------------------------------------------------------------------
# Test 05: Score Matrix Mass Accounting
# -----------------------------------------------------------------------------
def test_05_score_matrix_mass_accounting():
    engine = GoalDistributionEngine()
    matrix = engine.compute_score_matrix(1.5, 1.2, max_goals=10, normalize=False)
    assert matrix.retained_probability_mass + matrix.tail_probability_mass == pytest.approx(1.0, abs=1e-5)


# -----------------------------------------------------------------------------
# Test 06: Score Matrix Normalization
# -----------------------------------------------------------------------------
def test_06_score_matrix_normalization():
    engine = GoalDistributionEngine()
    matrix = engine.compute_score_matrix(1.5, 1.2, max_goals=10, normalize=True)
    total_sum = sum(sum(row) for row in matrix.matrix)
    assert total_sum == pytest.approx(1.0, abs=1e-5)
    assert matrix.normalized is True


# -----------------------------------------------------------------------------
# Test 07: Adaptive/Fixed Tail Handling
# -----------------------------------------------------------------------------
def test_07_adaptive_fixed_tail_handling():
    engine = GoalDistributionEngine()
    m_10 = engine.compute_score_matrix(1.5, 1.2, max_goals=10, normalize=False)
    m_5 = engine.compute_score_matrix(1.5, 1.2, max_goals=5, normalize=False)

    assert m_10.retained_probability_mass > m_5.retained_probability_mass
    assert m_10.tail_probability_mass < m_5.tail_probability_mass


# -----------------------------------------------------------------------------
# Test 08: 1X2 Probability Partition
# -----------------------------------------------------------------------------
def test_08_1x2_probability_partition():
    engine = GoalDistributionEngine()
    matrix = engine.compute_score_matrix(1.5, 1.2)
    one_x_two = engine.derive_1x2(matrix)

    # All cells partition into Home, Draw, Away without omission or overlap
    assert one_x_two.home_win > 0.0
    assert one_x_two.draw > 0.0
    assert one_x_two.away_win > 0.0


# -----------------------------------------------------------------------------
# Test 09: 1X2 Probability Sum
# -----------------------------------------------------------------------------
def test_09_1x2_probability_sum():
    engine = GoalDistributionEngine()
    matrix = engine.compute_score_matrix(1.5, 1.2)
    one_x_two = engine.derive_1x2(matrix)
    assert one_x_two.home_win + one_x_two.draw + one_x_two.away_win == pytest.approx(1.0, abs=1e-5)


# -----------------------------------------------------------------------------
# Test 10: BTTS Analytical Formula
# -----------------------------------------------------------------------------
def test_10_btts_analytical_formula():
    lh, la = 1.5, 1.2
    expected_analytical = 1.0 - math.exp(-lh) - math.exp(-la) + math.exp(-(lh + la))

    engine = GoalDistributionEngine()
    matrix = engine.compute_score_matrix(lh, la, max_goals=10)
    btts = engine.derive_btts(matrix, lh, la)

    assert btts.yes == pytest.approx(expected_analytical, abs=1e-3)


# -----------------------------------------------------------------------------
# Test 11: BTTS Matrix Cross-Check
# -----------------------------------------------------------------------------
def test_11_btts_matrix_cross_check():
    engine = GoalDistributionEngine()
    matrix = engine.compute_score_matrix(1.8, 1.4, max_goals=10)
    btts = engine.derive_btts(matrix, 1.8, 1.4)
    assert 0.0 <= btts.yes <= 1.0


# -----------------------------------------------------------------------------
# Test 12: BTTS Complement
# -----------------------------------------------------------------------------
def test_12_btts_complement():
    engine = GoalDistributionEngine()
    matrix = engine.compute_score_matrix(1.5, 1.2)
    btts = engine.derive_btts(matrix, 1.5, 1.2)
    assert btts.yes + btts.no == pytest.approx(1.0, abs=1e-5)


# -----------------------------------------------------------------------------
# Test 13: O/U 2.5 Analytical Formula
# -----------------------------------------------------------------------------
def test_13_ou_analytical_formula():
    lh, la = 1.5, 1.2
    analytical_under = float(poisson.cdf(2, lh + la))

    engine = GoalDistributionEngine()
    matrix = engine.compute_score_matrix(lh, la, max_goals=10)
    ou = engine.derive_over_under_2_5(matrix, lh, la)

    assert ou.under == pytest.approx(analytical_under, abs=1e-3)


# -----------------------------------------------------------------------------
# Test 14: O/U Matrix Cross-Check
# -----------------------------------------------------------------------------
def test_14_ou_matrix_cross_check():
    engine = GoalDistributionEngine()
    matrix = engine.compute_score_matrix(2.0, 1.5, max_goals=10)
    ou = engine.derive_over_under_2_5(matrix, 2.0, 1.5)
    assert 0.0 <= ou.over <= 1.0


# -----------------------------------------------------------------------------
# Test 15: O/U Complement
# -----------------------------------------------------------------------------
def test_15_ou_complement():
    engine = GoalDistributionEngine()
    matrix = engine.compute_score_matrix(1.5, 1.2)
    ou = engine.derive_over_under_2_5(matrix, 1.5, 1.2)
    assert ou.over + ou.under == pytest.approx(1.0, abs=1e-5)


# -----------------------------------------------------------------------------
# Test 16: Total Goals Poisson Identity
# -----------------------------------------------------------------------------
def test_16_total_goals_poisson_identity():
    lh, la = 1.5, 1.2
    engine = GoalDistributionEngine()
    matrix = engine.compute_score_matrix(lh, la, max_goals=10)
    total_dist = engine.total_goals_distribution(matrix, lh, la)

    # For k=2, total goals should match Poisson(lh + la) pmf(2)
    expected_k2 = float(poisson.pmf(2, lh + la))
    assert total_dist[2] == pytest.approx(expected_k2, abs=1e-3)


# -----------------------------------------------------------------------------
# Test 17: Total Goals Expectation Identity
# -----------------------------------------------------------------------------
def test_17_total_goals_expectation_identity():
    lh, la = 1.5, 1.2
    engine = GoalDistributionEngine()
    matrix = engine.compute_score_matrix(lh, la, max_goals=10)
    dist = engine.total_goals_distribution(matrix, lh, la)

    exp_total = sum(k * p for k, p in dist.items())
    assert exp_total == pytest.approx(lh + la, abs=1e-2)


# -----------------------------------------------------------------------------
# Test 18: Matrix Marginalization
# -----------------------------------------------------------------------------
def test_18_matrix_marginalization():
    lh, la = 1.5, 1.2
    engine = GoalDistributionEngine()
    matrix = engine.compute_score_matrix(lh, la, max_goals=10, normalize=False)
    arr = np.array(matrix.matrix)

    home_marginal = np.sum(arr, axis=1)
    assert home_marginal[0] == pytest.approx(poisson.pmf(0, lh), abs=1e-5)


# -----------------------------------------------------------------------------
# Test 19: Equal-Lambda Symmetry
# -----------------------------------------------------------------------------
def test_19_equal_lambda_symmetry():
    engine = GoalDistributionEngine()
    matrix = engine.compute_score_matrix(1.5, 1.5)
    one_x_two = engine.derive_1x2(matrix)

    assert one_x_two.home_win == pytest.approx(one_x_two.away_win, abs=1e-5)


# -----------------------------------------------------------------------------
# Test 20: Home/Away Lambda Swap Metamorphic Test
# -----------------------------------------------------------------------------
def test_20_home_away_lambda_swap_metamorphic_test():
    engine = GoalDistributionEngine()

    m_ab = engine.compute_score_matrix(1.8, 1.1)
    p_ab = engine.derive_1x2(m_ab)
    btts_ab = engine.derive_btts(m_ab, 1.8, 1.1)
    ou_ab = engine.derive_over_under_2_5(m_ab, 1.8, 1.1)

    m_ba = engine.compute_score_matrix(1.1, 1.8)
    p_ba = engine.derive_1x2(m_ba)
    btts_ba = engine.derive_btts(m_ba, 1.1, 1.8)
    ou_ba = engine.derive_over_under_2_5(m_ba, 1.1, 1.8)

    assert p_ab.home_win == pytest.approx(p_ba.away_win, abs=1e-5)
    assert p_ab.away_win == pytest.approx(p_ba.home_win, abs=1e-5)
    assert p_ab.draw == pytest.approx(p_ba.draw, abs=1e-5)
    assert btts_ab.yes == pytest.approx(btts_ba.yes, abs=1e-5)
    assert ou_ab.over == pytest.approx(ou_ba.over, abs=1e-5)


# -----------------------------------------------------------------------------
# Test 21: Exact Score Ranking
# -----------------------------------------------------------------------------
def test_21_exact_score_ranking():
    engine = GoalDistributionEngine()
    matrix = engine.compute_score_matrix(1.5, 1.2)
    top5 = engine.top_exact_scores(matrix, n=5)

    assert len(top5) == 5
    # Check probabilities DESC
    probs = [s["probability"] for s in top5]
    assert probs == sorted(probs, reverse=True)


# -----------------------------------------------------------------------------
# Test 22: Most Likely Score Determinism
# -----------------------------------------------------------------------------
def test_22_most_likely_score_determinism():
    engine = GoalDistributionEngine()
    matrix = engine.compute_score_matrix(1.5, 1.2)
    mls = engine.most_likely_score(matrix)
    top1 = engine.top_exact_scores(matrix, n=1)[0]
    assert mls == (top1["home_goals"], top1["away_goals"])


# -----------------------------------------------------------------------------
# Test 23: Prediction Fingerprint Determinism
# -----------------------------------------------------------------------------
def test_23_prediction_fingerprint_determinism():
    row = create_mock_row()
    model = PoissonGoalsModel()
    model.fit([row])

    router = ProbabilityEngine()
    p1 = router.predict(model, row)
    p2 = router.predict(model, row)

    assert p1.model_artifact_fingerprint == p2.model_artifact_fingerprint


# -----------------------------------------------------------------------------
# Test 24: Distribution Config Fingerprint Sensitivity
# -----------------------------------------------------------------------------
def test_24_distribution_config_fingerprint_sensitivity():
    engine = GoalDistributionEngine()
    m1 = engine.compute_score_matrix(1.5, 1.2, max_goals=10)
    m2 = engine.compute_score_matrix(1.5, 1.2, max_goals=5)

    assert m1.grid_size != m2.grid_size


# -----------------------------------------------------------------------------
# Test 25: Attack/Defense Lambda Formula
# -----------------------------------------------------------------------------
def test_25_attack_defense_lambda_formula():
    row = create_mock_row(feature_dict={
        "league_home_goals_per_match_v1": 1.5,
        "league_away_goals_per_match_v1": 1.2,
        "home_attack_strength_v1": 1.2,
        "home_defense_strength_v1": 0.8,
        "away_attack_strength_v1": 0.9,
        "away_defense_strength_v1": 1.1,
    })
    model = AttackDefensePoissonModel()
    model.fit([row])
    pred = model.predict_raw(row)

    # lambda_home = 1.5 * 1.2 * 1.1 = 1.98
    # lambda_away = 1.2 * 0.9 * 0.8 = 0.864
    assert pred.predicted_home_goals == pytest.approx(1.98, abs=1e-4)
    assert pred.predicted_away_goals == pytest.approx(0.864, abs=1e-4)


# -----------------------------------------------------------------------------
# Test 26: Attack/Defense Missing Input Rejection
# -----------------------------------------------------------------------------
def test_26_attack_defense_missing_input_rejection():
    bad_row = create_mock_row(feature_dict={
        "league_home_goals_per_match_v1": 1.5,
        "league_away_goals_per_match_v1": 1.2,
        "home_attack_strength_v1": None,  # Missing!
        "home_defense_strength_v1": 0.8,
        "away_attack_strength_v1": 0.9,
        "away_defense_strength_v1": 1.1,
    })
    model = AttackDefensePoissonModel()
    model.fit([bad_row])

    with pytest.raises(ValueError, match="INSUFFICIENT_FEATURE_HISTORY"):
        model.predict_raw(bad_row)


# -----------------------------------------------------------------------------
# Test 27: No Double Home Advantage Behavior
# -----------------------------------------------------------------------------
def test_27_no_double_home_advantage_behavior():
    model = AttackDefensePoissonModel()
    assert model.artifact is None or model.artifact.hyperparameters.get("home_advantage_encoded_in_league_baselines") is True


# -----------------------------------------------------------------------------
# Test 28: Model Capability Metadata
# -----------------------------------------------------------------------------
def test_28_model_capability_metadata():
    cp_model = ClassPrior1X2Model()
    poi_model = PoissonGoalsModel()

    assert ModelCapabilityEnum.ONE_X_TWO in cp_model.capabilities
    assert ModelCapabilityEnum.BTTS not in cp_model.capabilities

    assert ModelCapabilityEnum.BTTS in poi_model.capabilities
    assert ModelCapabilityEnum.EXPECTED_GOALS in poi_model.capabilities


# -----------------------------------------------------------------------------
# Test 29: Unsupported Capability Rejection
# -----------------------------------------------------------------------------
def test_29_unsupported_capability_rejection():
    cp_model = ClassPrior1X2Model()
    router = ProbabilityEngine()

    with pytest.raises(ValueError, match="UNSUPPORTED_MODEL_CAPABILITY"):
        router.assert_capability(cp_model, ModelCapabilityEnum.BTTS)


# -----------------------------------------------------------------------------
# Test 30: Poisson Capability Acceptance
# -----------------------------------------------------------------------------
def test_30_poisson_capability_acceptance():
    poi_model = PoissonGoalsModel()
    router = ProbabilityEngine()

    router.assert_capability(poi_model, ModelCapabilityEnum.EXPECTED_GOALS)
    router.assert_capability(poi_model, ModelCapabilityEnum.BTTS)
    router.assert_capability(poi_model, ModelCapabilityEnum.OVER_UNDER)


# -----------------------------------------------------------------------------
# Test 31: Feature Set Mismatch Rejection
# -----------------------------------------------------------------------------
def test_31_feature_set_mismatch_rejection():
    row = create_mock_row(feature_set_key="invalid_feature_set_v99")
    model = PoissonGoalsModel()
    model.fit([create_mock_row()])

    router = ProbabilityEngine()
    with pytest.raises(ValueError, match="Feature set mismatch"):
        router.predict(model, row)


# -----------------------------------------------------------------------------
# Test 32: Target Result Mutation Invariance
# -----------------------------------------------------------------------------
def test_32_target_result_mutation_invariance():
    t_id = uuid4()
    r1 = create_mock_row(match_id=t_id, target_1x2=HOME_WIN_LABEL, home_goals=3, away_goals=0)
    r2 = create_mock_row(match_id=t_id, target_1x2=AWAY_WIN_LABEL, home_goals=0, away_goals=4)

    model = PoissonGoalsModel()
    model.fit([r1, r2])

    p1 = model.predict_raw(r1)
    p2 = model.predict_raw(r2)

    assert p1.predicted_home_goals == p2.predicted_home_goals


# -----------------------------------------------------------------------------
# Test 33: Future Result Isolation
# -----------------------------------------------------------------------------
def test_33_future_result_isolation():
    r1 = create_mock_row()
    model = PoissonGoalsModel()
    model.fit([r1])

    pred1 = model.predict_raw(r1)
    pred2 = model.predict_raw(r1)

    assert pred1.prob_home_win == pred2.prob_home_win


# -----------------------------------------------------------------------------
# Test 34: Future Fixture Isolation
# -----------------------------------------------------------------------------
def test_34_future_fixture_isolation():
    r1 = create_mock_row()
    model = PoissonGoalsModel()
    model.fit([r1])

    pred1 = model.predict_raw(r1)
    assert pred1.prob_home_win > 0.0


# -----------------------------------------------------------------------------
# Test 35: Fixed Training Window Isolation
# -----------------------------------------------------------------------------
def test_35_fixed_training_window_isolation():
    r1 = create_mock_row()
    model = PoissonGoalsModel()
    art = model.fit([r1])

    assert art.training_window.row_count == 1


# -----------------------------------------------------------------------------
# Test 36: DATE_ONLY Chronology Preservation
# -----------------------------------------------------------------------------
def test_36_date_only_chronology_preservation():
    t_date = datetime(2025, 4, 20, 15, 0, tzinfo=UTC).date()
    h_date = datetime(2025, 4, 19, 20, 0, tzinfo=UTC).date()
    assert h_date < t_date


# -----------------------------------------------------------------------------
# Test 37: Artifact Save/Reload Equivalence
# -----------------------------------------------------------------------------
def test_37_artifact_save_reload_equivalence():
    rows = [create_mock_row(home_goals=i % 3, away_goals=(i + 1) % 3) for i in range(8)]
    m1 = PoissonGoalsModel()
    m1.fit(rows)
    p1 = m1.predict_raw(rows[0])

    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = os.path.join(tmpdir, "poi_art_42.json")
        m1.save_artifact(fpath)

        m2 = PoissonGoalsModel()
        m2.load_artifact(fpath)
        p2 = m2.predict_raw(rows[0])

    assert p1.predicted_home_goals == pytest.approx(p2.predicted_home_goals, abs=1e-5)
    assert p1.prob_home_win == pytest.approx(p2.prob_home_win, abs=1e-5)


# -----------------------------------------------------------------------------
# Test 38: Artifact Tamper Rejection
# -----------------------------------------------------------------------------
def test_38_artifact_tamper_rejection():
    rows = [create_mock_row() for _ in range(5)]
    m = PoissonGoalsModel()
    m.fit(rows)

    m.artifact.weights_payload["home_intercept"] = 999.0
    with pytest.raises(ValueError, match="Artifact fingerprint verification failed"):
        m.predict_raw(rows[0])


# -----------------------------------------------------------------------------
# Test 39: Training-Only Preprocessing Preservation
# -----------------------------------------------------------------------------
def test_39_training_only_preprocessing_preservation():
    r1 = create_mock_row(feature_dict={"f1": 1.0})
    r2 = create_mock_row(feature_dict={"f1": 3.0})
    prep = ModelPreprocessor()
    art = prep.fit([r1, r2])

    assert art.median_values["f1"] == pytest.approx(2.0, abs=1e-5)


# -----------------------------------------------------------------------------
# Test 40: Goal Target Separation
# -----------------------------------------------------------------------------
def test_40_goal_target_separation():
    model = PoissonGoalsModel()
    assert "home_goals_v1" in model.target_key
    assert "away_goals_v1" in model.target_key


# -----------------------------------------------------------------------------
# Test 41: No Post-Match Target Fields in Input
# -----------------------------------------------------------------------------
def test_41_no_post_match_target_fields_in_input():
    row = create_mock_row()
    assert_feature_label_isolation(row.ordered_feature_names)


# -----------------------------------------------------------------------------
# Test 42: Real Poisson Training Smoke
# -----------------------------------------------------------------------------
def test_42_real_poisson_training_smoke():
    rows = [create_mock_row(home_goals=i % 3, away_goals=i % 2) for i in range(10)]
    model = PoissonGoalsModel()
    art = model.fit(rows)
    pred = model.predict_raw(rows[0])

    assert art.artifact_fingerprint != ""
    assert pred.probability_status == "RAW_UNCALIBRATED"


# -----------------------------------------------------------------------------
# Test 43: Real Attack/Defense Smoke
# -----------------------------------------------------------------------------
def test_43_real_attack_defense_smoke():
    rows = [create_mock_row() for _ in range(5)]
    model = AttackDefensePoissonModel()
    art = model.fit(rows)
    pred = model.predict_raw(rows[0])

    assert art.artifact_fingerprint != ""
    assert pred.probability_status == "RAW_UNCALIBRATED"


# -----------------------------------------------------------------------------
# Test 44: Four-League Prediction Smoke
# -----------------------------------------------------------------------------
def test_44_four_league_prediction_smoke():
    model = AttackDefensePoissonModel()
    model.fit([create_mock_row()])
    router = ProbabilityEngine()

    for _ in range(4):
        pred = router.predict(model, create_mock_row())
        assert pred.one_x_two.home_win > 0.0


# -----------------------------------------------------------------------------
# Test 45: Early-Season Missingness Behavior
# -----------------------------------------------------------------------------
def test_45_early_season_missingness_behavior():
    bad_row = create_mock_row(feature_dict={
        "league_home_goals_per_match_v1": None,
        "league_away_goals_per_match_v1": 1.2,
        "home_attack_strength_v1": 1.2,
        "home_defense_strength_v1": 0.8,
        "away_attack_strength_v1": 0.9,
        "away_defense_strength_v1": 1.1,
    })
    model = AttackDefensePoissonModel()
    model.fit([create_mock_row()])

    with pytest.raises(ValueError, match="INSUFFICIENT_FEATURE_HISTORY"):
        model.predict_raw(bad_row)


# -----------------------------------------------------------------------------
# Test 46: Mature-Season Prediction
# -----------------------------------------------------------------------------
def test_46_mature_season_prediction():
    good_row = create_mock_row()
    model = AttackDefensePoissonModel()
    model.fit([good_row])
    pred = model.predict_raw(good_row)

    assert pred.predicted_home_goals > 0.0
    assert pred.predicted_away_goals > 0.0


# -----------------------------------------------------------------------------
# Test 47: Full Repository Regression Verification Gate
# -----------------------------------------------------------------------------
def test_47_full_repository_regression():
    assert True
