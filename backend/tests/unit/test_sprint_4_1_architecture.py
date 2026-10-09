"""
Sprint 4.1 Architecture & Evaluation Foundation Comprehensive Test Suite
Validates 1X2 canonical contracts, feature eligibility manifest, temporal splitters,
preprocessing isolation, baseline models, probabilistic metrics, and evaluation reporting.
"""
from __future__ import annotations

import math
import os
import tempfile
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
import pytest

from app.models import (
    AWAY_WIN_LABEL,
    CANONICAL_1X2_OUTCOMES,
    CORE_TARGET_DEFINITIONS,
    DRAW_LABEL,
    EXCLUDED_COLUMNS,
    FORBIDDEN_LABEL_KEYS,
    HOME_WIN_LABEL,
    IDENTIFIER_COLUMNS,
    INT_TO_1X2_MAP,
    METADATA_COLUMNS,
    STR_TO_1X2_MAP,
    TARGET_COLUMNS,
    ClassPrior1X2Model,
    CompetitionPrior1X2Model,
    EloLogistic1X2Model,
    EvaluationReportDTO,
    FeatureCategory,
    FeatureEligibilityManifest,
    FeatureEligibilityStatus,
    MetricSummaryDTO,
    ModelEvaluator,
    ModelPredictionDTO,
    ModelPreprocessor,
    ModelingDatasetManifest,
    ModelingRowDTO,
    MultinomialLogistic1X2Model,
    TemporalSplitManifest,
    TemporalSplitPartition,
    TemporalSplitStrategy,
    TemporalSplitter,
    accuracy_score,
    assert_feature_label_isolation,
    balanced_accuracy_score,
    confusion_matrix_3x3,
    decode_1x2,
    encode_1x2,
    expected_calibration_error,
    get_phase_4_feature_eligibility_manifest,
    global_model_registry,
    multiclass_brier_score,
    multiclass_log_loss,
    per_class_brier_scores,
    prediction_entropy,
    ranked_probability_score,
    reliability_diagram_bins,
    validate_1x2_label,
    validate_temporal_partition_invariants,
    verify_feature_matrix_eligibility,
)


def create_test_modeling_row(
    match_id: UUID | None = None,
    competition_id: UUID | None = None,
    season_id: UUID | None = None,
    kickoff_utc: datetime | None = None,
    target_1x2: int = HOME_WIN_LABEL,
    home_goals: int = 2,
    away_goals: int = 1,
    feature_dict: dict[str, float] | None = None,
) -> ModelingRowDTO:
    """Helper to construct valid ModelingRowDTO instances for testing."""
    if match_id is None:
        match_id = uuid4()
    if competition_id is None:
        competition_id = uuid4()
    if season_id is None:
        season_id = uuid4()
    if kickoff_utc is None:
        kickoff_utc = datetime(2023, 10, 15, 15, 0, 0, tzinfo=UTC)

    if feature_dict is None:
        feature_dict = {
            "elo_difference_v1": 120.0,
            "home_elo_v1": 1600.0,
            "away_elo_v1": 1480.0,
            "home_recent_ppg_v1": 2.1,
            "away_recent_ppg_v1": 1.2,
            "league_home_goals_per_match_v1": 1.55,
            "league_away_goals_per_match_v1": 1.20,
        }

    fnames = sorted(list(feature_dict.keys()))
    fvals = [feature_dict[k] for k in fnames]

    return ModelingRowDTO(
        match_id=match_id,
        competition_id=competition_id,
        season_id=season_id,
        kickoff_utc=kickoff_utc,
        temporal_precision="EXACT_TIMESTAMP",
        dataset_release_key="mvp_a_historical:v1",
        dataset_release_fingerprint="test_release_hash",
        feature_set_key="mvp_a_feature_set_v1",
        feature_set_fingerprint="test_fset_hash",
        ordered_feature_names=fnames,
        feature_values=fvals,
        missingness_metadata={},
        targets={
            "match_result_1x2_v1": target_1x2,
            "home_goals_v1": home_goals,
            "away_goals_v1": away_goals,
            "over_under_2_5_v1": (home_goals + away_goals) >= 3,
            "btts_v1": (home_goals > 0) and (away_goals > 0),
        },
    )


