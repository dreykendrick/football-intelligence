"""
Unit Test Suite for Sprint 4.1 — Leakage-Safe Feature Preprocessing & Imputation Architecture
Verifies training-only fitted median imputation, missing indicators, standardization, and structural feature auditing.
"""
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.models.dataset_dto import ModelingRowDTO
from app.models.preprocessing import ModelPreprocessor


def _make_row(f_values: list[float | None], f_names: list[str] | None = None) -> ModelingRowDTO:
    if f_names is None:
        f_names = [f"feat_{i}" for i in range(len(f_values))]
    return ModelingRowDTO(
        match_id=uuid4(),
        competition_id=uuid4(),
        season_id=uuid4(),
        kickoff_utc=datetime.now(UTC),
        ordered_feature_names=f_names,
        feature_values=f_values,
        targets={"match_result_1x2_v1": 0},
    )


@pytest.mark.unit
def test_median_imputation_fit_statistics_from_training_only():
    f_names = ["feat_a", "feat_b"]
    # Training values for feat_a: [1.0, 2.0, None, 100.0] -> Non-missing: [1.0, 2.0, 100.0] -> Median = 2.0
    # Training values for feat_b: [10.0, None, 30.0, 20.0] -> Non-missing: [10.0, 20.0, 30.0] -> Median = 20.0
    train_rows = [
        _make_row([1.0, 10.0], f_names),
        _make_row([2.0, None], f_names),
        _make_row([None, 30.0], f_names),
        _make_row([100.0, 20.0], f_names),
    ]

    prep = ModelPreprocessor(add_missing_indicators=True, scale_features=False)
    artifact = prep.fit(train_rows)

    assert artifact.median_values["feat_a"] == 2.0
    assert artifact.median_values["feat_b"] == 20.0

    # Verify output column structure: feat_a, feat_a__is_missing, feat_b, feat_b__is_missing
    assert artifact.fitted_feature_names == [
        "feat_a", "feat_a__is_missing", "feat_b", "feat_b__is_missing"
    ]

    # Transform a target test row with missing value in feat_a
    test_row = _make_row([None, 15.0], f_names)
    transformed_vec = prep.transform_row(test_row)

    # feat_a imputed to 2.0, indicator=1.0, feat_b=15.0, indicator=0.0
    assert transformed_vec == [2.0, 1.0, 15.0, 0.0]


@pytest.mark.unit
def test_preprocessor_training_only_isolation_future_rows_do_not_affect_medians():
    f_names = ["feat_x"]
    train_rows = [
        _make_row([10.0], f_names),
        _make_row([20.0], f_names),
        _make_row([30.0], f_names),
    ]

    prep = ModelPreprocessor(add_missing_indicators=False, scale_features=False)
    artifact = prep.fit(train_rows)

    assert artifact.median_values["feat_x"] == 20.0

    # Transform future row with huge outlier value (100,000.0)
    future_row = _make_row([100000.0], f_names)
    transformed_vec = prep.transform_row(future_row)

    # Preprocessor artifact medians MUST remain 20.0
    assert artifact.median_values["feat_x"] == 20.0
    assert transformed_vec == [100000.0]


@pytest.mark.unit
def test_all_missing_feature_handling():
    f_names = ["feat_normal", "feat_all_missing"]
    train_rows = [
        _make_row([5.0, None], f_names),
        _make_row([10.0, None], f_names),
        _make_row([15.0, None], f_names),
    ]

    prep = ModelPreprocessor(add_missing_indicators=True, scale_features=False)
    artifact = prep.fit(train_rows)

    assert "feat_all_missing" in artifact.excluded_features
    assert artifact.excluded_features["feat_all_missing"] == "ALL_MISSING_IN_TRAINING"

    # Only feat_normal and feat_normal__is_missing should be in fitted columns
    assert artifact.fitted_feature_names == ["feat_normal", "feat_normal__is_missing"]
