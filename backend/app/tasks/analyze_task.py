import logging
from datetime import datetime, timezone

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models import Job, Company, Person
from app.services.expertise_analyzer import analyze_people

log = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=1, time_limit=3600)
def analyze_expertise_batch(self, company_id: str, person_ids: list[str],
                            enrich_linkedin: bool = False):
    """Analyze expertise for all people in a company using LLM."""
    db = SessionLocal()
    try:
        people = db.query(Person).filter(Person.id.in_(person_ids)).all()
        if not people:
            log.warning(f"No people found for company {company_id}")
            _finalize_company(db, company_id)
            return

        # Prepare data for LLM
        people_data = []
        for p in people:
            people_data.append({
                "name": p.name,
                "title": p.title,
                "department": p.department,
                "bio": p.bio,
                "location": p.location,
            })

        # Run LLM analysis in batches
        results = analyze_people(people_data, batch_size=15)

        # Update database
        updated = 0
        for person, result in zip(people, results):
            if not result:
                continue
            person.primary_expertise = result.get("primary_expertise")
            person.justification = result.get("justification")
            person.matched_13_categories = result.get("matched_13_categories", [])
            person.sector = result.get("sector")
            person.geography = result.get("geography")
            person.inferred_expertise_functional = result.get("inferred_expertise_functional")
            person.matched_inferred_expertise_topics = result.get("matched_inferred_expertise_topics", [])
            person.expertise_raw = result
            person.updated_at = datetime.now(timezone.utc)
            updated += 1

        db.commit()
        log.info(f"Updated expertise for {updated}/{len(people)} people in company {company_id}")

        # Chain LinkedIn enrichment if requested
        if enrich_linkedin:
            from app.tasks.linkedin_task import enrich_linkedin_batch
            linkedin_ids = [str(p.id) for p in people if p.linkedin_url]
            if linkedin_ids:
                enrich_linkedin_batch.delay(company_id, linkedin_ids)
            else:
                _finalize_company(db, company_id)
        else:
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