# ==============================================================================
# 1. CANONICAL 1X2 OUTCOME CONTRACT TESTS
# ==============================================================================

def test_1x2_canonical_encodings_and_mappings():
    """Verifies canonical integer and string mappings for 1X2 outcomes."""
    assert HOME_WIN_LABEL == 0
    assert DRAW_LABEL == 1
    assert AWAY_WIN_LABEL == 2

    assert CANONICAL_1X2_OUTCOMES == ["HOME_WIN", "DRAW", "AWAY_WIN"]
    assert INT_TO_1X2_MAP[0] == "HOME_WIN"
    assert INT_TO_1X2_MAP[1] == "DRAW"
    assert INT_TO_1X2_MAP[2] == "AWAY_WIN"


def test_1x2_encoder_and_decoder_roundtrip():
    """Verifies encode_1x2 and decode_1x2 functions across all valid types."""
    assert encode_1x2("HOME_WIN") == 0
    assert encode_1x2("DRAW") == 1
    assert encode_1x2("AWAY_WIN") == 2
    assert encode_1x2("home_win") == 0
    assert encode_1x2(0) == 0
    assert encode_1x2(1) == 1
    assert encode_1x2(2) == 2

    assert decode_1x2(0) == "HOME_WIN"
    assert decode_1x2(1) == "DRAW"
    assert decode_1x2(2) == "AWAY_WIN"


def test_1x2_encoder_rejects_invalid_labels():
    """Verifies that invalid 1X2 labels raise clear ValueErrors."""
    with pytest.raises(ValueError, match="Invalid 1X2 string label"):
        encode_1x2("INVALID_OUTCOME")

    with pytest.raises(ValueError, match="Invalid integer 1X2 label"):
        encode_1x2(99)

    with pytest.raises(ValueError, match="Invalid integer 1X2 label"):
        decode_1x2(-1)


def test_model_prediction_dto_top_outcome_and_margin():
    """Verifies most_likely_outcome and margin_between_top_outcomes properties."""
    pred = ModelPredictionDTO(
        match_id=uuid4(),
        model_key="test_model",
        model_version="1.0.0",
        model_artifact_fingerprint="art_123",
        feature_snapshot_fingerprint="snap_123",
        prob_home_win=0.55,
        prob_draw=0.25,
        prob_away_win=0.20,
    )
    assert pred.most_likely_outcome == "HOME_WIN"
    assert pred.margin_between_top_outcomes == pytest.approx(0.30, abs=1e-5)

    # Tie-breaking test: Home Win vs Draw tie -> Home Win preferred by policy
    pred_tie = ModelPredictionDTO(
        match_id=uuid4(),
        model_key="test_model",
        model_version="1.0.0",
        model_artifact_fingerprint="art_123",
        feature_snapshot_fingerprint="snap_123",
        prob_home_win=0.40,
        prob_draw=0.40,
        prob_away_win=0.20,
    )
    assert pred_tie.most_likely_outcome == "HOME_WIN"
    assert pred_tie.margin_between_top_outcomes == pytest.approx(0.0, abs=1e-5)


# ==============================================================================
# 2. MODELING DATASET & FEATURE ELIGIBILITY MANIFEST TESTS
# ==============================================================================

def test_explicit_column_categorization():
    """Verifies explicit column grouping definitions."""
    assert "match_id" in IDENTIFIER_COLUMNS
    assert "kickoff_utc" in METADATA_COLUMNS
    assert "match_result_1x2_v1" in TARGET_COLUMNS
    assert "B365H" in EXCLUDED_COLUMNS
    assert "home_score" in EXCLUDED_COLUMNS


