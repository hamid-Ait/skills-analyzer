import logging
import re
import unicodedata
from urllib.parse import urlparse, unquote
from typing import Optional

from app.config import settings

log = logging.getLogger(__name__)

_STOP_NAME_TOKENS = {"the", "and", "for", "von", "van", "de", "le", "la"}


def _fold_ascii(text: str) -> str:
    """Lowercase and strip accents so 'François' compares equal to 'francois'."""
    nfkd = unicodedata.normalize("NFKD", text)
    return nfkd.encode("ascii", "ignore").decode("ascii").lower()


def _significant_tokens(text: str) -> list[str]:
    """
    De-accent, then split on any non-letter (spaces, hyphens, apostrophes, digits)
    into significant tokens (≥3 chars, not a stop word). So "Marie-Laurence",
    "O'Keeffe", and "Pálfi" all tokenize cleanly.
    """
    return [
        t for t in re.split(r"[^a-z]+", _fold_ascii(text))
        if len(t) >= 3 and t not in _STOP_NAME_TOKENS
    ]


def _run_dataset_id(run) -> str | None:
    """Extract defaultDatasetId from an Apify run result.

    apify_client <2.x returns a plain dict; newer versions return a typed Run
    object.  This helper handles both shapes so callers don't need to care.
    """
    if run is None:
        return None
    if isinstance(run, dict):
        return run.get("defaultDatasetId")
    # Typed object: try snake_case first (new SDK), then camelCase fallback
    return getattr(run, "default_dataset_id", None) or getattr(run, "defaultDatasetId", None)


def _token_matches_segment(token: str, segments: set[str]) -> bool:
    """
    True if a name token equals a slug segment, or shares a ≥3-char prefix with one
    (nickname tolerance: rob~robert, elliot~elliott, katie~katherine).
    """
    for seg in segments:
        if token == seg:
            return True
        shorter, longer = (token, seg) if len(token) <= len(seg) else (seg, token)
        if len(shorter) >= 3 and longer.startswith(shorter):
            return True
    return False


_GENERIC_COMPANY_TOKENS = {
    "group", "llc", "ltd", "plc", "inc", "corp", "company", "partners",
    "associates", "consulting", "consultants", "advisory", "advisors",
    "services", "solutions", "global", "holdings", "international",
}


def _company_in_text(company_name: str, text: str) -> bool:
    """
    True if a distinctive company token appears in text (de-accented).

    Generic corporate words (Group, Partners, Consulting, …) are ignored so the
    check keys on the brand: "teneo" from "Teneo", "stratton" from "Stratton HR".
    Used to verify a Google result actually belongs to the target company before
    accepting it — name-in-slug alone can't tell two same-named people apart.

    If the company name has no usable tokens, returns True (cannot verify → do not
    block); if the text is empty, returns False (nothing to verify against).
    """
    haystack = _fold_ascii(text)
    if not haystack.strip():
        return False
    tokens = [t for t in _significant_tokens(company_name) if t not in _GENERIC_COMPANY_TOKENS]
    if not tokens:
        tokens = _significant_tokens(company_name)
    if not tokens:
        return True
    return any(t in haystack for t in tokens)


