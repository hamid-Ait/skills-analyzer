import logging
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import Person, Company, PersonAnalysisRun
from app.schemas.person import PersonBrief, PersonDetail, PersonList

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/providers")
def list_providers():
    from app.services.expertise_analyzer import SUPPORTED_PROVIDERS, PROVIDER_DEFAULT_MODELS
    return [
        {"provider": p, "default_model": PROVIDER_DEFAULT_MODELS.get(p, "")}
        for p in sorted(SUPPORTED_PROVIDERS)
    ]


class AnalyzeWithRequest(BaseModel):
    provider: str
    model: str | None = None


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


@router.post("/people/{person_id}/reanalyze")
def reanalyze_person(person_id: UUID, db: Session = Depends(get_db)):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    # Reset so the "already analyzed" guard in analyze_task.py doesn't skip this person
    person.primary_expertise = None
    db.commit()
    from app.tasks.analyze_task import analyze_expertise_batch
    analyze_expertise_batch.delay(str(person.company_id), [str(person.id)])
    return {"status": "queued", "person_id": str(person_id)}


@router.post("/people/{person_id}/analyze-with")
def analyze_person_with_provider(
    person_id: UUID,
    req: AnalyzeWithRequest,
    db: Session = Depends(get_db),
):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    from app.services.expertise_analyzer import (
        get_provider_by_name, format_people_for_analysis, _parse_llm_response, SUPPORTED_PROVIDERS,
    )
    from app.tasks.analyze_task import _build_person_entry

    if req.provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{req.provider}'. Supported: {sorted(SUPPORTED_PROVIDERS)}")

    company = db.query(Company).filter(Company.id == person.company_id).first()
    company_name = company.name if company else ""

    log.info(
        "analyze-with: person=%s (%s) provider=%s model=%s",
        person.name, person_id, req.provider, req.model or "default",
    )

    try:
        provider = get_provider_by_name(req.provider, model=req.model or None)
        entry = _build_person_entry(person, company_name=company_name)
        text = format_people_for_analysis([entry], company_name=company_name)
        raw = provider.analyze_batch(text)
        results = _parse_llm_response(raw)
    except ValueError as exc:
        log.error("analyze-with: bad request for %s — %s", person.name, exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        log.error("analyze-with: LLM call failed for %s — %s", person.name, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}")

    if not results:
        log.error(
            "analyze-with: unparseable response for %s (provider=%s). Raw: %s",
            person.name, req.provider, raw[:500],
        )
        raise HTTPException(
            status_code=502,
            detail=f"LLM returned an unparseable response. Raw (first 500 chars): {raw[:500]}",
        )
    result = results[0]

    if provider.last_usage:
        from app.services.cost_tracker import log_usage
        log.info(
            "analyze-with: %s → primary=%s | tokens in=%s out=%s",
            person.name,
            result.get("primary_expertise", "?"),
            provider.last_usage.get("input_tokens"),
            provider.last_usage.get("output_tokens"),
        )
        log_usage(
            company_id=str(person.company_id),
            service="llm",
            provider=req.provider,
            model=provider.last_usage.get("model"),
            pipeline_step="analysis_compare",
            input_tokens=provider.last_usage.get("input_tokens"),
            output_tokens=provider.last_usage.get("output_tokens"),
        )

    actual_model = getattr(provider, "model", None)
    max_version = (
        db.query(func.max(PersonAnalysisRun.version))
        .filter(
            PersonAnalysisRun.person_id == person.id,
            PersonAnalysisRun.provider == req.provider,
            PersonAnalysisRun.model == actual_model,
        )
        .scalar()
    ) or 0

    run = PersonAnalysisRun(
        person_id=person.id,
        provider=req.provider,
        model=actual_model,
        version=max_version + 1,
        result=result,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    return {
        "id": str(run.id),
        "person_id": str(person_id),
        "provider": run.provider,
        "model": run.model,
        "version": run.version,
        "result": run.result,
        "created_at": run.created_at.isoformat(),
    }


@router.get("/people/{person_id}/analysis-runs")
def list_analysis_runs(person_id: UUID, db: Session = Depends(get_db)):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    runs = (
        db.query(PersonAnalysisRun)
        .filter(PersonAnalysisRun.person_id == person_id)
        .order_by(PersonAnalysisRun.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(r.id),
            "provider": r.provider,
            "model": r.model,
            "version": r.version,
            "result": r.result,
            "created_at": r.created_at.isoformat(),
        }
        for r in runs
    ]
