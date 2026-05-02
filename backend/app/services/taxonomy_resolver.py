"""Company-specific taxonomy resolver.

Maps a firm's declared capabilities and industries to Layer 1 categories and
matched_sectors entries. Taxonomy files live in docs/resources/<company_slug>/.
Returns None gracefully when no taxonomy exists for a company.
"""

import json
import logging
import re
from pathlib import Path
from functools import lru_cache

log = logging.getLogger(__name__)

# Root of docs/resources/ relative to this file (backend/app/services/ → ../../../../docs/resources)
_RESOURCES_ROOT = Path(__file__).parent.parent.parent.parent / "docs" / "resources"

# ---------------------------------------------------------------------------
# Capability → Layer 1 mapping
# ---------------------------------------------------------------------------
_CAPABILITY_TO_L1: dict[str, str] = {
    # Parent capabilities
    "Mergers & Acquisitions":                "M&A and Corporate Development",
    "Post-Merger Integration":               "M&A and Corporate Development",
    "Pricing & Revenue Optimization":        "Revenue Growth",
    "Marketing & Sales":                     "Marketing",
    "Operations & Supply Chain":             "Operational Improvements",
    "Performance Improvement":               "Operational Improvements",
    "Procurement":                           "Operational Improvements",
    "Organization Design and Effectiveness": "People and Talent",
    "Artificial Intelligence":               "Technology",
    "Data & Analytics":                      "Technology",
    "Digital":                               "Technology",
    "Sustainability":                        "Environment (ESG)",
    # Children broad enough for Layer 1
    "Organizational Design":                 "People and Talent",
    "Organizational Effectiveness":          "People and Talent",
    "Brand Strategy":                        "Marketing",
    "Marketing Strategy":                    "Marketing",
    "Commercial Excellence":                 "Revenue Growth",
    "Cost Optimization":                     "Operational Improvements",
    "Supply Chain Strategy":                 "Operational Improvements",
    # M&A sub-activities
    "Due Diligence":                         "M&A and Corporate Development",
    "Operational Due Diligence":             "M&A and Corporate Development",
    "Carve-outs & Divestitures":             "M&A and Corporate Development",
    "M&A Synergies":                         "M&A and Corporate Development",
    "Target Identification":                 "M&A and Corporate Development",
    "Exit Support":                          "M&A and Corporate Development",
    "Joint Ventures and Alliances":          "M&A and Corporate Development",
}

_CAPABILITY_SKIP: frozenset[str] = frozenset({
    "Strategy", "Private Equity", "Analytical Sciences",
    "Major Capital Projects Advisory", "Predictable Innovation", "Hidden Terms",
})

# ---------------------------------------------------------------------------
# Industry → matched_sectors mapping (multi-value)
# ---------------------------------------------------------------------------
_INDUSTRY_TO_MATCHED_SECTORS: dict[str, list[str]] = {
    # Parent industries
    "Business Services":             ["Professional, Business & Support Services"],
    "Consumer Products":             ["Consumer"],
    "Education":                     ["Education & Training"],
    "Energy & Environment":          ["Energy", "Environment"],
    "Financial Services":            ["Financial, Investment and Insurance Services"],
    "Healthcare Services":           ["Healthcare, Medical & Social Care"],
    "Industrials":                   ["Industrials", "Manufacturing and Product Development"],
    "Life Sciences & Pharma":        ["Life Sciences", "Pharmaceutical"],
    "Media & Entertainment":         ["Media, News, Publishing & Information Services",
                                      "Arts, Entertainment, Recreation, Sports"],
    "MedTech":                       ["Life Sciences"],
    "Private Equity":                ["Financial, Investment and Insurance Services"],
    "Retail":                        ["Wholesale, Retail & Hiring"],
    "Technology":                    ["Computing, Technology, Robotics & AI"],
    "Travel, Transport & Logistics": ["Transportation and Logistics"],
    # Children with precision or multi-mapping
    "Aerospace & Defense":           ["Aerospace", "Defence, Protection and Security"],
    "Agribusiness":                  ["Agriculture, Horticulture, Forestry & Fishing"],
    "Automotive":                    ["Automotive"],
    "Biotech and Pharmaceuticals":   ["Life Sciences", "Pharmaceutical"],
    "Building & Construction":       ["Construction",
                                      "Civil, Mechanical, Electrical Engineering and Architecture"],
    "Chemicals":                     ["Chemicals and Materials"],
    "Construction & Engineering":    ["Construction",
                                      "Civil, Mechanical, Electrical Engineering and Architecture"],
    "Fintech":                       ["Financial, Investment and Insurance Services",
                                      "Computing, Technology, Robotics & AI"],
    "Freight & Logistics":           ["Transportation and Logistics", "Warehousing and Storage"],
    "Hotel & Hospitality":           ["Tourism, Travel and Hospitality"],
    "Lotteries & Casinos":           ["Arts, Entertainment, Recreation, Sports"],
    "Maritime":                      ["Maritime & Marine"],
    "Metals & Mining":               ["Mining, Quarrying and Extraction"],
    "Pet":                           ["Pets & Domesticated Animals"],
    "Rail":                          ["Transportation and Logistics"],
    "Renewables":                    ["Energy", "Environment"],
    "Tech-Enabled Services and Healthcare IT":
                                     ["Healthcare, Medical & Social Care",
                                      "Computing, Technology, Robotics & AI"],
    "Telehealth and Digital Transformation":
                                     ["Healthcare, Medical & Social Care",
                                      "Computing, Technology, Robotics & AI"],
    "Water":                         ["Utilities", "Environment"],
    "Food & Beverage":               ["Food and Beverage"],
    "Foodservice":                   ["Food and Beverage", "Tourism, Travel and Hospitality"],
    "Grocery":                       ["Food and Beverage", "Wholesale, Retail & Hiring"],
    "Restaurant":                    ["Food and Beverage", "Tourism, Travel and Hospitality"],
    "Oil & Gas":                     ["Energy"],
    "Power & Utilities":             ["Energy", "Utilities"],
    "Waste & Recycling":             ["Environment"],
    "Banking":                       ["Financial, Investment and Insurance Services"],
    "Insurance":                     ["Financial, Investment and Insurance Services"],
    "Advertising":                   ["Advertising and Marketing",
                                      "Media, News, Publishing & Information Services"],
    "Publishing":                    ["Media, News, Publishing & Information Services"],
    "Airlines & Aviation":           ["Aerospace", "Transportation and Logistics"],
    "Airports":                      ["Transportation and Logistics"],
    "Higher Education":              ["Education & Training"],
    "K-12":                          ["Education & Training"],
    "Industrial Equipment & Technology": ["Industrials", "Manufacturing and Product Development"],
    "Industrial Services":           ["Industrials",
                                      "Professional, Business & Support Services"],
    "Industrial Distribution":       ["Industrials", "Warehousing and Storage"],
    "Paper & Packaging":             ["Manufacturing and Product Development"],
    "Consumer Tech":                 ["Computing, Technology, Robotics & AI", "Consumer"],
    "Enterprise Software":           ["Computing, Technology, Robotics & AI"],
    "Technology Infrastructure":     ["Computing, Technology, Robotics & AI"],
    "Drug Delivery":                 ["Pharmaceutical", "Life Sciences"],
    "Pharma Services":               ["Pharmaceutical"],
    "Diagnostics, Research Tools and Personalized Medicine": ["Life Sciences"],
    "Acute Care & Hospital":         ["Healthcare, Medical & Social Care"],
    "Mental and Behavioral Health":  ["Healthcare, Medical & Social Care"],
    "Physician Practice Management": ["Healthcare, Medical & Social Care"],
    "Homecare & Home Healthcare":    ["Healthcare, Medical & Social Care"],
}

