from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from typing import Optional, Any


class CompanyBrief(BaseModel):
    id: UUID
    url: str
    name: Optional[str] = None
    team_url: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    people_count: int = 0
    pages_scraped: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompanyDetail(CompanyBrief):
    job_id: UUID
    waf_detected: bool = False
    waf_name: Optional[str] = None
    scrape_meta: Optional[dict[str, Any]] = None


class CompanyList(BaseModel):
    items: list[CompanyBrief]
    total: int
    page: int
    page_size: int
