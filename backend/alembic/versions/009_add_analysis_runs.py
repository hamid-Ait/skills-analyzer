"""add person_analysis_runs table

Revision ID: 009
Revises: 008
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'person_analysis_runs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('person_id', UUID(as_uuid=True), sa.ForeignKey('people.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('model', sa.String(100), nullable=True),
        sa.Column('result', JSONB, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('idx_analysis_runs_person_id', 'person_analysis_runs', ['person_id'])


def downgrade():
    op.drop_index('idx_analysis_runs_person_id', table_name='person_analysis_runs')
    op.drop_table('person_analysis_runs')