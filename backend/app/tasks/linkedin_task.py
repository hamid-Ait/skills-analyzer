import logging
from datetime import datetime, timezone

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models import Company, Person
from app.services.apify_linkedin import ApifyLinkedInClient

log = logging.getLogger(__name__)


def _build_experience_summary(experience: list[dict]) -> str:
    """Build a text summary from the first 5 LinkedIn experience entries."""
    if not experience:
        return "—"
    lines = []
    for exp in experience[:5]:
        position = exp.get("position") or exp.get("title") or ""
        company = exp.get("companyName") or ""
        duration = exp.get("duration") or ""
        location = exp.get("location") or ""
        parts = [p for p in [position, company, duration, location] if p]
        if parts:
            lines.append("\n".join(parts))
    return "\n".join(lines) if lines else "—"


@celery_app.task(bind=True, max_retries=1, time_limit=14400, soft_time_limit=13800)
def enrich_linkedin_batch(self, company_id: str, person_ids: list[str],
                          all_person_ids: list[str] | None = None):
    """Enrich people records with LinkedIn data via Apify.

    person_ids: people to enrich (must have linkedin_url, not yet enriched)
    all_person_ids: all people for the company (passed to next task in chain)
    """
    # Use all_person_ids for chaining; fall back to person_ids
    chain_ids = all_person_ids or person_ids
    db = SessionLocal()
    try:
        people = db.query(Person).filter(Person.id.in_(person_ids)).all()
        if not people:
            from app.tasks.analyze_task import analyze_expertise_batch
            analyze_expertise_batch.delay(company_id, chain_ids)
            return

        # Build URL-to-person mapping
        url_to_person = {}
        urls = []
        for p in people:
            if p.linkedin_url and not p.linkedin_enriched:
                url_to_person[p.linkedin_url] = p
                urls.append(p.linkedin_url)

        if not urls:
            from app.tasks.analyze_task import analyze_expertise_batch
            analyze_expertise_batch.delay(company_id, chain_ids)
            return

        log.info(f"Enriching {len(urls)} LinkedIn profiles for company {company_id}")

        # Update company status
        company = db.query(Company).filter(Company.id == company_id).first()
        if company:
            company.status = "enriching"
            company.updated_at = datetime.now(timezone.utc)
            db.commit()

        # Call Apify in batches of 50
        client = ApifyLinkedInClient()
        batch_size = 50
        enriched = 0

        for i in range(0, len(urls), batch_size):
            batch_urls = urls[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(urls) + batch_size - 1) // batch_size
            log.info(f"  Enrichment batch {batch_num}/{total_batches} ({len(batch_urls)} profiles)")

            try:
                profiles = client.enrich_profiles(batch_urls)
            except Exception as exc:
                log.warning(f"  Batch {batch_num} failed: {exc} — continuing with next batch")
                continue

            for profile in profiles:
                profile_url = profile.get("linkedinUrl") or profile.get("url") or ""
                # Also check originalQuery for the input URL we sent
                original_url = (profile.get("originalQuery") or {}).get("query", "")
                # Match by URL
                person = None
                for url in url_to_person:
                    if (url in profile_url or profile_url in url
                            or url in original_url or original_url in url):
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
                person.linkedin_experience_summary = _build_experience_summary(
                    fields.get("linkedin_experience") or []
                )
                # Fill gaps from LinkedIn data
                if not person.location and fields.get("location"):
                    person.location = fields["location"]
                if not person.image_url and fields.get("image_url"):
                    person.image_url = fields["image_url"]
                person.linkedin_enriched = True
                person.linkedin_enriched_at = datetime.now(timezone.utc)
                person.updated_at = datetime.now(timezone.utc)
                enriched += 1

            db.commit()
            log.info(f"  Batch {batch_num} done — {enriched} enriched so far")

        log.info(f"LinkedIn enriched {enriched}/{len(urls)} profiles for company {company_id}")

        # Chain to LLM expertise analysis now that we have full LinkedIn data
        from app.tasks.analyze_task import analyze_expertise_batch
        analyze_expertise_batch.delay(company_id, chain_ids)

    except Exception as exc:
        log.error(f"LinkedIn enrichment failed for company {company_id}: {exc}", exc_info=True)
        # Still chain to analysis with whatever we have — partial enrichment is better than none
        from app.tasks.analyze_task import analyze_expertise_batch
        analyze_expertise_batch.delay(company_id, chain_ids)
    finally:
        db.close()
