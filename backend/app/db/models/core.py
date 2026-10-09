"""
Core Domain ORM Models
Competitions, Seasons, Teams, Matches, Match Statistics, and Audit Logs.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseMixin


class SystemAuditLog(Base, BaseMixin):
    """System-wide operational audit log."""
    __tablename__ = "system_audit_logs"

    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)


class Competition(Base, BaseMixin):
    """Canonical Competition/League entity."""
    __tablename__ = "competitions"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str] = mapped_column(String(50), nullable=False)
    competition_type: Mapped[str] = mapped_column(String(30), default="DOMESTIC_LEAGUE", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    seasons: Mapped[list[Season]] = relationship("Season", back_populates="competition", cascade="all, delete-orphan")


class Season(Base, BaseMixin):
    """Canonical Season entity independently bounded from competition names."""
    __tablename__ = "seasons"
    __table_args__ = (
        UniqueConstraint("competition_id", "season_year", name="uq_competition_season"),
    )

    competition_id: Mapped[UUID] = mapped_column(
        ForeignKey("competitions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    season_year: Mapped[str] = mapped_column(String(20), nullable=False)
    start_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    competition: Mapped[Competition] = relationship("Competition", back_populates="seasons")
    matches: Mapped[list[Match]] = relationship("Match", back_populates="season")


class Team(Base, BaseMixin):
    """Canonical Team entity."""
    __tablename__ = "teams"

    canonical_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    short_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    short_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    country: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    alias_mappings: Mapped[list[TeamAliasMapping]] = relationship("TeamAliasMapping", back_populates="team")


class TeamAliasMapping(Base, BaseMixin):
    """Mapping table for resolving raw team names to canonical team IDs."""
    __tablename__ = "team_alias_mappings"
    __table_args__ = (
        UniqueConstraint("provider_name", "raw_alias", name="uq_provider_team_alias"),
    )

    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)
    raw_alias: Mapped[str] = mapped_column(String(100), nullable=False)

    team: Mapped[Team] = relationship("Team", back_populates="alias_mappings")


class Match(Base, BaseMixin):
    """Canonical Match entity representing scheduled or completed football matches."""
    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint("home_team_id != away_team_id", name="chk_match_distinct_teams"),
        CheckConstraint("home_score >= 0 OR home_score IS NULL", name="chk_match_home_score_nonnegative"),
        CheckConstraint("away_score >= 0 OR away_score IS NULL", name="chk_match_away_score_nonnegative"),
    )

    season_id: Mapped[UUID] = mapped_column(
        ForeignKey("seasons.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    home_team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    away_team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="SCHEDULED", index=True)
    home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    half_time_home_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    half_time_away_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    season: Mapped[Season] = relationship("Season", back_populates="matches")
    home_team: Mapped[Team] = relationship("Team", foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship("Team", foreign_keys=[away_team_id])
    statistics: Mapped[list[MatchStatistic]] = relationship("MatchStatistic", back_populates="match", cascade="all, delete-orphan")


class MatchStatistic(Base, BaseMixin):
    """Match level aggregate team statistics (shots, corners, fouls, provider xG)."""
    __tablename__ = "match_statistics"
    __table_args__ = (
        UniqueConstraint("match_id", "team_id", name="uq_match_team_statistic"),
    )

    match_id: Mapped[UUID] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    shots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shots_on_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    corners: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fouls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    yellow_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    red_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_xg: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    match: Mapped[Match] = relationship("Match", back_populates="statistics")
    team: Mapped[Team] = relationship("Team")
