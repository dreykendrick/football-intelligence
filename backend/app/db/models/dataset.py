"""
Historical Dataset Release ORM Models
Dataset releases, explicit competition-season membership, match membership, and exclusion audit records.
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
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseMixin

if TYPE_CHECKING:
    from app.db.models.core import Competition, Match, Season, Team
    from app.db.models.mappings import IngestionBatch


class HistoricalDatasetRelease(Base, BaseMixin):
    """Immutable Historical Dataset Release Entity."""
    __tablename__ = "historical_dataset_releases"
    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_dataset_key_version"),
    )

    key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)
    selection_policy_key: Mapped[str] = mapped_column(String(100), nullable=False, default="mvp_a_recent_3_usable_seasons")
    selection_policy_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    total_competitions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_seasons: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_matches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dataset_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    quality_run_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    quality_status: Mapped[str] = mapped_column(String(30), nullable=False, default="UNKNOWN")
    identity_readiness_status: Mapped[str] = mapped_column(String(30), nullable=False, default="UNKNOWN")
    warning_acceptances: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_dataset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("historical_dataset_releases.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    seasons: Mapped[list[HistoricalDatasetSeason]] = relationship(
        "HistoricalDatasetSeason", back_populates="dataset_release", cascade="all, delete-orphan"
    )
    matches: Mapped[list[HistoricalDatasetMatch]] = relationship(
        "HistoricalDatasetMatch", back_populates="dataset_release", cascade="all, delete-orphan"
    )
    exclusions: Mapped[list[HistoricalDatasetExclusion]] = relationship(
        "HistoricalDatasetExclusion", back_populates="dataset_release", cascade="all, delete-orphan"
    )
    superseded_by: Mapped[list[HistoricalDatasetRelease]] = relationship(
        "HistoricalDatasetRelease", back_populates="supersedes_dataset"
    )
    supersedes_dataset: Mapped[HistoricalDatasetRelease | None] = relationship(
        "HistoricalDatasetRelease", remote_side="HistoricalDatasetRelease.id", back_populates="superseded_by"
    )


class HistoricalDatasetSeason(Base, BaseMixin):
    """Dataset Competition-Season Membership Entity."""
    __tablename__ = "historical_dataset_seasons"
    __table_args__ = (
        UniqueConstraint("dataset_release_id", "competition_id", "season_id", name="uq_dataset_comp_season"),
    )

    dataset_release_id: Mapped[UUID] = mapped_column(
        ForeignKey("historical_dataset_releases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competition_id: Mapped[UUID] = mapped_column(
        ForeignKey("competitions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    season_id: Mapped[UUID] = mapped_column(
        ForeignKey("seasons.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    competition_code: Mapped[str] = mapped_column(String(20), nullable=False)
    season_year: Mapped[str] = mapped_column(String(20), nullable=False)
    readiness_status: Mapped[str] = mapped_column(String(30), nullable=False)
    match_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expected_matches: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_provider_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    dataset_release: Mapped[HistoricalDatasetRelease] = relationship("HistoricalDatasetRelease", back_populates="seasons")
    competition: Mapped[Competition] = relationship("Competition")
    season: Mapped[Season] = relationship("Season")


class HistoricalDatasetMatch(Base, BaseMixin):
    """Dataset Match Membership Entity."""
    __tablename__ = "historical_dataset_matches"
    __table_args__ = (
        UniqueConstraint("dataset_release_id", "match_id", name="uq_dataset_match"),
    )

    dataset_release_id: Mapped[UUID] = mapped_column(
        ForeignKey("historical_dataset_releases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    match_id: Mapped[UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    competition_id: Mapped[UUID] = mapped_column(
        ForeignKey("competitions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    season_id: Mapped[UUID] = mapped_column(
        ForeignKey("seasons.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    home_team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    away_team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ingestion_batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ingestion_batches.id", ondelete="SET NULL"), nullable=True
    )
    raw_source_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)

    dataset_release: Mapped[HistoricalDatasetRelease] = relationship("HistoricalDatasetRelease", back_populates="matches")
    match: Mapped[Match] = relationship("Match")
    competition: Mapped[Competition] = relationship("Competition")
    season: Mapped[Season] = relationship("Season")
    home_team: Mapped[Team] = relationship("Team", foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship("Team", foreign_keys=[away_team_id])
    ingestion_batch: Mapped[IngestionBatch | None] = relationship("IngestionBatch")


class HistoricalDatasetExclusion(Base, BaseMixin):
    """Dataset Excluded Match Audit Entity."""
    __tablename__ = "historical_dataset_exclusions"

    dataset_release_id: Mapped[UUID] = mapped_column(
        ForeignKey("historical_dataset_releases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    match_id: Mapped[UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    competition_code: Mapped[str] = mapped_column(String(20), nullable=False)
    season_year: Mapped[str] = mapped_column(String(20), nullable=False)
    exclusion_reason: Mapped[str] = mapped_column(String(255), nullable=False)
    quality_rule_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metadata_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    dataset_release: Mapped[HistoricalDatasetRelease] = relationship("HistoricalDatasetRelease", back_populates="exclusions")
    match: Mapped[Match] = relationship("Match")
