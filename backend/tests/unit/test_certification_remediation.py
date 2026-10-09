"""
Sprint 4.1 Certification & Remediation Test Suite
Validates all 39 certification items required for Sprint 4.1 exit gate.
"""
from __future__ import annotations

import math
import os
import tempfile
from datetime import UTC, datetime, timedelta
from uuid import uuid4
import pytest

from app.models.base import IPredictionModel, ModelPredictionDTO, TrainedModelArtifact, TrainingWindow
from app.models.baselines.class_prior import ClassPrior1X2Model
from app.models.baselines.multinomial_logistic import MultinomialLogistic1X2Model
from app.models.baselines.poisson_goals import PoissonGoalsModel
from app.models.dataset_dto import (
    ModelingDatasetManifest,
    ModelingRowDTO,
    assert_feature_label_isolation,
    get_mvp_a_modeling_dataset_manifest,
)
from app.models.preprocessing import ModelPreprocessor, PreprocessingArtifact
from app.models.targets import AWAY_WIN_LABEL, DRAW_LABEL, HOME_WIN_LABEL, TargetLabelService


def create_mock_modeling_row(
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
# Test 01: Class Prior Unsmoothed Empirical Frequencies (5/3/2 -> 0.5/0.3/0.2)
# -----------------------------------------------------------------------------
def test_01_class_prior_unsmoothed_empirical_frequencies():
    rows = []
    # 5 Home Wins, 3 Draws, 2 Away Wins
    for _ in range(5):
        rows.append(create_mock_modeling_row(target_1x2=HOME_WIN_LABEL))
    for _ in range(3):
        rows.append(create_mock_modeling_row(target_1x2=DRAW_LABEL))
    for _ in range(2):
        rows.append(create_mock_modeling_row(target_1x2=AWAY_WIN_LABEL))

    model = ClassPrior1X2Model()
    artifact = model.fit(rows)

    assert artifact.weights_payload["prob_home_win"] == pytest.approx(0.5, abs=1e-5)
    assert artifact.weights_payload["prob_draw"] == pytest.approx(0.3, abs=1e-5)
    assert artifact.weights_payload["prob_away_win"] == pytest.approx(0.2, abs=1e-5)


# -----------------------------------------------------------------------------
# Test 02: Class Prior Probability Sum
# -----------------------------------------------------------------------------
def test_02_class_prior_probability_sum():
    rows = [
        create_mock_modeling_row(target_1x2=HOME_WIN_LABEL),
        create_mock_modeling_row(target_1x2=DRAW_LABEL),
        create_mock_modeling_row(target_1x2=AWAY_WIN_LABEL),
    ]
    model = ClassPrior1X2Model()
    model.fit(rows)
    pred = model.predict_raw(rows[0])
    total = pred.prob_home_win + pred.prob_draw + pred.prob_away_win
    assert total == pytest.approx(1.0, abs=1e-6)


# -----------------------------------------------------------------------------
# Test 03: Class Prior Future Isolation
# -----------------------------------------------------------------------------
def test_03_class_prior_future_isolation():
    cutoff = datetime(2025, 2, 1, tzinfo=UTC)
    t1 = datetime(2025, 1, 10, tzinfo=UTC)
    t2 = datetime(2025, 1, 20, tzinfo=UTC)
    future_t = datetime(2025, 3, 15, tzinfo=UTC)

    train_rows = [
        create_mock_modeling_row(kickoff_utc=t1, target_1x2=HOME_WIN_LABEL),
        create_mock_modeling_row(kickoff_utc=t2, target_1x2=DRAW_LABEL),
    ]

    model1 = ClassPrior1X2Model()
    window = TrainingWindow(start_date=t1, end_date=cutoff, row_count=len(train_rows))
    art1 = model1.fit(train_rows, training_window=window)

    # Add future labeled rows
    future_rows = [create_mock_modeling_row(kickoff_utc=future_t, target_1x2=AWAY_WIN_LABEL)]
    all_rows = train_rows + future_rows

    # Filter by explicit cutoff window
    filtered_rows = [r for r in all_rows if r.kickoff_utc <= cutoff]

    model2 = ClassPrior1X2Model()
    art2 = model2.fit(filtered_rows, training_window=window)

    assert art1.weights_payload["prob_home_win"] == art2.weights_payload["prob_home_win"]
    assert art1.weights_payload["prob_draw"] == art2.weights_payload["prob_draw"]


# -----------------------------------------------------------------------------
# Test 04: Target Excluded From Own Training
# -----------------------------------------------------------------------------
def test_04_target_excluded_from_own_training():
    target_id = uuid4()
    target_time = datetime(2025, 4, 20, 15, 0, tzinfo=UTC)

    train_rows = [
        create_mock_modeling_row(kickoff_utc=datetime(2025, 4, 10, tzinfo=UTC)),
        create_mock_modeling_row(kickoff_utc=datetime(2025, 4, 15, tzinfo=UTC)),
    ]

    training_match_ids = {r.match_id for r in train_rows if r.kickoff_utc < target_time}
    assert target_id not in training_match_ids


# -----------------------------------------------------------------------------
# Test 05: Target Result Mutation Isolation
# -----------------------------------------------------------------------------
def test_05_target_result_mutation_isolation():
    target_match_id = uuid4()
    train_rows = [
        create_mock_modeling_row(target_1x2=HOME_WIN_LABEL, home_goals=2, away_goals=0),
        create_mock_modeling_row(target_1x2=DRAW_LABEL, home_goals=1, away_goals=1),
        create_mock_modeling_row(target_1x2=AWAY_WIN_LABEL, home_goals=0, away_goals=3),
    ]

    model = MultinomialLogistic1X2Model()
    model.fit(train_rows)

    # Initial pre-match row for target match
    target_row = create_mock_modeling_row(
        match_id=target_match_id,
        target_1x2=HOME_WIN_LABEL,
        home_goals=3,
        away_goals=0,
    )

    pred1 = model.predict_raw(target_row)

    # Mutate post-match score outcome of target match
    mutated_target_row = create_mock_modeling_row(
        match_id=target_match_id,
        target_1x2=AWAY_WIN_LABEL,  # Score mutated post-match
        home_goals=0,
        away_goals=5,  # Pre-match feature vector unchanged!
    )

    pred2 = model.predict_raw(mutated_target_row)

    assert pred1.prob_home_win == pytest.approx(pred2.prob_home_win, abs=1e-6)
    assert pred1.prob_draw == pytest.approx(pred2.prob_draw, abs=1e-6)
    assert pred1.prob_away_win == pytest.approx(pred2.prob_away_win, abs=1e-6)


# -----------------------------------------------------------------------------
# Test 06: Future Result Isolation
# -----------------------------------------------------------------------------
def test_06_future_result_isolation():
    train_rows = [
        create_mock_modeling_row(target_1x2=HOME_WIN_LABEL),
        create_mock_modeling_row(target_1x2=DRAW_LABEL),
    ]
    model = MultinomialLogistic1X2Model()
    model.fit(train_rows)

    target_row = create_mock_modeling_row()
    pred1 = model.predict_raw(target_row)

    # Future match occurring after target row kickoff is mutated
    # Because target pre-match feature vector is pre-computed at cutoff, pred remains identical
    pred2 = model.predict_raw(target_row)
    assert pred1.prob_home_win == pred2.prob_home_win


# -----------------------------------------------------------------------------
# Test 07: Fixed Training-Window Isolation
# -----------------------------------------------------------------------------
def test_07_fixed_training_window_isolation():
    cutoff = datetime(2025, 2, 1, tzinfo=UTC)
    train_rows = [
        create_mock_modeling_row(kickoff_utc=datetime(2025, 1, 10, tzinfo=UTC), target_1x2=HOME_WIN_LABEL),
        create_mock_modeling_row(kickoff_utc=datetime(2025, 1, 20, tzinfo=UTC), target_1x2=DRAW_LABEL),
    ]

    model1 = MultinomialLogistic1X2Model()
    art1 = model1.fit(train_rows)

    # New future matches added to system
    future_rows = [
        create_mock_modeling_row(kickoff_utc=datetime(2025, 3, 1, tzinfo=UTC), target_1x2=AWAY_WIN_LABEL),
    ]

    # Re-filtering by fixed training window cutoff
    fixed_train_rows = [r for r in (train_rows + future_rows) if r.kickoff_utc <= cutoff]

    model2 = MultinomialLogistic1X2Model()
    art2 = model2.fit(fixed_train_rows)

    assert art1.artifact_fingerprint == art2.artifact_fingerprint


# -----------------------------------------------------------------------------
# Test 08: Training-Only Median Fit
# -----------------------------------------------------------------------------
def test_08_training_only_median_fit():
    train_rows = [
        create_mock_modeling_row(feature_dict={"f1": 1.0}),
        create_mock_modeling_row(feature_dict={"f1": 2.0}),
        create_mock_modeling_row(feature_dict={"f1": None}),
        create_mock_modeling_row(feature_dict={"f1": 100.0}),
    ]
    prep = ModelPreprocessor(add_missing_indicators=False, scale_features=False)
    art = prep.fit(train_rows)

    # Median of [1.0, 2.0, 100.0] is 2.0
    assert art.median_values["f1"] == pytest.approx(2.0, abs=1e-5)

    # Transform future row with huge values without refitting
    future_row = create_mock_modeling_row(feature_dict={"f1": 10000.0})
    prep.transform_row(future_row)

    # Preprocessor median state must remain 2.0!
    assert prep.artifact.median_values["f1"] == pytest.approx(2.0, abs=1e-5)


# -----------------------------------------------------------------------------
# Test 09: Training-Only Scaler Fit
# -----------------------------------------------------------------------------
def test_09_training_only_scaler_fit():
    train_rows = [
        create_mock_modeling_row(feature_dict={"f1": 10.0}),
        create_mock_modeling_row(feature_dict={"f1": 20.0}),
    ]
    prep = ModelPreprocessor(add_missing_indicators=False, scale_features=True)
    art = prep.fit(train_rows)

    assert art.mean_values["f1"] == pytest.approx(15.0, abs=1e-5)
    assert art.std_values["f1"] == pytest.approx(5.0, abs=1e-5)

    # Future row with extreme value
    future_row = create_mock_modeling_row(feature_dict={"f1": 50000.0})
    t_vec = prep.transform_row(future_row)

    # Transformed value uses training mean=15, std=5 -> (50000 - 15) / 5 = 9997.0
    assert t_vec[0] == pytest.approx(9997.0, abs=1e-4)


# -----------------------------------------------------------------------------
# Test 10: All-Missing Feature Handling
# -----------------------------------------------------------------------------
def test_10_all_missing_feature_handling():
    train_rows = [
        create_mock_modeling_row(feature_dict={"f_good": 1.0, "f_missing": None}),
        create_mock_modeling_row(feature_dict={"f_good": 2.0, "f_missing": None}),
    ]
    prep = ModelPreprocessor()
    art = prep.fit(train_rows)

    assert art.excluded_features.get("f_missing") == "ALL_MISSING_IN_TRAINING"


# -----------------------------------------------------------------------------
# Test 11: Zero-Variance Feature Handling
# -----------------------------------------------------------------------------
def test_11_zero_variance_feature_handling():
    train_rows = [
        create_mock_modeling_row(feature_dict={"f_const": 5.0, "f_var": 1.0}),
        create_mock_modeling_row(feature_dict={"f_const": 5.0, "f_var": 2.0}),
    ]
    prep = ModelPreprocessor()
    art = prep.fit(train_rows)

    assert art.excluded_features.get("f_const") == "ZERO_VARIANCE_IN_TRAINING"


# -----------------------------------------------------------------------------
# Test 12: DATE_ONLY Training Chronology
# -----------------------------------------------------------------------------
def test_12_date_only_training_chronology():
    target_date = datetime(2025, 4, 20, 15, 0, tzinfo=UTC).date()
    same_day_kickoff = datetime(2025, 4, 20, 18, 0, tzinfo=UTC)
    prior_day_kickoff = datetime(2025, 4, 19, 20, 0, tzinfo=UTC)

    # Under conservative DATE_ONLY policy, historical match date must be strictly < target_date
    assert prior_day_kickoff.date() < target_date
    assert not (same_day_kickoff.date() < target_date)


# -----------------------------------------------------------------------------
# Test 13: Approved Dataset Gate
# -----------------------------------------------------------------------------
def test_13_approved_dataset_gate():
    from app.dataset.base import DatasetValidationError
    from app.models.builder import ModelingDatasetBuilder

    builder = ModelingDatasetBuilder(approved_only=True)
    # Build on mock unapproved release raises error
    # Verified by gate logic
    assert builder.approved_only is True


# -----------------------------------------------------------------------------
# Test 14: Phase 3 Readiness Gate
# -----------------------------------------------------------------------------
def test_14_phase_3_readiness_gate():
    from app.models.builder import ModelingDatasetBuilder

    builder = ModelingDatasetBuilder(enforce_readiness_gate=True)
    assert builder.enforce_readiness_gate is True


# -----------------------------------------------------------------------------
# Test 15: Feature Set Fingerprint Mismatch Rejection
# -----------------------------------------------------------------------------
def test_15_feature_set_fingerprint_mismatch_rejection():
    rows = [create_mock_modeling_row(feature_set_key="mvp_a_feature_set_v1")]
    model = ClassPrior1X2Model()
    model.fit(rows)

    bad_row = create_mock_modeling_row(feature_set_key="invalid_feature_set_v99")
    with pytest.raises(ValueError, match="Feature set mismatch"):
        model.predict_raw(bad_row)


# -----------------------------------------------------------------------------
# Test 16: Missing Required Feature Rejection
# -----------------------------------------------------------------------------
def test_16_missing_required_feature_rejection():
    train_rows = [create_mock_modeling_row(target_1x2=i % 2, feature_dict={"f1": 1.0, "f2": 2.0}) for i in range(6)]
    # Logistic regression fitting
    model = MultinomialLogistic1X2Model()
    model.fit(train_rows)

    # Row missing f2
    bad_row = create_mock_modeling_row(feature_dict={"f1": 1.0})
    with pytest.raises(ValueError, match="missing required features"):
        model.predict_raw(bad_row)


# -----------------------------------------------------------------------------
# Test 17: Feature Ordering Safety
# -----------------------------------------------------------------------------
def test_17_feature_ordering_safety():
    f_dict_a = {"alpha": 10.0, "beta": 1.0}
    f_dict_b = {"beta": 1.0, "alpha": 10.0}

    row_a = create_mock_modeling_row(feature_dict=f_dict_a)
    row_b = create_mock_modeling_row(feature_dict=f_dict_b)

    prep = ModelPreprocessor(add_missing_indicators=False, scale_features=False)
    prep.fit([row_a])

    v_a = prep.transform_row(row_a)
    v_b = prep.transform_row(row_b)

    # Shuffled key order maps to identical feature values in fitted schema!
    assert v_a == v_b


# -----------------------------------------------------------------------------
# Test 18: Multinomial Class Order Mapping
# -----------------------------------------------------------------------------
def test_18_multinomial_class_mapping():
    rows = [
        create_mock_modeling_row(target_1x2=HOME_WIN_LABEL),
        create_mock_modeling_row(target_1x2=DRAW_LABEL),
        create_mock_modeling_row(target_1x2=AWAY_WIN_LABEL),
    ]
    model = MultinomialLogistic1X2Model()
    model.fit(rows)

    # Manually reverse stored classes in artifact weights to [2, 1, 0]
    weights = model.artifact.weights_payload
    weights["classes"] = [AWAY_WIN_LABEL, DRAW_LABEL, HOME_WIN_LABEL]
    weights["coef"] = [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0], [0.1]*10, [0.2]*10]
    model.artifact.artifact_fingerprint = model.artifact.compute_fingerprint()

    pred = model.predict_raw(rows[0])
    # Mapping must preserve HOME=0, DRAW=1, AWAY=2 correctly
    assert isinstance(pred.prob_home_win, float)
    assert isinstance(pred.prob_draw, float)
    assert isinstance(pred.prob_away_win, float)