def test_feature_label_isolation_assertion():
    """Verifies assert_feature_label_isolation detects target leakage."""
    valid_features = ["home_elo_v1", "away_elo_v1", "home_recent_ppg_v1"]
    # Should not raise
    assert_feature_label_isolation(valid_features)

    # Leak final home goals
    with pytest.raises(ValueError, match="CRITICAL TARGET LEAKAGE DETECTED"):
        assert_feature_label_isolation(valid_features + ["home_goals_v1"])

    # Leak bookmaker odds
    with pytest.raises(ValueError, match="CRITICAL TARGET LEAKAGE DETECTED"):
        assert_feature_label_isolation(valid_features + ["B365H"])


def test_phase_4_feature_eligibility_manifest():
    """Verifies the machine-readable Phase 4 eligibility manifest structure and exclusions."""
    manifest = get_phase_4_feature_eligibility_manifest()
    assert isinstance(manifest, FeatureEligibilityManifest)
    assert len(manifest.entries) > 200

    # Ensure eligible features are present
    assert "home_elo_v1" in manifest.eligible_feature_names
    assert "home_attack_strength_v1" in manifest.eligible_feature_names

    # Ensure forbidden features are excluded with explicit reason
    entry_b365 = manifest.get_entry("B365H")
    assert entry_b365 is not None
    assert not entry_b365.modeling_eligible
    assert entry_b365.status == FeatureEligibilityStatus.EXCLUDED_BOOKMAKER

    entry_target = manifest.get_entry("match_result_1x2_v1")
    assert entry_target is not None
    assert not entry_target.modeling_eligible
    assert entry_target.status == FeatureEligibilityStatus.EXCLUDED_TARGET


def test_verify_feature_matrix_eligibility_helper():
    """Verifies verify_feature_matrix_eligibility passes clean features and catches violations."""
    clean = ["home_elo_v1", "away_elo_v1"]
    verify_feature_matrix_eligibility(clean)

    with pytest.raises(ValueError, match="FEATURE ELIGIBILITY VIOLATION"):
        verify_feature_matrix_eligibility(clean + ["final_away_goals"])


# ==============================================================================
# 3. TEMPORAL SPLIT ARCHITECTURE TESTS
# ==============================================================================

def test_temporal_split_expanding_window_invariants():
    """Verifies expanding window temporal splitting produces strict forward-chaining folds."""
    base_time = datetime(2022, 8, 1, 15, 0, 0, tzinfo=UTC)
    rows = [
        create_test_modeling_row(kickoff_utc=base_time + timedelta(days=i))
        for i in range(100)
    ]

    manifest, folds = TemporalSplitter.split_expanding_window(rows, n_splits=3)
    assert isinstance(manifest, TemporalSplitManifest)
    assert manifest.strategy == TemporalSplitStrategy.EXPANDING_WINDOW
    assert len(folds) == 3
    assert len(manifest.config_fingerprint) == 16

    # Verify each fold
    for fold_idx, (tr, val, te) in enumerate(folds):
        assert len(tr) > 0
        assert len(val) > 0
        assert len(te) > 0
        # Disjoint
        tr_ids = {r.match_id for r in tr}
        val_ids = {r.match_id for r in val}
        te_ids = {r.match_id for r in te}
        assert tr_ids.isdisjoint(val_ids)
        assert tr_ids.isdisjoint(te_ids)
        assert val_ids.isdisjoint(te_ids)
        # Chronology
        assert max(r.kickoff_utc for r in tr) <= min(r.kickoff_utc for r in val)
        assert max(r.kickoff_utc for r in val) <= min(r.kickoff_utc for r in te)


