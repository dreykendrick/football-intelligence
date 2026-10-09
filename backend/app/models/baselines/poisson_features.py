"""
Feature-Based Goal Regressor Model.
Implements expected-goals prediction using HistGradientBoostingRegressor with Poisson loss.
Outputs lambda_home and lambda_away, then derives distributions via GoalDistributionEngine.
"""
from __future__ import annotations

import json
import math
import os
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from app.models.base import (
    IPredictionModel,
    ModelCapabilityEnum,
    ModelPredictionDTO,
    TrainedModelArtifact,
    TrainingWindow,
)
from app.models.dataset_dto import ModelingRowDTO
from app.models.preprocessing import ModelPreprocessor
from app.models.engine import GoalDistributionEngine


class FeatureGoalRegressorModel(IPredictionModel):
    """Gradient Boosted Poisson Goal Regressor Baseline Model."""

    model_key: str = "feature_goal_model_v1"
    model_family: str = "GRADIENT_BOOSTED_POISSON"
    version: str = "1.0.0"
    target_key: str = "goals_v1"
    feature_set_key: str = "mvp_a_feature_set_v1"
    lifecycle_status: str = "EXPERIMENTAL"
    declared_capabilities: list[ModelCapabilityEnum] = [
        ModelCapabilityEnum.ONE_X_TWO,
        ModelCapabilityEnum.EXACT_SCORE,
        ModelCapabilityEnum.OVER_UNDER,
        ModelCapabilityEnum.BTTS,
    ]

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
        self._clf_home: HistGradientBoostingRegressor | None = None
        self._clf_away: HistGradientBoostingRegressor | None = None
        self._distribution_engine = GoalDistributionEngine()

    def fit(
        self, training_rows: list[ModelingRowDTO], training_window: TrainingWindow | None = None
    ) -> TrainedModelArtifact:
        if not training_rows:
            raise ValueError("Cannot fit FeatureGoalRegressorModel on empty training rows.")

        self._preprocessor = ModelPreprocessor(add_missing_indicators=False, scale_features=False)
        prep_art = self._preprocessor.fit(training_rows)

        X_list, column_names = self._preprocessor.transform(training_rows)
        X = np.array(X_list, dtype=np.float64)
        y_home = np.array([r.targets.get("home_goals_v1") for r in training_rows], dtype=np.float64)
        y_away = np.array([r.targets.get("away_goals_v1") for r in training_rows], dtype=np.float64)

        # Train home model
        self._clf_home = HistGradientBoostingRegressor(
            loss="poisson",
            learning_rate=self.learning_rate,
            max_iter=self.max_iter,
            max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            l2_regularization=self.l2_regularization,
            random_state=self.random_state,
        )
        self._clf_home.fit(X, y_home)

        # Train away model
        self._clf_away = HistGradientBoostingRegressor(
            loss="poisson",
            learning_rate=self.learning_rate,
            max_iter=self.max_iter,
            max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            l2_regularization=self.l2_regularization,
            random_state=self.random_state + 1,  # different seed for independence
        )
        self._clf_away.fit(X, y_away)

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
            weights_payload={"n_features_in": int(self._clf_home.n_features_in_)},
        )
        artifact.artifact_fingerprint = artifact.compute_fingerprint()
        self.artifact = artifact
        return self.artifact

    def predict_raw(self, row: ModelingRowDTO) -> ModelPredictionDTO:
        if not self.artifact or not self._clf_home or not self._clf_away:
            raise RuntimeError("Model has not been fitted or loaded.")

        if not self.artifact.verify_integrity():
            raise ValueError("Artifact fingerprint verification failed.")

        if not self._preprocessor:
            self._preprocessor = ModelPreprocessor()
            self._preprocessor.artifact = self.artifact.preprocessor_artifact

        x_vec = self._preprocessor.transform_row(row)
        x_arr = np.array([x_vec], dtype=np.float64)

        # Predict expected goals
        lambda_home = float(self._clf_home.predict(x_arr)[0])
        lambda_away = float(self._clf_away.predict(x_arr)[0])

        # Enforce sanity bounds
        lambda_home = max(0.01, min(15.0, lambda_home))
        lambda_away = max(0.01, min(15.0, lambda_away))

        # Derive probabilities using engine
        matrix = self._distribution_engine.compute_score_matrix(lambda_home, lambda_away)
        one_x_two = self._distribution_engine.derive_1x2(matrix, source_model=self.model_key)
        btts = self._distribution_engine.derive_btts(matrix, lambda_home, lambda_away)
        ou25 = self._distribution_engine.derive_over_under_2_5(matrix, lambda_home, lambda_away)
        exact_scores = self._distribution_engine.top_exact_scores(matrix)

        mls = (exact_scores[0]["home_goals"], exact_scores[0]["away_goals"]) if exact_scores else (0, 0)

        return ModelPredictionDTO(
            match_id=row.match_id,
            model_key=self.model_key,
            model_version=self.version,
            model_artifact_fingerprint=self.artifact.artifact_fingerprint,
            feature_snapshot_fingerprint=row.feature_set_fingerprint,
            prob_home_win=one_x_two.home_win,
            prob_draw=one_x_two.draw,
            prob_away_win=one_x_two.away_win,
            predicted_home_goals=lambda_home,
            predicted_away_goals=lambda_away,
            prob_over_25=ou25.over,
            prob_under_25=ou25.under,
            prob_btts_yes=btts.yes,
            prob_btts_no=btts.no,
            most_likely_score=mls,
            top_exact_scores=exact_scores[:10],
            raw_outputs={"lambda_home": lambda_home, "lambda_away": lambda_away},
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
        if not self.artifact or not self._clf_home or not self._clf_away:
            raise RuntimeError("Cannot save un-fitted model artifact.")
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.artifact.model_dump_json(indent=2))
        with open(filepath + ".home.pkl", "wb") as f:
            pickle.dump(self._clf_home, f)
        with open(filepath + ".away.pkl", "wb") as f:
            pickle.dump(self._clf_away, f)

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
        
        with open(filepath + ".home.pkl", "rb") as f:
            self._clf_home = pickle.load(f)
        with open(filepath + ".away.pkl", "rb") as f:
            self._clf_away = pickle.load(f)
