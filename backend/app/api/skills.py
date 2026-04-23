from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from app.database import get_db
from app.models import Person, Company
from app.schemas.skills import SkillsMatrix, CategoryCount, ExpertiseCount

router = APIRouter()


@router.get("/companies/{company_id}/skills-matrix", response_model=SkillsMatrix)
def get_skills_matrix(company_id: UUID, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    total_people = db.query(func.count(Person.id)).filter(Person.company_id == company_id).scalar() or 0
    total_analyzed = db.query(func.count(Person.id)).filter(
        Person.company_id == company_id,
        Person.primary_expertise.isnot(None),
    ).scalar() or 0

    # Category counts via unnest
    cat_rows = db.execute(
        text("""
            SELECT cat, COUNT(*) as cnt
            FROM people, unnest(matched_13_categories) AS cat
            WHERE company_id = :cid AND matched_13_categories IS NOT NULL
            GROUP BY cat
            ORDER BY cnt DESC
        """),
        {"cid": str(company_id)},
    ).fetchall()

    categories = []
    for name, count in cat_rows:
        pct = (count / total_analyzed * 100) if total_analyzed else 0
        categories.append(CategoryCount(name=name, count=count, percentage=round(pct, 1)))

    # Top expertise
    exp_rows = db.execute(
        text("""
            SELECT primary_expertise, COUNT(*) as cnt
            FROM people
            WHERE company_id = :cid AND primary_expertise IS NOT NULL
            GROUP BY primary_expertise
            ORDER BY cnt DESC
            LIMIT 20
        """),
        {"cid": str(company_id)},
    ).fetchall()
    top_expertise = [ExpertiseCount(name=name, count=count) for name, count in exp_rows]

    # Sectors (split semicolon-separated values into individual sectors)
    sec_rows = db.execute(
        text("""
            SELECT TRIM(s) AS sector, COUNT(*) AS cnt
            FROM people, regexp_split_to_table(sector, ';') AS s
            WHERE company_id = :cid AND sector IS NOT NULL
            GROUP BY TRIM(s)
            ORDER BY cnt DESC
            LIMIT 15
        """),
        {"cid": str(company_id)},
    ).fetchall()
    sectors = [ExpertiseCount(name=name, count=count) for name, count in sec_rows]

    # Geographies (split semicolon-separated values into individual geographies)
    geo_rows = db.execute(
        text("""
            SELECT TRIM(g) AS geography, COUNT(*) AS cnt
            FROM people, regexp_split_to_table(geography, ';') AS g
            WHERE company_id = :cid AND geography IS NOT NULL
            GROUP BY TRIM(g)
            ORDER BY cnt DESC
            LIMIT 15
        """),
        {"cid": str(company_id)},
    ).fetchall()
    geographies = [ExpertiseCount(name=name, count=count) for name, count in geo_rows]

    return SkillsMatrix(
        total_people=total_people,
        total_analyzed=total_analyzed,
        categories=categories,
        top_expertise=top_expertise,
        sectors=sectors,
        geographies=geographies,
    )
