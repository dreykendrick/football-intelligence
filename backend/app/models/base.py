"""
Core Prediction Model Interfaces, DTOs & Serialization Architecture
Defines IPredictionModel abstract contract, ModelPredictionDTO, TrainingWindow, and TrainedModelArtifact structures.
"""
from __future__ import annotations

import abc
import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.dataset_dto import ModelingRowDTO
from app.models.preprocessing import PreprocessingArtifact


class TrainingWindow(BaseModel):
    """Metadata specification describing the explicit historical interval used during model fitting."""

    start_date: datetime | None = None
    end_date: datetime | None = None
    competitions: list[str] = Field(default_factory=list)
    seasons: list[str] = Field(default_factory=list)
    row_count: int = 0
    modeling_dataset_key: str = "mvp_a_modeling_dataset_v1"
    modeling_dataset_fingerprint: str = ""


class ModelPredictionDTO(BaseModel):
    """Immutable output container for a model's pre-match raw prediction."""

    match_id: UUID
    model_key: str
    model_version: str
    model_artifact_fingerprint: str
    feature_snapshot_fingerprint: str
    prediction_timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    prediction_horizon: str = "FINAL_PREMATCH"

    # Core Probabilities (0.0 to 1.0)
    prob_home_win: float
    prob_draw: float
    prob_away_win: float

    # Expected Goals (Poisson / Score Models)
    predicted_home_goals: float | None = None
    predicted_away_goals: float | None = None

    # Secondary Probabilities
    prob_over_25: float | None = None
    prob_under_25: float | None = None
    prob_btts_yes: float | None = None
    prob_btts_no: float | None = None

    # Raw Outputs Payload & Status Metadata
    raw_outputs: dict[str, Any] = Field(default_factory=dict)
    probability_status: str = "RAW_UNCALIBRATED"
    lifecycle_status: str = "EXPERIMENTAL"
    
    # Calibration
    calibrated_probabilities: dict[str, float] = Field(default_factory=dict)
    calibration_method: str | None = None
    calibration_artifact_fingerprint: str | None = None

    @property
    def most_likely_outcome(self) -> str:
        """Returns the outcome key with the highest estimated probability (tie-breaking: HOME_WIN, DRAW, AWAY_WIN)."""
        probs = [
            (self.prob_home_win, 0, "HOME_WIN"),
            (self.prob_draw, 1, "DRAW"),
            (self.prob_away_win, 2, "AWAY_WIN"),
        ]
        # Sort descending by probability, then ascending by tie-breaker index
        probs.sort(key=lambda x: (-x[0], x[1]))
        return probs[0][2]

    @property
    def margin_between_top_outcomes(self) -> float:
        """Returns difference between the highest and second-highest estimated probabilities."""
        sorted_probs = sorted([self.prob_home_win, self.prob_draw, self.prob_away_win], reverse=True)
        return round(sorted_probs[0] - sorted_probs[1], 6)



