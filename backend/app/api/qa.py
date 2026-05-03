from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.company import Company
from app.models.person import Person
from app.services.qa_validator import QAThresholds, ValidationResult, categorize_issue, validate_person

router = APIRouter(prefix="/qa", tags=["QA"])


def _thresholds() -> QAThresholds:
    return QAThresholds(
        max_l1_categories=settings.QA_MAX_L1_CATEGORIES,
        max_declared_capabilities=settings.QA_MAX_DECLARED_CAPABILITIES,
        max_inferred=settings.QA_MAX_INFERRED,
        max_topics=settings.QA_MAX_TOPICS,
    )


def _validate_all(
    db: Session,
    company_id: Optional[str],
    thresholds: QAThresholds,
) -> list[tuple[Person, str, ValidationResult]]:
    """Return (person, company_name, result) for all analyzed people."""
    q = (
        db.query(Person, Company.name.label("company_name"))
        .join(Company, Person.company_id == Company.id)
        .filter(Person.expertise_raw.isnot(None))
    )
    if company_id:
        q = q.filter(Person.company_id == company_id)

    return [
        (person, company_name, validate_person(person, thresholds))
        for person, company_name in q.order_by(Person.name).all()
    ]


@router.get("/summary")
def qa_summary(
    company_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    thresholds = _thresholds()
    rows = _validate_all(db, company_id, thresholds)

    issue_counts: dict[str, int] = {}
    status_counts = {"failed": 0, "flagged": 0, "clean": 0}

    for _, _, result in rows:
        status_counts[result.status] += 1
        for msg in result.hard_failures + result.soft_warnings:
            key = categorize_issue(msg)
            issue_counts[key] = issue_counts.get(key, 0) + 1

    return {
        "total_analyzed": len(rows),
        "total_failed": status_counts["failed"],
        "total_flagged": status_counts["flagged"],
        "total_clean": status_counts["clean"],
        "issue_type_counts": issue_counts,
        "thresholds": {
            "max_l1_categories": thresholds.max_l1_categories,
            "max_declared_capabilities": thresholds.max_declared_capabilities,
            "max_inferred": thresholds.max_inferred,
            "max_topics": thresholds.max_topics,
        },
    }


@router.get("/issues")
def qa_issues(
    company_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="failed | flagged | clean"),
    issue_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    thresholds = _thresholds()
    all_rows = _validate_all(db, company_id, thresholds)

    # Aggregate counts before filtering
    status_counts = {"failed": 0, "flagged": 0, "clean": 0}
    for _, _, r in all_rows:
        status_counts[r.status] += 1

    # Apply filters
    filtered = []
    for person, company_name, result in all_rows:
        if status and result.status != status:
            continue
        if issue_type:
            all_msgs = result.hard_failures + result.soft_warnings
            if not any(categorize_issue(m) == issue_type for m in all_msgs):
                continue
        filtered.append({
            "person_id": str(person.id),
            "person_name": person.name,
            "company_id": str(person.company_id),
            "company_name": company_name,
            "status": result.status,
            "hard_failures": result.hard_failures,
            "soft_warnings": result.soft_warnings,
        })

    total = len(filtered)
    start = (page - 1) * page_size
    items = filtered[start: start + page_size]

    return {
        "items": items,
        "total": total,
        "total_failed": status_counts["failed"],
        "total_flagged": status_counts["flagged"],
        "total_clean": status_counts["clean"],
        "page": page,
        "page_size": page_size,
    }


@router.post("/reanalyze")
def qa_reanalyze(
    company_id: Optional[str] = Body(None),
    status: Optional[str] = Body(None, description="failed | flagged | clean"),
    issue_type: Optional[str] = Body(None),
    db: Session = Depends(get_db),
):
    """Queue re-analysis for all profiles matching the given QA filters."""
    from app.tasks.analyze_task import analyze_expertise_batch

    if not status and not issue_type and not company_id:
        raise HTTPException(
            status_code=400,
            detail="At least one filter (status, issue_type, or company_id) is required.",
        )

    thresholds = _thresholds()
    all_rows = _validate_all(db, company_id, thresholds)

    # Collect matching person IDs grouped by company
    by_company: dict[str, list[str]] = {}
    for person, _, result in all_rows:
        if status and result.status != status:
            continue
        if issue_type:
            all_msgs = result.hard_failures + result.soft_warnings
            if not any(categorize_issue(m) == issue_type for m in all_msgs):
                continue
        cid = str(person.company_id)
        by_company.setdefault(cid, []).append(str(person.id))

    if not by_company:
        return {"queued": 0, "companies": []}

    # Reset primary_expertise so the analysis task doesn't skip already-analyzed people
    all_ids = [pid for ids in by_company.values() for pid in ids]
    db.query(Person).filter(Person.id.in_(all_ids)).update(
        {"primary_expertise": None, "updated_at": datetime.now(timezone.utc)},
        synchronize_session=False,
    )
    db.commit()

    # Queue one Celery task per company
    for cid, person_ids in by_company.items():
        analyze_expertise_batch.delay(cid, person_ids)

    return {
        "queued": len(all_ids),
        "companies": list(by_company.keys()),
    }


@router.post("/validate/{person_id}")
def validate_single(person_id: str, db: Session = Depends(get_db)):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Person not found")

    thresholds = _thresholds()
    result = validate_person(person, thresholds)
    return {
        "person_id": person_id,
        "person_name": person.name,
        "status": result.status,
        "hard_failures": result.hard_failures,
        "soft_warnings": result.soft_warnings,
    }