"""Sprint 1.2 Complete Relational Schema Migration

Revision ID: 20260901_0002
Revises: 20260901_0001
Create Date: 2026-09-01 21:00:00.000000

"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260901_0002"
down_revision: str | None = "20260901_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Update Competitions & Seasons & Teams & Matches
    op.add_column("competitions", sa.Column("competition_type", sa.String(length=30), nullable=False, server_default="DOMESTIC_LEAGUE"))
    op.add_column("competitions", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("competitions", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))

    op.add_column("seasons", sa.Column("start_year", sa.Integer(), nullable=True))
    op.add_column("seasons", sa.Column("end_year", sa.Integer(), nullable=True))
    op.add_column("seasons", sa.Column("start_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("seasons", sa.Column("end_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("seasons", sa.Column("is_current", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("seasons", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))

    op.add_column("teams", sa.Column("short_name", sa.String(length=50), nullable=True))
    op.add_column("teams", sa.Column("country", sa.String(length=50), nullable=True))
    op.add_column("teams", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("teams", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))

    op.add_column("matches", sa.Column("half_time_home_score", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("half_time_away_score", sa.Integer(), nullable=True))
    op.add_column("matches", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("matches", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))

    # Check constraints on matches
    op.create_check_constraint("chk_match_distinct_teams", "matches", "home_team_id != away_team_id")
    op.create_check_constraint("chk_match_home_score_nonnegative", "matches", "home_score >= 0 OR home_score IS NULL")
    op.create_check_constraint("chk_match_away_score_nonnegative", "matches", "away_score >= 0 OR away_score IS NULL")

    # Match Statistics
    op.create_table(
        "match_statistics",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("match_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("shots", sa.Integer(), nullable=True),
        sa.Column("shots_on_target", sa.Integer(), nullable=True),
        sa.Column("corners", sa.Integer(), nullable=True),
        sa.Column("fouls", sa.Integer(), nullable=True),
        sa.Column("yellow_cards", sa.Integer(), nullable=True),
        sa.Column("red_cards", sa.Integer(), nullable=True),
        sa.Column("provider_xg", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "team_id", name="uq_match_team_statistic"),
    )
    op.create_index("ix_match_statistics_match_id", "match_statistics", ["match_id"])
    op.create_index("ix_match_statistics_team_id", "match_statistics", ["team_id"])

    # 2. Providers & Mappings
    op.create_table(
        "providers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_key", sa.String(length=50), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("provider_type", sa.String(length=30), nullable=False, server_default="HISTORICAL_CSV"),
        sa.Column("base_url", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_key", name="uq_provider_key"),
    )
    op.create_index("ix_providers_provider_key", "providers", ["provider_key"])

    op.create_table(
        "ingestion_batches",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_reference", sa.String(length=255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("metadata_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestion_batches_provider_id", "ingestion_batches", ["provider_id"])
    op.create_index("ix_ingestion_batches_status", "ingestion_batches", ["status"])

    op.create_table(
        "provider_competition_mappings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("competition_id", sa.UUID(), nullable=False),
        sa.Column("external_competition_id", sa.String(length=100), nullable=True),
        sa.Column("external_code", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "external_code", name="uq_provider_competition_code"),
    )

    op.create_table(
        "provider_season_mappings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("season_id", sa.UUID(), nullable=False),
        sa.Column("external_season_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "external_season_id", name="uq_provider_season"),
    )

    op.create_table(
        "provider_team_mappings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("external_team_id", sa.String(length=100), nullable=True),
        sa.Column("raw_alias", sa.String(length=100), nullable=False),
        sa.Column("normalized_alias", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "raw_alias", name="uq_provider_team_raw_alias"),
    )

    op.create_table(
        "provider_match_mappings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("match_id", sa.UUID(), nullable=False),
        sa.Column("external_match_id", sa.String(length=100), nullable=False),
        sa.Column("raw_match_key", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "external_match_id", name="uq_provider_match"),
    )

    op.create_table(
        "raw_source_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("ingestion_batch_id", sa.UUID(), nullable=True),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("external_reference", sa.String(length=100), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("processing_status", sa.String(length=20), nullable=False, server_default="PROCESSED"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ingestion_batch_id"], ["ingestion_batches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 3. Features & Snapshots
    op.create_table(
        "feature_definitions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("feature_key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("data_type", sa.String(length=30), nullable=False, server_default="FLOAT"),
        sa.Column("category", sa.String(length=50), nullable=False, server_default="STRENGTH"),
        sa.Column("version", sa.String(length=20), nullable=False, server_default="1.0.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feature_key", name="uq_feature_key"),
    )

    op.create_table(
        "feature_sets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_feature_set_name_version"),
    )

    op.create_table(
        "feature_set_features",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("feature_set_id", sa.UUID(), nullable=False),
        sa.Column("feature_definition_id", sa.UUID(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["feature_definition_id"], ["feature_definitions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["feature_set_id"], ["feature_sets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feature_set_id", "feature_definition_id", name="uq_feature_set_feature"),
    )

    op.create_table(
        "feature_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("match_id", sa.UUID(), nullable=False),
        sa.Column("feature_set_id", sa.UUID(), nullable=False),
        sa.Column("snapshot_type", sa.String(length=20), nullable=False, server_default="FINAL"),
        sa.Column("feature_version", sa.String(length=20), nullable=False, server_default="1.0.0"),
        sa.Column("cutoff_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_values", sa.JSON(), nullable=False),
        sa.Column("missing_features", sa.JSON(), nullable=True),
        sa.Column("data_quality_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["feature_set_id"], ["feature_sets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", "feature_set_id", "snapshot_type", name="uq_match_feature_snapshot_type"),
    )
    op.create_index("ix_feature_snapshots_cutoff_timestamp", "feature_snapshots", ["cutoff_timestamp"])

    # 4. Models & Versions
    op.create_table(
        "models",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("model_key", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("model_family", sa.String(length=50), nullable=False, server_default="POISSON"),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_key", name="uq_model_key"),
    )

    op.create_table(
        "model_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("model_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.String(length=30), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=20), nullable=False, server_default="EXPERIMENTAL"),
        sa.Column("feature_set_id", sa.UUID(), nullable=False),
        sa.Column("training_start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("training_end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hyperparameters", sa.JSON(), nullable=True),
        sa.Column("artifact_path", sa.String(length=255), nullable=True),
        sa.Column("code_version", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["feature_set_id"], ["feature_sets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["model_id"], ["models.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "version", name="uq_model_version"),
    )
    op.create_index("ix_model_versions_lifecycle_status", "model_versions", ["lifecycle_status"])

    op.create_table(
        "model_lifecycle_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("model_version_id", sa.UUID(), nullable=False),
        sa.Column("previous_status", sa.String(length=20), nullable=True),
        sa.Column("new_status", sa.String(length=20), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("metadata_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 5. Prediction Snapshots
    op.create_table(
        "prediction_snapshots",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("match_id", sa.UUID(), nullable=False),
        sa.Column("model_version_id", sa.UUID(), nullable=False),
        sa.Column("feature_snapshot_id", sa.UUID(), nullable=False),
        sa.Column("snapshot_type", sa.String(length=20), nullable=False, server_default="FINAL"),
        sa.Column("prediction_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_kickoff_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prediction_horizon_seconds", sa.Integer(), nullable=True),
        sa.Column("prob_home_win", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("prob_draw", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("prob_away_win", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.Column("predicted_home_goals", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("predicted_away_goals", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("prob_over_25", sa.Numeric(precision=6, scale=5), nullable=True),
        sa.Column("prob_under_25", sa.Numeric(precision=6, scale=5), nullable=True),
        sa.Column("prob_btts_yes", sa.Numeric(precision=6, scale=5), nullable=True),
        sa.Column("prob_btts_no", sa.Numeric(precision=6, scale=5), nullable=True),
        sa.Column("data_quality_score", sa.Numeric(precision=6, scale=5), nullable=True),
        sa.Column("prediction_uncertainty", sa.Numeric(precision=6, scale=5), nullable=True),
        sa.Column("explainability_payload", sa.JSON(), nullable=True),
        sa.Column("supersedes_prediction_id", sa.UUID(), nullable=True),
        sa.Column("correction_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("prob_home_win >= 0 AND prob_home_win <= 1", name="chk_pred_prob_home_win_range"),
        sa.CheckConstraint("prob_draw >= 0 AND prob_draw <= 1", name="chk_pred_prob_draw_range"),
        sa.CheckConstraint("prob_away_win >= 0 AND prob_away_win <= 1", name="chk_pred_prob_away_win_range"),
        sa.CheckConstraint("abs(prob_home_win + prob_draw + prob_away_win - 1.0) <= 0.01", name="chk_pred_prob_sum_unity"),
        sa.ForeignKeyConstraint(["feature_snapshot_id"], ["feature_snapshots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supersedes_prediction_id"], ["prediction_snapshots.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prediction_snapshots_match_id", "prediction_snapshots", ["match_id"])
    op.create_index("ix_prediction_snapshots_model_version_id", "prediction_snapshots", ["model_version_id"])
    op.create_index("ix_prediction_snapshots_prediction_timestamp", "prediction_snapshots", ["prediction_timestamp"])

    # 6. Evaluation & Backtesting
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("model_version_id", sa.UUID(), nullable=False),
        sa.Column("feature_set_id", sa.UUID(), nullable=False),
        sa.Column("competition_scope", sa.JSON(), nullable=True),
        sa.Column("training_start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("training_end_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("test_start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("test_end_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("configuration", sa.JSON(), nullable=True),
        sa.Column("code_version", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["feature_set_id"], ["feature_sets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("model_version_id", sa.UUID(), nullable=False),
        sa.Column("backtest_run_id", sa.UUID(), nullable=True),
        sa.Column("competition_scope", sa.JSON(), nullable=True),
        sa.Column("season_scope", sa.JSON(), nullable=True),
        sa.Column("prediction_horizon", sa.String(length=20), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("configuration", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["backtest_run_id"], ["backtest_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "evaluation_metrics",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("evaluation_run_id", sa.UUID(), nullable=False),
        sa.Column("metric_key", sa.String(length=50), nullable=False),
        sa.Column("metric_value", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column("scope_category", sa.String(length=50), nullable=False, server_default="OVERALL"),
        sa.Column("metadata_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evaluation_metrics_metric_key", "evaluation_metrics", ["metric_key"])

    op.create_table(
        "data_quality_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("match_id", sa.UUID(), nullable=True),
        sa.Column("feature_snapshot_id", sa.UUID(), nullable=True),
        sa.Column("quality_type", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="WARNING"),
        sa.Column("quality_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("issue_key", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("metadata_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["feature_snapshot_id"], ["feature_snapshots.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("data_quality_logs")
    op.drop_table("evaluation_metrics")
    op.drop_table("evaluation_runs")
    op.drop_table("backtest_runs")
    op.drop_table("prediction_snapshots")
    op.drop_table("model_lifecycle_history")
    op.drop_table("model_versions")
    op.drop_table("models")
    op.drop_table("feature_snapshots")
    op.drop_table("feature_set_features")
    op.drop_table("feature_sets")
    op.drop_table("feature_definitions")
    op.drop_table("raw_source_records")
    op.drop_table("provider_match_mappings")
    op.drop_table("provider_team_mappings")
    op.drop_table("provider_season_mappings")
    op.drop_table("provider_competition_mappings")
    op.drop_table("ingestion_batches")
    op.drop_table("providers")
    op.drop_table("match_statistics")

    op.drop_constraint("chk_match_away_score_nonnegative", "matches", type_="check")
    op.drop_constraint("chk_match_home_score_nonnegative", "matches", type_="check")
    op.drop_constraint("chk_match_distinct_teams", "matches", type_="check")

    op.drop_column("matches", "updated_at")
    op.drop_column("matches", "completed_at")
    op.drop_column("matches", "half_time_away_score")
    op.drop_column("matches", "half_time_home_score")

    op.drop_column("teams", "updated_at")
    op.drop_column("teams", "is_active")
    op.drop_column("teams", "country")
    op.drop_column("teams", "short_name")

    op.drop_column("seasons", "updated_at")
    op.drop_column("seasons", "is_current")
    op.drop_column("seasons", "end_date")
    op.drop_column("seasons", "start_date")
    op.drop_column("seasons", "end_year")
    op.drop_column("seasons", "start_year")

    op.drop_column("competitions", "updated_at")
    op.drop_column("competitions", "is_active")
    op.drop_column("competitions", "competition_type")