def _slug_matches_name(slug: str, person_name: str) -> bool:
    """
    Return True if the LinkedIn profile slug plausibly belongs to person_name.

    Requires BOTH a first-name and a last-name token to appear as hyphen-delimited
    slug segments (with nickname/prefix tolerance). A single shared token — surname
    OR first name alone — is NOT enough, because Google's `site:linkedin.com/in`
    results routinely surface colleagues and relatives that share one name part,
    producing wrong-profile assignments:

      slug "douglas-adams-3a0"  person "Kristen Adams"     → False ❌ (surname only)
      slug "alexandra-liveris"  person "Andrew Liveris"    → False ❌ (surname only)
      slug "joe-burnett-cfa"    person "Joe Barry"         → False ❌ (first name only)
      slug "rob-harding-162"    person "Robert Harding"    → True  ✅ (rob~robert + harding)
      slug "elliott-grover-97"  person "Elliot Grover"     → True  ✅
      slug "harriet-coley-"     person "Courtney Burgess"  → False ❌

    Names with a single significant token fall back to requiring that one token.
    Tokens are de-accented and the slug is URL-decoded first, so "François Dubois"
    matches "francois-dubois" and "Petra Pálfi" matches "petra-p%C3%A1lfi".
    """
    segments = set(re.split(r"[^a-z0-9]+", _fold_ascii(unquote(slug))))
    tokens = _significant_tokens(person_name)
    if not tokens:
        return False
    if len(tokens) == 1:
        return _token_matches_segment(tokens[0], segments)
    first, last = tokens[0], tokens[-1]
    return _token_matches_segment(first, segments) and _token_matches_segment(last, segments)