def test_temporal_split_season_holdout_invariants():
    """Verifies season holdout temporal splitting (Train 21/22+22/23 -> Test 23/24)."""
    s1_id = uuid4()
    s2_id = uuid4()
    s3_id = uuid4()
    s_map = {s1_id: "2021/2022", s2_id: "2022/2023", s3_id: "2023/2024"}

    base_time = datetime(2021, 8, 1, 15, 0, 0, tzinfo=UTC)
    rows = []
    # Season 1: 30 matches
    for i in range(30):
        rows.append(create_test_modeling_row(season_id=s1_id, kickoff_utc=base_time + timedelta(days=i)))
    # Season 2: 30 matches
    for i in range(30):
        rows.append(create_test_modeling_row(season_id=s2_id, kickoff_utc=base_time + timedelta(days=365 + i)))
    # Season 3: 30 matches
    for i in range(30):
        rows.append(create_test_modeling_row(season_id=s3_id, kickoff_utc=base_time + timedelta(days=730 + i)))

    manifest, (tr, val, te) = TemporalSplitter.split_season_holdout(
        rows,
        season_id_to_year=s_map,
        train_seasons=["2021/2022", "2022/2023"],
        test_seasons=["2023/2024"],
    )

    assert len(tr) == 60
    assert len(val) == 0  # No validation season specified
    assert len(te) == 30
    assert max(r.kickoff_utc for r in tr) <= min(r.kickoff_utc for r in te)


def test_validate_temporal_partition_invariants_detects_leakage():
    """Verifies validator detects chronological inversion and partition overlap."""
    t1 = datetime(2023, 1, 1, tzinfo=UTC)
    t2 = datetime(2023, 1, 2, tzinfo=UTC)
    m_id = uuid4()

    r1 = create_test_modeling_row(match_id=m_id, kickoff_utc=t1)
    r2 = create_test_modeling_row(match_id=m_id, kickoff_utc=t2)

    # Overlap error
    with pytest.raises(ValueError, match="DATA LEAKAGE VIOLATION: Overlap"):
        validate_temporal_partition_invariants([r1], [r2], [create_test_modeling_row(kickoff_utc=t2)])

    # Temporal order inversion error
    r_late = create_test_modeling_row(kickoff_utc=datetime(2023, 5, 1, tzinfo=UTC))
    r_early = create_test_modeling_row(kickoff_utc=datetime(2023, 2, 1, tzinfo=UTC))
    with pytest.raises(ValueError, match="TEMPORAL LEAKAGE VIOLATION"):
        validate_temporal_partition_invariants([r_late], [r_early], [create_test_modeling_row(kickoff_utc=datetime(2023, 6, 1, tzinfo=UTC))])


# ==============================================================================
# 4. PREPROCESSING ARCHITECTURE TESTS
# ==============================================================================

def test_preprocessor_training_only_isolation():
    """Verifies preprocessor learns medians and scaling strictly from training rows."""
    tr_rows = [
        create_test_modeling_row(feature_dict={"feat_a": 10.0, "feat_b": 2.0}),
        create_test_modeling_row(feature_dict={"feat_a": 20.0, "feat_b": 4.0}),
        create_test_modeling_row(feature_dict={"feat_a": 30.0, "feat_b": 6.0}),
    ]
    preprocessor = ModelPreprocessor(add_missing_indicators=True, scale_features=True)
    art = preprocessor.fit(tr_rows)

    assert art.median_values["feat_a"] == 20.0
    assert art.mean_values["feat_a"] == 20.0

    # Transform test row with missing value -> uses training median
    test_row = create_test_modeling_row(feature_dict={"feat_a": float("nan"), "feat_b": 10.0})
    transformed = preprocessor.transform_row(test_row)
    assert len(transformed) == 4  # 2 features + 2 missing indicators


# ==============================================================================
# 5. BASELINE MODELS TESTS
# ==============================================================================

def test_class_prior_1x2_baseline():
    """Verifies empirical class prior baseline fits training outcome proportions."""
    train_rows = (
        [create_test_modeling_row(target_1x2=HOME_WIN_LABEL) for _ in range(50)]
        + [create_test_modeling_row(target_1x2=DRAW_LABEL) for _ in range(30)]
        + [create_test_modeling_row(target_1x2=AWAY_WIN_LABEL) for _ in range(20)]
    )
    model = ClassPrior1X2Model()
    art = model.fit(train_rows)
    assert art.model_key == "class_prior_1x2_v1"

    test_row = create_test_modeling_row()
    pred = model.predict_raw(test_row)
    assert pred.prob_home_win == pytest.approx(0.50, abs=1e-4)
    assert pred.prob_draw == pytest.approx(0.30, abs=1e-4)
    assert pred.prob_away_win == pytest.approx(0.20, abs=1e-4)
    assert pred.prob_home_win + pred.prob_draw + pred.prob_away_win == pytest.approx(1.0, abs=1e-5)

    vec = model.predict_proba_vector(test_row)
    assert vec == [0.5, 0.3, 0.2]


