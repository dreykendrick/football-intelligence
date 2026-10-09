"""
Prediction Snapshot ORM Models
Append-only immutable prediction snapshots, probability constraints, goal expectations, and prediction corrections.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseMixin

if TYPE_CHECKING:
    from app.db.models.core import Match
    from app.db.models.features import FeatureSnapshot
    from app.db.models.models import ModelVersion


class PredictionSnapshot(Base, BaseMixin):
    """Immutable Pre-Match Prediction Snapshot Entity."""
    __tablename__ = "prediction_snapshots"
    __table_args__ = (
        CheckConstraint("prob_home_win >= 0 AND prob_home_win <= 1", name="chk_pred_prob_home_win_range"),
        CheckConstraint("prob_draw >= 0 AND prob_draw <= 1", name="chk_pred_prob_draw_range"),
        CheckConstraint("prob_away_win >= 0 AND prob_away_win <= 1", name="chk_pred_prob_away_win_range"),
        CheckConstraint("abs(prob_home_win + prob_draw + prob_away_win - 1.0) <= 0.01", name="chk_pred_prob_sum_unity"),
        CheckConstraint("prob_over_25 >= 0 AND prob_over_25 <= 1 OR prob_over_25 IS NULL", name="chk_pred_prob_over_25_range"),
        CheckConstraint("prob_under_25 >= 0 AND prob_under_25 <= 1 OR prob_under_25 IS NULL", name="chk_pred_prob_under_25_range"),
        CheckConstraint("prob_btts_yes >= 0 AND prob_btts_yes <= 1 OR prob_btts_yes IS NULL", name="chk_pred_prob_btts_yes_range"),
        CheckConstraint("prob_btts_no >= 0 AND prob_btts_no <= 1 OR prob_btts_no IS NULL", name="chk_pred_prob_btts_no_range"),
    )

    match_id: Mapped[UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    model_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    feature_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("feature_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    snapshot_type: Mapped[str] = mapped_column(String(20), nullable=False, default="FINAL", index=True)
    prediction_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )
    target_kickoff_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    prediction_horizon_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Core Probabilities (NUMERIC 6,5)
    prob_home_win: Mapped[float] = mapped_column(Numeric(6, 5), nullable=False)
    prob_draw: Mapped[float] = mapped_column(Numeric(6, 5), nullable=False)
    prob_away_win: Mapped[float] = mapped_column(Numeric(6, 5), nullable=False)

    # Poisson Expected Goals
    predicted_home_goals: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    predicted_away_goals: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    # Secondary Probabilities
    prob_over_25: Mapped[float | None] = mapped_column(Numeric(6, 5), nullable=True)
    prob_under_25: Mapped[float | None] = mapped_column(Numeric(6, 5), nullable=True)
    prob_btts_yes: Mapped[float | None] = mapped_column(Numeric(6, 5), nullable=True)
    prob_btts_no: Mapped[float | None] = mapped_column(Numeric(6, 5), nullable=True)

    # Uncertainty & Quality Indicators
    data_quality_score: Mapped[float | None] = mapped_column(Numeric(6, 5), nullable=True)
    prediction_uncertainty: Mapped[float | None] = mapped_column(Numeric(6, 5), nullable=True)
    explainability_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Prediction Superceding & Correction Support
    supersedes_prediction_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("prediction_snapshots.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    correction_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    match: Mapped[Match] = relationship("Match")
    model_version: Mapped[ModelVersion] = relationship("ModelVersion")
    feature_snapshot: Mapped[FeatureSnapshot] = relationship("FeatureSnapshot")
    superseded_prediction: Mapped[PredictionSnapshot | None] = relationship("PredictionSnapshot", remote_side="PredictionSnapshot.id")
