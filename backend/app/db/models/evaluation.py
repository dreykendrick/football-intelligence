"""
Backtest & Evaluation ORM Models
Backtest runs, evaluation runs, metric key-value records, and data quality issue logs.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseMixin

if TYPE_CHECKING:
    from app.db.models.features import FeatureSet
    from app.db.models.models import ModelVersion


class BacktestRun(Base, BaseMixin):
    """Chronological Backtest Execution Run Entity."""
    __tablename__ = "backtest_runs"

    model_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    feature_set_id: Mapped[UUID] = mapped_column(
        ForeignKey("feature_sets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    competition_scope: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    training_start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    training_end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    test_start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    test_end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    configuration: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    code_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)

    model_version: Mapped[ModelVersion] = relationship("ModelVersion")
    feature_set: Mapped[FeatureSet] = relationship("FeatureSet")
    evaluation_runs: Mapped[list[EvaluationRun]] = relationship("EvaluationRun", back_populates="backtest_run")


class EvaluationRun(Base, BaseMixin):
    """Model Evaluation Run Execution Entity."""
    __tablename__ = "evaluation_runs"

    model_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    backtest_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("backtest_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    competition_scope: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    season_scope: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prediction_horizon: Mapped[str | None] = mapped_column(String(20), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    sample_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    configuration: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    model_version: Mapped[ModelVersion] = relationship("ModelVersion")
    backtest_run: Mapped[BacktestRun | None] = relationship("BacktestRun", back_populates="evaluation_runs")
    metrics: Mapped[list[EvaluationMetric]] = relationship("EvaluationMetric", back_populates="evaluation_run", cascade="all, delete-orphan")


class EvaluationMetric(Base, BaseMixin):
    """Extensible Evaluation Metric Store Entity."""
    __tablename__ = "evaluation_metrics"

    evaluation_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    metric_value: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    scope_category: Mapped[str] = mapped_column(String(50), nullable=False, default="OVERALL", index=True)
    metadata_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    evaluation_run: Mapped[EvaluationRun] = relationship("EvaluationRun", back_populates="metrics")


class DataQualityLog(Base, BaseMixin):
    """Data Quality Assessment & Finding Entity."""
    __tablename__ = "data_quality_logs"

    match_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("matches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    feature_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("feature_snapshots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    quality_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    rule_key: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="WARNING", index=True)
    quality_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    issue_key: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    competition_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    season_year: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    resolution_status: Mapped[str] = mapped_column(String(30), nullable=False, default="OPEN", index=True)
    resolution_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
