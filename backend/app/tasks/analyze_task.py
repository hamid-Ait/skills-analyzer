import logging
import time
from datetime import datetime, timezone

from app.config import settings
from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models import Job, Company, Person
from app.services.expertise_analyzer import (
    format_people_for_analysis, get_provider,
    _parse_llm_response, _normalize_name,
    EXPERTISE_SYSTEM_PROMPT, SECTOR_VOCAB,
)
from app.services.keyword_matcher import match_person_from_db
from app.services.expertise_merger import merge, merge_keyword_only

log = logging.getLogger(__name__)

BATCH_SIZE = 10

# ── Post-processing category filter ──────────────────────────────────────────
# The LLM over-applies several Layer 1 categories by reasoning from seniority
# rather than explicit profile evidence. This filter strips a category unless
# at least one of its required keywords appears in the combined profile text.
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "R&D": [
        # Must indicate the person directly does or leads research/product development
        "r&d", "research and development", "research lab", "patent",
        "innovation pipeline", "r & d",
    ],
    "People and Talent": [
        # Must indicate an HR/talent/people advisory focus — not just mentioning people
        # Avoid generic consulting terms like "human capital" that appear broadly
        "people & organization", "people and organization",
        "talent management practice", "talent advisory",
        "human resources practice", "hr practice", "hr leader",
        "people chair", "people practice", "people lead",
        "chief people officer", "chief human resources",
        "workforce planning", "people officer",
        "organizational effectiveness practice", "talent practice",
    ],
    "Environment (ESG)": [
        # Must indicate ESG/sustainability advisory focus — not firm-wide mentions
        "climate practice", "sustainability practice",
        "climate & sustainability", "climate and sustainability",
        "esg practice", "esg reporting", "esg advisory",
        "decarbonization", "decarbonisation", "net-zero", "net zero",
        "nature-positive", "environmental advisory",
    ],
    "Social (ESG)": [
        # Must indicate explicit social impact or DEI advisory work
        "social impact", "social responsibility", "social practice",
        "dei practice", "diversity, equity", "diversity and inclusion",
        "community impact",
    ],
    "Governance (ESG)": [
        # Must indicate explicit governance advisory — not generic governance mentions
        "board governance", "esg governance", "governance framework",
        "governance architecture", "audit committee",
        "corporate governance advisory", "esg reporting",
    ],
    "Legal": [
        # Must indicate legal advisory or in-house legal work
        "general counsel", "chief legal", "legal officer",
        "litigation", "law firm", "legal practice", "legal advisory",
        "in-house counsel", "legal and regulatory",
    ],
}


_VALID_SECTORS: set[str] = set(SECTOR_VOCAB)

# Reverse mapping: matched sector → canonical parent sector in SECTOR_VOCAB
# Used to enforce coupling — if a matched sector is present, its parent must be too
_MATCHED_TO_PARENT_SECTOR: dict[str, str] = {
    "Healthcare, Medical & Social Care":                    "Healthcare",
    "Pharmaceutical":                                       "Pharmaceuticals & Life Sciences",
    "Life Sciences":                                        "Pharmaceuticals & Life Sciences",
    "Financial, Investment and Insurance Services":         "Financial Services",
    "Consumer":                                             "Consumer & Retail",
    "Wholesale, Retail & Hiring":                           "Consumer & Retail",
    "Manufacturing and Product Development":                "Industrials & Manufacturing",
    "Industrials":                                          "Industrials & Manufacturing",
    "Computing, Technology, Robotics & AI":                 "Technology & Software",
    "Real Estate & Property: Industrial, Commercial and Private": "Real Estate",
    "Transportation and Logistics":                         "Transportation & Logistics",
    "Education & Training":                                 "Education",
    "Public Services":                                      "Government & Public Sector",
    "Media, News, Publishing & Information Services":       "Media & Entertainment",
    "Arts, Entertainment, Recreation, Sports":              "Media & Entertainment",
    "Agriculture, Horticulture, Forestry & Fishing":        "Agriculture & Food",
    "Food and Beverage":                                    "Food & Beverage",
    "Automotive":                                           "Automotive",
    "Energy":                                               "Energy & Utilities",
    "Utilities":                                            "Energy & Utilities",
}


def _enforce_sector_coupling(sectors: list[str], matched: list[str], name: str) -> list[str]:
    """Ensure every matched sector has a corresponding parent sector. Adds missing parents."""
    sector_set = set(sectors)
    for ms in matched:
        parent = _MATCHED_TO_PARENT_SECTOR.get(ms)
        if parent and parent not in sector_set:
            sector_set.add(parent)
            log.info("  %s: added missing parent sector '%s' for matched '%s'", name, parent, ms)
    return sorted(sector_set)


