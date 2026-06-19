from datetime import datetime
from uuid import UUID
from pydantic import BaseModel
from typing import Optional, Any


class PersonBrief(BaseModel):
    id: UUID
    name: str
    title: Optional[str] = None
    department: Optional[str] = None
    location: Optional[str] = None
    image_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    primary_expertise: Optional[str] = None
    matched_13_categories: Optional[list[str]] = None
    sector: Optional[str] = None

    model_config = {"from_attributes": True}


class PersonDetail(PersonBrief):
    company_id: UUID
    bio: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    twitter_url: Optional[str] = None
    other_url: Optional[str] = None
    profile_url: Optional[str] = None
    extra: Optional[dict[str, Any]] = None
    source_url: Optional[str] = None
    profile_enriched: bool = False
    justification: Optional[str] = None
    matched_sector: Optional[list[str]] = None
    geography: Optional[str] = None
    inferred_expertise_functional: Optional[list[str]] = None
    inference_reasoning: Optional[str] = None
    matched_inferred_expertise_topics: Optional[list[str]] = None
    linkedin_experience_summary: Optional[str] = None
    data_source: Optional[str] = None
    linkedin_headline: Optional[str] = None
    linkedin_summary: Optional[str] = None
    linkedin_experience: Optional[Any] = None
    linkedin_education: Optional[Any] = None
    linkedin_skills: Optional[list[str]] = None
    linkedin_enriched: bool = False
    expertise_evidence: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class PersonList(BaseModel):
    items: list[PersonBrief]
    total: int
    page: int
    page_size: int
