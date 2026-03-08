import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Person(Base):
    __tablename__ = "people"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    # Canonical fields from existing agent.py
    name: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    twitter_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    other_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_enriched: Mapped[bool] = mapped_column(Boolean, default=False)

    # LLM expertise analysis fields
    primary_expertise: Mapped[str | None] = mapped_column(Text, nullable=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_13_categories: Mapped[list | None] = mapped_column(ARRAY(String), nullable=True)
    sector: Mapped[str | None] = mapped_column(Text, nullable=True)
    geography: Mapped[str | None] = mapped_column(Text, nullable=True)
    inferred_expertise_functional: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_inferred_expertise_topics: Mapped[list | None] = mapped_column(ARRAY(String), nullable=True)
    linkedin_experience_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expertise_raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_data_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # LinkedIn enrichment fields (via Apify)
    linkedin_headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    linkedin_experience: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    linkedin_education: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    linkedin_skills: Mapped[list | None] = mapped_column(ARRAY(String), nullable=True)
    linkedin_enriched: Mapped[bool] = mapped_column(Boolean, default=False)
    linkedin_enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    company = relationship("Company", back_populates="people")

    __table_args__ = (
        Index("idx_people_company_id", "company_id"),
        Index("idx_people_matched_categories", "matched_13_categories", postgresql_using="gin"),
    )
