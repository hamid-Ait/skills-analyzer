from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import Person, Company
from app.schemas.person import PersonBrief, PersonDetail, PersonList

router = APIRouter()


@router.get("/companies/{company_id}/people", response_model=PersonList)
def list_people(
    company_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    query = db.query(Person).filter(Person.company_id == company_id)
    if search:
        query = query.filter(
            Person.name.ilike(f"%{search}%") | Person.title.ilike(f"%{search}%")
        )
    if category:
        query = query.filter(Person.matched_13_categories.any(category))

    total = query.count()
    people = query.order_by(Person.name).offset((page - 1) * page_size).limit(page_size).all()

    return PersonList(
        items=[PersonBrief.model_validate(p) for p in people],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/people/{person_id}", response_model=PersonDetail)
def get_person(person_id: UUID, db: Session = Depends(get_db)):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    return PersonDetail.model_validate(person)
