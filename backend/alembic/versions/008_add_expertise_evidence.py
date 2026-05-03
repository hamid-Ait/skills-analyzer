"""add expertise_evidence column

Revision ID: 008
Revises: 007
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('people', sa.Column('expertise_evidence', JSONB, nullable=True))


def downgrade():
    op.drop_column('people', 'expertise_evidence')