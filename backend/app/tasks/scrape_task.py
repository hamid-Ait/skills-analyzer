import logging
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from app.tasks.celery_app import celery_app
from app.config import settings
from app.database import SessionLocal
from app.models import Job, Company, Person

log = logging.getLogger(__name__)



def _import_agent():
    """Lazily import and configure agent.py module-level vars."""
    from scraping_agent import agent as _agent

    work_dir = Path(tempfile.mkdtemp(prefix="pi_agent_"))
    _agent.OUTPUT_DIR = work_dir / "scraped_data"
    _agent.SCRIPTS_DIR = work_dir / "generated_scripts"
    _agent.PROGRESS_DIR = work_dir / "progress"
    _agent.HTML_DIR = work_dir / "html"
    _agent.OUTPUT_DIR.mkdir(exist_ok=True)
    _agent.SCRIPTS_DIR.mkdir(exist_ok=True)
    _agent.PROGRESS_DIR.mkdir(exist_ok=True)

    return _agent


def _update_company(db, company_id: str, **kwargs):
    company = db.query(Company).filter(Company.id == company_id).first()
    if company:
        for k, v in kwargs.items():
            setattr(company, k, v)
        company.updated_at = datetime.now(timezone.utc)
        db.commit()


@celery_app.task(bind=True, max_retries=1, time_limit=3600)
def scrape_company(self, company_id: str, discover: bool = True,
                   follow_profiles: bool = True, enrich_linkedin: bool = False):
    """Celery task: scrape one company URL using the existing agent.py."""
    import anthropic
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

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        proxy_list = []
        if settings.PROXY_URLS:
            proxy_list = [p.strip() for p in settings.PROXY_URLS.split(",") if p.strip()]

        session = WafSession(proxies=proxy_list, min_delay=0.8, max_delay=2.0)

        # Discover team page
        team_url = company.url
        if discover:
            found = agent.discover_team_url(client, company.url, session)
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

        # Scrape
        people_data, meta = agent.scrape_site(
            team_url, client, session,
            follow_profiles=follow_profiles,
        )

        # Store results
        _update_company(
            db, company_id,
            status="analyzing",
            people_count=len(people_data),
            pages_scraped=meta.get("pages_scraped", 0),
            waf_detected=meta.get("waf", {}).get("waf_detected", False),
            waf_name=meta.get("waf", {}).get("waf_name"),
            scrape_meta=meta,
        )

        # Deduplicate image URLs — if the same URL appears for multiple people,
        # it's likely a placeholder/stock image, not a real photo.
        image_urls = [p.get("image_url") for p in people_data if p.get("image_url")]
        duplicate_images = {url for url in image_urls if image_urls.count(url) > 1}

        # Bulk insert people
        person_ids = []
        for p in people_data:
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

        db.commit()
        log.info(f"Inserted {len(person_ids)} people for company {company_id}")

        if not person_ids:
            # No people found on website — fall back to Google search for LinkedIn profiles
            log.info(f"No people found on website for company {company_id}, trying Google search fallback")
            from app.tasks.google_search_task import search_people_fallback
            _update_company(db, company_id, status="searching")
            search_people_fallback.delay(company_id, enrich_linkedin=enrich_linkedin)
            return

        # Chain expertise analysis
        from app.tasks.analyze_task import analyze_expertise_batch
        analyze_expertise_batch.delay(company_id, person_ids, enrich_linkedin=enrich_linkedin)

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

        companies = db.query(Company).filter(Company.job_id == job_id).all()
        for company in companies:
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
