"""Convert inferred_expertise_functional from Text to ARRAY(String)

Revision ID: 002
Revises: 001
Create Date: 2026-03-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add a temporary column with the new type
    op.add_column('people', sa.Column('inferred_expertise_functional_new', ARRAY(sa.String), nullable=True))

    # Migrate existing data: split semicolon-separated text into array
    op.execute("""
        UPDATE people
        SET inferred_expertise_functional_new = (
            SELECT array_agg(trim(elem))
            FROM unnest(string_to_array(inferred_expertise_functional, ';')) AS elem
            WHERE trim(elem) != ''
        )
        WHERE inferred_expertise_functional IS NOT NULL
          AND inferred_expertise_functional != '—'
    """)

    # Drop old column and rename new one
    op.drop_column('people', 'inferred_expertise_functional')
    op.alter_column('people', 'inferred_expertise_functional_new', new_column_name='inferred_expertise_functional')


def downgrade() -> None:
    # Add back text column
    op.add_column('people', sa.Column('inferred_expertise_functional_old', sa.Text, nullable=True))

    # Convert array back to semicolon-separated text
    op.execute("""
        UPDATE people
        SET inferred_expertise_functional_old = array_to_string(inferred_expertise_functional, '; ')
        WHERE inferred_expertise_functional IS NOT NULL
    """)

    op.drop_column('people', 'inferred_expertise_functional')
    op.alter_column('people', 'inferred_expertise_functional_old', new_column_name='inferred_expertise_functional')