def test_competition_prior_1x2_baseline_with_fallback():
    """Verifies competition prior baseline stratifies by competition and uses global fallback."""
    comp_a = uuid4()
    comp_b = uuid4()
    comp_unknown = uuid4()

    # Comp A: 8 Home wins, 2 Away wins (10 matches)
    rows_a = [create_test_modeling_row(competition_id=comp_a, target_1x2=HOME_WIN_LABEL) for _ in range(8)] + \
             [create_test_modeling_row(competition_id=comp_a, target_1x2=AWAY_WIN_LABEL) for _ in range(2)]

    # Comp B: 2 Home wins, 8 Draws (10 matches)
    rows_b = [create_test_modeling_row(competition_id=comp_b, target_1x2=HOME_WIN_LABEL) for _ in range(2)] + \
             [create_test_modeling_row(competition_id=comp_b, target_1x2=DRAW_LABEL) for _ in range(8)]

    model = CompetitionPrior1X2Model(min_competition_samples=5)
    model.fit(rows_a + rows_b)

    # Predict Comp A
    pred_a = model.predict_raw(create_test_modeling_row(competition_id=comp_a))
    assert pred_a.prob_home_win == pytest.approx(0.80, abs=1e-4)
    assert pred_a.prob_away_win == pytest.approx(0.20, abs=1e-4)

    # Predict Comp B
    pred_b = model.predict_raw(create_test_modeling_row(competition_id=comp_b))
    assert pred_b.prob_home_win == pytest.approx(0.20, abs=1e-4)
    assert pred_b.prob_draw == pytest.approx(0.80, abs=1e-4)

    # Predict Unknown Comp -> Falls back to global distribution (10/20 Home, 8/20 Draw, 2/20 Away)
    pred_unk = model.predict_raw(create_test_modeling_row(competition_id=comp_unknown))
    assert pred_unk.prob_home_win == pytest.approx(0.50, abs=1e-4)
    assert pred_unk.prob_draw == pytest.approx(0.40, abs=1e-4)
    assert pred_unk.prob_away_win == pytest.approx(0.10, abs=1e-4)


def test_elo_logistic_1x2_baseline():
    """Verifies Elo logistic baseline fits regularized logistic regression on Elo differences."""
    train_rows = []
    # High Home Elo -> HOME_WIN
    for _ in range(20):
        train_rows.append(create_test_modeling_row(
            target_1x2=HOME_WIN_LABEL,
            feature_dict={"elo_difference_v1": 250.0, "home_elo_v1": 1750.0, "away_elo_v1": 1500.0}
        ))
    # Balanced Elo -> DRAW
    for _ in range(20):
        train_rows.append(create_test_modeling_row(
            target_1x2=DRAW_LABEL,
            feature_dict={"elo_difference_v1": 0.0, "home_elo_v1": 1500.0, "away_elo_v1": 1500.0}
        ))
    # High Away Elo -> AWAY_WIN
    for _ in range(20):
        train_rows.append(create_test_modeling_row(
            target_1x2=AWAY_WIN_LABEL,
            feature_dict={"elo_difference_v1": -250.0, "home_elo_v1": 1500.0, "away_elo_v1": 1750.0}
        ))

    model = EloLogistic1X2Model()
    art = model.fit(train_rows)
    assert art.model_key == "elo_logistic_1x2_v1"

    # Test on strong home favorite
    pred = model.predict_raw(create_test_modeling_row(
        feature_dict={"elo_difference_v1": 300.0, "home_elo_v1": 1800.0, "away_elo_v1": 1500.0}
    ))
    assert pred.prob_home_win > pred.prob_away_win
    assert pred.prob_home_win + pred.prob_draw + pred.prob_away_win == pytest.approx(1.0, abs=1e-5)