class ApifyLinkedInEmployeesClient:
    """Client for Apify harvestapi/linkedin-company-employees actor."""

    ACTOR_ID = "harvestapi/linkedin-company-employees"
    GOOGLE_ACTOR_ID = "apify/google-search-scraper"

    def __init__(self, api_token: Optional[str] = None):
        from apify_client import ApifyClient
        self.client = ApifyClient(api_token or settings.APIFY_API_TOKEN)
        self._last_run: dict | None = None

    def _resolve_linkedin_company_url(
        self, company_name: str, company_url: str
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Resolve a company website URL to its LinkedIn company page URL and display name.

        Returns (linkedin_url, display_name). The display name is extracted from the
        Google result title (e.g. "Stratton HR | LinkedIn" → "Stratton HR") and is
        more reliable than the stored company name for use in people search queries —
        especially when the stored name is a LinkedIn slug like "strattonhr" rather
        than the human-readable "Stratton HR".
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
            dataset = self.client.dataset(_run_dataset_id(run))

            for item in dataset.iterate_items():
                for result in item.get("organicResults", []):
                    url = result.get("url", "")
                    if "linkedin.com/company/" in url:
                        match = re.search(r"linkedin\.com/company/([^/?#]+)", url)
                        if match:
                            slug = match.group(1)
                            linkedin_url = f"https://www.linkedin.com/company/{slug}"
                            # Extract display name from title: "Stratton HR | LinkedIn"
                            title = result.get("title", "")
                            display_name = re.split(r"\s*[|\-–]\s*LinkedIn", title, maxsplit=1)[0].strip()
                            display_name = display_name or None
                            log.info(
                                f"Resolved LinkedIn company URL: {linkedin_url} "
                                f"(display name: {display_name!r})"
                            )
                            return linkedin_url, display_name

        except Exception as exc:
            log.error(f"Failed to resolve LinkedIn company URL for {company_name}: {exc}")

        return None, None

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
            linkedin_url, _ = self._resolve_linkedin_company_url(company_name, company_url)
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
            dataset = self.client.dataset(_run_dataset_id(run))
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

    def search_people_google_batch(
        self,
        person_names: list[str],
        company_name: str,
        batch_size: int = 25,
    ) -> dict[str, str]:
        """
        Batch Google search for multiple people. Each person gets two queries
        (with and without company qualifier). Processes in groups of batch_size.
        Returns {person_name: linkedin_profile_url}.
        """
        results: dict[str, str] = {}
        total_batches = -(-len(person_names) // batch_size)
        for i in range(0, len(person_names), batch_size):
            batch = person_names[i : i + batch_size]
            batch_results = self._google_people_batch_call(batch, company_name)
            results.update(batch_results)
            log.info(
                f"  Google batch {i // batch_size + 1}/{total_batches}: "
                f"{len(batch_results)}/{len(batch)} resolved"
            )
        return results

    def _google_people_batch_call(
        self, person_names: list[str], company_name: str
    ) -> dict[str, str]:
        """
        Execute one Google actor call with one company-qualified query per person:
          site:linkedin.com/in "Name" "Company"

        No unqualified fallback — unqualified queries return profiles where the
        searched name appears as a mention (recommendation, colleague reference),
        not as the profile owner, producing systematic false positives.

        Each result is validated on two axes before being accepted:
          1. _slug_matches_name — the URL slug must carry the person's name.
          2. _company_in_text   — the company must appear in the result title/snippet.
        The company check is what disambiguates two different people who share a name
        (only one works at the target company); name-in-slug alone cannot. A final
        cross-batch dedup then removes any URL assigned to multiple people.

        Returns {person_name: linkedin_url}.
        """
        lines = [
            f'site:linkedin.com/in "{name}" "{company_name}"'
            for name in person_names
        ]
        queries = "\n".join(lines)

        run_input = {
            "queries": queries,
            "maxPagesPerQuery": 1,
            "resultsPerPage": 5,
            "languageCode": "en",
            "mobileResults": False,
        }
        run = self.client.actor(self.GOOGLE_ACTOR_ID).call(run_input=run_input)
        self._last_run = run
        dataset = self.client.dataset(_run_dataset_id(run))

        results: dict[str, str] = {}
        for item in dataset.iterate_items():
            term = (item.get("searchQuery") or {}).get("term", "")
            name_match = re.search(r'"([^"]+)"', term)
            if not name_match:
                continue
            person_name = name_match.group(1)
            if person_name in results:
                continue
            for result in item.get("organicResults", []):
                url = result.get("url", "")
                if "linkedin.com/in/" not in url:
                    continue
                m = re.search(r"linkedin\.com/in/([^/?#]+)", url)
                if not m or not _slug_matches_name(m.group(1), person_name):
                    continue
                snippet = " ".join(
                    filter(
                        None,
                        [
                            result.get("title", ""),
                            result.get("description", ""),
                            result.get("snippet", ""),
                        ],
                    )
                )
                if not _company_in_text(company_name, snippet):
                    log.info(
                        f"  Google: name matches but company {company_name!r} absent "
                        f"in snippet for {person_name!r} — skipping {m.group(1)}"
                    )
                    continue
                results[person_name] = f"https://www.linkedin.com/in/{m.group(1)}"
                break

        # Cross-batch dedup: if the same URL appears for multiple people it is a
        # false positive for all but the one whose name actually matches the slug.
        url_to_names: dict[str, list[str]] = {}
        for name, url in results.items():
            url_to_names.setdefault(url, []).append(name)

        to_drop: list[str] = []
        for url, names in url_to_names.items():
            if len(names) == 1:
                continue
            slug_m = re.search(r"linkedin\.com/in/([^/?#]+)", url)
            slug = slug_m.group(1) if slug_m else ""
            real_owner = next(
                (n for n in names if _slug_matches_name(slug, n)), None
            )
            for name in names:
                if name != real_owner:
                    log.warning(
                        f"  Dropping duplicate URL for {name} -> {url} "
                        f"(real owner: {real_owner!r})"
                    )
                    to_drop.append(name)

        for name in to_drop:
            results.pop(name, None)

        return results

    def search_person_by_name(
        self, person_name: str, company_linkedin_url: str, max_candidates: int = 5
    ) -> tuple[list[dict], object]:
        """
        Search for a specific person by name within a company's LinkedIn people index.

        Uses searchQuery scoped to company_linkedin_url so LinkedIn's own search
        does the filtering — finds advisors and alumni, not just current employees.
        Returns up to max_candidates profiles so the caller can pick the best name
        match rather than blindly accepting the first result.

        Returns (profiles, run).
        """
        run_input = {
            "companies": [company_linkedin_url],
            "maxItems": max_candidates,
            "searchQuery": person_name,
        }
        run = self.client.actor(self.ACTOR_ID).call(run_input=run_input)
        self._last_run = run
        items = list(self.client.dataset(_run_dataset_id(run)).iterate_items())
        profiles = [p for item in items if (p := self._parse_employee(item))]
        return profiles, run

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