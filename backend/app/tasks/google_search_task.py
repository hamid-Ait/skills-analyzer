import logging
from datetime import datetime, timezone

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models import Company, Person
from app.services.apify_google_search import ApifyLinkedInEmployeesClient
from app.services.cost_tracker import log_usage, extract_apify_cost

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

        # Log Apify cost for bulk employee fetch
        if client._last_run:
            cost = extract_apify_cost(client.client, client._last_run)
            log_usage(
                company_id=company_id,
                service="apify",
                provider="apify",
                model=client.ACTOR_ID,
                pipeline_step="team_discovery",
                cost_usd=cost,
            )

        if not profiles:
            log.info(f"LinkedIn employees search found no people for company {company_id}")
            from app.tasks.analyze_task import _finalize_company
            from app.tasks.scrape_task import _update_company
            _update_company(db, company_id, status="completed", people_count=0)
            _finalize_company(db, company_id)
            return

        # Insert people from LinkedIn employees search (includes full profile data)
        person_ids = []
        for p in profiles:
            person = Person(
                company_id=company.id,
                name=p["name"],
                title=p.get("title"),
                bio=p.get("bio"),
                linkedin_url=p.get("linkedin_url"),
                linkedin_headline=p.get("linkedin_headline"),
                linkedin_summary=p.get("linkedin_summary"),
                linkedin_experience=p.get("linkedin_experience"),
                linkedin_education=p.get("linkedin_education"),
                linkedin_skills=p.get("linkedin_skills"),
                linkedin_experience_summary=p.get("linkedin_experience_summary"),
                linkedin_enriched=True,
                linkedin_enriched_at=datetime.now(timezone.utc),
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

        # Data already rich from company employees actor — go to LLM analysis
        from app.tasks.analyze_task import analyze_expertise_batch
        analyze_expertise_batch.delay(company_id, person_ids)

    except Exception as exc:
        log.error(f"LinkedIn employees fallback failed for company {company_id}: {exc}", exc_info=True)
        from app.tasks.analyze_task import _update_company_error
        _update_company_error(db, company_id, f"LinkedIn employees fallback: {exc}")
        raise
    finally:
        db.close()