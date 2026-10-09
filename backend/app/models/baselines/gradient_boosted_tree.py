"""
Gradient Boosted Tree 1X2 Classification Model.
Implements a multiclass gradient-boosted tree challenger using scikit-learn's HistGradientBoostingClassifier.
"""
from __future__ import annotations

import json
import math
import os
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from app.models.base import (
    IPredictionModel,
    ModelCapabilityEnum,
    ModelPredictionDTO,
    TrainedModelArtifact,
    TrainingWindow,
)
from app.models.dataset_dto import ModelingRowDTO
from app.models.preprocessing import ModelPreprocessor
from app.models.targets import AWAY_WIN_LABEL, DRAW_LABEL, HOME_WIN_LABEL


class GradientBoosted1X2Model(IPredictionModel):
    """Gradient Boosted Tree 1X2 Baseline Model."""

    model_key: str = "gradient_boosted_1x2_v1"
    model_family: str = "GRADIENT_BOOSTED_TREE"
    version: str = "1.0.0"
    target_key: str = "match_result_1x2_v1"
    feature_set_key: str = "mvp_a_feature_set_v1"
    lifecycle_status: str = "EXPERIMENTAL"
    declared_capabilities: list[ModelCapabilityEnum] = [ModelCapabilityEnum.ONE_X_TWO]

    def __init__(
        self,
        learning_rate: float = 0.05,
        max_iter: int = 200,
        max_depth: int | None = 5,
        min_samples_leaf: int = 50,
        l2_regularization: float = 1.0,
        random_state: int = 42,
    ) -> None:
        self.learning_rate = learning_rate
        self.max_iter = max_iter
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.l2_regularization = l2_regularization
        self.random_state = random_state
        self.artifact: TrainedModelArtifact | None = None
        self._preprocessor: ModelPreprocessor | None = None
        self._clf: HistGradientBoostingClassifier | None = None

    def fit(
        self, training_rows: list[ModelingRowDTO], training_window: TrainingWindow | None = None
    ) -> TrainedModelArtifact:
        if not training_rows:
            raise ValueError("Cannot fit GradientBoosted1X2Model on empty training rows.")

        self._preprocessor = ModelPreprocessor(add_missing_indicators=False, scale_features=False)
        prep_art = self._preprocessor.fit(training_rows)

        X_list, column_names = self._preprocessor.transform(training_rows)
        X = np.array(X_list, dtype=np.float64)
        y = np.array([r.targets.get("match_result_1x2_v1") for r in training_rows], dtype=np.int64)

        distinct_classes = np.unique(y)
        if len(distinct_classes) < 2:
            raise ValueError(f"Training dataset must contain at least 2 distinct target classes, found: {distinct_classes}")

        clf = HistGradientBoostingClassifier(
            learning_rate=self.learning_rate,
            max_iter=self.max_iter,
            max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            l2_regularization=self.l2_regularization,
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

        artifact = TrainedModelArtifact(
            model_key=self.model_key,
            model_family=self.model_family,
            version=self.version,
            target_key=self.target_key,
            feature_set_key=self.feature_set_key,
            lifecycle_status=self.lifecycle_status,
            training_window=training_window,
            preprocessor_artifact=prep_art,
            hyperparameters={
                "learning_rate": self.learning_rate,
                "max_iter": self.max_iter,
                "max_depth": self.max_depth,
                "min_samples_leaf": self.min_samples_leaf,
                "l2_regularization": self.l2_regularization,
                "random_state": self.random_state,
            },
            # NOTE: HistGradientBoostingClassifier cannot be trivially serialized to JSON weights.
            # We must use pickling in production, but for Sprint 4.5 artifact spec we store empty weights
            # and rely on standard saving mechanism or just memory for evaluation.
            # To strictly meet serialization requirements without a binary blob, we would store the trees,
            # but that is extremely complex. We'll store a placeholder and use pickle for the actual model.
            weights_payload={"classes": clf.classes_.tolist(), "n_features_in": int(clf.n_features_in_)},
        )
        artifact.artifact_fingerprint = artifact.compute_fingerprint()
        self.artifact = artifact
        return self.artifact

    def predict_raw(self, row: ModelingRowDTO) -> ModelPredictionDTO:
        if not self.artifact or not self._clf:
            raise RuntimeError("Model has not been fitted or loaded.")

        if not self.artifact.verify_integrity():
            raise ValueError("Artifact fingerprint verification failed.")

        if not self._preprocessor:
            self._preprocessor = ModelPreprocessor()
            self._preprocessor.artifact = self.artifact.preprocessor_artifact

        x_vec = self._preprocessor.transform_row(row)
        x_arr = np.array([x_vec], dtype=np.float64)

        probs = self._clf.predict_proba(x_arr)[0]
        classes = self.artifact.weights_payload["classes"]

        class_prob_map: dict[int, float] = {cls_id: float(p) for cls_id, p in zip(classes, probs)}

        ph = class_prob_map.get(HOME_WIN_LABEL, 0.0)
        pd = class_prob_map.get(DRAW_LABEL, 0.0)
        pa = class_prob_map.get(AWAY_WIN_LABEL, 0.0)

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
            raw_outputs={"gbdt_probabilities": class_prob_map},
            probability_status="RAW_UNCALIBRATED",
            lifecycle_status=self.lifecycle_status,
        )

    def predict_proba(self, row: ModelingRowDTO) -> dict[str, float]:
        pred = self.predict_raw(row)
        return {
            "HOME_WIN": pred.prob_home_win,
            "DRAW": pred.prob_draw,
            "AWAY_WIN": pred.prob_away_win,
        }

    def save_artifact(self, filepath: str) -> None:
        import pickle
        if not self.artifact or not self._clf:
            raise RuntimeError("Cannot save un-fitted model artifact.")
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        # Save JSON artifact
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.artifact.model_dump_json(indent=2))
        # Save scikit-learn model object alongside
        with open(filepath + ".pkl", "wb") as f:
            pickle.dump(self._clf, f)

    def load_artifact(self, filepath: str) -> None:
        import pickle
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.artifact = TrainedModelArtifact.model_validate(data)
        self.learning_rate = self.artifact.hyperparameters.get("learning_rate", 0.05)
        self.max_iter = self.artifact.hyperparameters.get("max_iter", 200)
        self.max_depth = self.artifact.hyperparameters.get("max_depth", 5)
        self.min_samples_leaf = self.artifact.hyperparameters.get("min_samples_leaf", 50)
        self.l2_regularization = self.artifact.hyperparameters.get("l2_regularization", 1.0)
        self.random_state = self.artifact.hyperparameters.get("random_state", 42)
        
        self._preprocessor = ModelPreprocessor()
        self._preprocessor.artifact = self.artifact.preprocessor_artifact
        
        with open(filepath + ".pkl", "rb") as f:
            self._clf = pickle.load(f)
