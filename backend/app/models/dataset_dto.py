"""
Modeling Dataset DTOs & Anti-Leakage Feature/Label Isolation Architecture
Defines ModelingRowDTO, ModelingExampleDTO, ModelingDatasetManifest, and explicit feature/label boundary isolation checks.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.features.assembler import FeatureSetVectorDTO
from app.features.manifest import EXCLUDED_FEATURE_KEYS, get_mvp_a_feature_set_v1_manifest
from app.models.targets import CORE_TARGET_DEFINITIONS

MVP_A_MODELING_DATASET_KEY: str = "mvp_a_modeling_dataset_v1"
MVP_A_MODELING_DATASET_VERSION: str = "1.0.0"

# Target keys that must NEVER be inside the pre-match feature vector
FORBIDDEN_LABEL_KEYS: set[str] = set(EXCLUDED_FEATURE_KEYS).union({
    "match_result_1x2_v1",
    "over_under_2_5_v1",
    "btts_v1",
    "home_goals_v1",
    "away_goals_v1",
    "home_score",
    "away_score",
    "final_home_goals",
    "final_away_goals",
})

IDENTIFIER_COLUMNS: list[str] = [
    "match_id",
    "competition_id",
    "season_id",
    "home_team_id",
    "away_team_id",
]
METADATA_COLUMNS: list[str] = [
    "kickoff_utc",
    "temporal_precision",
    "dataset_release_key",
    "dataset_release_fingerprint",
    "feature_set_key",
    "feature_set_fingerprint",
    "home_team_name",
    "away_team_name",
]
TARGET_COLUMNS: list[str] = sorted(list(CORE_TARGET_DEFINITIONS.keys()))
EXCLUDED_COLUMNS: list[str] = sorted(list(FORBIDDEN_LABEL_KEYS))



def assert_feature_label_isolation(feature_names: list[str], target_keys: list[str] | None = None) -> None:
    """
    Programmatically verifies that no outcome label, scoreline, or forbidden key
    is present within the pre-match feature name list.
    Raises ValueError if target leakage is detected.
    """
    feature_set = set(feature_names)
    forbidden = set(FORBIDDEN_LABEL_KEYS)
    if target_keys:
        forbidden.update(target_keys)
    leaked = feature_set.intersection(forbidden)
    if leaked:
        raise ValueError(
            f"CRITICAL TARGET LEAKAGE DETECTED: Pre-match feature vector contains forbidden label/outcome keys: {sorted(leaked)}"
        )


class ModelingRowDTO(BaseModel):
    """Canonical modeling dataset row containing strictly separated pre-match features and post-match targets."""

    match_id: UUID
    competition_id: UUID
    season_id: UUID
    kickoff_utc: datetime
    temporal_precision: str = "EXACT_TIMESTAMP"  # "EXACT_TIMESTAMP" or "DATE_ONLY"
    home_team_id: UUID | None = None
    away_team_id: UUID | None = None
    home_team_name: str | None = None
    away_team_name: str | None = None
    dataset_release_key: str = "mvp_a_historical:v1"
    dataset_release_fingerprint: str = ""
    feature_set_key: str = "mvp_a_feature_set_v1"
    feature_set_fingerprint: str = ""
    ordered_feature_names: list[str] = Field(default_factory=list)
    feature_values: list[float | None] = Field(default_factory=list)
    missingness_metadata: dict[str, Any] = Field(default_factory=dict)
    targets: dict[str, Any] = Field(default_factory=dict)


class ModelingExampleDTO(BaseModel):
    """Decoupled container for features and labels for a single match."""

    features: FeatureSetVectorDTO
    labels: dict[str, Any]


class ModelingDatasetManifest(BaseModel):
    """Versioned contract and deterministic specification for a modeling dataset."""

    modeling_dataset_key: str = MVP_A_MODELING_DATASET_KEY
    version: str = MVP_A_MODELING_DATASET_VERSION
    dataset_release_key: str = "mvp_a_historical:v1"
    dataset_release_fingerprint: str = ""
    feature_set_key: str = "mvp_a_feature_set_v1"
    feature_set_fingerprint: str = ""
    target_keys: list[str] = Field(default_factory=lambda: sorted(list(CORE_TARGET_DEFINITIONS.keys())))
    row_eligibility_rule: str = "FINISHED_MATCHES_WITH_VALID_SCORES_ONLY"
    ordering_rule: str = "KICKOFF_UTC_ASC_THEN_MATCH_ID"

    @property
    def fingerprint(self) -> str:
        """Deterministic fingerprint of the modeling dataset specification."""
        tkeys = ":".join(sorted(self.target_keys))
        raw = f"{self.modeling_dataset_key}:{self.version}:{self.dataset_release_key}:{self.dataset_release_fingerprint}:{self.feature_set_key}:{self.feature_set_fingerprint}:{tkeys}:{self.row_eligibility_rule}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def get_mvp_a_modeling_dataset_manifest(
    dataset_release_fingerprint: str = "",
) -> ModelingDatasetManifest:
    """Returns the canonical frozen manifest for mvp_a_modeling_dataset_v1."""
    fset_manifest = get_mvp_a_feature_set_v1_manifest()
    return ModelingDatasetManifest(
        modeling_dataset_key=MVP_A_MODELING_DATASET_KEY,
        version=MVP_A_MODELING_DATASET_VERSION,
        dataset_release_key=fset_manifest.dataset_release_key,
        dataset_release_fingerprint=dataset_release_fingerprint,
        feature_set_key=fset_manifest.feature_set_key,
        feature_set_fingerprint=fset_manifest.fingerprint,
    )
