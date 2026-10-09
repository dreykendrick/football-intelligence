"""Sprint 1.4 Data Quality Finding Fields

Revision ID: 20260904_0003
Revises: 20260901_0002
Create Date: 2026-09-04 00:20:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260904_0003"
down_revision: str | None = "20260901_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("data_quality_logs", sa.Column("rule_key", sa.String(50), nullable=True))
    op.add_column("data_quality_logs", sa.Column("entity_type", sa.String(50), nullable=True))
    op.add_column("data_quality_logs", sa.Column("entity_id", sa.Uuid(), nullable=True))
    op.add_column("data_quality_logs", sa.Column("competition_code", sa.String(20), nullable=True))
    op.add_column("data_quality_logs", sa.Column("season_year", sa.String(20), nullable=True))
    op.add_column("data_quality_logs", sa.Column("resolution_status", sa.String(30), nullable=False, server_default="OPEN"))
    op.add_column("data_quality_logs", sa.Column("resolution_reason", sa.String(255), nullable=True))

    op.create_index("ix_data_quality_logs_rule_key", "data_quality_logs", ["rule_key"])
    op.create_index("ix_data_quality_logs_severity", "data_quality_logs", ["severity"])
    op.create_index("ix_data_quality_logs_competition_code", "data_quality_logs", ["competition_code"])
    op.create_index("ix_data_quality_logs_season_year", "data_quality_logs", ["season_year"])
    op.create_index("ix_data_quality_logs_resolution_status", "data_quality_logs", ["resolution_status"])


def downgrade() -> None:
    op.drop_index("ix_data_quality_logs_resolution_status", table_name="data_quality_logs")
    op.drop_index("ix_data_quality_logs_season_year", table_name="data_quality_logs")
    op.drop_index("ix_data_quality_logs_competition_code", table_name="data_quality_logs")
    op.drop_index("ix_data_quality_logs_severity", table_name="data_quality_logs")
    op.drop_index("ix_data_quality_logs_rule_key", table_name="data_quality_logs")

    op.drop_column("data_quality_logs", "resolution_reason")
    op.drop_column("data_quality_logs", "resolution_status")
    op.drop_column("data_quality_logs", "season_year")
    op.drop_column("data_quality_logs", "competition_code")
    op.drop_column("data_quality_logs", "entity_id")
    op.drop_column("data_quality_logs", "entity_type")
    op.drop_column("data_quality_logs", "rule_key")