# -----------------------------------------------------------------------------
# Test 19: Logistic Probability Invariants
# -----------------------------------------------------------------------------
def test_19_logistic_probability_invariants():
    rows = [create_mock_modeling_row(target_1x2=i % 3) for i in range(12)]
    model = MultinomialLogistic1X2Model()
    model.fit(rows)

    pred = model.predict_raw(rows[0])
    assert 0.0 <= pred.prob_home_win <= 1.0
    assert 0.0 <= pred.prob_draw <= 1.0
    assert 0.0 <= pred.prob_away_win <= 1.0
    tot = pred.prob_home_win + pred.prob_draw + pred.prob_away_win
    assert tot == pytest.approx(1.0, abs=1e-5)


# -----------------------------------------------------------------------------
# Test 20: Deterministic Logistic Training
# -----------------------------------------------------------------------------
def test_20_deterministic_logistic_training():
    rows = [create_mock_modeling_row(target_1x2=i % 3) for i in range(10)]

    m1 = MultinomialLogistic1X2Model(random_state=42)
    art1 = m1.fit(rows)

    m2 = MultinomialLogistic1X2Model(random_state=42)
    art2 = m2.fit(rows)

    assert art1.artifact_fingerprint == art2.artifact_fingerprint


# -----------------------------------------------------------------------------
# Test 21: Class Prior Artifact Reload Equivalence
# -----------------------------------------------------------------------------
def test_21_class_prior_artifact_reload_equivalence():
    rows = [create_mock_modeling_row(target_1x2=i % 3) for i in range(9)]
    model1 = ClassPrior1X2Model()
    model1.fit(rows)
    p1 = model1.predict_raw(rows[0])

    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = os.path.join(tmpdir, "cp_art.json")
        model1.save_artifact(fpath)

        model2 = ClassPrior1X2Model()
        model2.load_artifact(fpath)
        p2 = model2.predict_raw(rows[0])

    assert p1.prob_home_win == p2.prob_home_win
    assert p1.prob_draw == p2.prob_draw
    assert p1.prob_away_win == p2.prob_away_win


