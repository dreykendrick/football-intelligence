"""
Canonical Feature Set Manifest for Phase 3 — mvp_a_feature_set_v1
Defines the frozen, versioned manifest specification of all included and excluded pre-match features for Phase 4 consumption.
"""
from __future__ import annotations

import hashlib
from typing import Any
from pydantic import BaseModel, Field

from app.features.registry import global_feature_registry

MVP_A_FEATURE_SET_V1_KEY: str = "mvp_a_feature_set_v1"
MVP_A_FEATURE_SET_V1_VERSION: str = "1.0.0"
MVP_A_DATASET_RELEASE_KEY: str = "mvp_a_historical:v1"

# Explicit list of excluded Phase 4 prediction labels, odds, probabilities, and unverified data sources
EXCLUDED_FEATURE_KEYS: list[str] = [
    # Target Labels & Match Outcome Results
    "home_goals",
    "away_goals",
    "home_win",
    "draw",
    "away_win",
    "result",
    "half_time_home_score",
    "half_time_away_score",
    "btts_label",
    "over_2_5_label",
    # Bookmaker Odds & Implied Probabilities
    "B365H",
    "B365D",
    "B365A",
    "AvgH",
    "AvgD",
    "AvgA",
    "implied_home_prob",
    "implied_draw_prob",
    "implied_away_prob",
    # Phase 4 Model Outputs & Probabilities
    "predicted_home_goals",
    "predicted_away_goals",
    "lambda_home",
    "lambda_away",
    "elo_win_probability_home_v1",
    "elo_win_probability_draw_v1",
    "elo_win_probability_away_v1",
    "predicted_home_win_probability",
    "predicted_draw_probability",
    "predicted_away_win_probability",
    "btts_probability",
    "over_under_probability",
    # Unverified / Excluded Context Sources
    "provider_xg",
    "travel_distance_km",
    "weather_temperature",
    "injury_count",
    "future_fixture_density",
]


class FeatureSetManifest(BaseModel):
    """Frozen, inspectable manifest specification for a versioned feature set."""

    feature_set_key: str = MVP_A_FEATURE_SET_V1_KEY
    version: str = MVP_A_FEATURE_SET_V1_VERSION
    dataset_release_key: str = MVP_A_DATASET_RELEASE_KEY
    created_by_code_version: str = "1.0.0"
    scientific_notes: str = (
        "Frozen pre-match statistical feature set for MVP-A containing 251 point-in-time features "
        "covering general form, venue form, league baselines, attack/defense strength ratios, Elo ratings, "
        "and observed schedule rest/congestion. Explicitly excludes odds, 1X2 probabilities, and target scorelines."
    )
    included_feature_keys: list[str] = Field(default_factory=list)
    excluded_feature_keys: list[str] = Field(default_factory=lambda: list(EXCLUDED_FEATURE_KEYS))

    @property
    def feature_count(self) -> int:
        return len(self.included_feature_keys)

    @property
    def fingerprint(self) -> str:
        """Deterministic fingerprint of the feature set manifest composition."""
        raw_keys = ":".join(sorted(self.included_feature_keys))
        raw = f"{self.feature_set_key}:{self.version}:{self.dataset_release_key}:{raw_keys}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def get_mvp_a_feature_set_v1_manifest() -> FeatureSetManifest:
    """Returns the canonical frozen manifest for mvp_a_feature_set_v1."""
    # Included feature keys are frozen as all registered feature keys in sorted order
    keys = global_feature_registry.list_feature_keys()
    return FeatureSetManifest(
        feature_set_key=MVP_A_FEATURE_SET_V1_KEY,
        version=MVP_A_FEATURE_SET_V1_VERSION,
        dataset_release_key=MVP_A_DATASET_RELEASE_KEY,
        included_feature_keys=sorted(keys),
    )