class TrainedModelArtifact(BaseModel):
    """Immutable, serializable metadata and state payload for a fitted model artifact."""

    model_key: str
    model_family: str
    version: str = "1.0.0"
    target_key: str
    feature_set_key: str = "mvp_a_feature_set_v1"
    lifecycle_status: str = "EXPERIMENTAL"
    evaluation_status: str = "NOT_PERFORMED"
    calibration_status: str = "NOT_PERFORMED"
    training_window: TrainingWindow
    preprocessor_artifact: PreprocessingArtifact
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    weights_payload: dict[str, Any] = Field(default_factory=dict)
    artifact_fingerprint: str = ""

    def compute_fingerprint(self) -> str:
        """Computes deterministic SHA-256 fingerprint of model configuration and weights state."""
        w_json = json.dumps(self.weights_payload, sort_keys=True)
        w_hash = hashlib.sha256(w_json.encode("utf-8")).hexdigest()[:12]
        raw = (
            f"{self.model_key}:{self.version}:{self.target_key}:{self.feature_set_key}:"
            f"{self.training_window.modeling_dataset_fingerprint}:{self.preprocessor_artifact.fingerprint}:{w_hash}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def verify_integrity(self) -> bool:
        """Verifies that the stored artifact_fingerprint matches the computed fingerprint."""
        if not self.artifact_fingerprint:
            return True
        return self.artifact_fingerprint == self.compute_fingerprint()



from enum import Enum

class ModelCapabilityEnum(str, Enum):
    EXPECTED_GOALS = "EXPECTED_GOALS"
    EXACT_SCORE = "EXACT_SCORE"
    ONE_X_TWO = "ONE_X_TWO"
    BTTS = "BTTS"
    OVER_UNDER = "OVER_UNDER"


class OneXTwoProbabilityDTO(BaseModel):
    home_win: float
    draw: float
    away_win: float
    probability_status: str = "RAW_UNCALIBRATED"
    source_model: str = ""


class BTTSProbabilityDTO(BaseModel):
    yes: float
    no: float
    probability_status: str = "RAW_UNCALIBRATED"


class OverUnderProbabilityDTO(BaseModel):
    line: float = 2.5
    over: float
    under: float
    probability_status: str = "RAW_UNCALIBRATED"


class MatchProbabilityPrediction(BaseModel):
    match_id: UUID
    model_key: str
    model_version: str
    model_artifact_fingerprint: str
    feature_set_key: str = "mvp_a_feature_set_v1"
    feature_snapshot_fingerprint: str
    lambda_home: float | None = None
    lambda_away: float | None = None
    one_x_two: OneXTwoProbabilityDTO
    btts: BTTSProbabilityDTO | None = None
    over_under_2_5: OverUnderProbabilityDTO | None = None
    most_likely_score: tuple[int, int] | None = None
    top_exact_scores: list[dict[str, Any]] = Field(default_factory=list)
    distribution_metadata: dict[str, Any] = Field(default_factory=dict)
    probability_status: str = "RAW_UNCALIBRATED"
    lifecycle_status: str = "EXPERIMENTAL"
    prediction_horizon: str = "FINAL_PREMATCH"


class IPredictionModel(abc.ABC):
    """Abstract Interface Contract for all Phase 4 statistical prediction models."""

    model_key: str
    model_family: str
    version: str = "1.0.0"
    target_key: str
    feature_set_key: str = "mvp_a_feature_set_v1"
    lifecycle_status: str = "EXPERIMENTAL"
    declared_capabilities: list[ModelCapabilityEnum] = [ModelCapabilityEnum.ONE_X_TWO]

    @property
    def capabilities(self) -> list[ModelCapabilityEnum]:
        """Returns model capabilities."""
        caps = getattr(self, "declared_capabilities", None)
        if isinstance(caps, list):
            return caps
        return [ModelCapabilityEnum.ONE_X_TWO]

    @abc.abstractmethod
    def fit(
        self, training_rows: list[ModelingRowDTO], training_window: TrainingWindow | None = None
    ) -> TrainedModelArtifact:
        """Fits model parameters strictly using training rows."""
        pass

    @abc.abstractmethod
    def predict_raw(self, row: ModelingRowDTO) -> ModelPredictionDTO:
        """Generates raw uncalibrated prediction outputs for a target match row."""
        pass

    @abc.abstractmethod
    def predict_proba(self, row: ModelingRowDTO) -> dict[str, float]:
        """Returns dictionary of raw probabilities for the primary target."""
        pass

    def predict_proba_vector(self, row: ModelingRowDTO) -> list[float]:
        """Returns list of canonical 1X2 probabilities [P(Home Win), P(Draw), P(Away Win)]."""
        p_dict = self.predict_proba(row)
        return [
            float(p_dict.get("HOME_WIN", 0.0)),
            float(p_dict.get("DRAW", 0.0)),
            float(p_dict.get("AWAY_WIN", 0.0)),
        ]

    @abc.abstractmethod
    def save_artifact(self, filepath: str) -> None:
        """Serializes model artifact state to disk."""
        pass

    @abc.abstractmethod
    def load_artifact(self, filepath: str) -> None:
        """Deserializes model artifact state from disk."""
        pass

    def metadata(self) -> dict[str, Any]:
        """Returns model identity and specification metadata."""
        return {
            "model_key": self.model_key,
            "model_family": self.model_family,
            "version": self.version,
            "target_key": self.target_key,
            "feature_set_key": self.feature_set_key,
            "lifecycle_status": self.lifecycle_status,
            "capabilities": [c.value for c in self.capabilities],
            "evaluation_status": "NOT_PERFORMED",
            "calibration_status": "NOT_PERFORMED",
        }
