"""add matched_sector column

Revision ID: 007
Revises: 006
Create Date: 2026-04-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('people', sa.Column('matched_sector', ARRAY(sa.String()), nullable=True))


def downgrade():
    op.drop_column('people', 'matched_sector')