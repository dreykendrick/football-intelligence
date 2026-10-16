"""Sprint 6.3 Live Shadow Prediction Pipeline Relational Schema

Revision ID: 20261016_0005
Revises: 20260904_0004
Create Date: 2026-10-16 02:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261016_0005"
down_revision: str | None = "20260904_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Shadow Prediction Runs
    op.create_table(
        "shadow_prediction_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="SUCCESS"),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("eligible_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("predicted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fallback_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("run_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shadow_prediction_runs_status", "shadow_prediction_runs", ["status"])
    op.create_index("ix_shadow_prediction_runs_started_at", "shadow_prediction_runs", ["started_at"])

    # 2. Shadow Predictions
    op.create_table(
        "shadow_predictions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("fixture_id", sa.UUID(), nullable=False),
        sa.Column("prediction_run_id", sa.UUID(), nullable=True),
        sa.Column("prediction_mode", sa.String(length=20), nullable=False, server_default="SHADOW"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lead_time_seconds", sa.Integer(), nullable=False),
        sa.Column("feature_snapshot_id", sa.UUID(), nullable=True),
        sa.Column("feature_snapshot_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("history_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("phase5_manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("phase5_2_policy_hash", sa.String(length=64), nullable=False),
        sa.Column("phase6_1_manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("phase6_2_manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("c1_model_key", sa.String(length=50), nullable=False),
        sa.Column("c1_model_version", sa.String(length=20), nullable=False),
        sa.Column("c1_artifact_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("m1_model_key", sa.String(length=50), nullable=False),
        sa.Column("m1_model_version", sa.String(length=20), nullable=False),
        sa.Column("m1_artifact_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("prob_home", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("prob_draw", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("prob_away", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("structural_prob_home", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("structural_prob_draw", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("structural_prob_away", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("lambda_home", sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column("lambda_away", sa.Numeric(precision=6, scale=3), nullable=False),
        sa.Column("btts_yes", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("btts_no", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("over_2_5", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("under_2_5", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("exact_score_matrix_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("top_scorelines", sa.JSON(), nullable=False),
        sa.Column("quality_state", sa.String(length=50), nullable=False),
        sa.Column("quality_reasons", sa.JSON(), nullable=True),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fallback_model", sa.String(length=50), nullable=True),
        sa.Column("fallback_reason", sa.String(length=255), nullable=True),
        sa.Column("model_disagreement_value", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("model_disagreement_band", sa.String(length=20), nullable=False),
        sa.Column("is_canonical_evaluation_prediction", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("prediction_schema_version", sa.String(length=20), nullable=False, server_default="1.0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("prob_home >= 0 AND prob_home <= 1", name="chk_shadow_prob_home"),
        sa.CheckConstraint("prob_draw >= 0 AND prob_draw <= 1", name="chk_shadow_prob_draw"),
        sa.CheckConstraint("prob_away >= 0 AND prob_away <= 1", name="chk_shadow_prob_away"),
        sa.CheckConstraint("abs(prob_home + prob_draw + prob_away - 1.0) <= 0.01", name="chk_shadow_prob_sum"),
        sa.CheckConstraint("abs(btts_yes + btts_no - 1.0) <= 0.01", name="chk_shadow_btts_sum"),
        sa.CheckConstraint("abs(over_2_5 + under_2_5 - 1.0) <= 0.01", name="chk_shadow_ou25_sum"),
        sa.ForeignKeyConstraint(["fixture_id"], ["matches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["prediction_run_id"], ["shadow_prediction_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["feature_snapshot_id"], ["feature_snapshots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shadow_predictions_fixture_id", "shadow_predictions", ["fixture_id"])
    op.create_index("ix_shadow_predictions_generated_at", "shadow_predictions", ["generated_at"])
    op.create_index("ix_shadow_predictions_kickoff_utc", "shadow_predictions", ["kickoff_utc"])
    op.create_index("ix_shadow_predictions_quality_state", "shadow_predictions", ["quality_state"])
    op.create_index("ix_shadow_predictions_canonical", "shadow_predictions", ["is_canonical_evaluation_prediction"])

    # 3. Shadow Evaluations
    op.create_table(
        "shadow_evaluations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("prediction_id", sa.UUID(), nullable=False),
        sa.Column("fixture_id", sa.UUID(), nullable=False),
        sa.Column("result_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("result_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_home_goals", sa.Integer(), nullable=False),
        sa.Column("actual_away_goals", sa.Integer(), nullable=False),
        sa.Column("actual_1x2", sa.String(length=10), nullable=False),
        sa.Column("actual_btts", sa.Boolean(), nullable=False),
        sa.Column("actual_over_2_5", sa.Boolean(), nullable=False),
        sa.Column("log_loss_1x2", sa.Numeric(precision=8, scale=5), nullable=False),
        sa.Column("brier_1x2", sa.Numeric(precision=8, scale=5), nullable=False),
        sa.Column("btts_log_loss", sa.Numeric(precision=8, scale=5), nullable=False),
        sa.Column("btts_brier", sa.Numeric(precision=8, scale=5), nullable=False),
        sa.Column("ou25_log_loss", sa.Numeric(precision=8, scale=5), nullable=False),
        sa.Column("ou25_brier", sa.Numeric(precision=8, scale=5), nullable=False),
        sa.Column("actual_score_probability", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("top1_score_hit", sa.Boolean(), nullable=False),
        sa.Column("top3_score_hit", sa.Boolean(), nullable=False),
        sa.Column("evaluation_schema_version", sa.String(length=20), nullable=False, server_default="1.0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["prediction_id"], ["shadow_predictions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["fixture_id"], ["matches.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prediction_id", "result_version", name="uq_shadow_evaluation_prediction_version"),
    )
    op.create_index("ix_shadow_evaluations_prediction_id", "shadow_evaluations", ["prediction_id"])
    op.create_index("ix_shadow_evaluations_fixture_id", "shadow_evaluations", ["fixture_id"])

    # 4. Monitoring Alerts
    op.create_table(
        "monitoring_alerts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("metric", sa.String(length=50), nullable=False),
        sa.Column("value", sa.Numeric(precision=10, scale=5), nullable=False),
        sa.Column("threshold", sa.Numeric(precision=10, scale=5), nullable=False),
        sa.Column("window", sa.Integer(), nullable=False),
        sa.Column("model_identity", sa.String(length=100), nullable=False),
        sa.Column("prediction_cohort", sa.String(length=100), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("metadata_payload", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_monitoring_alerts_severity", "monitoring_alerts", ["severity"])
    op.create_index("ix_monitoring_alerts_metric", "monitoring_alerts", ["metric"])
    op.create_index("ix_monitoring_alerts_created_at", "monitoring_alerts", ["created_at"])


def downgrade() -> None:
    op.drop_table("monitoring_alerts")
    op.drop_table("shadow_evaluations")
    op.drop_table("shadow_predictions")
    op.drop_table("shadow_prediction_runs")