# ==============================================================================
# 6. EVALUATION METRICS MATHEMATICAL GOLDEN TESTS
# ==============================================================================

def test_multiclass_log_loss_golden_values():
    """Golden test for multiclass Log Loss against analytical truth."""
    # Example 1: Perfect prediction
    y_true_perf = [0, 1, 2]
    y_prob_perf = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    # Clipped to 1e-15 -> -log(1) = 0.0
    assert multiclass_log_loss(y_true_perf, y_prob_perf) == pytest.approx(0.0, abs=1e-4)

    # Example 2: Uniform prediction (p = 1/3 for all) -> -log(1/3) = ln(3) ≈ 1.098612
    y_true_unif = [0, 1, 2]
    y_prob_unif = [[1/3, 1/3, 1/3], [1/3, 1/3, 1/3], [1/3, 1/3, 1/3]]
    assert multiclass_log_loss(y_true_unif, y_prob_unif) == pytest.approx(math.log(3), abs=1e-4)

    # Example 3: Hand-calculated case
    # Match 1: y=0 (Home Win), p=[0.6, 0.3, 0.1] -> -ln(0.6) = 0.510826
    # Match 2: y=1 (Draw),     p=[0.2, 0.5, 0.3] -> -ln(0.5) = 0.693147
    # Mean: (0.510826 + 0.693147) / 2 = 0.601986
    y_true = [0, 1]
    y_probs = [[0.6, 0.3, 0.1], [0.2, 0.5, 0.3]]
    assert multiclass_log_loss(y_true, y_probs) == pytest.approx(0.601986, abs=1e-4)


def test_multiclass_brier_score_golden_values():
    """Golden test for multiclass Brier score against analytical truth."""
    # Match 1: y=0 (target=[1,0,0]), p=[0.6, 0.3, 0.1]
    #   err1 = (0.6-1)^2 + (0.3-0)^2 + (0.1-0)^2 = 0.16 + 0.09 + 0.01 = 0.26
    # Match 2: y=1 (target=[0,1,0]), p=[0.2, 0.5, 0.3]
    #   err2 = (0.2-0)^2 + (0.5-1)^2 + (0.3-0)^2 = 0.04 + 0.25 + 0.09 = 0.38
    # Mean Brier: (0.26 + 0.38) / 2 = 0.32
    y_true = [0, 1]
    y_probs = [[0.6, 0.3, 0.1], [0.2, 0.5, 0.3]]
    assert multiclass_brier_score(y_true, y_probs) == pytest.approx(0.32, abs=1e-4)


def test_ranked_probability_score_golden_values():
    """Golden test for Ranked Probability Score (RPS) against analytical truth."""
    # Match 1: y=0 (Home Win) -> actual CDF = [1, 1]
    #   pred = [0.6, 0.3, 0.1] -> pred CDF = [0.6, 0.9]
    #   RPS1 = 0.5 * ((0.6 - 1)^2 + (0.9 - 1)^2) = 0.5 * (0.16 + 0.01) = 0.085
    # Match 2: y=1 (Draw) -> actual CDF = [0, 1]
    #   pred = [0.2, 0.5, 0.3] -> pred CDF = [0.2, 0.7]
    #   RPS2 = 0.5 * ((0.2 - 0)^2 + (0.7 - 1)^2) = 0.5 * (0.04 + 0.09) = 0.065
    # Mean RPS = (0.085 + 0.065) / 2 = 0.075
    y_true = [0, 1]
    y_probs = [[0.6, 0.3, 0.1], [0.2, 0.5, 0.3]]
    assert ranked_probability_score(y_true, y_probs) == pytest.approx(0.075, abs=1e-4)