# Matched sectors with specific evidence requirements (same pattern as _CATEGORY_KEYWORDS)
_MATCHED_SECTOR_KEYWORDS: dict[str, list[str]] = {
    "Professional, Business & Support Services": [
        "professional services", "business services", "consulting services",
        "advisory services", "support services", "outsourcing",
        "managed services", "staffing", "recruitment services",
    ],
}


def _filter_sectors(sectors: list[str]) -> list[str]:
    """Pass sectors through as-is — sectors are now free-text from the LLM."""
    return sectors


def _filter_matched_sectors(sectors: list[str], profile_text: str) -> list[str]:
    """Strip matched sectors that lack keyword evidence (for over-applied ones)."""
    filtered = []
    for s in sectors:
        keywords = _MATCHED_SECTOR_KEYWORDS.get(s)
        if keywords is None:
            filtered.append(s)
        elif any(kw in profile_text for kw in keywords):
            filtered.append(s)
        else:
            log.info("  Filtered matched sector '%s' — no keyword evidence", s)
    return filtered


def _profile_text(p: Person) -> str:
    """Concatenate all searchable text fields for a person in lowercase."""
    extra = p.extra or {}
    parts = [
        p.name or "",
        p.title or "",
        p.department or "",
        p.bio or "",
        p.linkedin_headline or "",
        p.linkedin_summary or "",
        p.linkedin_experience_summary or "",
        " ".join(p.linkedin_skills or []),
        " ".join(extra.get("expertise_industries") or []),
        " ".join(extra.get("expertise_capabilities") or []),
    ]
    return " ".join(parts).lower()


def _filter_categories(categories: list[str], profile_text: str) -> list[str]:
    """Remove categories that lack keyword support in the profile text."""
    filtered = []
    for cat in categories:
        keywords = _CATEGORY_KEYWORDS.get(cat)
        if keywords is None:
            # No restriction for this category — keep it
            filtered.append(cat)
        elif any(kw in profile_text for kw in keywords):
            filtered.append(cat)
        else:
            log.debug("  Filtered out '%s' — no keyword evidence in profile", cat)
    return filtered


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
    extra = p.extra or {}
    if extra.get("expertise_industries"):
        entry["website_industries"] = extra["expertise_industries"]
    if extra.get("expertise_capabilities"):
        entry["website_capabilities"] = extra["expertise_capabilities"]
    if extra.get("education"):
        entry["website_education"] = extra["education"]
    return entry


def _apply_result(person: Person, result: dict):
    """Write merged result fields onto a Person record."""
    person.primary_expertise = result.get("primary_expertise")
    person.justification = result.get("justification")
    # Support both old (matched_13_categories) and new (explicit_expertise_13) field names
    categories = (
        result.get("explicit_expertise_13")
        or result.get("matched_13_categories", [])
    )
    ptext = _profile_text(person)
    person.matched_13_categories = _filter_categories(list(categories or []), ptext)

    # Sectors/geographies: new prompt returns arrays, DB column is Text
    sectors = result.get("sectors") or result.get("sector")
    if isinstance(sectors, str):
        sectors = [s.strip() for s in sectors.split(";") if s.strip()]
    sectors = _filter_sectors(list(sectors or []))
    matched_sectors = result.get("matched_sectors") or []
    if isinstance(matched_sectors, str):
        matched_sectors = [s.strip() for s in matched_sectors.split(";") if s.strip()]
    matched_sectors = _filter_matched_sectors(list(matched_sectors), ptext)
    # Enforce coupling: add any parent sectors implied by matched sectors
    # Sector coupling enforcement disabled — sectors are now free-text, not controlled vocab
    # sectors = _enforce_sector_coupling(sectors, matched_sectors, person.name or "")
    person.sector = "; ".join(sectors) if sectors else None
    person.matched_sector = matched_sectors or None
    geographies = result.get("geographies") or result.get("geography")
    if isinstance(geographies, list):
        geographies = "; ".join(geographies) if geographies else None
    person.geography = geographies
    func = result.get("inferred_expertise_functional", [])
    if isinstance(func, str):
        func = [f.strip() for f in func.split(",") if f.strip()]
    person.inferred_expertise_functional = func
    person.inference_reasoning = result.get("inference_reasoning")
    person.matched_inferred_expertise_topics = (
        result.get("topic_overlap")
        or result.get("matched_inferred_expertise_topics", [])
    )
    person.expertise_evidence = result.get("evidence_map") or None
    person.expertise_raw = result
    if result.get("company_practice"):
        person.department = result["company_practice"]
    person.updated_at = datetime.now(timezone.utc)

    log.debug(
        "  %s → primary=%s | 13=%d | functional=%d | topics=%d",
        person.name,
        person.primary_expertise,
        len(person.matched_13_categories or []),
        len(person.inferred_expertise_functional or []),
        len(person.matched_inferred_expertise_topics or []),
    )


