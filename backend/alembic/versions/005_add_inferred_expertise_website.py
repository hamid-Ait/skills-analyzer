"""Add inferred_expertise_website column to people table

Revision ID: 005
Revises: 004
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('people', sa.Column(
        'inferred_expertise_website',
        ARRAY(sa.String()),
        nullable=True,
    ))


def downgrade():
    op.drop_column('people', 'inferred_expertise_website')