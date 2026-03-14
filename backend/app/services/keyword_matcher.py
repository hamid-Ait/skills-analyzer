"""Keyword-based expertise matching.

Replicates the deterministic keyword matching logic from the original
Alvarez & Marsal script. Loads keyword maps from JSON files and matches
against a combined text blob built from person profile data.
"""

import json
import logging
from pathlib import Path
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
KEYWORD_DIR = DATA_DIR / "keyword_maps"


def _load_json(path: Path) -> dict | list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# Load keyword maps once at module level
_EXPERTISE_13: dict[str, list[str]] = _load_json(KEYWORD_DIR / "expertise_13.json")
_FUNCTIONAL_KW: dict[str, list[str]] = _load_json(KEYWORD_DIR / "functional_keywords.json")
_SECTOR_KW: dict[str, list[str]] = _load_json(KEYWORD_DIR / "sector_keywords.json")
_GEOGRAPHY_KW: dict[str, list[str]] = _load_json(KEYWORD_DIR / "geography_keywords.json")

# Primary expertise priority order (for selecting a single label)
_PRIMARY_PRIORITY = [
    "Finance and Accounting",
    "M&A and Corporate Development",
    "Operational Improvements",
    "Revenue Growth",
    "Technology",
    "People and Talent",
    "Marketing",
    "Legal",
    "Governance (ESG)",
]


@dataclass
class KeywordResult:
    matched_13: list[str] = field(default_factory=list)
    primary_expertise: str = "Management Consulting"
    sectors: list[str] = field(default_factory=list)
    geography: list[str] = field(default_factory=list)
    functional: list[str] = field(default_factory=list)


def build_combined_text(
    headline: str = "",
    about: str = "",
    experience: list[str] | str = "",
    education: list[str] | str = "",
    raw_text: str = "",
    bio: str = "",
    title: str = "",
    department: str = "",
    skills: list[str] | None = None,
) -> str:
    """Combine all available text into a single lowercase string for matching."""
    parts = [headline, about]
    if isinstance(experience, list):
        parts.append(" ".join(experience))
    else:
        parts.append(experience)
    if isinstance(education, list):
        parts.append(" ".join(education))
    else:
        parts.append(education)
    parts.extend([raw_text, bio, title, department])
    if skills:
        parts.append(" ".join(skills))
    return " ".join(p for p in parts if p).lower()


def _match_against(text: str, keyword_map: dict[str, list[str]]) -> list[str]:
    """Return all categories from keyword_map that have at least one keyword in text."""
    return [cat for cat, keywords in keyword_map.items() if any(kw in text for kw in keywords)]


def _select_primary(matched_13: list[str]) -> str:
    """Select a single primary expertise label using priority order."""
    for p in _PRIMARY_PRIORITY:
        if p in matched_13:
            return p
    return matched_13[0] if matched_13 else "Management Consulting"


def match_person(
    headline: str = "",
    about: str = "",
    experience: list[str] | str = "",
    education: list[str] | str = "",
    raw_text: str = "",
    bio: str = "",
    title: str = "",
    department: str = "",
    skills: list[str] | None = None,
) -> KeywordResult:
    """Run all keyword matches for a single person and return structured results."""
    text = build_combined_text(
        headline=headline, about=about, experience=experience,
        education=education, raw_text=raw_text, bio=bio,
        title=title, department=department, skills=skills,
    )
    m13 = _match_against(text, _EXPERTISE_13)
    functional = _match_against(text, _FUNCTIONAL_KW)
    sectors = _match_against(text, _SECTOR_KW)
    geography = _match_against(text, _GEOGRAPHY_KW)
    primary = _select_primary(m13)

    return KeywordResult(
        matched_13=m13,
        primary_expertise=primary,
        sectors=sectors,
        geography=geography,
        functional=functional,
    )


def match_person_from_db(person) -> KeywordResult:
    """Match using a Person ORM object, pulling all available fields."""
    experience_text = ""
    if person.linkedin_experience_summary:
        experience_text = person.linkedin_experience_summary
    elif person.linkedin_experience:
        # JSONB field — extract text from structured data
        exp = person.linkedin_experience
        if isinstance(exp, list):
            experience_text = " ".join(
                f"{e.get('title', '')} {e.get('company', '')} {e.get('description', '')}"
                for e in exp
            )

    return match_person(
        headline=person.linkedin_headline or "",
        about=person.linkedin_summary or "",
        experience=experience_text,
        bio=person.bio or "",
        title=person.title or "",
        department=person.department or "",
        skills=person.linkedin_skills,
    )