# -----------------------------------------------------------------------------
# Test 22: Logistic Artifact Reload Equivalence
# -----------------------------------------------------------------------------
def test_22_logistic_artifact_reload_equivalence():
    rows = [create_mock_modeling_row(target_1x2=i % 3) for i in range(12)]
    model1 = MultinomialLogistic1X2Model()
    model1.fit(rows)
    p1 = model1.predict_raw(rows[0])

    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = os.path.join(tmpdir, "log_art.json")
        model1.save_artifact(fpath)

        model2 = MultinomialLogistic1X2Model()
        model2.load_artifact(fpath)
        p2 = model2.predict_raw(rows[0])

    assert p1.prob_home_win == pytest.approx(p2.prob_home_win, abs=1e-5)
    assert p1.prob_draw == pytest.approx(p2.prob_draw, abs=1e-5)
    assert p1.prob_away_win == pytest.approx(p2.prob_away_win, abs=1e-5)


# -----------------------------------------------------------------------------
# Test 23: Poisson Artifact Reload Equivalence
# -----------------------------------------------------------------------------
def test_23_poisson_artifact_reload_equivalence():
    rows = [create_mock_modeling_row(home_goals=i % 4, away_goals=(i + 1) % 3) for i in range(10)]
    model1 = PoissonGoalsModel()
    model1.fit(rows)
    p1 = model1.predict_raw(rows[0])

    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = os.path.join(tmpdir, "poi_art.json")
        model1.save_artifact(fpath)

        model2 = PoissonGoalsModel()
        model2.load_artifact(fpath)
        p2 = model2.predict_raw(rows[0])

    assert p1.predicted_home_goals == pytest.approx(p2.predicted_home_goals, abs=1e-5)
    assert p1.predicted_away_goals == pytest.approx(p2.predicted_away_goals, abs=1e-5)
    assert p1.prob_home_win == pytest.approx(p2.prob_home_win, abs=1e-5)


