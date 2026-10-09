"""
Calibrated Model Wrapper
Wraps a raw IPredictionModel and applies a fitted ProbabilityCalibrator.
"""
import os
import json
from typing import Any
import numpy as np

from app.models.base import (
    IPredictionModel,
    ModelPredictionDTO,
    TrainedModelArtifact,
    TrainingWindow,
)
from app.models.dataset_dto import ModelingRowDTO
from app.models.calibration import ProbabilityCalibrator
from app.models.registry import global_model_registry

class CalibratedPredictionModel(IPredictionModel):
    model_family = "CALIBRATED_WRAPPER"
    model_key = "calibrated_prediction_wrapper_v1"

    def __init__(self, raw_model: IPredictionModel | None = None, version: str = "1.0.0"):
        self.version = version
        self.raw_model = raw_model
        self.calibrator = ProbabilityCalibrator()
        self.artifact: TrainedModelArtifact | None = None
        
        if self.raw_model:
            self.model_key = f"{self.raw_model.model_key}_calibrated"
            self.target_key = self.raw_model.target_key
            self.feature_set_key = self.raw_model.feature_set_key
            self.lifecycle_status = self.raw_model.lifecycle_status
        else:
            self.model_key = "unknown_calibrated"
            self.target_key = ""
            self.feature_set_key = ""
            self.lifecycle_status = "EXPERIMENTAL"

    def fit(self, training_rows: list[ModelingRowDTO], training_window: TrainingWindow | None = None) -> TrainedModelArtifact:
        raise NotImplementedError("CalibratedPredictionModel should be fitted via orchestration script with out-of-sample splits, not directly via fit().")

    def predict_raw(self, row: ModelingRowDTO) -> ModelPredictionDTO:
        if not self.artifact or not self.raw_model or not self.calibrator.is_fitted:
            raise RuntimeError("CalibratedPredictionModel is not fully fitted/loaded.")
        
        # Get raw prediction
        pred = self.raw_model.predict_raw(row)
        
        # Extract raw probabilities
        raw_probs = np.array([[pred.prob_home_win, pred.prob_draw, pred.prob_away_win]])
        
        # Apply calibration
        cal_probs = self.calibrator.calibrate(raw_probs)[0]
        
        # Map integer classes to string keys if necessary
        mapped_classes = []
        for cls in self.calibrator.model.classes_:
            if cls == 0: mapped_classes.append("HOME_WIN")
            elif cls == 1: mapped_classes.append("DRAW")
            elif cls == 2: mapped_classes.append("AWAY_WIN")
            else: mapped_classes.append(str(cls))
            
        cal_dict = {cls: float(prob) for cls, prob in zip(mapped_classes, cal_probs)}
        
        # Update DTO
        pred.calibrated_probabilities = cal_dict
        pred.prob_home_win = cal_dict.get("HOME_WIN", pred.prob_home_win)
        pred.prob_draw = cal_dict.get("DRAW", pred.prob_draw)
        pred.prob_away_win = cal_dict.get("AWAY_WIN", pred.prob_away_win)
        
        pred.probability_status = "CALIBRATED"
        pred.calibration_method = self.calibrator.method
        pred.calibration_artifact_fingerprint = self.artifact.artifact_fingerprint
        pred.model_key = self.model_key
        
        return pred

    def predict_proba(self, row: ModelingRowDTO) -> dict[str, float]:
        pred = self.predict_raw(row)
        return {
            "HOME_WIN": pred.prob_home_win,
            "DRAW": pred.prob_draw,
            "AWAY_WIN": pred.prob_away_win,
        }

    def save_artifact(self, filepath: str) -> None:
        if not self.artifact:
            raise RuntimeError("Cannot save un-fitted model artifact.")
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.artifact.model_dump_json(indent=2))

    def load_artifact(self, filepath: str) -> None:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.artifact = TrainedModelArtifact.model_validate(data)
        
        # Re-hydrate raw model
        raw_key = self.artifact.hyperparameters["raw_model_key"]
        raw_cls = global_model_registry.get_model_class(raw_key)
        self.raw_model = raw_cls()
        self.raw_model.artifact = TrainedModelArtifact.model_validate(self.artifact.hyperparameters["raw_artifact_payload"])
        
        # Re-hydrate calibrator
        self.calibrator.load_payload(self.artifact.weights_payload["calibrator"])
        
        self.model_key = self.artifact.model_key
        self.target_key = self.artifact.target_key
        self.feature_set_key = self.artifact.feature_set_key
        self.lifecycle_status = self.artifact.lifecycle_status

    def metadata(self) -> dict[str, Any]:
        return {
            "model_key": self.model_key,
            "model_family": self.model_family,
            "version": self.version,
            "target_key": self.target_key,
            "feature_set_key": self.feature_set_key,
            "lifecycle_status": self.lifecycle_status,
        }
