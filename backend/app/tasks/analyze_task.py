import logging
from datetime import datetime, timezone

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models import Job, Company, Person
from app.services.expertise_analyzer import (
    analyze_batch_by_name, format_people_for_analysis, get_provider,
    _parse_llm_response, _normalize_name,
)

log = logging.getLogger(__name__)

BATCH_SIZE = 50


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
    """Write LLM result fields onto a Person record."""
    person.primary_expertise = result.get("primary_expertise")
    person.justification = result.get("justification")
    person.matched_13_categories = result.get("matched_13_categories", [])
    person.sector = result.get("sector")
    person.geography = result.get("geography")
    person.inferred_expertise_functional = result.get("inferred_expertise_functional")
    person.matched_inferred_expertise_topics = result.get("matched_inferred_expertise_topics", [])
    person.expertise_raw = result
    person.updated_at = datetime.now(timezone.utc)


@celery_app.task(bind=True, max_retries=1, time_limit=72000)
def analyze_expertise_batch(self, company_id: str, person_ids: list[str]):
    """Analyze expertise for all people in a company using LLM.

    Processes in batches of BATCH_SIZE, matching results by name and
    committing to DB after each batch so progress is never lost.
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

        # Build name → Person lookup for matching LLM results back
        name_to_people: dict[str, list[Person]] = {}
        for p in people:
            norm = _normalize_name(p.name or "")
            name_to_people.setdefault(norm, []).append(p)

        # Process in batches
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
                results = _parse_llm_response(raw_response)

                # Match by name
                batch_updated = 0
                matched_by_name = 0
                for result in results:
                    result_name = result.get("name", "")
                    if not result_name or not result.get("primary_expertise"):
                        continue
                    norm = _normalize_name(result_name)
                    candidates = name_to_people.get(norm, [])
                    for person in candidates:
                        if person.primary_expertise is None:
                            _apply_result(person, result)
                            batch_updated += 1
                            matched_by_name += 1
                            break

                # Fallback: positional matching for results without names
                if matched_by_name == 0 and len(results) == len(batch):
                    log.warning(f"  Batch {batch_num}: no name matches, using positional fallback")
                    for person, result in zip(batch, results):
                        if result and result.get("primary_expertise") and person.primary_expertise is None:
                            _apply_result(person, result)
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