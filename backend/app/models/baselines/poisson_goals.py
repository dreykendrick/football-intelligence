"""
Poisson Goals Baseline Model Implementation
Implements a dual Poisson GLM estimating expected home goals (lambda_home) and away goals (lambda_away),
with score-matrix derivation for raw 1X2, BTTS, and Over/Under 2.5 probabilities.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any
import numpy as np
from scipy.stats import poisson
from sklearn.linear_model import PoissonRegressor

from app.models.base import IPredictionModel, ModelCapabilityEnum, ModelPredictionDTO, TrainedModelArtifact, TrainingWindow
from app.models.dataset_dto import ModelingRowDTO
from app.models.preprocessing import ModelPreprocessor, PreprocessingArtifact


class PoissonGoalsModel(IPredictionModel):
    """Poisson Expected Goals Baseline Model."""

    model_key: str = "poisson_goals_v1"
    model_family: str = "POISSON_GOALS"
    version: str = "1.0.0"
    target_key: str = "home_goals_v1:away_goals_v1"
    feature_set_key: str = "mvp_a_feature_set_v1"
    lifecycle_status: str = "EXPERIMENTAL"
    declared_capabilities: list[ModelCapabilityEnum] = [
        ModelCapabilityEnum.EXPECTED_GOALS,
        ModelCapabilityEnum.EXACT_SCORE,
        ModelCapabilityEnum.ONE_X_TWO,
        ModelCapabilityEnum.BTTS,
        ModelCapabilityEnum.OVER_UNDER,
    ]

    def __init__(self, alpha: float = 1.0, max_iter: int = 500) -> None:
        self.alpha = alpha
        self.max_iter = max_iter
        self.artifact: TrainedModelArtifact | None = None
        self._preprocessor: ModelPreprocessor | None = None

    def fit(
        self, training_rows: list[ModelingRowDTO], training_window: TrainingWindow | None = None
    ) -> TrainedModelArtifact:
        """Fits home and away goal Poisson regressions strictly on training rows."""
        if not training_rows:
            raise ValueError("Cannot fit PoissonGoalsModel on empty training rows.")

        # 1. Fit preprocessor on training data only
        self._preprocessor = ModelPreprocessor(add_missing_indicators=True, scale_features=True)
        prep_art = self._preprocessor.fit(training_rows)

        # 2. Transform training rows
        X_list, column_names = self._preprocessor.transform(training_rows)
        X = np.array(X_list, dtype=np.float64)

        y_home = np.array([r.targets.get("home_goals_v1", 0) for r in training_rows], dtype=np.float64)
        y_away = np.array([r.targets.get("away_goals_v1", 0) for r in training_rows], dtype=np.float64)

        # 3. Fit Home Goals Poisson Regressor
        reg_home = PoissonRegressor(alpha=self.alpha, max_iter=self.max_iter)
        reg_home.fit(X, y_home)

        # 4. Fit Away Goals Poisson Regressor
        reg_away = PoissonRegressor(alpha=self.alpha, max_iter=self.max_iter)
        reg_away.fit(X, y_away)

        if not training_window:
            training_window = TrainingWindow(
                row_count=len(training_rows),
                modeling_dataset_key=training_rows[0].dataset_release_key,
                modeling_dataset_fingerprint=training_rows[0].dataset_release_fingerprint,
            )

        weights = {
            "home_coef": reg_home.coef_.tolist(),
            "home_intercept": float(reg_home.intercept_),
            "away_coef": reg_away.coef_.tolist(),
            "away_intercept": float(reg_away.intercept_),
        }

        artifact = TrainedModelArtifact(
            model_key=self.model_key,
            model_family=self.model_family,
            version=self.version,
            target_key=self.target_key,
            feature_set_key=self.feature_set_key,
            lifecycle_status=self.lifecycle_status,
            training_window=training_window,
            preprocessor_artifact=prep_art,
            hyperparameters={"alpha": self.alpha, "max_iter": self.max_iter},
            weights_payload=weights,
        )
        artifact.artifact_fingerprint = artifact.compute_fingerprint()
        self.artifact = artifact

        return self.artifact

    def predict_raw(self, row: ModelingRowDTO) -> ModelPredictionDTO:
        """Generates raw predicted expected goals (lambda) and derived score-matrix probabilities."""
        if not self.artifact:
            raise RuntimeError("Model has not been fitted or loaded with an artifact.")

        if not self.artifact.verify_integrity():
            raise ValueError("Artifact fingerprint verification failed: payload has been tampered with.")

        if row.feature_set_key != self.artifact.feature_set_key:
            raise ValueError(f"Feature set mismatch: expected '{self.artifact.feature_set_key}', got '{row.feature_set_key}'")

        # Schema validation
        required_features = [
            f for f in self.artifact.preprocessor_artifact.ordered_input_features
            if self.artifact.preprocessor_artifact.excluded_features.get(f) != "ALL_MISSING_IN_TRAINING"
        ]
        row_feat_set = set(row.ordered_feature_names)
        missing_req = [f for f in required_features if f not in row_feat_set]
        if missing_req:
            raise ValueError(f"Input feature vector missing required features: {missing_req[:5]}")

        if not self._preprocessor:
            self._preprocessor = ModelPreprocessor()
            self._preprocessor.artifact = self.artifact.preprocessor_artifact

        # Transform single row
        x_vec = self._preprocessor.transform_row(row)
        x_arr = np.array(x_vec, dtype=np.float64)

        weights = self.artifact.weights_payload
        h_coef = np.array(weights["home_coef"], dtype=np.float64)
        h_intercept = float(weights["home_intercept"])
        a_coef = np.array(weights["away_coef"], dtype=np.float64)
        a_intercept = float(weights["away_intercept"])

        # Compute log-linear Poisson expectations (lambda > 0)
        lh_log = np.dot(h_coef, x_arr) + h_intercept
        la_log = np.dot(a_coef, x_arr) + a_intercept

        # Clip log-exponent to prevent numerical overflow
        lh_log = max(-10.0, min(10.0, lh_log))
        la_log = max(-10.0, min(10.0, la_log))

        lambda_home = max(0.01, round(float(math.exp(lh_log)), 4))
        lambda_away = max(0.01, round(float(math.exp(la_log)), 4))

        # Build 11x11 score distribution matrix (0 to 10 goals)
        grid_size = 11
        h_pmf = [poisson.pmf(i, lambda_home) for i in range(grid_size)]
        a_pmf = [j for j in (poisson.pmf(j, lambda_away) for j in range(grid_size))]

        matrix = np.outer(h_pmf, a_pmf)

        # Derive 1X2 Probabilities
        prob_home_win = float(np.sum(np.tril(matrix, -1)))
        prob_draw = float(np.sum(np.diag(matrix)))
        prob_away_win = float(np.sum(np.triu(matrix, 1)))

        tot_1x2 = prob_home_win + prob_draw + prob_away_win
        if tot_1x2 > 0:
            prob_home_win = round(prob_home_win / tot_1x2, 6)
            prob_draw = round(prob_draw / tot_1x2, 6)
            prob_away_win = round(1.0 - (prob_home_win + prob_draw), 6)

        # Derive Over / Under 2.5
        prob_over_25 = 0.0
        for i in range(grid_size):
            for j in range(grid_size):
                if i + j >= 3:
                    prob_over_25 += matrix[i, j]

        prob_over_25 = round(min(1.0, max(0.0, float(prob_over_25))), 6)
        prob_under_25 = round(1.0 - prob_over_25, 6)

        # Derive BTTS
        prob_btts_yes = 0.0
        for i in range(1, grid_size):
            for j in range(1, grid_size):
                prob_btts_yes += matrix[i, j]

        prob_btts_yes = round(min(1.0, max(0.0, float(prob_btts_yes))), 6)
        prob_btts_no = round(1.0 - prob_btts_yes, 6)

        return ModelPredictionDTO(
            match_id=row.match_id,
            model_key=self.model_key,
            model_version=self.version,
            model_artifact_fingerprint=self.artifact.artifact_fingerprint,
            feature_snapshot_fingerprint=row.feature_set_fingerprint,
            prob_home_win=prob_home_win,
            prob_draw=prob_draw,
            prob_away_win=prob_away_win,
            predicted_home_goals=lambda_home,
            predicted_away_goals=lambda_away,
            prob_over_25=prob_over_25,
            prob_under_25=prob_under_25,
            prob_btts_yes=prob_btts_yes,
            prob_btts_no=prob_btts_no,
            raw_outputs={
                "lambda_home": lambda_home,
                "lambda_away": lambda_away,
                "score_matrix_sum": round(float(np.sum(matrix)), 6),
            },
            probability_status="RAW_UNCALIBRATED",
            lifecycle_status=self.lifecycle_status,
        )

    def predict_proba(self, row: ModelingRowDTO) -> dict[str, float]:
        """Returns raw 1X2 probabilities derived from Poisson score matrix."""
        pred = self.predict_raw(row)
        return {
            "HOME_WIN": pred.prob_home_win,
            "DRAW": pred.prob_draw,
            "AWAY_WIN": pred.prob_away_win,
        }

    def save_artifact(self, filepath: str) -> None:
        """Serializes model artifact JSON to disk."""
        if not self.artifact:
            raise RuntimeError("Cannot save un-fitted model artifact.")
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.artifact.model_dump_json(indent=2))

    def load_artifact(self, filepath: str) -> None:
        """Deserializes model artifact JSON from disk."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.artifact = TrainedModelArtifact.model_validate(data)
        self.alpha = self.artifact.hyperparameters.get("alpha", 1.0)
        self.max_iter = self.artifact.hyperparameters.get("max_iter", 500)
        self._preprocessor = ModelPreprocessor()
        self._preprocessor.artifact = self.artifact.preprocessor_artifact
