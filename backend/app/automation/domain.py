"""
Operational Automation Domain Types & DTOs (Sections 6, 12-14, 20, 40-42)
Defines execution modes, run statuses, due-work structures, and health diagnostics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class ExecutionMode(StrEnum):
    """Operational execution mode (Section 6)."""
    REPLAY_CERTIFICATION = "REPLAY_CERTIFICATION"
    LIVE_SHADOW = "LIVE_SHADOW"


class OperationalRunStatus(StrEnum):
    """Lifecycle statuses for operational runs (Section 14)."""
    STARTED = "STARTED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class OperationalHealthState(StrEnum):
    """
    Operational system health states (Section 40).
    STRICTLY SEPARATED from Phase 5.2 scientific model quality states.
    """
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    FAILED = "FAILED"


class DueWorkType(StrEnum):
    """Categories of deterministic due work (Section 20)."""
    FIXTURE_INGESTION_REFRESH = "FIXTURE_INGESTION_REFRESH"
    FEATURE_SNAPSHOT_MATERIALIZATION = "FEATURE_SNAPSHOT_MATERIALIZATION"
    SHADOW_PREDICTION_GENERATION = "SHADOW_PREDICTION_GENERATION"
    RESULT_SYNCHRONIZATION = "RESULT_SYNCHRONIZATION"
    POST_MATCH_SCORING = "POST_MATCH_SCORING"
    OBSERVATIONAL_MONITORING = "OBSERVATIONAL_MONITORING"


@dataclass
class DueWorkItem:
    """A single deterministic operational work unit."""
    work_type: DueWorkType
    fixture_id: UUID
    kickoff_utc: datetime
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class OperationalRunSummary:
    """Summary of an operational execution run."""
    run_id: UUID = field(default_factory=uuid4)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    scheduler_instance_id: str = "orchestrator-main"
    git_commit: str = "HEAD"
    pipeline_version: str = "1.0.0"
    execution_mode: ExecutionMode = ExecutionMode.REPLAY_CERTIFICATION
    trigger_type: str = "MANUAL"
    lease_id: UUID | None = None
    fencing_token: int | None = None
    provider_status: str = "PENDING"
    run_status: OperationalRunStatus = OperationalRunStatus.STARTED
    failure_code: str | None = None
    failure_summary: str | None = None

    # Granular counters
    fixtures_discovered: int = 0
    fixtures_refreshed: int = 0
    snapshots_created: int = 0
    snapshots_reused: int = 0
    snapshots_failed: int = 0
    predictions_created: int = 0
    predictions_reused: int = 0
    predictions_blocked: int = 0
    predictions_missed_window: int = 0
    predictions_failed: int = 0
    results_processed: int = 0
    evaluations_created: int = 0
    evaluations_reused: int = 0
    evaluations_failed: int = 0
    alerts_created: int = 0
    retry_count: int = 0

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthStatusDTO:
    """Operational health diagnostic DTO (Section 42)."""
    health_state: OperationalHealthState
    database_reachable: bool
    alembic_head_valid: bool
    scientific_manifests_valid: bool
    c1_available: bool
    m1_available: bool
    lease_active: bool
    current_fencing_token: int
    last_successful_run: datetime | None
    last_prediction_activity: datetime | None
    provider_configured: bool
    diagnostics: list[str] = field(default_factory=list)
