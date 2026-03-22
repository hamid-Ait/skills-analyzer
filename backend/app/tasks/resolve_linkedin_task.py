import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models import Company, Person
from app.services.apify_google_search import ApifyLinkedInEmployeesClient
from app.services.cost_tracker import log_usage, extract_apify_cost

log = logging.getLogger(__name__)


def _search_single(client, person_name, company_linkedin_url, company_id=None):
    """Search for a single person by name. Returns (name, profile_dict | None)."""
    try:
        result, run = client.search_person_by_name(person_name, company_linkedin_url)
        if run:
            cost = extract_apify_cost(client.client, run)
            log_usage(
                company_id=company_id,
                service="apify",
                provider="apify",
                model=client.ACTOR_ID,
                pipeline_step="linkedin_resolve",
                cost_usd=cost,
                metadata_json={"person_name": person_name},
            )
        return person_name, result
    except Exception as exc:
        log.warning(f"Search failed for {person_name}: {exc}")
        return person_name, None


def _apply_profile(person, profile):
    """Apply rich LinkedIn profile data to a Person model instance."""
    person.linkedin_url = profile.get("linkedin_url")
    if profile.get("linkedin_headline"):
        person.linkedin_headline = profile["linkedin_headline"]
    if profile.get("linkedin_summary"):
        person.linkedin_summary = profile["linkedin_summary"]
    if profile.get("linkedin_experience"):
        person.linkedin_experience = profile["linkedin_experience"]
    if profile.get("linkedin_education"):
        person.linkedin_education = profile["linkedin_education"]
    if profile.get("linkedin_skills"):
        person.linkedin_skills = profile["linkedin_skills"]
    if profile.get("linkedin_experience_summary"):
        person.linkedin_experience_summary = profile["linkedin_experience_summary"]
    if not person.image_url and profile.get("image_url"):
        person.image_url = profile["image_url"]
    if not person.location and profile.get("location"):
        person.location = profile["location"]
    if not person.bio and profile.get("bio"):
        person.bio = profile["bio"]
    person.linkedin_enriched = True
    person.linkedin_enriched_at = datetime.now(timezone.utc)
    person.updated_at = datetime.now(timezone.utc)


@celery_app.task(bind=True, max_retries=1, time_limit=3600)
def resolve_linkedin_urls(self, company_id: str, person_ids: list[str]):
    """
    Resolve missing LinkedIn URLs by searching each person by name
    using the company employees actor with searchQuery parameter.
    Uses parallel threads (max 4) for speed.
    Then chains to enrich_linkedin_batch.
    """
    db = SessionLocal()
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            log.error(f"Company {company_id} not found")
            return

        people = db.query(Person).filter(
            Person.id.in_(person_ids),
            Person.linkedin_url.is_(None),
        ).all()

        if not people:
            log.info(f"All people already have LinkedIn URLs for company {company_id}")
            _chain_enrichment(company_id, person_ids)
            return

        company_name = company.name or company.url
        company.status = "resolving"
        company.updated_at = datetime.now(timezone.utc)
        db.commit()
        log.info(f"Resolving LinkedIn URLs for {len(people)} people in {company_name}")

        client = ApifyLinkedInEmployeesClient()

        # Resolve company LinkedIn URL once
        if "linkedin.com/company/" in (company.url or ""):
            company_linkedin_url = company.url
        else:
            company_linkedin_url = client._resolve_linkedin_company_url(
                company_name, company.url
            )
            # Log Google search cost for company URL resolution
            if client._last_run:
                cost = extract_apify_cost(client.client, client._last_run)
                log_usage(
                    company_id=company_id,
                    service="apify",
                    provider="apify",
                    model=client.GOOGLE_ACTOR_ID,
                    pipeline_step="linkedin_resolve",
                    cost_usd=cost,
                )

        if not company_linkedin_url:
            log.warning(f"Could not find LinkedIn company page for {company_name}")
            _chain_enrichment(company_id, person_ids)
            return

        log.info(f"Using LinkedIn company URL: {company_linkedin_url}")

        # Search each person in parallel
        resolved = 0
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(
                    _search_single, client, p.name, company_linkedin_url, company_id
                ): p
                for p in people
            }
            for i, future in enumerate(as_completed(futures)):
                person = futures[future]
                name, profile = future.result()
                if profile:
                    _apply_profile(person, profile)
                    resolved += 1
                    log.info(f"  Resolved: {person.name} -> {profile.get('linkedin_url')}")

                if (i + 1) % 20 == 0:
                    db.commit()
                    log.info(f"  Progress: {resolved}/{len(people)} resolved so far")

        db.commit()
        log.info(f"Total LinkedIn URLs resolved: {resolved}/{len(people)} for {company_name}")

        # Chain to LinkedIn enrichment with ALL person_ids
        _chain_enrichment(company_id, person_ids)

    except Exception as exc:
        log.error(f"LinkedIn URL resolution failed for company {company_id}: {exc}", exc_info=True)
        # Don't block the pipeline — still chain to enrichment with whatever we have
        _chain_enrichment(company_id, person_ids)
    finally:
        db.close()


def _chain_enrichment(company_id: str, person_ids: list[str]):
    """Chain to LinkedIn enrichment for unenriched people, then to LLM analysis."""
    from app.tasks.linkedin_task import enrich_linkedin_batch
    db = SessionLocal()
    try:
        unenriched_ids = [
            str(p.id) for p in
            db.query(Person).filter(
                Person.id.in_(person_ids),
                Person.linkedin_url.isnot(None),
                Person.linkedin_enriched.is_(False),
            ).all()
        ]
        if unenriched_ids:
            # Enrich remaining profiles, then analyze ALL people
            enrich_linkedin_batch.delay(company_id, unenriched_ids, all_person_ids=person_ids)
        else:
            # All already enriched — go straight to LLM analysis with ALL people
            from app.tasks.analyze_task import analyze_expertise_batch
            analyze_expertise_batch.delay(company_id, person_ids)
    finally:
        db.close()
