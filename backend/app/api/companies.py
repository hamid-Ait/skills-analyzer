import logging
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Company, Person
from app.schemas.company import CompanyBrief, CompanyDetail, CompanyList

log = logging.getLogger(__name__)

router = APIRouter()


TERMINAL_STATUSES = {"completed", "error"}


def _enrich_company_briefs(companies: list, db: Session) -> list[CompanyBrief]:
    """Add top_categories and completeness stats to company briefs."""
    if not companies:
        return []

    company_ids = [str(c.id) for c in companies]
    # Build safe IN clause with quoted UUID literals
    id_list = ", ".join(f"'{cid}'" for cid in company_ids)

    # Batch query: per-company stats
    stats_rows = db.execute(
        text(f"""
            SELECT
                company_id,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE primary_expertise IS NOT NULL) AS analyzed,
                COUNT(*) FILTER (WHERE linkedin_enriched = TRUE) AS linkedin,
                COUNT(*) FILTER (WHERE image_url IS NOT NULL) AS photo
            FROM people
            WHERE company_id IN ({id_list})
            GROUP BY company_id
        """)
    ).fetchall()

    stats_map = {}
    for row in stats_rows:
        cid = str(row[0])
        total = row[1] or 0
        stats_map[cid] = {
            "analyzed_pct": round(row[2] / total * 100) if total else 0,
            "linkedin_pct": round(row[3] / total * 100) if total else 0,
            "photo_pct": round(row[4] / total * 100) if total else 0,
        }

    # Batch query: top 3 categories per company
    cat_rows = db.execute(
        text(f"""
            SELECT company_id, cat, COUNT(*) AS cnt
            FROM people, unnest(matched_13_categories) AS cat
            WHERE company_id IN ({id_list})
              AND matched_13_categories IS NOT NULL
            GROUP BY company_id, cat
            ORDER BY company_id, cnt DESC
        """)
    ).fetchall()

    cat_map: dict[str, list[str]] = {}
    for row in cat_rows:
        cid = str(row[0])
        if cid not in cat_map:
            cat_map[cid] = []
        if len(cat_map[cid]) < 3:
            cat_map[cid].append(row[1])

    briefs = []
    for c in companies:
        brief = CompanyBrief.model_validate(c)
        cid = str(c.id)
        if cid in stats_map:
            brief.analyzed_pct = stats_map[cid]["analyzed_pct"]
            brief.linkedin_pct = stats_map[cid]["linkedin_pct"]
            brief.photo_pct = stats_map[cid]["photo_pct"]
        if cid in cat_map:
            brief.top_categories = cat_map[cid]
        briefs.append(brief)

    return briefs


