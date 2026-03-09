from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Company, Person
from app.schemas.company import CompanyBrief, CompanyDetail, CompanyList

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
