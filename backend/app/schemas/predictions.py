"""
Prediction Snapshot Pydantic Schemas
Validation DTOs for Pre-Match Probability and Uncertainty Snapshots.
"""
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PredictionSnapshotBase(BaseModel):
    snapshot_type: str = "FINAL"
    target_kickoff_timestamp: datetime
    prediction_horizon_seconds: int | None = None

    prob_home_win: float = Field(..., ge=0.0, le=1.0)
    prob_draw: float = Field(..., ge=0.0, le=1.0)
    prob_away_win: float = Field(..., ge=0.0, le=1.0)

    predicted_home_goals: float | None = None
    predicted_away_goals: float | None = None

    prob_over_25: float | None = Field(None, ge=0.0, le=1.0)
    prob_under_25: float | None = Field(None, ge=0.0, le=1.0)
    prob_btts_yes: float | None = Field(None, ge=0.0, le=1.0)
    prob_btts_no: float | None = Field(None, ge=0.0, le=1.0)

    data_quality_score: float | None = Field(None, ge=0.0, le=1.0)
    prediction_uncertainty: float | None = Field(None, ge=0.0, le=1.0)
    explainability_payload: dict[str, Any] | None = None

    @field_validator("prob_away_win")
    @classmethod
    def validate_probabilities_sum(cls, v: float, info: Any) -> float:
        home = info.data.get("prob_home_win", 0.0)
        draw = info.data.get("prob_draw", 0.0)
        total = home + draw + v
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"1X2 probabilities must sum to 1.0 (got {total:.5f})")
        return v


class PredictionSnapshotCreate(PredictionSnapshotBase):
    match_id: UUID
    model_version_id: UUID
    feature_snapshot_id: UUID
    supersedes_prediction_id: UUID | None = None
    correction_reason: str | None = None


class PredictionSnapshotResponse(PredictionSnapshotBase):
    id: UUID
    match_id: UUID
    model_version_id: UUID
    feature_snapshot_id: UUID
    prediction_timestamp: datetime
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
