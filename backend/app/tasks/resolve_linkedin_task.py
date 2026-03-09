import logging
from datetime import datetime, timezone
from difflib import SequenceMatcher

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models import Company, Person
from app.services.apify_google_search import ApifyLinkedInEmployeesClient

log = logging.getLogger(__name__)


def _normalize_name(name: str) -> str:
    """Normalize name for fuzzy matching."""
    return " ".join(name.lower().strip().split())


def _name_similarity(a: str, b: str) -> float:
    """Return similarity ratio between two names (0-1)."""
    return SequenceMatcher(None, _normalize_name(a), _normalize_name(b)).ratio()


def _match_employees_to_people(people: list, employees: list[dict], threshold: float = 0.8):
    """
    Match LinkedIn employees to website-scraped people by name.
    Returns list of (person, employee_dict) tuples for matches.
    """
    matches = []
    used_employees = set()

    for person in people:
        best_match = None
        best_score = 0

        for i, emp in enumerate(employees):
            if i in used_employees:
                continue
            score = _name_similarity(person.name, emp["name"])
            if score > best_score:
                best_score = score
                best_match = (i, emp)

        if best_match and best_score >= threshold:
            idx, emp = best_match
            used_employees.add(idx)
            matches.append((person, emp))

    return matches


@celery_app.task(bind=True, max_retries=1, time_limit=3600)
def resolve_linkedin_urls(self, company_id: str, person_ids: list[str]):
    """
    Resolve missing LinkedIn URLs for website-scraped people.
    Step 1: Fetch company employees from LinkedIn, match by name.
    Step 2: For remaining unmatched, Google search individual profiles.
    Then chain to enrich_linkedin_batch.
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
        resolved = 0

        # Step 1: Fetch company employees and match by name
        employees = client.search_company_people(company_name, company.url)
        if employees:
            matches = _match_employees_to_people(people, employees)
            for person, emp in matches:
                person.linkedin_url = emp.get("linkedin_url")
                # Save rich LinkedIn data from company employees actor
                if emp.get("linkedin_headline"):
                    person.linkedin_headline = emp["linkedin_headline"]
                if emp.get("linkedin_summary"):
                    person.linkedin_summary = emp["linkedin_summary"]
                if emp.get("linkedin_experience"):
                    person.linkedin_experience = emp["linkedin_experience"]
                if emp.get("linkedin_education"):
                    person.linkedin_education = emp["linkedin_education"]
                if emp.get("linkedin_skills"):
                    person.linkedin_skills = emp["linkedin_skills"]
                if emp.get("linkedin_experience_summary"):
                    person.linkedin_experience_summary = emp["linkedin_experience_summary"]
                if not person.image_url and emp.get("image_url"):
                    person.image_url = emp["image_url"]
                if not person.location and emp.get("location"):
                    person.location = emp["location"]
                if not person.bio and emp.get("bio"):
                    person.bio = emp["bio"]
                person.linkedin_enriched = True
                person.linkedin_enriched_at = datetime.now(timezone.utc)
                person.updated_at = datetime.now(timezone.utc)
                resolved += 1

            db.commit()
            log.info(
                f"Step 1 (company employees): matched {resolved}/{len(people)} "
                f"people from {len(employees)} LinkedIn employees"
            )

        # Step 2: Google search for remaining unmatched people
        still_missing = [p for p in people if not p.linkedin_url]
        if still_missing:
            log.info(f"Step 2 (Google search): resolving {len(still_missing)} remaining people")
            google_resolved = _google_search_linkedin_urls(
                client, still_missing, company_name, company.url, db
            )
            resolved += google_resolved

        log.info(f"Total LinkedIn URLs resolved: {resolved}/{len(people)} for {company_name}")

        # Chain to LinkedIn enrichment with ALL person_ids
        _chain_enrichment(company_id, person_ids)

    except Exception as exc:
        log.error(f"LinkedIn URL resolution failed for company {company_id}: {exc}", exc_info=True)
        # Don't block the pipeline — still chain to enrichment with whatever we have
        _chain_enrichment(company_id, person_ids)
    finally:
        db.close()


def _google_search_linkedin_urls(
    client: ApifyLinkedInEmployeesClient,
    people: list,
    company_name: str,
    company_url: str,
    db,
    batch_size: int = 10,
) -> int:
    """
    Search Google for LinkedIn profiles of individual people.
    Batches queries to reduce API calls.
    """
    from urllib.parse import urlparse
    domain = urlparse(company_url).netloc or company_url
    domain = domain.replace("www.", "")
    resolved = 0

    # Build search queries in batches
    for i in range(0, len(people), batch_size):
        batch = people[i:i + batch_size]
        queries = []
        for person in batch:
            # Use both company name and domain for better matching
            query = f'site:linkedin.com/in "{person.name}" "{company_name}" OR "{domain}"'
            queries.append({"person": person, "query": query})

        try:
            # Run all queries in one Google search actor call
            # The actor expects queries as a newline-separated string
            run_input = {
                "queries": "\n".join(q["query"] for q in queries),
                "maxPagesPerQuery": 1,
                "resultsPerPage": 3,
                "languageCode": "en",
                "mobileResults": False,
            }
            run = client.client.actor(client.GOOGLE_ACTOR_ID).call(run_input=run_input)
            dataset = client.client.dataset(run["defaultDatasetId"])
            items = list(dataset.iterate_items())

            # Match results back to people
            for item in items:
                search_query = item.get("searchQuery", {}).get("term", "")
                # Find which person this result is for
                person = None
                for q in queries:
                    if q["person"].name.lower() in search_query.lower():
                        person = q["person"]
                        break

                if not person or person.linkedin_url:
                    continue

                # Find first linkedin.com/in/ result
                for result in item.get("organicResults", []):
                    url = result.get("url", "")
                    if "linkedin.com/in/" in url:
                        person.linkedin_url = url.split("?")[0]  # Strip query params
                        person.updated_at = datetime.now(timezone.utc)
                        resolved += 1
                        log.info(f"  Google resolved: {person.name} -> {person.linkedin_url}")
                        break

            db.commit()

        except Exception as exc:
            log.warning(f"Google search batch failed: {exc}")

    return resolved


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