"""Sprint 7.1 Operational Automation, Scheduling, Leases & Reliability Schema

Revision ID: 20261023_0006
Revises: 20261016_0005
Create Date: 2026-10-23 08:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261023_0006"
down_revision: str | None = "20261016_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Scheduler Leases
    op.create_table(
        "scheduler_leases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("lease_name", sa.String(length=64), nullable=False),
        sa.Column("lease_owner", sa.String(length=100), nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("lease_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lease_name", name="uq_scheduler_leases_name"),
    )
    op.create_index("ix_scheduler_leases_lease_name", "scheduler_leases", ["lease_name"])
    op.create_index("ix_scheduler_leases_expires_at", "scheduler_leases", ["expires_at"])

    # 2. Operational Runs
    op.create_table(
        "operational_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduler_instance_id", sa.String(length=100), nullable=False),
        sa.Column("git_commit", sa.String(length=40), nullable=False),
        sa.Column("pipeline_version", sa.String(length=20), nullable=False, server_default="1.0.0"),
        sa.Column("execution_mode", sa.String(length=30), nullable=False, server_default="REPLAY_CERTIFICATION"),
        sa.Column("trigger_type", sa.String(length=50), nullable=False, server_default="MANUAL"),
        sa.Column("lease_id", sa.UUID(), nullable=True),
        sa.Column("fencing_token", sa.BigInteger(), nullable=True),
        sa.Column("provider_status", sa.String(length=50), nullable=False, server_default="PENDING"),
        sa.Column("fixtures_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fixtures_refreshed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshots_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshots_reused", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshots_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("predictions_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("predictions_reused", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("predictions_blocked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("predictions_missed_window", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("predictions_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("results_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evaluations_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evaluations_reused", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evaluations_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("alerts_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("run_status", sa.String(length=30), nullable=False, server_default="STARTED"),
        sa.Column("failure_code", sa.String(length=50), nullable=True),
        sa.Column("failure_summary", sa.Text(), nullable=True),
        sa.Column("run_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["lease_id"], ["scheduler_leases.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_operational_runs_started_at", "operational_runs", ["started_at"])
    op.create_index("ix_operational_runs_run_status", "operational_runs", ["run_status"])

    # 3. Operational Failures
    op.create_table(
        "operational_failures",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=True),
        sa.Column("component", sa.String(length=50), nullable=False),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("error_category", sa.String(length=50), nullable=False),
        sa.Column("retryability", sa.String(length=20), nullable=False, server_default="PERMANENT"),
        sa.Column("failure_code", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_failure_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["run_id"], ["operational_runs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_operational_failures_error_category", "operational_failures", ["error_category"])
    op.create_index("ix_operational_failures_run_id", "operational_failures", ["run_id"])


def downgrade() -> None:
    op.drop_table("operational_failures")
    op.drop_table("operational_runs")
    op.drop_table("scheduler_leases")
