"""
Multinomial Logistic Regression 1X2 Baseline Model Implementation
Implements an interpretable multiclass logistic regression model consuming pre-match features
after deterministic leakage-safe preprocessing.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any
import numpy as np
from sklearn.linear_model import LogisticRegression

from app.models.base import IPredictionModel, ModelCapabilityEnum, ModelPredictionDTO, TrainedModelArtifact, TrainingWindow
from app.models.dataset_dto import ModelingRowDTO
from app.models.preprocessing import ModelPreprocessor, PreprocessingArtifact
from app.models.targets import AWAY_WIN_LABEL, DRAW_LABEL, HOME_WIN_LABEL


class MultinomialLogistic1X2Model(IPredictionModel):
    """Multinomial Logistic Regression 1X2 Baseline Model."""

    model_key: str = "multinomial_logistic_1x2_v1"
    model_family: str = "MULTINOMIAL_LOGISTIC"
    version: str = "1.0.0"
    target_key: str = "match_result_1x2_v1"
    feature_set_key: str = "mvp_a_feature_set_v1"
    lifecycle_status: str = "EXPERIMENTAL"
    declared_capabilities: list[ModelCapabilityEnum] = [ModelCapabilityEnum.ONE_X_TWO]

    def __init__(self, C: float = 1.0, max_iter: int = 500, random_state: int = 42) -> None:
        self.C = C
        self.max_iter = max_iter
        self.random_state = random_state
        self.artifact: TrainedModelArtifact | None = None
        self._preprocessor: ModelPreprocessor | None = None
        self._clf: LogisticRegression | None = None

    def fit(
        self, training_rows: list[ModelingRowDTO], training_window: TrainingWindow | None = None
    ) -> TrainedModelArtifact:
        """Fits multinomial logistic regression parameters strictly on training rows."""
        if not training_rows:
            raise ValueError("Cannot fit MultinomialLogistic1X2Model on empty training rows.")

        # 1. Fit leakage-safe preprocessor on training data only
        self._preprocessor = ModelPreprocessor(add_missing_indicators=True, scale_features=True)
        prep_art = self._preprocessor.fit(training_rows)

        # 2. Transform training rows
        X_list, column_names = self._preprocessor.transform(training_rows)
        X = np.array(X_list, dtype=np.float64)
        y = np.array([r.targets.get("match_result_1x2_v1") for r in training_rows], dtype=np.int64)

        distinct_classes = np.unique(y)
        if len(distinct_classes) < 2:
            raise ValueError(f"Training dataset must contain at least 2 distinct target classes, found: {distinct_classes}")

        # 3. Fit Logistic Regression
        clf = LogisticRegression(
            C=self.C,
            solver="lbfgs",
            max_iter=self.max_iter,
            random_state=self.random_state,
        )
        clf.fit(X, y)
        self._clf = clf

        if not training_window:
            training_window = TrainingWindow(
                row_count=len(training_rows),
                modeling_dataset_key=training_rows[0].dataset_release_key,
                modeling_dataset_fingerprint=training_rows[0].dataset_release_fingerprint,
            )

        weights = {
            "coef": clf.coef_.tolist(),
            "intercept": clf.intercept_.tolist(),
            "classes": clf.classes_.tolist(),
            "n_features_in": int(clf.n_features_in_),
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
            hyperparameters={"C": self.C, "max_iter": self.max_iter, "random_state": self.random_state},
            weights_payload=weights,
        )
        artifact.artifact_fingerprint = artifact.compute_fingerprint()
        self.artifact = artifact

        return self.artifact

    def predict_raw(self, row: ModelingRowDTO) -> ModelPredictionDTO:
        """Generates raw uncalibrated 1X2 prediction probabilities."""
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

        # Re-instantiate preprocessor if needed
        if not self._preprocessor:
            self._preprocessor = ModelPreprocessor()
            self._preprocessor.artifact = self.artifact.preprocessor_artifact

        # Transform single target row
        x_vec = self._preprocessor.transform_row(row)

        weights = self.artifact.weights_payload
        coef = np.array(weights["coef"], dtype=np.float64)
        intercept = np.array(weights["intercept"], dtype=np.float64)
        classes = list(weights["classes"])

        x_arr = np.array(x_vec, dtype=np.float64)

        if coef.ndim == 1:
            # Binary classification fallback
            z = np.dot(coef, x_arr) + intercept[0]
            p1 = 1.0 / (1.0 + math.exp(-z))
            p0 = 1.0 - p1
            probs = np.array([p0, p1])
        else:
            # Multiclass softmax
            logits = np.dot(coef, x_arr) + intercept
            # Softmax stabilization
            max_l = np.max(logits)
            exp_l = np.exp(logits - max_l)
            probs = exp_l / np.sum(exp_l)

        # Map classes explicitly to HOME_WIN (0), DRAW (1), AWAY_WIN (2)
        class_prob_map: dict[int, float] = {cls_id: float(p) for cls_id, p in zip(classes, probs)}

        ph = class_prob_map.get(HOME_WIN_LABEL, 0.0)
        pd = class_prob_map.get(DRAW_LABEL, 0.0)
        pa = class_prob_map.get(AWAY_WIN_LABEL, 0.0)

        # Normalize probabilities so sum equals 1.0
        tot = ph + pd + pa
        if tot > 0:
            ph = round(ph / tot, 6)
            pd = round(pd / tot, 6)
            pa = round(1.0 - (ph + pd), 6)

        return ModelPredictionDTO(
            match_id=row.match_id,
            model_key=self.model_key,
            model_version=self.version,
            model_artifact_fingerprint=self.artifact.artifact_fingerprint,
            feature_snapshot_fingerprint=row.feature_set_fingerprint,
            prob_home_win=ph,
            prob_draw=pd,
            prob_away_win=pa,
            raw_outputs={"logistic_probabilities": class_prob_map},
            probability_status="RAW_UNCALIBRATED",
            lifecycle_status=self.lifecycle_status,
        )

    def predict_proba(self, row: ModelingRowDTO) -> dict[str, float]:
        """Returns raw 1X2 probabilities dict."""
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
        self.C = self.artifact.hyperparameters.get("C", 1.0)
        self.max_iter = self.artifact.hyperparameters.get("max_iter", 500)
        self.random_state = self.artifact.hyperparameters.get("random_state", 42)
        self._preprocessor = ModelPreprocessor()
        self._preprocessor.artifact = self.artifact.preprocessor_artifact
