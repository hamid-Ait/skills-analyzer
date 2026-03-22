import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)
    service: Mapped[str] = mapped_column(String(50), nullable=False)  # "llm" | "apify"
    provider: Mapped[str] = mapped_column(String(100), nullable=False)  # "claude" | "openai" | "gemini" | "deepseek" | "manus" | "apify"
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pipeline_step: Mapped[str] = mapped_column(String(100), nullable=False)  # "scraping" | "team_discovery" | "linkedin_resolve" | "enrichment" | "analysis"
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
