"""
Operational Automation & Scheduler ORM Models (Sprint 7.1)
Durable tables for distributed scheduler leases, operational runs, and classified failure records.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseMixin


class SchedulerLease(Base, BaseMixin):
    """
    Distributed scheduler lease with monotonic fencing token, heartbeat, and automatic expiry.
    Protects against split-brain execution and dead worker stalling.
    """
    __tablename__ = "scheduler_leases"

    lease_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    lease_owner: Mapped[str] = mapped_column(String(100), nullable=False)
    fencing_token: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    lease_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    runs: Mapped[list[OperationalRun]] = relationship("OperationalRun", back_populates="lease")


class OperationalRun(Base, BaseMixin):
    """
    Durable operational run/attempt record tracking orchestration metrics, execution mode,
    fencing token, and run status.
    """
    __tablename__ = "operational_runs"

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduler_instance_id: Mapped[str] = mapped_column(String(100), nullable=False)
    git_commit: Mapped[str] = mapped_column(String(40), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(20), default="1.0.0", nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(30), default="REPLAY_CERTIFICATION", nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(50), default="MANUAL", nullable=False)

    lease_id: Mapped[UUID | None] = mapped_column(ForeignKey("scheduler_leases.id"), nullable=True)
    fencing_token: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    provider_status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)

    fixtures_discovered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fixtures_refreshed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    snapshots_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    snapshots_reused: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    snapshots_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    predictions_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    predictions_reused: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    predictions_blocked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    predictions_missed_window: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    predictions_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    results_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    evaluations_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    evaluations_reused: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    evaluations_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    alerts_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    run_status: Mapped[str] = mapped_column(String(30), default="STARTED", nullable=False, index=True)
    failure_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    failure_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    lease: Mapped[SchedulerLease | None] = relationship("SchedulerLease", back_populates="runs")
    failures: Mapped[list[OperationalFailure]] = relationship("OperationalFailure", back_populates="run")


class OperationalFailure(Base, BaseMixin):
    """
    Classified operational failure record separating error category from retryability.
    """
    __tablename__ = "operational_failures"

    run_id: Mapped[UUID | None] = mapped_column(ForeignKey("operational_runs.id"), nullable=True)
    component: Mapped[str] = mapped_column(String(50), nullable=False)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    error_category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    retryability: Mapped[str] = mapped_column(String(20), default="PERMANENT", nullable=False)
    failure_code: Mapped[str] = mapped_column(String(50), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)

    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_failure_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    last_failure_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    run: Mapped[OperationalRun | None] = relationship("OperationalRun", back_populates="failures")