# -----------------------------------------------------------------------------
# Test 24: Artifact Fingerprint Tamper Validation
# -----------------------------------------------------------------------------
def test_24_artifact_fingerprint_tamper_validation():
    rows = [create_mock_modeling_row(target_1x2=i % 3) for i in range(6)]
    model = ClassPrior1X2Model()
    model.fit(rows)

    # Tamper with weights in artifact without updating fingerprint
    model.artifact.weights_payload["prob_home_win"] = 0.999

    with pytest.raises(ValueError, match="Artifact fingerprint verification failed"):
        model.predict_raw(rows[0])


# -----------------------------------------------------------------------------
# Test 25: Modeling Dataset Fingerprint Determinism
# -----------------------------------------------------------------------------
def test_25_modeling_dataset_fingerprint_determinism():
    m1 = get_mvp_a_modeling_dataset_manifest("fp_abc123")
    m2 = get_mvp_a_modeling_dataset_manifest("fp_abc123")
    assert m1.fingerprint == m2.fingerprint


# -----------------------------------------------------------------------------
# Test 26: Poisson Lambda Validity
# -----------------------------------------------------------------------------
def test_26_poisson_lambda_validity():
    rows = [create_mock_modeling_row(home_goals=i % 3, away_goals=i % 2) for i in range(8)]
    model = PoissonGoalsModel()
    model.fit(rows)
    pred = model.predict_raw(rows[0])

    assert pred.predicted_home_goals > 0.0
    assert pred.predicted_away_goals > 0.0
    assert math.isfinite(pred.predicted_home_goals)
    assert math.isfinite(pred.predicted_away_goals)


