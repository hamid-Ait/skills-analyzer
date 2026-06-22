import logging
import re
import unicodedata
import difflib
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from app.config import settings
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


def _search_name(stored_name: str | None, company_url: str | None) -> str:
    """
    Return the best available company name for search queries.

    The stored name is often the LinkedIn slug (e.g. "teneoglobal") rather than
    the human-readable name ("Teneo"). A slug has no spaces and is all-lowercase,
    producing queries that return 0 results. Fall back to the hostname when the
    stored name looks like a slug.
    """
    name = (stored_name or "").strip()
    if name and (" " in name or any(c.isupper() for c in name)):
        return name
    if company_url:
        host = urlparse(company_url).hostname or ""
        host = host.removeprefix("www.")
        domain_part = host.split(".")[0]
        if domain_part:
            log.info(
                f"Company name '{name or '(none)'}' looks like a slug — "
                f"using domain '{domain_part.title()}' for search"
            )
            return domain_part.title()
    return name or company_url or ""


def _normalize_name(name: str) -> str:
    """Lowercase, strip accents, remove common titles/suffixes, collapse whitespace."""
    nfkd = unicodedata.normalize("NFKD", name.strip())
    normalized = nfkd.encode("ascii", "ignore").decode("ascii").lower()
    normalized = _TITLE_PREFIX_RE.sub("", normalized)
    normalized = _SUFFIX_RE.sub("", normalized)
    normalized = re.sub(r"[^a-z\s]", " ", normalized)
    return " ".join(normalized.split())


def _nickname_lookup(norm_name: str, index: dict[str, dict]) -> Optional[dict]:
    """
    Match names where the last name is identical and one first name is a prefix
    of the other (min 3 chars). Catches Alex/Alexander, Rob/Robert, Will/William.
    """
    tokens = norm_name.split()
    if len(tokens) < 2:
        return None
    first, last = tokens[0], tokens[-1]
    for candidate, profile in index.items():
        c_tokens = candidate.split()
        if len(c_tokens) < 2:
            continue
        c_first, c_last = c_tokens[0], c_tokens[-1]
        if last != c_last:
            continue
        shorter, longer = (first, c_first) if len(first) <= len(c_first) else (c_first, first)
        if len(shorter) >= 3 and longer.startswith(shorter):
            return profile
    return None


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


def _title_corroborates(person_title: str | None, profile: dict) -> bool:
    """
    True if a significant token (≥4 chars) of the person's scraped title appears in
    the candidate's LinkedIn title/headline. Used to safely accept softer name matches.
    """
    if not person_title:
        return False
    hay = " ".join(
        filter(None, [profile.get("title") or "", profile.get("linkedin_headline") or ""])
    ).lower()
    if not hay:
        return False
    tokens = [t for t in re.split(r"[^a-z]+", person_title.lower()) if len(t) >= 4]
    return any(t in hay for t in tokens)


def _best_profile_match(person: Person, profiles: list[dict]) -> Optional[dict]:
    """
    Pick the best-matching profile for a person from a list of candidates.

    Match tiers, highest confidence first:
      1. Exact normalized name
      2. Nickname / first-name prefix, same last name (Alex/Alexander)
      3. Strict fuzzy name similarity (>= 0.88)
      4. Soft fuzzy (>= 0.80) corroborated by title/headline token overlap

    Tier 4 recovers real matches that strict name-only matching rejects (maiden
    names, transliterations, dropped middle names) without admitting unrelated
    people, because the scraped title must also agree. Returns the profile or None.
    """
    norm_expected = _normalize_name(person.name)
    if not norm_expected:
        return None

    scored: list[tuple[float, dict]] = []
    for prof in profiles:
        norm = _normalize_name(prof.get("name", ""))
        if not norm:
            continue
        if norm == norm_expected:
            return prof
        if _nickname_lookup(norm_expected, {norm: prof}):
            return prof
        ratio = difflib.SequenceMatcher(None, norm_expected, norm).ratio()
        scored.append((ratio, prof))

    if not scored:
        return None

    best_ratio, best_prof = max(scored, key=lambda s: s[0])
    if best_ratio >= 0.88:
        return best_prof
    if best_ratio >= 0.80 and _title_corroborates(person.title, best_prof):
        return best_prof
    return None


