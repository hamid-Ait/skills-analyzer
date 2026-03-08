from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Company
from app.schemas.company import CompanyBrief, CompanyDetail, CompanyList

router = APIRouter()


TERMINAL_STATUSES = {"completed", "error"}


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
        items=[CompanyBrief.model_validate(c) for c in companies],
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
