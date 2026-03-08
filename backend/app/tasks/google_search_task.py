import logging
from datetime import datetime, timezone

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models import Company, Person
from app.services.apify_google_search import ApifyLinkedInEmployeesClient

log = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=1, time_limit=3600)
def search_people_fallback(self, company_id: str, enrich_linkedin: bool = False):
    """
    Fallback: when website scraping finds no people, fetch employees
    from LinkedIn via Apify harvestapi/linkedin-company-employees.
    """
    db = SessionLocal()
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            log.error(f"Company {company_id} not found")
            return

        company_name = company.name or company.url
        client = ApifyLinkedInEmployeesClient()
        profiles = client.search_company_people(company_name, company.url)

        if not profiles:
            log.info(f"LinkedIn employees search found no people for company {company_id}")
            from app.tasks.analyze_task import _finalize_company
            from app.tasks.scrape_task import _update_company
            _update_company(db, company_id, status="completed", people_count=0)
            _finalize_company(db, company_id)
            return

        # Insert people from LinkedIn employees search
        person_ids = []
        for p in profiles:
            person = Person(
                company_id=company.id,
                name=p["name"],
                title=p.get("title"),
                bio=p.get("bio"),
                linkedin_url=p.get("linkedin_url"),
                image_url=p.get("image_url"),
                location=p.get("location"),
                data_source="LinkedIn (Apify)",
                source_url="linkedin-employees-fallback",
                raw_data_json=p,
            )
            db.add(person)
            db.flush()
            person_ids.append(str(person.id))

        from app.tasks.scrape_task import _update_company
        _update_company(
            db, company_id,
            status="analyzing",
            people_count=len(person_ids),
        )
        db.commit()
        log.info(f"Inserted {len(person_ids)} people from LinkedIn for company {company_id}")

        # Skip LinkedIn enrichment — data already comes from LinkedIn
        from app.tasks.analyze_task import analyze_expertise_batch
        analyze_expertise_batch.delay(company_id, person_ids, enrich_linkedin=False)

    except Exception as exc:
        log.error(f"LinkedIn employees fallback failed for company {company_id}: {exc}", exc_info=True)
        from app.tasks.analyze_task import _update_company_error
        _update_company_error(db, company_id, f"LinkedIn employees fallback: {exc}")
        raise
    finally:
        db.close()