def _resolve_via_roster(
    db,
    client: ApifyLinkedInEmployeesClient,
    people: list[Person],
    company_linkedin_url: str,
    google_company_name: str,
    company_id: str,
) -> tuple[int, list[Person]]:
    """
    Stage 0: bulk-fetch the company's LinkedIn employee roster in one call, then match
    every person locally against the full set.

    This is the highest-recall and lowest-marginal-cost source for current employees:
    one API call returns the whole roster with full profiles, and local matching can
    layer every strategy for free against every candidate (vs. the 5-candidate cap of
    per-person search). Matched people get full profile data inline via _apply_profile,
    so they skip the separate enrichment step. Unmatched people fall through to Google
    and per-person search, so the roster only ever adds coverage.

    Returns (resolved_count, still_unmatched).
    """
    try:
        roster = client.search_company_people(
            google_company_name,
            company_linkedin_url,
            max_results=settings.LINKEDIN_ROSTER_MAX,
        )
    except Exception as exc:
        log.warning(f"  Roster fetch failed: {exc}")
        return 0, list(people)

    if client._last_run:
        cost = extract_apify_cost(client.client, client._last_run)
        log_usage(
            company_id=company_id,
            service="apify",
            provider="apify",
            model=client.ACTOR_ID,
            pipeline_step="linkedin_resolve",
            cost_usd=cost,
            metadata_json={"roster_stage": True, "roster_size": len(roster)},
        )

    if not roster:
        return 0, list(people)

    log.info(
        f"  Roster: fetched {len(roster)} employees; "
        f"matching {len(people)} people locally"
    )
    resolved = 0
    unmatched: list[Person] = []
    for person in people:
        profile = _best_profile_match(person, roster)
        if profile and profile.get("linkedin_url"):
            _apply_profile(person, profile)
            resolved += 1
            log.info(f"  Roster-resolved: {person.name} -> {profile.get('linkedin_url')}")
        else:
            unmatched.append(person)
    db.commit()
    return resolved, unmatched


def _resolve_via_google(
    db,
    client: ApifyLinkedInEmployeesClient,
    people: list[Person],
    company_name: str,
    company_id: str,
    batch_size: int = 25,
) -> tuple[int, list[Person]]:
    """
    Batched Google search: site:linkedin.com/in "Name" "Company" per person.

    Company-qualified queries only — no unqualified fallback.
    Each URL is validated by slug matching before being accepted.
    Returns (resolved_count, still_unmatched).
    """
    names = [p.name for p in people]
    person_map = {p.name: p for p in people}
    resolved = 0
    unmatched: list[Person] = []
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
                    "google_stage": True,
                    "batch": i // batch_size + 1,
                    "of": total_batches,
                },
            )

        batch_resolved = set(batch_found.keys())
        for name in batch_names:
            person = person_map[name]
            if name in batch_found:
                person.linkedin_url = batch_found[name]
                person.updated_at = datetime.now(timezone.utc)
                resolved += 1
                log.info(f"  Google-resolved: {name} -> {batch_found[name]}")
            else:
                unmatched.append(person)

        log.info(
            f"  Google batch {i // batch_size + 1}/{total_batches}: "
            f"{len(batch_resolved)}/{len(batch_names)} resolved"
        )
        db.commit()

    return resolved, unmatched


def _resolve_via_linkedin_search(
    db,
    client: ApifyLinkedInEmployeesClient,
    people: list[Person],
    company_linkedin_url: str,
    company_id: str,
) -> int:
    """
    Resolve LinkedIn profiles one person at a time using LinkedIn's own people search.

    Each call to harvestapi/linkedin-company-employees uses the searchQuery parameter
    scoped to company_linkedin_url. LinkedIn's search covers current employees,
    advisors, and alumni — broader than any bulk-fetch approach.

    Up to 3 candidates are returned per call. The first candidate whose name
    satisfies exact, fuzzy, or nickname matching is accepted. This eliminates
    false positives that plagued both the bulk-fetch and Google stages.

    Full profile data (experience, education, skills, headline) is applied
    immediately via _apply_profile, so no separate enrichment step is needed.
    """
    resolved = 0
    for i, person in enumerate(people):
        log.info(f"  LinkedIn search [{i + 1}/{len(people)}]: {person.name}")
        try:
            candidates, run = client.search_person_by_name(person.name, company_linkedin_url)
        except Exception as exc:
            log.warning(f"  LinkedIn search failed for {person.name}: {exc}")
            continue

        if run:
            cost = extract_apify_cost(client.client, run)
            log_usage(
                company_id=company_id,
                service="apify",
                provider="apify",
                model=client.ACTOR_ID,
                pipeline_step="linkedin_resolve",
                cost_usd=cost,
                metadata_json={"person": person.name, "candidates": len(candidates)},
            )

        if not candidates:
            log.info(f"  LinkedIn search: no result for {person.name}")
            continue

        matched_profile = _best_profile_match(person, candidates)

        if not matched_profile:
            names_found = [p.get("name") for p in candidates]
            log.info(
                f"  LinkedIn search: name mismatch for {person.name} "
                f"(got: {names_found})"
            )
            continue

        _apply_profile(person, matched_profile)
        resolved += 1
        log.info(
            f"  LinkedIn-resolved: {person.name} -> {matched_profile.get('linkedin_url')}"
        )
        db.commit()

    return resolved


