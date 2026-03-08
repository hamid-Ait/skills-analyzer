from uuid import UUID
from pydantic import BaseModel
from app.schemas.company import CompanyBrief


class UploadResponse(BaseModel):
    job_id: UUID
    total_urls: int
    companies: list[CompanyBrief]
