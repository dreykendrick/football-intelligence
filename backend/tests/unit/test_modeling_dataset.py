"""
Unit Test Suite for Sprint 4.1 — Modeling Dataset Architecture & Anti-Leakage Feature/Label Isolation
Verifies feature/label isolation assertion, modeling dataset manifest determinism, and row DTO invariants.
"""
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.models.dataset_dto import (
    MVP_A_MODELING_DATASET_KEY,
    ModelingDatasetManifest,
    ModelingExampleDTO,
    ModelingRowDTO,
    assert_feature_label_isolation,
    get_mvp_a_modeling_dataset_manifest,
)


@pytest.mark.unit
def test_feature_label_isolation_passes_on_valid_features():
    valid_feature_names = [
        "home_recent_ppg_v1",
        "away_recent_ppg_v1",
        "home_goals_scored_avg_v1",
        "away_goals_conceded_avg_v1",
        "home_elo_v1",
        "away_elo_v1",
        "home_rest_days_v1",
    ]
    # Must not raise error
    assert_feature_label_isolation(valid_feature_names)


@pytest.mark.unit
def test_feature_label_isolation_rejects_leaked_target_labels():
    leaked_cases = [
        ["home_recent_ppg_v1", "home_goals"],
        ["home_recent_ppg_v1", "away_goals"],
        ["home_recent_ppg_v1", "result"],
        ["home_recent_ppg_v1", "match_result_1x2_v1"],
        ["home_recent_ppg_v1", "over_under_2_5_v1"],
        ["home_recent_ppg_v1", "btts_v1"],
        ["home_recent_ppg_v1", "B365H"],
    ]

    for leaked_list in leaked_cases:
        with pytest.raises(ValueError, match="CRITICAL TARGET LEAKAGE DETECTED"):
            assert_feature_label_isolation(leaked_list)


@pytest.mark.unit
def test_modeling_dataset_manifest_determinism():
    manifest1 = get_mvp_a_modeling_dataset_manifest(dataset_release_fingerprint="abc123chk")
    manifest2 = get_mvp_a_modeling_dataset_manifest(dataset_release_fingerprint="abc123chk")

    assert manifest1.modeling_dataset_key == MVP_A_MODELING_DATASET_KEY
    assert manifest1.version == "1.0.0"
    assert manifest1.feature_set_key == "mvp_a_feature_set_v1"
    assert manifest1.fingerprint == manifest2.fingerprint
    assert len(manifest1.fingerprint) == 16


@pytest.mark.unit
def test_modeling_row_dto_structure():
    match_id = uuid4()
    comp_id = uuid4()
    season_id = uuid4()
    now = datetime.now(UTC)

    row = ModelingRowDTO(
        match_id=match_id,
        competition_id=comp_id,
        season_id=season_id,
        kickoff_utc=now,
        temporal_precision="EXACT_TIMESTAMP",
        dataset_release_key="mvp_a_historical:v1",
        dataset_release_fingerprint="release_fp_123",
        feature_set_key="mvp_a_feature_set_v1",
        feature_set_fingerprint="fset_fp_456",
        ordered_feature_names=["home_recent_ppg_v1", "away_recent_ppg_v1"],
        feature_values=[1.8, 1.2],
        missingness_metadata={},
        targets={"match_result_1x2_v1": 0, "home_goals_v1": 2, "away_goals_v1": 1},
    )

    assert row.match_id == match_id
    assert row.feature_values == [1.8, 1.2]
    assert row.targets["match_result_1x2_v1"] == 0
