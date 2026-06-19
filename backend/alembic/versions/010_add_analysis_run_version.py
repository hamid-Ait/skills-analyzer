"""add version column to person_analysis_runs

Revision ID: 010
Revises: 009
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa

revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'person_analysis_runs',
        sa.Column('version', sa.Integer, nullable=False, server_default='1'),
    )


def downgrade():
    op.drop_column('person_analysis_runs', 'version')