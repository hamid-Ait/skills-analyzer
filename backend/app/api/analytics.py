from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from pydantic import BaseModel

from app.database import get_db
from app.models import Person, Company


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------

class CategoryCount(BaseModel):
    name: str
    count: int
    percentage: float


class NameCount(BaseModel):
    name: str
    count: int


class CompanyStat(BaseModel):
    id: UUID
    name: Optional[str]
    url: str
    people_count: int
    analyzed_count: int
    linkedin_enriched_count: int
    photo_count: int


class OverviewResponse(BaseModel):
    total_companies: int
    total_people: int
    total_analyzed: int
    total_linkedin_enriched: int
    total_with_photo: int
    categories: list[CategoryCount]
    top_expertise: list[NameCount]
    sectors: list[NameCount]
    geographies: list[NameCount]
    company_stats: list[CompanyStat]


class HeatmapCompany(BaseModel):
    id: UUID
    name: Optional[str]
    categories: dict[str, int]


class HeatmapResponse(BaseModel):
    companies: list[HeatmapCompany]
    category_names: list[str]


class PersonSearchItem(BaseModel):
    id: UUID
    name: str
    title: Optional[str]
    location: Optional[str]
    image_url: Optional[str]
    linkedin_url: Optional[str]
    primary_expertise: Optional[str]
    matched_13_categories: Optional[list[str]]
    sector: Optional[str]
    geography: Optional[str]
    company_id: UUID
    company_name: Optional[str]


class PeopleSearchResponse(BaseModel):
    items: list[PersonSearchItem]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter()


@router.get("/analytics/overview", response_model=OverviewResponse)
def get_analytics_overview(db: Session = Depends(get_db)):
    """Aggregate stats across all completed companies."""

    # Per-company stats in a single query
    company_rows = db.execute(
        text("""
            SELECT
                c.id,
                c.name,
                c.url,
                COUNT(p.id) AS people_count,
                COUNT(p.id) FILTER (WHERE p.primary_expertise IS NOT NULL) AS analyzed_count,
                COUNT(p.id) FILTER (WHERE p.linkedin_enriched = TRUE) AS linkedin_enriched_count,
                COUNT(p.id) FILTER (WHERE p.image_url IS NOT NULL) AS photo_count
            FROM companies c
            LEFT JOIN people p ON p.company_id = c.id
            WHERE c.status = 'completed'
            GROUP BY c.id, c.name, c.url
            ORDER BY people_count DESC
        """)
    ).fetchall()

    if not company_rows:
        return OverviewResponse(
            total_companies=0, total_people=0, total_analyzed=0,
            total_linkedin_enriched=0, total_with_photo=0,
            categories=[], top_expertise=[], sectors=[], geographies=[],
            company_stats=[],
        )

    company_stats = []
    total_people = total_analyzed = total_linkedin = total_photo = 0
    for row in company_rows:
        company_stats.append(CompanyStat(
            id=row[0], name=row[1], url=row[2],
            people_count=row[3], analyzed_count=row[4],
            linkedin_enriched_count=row[5], photo_count=row[6],
        ))
        total_people += row[3]
        total_analyzed += row[4]
        total_linkedin += row[5]
        total_photo += row[6]

    # Category counts via unnest
    cat_rows = db.execute(
        text("""
            SELECT cat, COUNT(*) AS cnt
            FROM people p
            JOIN companies c ON c.id = p.company_id
            , unnest(p.matched_13_categories) AS cat
            WHERE c.status = 'completed'
              AND p.matched_13_categories IS NOT NULL
            GROUP BY cat
            ORDER BY cnt DESC
        """)
    ).fetchall()

    categories = []
    for name, count in cat_rows:
        pct = (count / total_analyzed * 100) if total_analyzed else 0
        categories.append(CategoryCount(name=name, count=count, percentage=round(pct, 1)))

    # Top expertise
    exp_rows = db.execute(
        text("""
            SELECT primary_expertise, COUNT(*) AS cnt
            FROM people p JOIN companies c ON c.id = p.company_id
            WHERE c.status = 'completed' AND primary_expertise IS NOT NULL
            GROUP BY primary_expertise ORDER BY cnt DESC LIMIT 20
        """)
    ).fetchall()
    top_expertise = [NameCount(name=n, count=c) for n, c in exp_rows]

    # Sectors
    sec_rows = db.execute(
        text("""
            SELECT sector, COUNT(*) AS cnt
            FROM people p JOIN companies c ON c.id = p.company_id
            WHERE c.status = 'completed' AND sector IS NOT NULL
            GROUP BY sector ORDER BY cnt DESC LIMIT 15
        """)
    ).fetchall()
    sectors = [NameCount(name=n, count=c) for n, c in sec_rows]

    # Geographies
    geo_rows = db.execute(
        text("""
            SELECT geography, COUNT(*) AS cnt
            FROM people p JOIN companies c ON c.id = p.company_id
            WHERE c.status = 'completed' AND geography IS NOT NULL
            GROUP BY geography ORDER BY cnt DESC LIMIT 15
        """)
    ).fetchall()
    geographies = [NameCount(name=n, count=c) for n, c in geo_rows]

    return OverviewResponse(
        total_companies=len(company_rows),
        total_people=total_people,
        total_analyzed=total_analyzed,
        total_linkedin_enriched=total_linkedin,
        total_with_photo=total_photo,
        categories=categories,
        top_expertise=top_expertise,
        sectors=sectors,
        geographies=geographies,
        company_stats=company_stats,
    )


