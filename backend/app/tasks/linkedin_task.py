import logging
from datetime import datetime, timezone

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models import Person
from app.services.apify_linkedin import ApifyLinkedInClient
from app.tasks.analyze_task import _finalize_company, _update_company_error

log = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=1, time_limit=3600)
def enrich_linkedin_batch(self, company_id: str, person_ids: list[str]):
    """Enrich people records with LinkedIn data via Apify."""
    db = SessionLocal()
    try:
        people = db.query(Person).filter(Person.id.in_(person_ids)).all()
        if not people:
            _finalize_company(db, company_id)
            return

        # Build URL-to-person mapping
        url_to_person = {}
        urls = []
        for p in people:
            if p.linkedin_url and not p.linkedin_enriched:
                url_to_person[p.linkedin_url] = p
                urls.append(p.linkedin_url)

        if not urls:
            _finalize_company(db, company_id)
            return

        # Call Apify in batches of 50
        client = ApifyLinkedInClient()
        batch_size = 50
        enriched = 0

        for i in range(0, len(urls), batch_size):
            batch_urls = urls[i:i + batch_size]
            profiles = client.enrich_profiles(batch_urls)

            for profile in profiles:
                profile_url = profile.get("url") or profile.get("linkedinUrl") or ""
                # Match by URL
                person = None
                for url in url_to_person:
                    if url in profile_url or profile_url in url:
                        person = url_to_person[url]
                        break

                if not person:
                    continue

                fields = ApifyLinkedInClient.extract_profile_fields(profile)
                person.linkedin_headline = fields.get("linkedin_headline")
                person.linkedin_summary = fields.get("linkedin_summary")
                person.linkedin_experience = fields.get("linkedin_experience")
                person.linkedin_education = fields.get("linkedin_education")
                person.linkedin_skills = fields.get("linkedin_skills")
                person.linkedin_enriched = True
                person.linkedin_enriched_at = datetime.now(timezone.utc)
                person.updated_at = datetime.now(timezone.utc)
                enriched += 1

            db.commit()

        log.info(f"LinkedIn enriched {enriched}/{len(urls)} profiles for company {company_id}")
        _finalize_company(db, company_id)

    except Exception as exc:
        log.error(f"LinkedIn enrichment failed for company {company_id}: {exc}", exc_info=True)
        _update_company_error(db, company_id, f"LinkedIn enrichment: {exc}")
        raise
    finally:
        db.close()
