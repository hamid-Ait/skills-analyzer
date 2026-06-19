"""Add inference_reasoning column to people table

Revision ID: 006
Revises: 005
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa

revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('people', sa.Column('inference_reasoning', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('people', 'inference_reasoning')