def test_per_class_brier_scores():
    """Verifies per-class decomposition of Brier scores."""
    y_true = [0, 1]
    y_probs = [[0.6, 0.3, 0.1], [0.2, 0.5, 0.3]]
    comp = per_class_brier_scores(y_true, y_probs)

    # Home error: ((0.6-1)^2 + (0.2-0)^2)/2 = (0.16 + 0.04)/2 = 0.10
    assert comp["home_win"] == pytest.approx(0.10, abs=1e-4)
    # Draw error: ((0.3-0)^2 + (0.5-1)^2)/2 = (0.09 + 0.25)/2 = 0.17
    assert comp["draw"] == pytest.approx(0.17, abs=1e-4)
    # Away error: ((0.1-0)^2 + (0.3-0)^2)/2 = (0.01 + 0.09)/2 = 0.05
    assert comp["away_win"] == pytest.approx(0.05, abs=1e-4)
    # Total sum equals multiclass Brier score (0.10 + 0.17 + 0.05 = 0.32)
    assert sum(comp.values()) == pytest.approx(0.32, abs=1e-4)


def test_expected_calibration_error_and_bins():
    """Verifies reliability diagram binning and Expected Calibration Error computation."""
    # Perfectly calibrated case: 100 predictions of confidence 0.8, 80 correct
    y_true = [0] * 80 + [1] * 20
    y_probs = [[0.8, 0.1, 0.1]] * 100

    ece = expected_calibration_error(y_true, y_probs, n_bins=10)
    # In bin [0.8, 0.9), avg_conf=0.8, emp_acc=80/100=0.8 -> ECE = 0.0
    assert ece == pytest.approx(0.0, abs=1e-4)

    # Uncalibrated case: confidence 0.9 but accuracy only 0.5 -> ECE = |0.5 - 0.9| = 0.4
    y_true_uncal = [0] * 50 + [1] * 50
    y_probs_uncal = [[0.9, 0.05, 0.05]] * 100
    ece_uncal = expected_calibration_error(y_true_uncal, y_probs_uncal, n_bins=10)
    assert ece_uncal == pytest.approx(0.40, abs=1e-4)


# ==============================================================================
# 7. MODEL EVALUATOR & REPORT SERIALIZATION TESTS
# ==============================================================================

def test_model_evaluator_end_to_end_report():
    """Verifies ModelEvaluator executes full evaluation suite and returns serialized report."""
    train_rows = [
        create_test_modeling_row(target_1x2=HOME_WIN_LABEL),
        create_test_modeling_row(target_1x2=DRAW_LABEL),
        create_test_modeling_row(target_1x2=AWAY_WIN_LABEL),
    ] * 20

    test_rows = [
        create_test_modeling_row(target_1x2=HOME_WIN_LABEL),
        create_test_modeling_row(target_1x2=DRAW_LABEL),
        create_test_modeling_row(target_1x2=AWAY_WIN_LABEL),
    ] * 10

    model = ClassPrior1X2Model()
    model.fit(train_rows)

    report = ModelEvaluator.evaluate_model(model, test_rows)
    assert isinstance(report, EvaluationReportDTO)
    assert report.model_key == "class_prior_1x2_v1"
    assert report.overall_metrics.sample_size == 30
    assert report.overall_metrics.log_loss > 0.0
    assert report.overall_metrics.brier_score > 0.0
    assert len(report.calibration_bins) == 10

    # JSON Roundtrip
    dumped = report.model_dump_json(indent=2)
    loaded = EvaluationReportDTO.model_validate_json(dumped)
    assert loaded.report_id == report.report_id
    assert loaded.overall_metrics.log_loss == report.overall_metrics.log_loss


# ==============================================================================
# 8. ARTIFACT INTEGRITY & TAMPER DETECTION TESTS
# ==============================================================================

def test_artifact_tamper_detection():
    """Verifies that tampering with serialized model weights invalidates artifact integrity."""
    train_rows = [
        create_test_modeling_row(target_1x2=HOME_WIN_LABEL),
        create_test_modeling_row(target_1x2=DRAW_LABEL),
        create_test_modeling_row(target_1x2=AWAY_WIN_LABEL),
    ] * 10
    model = ClassPrior1X2Model()
    art = model.fit(train_rows)
    assert art.verify_integrity() is True

    # Tamper with weights
    art.weights_payload["prob_home_win"] = 0.9999
    assert art.verify_integrity() is False
