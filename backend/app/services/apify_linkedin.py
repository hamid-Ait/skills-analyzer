import logging
from typing import Any, Optional

from app.config import settings

log = logging.getLogger(__name__)


def _run_dataset_id(run) -> str | None:
    if run is None:
        return None
    if isinstance(run, dict):
        return run.get("defaultDatasetId")
    return getattr(run, "default_dataset_id", None) or getattr(run, "defaultDatasetId", None)


def _strip_nulls(obj: Any) -> Any:
    """Recursively remove null bytes (\\u0000) that PostgreSQL rejects in text/JSONB."""
    if isinstance(obj, str):
        return obj.replace("\x00", "")
    if isinstance(obj, dict):
        return {k: _strip_nulls(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_nulls(v) for v in obj]
    return obj


class ApifyLinkedInClient:
    """Client for Apify harvestapi/linkedin-profile-scraper actor."""

    ACTOR_ID = "harvestapi/linkedin-profile-scraper"

    def __init__(self, api_token: Optional[str] = None):
        from apify_client import ApifyClient
        self.client = ApifyClient(api_token or settings.APIFY_API_TOKEN)
        self._last_run: dict | None = None

    def enrich_profiles(self, linkedin_urls: list[str]) -> list[dict]:
        """
        Submit LinkedIn profile URLs to Apify actor.
        Returns list of profile data dicts.
        """
        if not linkedin_urls:
            return []

        log.info(f"Enriching {len(linkedin_urls)} LinkedIn profiles via Apify...")

        try:
            run_input = {
                "profileScraperMode": "Profile details no email ($4 per 1k)",
                "queries": linkedin_urls,
            }
            run = self.client.actor(self.ACTOR_ID).call(run_input=run_input)
            self._last_run = run
            dataset = self.client.dataset(_run_dataset_id(run))
            items = list(dataset.iterate_items())
            log.info(f"Apify returned {len(items)} profiles")
            return items
        except Exception as exc:
            log.error(f"Apify LinkedIn enrichment failed: {exc}")
            return []

    @staticmethod
    def extract_profile_fields(apify_data: dict) -> dict:
        """Extract relevant fields from harvestapi/linkedin-profile-scraper response."""

        # Headline
        headline = apify_data.get("headline")

        # Summary/about
        summary = apify_data.get("about")

        # Experience — structured list with position, company, duration, dates
        experience = apify_data.get("experience", [])

        # Education — structured list with school, degree, dates
        education = apify_data.get("education", [])

        # Skills — list of skill dicts or strings
        raw_skills = apify_data.get("skills") or apify_data.get("topSkills") or []
        skills = []
        for s in raw_skills:
            if isinstance(s, dict):
                name = s.get("name") or s.get("skill")
                if name:
                    skills.append(name)
            elif isinstance(s, str):
                skills.append(s)

        # Location
        location = None
        loc_data = apify_data.get("location")
        if isinstance(loc_data, dict):
            location = loc_data.get("linkedinText") or (loc_data.get("parsed") or {}).get("text")
        elif isinstance(loc_data, str):
            location = loc_data

        # Profile picture
        image_url = None
        pic_data = apify_data.get("profilePicture")
        if isinstance(pic_data, dict):
            image_url = pic_data.get("url")
        elif isinstance(pic_data, str):
            image_url = pic_data
        # Fallback to top-level "photo" field
        if not image_url:
            image_url = apify_data.get("photo")

        return _strip_nulls({
            "linkedin_headline": headline,
            "linkedin_summary": summary,
            "linkedin_experience": experience,
            "linkedin_education": education,
            "linkedin_skills": skills,
            "location": location,
            "image_url": image_url,
        })