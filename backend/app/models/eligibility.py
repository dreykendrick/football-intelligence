"""
Phase 4 Feature Eligibility Manifest & Governance Architecture
Provides a machine-readable specification of all approved point-in-time features,
explicitly documenting categories, missing-value policies, transformation requirements,
and strict exclusion of targets, bookmaker odds, and post-match data.
"""
from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

from app.features.manifest import EXCLUDED_FEATURE_KEYS, get_mvp_a_feature_set_v1_manifest
from app.features.registry import global_feature_registry
from app.models.dataset_dto import FORBIDDEN_LABEL_KEYS


class FeatureCategory(str, Enum):
    FORM = "FORM"
    VENUE = "VENUE"
    STRENGTH = "STRENGTH"
    ELO = "ELO"
    SCHEDULE = "SCHEDULE"
    BASELINE = "BASELINE"
    TARGET = "TARGET"
    BOOKMAKER = "BOOKMAKER"
    POST_MATCH = "POST_MATCH"
    UNVERIFIED_CONTEXT = "UNVERIFIED_CONTEXT"


class FeatureEligibilityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    EXCLUDED_TARGET = "EXCLUDED_TARGET"
    EXCLUDED_BOOKMAKER = "EXCLUDED_BOOKMAKER"
    EXCLUDED_POST_MATCH = "EXCLUDED_POST_MATCH"
    EXCLUDED_UNVERIFIED = "EXCLUDED_UNVERIFIED"


class FeatureEligibilityEntry(BaseModel):
    """Machine-readable metadata entry for a single feature/column in Phase 4."""

    name: str
    data_type: str = "float64"
    category: FeatureCategory
    status: FeatureEligibilityStatus
    point_in_time_eligible: bool
    modeling_eligible: bool
    exclusion_reason: str | None = None
    missing_value_policy: str = "TRAINING_MEDIAN_IMPUTATION"
    transformation_policy: str = "TRAINING_STANDARDIZATION"
    feature_set_version: str = "1.0.0"


class FeatureEligibilityManifest(BaseModel):
    """Frozen machine-readable Phase 4 feature eligibility manifest."""

    manifest_version: str = "1.0.0"
    feature_set_key: str = "mvp_a_feature_set_v1"
    entries: list[FeatureEligibilityEntry] = Field(default_factory=list)

    @property
    def eligible_feature_names(self) -> list[str]:
        return [e.name for e in self.entries if e.modeling_eligible]

    @property
    def excluded_feature_names(self) -> list[str]:
        return [e.name for e in self.entries if not e.modeling_eligible]

    def get_entry(self, name: str) -> FeatureEligibilityEntry | None:
        for e in self.entries:
            if e.name == name:
                return e
        return None


def get_phase_4_feature_eligibility_manifest() -> FeatureEligibilityManifest:
    """Constructs the canonical Phase 4 feature eligibility manifest."""
    entries: list[FeatureEligibilityEntry] = []

    # 1. Registered Phase 3 point-in-time features
    reg_keys = global_feature_registry.list_feature_keys()
    for fkey in sorted(reg_keys):
        # Categorize by feature key name
        if "elo" in fkey:
            cat = FeatureCategory.ELO
        elif "venue" in fkey:
            cat = FeatureCategory.VENUE
        elif "strength" in fkey:
            cat = FeatureCategory.STRENGTH
        elif "rest" in fkey or "matches_last" in fkey:
            cat = FeatureCategory.SCHEDULE
        elif "league_" in fkey:
            cat = FeatureCategory.BASELINE
        else:
            cat = FeatureCategory.FORM

        entries.append(
            FeatureEligibilityEntry(
                name=fkey,
                data_type="float64",
                category=cat,
                status=FeatureEligibilityStatus.ELIGIBLE,
                point_in_time_eligible=True,
                modeling_eligible=True,
                exclusion_reason=None,
                missing_value_policy="TRAINING_MEDIAN_IMPUTATION",
                transformation_policy="TRAINING_STANDARDIZATION",
                feature_set_version="1.0.0",
            )
        )

    # 2. Excluded Target Labels
    targets = [
        "match_result_1x2_v1", "home_goals", "away_goals", "home_win", "draw", "away_win",
        "result", "half_time_home_score", "half_time_away_score", "btts_label", "over_2_5_label",
        "home_goals_v1", "away_goals_v1", "btts_v1", "over_under_2_5_v1", "final_home_goals", "final_away_goals"
    ]
    for t in sorted(set(targets)):
        entries.append(
            FeatureEligibilityEntry(
                name=t,
                data_type="int64" if "goals" in t or "1x2" in t else "bool",
                category=FeatureCategory.TARGET,
                status=FeatureEligibilityStatus.EXCLUDED_TARGET,
                point_in_time_eligible=False,
                modeling_eligible=False,
                exclusion_reason="Supervised post-match target outcome; forbidden in pre-match inputs",
                missing_value_policy="REJECT_ROW",
                transformation_policy="NONE",
            )
        )

    # 3. Excluded Bookmaker Odds
    bookmaker_keys = [
        "B365H", "B365D", "B365A", "AvgH", "AvgD", "AvgA",
        "implied_home_prob", "implied_draw_prob", "implied_away_prob"
    ]
    for b in sorted(bookmaker_keys):
        entries.append(
            FeatureEligibilityEntry(
                name=b,
                data_type="float64",
                category=FeatureCategory.BOOKMAKER,
                status=FeatureEligibilityStatus.EXCLUDED_BOOKMAKER,
                point_in_time_eligible=False,
                modeling_eligible=False,
                exclusion_reason="Bookmaker market odds; forbidden in independent football intelligence models",
                missing_value_policy="EXCLUDED",
                transformation_policy="NONE",
            )
        )

    # 4. Excluded Unverified / Context
    context_keys = [
        "provider_xg", "travel_distance_km", "weather_temperature",
        "injury_count", "future_fixture_density"
    ]
    for c in sorted(context_keys):
        entries.append(
            FeatureEligibilityEntry(
                name=c,
                data_type="float64",
                category=FeatureCategory.UNVERIFIED_CONTEXT,
                status=FeatureEligibilityStatus.EXCLUDED_UNVERIFIED,
                point_in_time_eligible=False,
                modeling_eligible=False,
                exclusion_reason="Unverified external data source not certified in MVP-A",
                missing_value_policy="EXCLUDED",
                transformation_policy="NONE",
            )
        )

    return FeatureEligibilityManifest(
        manifest_version="1.0.0",
        feature_set_key="mvp_a_feature_set_v1",
        entries=entries,
    )


def verify_feature_matrix_eligibility(feature_names: list[str]) -> None:
    """
    Validates a list of candidate model input feature names against the Phase 4 eligibility manifest.
    Raises ValueError if any ineligible or forbidden feature is found.
    """
    manifest = get_phase_4_feature_eligibility_manifest()
    excluded_map = {e.name: e.exclusion_reason for e in manifest.entries if not e.modeling_eligible}
    forbidden_set = set(FORBIDDEN_LABEL_KEYS).union(set(EXCLUDED_FEATURE_KEYS))

    violations: list[str] = []
    for f in feature_names:
        if f in forbidden_set or f in excluded_map:
            reason = excluded_map.get(f, "Forbidden outcome/bookmaker key")
            violations.append(f"{f} ({reason})")

    if violations:
        raise ValueError(
            f"FEATURE ELIGIBILITY VIOLATION: The following forbidden features were found in the model matrix: {violations}"
        )
