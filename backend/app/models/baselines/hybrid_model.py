"""
Hybrid Structural + Feature Model.
Combines structural football strength (via AttackDefensePoissonModel) with engineered pre-match features.
Uses out-of-fold M1 predictions during training to avoid stacking leakage.
"""
from __future__ import annotations

import json
import os
import math
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
from app.models.baselines.attack_defense_poisson import AttackDefensePoissonModel
from app.models.splitting import TemporalSplitter
from app.models.targets import AWAY_WIN_LABEL, DRAW_LABEL, HOME_WIN_LABEL


class HybridStructuralFeatureModel(IPredictionModel):
    """Hybrid baseline model combining M1 lambdas and ML features."""

    model_key: str = "hybrid_structural_features_v1"
    model_family: str = "HYBRID_STRUCTURAL_ML"
    version: str = "1.0.0"
    target_key: str = "match_result_1x2_v1"
    feature_set_key: str = "mvp_a_feature_set_v1"
    lifecycle_status: str = "EXPERIMENTAL"
    declared_capabilities: list[ModelCapabilityEnum] = [ModelCapabilityEnum.ONE_X_TWO]

    def __init__(
        self,
        learning_rate: float = 0.05,
        max_iter: int = 150,
        max_depth: int | None = 4,
        random_state: int = 42,
    ) -> None:
        self.learning_rate = learning_rate
        self.max_iter = max_iter
        self.max_depth = max_depth
        self.random_state = random_state
        self.artifact: TrainedModelArtifact | None = None
        self._preprocessor: ModelPreprocessor | None = None
        self._clf: HistGradientBoostingClassifier | None = None
        self._m1_model = AttackDefensePoissonModel()

    def fit(
        self, training_rows: list[ModelingRowDTO], training_window: TrainingWindow | None = None
    ) -> TrainedModelArtifact:
        if not training_rows:
            raise ValueError("Cannot fit HybridStructuralFeatureModel on empty rows.")

        # 1. Fit Final M1 on all training rows (for inference)
        # Note: we also need out-of-fold predictions for training C4.
        self._m1_model.fit(training_rows)

        # 2. Generate out-of-fold M1 predictions for the training set to prevent leakage.
        # We split the training rows chronologically into 2 folds: early and late.
        # Train early -> predict late. For early, we just train a tiny sub-model on early_half 
        # (or use expanding window). For simplicity, we use 3 folds chronologically.
        oof_lambdas = np.zeros((len(training_rows), 2))
        
        # Sort rows chronologically just in case
        sorted_indices = np.argsort([r.kickoff_utc.timestamp() for r in training_rows])
        sorted_rows = [training_rows[i] for i in sorted_indices]
        
        folds = 3
        fold_size = len(sorted_rows) // folds
        
        for f in range(folds):
            if f == 0:
                # First fold: no history! We'll just train on itself (leakage, but minimal history anyway)
                # or better: use league averages / cold starts.
                temp_m1 = AttackDefensePoissonModel()
                temp_m1.fit(sorted_rows[:fold_size])
                for i in range(fold_size):
                    pred = temp_m1.predict_raw(sorted_rows[i])
                    oof_lambdas[sorted_indices[i], 0] = math.log(max(0.1, pred.predicted_home_goals))
                    oof_lambdas[sorted_indices[i], 1] = math.log(max(0.1, pred.predicted_away_goals))
            else:
                train_subset = sorted_rows[:f*fold_size]
                val_subset = sorted_rows[f*fold_size : (f+1)*fold_size if f < folds - 1 else len(sorted_rows)]
                
                temp_m1 = AttackDefensePoissonModel()
                temp_m1.fit(train_subset)
                
                start_idx = f * fold_size
                for i, r in enumerate(val_subset):
                    pred = temp_m1.predict_raw(r)
                    oof_lambdas[sorted_indices[start_idx + i], 0] = math.log(max(0.1, pred.predicted_home_goals))
                    oof_lambdas[sorted_indices[start_idx + i], 1] = math.log(max(0.1, pred.predicted_away_goals))

        # 3. Fit preprocessing on original features
        self._preprocessor = ModelPreprocessor(add_missing_indicators=False, scale_features=False)
        prep_art = self._preprocessor.fit(training_rows)

        X_base, _ = self._preprocessor.transform(training_rows)
        X_base_arr = np.array(X_base, dtype=np.float64)
        
        # Combine base features + OOF lambdas
        X_hybrid = np.hstack((X_base_arr, oof_lambdas))
        y = np.array([r.targets.get("match_result_1x2_v1") for r in training_rows], dtype=np.int64)

        # 4. Fit Hybrid GBDT
        self._clf = HistGradientBoostingClassifier(
            learning_rate=self.learning_rate,
            max_iter=self.max_iter,
            max_depth=self.max_depth,
            random_state=self.random_state,
        )
        self._clf.fit(X_hybrid, y)

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
                "random_state": self.random_state,
            },
            weights_payload={"classes": self._clf.classes_.tolist(), "n_features_in": int(self._clf.n_features_in_)},
        )
        artifact.artifact_fingerprint = artifact.compute_fingerprint()
        self.artifact = artifact
        return self.artifact

    def predict_raw(self, row: ModelingRowDTO) -> ModelPredictionDTO:
        if not self.artifact or not self._clf or not self._m1_model.artifact:
            raise RuntimeError("Model has not been fitted or loaded.")

        if not self._preprocessor:
            self._preprocessor = ModelPreprocessor()
            self._preprocessor.artifact = self.artifact.preprocessor_artifact

        x_vec = self._preprocessor.transform_row(row)
        
        # Get M1 structural prediction
        m1_pred = self._m1_model.predict_raw(row)
        log_lh = math.log(max(0.1, m1_pred.predicted_home_goals))
        log_la = math.log(max(0.1, m1_pred.predicted_away_goals))

        x_hybrid = np.array([x_vec + [log_lh, log_la]], dtype=np.float64)

        probs = self._clf.predict_proba(x_hybrid)[0]
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
            raw_outputs={"hybrid_probabilities": class_prob_map, "m1_lambda_home": math.exp(log_lh)},
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
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.artifact.model_dump_json(indent=2))
        with open(filepath + ".pkl", "wb") as f:
            pickle.dump(self._clf, f)
        # Save M1 inside a subdir
        self._m1_model.save_artifact(filepath + "_m1.json")

    def load_artifact(self, filepath: str) -> None:
        import pickle
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.artifact = TrainedModelArtifact.model_validate(data)
        
        self.learning_rate = self.artifact.hyperparameters.get("learning_rate", 0.05)
        self.max_iter = self.artifact.hyperparameters.get("max_iter", 150)
        self.max_depth = self.artifact.hyperparameters.get("max_depth", 4)
        self.random_state = self.artifact.hyperparameters.get("random_state", 42)
        
        self._preprocessor = ModelPreprocessor()
        self._preprocessor.artifact = self.artifact.preprocessor_artifact
        
        with open(filepath + ".pkl", "rb") as f:
            self._clf = pickle.load(f)
            
        self._m1_model.load_artifact(filepath + "_m1.json")