@router.get("/companies", response_model=CompanyList)
def list_companies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    active: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    # When active=true, return all in-progress companies (no dedup needed)
    if active:
        query = db.query(Company).filter(Company.status.notin_(TERMINAL_STATUSES))
        if search:
            query = query.filter(Company.name.ilike(f"%{search}%") | Company.url.ilike(f"%{search}%"))
        total = query.count()
        companies = query.order_by(Company.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return CompanyList(
            items=[CompanyBrief.model_validate(c) for c in companies],
            total=total, page=page, page_size=page_size,
        )

    # Subquery: most recent company id per URL
    latest = (
        db.query(
            Company.url,
            func.max(Company.created_at).label("max_created"),
        )
        .group_by(Company.url)
    )
    if status:
        latest = latest.filter(Company.status == status)
    if search:
        latest = latest.filter(Company.name.ilike(f"%{search}%") | Company.url.ilike(f"%{search}%"))

    latest_sub = latest.subquery()

    query = (
        db.query(Company)
        .join(latest_sub, (Company.url == latest_sub.c.url) & (Company.created_at == latest_sub.c.max_created))
    )
    if status:
        query = query.filter(Company.status == status)

    total = query.count()
    companies = query.order_by(Company.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return CompanyList(
        items=_enrich_company_briefs(companies, db),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/companies/{company_id}", response_model=CompanyDetail)
def get_company(company_id: UUID, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return CompanyDetail.model_validate(company)


class RetryRequest(BaseModel):
    mode: str = "rescrape"  # "rescrape", "reanalyze", "reenrich"


class RetryResponse(BaseModel):
    status: str
    message: str


@router.post("/companies/{company_id}/retry", response_model=RetryResponse)
def retry_company(company_id: UUID, body: RetryRequest, db: Session = Depends(get_db)):
    """Retry processing a company.

    Modes:
    - rescrape: Delete people, re-scrape from scratch (uses team_url if already discovered)
    - reanalyze: Keep people, re-run LLM expertise analysis
    - reenrich: Keep people, re-run LinkedIn enrichment + analysis
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Don't retry if already in progress
    in_progress = {"pending", "discovering", "scraping", "searching", "analyzing", "resolving", "enriching"}
    if company.status in in_progress:
        raise HTTPException(status_code=400, detail=f"Company is already {company.status}")

    if body.mode == "rescrape":
        # Delete existing people and start fresh
        db.query(Person).filter(Person.company_id == company_id).delete()
        company.status = "pending"
        company.error_message = None
        company.people_count = 0
        # Keep team_url so we skip discovery if already found
        discover = company.team_url is None
        company.updated_at = datetime.now(timezone.utc)
        db.commit()

        from app.tasks.scrape_task import scrape_company
        scrape_company.delay(
            str(company_id),
            discover=discover,
            follow_profiles=True,
            enrich_linkedin=True,
        )
        return RetryResponse(status="ok", message=f"Re-scraping {company.name or company.url}")

    elif body.mode == "reanalyze":
        # Keep people, re-run LLM analysis for ALL (clears existing)
        person_ids = [
            str(p.id) for p in
            db.query(Person).filter(Person.company_id == company_id).all()
        ]
        if not person_ids:
            raise HTTPException(status_code=400, detail="No people to analyze")

        # Clear old expertise data
        db.execute(
            text("""
                UPDATE people SET
                    primary_expertise = NULL, justification = NULL,
                    matched_13_categories = NULL, sector = NULL,
                    geography = NULL, inferred_expertise_functional = NULL,
                    matched_inferred_expertise_topics = NULL, expertise_raw = NULL
                WHERE company_id = :cid
            """),
            {"cid": str(company_id)},
        )
        company.status = "analyzing"
        company.error_message = None
        company.updated_at = datetime.now(timezone.utc)
        db.commit()

        from app.tasks.analyze_task import analyze_expertise_batch
        analyze_expertise_batch.delay(str(company_id), person_ids)
        return RetryResponse(status="ok", message=f"Re-analyzing {len(person_ids)} people")

    elif body.mode == "analyze_missing":
        # Only analyze people who don't have expertise yet
        missing = db.query(Person).filter(
            Person.company_id == company_id,
            Person.primary_expertise.is_(None),
        ).all()
        if not missing:
            raise HTTPException(status_code=400, detail="All people are already analyzed")

        person_ids = [str(p.id) for p in missing]
        company.status = "analyzing"
        company.error_message = None
        company.updated_at = datetime.now(timezone.utc)
        db.commit()

        from app.tasks.analyze_task import analyze_expertise_batch
        analyze_expertise_batch.delay(str(company_id), person_ids)
        return RetryResponse(status="ok", message=f"Analyzing {len(missing)} unanalyzed people")

    elif body.mode == "reenrich":
        # Reset LinkedIn enrichment, then re-enrich + re-analyze
        people = db.query(Person).filter(Person.company_id == company_id).all()
        if not people:
            raise HTTPException(status_code=400, detail="No people to enrich")

        person_ids = [str(p.id) for p in people]
        has_url_ids = [str(p.id) for p in people if p.linkedin_url]
        no_url_ids = [str(p.id) for p in people if not p.linkedin_url]

        # Clear LinkedIn enrichment + expertise data
        db.execute(
            text("""
                UPDATE people SET
                    linkedin_enriched = FALSE, linkedin_enriched_at = NULL,
                    linkedin_headline = NULL, linkedin_summary = NULL,
                    linkedin_experience = NULL, linkedin_education = NULL,
                    linkedin_skills = NULL, linkedin_experience_summary = NULL,
                    primary_expertise = NULL, justification = NULL,
                    matched_13_categories = NULL, sector = NULL,
                    geography = NULL, inferred_expertise_functional = NULL,
                    matched_inferred_expertise_topics = NULL, expertise_raw = NULL
                WHERE company_id = :cid
            """),
            {"cid": str(company_id)},
        )
        company.error_message = None
        company.updated_at = datetime.now(timezone.utc)

        if has_url_ids:
            # People with LinkedIn URLs → go straight to profile scraper, skip resolve
            company.status = "enriching"
            db.commit()
            from app.tasks.linkedin_task import enrich_linkedin_batch
            enrich_linkedin_batch.delay(str(company_id), has_url_ids, all_person_ids=person_ids)
        elif no_url_ids:
            # No one has URLs — need to resolve first
            company.status = "resolving"
            db.commit()
            from app.tasks.resolve_linkedin_task import resolve_linkedin_urls
            resolve_linkedin_urls.delay(str(company_id), person_ids)
        else:
            # No people at all — just re-analyze
            company.status = "analyzing"
            db.commit()
            from app.tasks.analyze_task import analyze_expertise_batch
            analyze_expertise_batch.delay(str(company_id), person_ids)

        return RetryResponse(status="ok", message=f"Re-enriching {len(person_ids)} people ({len(has_url_ids)} with URLs)")

    else:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {body.mode}")


@router.post("/companies/backfill-sectors", response_model=RetryResponse)
def backfill_sectors(db: Session = Depends(get_db)):
    """Re-analyze all people who have been analyzed but have an empty sector field."""
    people = db.query(Person).filter(
        Person.primary_expertise.isnot(None),
        (Person.sector.is_(None)) | (Person.sector == ""),
    ).all()

    if not people:
        return RetryResponse(status="ok", message="No people with missing sectors found")

    # Group by company
    by_company: dict[str, list[str]] = {}
    for p in people:
        cid = str(p.company_id)
        by_company.setdefault(cid, []).append(str(p.id))

    # Clear expertise for affected people so the analyzer re-processes them
    affected_ids = [p.id for p in people]
    db.execute(
        text("""
            UPDATE people SET
                primary_expertise = NULL, justification = NULL,
                matched_13_categories = NULL, sector = NULL,
                geography = NULL, inferred_expertise_functional = NULL,
                matched_inferred_expertise_topics = NULL, expertise_raw = NULL
            WHERE id = ANY(:ids)
        """),
        {"ids": affected_ids},
    )
    db.commit()

    # Dispatch analysis per company
    from app.tasks.analyze_task import analyze_expertise_batch
    for cid, pids in by_company.items():
        company = db.query(Company).filter(Company.id == cid).first()
        if company and company.status not in {"pending", "discovering", "scraping", "searching", "resolving", "enriching", "analyzing"}:
            company.status = "analyzing"
            company.updated_at = datetime.now(timezone.utc)
            db.commit()
        analyze_expertise_batch.delay(cid, pids)

    total = len(affected_ids)
    companies = len(by_company)
    return RetryResponse(
        status="ok",
        message=f"Re-analyzing {total} people across {companies} companies",
    )