@celery_app.task(bind=True, max_retries=1, time_limit=3600)
def resolve_linkedin_urls(self, company_id: str, person_ids: list[str]):
    """
    Resolve missing LinkedIn URLs via per-person LinkedIn people search.

    Each person gets their own harvestapi/linkedin-company-employees call with
    searchQuery set to their name. LinkedIn's search is scoped to the company page
    so it finds current employees, advisors, and alumni without the false-positive
    risk of bulk-fetch + name matching or Google site: queries.

    Full profile data is applied inline — no separate enrichment step needed.
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

        company_name = _search_name(company.name, company.url)
        company.status = "resolving"
        company.updated_at = datetime.now(timezone.utc)
        db.commit()
        log.info(f"Resolving LinkedIn URLs for {len(people)} people in {company_name}")

        client = ApifyLinkedInEmployeesClient()

        # Resolve the company LinkedIn page URL once via Google.
        # Also captures the display name (e.g. "Stratton HR" from "Stratton HR | LinkedIn")
        # which is more reliable than the stored slug name for diagnostic logging.
        # Resolve the company LinkedIn page URL once via Google.
        # The display name from the result title (e.g. "Stratton HR" from
        # "Stratton HR | LinkedIn") is more reliable than the stored slug name
        # for use in Stage 1 Google people-search queries.
        if "linkedin.com/company/" in (company.url or ""):
            company_linkedin_url = company.url
            google_company_name = company_name
        else:
            company_linkedin_url, linkedin_display_name = (
                client._resolve_linkedin_company_url(company_name, company.url)
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
            google_company_name = linkedin_display_name or company_name
            log.info(
                f"Company LinkedIn URL: {company_linkedin_url} "
                f"(Google query name: {google_company_name!r})"
            )

        if not company_linkedin_url:
            log.warning(
                f"Could not find LinkedIn company page for {company_name} — "
                f"running Google people search only (no roster / per-person stages)"
            )

        # Stage 0: bulk roster match (only when the company page is known).
        # One call, full local matching, full profiles inline. Unmatched fall through.
        roster_resolved = 0
        unmatched = people
        if company_linkedin_url:
            roster_resolved, unmatched = _resolve_via_roster(
                db, client, people, company_linkedin_url, google_company_name, company_id
            )
            log.info(
                f"Roster stage: {roster_resolved}/{len(people)} resolved, "
                f"{len(unmatched)} unmatched → Google"
            )

        # Stage 1: Google batch search (cheap, ~$0.001-0.002/person). Needs only the
        # company display name, so it runs even when the company page URL is unknown.
        # Resolves URL only — full profile data fetched later by _chain_enrichment.
        google_resolved = 0
        if unmatched:
            google_resolved, unmatched = _resolve_via_google(
                db, client, unmatched, google_company_name, company_id
            )
            log.info(
                f"Google stage: {google_resolved} resolved, "
                f"{len(unmatched)} unmatched → LinkedIn search"
            )

        # Stage 2: per-person LinkedIn searchQuery for what Google missed (~$0.03/person).
        # Requires the company page URL. Returns full profile data inline.
        linkedin_resolved = 0
        if unmatched and company_linkedin_url:
            linkedin_resolved = _resolve_via_linkedin_search(
                db, client, unmatched, company_linkedin_url, company_id
            )
            log.info(f"LinkedIn search stage: {linkedin_resolved}/{len(unmatched)} resolved")

        resolved = roster_resolved + google_resolved + linkedin_resolved
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
    """Chain to LinkedIn enrichment for unenriched people, then to LLM analysis.

    People resolved via _resolve_via_linkedin_search already have linkedin_enriched=True
    (set by _apply_profile), so the unenriched_ids list will be empty for them and
    we go directly to analysis.
    """
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