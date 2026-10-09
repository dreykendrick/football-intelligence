"""
Class Prior 1X2 Baseline Model Implementation
Implements a trivial empirical class-prior reference model that returns static 1X2 probabilities
derived strictly from training label frequencies.
"""
from __future__ import annotations

import json
import os
from typing import Any

from app.models.base import IPredictionModel, ModelCapabilityEnum, ModelPredictionDTO, TrainedModelArtifact, TrainingWindow
from app.models.dataset_dto import ModelingRowDTO
from app.models.preprocessing import ModelPreprocessor, PreprocessingArtifact
from app.models.targets import AWAY_WIN_LABEL, DRAW_LABEL, HOME_WIN_LABEL


class ClassPrior1X2Model(IPredictionModel):
    """Empirical Class-Prior 1X2 Baseline Model."""

    model_key: str = "class_prior_1x2_v1"
    model_family: str = "CLASS_PRIOR"
    version: str = "1.0.0"
    target_key: str = "match_result_1x2_v1"
    feature_set_key: str = "mvp_a_feature_set_v1"
    lifecycle_status: str = "EXPERIMENTAL"
    declared_capabilities: list[ModelCapabilityEnum] = [ModelCapabilityEnum.ONE_X_TWO]

    def __init__(self) -> None:
        self.artifact: TrainedModelArtifact | None = None

    def fit(
        self, training_rows: list[ModelingRowDTO], training_window: TrainingWindow | None = None
    ) -> TrainedModelArtifact:
        """Fits empirical 1X2 class prior probabilities strictly from training labels."""
        if not training_rows:
            raise ValueError("Cannot fit ClassPrior1X2Model on empty training rows.")

        total = len(training_rows)
        home_cnt = 0
        draw_cnt = 0
        away_cnt = 0

        for r in training_rows:
            target_val = r.targets.get("match_result_1x2_v1")
            if target_val == HOME_WIN_LABEL:
                home_cnt += 1
            elif target_val == DRAW_LABEL:
                draw_cnt += 1
            elif target_val == AWAY_WIN_LABEL:
                away_cnt += 1

        prob_home = round(home_cnt / total, 6)
        prob_draw = round(draw_cnt / total, 6)
        prob_away = round(away_cnt / total, 6)

        # Normalize to ensure sum equals exactly 1.0
        prob_sum = prob_home + prob_draw + prob_away
        if prob_sum > 0:
            prob_home = round(prob_home / prob_sum, 6)
            prob_draw = round(prob_draw / prob_sum, 6)
            prob_away = round(1.0 - (prob_home + prob_draw), 6)

        # Dummy preprocessor fitting to satisfy schema
        preprocessor = ModelPreprocessor(add_missing_indicators=False, scale_features=False)
        prep_art = preprocessor.fit(training_rows)

        if not training_window:
            training_window = TrainingWindow(
                row_count=total,
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
            hyperparameters={},
            weights_payload={
                "prob_home_win": prob_home,
                "prob_draw": prob_draw,
                "prob_away_win": prob_away,
                "sample_size": total,
            },
        )
        artifact.artifact_fingerprint = artifact.compute_fingerprint()
        self.artifact = artifact
        return self.artifact

    def predict_raw(self, row: ModelingRowDTO) -> ModelPredictionDTO:
        """Generates raw static class prior prediction."""
        if not self.artifact:
            raise RuntimeError("Model has not been fitted or loaded with an artifact.")

        if not self.artifact.verify_integrity():
            raise ValueError("Artifact fingerprint verification failed: payload has been tampered with.")

        if row.feature_set_key != self.artifact.feature_set_key:
            raise ValueError(f"Feature set mismatch: expected '{self.artifact.feature_set_key}', got '{row.feature_set_key}'")

        weights = self.artifact.weights_payload
        ph = float(weights["prob_home_win"])
        pd = float(weights["prob_draw"])
        pa = float(weights["prob_away_win"])

        return ModelPredictionDTO(
            match_id=row.match_id,
            model_key=self.model_key,
            model_version=self.version,
            model_artifact_fingerprint=self.artifact.artifact_fingerprint,
            feature_snapshot_fingerprint=row.feature_set_fingerprint,
            prob_home_win=ph,
            prob_draw=pd,
            prob_away_win=pa,
            raw_outputs={"class_prior_probabilities": [ph, pd, pa]},
            probability_status="RAW_UNCALIBRATED",
            lifecycle_status=self.lifecycle_status,
        )

    def predict_proba(self, row: ModelingRowDTO) -> dict[str, float]:
        """Returns 1X2 class prior probabilities dict."""
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