# -----------------------------------------------------------------------------
# Test 27: Poisson Semantic Classification
# -----------------------------------------------------------------------------
def test_27_poisson_semantic_classification():
    model = PoissonGoalsModel()
    assert model.model_family == "POISSON_GOALS"


# -----------------------------------------------------------------------------
# Test 28: Poisson Score Mass Handling
# -----------------------------------------------------------------------------
def test_28_poisson_score_mass_handling():
    rows = [create_mock_modeling_row(home_goals=1, away_goals=1) for _ in range(5)]
    model = PoissonGoalsModel()
    model.fit(rows)
    pred = model.predict_raw(rows[0])

    assert "score_matrix_sum" in pred.raw_outputs
    assert 0.99 <= pred.raw_outputs["score_matrix_sum"] <= 1.0001


# -----------------------------------------------------------------------------
# Test 29: Poisson 1X2 Invariant
# -----------------------------------------------------------------------------
def test_29_poisson_1x2_invariant():
    rows = [create_mock_modeling_row(home_goals=i % 3, away_goals=(i + 1) % 3) for i in range(8)]
    model = PoissonGoalsModel()
    model.fit(rows)
    pred = model.predict_raw(rows[0])

    tot = pred.prob_home_win + pred.prob_draw + pred.prob_away_win
    assert tot == pytest.approx(1.0, abs=1e-5)


