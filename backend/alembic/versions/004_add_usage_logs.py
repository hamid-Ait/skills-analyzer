"""Add usage_logs table for cost monitoring

Revision ID: 004
Revises: 003
Create Date: 2026-03-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'usage_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id'), nullable=True),
        sa.Column('service', sa.String(50), nullable=False),
        sa.Column('provider', sa.String(100), nullable=False),
        sa.Column('model', sa.String(200), nullable=True),
        sa.Column('pipeline_step', sa.String(100), nullable=False),
        sa.Column('input_tokens', sa.Integer, nullable=True),
        sa.Column('output_tokens', sa.Integer, nullable=True),
        sa.Column('cost_usd', sa.Float, nullable=False),
        sa.Column('metadata_json', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_usage_logs_company_id', 'usage_logs', ['company_id'])
    op.create_index('ix_usage_logs_created_at', 'usage_logs', ['created_at'])
    op.create_index('ix_usage_logs_service', 'usage_logs', ['service'])


def downgrade() -> None:
    op.drop_index('ix_usage_logs_service')
    op.drop_index('ix_usage_logs_created_at')
    op.drop_index('ix_usage_logs_company_id')
    op.drop_table('usage_logs')
