"""
Provider Entity Mappings & Ingestion Batch Models
Provider sources, batch ingestion tracking, provider entity mapping tables, and raw source audit records.
"""
from __future__ import annotations

from datetime import UTC, datetime
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
    from app.db.models.core import Competition, Match, Season, Team


class Provider(Base, BaseMixin):
    """External Data Provider definition entity."""
    __tablename__ = "providers"

    provider_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(30), nullable=False, default="HISTORICAL_CSV")
    base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    batches: Mapped[list[IngestionBatch]] = relationship("IngestionBatch", back_populates="provider")


class IngestionBatch(Base, BaseMixin):
    """Ingestion Operation Batch Record."""
    __tablename__ = "ingestion_batches"

    provider_id: Mapped[UUID] = mapped_column(
        ForeignKey("providers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    provider: Mapped[Provider] = relationship("Provider", back_populates="batches")
    raw_records: Mapped[list[RawSourceRecord]] = relationship("RawSourceRecord", back_populates="ingestion_batch")


class ProviderCompetitionMapping(Base, BaseMixin):
    """Provider-specific competition mapping."""
    __tablename__ = "provider_competition_mappings"
    __table_args__ = (
        UniqueConstraint("provider_id", "external_code", name="uq_provider_competition_code"),
    )

    provider_id: Mapped[UUID] = mapped_column(
        ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competition_id: Mapped[UUID] = mapped_column(
        ForeignKey("competitions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    external_competition_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_code: Mapped[str] = mapped_column(String(50), nullable=False)

    provider: Mapped[Provider] = relationship("Provider")
    competition: Mapped[Competition] = relationship("Competition")


class ProviderSeasonMapping(Base, BaseMixin):
    """Provider-specific season mapping."""
    __tablename__ = "provider_season_mappings"
    __table_args__ = (
        UniqueConstraint("provider_id", "external_season_id", name="uq_provider_season"),
    )

    provider_id: Mapped[UUID] = mapped_column(
        ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    season_id: Mapped[UUID] = mapped_column(
        ForeignKey("seasons.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    external_season_id: Mapped[str] = mapped_column(String(100), nullable=False)

    provider: Mapped[Provider] = relationship("Provider")
    season: Mapped[Season] = relationship("Season")


class ProviderTeamMapping(Base, BaseMixin):
    """Provider-specific team mapping."""
    __tablename__ = "provider_team_mappings"
    __table_args__ = (
        UniqueConstraint("provider_id", "raw_alias", name="uq_provider_team_raw_alias"),
    )

    provider_id: Mapped[UUID] = mapped_column(
        ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    external_team_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    raw_alias: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_alias: Mapped[str | None] = mapped_column(String(100), nullable=True)

    provider: Mapped[Provider] = relationship("Provider")
    team: Mapped[Team] = relationship("Team")


class ProviderMatchMapping(Base, BaseMixin):
    """Provider-specific match mapping."""
    __tablename__ = "provider_match_mappings"
    __table_args__ = (
        UniqueConstraint("provider_id", "external_match_id", name="uq_provider_match"),
    )

    provider_id: Mapped[UUID] = mapped_column(
        ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    match_id: Mapped[UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_match_id: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_match_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    provider: Mapped[Provider] = relationship("Provider")
    match: Mapped[Match] = relationship("Match")


class RawSourceRecord(Base, BaseMixin):
    """Raw Source Payload Preservation Entity."""
    __tablename__ = "raw_source_records"

    provider_id: Mapped[UUID] = mapped_column(
        ForeignKey("providers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ingestion_batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ingestion_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processing_status: Mapped[str] = mapped_column(String(20), default="PROCESSED", nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    provider: Mapped[Provider] = relationship("Provider")
    ingestion_batch: Mapped[IngestionBatch] = relationship("IngestionBatch", back_populates="raw_records")
