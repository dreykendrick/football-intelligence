"""Sprint 2.5 Historical Dataset Assembly Relational Schema

Revision ID: 20260904_0004
Revises: 20260904_0003
Create Date: 2026-09-04 02:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260904_0004"
down_revision: str | None = "20260904_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Historical Dataset Releases
    op.create_table(
        "historical_dataset_releases",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("version", sa.String(length=30), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("selection_policy_key", sa.String(length=100), nullable=False, server_default="mvp_a_recent_3_usable_seasons"),
        sa.Column("selection_policy_version", sa.String(length=20), nullable=False, server_default="1.0.0"),
        sa.Column("total_competitions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_seasons", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_matches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dataset_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("quality_run_id", sa.UUID(), nullable=True),
        sa.Column("quality_status", sa.String(length=30), nullable=False, server_default="UNKNOWN"),
        sa.Column("identity_readiness_status", sa.String(length=30), nullable=False, server_default="UNKNOWN"),
        sa.Column("warning_acceptances", sa.JSON(), nullable=True),
        sa.Column("metadata_payload", sa.JSON(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_dataset_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["supersedes_dataset_id"], ["historical_dataset_releases.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", "version", name="uq_dataset_key_version"),
    )
    op.create_index("ix_historical_dataset_releases_key", "historical_dataset_releases", ["key"])
    op.create_index("ix_historical_dataset_releases_version", "historical_dataset_releases", ["version"])
    op.create_index("ix_historical_dataset_releases_status", "historical_dataset_releases", ["status"])
    op.create_index("ix_historical_dataset_releases_fingerprint", "historical_dataset_releases", ["dataset_fingerprint"])

    # 2. Historical Dataset Seasons
    op.create_table(
        "historical_dataset_seasons",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("dataset_release_id", sa.UUID(), nullable=False),
        sa.Column("competition_id", sa.UUID(), nullable=False),
        sa.Column("season_id", sa.UUID(), nullable=False),
        sa.Column("competition_code", sa.String(length=20), nullable=False),
        sa.Column("season_year", sa.String(length=20), nullable=False),
        sa.Column("readiness_status", sa.String(length=30), nullable=False),
        sa.Column("match_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expected_matches", sa.Integer(), nullable=True),
        sa.Column("source_provider_key", sa.String(length=50), nullable=True),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("source_checksum", sa.String(length=64), nullable=True),
        sa.Column("metadata_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["dataset_release_id"], ["historical_dataset_releases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_release_id", "competition_id", "season_id", name="uq_dataset_comp_season"),
    )
    op.create_index("ix_historical_dataset_seasons_dataset_release_id", "historical_dataset_seasons", ["dataset_release_id"])
    op.create_index("ix_historical_dataset_seasons_competition_id", "historical_dataset_seasons", ["competition_id"])
    op.create_index("ix_historical_dataset_seasons_season_id", "historical_dataset_seasons", ["season_id"])

    # 3. Historical Dataset Matches
    op.create_table(
        "historical_dataset_matches",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("dataset_release_id", sa.UUID(), nullable=False),
        sa.Column("match_id", sa.UUID(), nullable=False),
        sa.Column("competition_id", sa.UUID(), nullable=False),
        sa.Column("season_id", sa.UUID(), nullable=False),
        sa.Column("kickoff_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("home_team_id", sa.UUID(), nullable=False),
        sa.Column("away_team_id", sa.UUID(), nullable=False),
        sa.Column("ingestion_batch_id", sa.UUID(), nullable=True),
        sa.Column("raw_source_checksum", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["away_team_id"], ["teams.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["dataset_release_id"], ["historical_dataset_releases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["home_team_id"], ["teams.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ingestion_batch_id"], ["ingestion_batches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_release_id", "match_id", name="uq_dataset_match"),
    )
    op.create_index("ix_historical_dataset_matches_dataset_release_id", "historical_dataset_matches", ["dataset_release_id"])
    op.create_index("ix_historical_dataset_matches_match_id", "historical_dataset_matches", ["match_id"])
    op.create_index("ix_historical_dataset_matches_competition_id", "historical_dataset_matches", ["competition_id"])
    op.create_index("ix_historical_dataset_matches_season_id", "historical_dataset_matches", ["season_id"])
    op.create_index("ix_historical_dataset_matches_kickoff_utc", "historical_dataset_matches", ["kickoff_utc"])

    # 4. Historical Dataset Exclusions
    op.create_table(
        "historical_dataset_exclusions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("dataset_release_id", sa.UUID(), nullable=False),
        sa.Column("match_id", sa.UUID(), nullable=False),
        sa.Column("competition_code", sa.String(length=20), nullable=False),
        sa.Column("season_year", sa.String(length=20), nullable=False),
        sa.Column("exclusion_reason", sa.String(length=255), nullable=False),
        sa.Column("quality_rule_key", sa.String(length=50), nullable=True),
        sa.Column("metadata_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dataset_release_id"], ["historical_dataset_releases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_historical_dataset_exclusions_dataset_release_id", "historical_dataset_exclusions", ["dataset_release_id"])
    op.create_index("ix_historical_dataset_exclusions_match_id", "historical_dataset_exclusions", ["match_id"])


def downgrade() -> None:
    op.drop_table("historical_dataset_exclusions")
    op.drop_table("historical_dataset_matches")
    op.drop_table("historical_dataset_seasons")
    op.drop_table("historical_dataset_releases")
