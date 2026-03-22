import csv
import io
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Job, Company, Person
from app.schemas.upload import UploadResponse
from app.schemas.company import CompanyBrief
from app.tasks.scrape_task import process_job

router = APIRouter()


def _domain_to_name(url: str) -> str:
    domain = urlparse(url).netloc.replace("www.", "")
    name = domain.split(".")[0]
    return name.replace("-", " ").replace("_", " ").title()


def _normalize_url(url: str) -> str:
    """Normalize URL for comparison (strip trailing slash, lowercase)."""
    return url.rstrip("/").lower()


def _parse_urls_from_file(content: bytes, filename: str) -> list[str]:
    text = content.decode("utf-8")
    urls = []

    if filename.endswith(".json"):
        raw = json.loads(text)
        items = raw if isinstance(raw, list) else raw.get("urls", raw.get("URLs", []))
        for item in items:
            if isinstance(item, str):
                urls.append(item.strip())
            elif isinstance(item, dict):
                for k in ("url", "URL", "link", "href", "website"):
                    if k in item:
                        urls.append(item[k].strip())
                        break

    elif filename.endswith(".csv"):
        reader_text = io.StringIO(text)
        sample = text[:1024]
        if any(h in sample.lower() for h in ("url", "link", "href", "website")):
            for row in csv.DictReader(reader_text):
                for k in ("url", "URL", "link", "href", "website"):
                    if k in row:
                        urls.append(row[k].strip())
                        break
        else:
            reader_text.seek(0)
            for row in csv.reader(reader_text):
                if row:
                    urls.append(row[0].strip())

    elif filename.endswith(".txt"):
        for line in text.splitlines():
            line = line.strip()
            if line and line.startswith("http"):
                urls.append(line)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {filename}")

    return [u for u in urls if u.startswith("http")]


class ExistingCompanyInfo(BaseModel):
    url: str
    name: str | None
    people_count: int
    status: str


class CheckUrlsRequest(BaseModel):
    urls: list[str]


class CheckUrlsResponse(BaseModel):
    existing: list[ExistingCompanyInfo]
    new_urls: list[str]


@router.post("/upload/check-urls", response_model=CheckUrlsResponse)
def check_urls(body: CheckUrlsRequest, db: Session = Depends(get_db)):
    """Check which URLs already have company records in the DB."""
    all_companies = db.query(Company).filter(Company.url.in_(body.urls)).all()

    # Deduplicate: keep the most recent company per normalized URL
    by_url: dict[str, Company] = {}
    for c in all_companies:
        norm = _normalize_url(c.url)
        if norm not in by_url or c.created_at > by_url[norm].created_at:
            by_url[norm] = c

    existing = [
        ExistingCompanyInfo(
            url=c.url, name=c.name, people_count=c.people_count, status=c.status,
        )
        for c in by_url.values()
    ]
    existing_norms = set(by_url.keys())
    new_urls = [u for u in body.urls if _normalize_url(u) not in existing_norms]

    return CheckUrlsResponse(existing=existing, new_urls=new_urls)


@router.post("/upload", response_model=UploadResponse)
def upload_file(
    file: UploadFile = File(...),
    discover: bool = Form(True),
    follow_profiles: bool = Form(True),
    enrich_linkedin: bool = Form(False),
    skip_urls: str = Form("[]"),
    db: Session = Depends(get_db),
):
    content = file.file.read()
    urls = _parse_urls_from_file(content, file.filename or "unknown.json")

    if not urls:
        raise HTTPException(status_code=400, detail="No valid URLs found in the uploaded file")

    # Parse skip_urls — existing companies the user chose not to refresh
    try:
        skip_set = {_normalize_url(u) for u in json.loads(skip_urls)} if skip_urls != "[]" else set()
    except (json.JSONDecodeError, TypeError):
        skip_set = set()

    # Find existing companies by URL
    existing_companies = db.query(Company).filter(Company.url.in_(urls)).all()
    existing_by_url: dict[str, Company] = {}
    for c in existing_companies:
        norm = _normalize_url(c.url)
        # Keep the most recent record per URL
        if norm not in existing_by_url or c.created_at > existing_by_url[norm].created_at:
            existing_by_url[norm] = c

    job = Job(filename=file.filename, total_urls=len(urls), status="pending")
    db.add(job)
    db.flush()

    companies = []
    for url in urls:
        norm = _normalize_url(url)
        existing = existing_by_url.get(norm)

        if existing and norm in skip_set:
            # User chose to skip this existing company — don't refresh it
            continue
        elif existing:
            # Reset existing company for rescraping
            db.query(Person).filter(Person.company_id == existing.id).delete()
            existing.job_id = job.id
            existing.status = "pending"
            existing.error_message = None
            existing.people_count = 0
            existing.pages_scraped = 0
            # Keep existing team_url — avoids re-discovering a known team page
            existing.waf_detected = False
            existing.waf_name = None
            existing.scrape_meta = None
            existing.updated_at = datetime.now(timezone.utc)
            companies.append(existing)
        else:
            company = Company(
                job_id=job.id,
                url=url,
                name=_domain_to_name(url),
                status="pending",
            )
            db.add(company)
            db.flush()
            companies.append(company)

    # Update job total to reflect actual companies being processed
    job.total_urls = len(companies)
    db.commit()

    if not companies:
        return UploadResponse(
            job_id=job.id,
            total_urls=0,
            companies=[],
        )

    # Dispatch Celery task
    process_job.delay(
        str(job.id),
        discover=discover,
        follow_profiles=follow_profiles,
        enrich_linkedin=enrich_linkedin,
    )

    return UploadResponse(
        job_id=job.id,
        total_urls=len(urls),
        companies=[CompanyBrief.model_validate(c) for c in companies],
    )
