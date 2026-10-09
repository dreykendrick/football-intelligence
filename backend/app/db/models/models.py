"""
Model Registry & Versioning ORM Models
Logical models, model versions, hyperparameters, and lifecycle history audit records.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseMixin

if TYPE_CHECKING:
    from app.db.models.features import FeatureSet


class Model(Base, BaseMixin):
    """Logical Model entity catalog."""
    __tablename__ = "models"

    model_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_family: Mapped[str] = mapped_column(String(50), nullable=False, default="POISSON")
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    versions: Mapped[list[ModelVersion]] = relationship("ModelVersion", back_populates="model")


class ModelVersion(Base, BaseMixin):
    """Immutable Model Version implementation entity."""
    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("model_id", "version", name="uq_model_version"),
    )

    model_id: Mapped[UUID] = mapped_column(
        ForeignKey("models.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(20), nullable=False, default="EXPERIMENTAL", index=True)
    feature_set_id: Mapped[UUID] = mapped_column(
        ForeignKey("feature_sets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    training_start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    training_end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hyperparameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    code_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)

    model: Mapped[Model] = relationship("Model", back_populates="versions")
    feature_set: Mapped[FeatureSet] = relationship("FeatureSet")
    lifecycle_history: Mapped[list[ModelLifecycleHistory]] = relationship("ModelLifecycleHistory", back_populates="model_version")


class ModelLifecycleHistory(Base, BaseMixin):
    """Audit log of model lifecycle status transitions."""
    __tablename__ = "model_lifecycle_history"

    model_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    previous_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    model_version: Mapped[ModelVersion] = relationship("ModelVersion", back_populates="lifecycle_history")
