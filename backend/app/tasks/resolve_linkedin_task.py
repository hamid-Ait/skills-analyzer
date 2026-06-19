import logging
import re
import unicodedata
import difflib
from datetime import datetime, timezone
from typing import Optional

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models import Company, Person
from app.services.apify_google_search import ApifyLinkedInEmployeesClient
from app.services.cost_tracker import log_usage, extract_apify_cost

log = logging.getLogger(__name__)

_TITLE_PREFIX_RE = re.compile(
    r"^\s*(sir|dame|lord|lady|dr|prof|mr|mrs|ms|rev|gen|col|maj|adm|amb|hon)\.?\s+",
    re.IGNORECASE,
)
_SUFFIX_RE = re.compile(
    r"\s+(jr|sr|ii|iii|iv|v|esq|phd|md|dds|jd|lld)\.?\s*$",
    re.IGNORECASE,
)


def _normalize_name(name: str) -> str:
    """Lowercase, strip accents, remove common titles/suffixes, collapse whitespace."""
    nfkd = unicodedata.normalize("NFKD", name.strip())
    normalized = nfkd.encode("ascii", "ignore").decode("ascii").lower()
    normalized = _TITLE_PREFIX_RE.sub("", normalized)
    normalized = _SUFFIX_RE.sub("", normalized)
    # Keep only letters and spaces
    normalized = re.sub(r"[^a-z\s]", " ", normalized)
    return " ".join(normalized.split())


def _fuzzy_lookup(
    norm_name: str, index: dict[str, dict], cutoff: float = 0.88
) -> Optional[dict]:
    """Return the closest name match from index if similarity >= cutoff, else None."""
    matches = difflib.get_close_matches(norm_name, index.keys(), n=1, cutoff=cutoff)
    return index[matches[0]] if matches else None


def _apply_profile(person: Person, profile: dict) -> None:
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


def _resolve_via_bulk_fetch(
    db,
    client: ApifyLinkedInEmployeesClient,
    people: list[Person],
    company_name: str,
    company_linkedin_url: str,
    company_id: str,
) -> tuple[int, list[Person]]:
    """
    Fetch all LinkedIn employees in one actor call, then fuzzy-match by name.
    Returns (resolved_count, unmatched_people).
    """
    all_employees = client.search_company_people(
        company_name, company_linkedin_url, max_results=10000
    )
    if client._last_run:
        cost = extract_apify_cost(client.client, client._last_run)
        log_usage(
            company_id=company_id,
            service="apify",
            provider="apify",
            model=client.ACTOR_ID,
            pipeline_step="linkedin_resolve",
            cost_usd=cost,
            metadata_json={"bulk_fetch": True, "count": len(all_employees)},
        )

    log.info(f"Bulk fetch returned {len(all_employees)} LinkedIn employees")
    employee_index = {
        _normalize_name(e["name"]): e for e in all_employees if e.get("name")
    }

    resolved = 0
    unmatched: list[Person] = []
    for person in people:
        norm = _normalize_name(person.name)
        profile = employee_index.get(norm) or _fuzzy_lookup(norm, employee_index)
        if profile:
            _apply_profile(person, profile)
            resolved += 1
            log.info(f"  Bulk-matched: {person.name} -> {profile.get('linkedin_url')}")
        else:
            unmatched.append(person)

    db.commit()
    return resolved, unmatched


def _resolve_via_google(
    db,
    client: ApifyLinkedInEmployeesClient,
    unmatched: list[Person],
    company_name: str,
    company_id: str,
    batch_size: int = 25,
) -> int:
    """
    Batched Google fallback: site:linkedin.com/in "Name" "Company" for unmatched people.
    Returns count of newly resolved people.
    """
    names = [p.name for p in unmatched]
    person_map = {p.name: p for p in unmatched}
    resolved = 0
    total_batches = -(-len(names) // batch_size)

    for i in range(0, len(names), batch_size):
        batch_names = names[i : i + batch_size]
        batch_found = client._google_people_batch_call(batch_names, company_name)

        if client._last_run:
            cost = extract_apify_cost(client.client, client._last_run)
            log_usage(
                company_id=company_id,
                service="apify",
                provider="apify",
                model=client.GOOGLE_ACTOR_ID,
                pipeline_step="linkedin_resolve",
                cost_usd=cost,
                metadata_json={
                    "google_fallback": True,
                    "batch": i // batch_size + 1,
                    "of": total_batches,
                },
            )

        for name, linkedin_url in batch_found.items():
            person = person_map.get(name)
            if person:
                person.linkedin_url = linkedin_url
                person.updated_at = datetime.now(timezone.utc)
                resolved += 1
                log.info(f"  Google-resolved: {name} -> {linkedin_url}")

        log.info(
            f"  Google batch {i // batch_size + 1}/{total_batches}: "
            f"{len(batch_found)}/{len(batch_names)} resolved"
        )
        db.commit()

    return resolved


@celery_app.task(bind=True, max_retries=1, time_limit=3600)
def resolve_linkedin_urls(self, company_id: str, person_ids: list[str]):
    """
    Resolve missing LinkedIn URLs via two-stage approach:
      1. Bulk-fetch all current LinkedIn employees (1 actor call) + fuzzy name match.
         People who currently list the company as employer are matched here.
      2. Batched Google search fallback (site:linkedin.com/in "Name" "Company") for
         unmatched people — catches advisors/alumni who don't list current employment.
    Matched people from stage 1 get full profile data; stage 2 people get a URL only
    and are enriched by the subsequent enrich_linkedin_batch task.
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

        # Stage 1: bulk employee fetch + fuzzy name matching
        resolved, unmatched = _resolve_via_bulk_fetch(
            db, client, people, company_name, company_linkedin_url, company_id
        )
        log.info(
            f"Bulk match: {resolved}/{len(people)} resolved, "
            f"{len(unmatched)} unmatched → Google fallback"
        )

        # Stage 2: Google search fallback for unmatched people
        if unmatched:
            google_resolved = _resolve_via_google(
                db, client, unmatched, company_name, company_id
            )
            resolved += google_resolved
            log.info(f"Google fallback added {google_resolved} more resolutions")

        log.info(f"Total resolved: {resolved}/{len(people)} for {company_name}")
        _chain_enrichment(company_id, person_ids)

    except Exception as exc:
        log.error(
            f"LinkedIn URL resolution failed for company {company_id}: {exc}",
            exc_info=True,
        )
        _chain_enrichment(company_id, person_ids)
    finally:
        db.close()


def _chain_enrichment(company_id: str, person_ids: list[str]) -> None:
    """Chain to LinkedIn enrichment for unenriched people, then to LLM analysis."""
    from app.tasks.linkedin_task import enrich_linkedin_batch

    db = SessionLocal()
    try:
        unenriched_ids = [
            str(p.id)
            for p in db.query(Person).filter(
                Person.id.in_(person_ids),
                Person.linkedin_url.isnot(None),
                Person.linkedin_enriched.is_(False),
            ).all()
        ]
        if unenriched_ids:
            enrich_linkedin_batch.delay(company_id, unenriched_ids, all_person_ids=person_ids)
        else:
            from app.tasks.analyze_task import analyze_expertise_batch

            analyze_expertise_batch.delay(company_id, person_ids)
    finally:
        db.close()