_INDUSTRY_SKIP: frozenset[str] = frozenset({
    "Hidden Terms", "Commercial Due Diligence",
    "Portfolio Company Value Enhancement", "Vendor Due Diligence",
})


# Common suffixes stripped before slug generation
_STRIP_SUFFIXES = (
    " consulting", " consultants", " advisory", " advisors",
    " group", " partners", " & co", " and co", " llc", " llp", " inc", " ltd",
)

# ---------------------------------------------------------------------------
# Slug normalisation — "L.E.K. Consulting" → "lek"
# ---------------------------------------------------------------------------
def _company_to_slug(company_name: str) -> str:
    name = company_name.lower().strip()
    # Strip common suffixes first
    for suffix in _STRIP_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
            break
    # Remove dots and other punctuation, collapse to letters/digits only
    name = re.sub(r"[^a-z0-9]+", "", name)
    return name


@lru_cache(maxsize=32)
def _load_taxonomy(company_slug: str) -> tuple[list, list] | None:
    """Load (capabilities, industries) for a company slug. Cached."""
    folder = _RESOURCES_ROOT / company_slug
    if not folder.exists():
        return None
    caps, inds = [], []
    cap_path = folder / "capabilities.json"
    ind_path = folder / "industries.json"
    if cap_path.exists():
        try:
            caps = json.loads(cap_path.read_text())["capabilities"]
        except Exception as exc:
            log.warning("Failed to load %s: %s", cap_path, exc)
    if ind_path.exists():
        try:
            inds = json.loads(ind_path.read_text())["industries"]
        except Exception as exc:
            log.warning("Failed to load %s: %s", ind_path, exc)
    return caps, inds


def _flatten_taxonomy(tree: list[dict]) -> set[str]:
    """Return all node names (parents + children) from a taxonomy tree."""
    names: set[str] = set()
    for node in tree:
        names.add(node["name"])
        for child in node.get("children", []):
            if isinstance(child, str):
                names.add(child)
            elif isinstance(child, dict):
                names.add(child.get("name", ""))
    return names


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def resolve_company_taxonomy(
    company_name: str,
    capabilities: list[str],
    industries: list[str],
) -> dict | None:
    """Resolve declared capabilities and industries to Layer 1 and matched_sectors hints.

    Returns a dict with:
        "l1_hints":     list[str]  — Layer 1 category suggestions (deduplicated, sorted)
        "sector_hints": list[str]  — matched_sectors suggestions (deduplicated, sorted)

    Returns None if no taxonomy file exists for the company.
    """
    slug = _company_to_slug(company_name)
    taxonomy = _load_taxonomy(slug)
    if taxonomy is None:
        return None

    cap_tree, ind_tree = taxonomy
    known_caps = _flatten_taxonomy(cap_tree)
    known_inds = _flatten_taxonomy(ind_tree)

    l1_hints: set[str] = set()
    for cap in capabilities:
        cap = cap.strip()
        if cap in _CAPABILITY_SKIP:
            continue
        if cap not in known_caps:
            continue
        l1 = _CAPABILITY_TO_L1.get(cap)
        if l1:
            l1_hints.add(l1)

    sector_hints: set[str] = set()
    for ind in industries:
        ind = ind.strip()
        if ind in _INDUSTRY_SKIP:
            continue
        if ind not in known_inds:
            continue
        sectors = _INDUSTRY_TO_MATCHED_SECTORS.get(ind)
        if sectors:
            sector_hints.update(sectors)

    if not l1_hints and not sector_hints:
        return None

    return {
        "l1_hints": sorted(l1_hints),
        "sector_hints": sorted(sector_hints),
    }