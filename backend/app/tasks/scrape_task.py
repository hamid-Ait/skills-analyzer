import logging
import re
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.tasks.celery_app import celery_app
from app.config import settings
from app.database import SessionLocal
from app.models import Job, Company, Person
from app.services.cost_tracker import log_usage

log = logging.getLogger(__name__)



def _import_agent():
    """Lazily import and configure agent.py module-level vars."""
    from scraping_agent import agent as _agent

    work_dir = Path(tempfile.mkdtemp(prefix="pi_agent_"))

    # Stable dirs — must persist across Celery task restarts for resume
    stable_dir = Path("/tmp/pi_agent_stable")
    _agent.PROGRESS_DIR = stable_dir / "progress"
    _agent.SCRIPTS_DIR = stable_dir / "generated_scripts"

    # Ephemeral dirs — per-run artifacts
    _agent.OUTPUT_DIR = work_dir / "scraped_data"
    _agent.HTML_DIR = work_dir / "html"

    for d in [_agent.PROGRESS_DIR, _agent.SCRIPTS_DIR,
              _agent.OUTPUT_DIR, _agent.HTML_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    return _agent


def _update_company(db, company_id: str, **kwargs):
    company = db.query(Company).filter(Company.id == company_id).first()
    if company:
        for k, v in kwargs.items():
            setattr(company, k, v)
        company.updated_at = datetime.now(timezone.utc)
        db.commit()


@celery_app.task(bind=True, max_retries=1, time_limit=7200)
def scrape_company(self, company_id: str, discover: bool = True,
                   follow_profiles: bool = True, enrich_linkedin: bool = False):
    """Celery task: scrape one company URL using the existing agent.py."""
    from scraping_agent.waf_bypass import WafSession

    db = SessionLocal()
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            log.error(f"Company {company_id} not found")
            return

        agent = _import_agent()

        # Update status
        status = "discovering" if discover else "scraping"
        _update_company(db, company_id, status=status)

        provider_key_map = {
            "claude":   settings.ANTHROPIC_API_KEY,
            "openai":   settings.OPENAI_API_KEY,
            "deepseek": settings.DEEPSEEK_API_KEY,
            "gemini":   settings.GOOGLE_API_KEY,
        }
        scraping_provider = settings.LLM_PROVIDER_SCRAPING or settings.LLM_PROVIDER
        scraping_model    = settings.LLM_MODEL_SCRAPING or None
        client = agent.LLMClient(
            provider=scraping_provider,
            api_key=provider_key_map.get(scraping_provider, ""),
            model=scraping_model,
        )

        discovery_provider = settings.LLM_PROVIDER_DISCOVERY or scraping_provider
        discovery_client = agent.LLMClient(
            provider=discovery_provider,
            api_key=provider_key_map.get(discovery_provider, ""),
        )

        proxy_list = []
        if settings.PROXY_URLS:
            proxy_list = [p.strip() for p in settings.PROXY_URLS.split(",") if p.strip()]

        session = WafSession(proxies=proxy_list, min_delay=0.8, max_delay=2.0)

        # Discover team page (or reuse previously discovered team_url)
        team_url = company.team_url or company.url
        if discover:
            found = agent.discover_team_url(discovery_client, company.url, session)
            # Drain discover usage before potential early return
            for entry in agent._usage_log:
                log_usage(
                    company_id=company_id,
                    service="llm",
                    provider=discovery_provider,
                    model=entry.get("model"),
                    pipeline_step=entry.get("step", "team_discovery"),
                    input_tokens=entry.get("input_tokens"),
                    output_tokens=entry.get("output_tokens"),
                )
            agent._usage_log.clear()

            if found:
                team_url = found
                _update_company(db, company_id, team_url=found)
            else:
                # No team page found — skip scraping, go straight to LinkedIn fallback
                log.info(f"No team page found for company {company_id}, skipping to LinkedIn fallback")
                from app.tasks.google_search_task import search_people_fallback
                _update_company(db, company_id, status="searching")
                search_people_fallback.delay(company_id, enrich_linkedin=enrich_linkedin)
                return

        _update_company(db, company_id, status="scraping")

        # Load resume state if available (slug matches agent.py's formula)
        slug = re.sub(r"[^\w]", "_", urlparse(team_url).netloc)[:40]
        resume_state = agent.load_progress(slug)
        if resume_state:
            log.info(f"Resuming scrape for {team_url} — {resume_state.get('records_count', 0)} records already saved")

        # Scrape
        people_data, meta = agent.scrape_site(
            team_url, client, session,
            follow_profiles=follow_profiles,
            resume_state=resume_state,
        )

        # Drain and log accumulated LLM usage from scraping agent
        for entry in agent._usage_log:
            log_usage(
                company_id=company_id,
                service="llm",
                provider="claude",
                model=entry.get("model"),
                pipeline_step=entry.get("step", "scraping"),
                input_tokens=entry.get("input_tokens"),
                output_tokens=entry.get("output_tokens"),
            )
        agent._usage_log.clear()

        # Update team_url if scraper followed a redirect to a different URL
        final_url = meta.get("final_url")
        if final_url and final_url != team_url:
            log.info(f"Team URL redirected: {team_url} -> {final_url}")
            _update_company(db, company_id, team_url=final_url)

        # Store results
        # Store results (people_count updated after insertion to reflect actual inserts)
        _update_company(
            db, company_id,
            status="analyzing",
            people_count=len(people_data),  # preliminary; updated below after dedup
            pages_scraped=meta.get("pages_scraped", 0),
            waf_detected=meta.get("waf", {}).get("waf_detected", False),
            waf_name=meta.get("waf", {}).get("waf_name"),
            scrape_meta=meta,
        )

        # Deduplicate image URLs — if the same URL appears for multiple people,
        # it's likely a placeholder/stock image, not a real photo.
        image_urls = [p.get("image_url") for p in people_data if p.get("image_url")]
        duplicate_images = {url for url in image_urls if image_urls.count(url) > 1}

        # Build dedup set from existing DB records to avoid duplicates on resume
        existing_people = (
            db.query(Person.name, Person.title)
            .filter(Person.company_id == company.id)
            .all()
        )
        existing_keys = {
            (p.name.strip().lower(), (p.title or "").strip().lower())
            for p in existing_people
        }

        # Insert people in batches (partial results survive crashes)
        INSERT_BATCH = 50
        person_ids = []
        pending = 0
        skipped = 0

        for p in people_data:
            dedup_key = (p["name"].strip().lower(), (p.get("title") or "").strip().lower())
            if dedup_key in existing_keys:
                skipped += 1
                continue

            person = Person(
                company_id=company.id,
                name=p["name"],
                title=p.get("title"),
                department=p.get("department"),
                bio=p.get("bio"),
                email=p.get("email"),
                phone=p.get("phone"),
                linkedin_url=p.get("linkedin_url"),
                twitter_url=p.get("twitter_url"),
                other_url=p.get("other_url"),
                image_url=p.get("image_url") if p.get("image_url") not in duplicate_images else None,
                location=p.get("location"),
                profile_url=p.get("profile_url"),
                extra=p.get("extra"),
                source_url=p.get("_source_url"),
                profile_enriched=p.get("_profile_enriched", False),
                data_source="Website + LinkedIn" if p.get("_profile_enriched") else "Website",
                raw_data_json=p,
            )
            db.add(person)
            db.flush()
            person_ids.append(str(person.id))
            existing_keys.add(dedup_key)
            pending += 1

            if pending >= INSERT_BATCH:
                db.commit()
                pending = 0

        if pending > 0:
            db.commit()

        if skipped:
            log.info(f"Skipped {skipped} duplicate people for company {company_id}")
        log.info(f"Inserted {len(person_ids)} people for company {company_id}")

        # Update people_count to reflect actual inserts (not scraped count which includes dupes)
        _update_company(db, company_id, people_count=len(person_ids))

        if not person_ids:
            # No people found on website — fall back to Google search for LinkedIn profiles
            log.info(f"No people found on website for company {company_id}, trying Google search fallback")
            from app.tasks.google_search_task import search_people_fallback
            _update_company(db, company_id, status="searching")
            search_people_fallback.delay(company_id, enrich_linkedin=enrich_linkedin)
            return

        # Chain next step: LinkedIn enrichment first (if requested), then LLM analysis
        if enrich_linkedin:
            from app.tasks.resolve_linkedin_task import resolve_linkedin_urls
            resolve_linkedin_urls.delay(company_id, person_ids)
        else:
            from app.tasks.analyze_task import analyze_expertise_batch
            analyze_expertise_batch.delay(company_id, person_ids)

    except Exception as exc:
        log.error(f"Scrape failed for company {company_id}: {exc}", exc_info=True)
        _update_company(db, company_id, status="error", error_message=str(exc)[:2000])

        # Update job status
        job = db.query(Job).join(Company).filter(Company.id == company_id).first()
        if job:
            job.completed_urls += 1
            all_done = job.completed_urls >= job.total_urls
            if all_done:
                job.status = "completed"
            db.commit()

        raise
    finally:
        db.close()


@celery_app.task(bind=True, time_limit=7200)
def process_job(self, job_id: str, discover: bool = True,
                follow_profiles: bool = True, enrich_linkedin: bool = False):
    """Dispatch scrape_company tasks for all companies in a job."""
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            log.error(f"Job {job_id} not found")
            return

        job.status = "processing"
        job.celery_task_id = self.request.id
        db.commit()

        # Statuses that indicate a company is currently being processed
        IN_PROGRESS_STATUSES = {"pending", "discovering", "scraping", "searching", "analyzing", "resolving", "enriching"}

        companies = db.query(Company).filter(Company.job_id == job_id).all()
        for company in companies:
            # Skip if another company with the same URL is already in progress
            already_processing = (
                db.query(Company)
                .filter(
                    Company.url == company.url,
                    Company.id != company.id,
                    Company.status.in_(IN_PROGRESS_STATUSES),
                )
                .first()
            )
            if already_processing:
                log.info(
                    f"Skipping company {company.id} ({company.url}) — "
                    f"already being processed by {already_processing.id}"
                )
                _update_company(db, str(company.id), status="completed",
                                error_message="Skipped: duplicate URL already in progress")
                job.completed_urls += 1
                db.commit()
                continue

            scrape_company.delay(
                str(company.id),
                discover=discover,
                follow_profiles=follow_profiles,
                enrich_linkedin=enrich_linkedin,
            )

    except Exception as exc:
        log.error(f"Process job failed: {exc}", exc_info=True)
        if job:
            job.status = "error"
            job.error_message = str(exc)[:2000]
            db.commit()
    finally:
        db.close()