@celery_app.task(bind=True, max_retries=1, time_limit=72000)
def analyze_expertise_batch(self, company_id: str, person_ids: list[str]):
    """Analyze expertise using hybrid keyword + LLM approach.

    For each batch:
    1. Run keyword matching (fast, deterministic)
    2. Run LLM classification (semantic, contextual)
    3. Merge results with taxonomy validation
    4. Store to DB
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

        # Step 1: Run keyword matching for all people upfront (fast)
        keyword_results: dict[str, object] = {}
        for p in people:
            norm = _normalize_name(p.name or "")
            keyword_results[norm] = match_person_from_db(p)

        # Step 2: Process in LLM batches
        provider = get_provider()
        total_updated = 0
        total_batches = (len(people) + BATCH_SIZE - 1) // BATCH_SIZE

        # Log prompt fingerprint so we can verify the worker has the latest prompt
        prompt_fingerprint = hash(EXPERTISE_SYSTEM_PROMPT) & 0xFFFFFFFF
        has_layer2b = "LAYER 2b" in EXPERTISE_SYSTEM_PROMPT
        log.info(
            f"Prompt fingerprint: {prompt_fingerprint:#010x} | "
            f"has_layer2b={has_layer2b} | "
            f"provider={settings.LLM_PROVIDER} | "
            f"people={len(people)} batches={total_batches}"
        )

        # Gemini free tier: 15 RPM. Space out calls to avoid 429s.
        rate_limit_providers = {"gemini", "deepseek"}
        min_interval = 4.5 if settings.LLM_PROVIDER in rate_limit_providers else 0
        last_call_time = 0.0

        for batch_idx in range(0, len(people), BATCH_SIZE):
            batch = people[batch_idx:batch_idx + BATCH_SIZE]
            batch_num = batch_idx // BATCH_SIZE + 1
            batch_data = [_build_person_entry(p) for p in batch]
            text = format_people_for_analysis(batch_data, company_name=company.name if company else "")

            try:
                if min_interval > 0:
                    elapsed = time.monotonic() - last_call_time
                    if elapsed < min_interval:
                        time.sleep(min_interval - elapsed)

                # Retry with backoff on rate-limit (429) errors
                max_retries = 3
                for attempt in range(max_retries + 1):
                    last_call_time = time.monotonic()
                    try:
                        raw_response = provider.analyze_batch(text)
                        break
                    except Exception as retry_exc:
                        if "429" in str(retry_exc) and attempt < max_retries:
                            wait = min(15 * (2 ** attempt), 120)
                            log.warning(f"  Batch {batch_num}: rate limited, retrying in {wait}s")
                            time.sleep(wait)
                        else:
                            raise
                results = _parse_llm_response(raw_response)
                log.info(f"  Batch {batch_num}: LLM returned {len(results)} results")

                # Check which expected fields are present in first result
                if results:
                    first = results[0]
                    expected = ["primary_expertise", "explicit_expertise_13", "inferred_expertise_functional", "topic_overlap", "sectors", "geographies"]
                    missing = [f for f in expected if f not in first]
                    if missing:
                        log.warning(f"  Batch {batch_num}: LLM response missing fields: {missing}")

                # Build name → LLM result mapping for this batch
                llm_by_name: dict[str, dict] = {}
                for result in results:
                    result_name = result.get("name", "")
                    if result_name:
                        llm_by_name[_normalize_name(result_name)] = result

                # Positional fallback if LLM returned no names
                if not llm_by_name and len(results) == len(batch):
                    log.warning(f"  Batch {batch_num}: no name matches, using positional fallback")
                    for person, result in zip(batch, results):
                        norm = _normalize_name(person.name or "")
                        if norm:
                            llm_by_name[norm] = result

                # Step 3: Merge keyword + LLM for each person in this batch
                batch_updated = 0
                for person in batch:
                    norm = _normalize_name(person.name or "")
                    if person.primary_expertise is not None:
                        continue  # Already analyzed

                    kw_result = keyword_results.get(norm)
                    llm_result = llm_by_name.get(norm, {})

                    # Post-process: strip categories without keyword evidence
                    if llm_result and llm_result.get("explicit_expertise_13"):
                        ptext = _profile_text(person)
                        original = llm_result["explicit_expertise_13"]
                        filtered = _filter_categories(original, ptext)
                        if len(filtered) != len(original):
                            removed = set(original) - set(filtered)
                            log.info(
                                "  %s: filtered categories %s",
                                person.name, removed,
                            )
                        llm_result = {**llm_result, "explicit_expertise_13": filtered}

                    if kw_result and llm_result:
                        merged = merge(kw_result, llm_result)
                    elif llm_result:
                        merged = llm_result
                    elif kw_result:
                        merged = merge_keyword_only(kw_result)
                    else:
                        continue

                    _apply_result(person, merged)
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