@router.get("/analytics/heatmap", response_model=HeatmapResponse)
def get_analytics_heatmap(db: Session = Depends(get_db)):
    """Companies x categories matrix for the expertise heatmap."""

    rows = db.execute(
        text("""
            SELECT c.id, c.name, cat, COUNT(*) AS cnt
            FROM companies c
            JOIN people p ON p.company_id = c.id
            , unnest(p.matched_13_categories) AS cat
            WHERE c.status = 'completed'
              AND p.matched_13_categories IS NOT NULL
            GROUP BY c.id, c.name, cat
            ORDER BY c.name, cnt DESC
        """)
    ).fetchall()

    company_map: dict = {}
    all_categories: set[str] = set()

    for company_id, company_name, cat, cnt in rows:
        all_categories.add(cat)
        if company_id not in company_map:
            company_map[company_id] = HeatmapCompany(
                id=company_id, name=company_name, categories={},
            )
        company_map[company_id].categories[cat] = cnt

    return HeatmapResponse(
        companies=list(company_map.values()),
        category_names=sorted(all_categories),
    )


@router.get("/analytics/search", response_model=PeopleSearchResponse)
def search_people(
    q: Optional[str] = Query(None, description="Search by name, title, or expertise"),
    category: Optional[str] = Query(None, description="Filter by category"),
    sector: Optional[str] = Query(None, description="Filter by sector"),
    geography: Optional[str] = Query(None, description="Filter by geography"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Global people search across all completed companies."""

    clauses = ["c.status = 'completed'"]
    params: dict = {}

    if q:
        clauses.append(
            "(p.name ILIKE :q OR p.title ILIKE :q OR p.primary_expertise ILIKE :q)"
        )
        params["q"] = f"%{q}%"

    if category:
        clauses.append(":category = ANY(p.matched_13_categories)")
        params["category"] = category

    if sector:
        clauses.append("p.sector ILIKE :sector")
        params["sector"] = f"%{sector}%"

    if geography:
        clauses.append("p.geography ILIKE :geography")
        params["geography"] = f"%{geography}%"

    where = " AND ".join(clauses)
    offset = (page - 1) * page_size

    total = db.execute(
        text(f"""
            SELECT COUNT(*)
            FROM people p JOIN companies c ON c.id = p.company_id
            WHERE {where}
        """),
        params,
    ).scalar() or 0

    rows = db.execute(
        text(f"""
            SELECT
                p.id, p.name, p.title, p.location, p.image_url,
                p.linkedin_url, p.primary_expertise, p.matched_13_categories,
                p.sector, p.geography, p.company_id, c.name AS company_name
            FROM people p
            JOIN companies c ON c.id = p.company_id
            WHERE {where}
            ORDER BY p.name
            LIMIT :limit OFFSET :offset
        """),
        {**params, "limit": page_size, "offset": offset},
    ).fetchall()

    items = [
        PersonSearchItem(
            id=r[0], name=r[1], title=r[2], location=r[3], image_url=r[4],
            linkedin_url=r[5], primary_expertise=r[6], matched_13_categories=r[7],
            sector=r[8], geography=r[9], company_id=r[10], company_name=r[11],
        )
        for r in rows
    ]

    return PeopleSearchResponse(
        items=items, total=total, page=page, page_size=page_size,
    )