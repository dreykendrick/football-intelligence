"""Initial schema foundation for Sprint 1.1

Revision ID: 20260901_0001
Revises: 
Create Date: 2026-09-01 19:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '20260901_0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'system_audit_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table(
        'competitions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('country', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )
    op.create_table(
        'teams',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('canonical_name', sa.String(length=100), nullable=False),
        sa.Column('short_code', sa.String(length=10), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('canonical_name')
    )
    op.create_table(
        'seasons',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('competition_id', sa.UUID(), nullable=False),
        sa.Column('season_year', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['competition_id'], ['competitions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('competition_id', 'season_year', name='uq_competition_season')
    )
    op.create_table(
        'team_alias_mappings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('team_id', sa.UUID(), nullable=False),
        sa.Column('provider_name', sa.String(length=50), nullable=False),
        sa.Column('raw_alias', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider_name', 'raw_alias', name='uq_provider_team_alias')
    )
    op.create_table(
        'matches',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('season_id', sa.UUID(), nullable=False),
        sa.Column('home_team_id', sa.UUID(), nullable=False),
        sa.Column('away_team_id', sa.UUID(), nullable=False),
        sa.Column('kickoff_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('home_score', sa.Integer(), nullable=True),
        sa.Column('away_score', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['away_team_id'], ['teams.id'], ),
        sa.ForeignKeyConstraint(['home_team_id'], ['teams.id'], ),
        sa.ForeignKeyConstraint(['season_id'], ['seasons.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('matches')
    op.drop_table('team_alias_mappings')
    op.drop_table('seasons')
    op.drop_table('teams')
    op.drop_table('competitions')
    op.drop_table('system_audit_logs')