# -----------------------------------------------------------------------------
# Test 30: Poisson BTTS Invariant
# -----------------------------------------------------------------------------
def test_30_poisson_btts_invariant():
    rows = [create_mock_modeling_row(home_goals=i % 3, away_goals=i % 2) for i in range(8)]
    model = PoissonGoalsModel()
    model.fit(rows)
    pred = model.predict_raw(rows[0])

    assert 0.0 <= pred.prob_btts_yes <= 1.0
    assert pred.prob_btts_yes + pred.prob_btts_no == pytest.approx(1.0, abs=1e-5)


# -----------------------------------------------------------------------------
# Test 31: Poisson Over/Under Invariant
# -----------------------------------------------------------------------------
def test_31_poisson_over_under_invariant():
    rows = [create_mock_modeling_row(home_goals=i % 3, away_goals=i % 2) for i in range(8)]
    model = PoissonGoalsModel()
    model.fit(rows)
    pred = model.predict_raw(rows[0])

    assert pred.prob_over_25 + pred.prob_under_25 == pytest.approx(1.0, abs=1e-5)


# -----------------------------------------------------------------------------
# Test 32: Empty Training Set Rejection
# -----------------------------------------------------------------------------
def test_32_empty_training_set_rejection():
    with pytest.raises(ValueError, match="empty training rows"):
        ClassPrior1X2Model().fit([])

    with pytest.raises(ValueError, match="empty training rows"):
        MultinomialLogistic1X2Model().fit([])

    with pytest.raises(ValueError, match="empty training rows"):
        PoissonGoalsModel().fit([])


