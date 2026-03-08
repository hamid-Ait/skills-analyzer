import logging
import re
from urllib.parse import urlparse
from typing import Optional

from app.config import settings

log = logging.getLogger(__name__)


class ApifyLinkedInEmployeesClient:
    """Client for Apify harvestapi/linkedin-company-employees actor."""

    ACTOR_ID = "harvestapi/linkedin-company-employees"
    GOOGLE_ACTOR_ID = "apify/google-search-scraper"

    def __init__(self, api_token: Optional[str] = None):
        from apify_client import ApifyClient
        self.client = ApifyClient(api_token or settings.APIFY_API_TOKEN)

    def _resolve_linkedin_company_url(self, company_name: str, company_url: str) -> Optional[str]:
        """
        Resolve a company website URL to its LinkedIn company page URL.
        Uses a Google search: site:linkedin.com/company "company name"
        """
        domain = urlparse(company_url).netloc or company_url
        domain = domain.replace("www.", "")

        query = f'site:linkedin.com/company "{company_name}" OR "{domain}"'
        log.info(f"Resolving LinkedIn company URL for {company_name}...")

        try:
            run_input = {
                "queries": query,
                "maxPagesPerQuery": 1,
                "resultsPerPage": 5,
                "languageCode": "en",
                "mobileResults": False,
            }
            run = self.client.actor(self.GOOGLE_ACTOR_ID).call(run_input=run_input)
            dataset = self.client.dataset(run["defaultDatasetId"])

            for item in dataset.iterate_items():
                for result in item.get("organicResults", []):
                    url = result.get("url", "")
                    if "linkedin.com/company/" in url:
                        # Extract company slug and normalize to www.linkedin.com
                        match = re.search(r"linkedin\.com/company/([^/?#]+)", url)
                        if match:
                            slug = match.group(1)
                            linkedin_url = f"https://www.linkedin.com/company/{slug}"
                            log.info(f"Resolved LinkedIn company URL: {linkedin_url}")
                            return linkedin_url

        except Exception as exc:
            log.error(f"Failed to resolve LinkedIn company URL for {company_name}: {exc}")

        return None

    def search_company_people(self, company_name: str, company_url: str,
                              max_results: int = 100) -> list[dict]:
        """
        Fetch employees of a company from LinkedIn via Apify.
        First resolves the company website to a LinkedIn company URL,
        then fetches employees from that LinkedIn company page.
        Returns a list of dicts with name, title, linkedin_url, etc.
        """
        # If already a LinkedIn URL, use it directly
        if "linkedin.com/company/" in company_url:
            linkedin_url = company_url
        else:
            linkedin_url = self._resolve_linkedin_company_url(company_name, company_url)
            if not linkedin_url:
                log.warning(f"Could not find LinkedIn company page for {company_name}")
                return []

        log.info(f"Fetching LinkedIn employees for {company_name} from {linkedin_url}...")

        try:
            run_input = {
                "companies": [linkedin_url],
                "maxItems": max_results,
            }
            run = self.client.actor(self.ACTOR_ID).call(run_input=run_input)
            dataset = self.client.dataset(run["defaultDatasetId"])
            items = list(dataset.iterate_items())

            profiles = []
            for item in items:
                profile = self._parse_employee(item)
                if profile:
                    profiles.append(profile)

            log.info(f"Apify returned {len(profiles)} employees for {company_name}")
            return profiles

        except Exception as exc:
            log.error(f"Apify LinkedIn employees search failed for {company_name}: {exc}")
            return []

    @staticmethod
    def _parse_employee(item: dict) -> Optional[dict]:
        """Parse an Apify harvestapi/linkedin-company-employees result."""
        first = item.get("firstName", "")
        last = item.get("lastName", "")
        name = f"{first} {last}".strip()
        if not name:
            return None

        linkedin_url = item.get("linkedinUrl")
        headline = item.get("headline")

        # Extract location text
        location = None
        loc_data = item.get("location")
        if isinstance(loc_data, dict):
            location = loc_data.get("linkedinText") or (loc_data.get("parsed") or {}).get("text")
        elif isinstance(loc_data, str):
            location = loc_data

        # Extract profile picture URL
        image_url = None
        pic_data = item.get("profilePicture")
        if isinstance(pic_data, dict):
            image_url = pic_data.get("url")
        elif isinstance(pic_data, str):
            image_url = pic_data

        # Extract current title from headline or currentPosition
        title = None
        if headline:
            # headline is usually "Title at Company" — extract the title part
            parts = headline.split(" at ")
            title = parts[0].strip() if parts else headline
        positions = item.get("currentPosition") or []
        if positions and not title:
            title = positions[0].get("title")

        return {
            "name": name,
            "title": title,
            "linkedin_url": linkedin_url,
            "location": location,
            "image_url": image_url,
            "bio": item.get("about") or headline,
        }