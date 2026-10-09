"""
Feature Engineering ORM Models
Feature definitions, feature sets, feature set compositions, and immutable pre-match feature snapshots.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseMixin

if TYPE_CHECKING:
    from app.db.models.core import Match


class FeatureDefinition(Base, BaseMixin):
    """Metadata catalog for calculated statistical and contextual features."""
    __tablename__ = "feature_definitions"

    feature_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data_type: Mapped[str] = mapped_column(String(30), nullable=False, default="FLOAT")
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="STRENGTH", index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class FeatureSet(Base, BaseMixin):
    """Versioned collection of features utilized by a predictive model."""
    __tablename__ = "feature_sets"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_feature_set_name_version"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    features: Mapped[list[FeatureSetFeature]] = relationship("FeatureSetFeature", back_populates="feature_set", cascade="all, delete-orphan")


class FeatureSetFeature(Base, BaseMixin):
    """Junction table associating FeatureSets with FeatureDefinitions."""
    __tablename__ = "feature_set_features"
    __table_args__ = (
        UniqueConstraint("feature_set_id", "feature_definition_id", name="uq_feature_set_feature"),
    )

    feature_set_id: Mapped[UUID] = mapped_column(
        ForeignKey("feature_sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    feature_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("feature_definitions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    feature_set: Mapped[FeatureSet] = relationship("FeatureSet", back_populates="features")
    feature_definition: Mapped[FeatureDefinition] = relationship("FeatureDefinition")


class FeatureSnapshot(Base, BaseMixin):
    """Immutable pre-match calculated feature snapshot payload."""
    __tablename__ = "feature_snapshots"
    __table_args__ = (
        UniqueConstraint("match_id", "feature_set_id", "snapshot_type", name="uq_match_feature_snapshot_type"),
    )

    match_id: Mapped[UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    feature_set_id: Mapped[UUID] = mapped_column(
        ForeignKey("feature_sets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    snapshot_type: Mapped[str] = mapped_column(String(20), nullable=False, default="FINAL", index=True)
    feature_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    cutoff_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    feature_values: Mapped[dict] = mapped_column(JSON, nullable=False)
    missing_features: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    data_quality_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    match: Mapped[Match] = relationship("Match")
    feature_set: Mapped[FeatureSet] = relationship("FeatureSet")