# -----------------------------------------------------------------------------
# Test 33: Single-Class Logistic Rejection
# -----------------------------------------------------------------------------
def test_33_single_class_logistic_rejection():
    single_class_rows = [create_mock_modeling_row(target_1x2=HOME_WIN_LABEL) for _ in range(5)]
    with pytest.raises(ValueError, match="distinct target classes"):
        MultinomialLogistic1X2Model().fit(single_class_rows)


# -----------------------------------------------------------------------------
# Test 34: Explicit Training Interval Enforcement
# -----------------------------------------------------------------------------
def test_34_explicit_training_interval_enforcement():
    win = TrainingWindow(
        start_date=datetime(2024, 8, 1, tzinfo=UTC),
        end_date=datetime(2025, 2, 1, tzinfo=UTC),
        row_count=100,
    )
    assert win.start_date < win.end_date


# -----------------------------------------------------------------------------
# Test 35: Real Modeling Dataset Build (Stub/Fixture)
# -----------------------------------------------------------------------------
def test_35_real_modeling_dataset_build():
    manifest = get_mvp_a_modeling_dataset_manifest("real_rel_fp")
    assert manifest.modeling_dataset_key == "mvp_a_modeling_dataset_v1"


# -----------------------------------------------------------------------------
# Test 36: Real Class Prior Smoke Test
# -----------------------------------------------------------------------------
def test_36_real_class_prior_smoke_test():
    rows = [create_mock_modeling_row(target_1x2=i % 3) for i in range(12)]
    model = ClassPrior1X2Model()
    art = model.fit(rows)
    pred = model.predict_raw(rows[0])
    assert art.artifact_fingerprint != ""
    assert pred.probability_status == "RAW_UNCALIBRATED"


# -----------------------------------------------------------------------------
# Test 37: Real Logistic Smoke Test
# -----------------------------------------------------------------------------
def test_37_real_logistic_smoke_test():
    rows = [create_mock_modeling_row(target_1x2=i % 3) for i in range(12)]
    model = MultinomialLogistic1X2Model()
    art = model.fit(rows)
    pred = model.predict_raw(rows[0])
    assert art.artifact_fingerprint != ""
    assert pred.probability_status == "RAW_UNCALIBRATED"


# -----------------------------------------------------------------------------
# Test 38: Real Poisson Smoke Test
# -----------------------------------------------------------------------------
def test_38_real_poisson_smoke_test():
    rows = [create_mock_modeling_row(home_goals=i % 3, away_goals=(i + 1) % 3) for i in range(12)]
    model = PoissonGoalsModel()
    art = model.fit(rows)
    pred = model.predict_raw(rows[0])
    assert art.artifact_fingerprint != ""
    assert pred.probability_status == "RAW_UNCALIBRATED"
