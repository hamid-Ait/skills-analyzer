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
        self._last_run: dict | None = None

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
            self._last_run = run
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
                              max_results: int = 10000) -> list[dict]:
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
            self._last_run = run
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

    def search_person_by_name(self, person_name: str, company_linkedin_url: str) -> tuple[Optional[dict], dict]:
        """
        Search for a specific person by name within a company's LinkedIn employees.
        Uses the searchQuery parameter for targeted lookup — returns at most 1 result.
        Returns (profile_dict | None, run_metadata).
        """
        run_input = {
            "companies": [company_linkedin_url],
            "maxItems": 1,
            "searchQuery": person_name,
        }
        run = self.client.actor(self.ACTOR_ID).call(run_input=run_input)
        self._last_run = run
        items = list(self.client.dataset(run["defaultDatasetId"]).iterate_items())
        profile = self._parse_employee(items[0]) if items else None
        return profile, run

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
        if not image_url:
            image_url = item.get("photo")

        # Extract current title from headline or currentPosition
        title = None
        if headline:
            parts = headline.split(" at ")
            title = parts[0].strip() if parts else headline
        positions = item.get("currentPosition") or []
        if positions and not title:
            title = positions[0].get("title")

        # Extract full experience list
        experience = item.get("experience") or []

        # Extract education
        education = item.get("education") or []

        # Extract skills from experience entries + topSkills
        skills = []
        top_skills = item.get("topSkills")
        if isinstance(top_skills, str) and top_skills:
            skills.extend([s.strip() for s in top_skills.split("•") if s.strip()])
        # Collect unique skills from experience entries
        seen_skills = set(s.lower() for s in skills)
        for exp in experience:
            for skill in (exp.get("skills") or []):
                if skill.lower() not in seen_skills:
                    skills.append(skill)
                    seen_skills.add(skill.lower())

        # Build experience summary (first 5 entries)
        experience_summary = _build_experience_summary_from_employees(experience)

        return {
            "name": name,
            "title": title,
            "linkedin_url": linkedin_url,
            "linkedin_headline": headline,
            "linkedin_summary": item.get("about"),
            "linkedin_experience": experience,
            "linkedin_education": education,
            "linkedin_skills": skills if skills else None,
            "linkedin_experience_summary": experience_summary,
            "location": location,
            "image_url": image_url,
            "bio": item.get("about") or headline,
        }


def _build_experience_summary_from_employees(experience: list[dict]) -> str:
    """Build a text summary from linkedin-company-employees experience entries.

    Each role is rendered as: "Position @ Company · Duration · Location"
    Roles are separated by newlines for easy splitting in the frontend.
    """
    if not experience:
        return "—"
    lines = []
    for exp in experience[:5]:
        position = exp.get("position") or ""
        company = exp.get("companyName") or ""
        duration = exp.get("duration") or ""
        location = exp.get("location") or ""
        # "Position @ Company · Duration · Location"
        role = position
        if company:
            role = f"{role} @ {company}" if role else company
        detail_parts = [p for p in [duration, location] if p]
        if detail_parts:
            role = f"{role} · {' · '.join(detail_parts)}" if role else " · ".join(detail_parts)
        if role:
            lines.append(role)
    return "\n".join(lines) if lines else "—"