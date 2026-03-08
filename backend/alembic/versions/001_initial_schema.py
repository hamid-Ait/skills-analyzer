"""Initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'jobs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('celery_task_id', sa.String(255), nullable=True),
        sa.Column('filename', sa.String(500), nullable=True),
        sa.Column('total_urls', sa.Integer, default=0),
        sa.Column('completed_urls', sa.Integer, default=0),
        sa.Column('status', sa.String(50), default='pending'),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    op.create_table(
        'companies',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('job_id', UUID(as_uuid=True), sa.ForeignKey('jobs.id'), nullable=False),
        sa.Column('url', sa.Text, nullable=False),
        sa.Column('name', sa.String(500), nullable=True),
        sa.Column('team_url', sa.Text, nullable=True),
        sa.Column('status', sa.String(50), default='pending'),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('people_count', sa.Integer, default=0),
        sa.Column('pages_scraped', sa.Integer, default=0),
        sa.Column('waf_detected', sa.Boolean, default=False),
        sa.Column('waf_name', sa.String(100), nullable=True),
        sa.Column('scrape_meta', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    op.create_table(
        'people',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.Text, nullable=False),
        sa.Column('title', sa.Text, nullable=True),
        sa.Column('department', sa.Text, nullable=True),
        sa.Column('bio', sa.Text, nullable=True),
        sa.Column('email', sa.String(500), nullable=True),
        sa.Column('phone', sa.String(100), nullable=True),
        sa.Column('linkedin_url', sa.Text, nullable=True),
        sa.Column('twitter_url', sa.Text, nullable=True),
        sa.Column('other_url', sa.Text, nullable=True),
        sa.Column('image_url', sa.Text, nullable=True),
        sa.Column('location', sa.Text, nullable=True),
        sa.Column('profile_url', sa.Text, nullable=True),
        sa.Column('extra', JSONB, nullable=True),
        sa.Column('source_url', sa.Text, nullable=True),
        sa.Column('profile_enriched', sa.Boolean, default=False),
        sa.Column('primary_expertise', sa.Text, nullable=True),
        sa.Column('justification', sa.Text, nullable=True),
        sa.Column('matched_13_categories', ARRAY(sa.String), nullable=True),
        sa.Column('sector', sa.Text, nullable=True),
        sa.Column('geography', sa.Text, nullable=True),
        sa.Column('inferred_expertise_functional', sa.Text, nullable=True),
        sa.Column('matched_inferred_expertise_topics', ARRAY(sa.String), nullable=True),
        sa.Column('linkedin_experience_summary', sa.Text, nullable=True),
        sa.Column('data_source', sa.String(100), nullable=True),
        sa.Column('expertise_raw', JSONB, nullable=True),
        sa.Column('raw_data_json', JSONB, nullable=True),
        sa.Column('linkedin_headline', sa.Text, nullable=True),
        sa.Column('linkedin_summary', sa.Text, nullable=True),
        sa.Column('linkedin_experience', JSONB, nullable=True),
        sa.Column('linkedin_education', JSONB, nullable=True),
        sa.Column('linkedin_skills', ARRAY(sa.String), nullable=True),
        sa.Column('linkedin_enriched', sa.Boolean, default=False),
        sa.Column('linkedin_enriched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    op.create_index('idx_people_company_id', 'people', ['company_id'])
    op.create_index('idx_people_matched_categories', 'people', ['matched_13_categories'], postgresql_using='gin')


def downgrade() -> None:
    op.drop_table('people')
    op.drop_table('companies')
    op.drop_table('jobs')
