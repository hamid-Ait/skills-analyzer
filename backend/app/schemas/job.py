from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from typing import Optional
from app.schemas.company import CompanyBrief


class JobCreate(BaseModel):
    filename: str
    total_urls: int


class JobBrief(BaseModel):
    id: UUID
    filename: Optional[str] = None
    total_urls: int
    completed_urls: int
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobDetail(JobBrief):
    companies: list[CompanyBrief] = []
