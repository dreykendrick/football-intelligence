"""
Leakage-Safe Feature Preprocessing & Imputation Architecture
Implements training-only fitted median imputation, missingness indicators, standardization,
and structural feature auditing (constant/all-missing exclusion) for statistical estimators.
"""
from __future__ import annotations

import hashlib
import math
from typing import Any
from pydantic import BaseModel, Field

from app.models.dataset_dto import ModelingRowDTO


class PreprocessingArtifact(BaseModel):
    """Immutable, serializable state artifact for a fitted preprocessor."""

    feature_set_key: str = "mvp_a_feature_set_v1"
    ordered_input_features: list[str] = Field(default_factory=list)
    fitted_feature_names: list[str] = Field(default_factory=list)
    median_values: dict[str, float] = Field(default_factory=dict)
    mean_values: dict[str, float] = Field(default_factory=dict)
    std_values: dict[str, float] = Field(default_factory=dict)
    add_missing_indicators: bool = True
    scale_features: bool = False
    excluded_features: dict[str, str] = Field(default_factory=dict)  # fkey -> reason

    @property
    def fingerprint(self) -> str:
        """Deterministic fingerprint of preprocessor state."""
        keys = ":".join(self.fitted_feature_names)
        medians = ":".join(f"{k}={self.median_values.get(k, 0.0):.4f}" for k in sorted(self.median_values.keys()))
        raw = f"{self.feature_set_key}:{keys}:{medians}:{self.add_missing_indicators}:{self.scale_features}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class ModelPreprocessor:
    """
    Leakage-Safe Preprocessor ensuring median imputation, missing indicators, and scaling
    are fitted strictly on training rows only.
    """

    def __init__(
        self,
        add_missing_indicators: bool = True,
        scale_features: bool = False,
        fallback_median: float = 0.0,
    ) -> None:
        self.add_missing_indicators = add_missing_indicators
        self.scale_features = scale_features
        self.fallback_median = fallback_median
        self.artifact: PreprocessingArtifact | None = None

    def fit(self, training_rows: list[ModelingRowDTO]) -> PreprocessingArtifact:
        """
        Fits imputer medians, scaler statistics, and structural exclusion rules
        strictly from training rows.
        """
        if not training_rows:
            raise ValueError("Cannot fit preprocessor on an empty training row set.")

        input_feature_names = training_rows[0].ordered_feature_names
        num_rows = len(training_rows)

        # 1. Collect non-missing values per feature
        feature_values_map: dict[str, list[float]] = {fkey: [] for fkey in input_feature_names}

        for row in training_rows:
            for idx, fkey in enumerate(row.ordered_feature_names):
                val = row.feature_values[idx]
                if val is not None and not math.isnan(val) and not math.isinf(val):
                    feature_values_map[fkey].append(float(val))

        median_values: dict[str, float] = {}
        mean_values: dict[str, float] = {}
        std_values: dict[str, float] = {}
        excluded_features: dict[str, str] = {}
        usable_features: list[str] = []

        # 2. Compute training medians, means, stds, and perform structural audit
        for fkey in input_feature_names:
            vals = feature_values_map[fkey]

            if not vals:
                # All values missing in training window -> exclude from fitted schema
                excluded_features[fkey] = "ALL_MISSING_IN_TRAINING"
                continue

            vals_sorted = sorted(vals)
            n = len(vals_sorted)
            if n % 2 == 1:
                med = vals_sorted[n // 2]
            else:
                med = (vals_sorted[n // 2 - 1] + vals_sorted[n // 2]) / 2.0

            median_values[fkey] = round(med, 6)

            # Variance / std calculation
            mean = sum(vals) / n
            mean_values[fkey] = round(mean, 6)

            variance = sum((x - mean) ** 2 for x in vals) / n
            std = math.sqrt(variance)
            std_values[fkey] = round(std, 6)

            if len(vals) == num_rows and variance == 0.0:
                # Zero variance (constant feature across all training rows)
                excluded_features[fkey] = "ZERO_VARIANCE_IN_TRAINING"
                # Keep in usable if scaling isn't strict, but log exclusion
                # usable_features.append(fkey)
                usable_features.append(fkey)
            else:
                usable_features.append(fkey)

        # 3. Construct final fitted feature output column list
        fitted_columns: list[str] = []
        for fkey in usable_features:
            fitted_columns.append(fkey)
            if self.add_missing_indicators:
                fitted_columns.append(f"{fkey}__is_missing")

        self.artifact = PreprocessingArtifact(
            feature_set_key=training_rows[0].feature_set_key,
            ordered_input_features=input_feature_names,
            fitted_feature_names=fitted_columns,
            median_values=median_values,
            mean_values=mean_values,
            std_values=std_values,
            add_missing_indicators=self.add_missing_indicators,
            scale_features=self.scale_features,
            excluded_features=excluded_features,
        )

        return self.artifact

    def transform_row(self, row: ModelingRowDTO) -> list[float]:
        """Transforms a single row using the fitted PreprocessingArtifact state."""
        if not self.artifact:
            raise RuntimeError("Preprocessor has not been fitted yet.")

        # Build feature map for fast lookup
        row_feat_map = dict(zip(row.ordered_feature_names, row.feature_values))

        out_vector: list[float] = []

        # Iterate over base features present in ordered_input_features that were not excluded as ALL_MISSING
        for fkey in self.artifact.ordered_input_features:
            if fkey in self.artifact.excluded_features and self.artifact.excluded_features[fkey] == "ALL_MISSING_IN_TRAINING":
                continue

            raw_val = row_feat_map.get(fkey)
            is_missing = raw_val is None or math.isnan(raw_val) or math.isinf(raw_val)

            # Impute value
            if is_missing:
                imputed_val = self.artifact.median_values.get(fkey, self.fallback_median)
                indicator_val = 1.0
            else:
                imputed_val = float(raw_val)  # type: ignore
                indicator_val = 0.0

            # Optional scaling
            if self.artifact.scale_features:
                mean = self.artifact.mean_values.get(fkey, 0.0)
                std = self.artifact.std_values.get(fkey, 1.0)
                if std > 1e-8:
                    imputed_val = (imputed_val - mean) / std

            out_vector.append(imputed_val)

            if self.artifact.add_missing_indicators:
                out_vector.append(indicator_val)

        return out_vector

    def transform(self, rows: list[ModelingRowDTO]) -> tuple[list[list[float]], list[str]]:
        """
        Transforms a batch of modeling rows using fitted preprocessor statistics.
        Returns tuple of (matrix_of_features, fitted_column_names).
        """
        if not self.artifact:
            raise RuntimeError("Preprocessor has not been fitted yet.")

        matrix = [self.transform_row(r) for r in rows]
        return matrix, self.artifact.fitted_feature_names
