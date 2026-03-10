import logging
from typing import Optional

from app.config import settings

log = logging.getLogger(__name__)


class ApifyLinkedInClient:
    """Client for Apify harvestapi/linkedin-profile-scraper actor."""

    ACTOR_ID = "harvestapi/linkedin-profile-scraper"

    def __init__(self, api_token: Optional[str] = None):
        from apify_client import ApifyClient
        self.client = ApifyClient(api_token or settings.APIFY_API_TOKEN)

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
            dataset = self.client.dataset(run["defaultDatasetId"])
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

        return {
            "linkedin_headline": headline,
            "linkedin_summary": summary,
            "linkedin_experience": experience,
            "linkedin_education": education,
            "linkedin_skills": skills,
            "location": location,
            "image_url": image_url,
        }