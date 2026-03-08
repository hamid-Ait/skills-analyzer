import csv
import io
import json
from urllib.parse import urlparse

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Job, Company
from app.schemas.upload import UploadResponse
from app.schemas.company import CompanyBrief
from app.tasks.scrape_task import process_job

router = APIRouter()


def _domain_to_name(url: str) -> str:
    domain = urlparse(url).netloc.replace("www.", "")
    name = domain.split(".")[0]
    return name.replace("-", " ").replace("_", " ").title()


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


@router.post("/upload", response_model=UploadResponse)
def upload_file(
    file: UploadFile = File(...),
    discover: bool = Form(True),
    follow_profiles: bool = Form(True),
    enrich_linkedin: bool = Form(False),
    db: Session = Depends(get_db),
):
    content = file.file.read()
    urls = _parse_urls_from_file(content, file.filename or "unknown.json")

    if not urls:
        raise HTTPException(status_code=400, detail="No valid URLs found in the uploaded file")

    job = Job(filename=file.filename, total_urls=len(urls), status="pending")
    db.add(job)
    db.flush()

    companies = []
    for url in urls:
        company = Company(
            job_id=job.id,
            url=url,
            name=_domain_to_name(url),
            status="pending",
        )
        db.add(company)
        db.flush()
        companies.append(company)

    db.commit()

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
