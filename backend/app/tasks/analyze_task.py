import logging
from datetime import datetime, timezone

from app.tasks.celery_app import celery_app
from app.config import settings
from app.database import SessionLocal
from app.models import Job, Company, Person
from app.services.expertise_analyzer import (
    format_people_for_analysis, get_provider,
    _parse_llm_response, _normalize_name,
)
from app.services.keyword_matcher import match_person_from_db
from app.services.expertise_merger import merge, merge_keyword_only
from app.services.cost_tracker import log_usage

log = logging.getLogger(__name__)

BATCH_SIZE = 10


def _build_person_entry(p: Person) -> dict:
    """Build the data dict sent to the LLM for a single person."""
    entry = {
        "name": p.name,
        "title": p.title,
        "department": p.department,
        "bio": p.bio,
        "location": p.location,
    }
    if p.linkedin_headline:
        entry["linkedin_headline"] = p.linkedin_headline
    if p.linkedin_summary:
        entry["linkedin_summary"] = p.linkedin_summary
    if p.linkedin_experience_summary:
        entry["linkedin_experience_summary"] = p.linkedin_experience_summary
    if p.linkedin_skills:
        entry["linkedin_skills"] = p.linkedin_skills
    return entry


def _apply_result(person: Person, result: dict):
    """Write merged result fields onto a Person record."""
    person.primary_expertise = result.get("primary_expertise")
    person.justification = result.get("justification")
    # Support both old (matched_13_categories) and new (explicit_expertise_13) field names
    person.matched_13_categories = (
        result.get("explicit_expertise_13")
        or result.get("matched_13_categories", [])
    )
    # Sectors/geographies: new prompt returns arrays, DB column is Text
    sectors = result.get("sectors") or result.get("sector")
    if isinstance(sectors, list):
        sectors = "; ".join(sectors) if sectors else None
    person.sector = sectors
    geographies = result.get("geographies") or result.get("geography")
    if isinstance(geographies, list):
        geographies = "; ".join(geographies) if geographies else None
    person.geography = geographies
    func = result.get("inferred_expertise_functional", [])
    if isinstance(func, str):
        func = [f.strip() for f in func.split(",") if f.strip()]
    person.inferred_expertise_functional = func
    person.matched_inferred_expertise_topics = (
        result.get("topic_overlap")
        or result.get("matched_inferred_expertise_topics", [])
    )
    person.expertise_raw = result
    person.updated_at = datetime.now(timezone.utc)


@celery_app.task(bind=True, max_retries=1, time_limit=72000)
def analyze_expertise_batch(self, company_id: str, person_ids: list[str]):
    """Analyze expertise using hybrid keyword + LLM approach.

    For each batch:
    1. Run keyword matching (fast, deterministic)
    2. Run LLM classification (semantic, contextual)
    3. Merge results with taxonomy validation
    4. Store to DB
    """
    db = SessionLocal()
    try:
        people = db.query(Person).filter(Person.id.in_(person_ids)).all()
        if not people:
            log.warning(f"No people found for company {company_id}")
            _finalize_company(db, company_id)
            return

        company = db.query(Company).filter(Company.id == company_id).first()
        if company:
            company.status = "analyzing"
            company.updated_at = datetime.now(timezone.utc)
            db.commit()

        # Step 1: Run keyword matching for all people upfront (fast)
        keyword_results: dict[str, object] = {}
        for p in people:
            norm = _normalize_name(p.name or "")
            keyword_results[norm] = match_person_from_db(p)

        # Step 2: Process in LLM batches
        provider = get_provider()
        total_updated = 0
        total_batches = (len(people) + BATCH_SIZE - 1) // BATCH_SIZE

        for batch_idx in range(0, len(people), BATCH_SIZE):
            batch = people[batch_idx:batch_idx + BATCH_SIZE]
            batch_num = batch_idx // BATCH_SIZE + 1
            batch_data = [_build_person_entry(p) for p in batch]
            text = format_people_for_analysis(batch_data)

            try:
                raw_response = provider.analyze_batch(text)

                # Log LLM usage
                if provider.last_usage:
                    log_usage(
                        company_id=company_id,
                        service="llm",
                        provider=settings.LLM_PROVIDER,
                        model=provider.last_usage.get("model"),
                        pipeline_step="analysis",
                        input_tokens=provider.last_usage.get("input_tokens"),
                        output_tokens=provider.last_usage.get("output_tokens"),
                    )

                results = _parse_llm_response(raw_response)

                # Build name → LLM result mapping for this batch
                llm_by_name: dict[str, dict] = {}
                for result in results:
                    result_name = result.get("name", "")
                    if result_name:
                        llm_by_name[_normalize_name(result_name)] = result

                # Positional fallback if LLM returned no names
                if not llm_by_name and len(results) == len(batch):
                    log.warning(f"  Batch {batch_num}: no name matches, using positional fallback")
                    for person, result in zip(batch, results):
                        norm = _normalize_name(person.name or "")
                        if norm:
                            llm_by_name[norm] = result

                # Step 3: Merge keyword + LLM for each person in this batch
                batch_updated = 0
                for person in batch:
                    norm = _normalize_name(person.name or "")
                    if person.primary_expertise is not None:
                        continue  # Already analyzed

                    kw_result = keyword_results.get(norm)
                    llm_result = llm_by_name.get(norm, {})

                    if kw_result and llm_result:
                        merged = merge(kw_result, llm_result)
                    elif llm_result:
                        merged = llm_result
                    elif kw_result:
                        merged = merge_keyword_only(kw_result)
                    else:
                        continue

                    _apply_result(person, merged)
                    batch_updated += 1

                total_updated += batch_updated
                db.commit()
                log.info(
                    f"  Batch {batch_num}/{total_batches}: "
                    f"{batch_updated}/{len(batch)} updated (total: {total_updated})"
                )

            except Exception as exc:
                log.error(f"  Batch {batch_num}/{total_batches} failed: {exc}")
                db.rollback()

        log.info(f"Analysis complete: {total_updated}/{len(people)} people for company {company_id}")
        _finalize_company(db, company_id)

    except Exception as exc:
        log.error(f"Expertise analysis failed for company {company_id}: {exc}", exc_info=True)
        _update_company_error(db, company_id, str(exc))
        raise
    finally:
        db.close()


def _finalize_company(db, company_id: str):
    """Mark company as completed and update job progress."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if company:
        company.status = "completed"
        company.updated_at = datetime.now(timezone.utc)

        job = db.query(Job).filter(Job.id == company.job_id).first()
        if job:
            job.completed_urls += 1
            if job.completed_urls >= job.total_urls:
                job.status = "completed"
            job.updated_at = datetime.now(timezone.utc)

        db.commit()
        log.info(f"Company {company_id} completed")


def _update_company_error(db, company_id: str, error: str):
    company = db.query(Company).filter(Company.id == company_id).first()
    if company:
        company.status = "error"
        company.error_message = error[:2000]
        company.updated_at = datetime.now(timezone.utc)

        job = db.query(Job).filter(Job.id == company.job_id).first()
        if job:
            job.completed_urls += 1
            if job.completed_urls >= job.total_urls:
                job.status = "completed"
            job.updated_at = datetime.now(timezone.utc)

        db.commit()