import logging
from typing import Optional

from app.config import settings

log = logging.getLogger(__name__)


class ApifyLinkedInClient:
    """Client for Apify LinkedIn Profile Scraper actor."""

    ACTOR_ID = "anchor/linkedin-profile-scraper"

    def __init__(self, api_token: Optional[str] = None):
        from apify_client import ApifyClient
        self.client = ApifyClient(api_token or settings.APIFY_API_TOKEN)

    def enrich_profiles(self, linkedin_urls: list[str], max_concurrent: int = 5) -> list[dict]:
        """
        Submit LinkedIn profile URLs to Apify actor.
        Returns list of profile data dicts.
        """
        if not linkedin_urls:
            return []

        log.info(f"Enriching {len(linkedin_urls)} LinkedIn profiles via Apify...")

        try:
            run_input = {
                "startUrls": [{"url": u} for u in linkedin_urls],
                "maxConcurrency": max_concurrent,
            }
            run = self.client.actor(self.ACTOR_ID).call(run_input=run_input)
            dataset = self.client.dataset(run["defaultDatasetId"])
            items = list(dataset.iterate_items())
            log.info(f"Apify returned {len(items)} profiles")
            return items
        except Exception as exc:
            log.error(f"Apify LinkedIn enrichment failed: {exc}")
            return []

    @staticmethod
    def extract_profile_fields(apify_data: dict) -> dict:
        """Extract relevant fields from Apify's raw response."""
        return {
            "linkedin_headline": apify_data.get("headline"),
            "linkedin_summary": apify_data.get("summary") or apify_data.get("about"),
            "linkedin_experience": apify_data.get("experience", []),
            "linkedin_education": apify_data.get("education", []),
            "linkedin_skills": [
                s.get("name") or s for s in (apify_data.get("skills") or [])
                if isinstance(s, (str, dict))
            ],
        }
