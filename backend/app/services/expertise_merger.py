"""Merge keyword-matched and LLM-classified expertise results.

Only the 13 explicit categories have a fixed taxonomy and get validated.
All other fields (functional, topics, sectors, geographies) are free-form
LLM output and pass through without taxonomy validation.

The keyword matcher still contributes to the 13 categories (deterministic baseline).
"""

import logging
from difflib import get_close_matches, SequenceMatcher

from app.services.keyword_matcher import KeywordResult
from app.services.expertise_analyzer import EXPERTISE_CATEGORIES

log = logging.getLogger(__name__)

# ── Alias map for the 13 categories ──────────────────────────────────────────
_ALIASES_13: dict[str, str] = {
    "tax": "Finance and Accounting",
    "tax advisory": "Finance and Accounting",
    "restructuring": "M&A and Corporate Development",
    "digital": "Technology",
    "data analytics": "Technology",
    "esg": "Environment (ESG)",
    "hr": "People and Talent",
    "human resources": "People and Talent",
}

_VALID_13 = {v.lower(): v for v in EXPERTISE_CATEGORIES}


def _validate_13(values: list) -> list[str]:
    """Validate values against the 13-category taxonomy.

    Pipeline: exact → alias → fuzzy (0.8) → reject.
    """
    normalized = []
    for v in values:
        if not v or not isinstance(v, str):
            continue
        v_lower = v.strip().lower()

        # 1. Exact match
        if v_lower in _VALID_13:
            normalized.append(_VALID_13[v_lower])
            continue

        # 2. Alias
        canonical = _ALIASES_13.get(v_lower)
        if canonical and canonical.lower() in _VALID_13:
            normalized.append(_VALID_13[canonical.lower()])
            continue

        # 3. Fuzzy (cutoff=0.8 — strict, only catches typos)
        close = get_close_matches(v_lower, _VALID_13.keys(), n=1, cutoff=0.8)
        if close:
            normalized.append(_VALID_13[close[0]])
            continue

        # 4. Rejected
        best_score = 0.0
        best_match = None
        for tax_lower, tax_canonical in _VALID_13.items():
            s = SequenceMatcher(None, v_lower, tax_lower).ratio()
            if s > best_score:
                best_score = s
                best_match = tax_canonical
        log.warning(
            "  Rejected '%s' [explicit_expertise_13] — nearest: '%s' (%.2f)",
            v, best_match, best_score,
        )

    return sorted(set(normalized))


def merge(keyword_result: KeywordResult, llm_result: dict) -> dict:
    """Merge keyword + LLM results.

    Only the 13 categories are validated against a fixed taxonomy.
    Everything else passes through from the LLM.
    """
    # ── explicit_expertise_13 (validated) ────────────────────────────────
    kw_13 = keyword_result.matched_13
    llm_13 = llm_result.get("explicit_expertise_13") or llm_result.get("matched_13_categories") or []
    if isinstance(llm_13, str):
        llm_13 = [s.strip() for s in llm_13.split(";")]
    merged_13 = _validate_13(list(set(kw_13 + llm_13)))

    # ── primary_expertise ────────────────────────────────────────────────
    primary = llm_result.get("primary_expertise") or keyword_result.primary_expertise

    # ── justification ────────────────────────────────────────────────────
    justification = llm_result.get("justification") or ""

    # ── sectors (free-form from LLM) ─────────────────────────────────────
    sectors = llm_result.get("sectors") or llm_result.get("sector") or []
    if isinstance(sectors, str):
        sectors = [s.strip() for s in sectors.split(";") if s.strip()]

    # ── geographies (free-form from LLM) ─────────────────────────────────
    geographies = llm_result.get("geographies") or llm_result.get("geography") or []
    if isinstance(geographies, str):
        geographies = [s.strip() for s in geographies.split(";") if s.strip()]

    # ── inferred_expertise_functional (free-form from LLM) ───────────────
    func = llm_result.get("inferred_expertise_functional") or []
    if isinstance(func, str):
        func = [s.strip() for s in func.split(";") if s.strip()]

    # ── topic_overlap (free-form from LLM) ───────────────────────────────
    topics = llm_result.get("topic_overlap") or llm_result.get("matched_inferred_expertise_topics") or []
    if isinstance(topics, str):
        topics = [s.strip() for s in topics.split(";") if s.strip()]

    return {
        "primary_expertise": primary,
        "justification": justification,
        "explicit_expertise_13": merged_13,
        "sectors": sectors,
        "geographies": geographies,
        "inferred_expertise_functional": func,
        "topic_overlap": topics,
        "inference_reasoning": llm_result.get("inference_reasoning"),
    }


def merge_keyword_only(keyword_result: KeywordResult) -> dict:
    """Build a result dict from keyword matching alone (no LLM available)."""
    return {
        "primary_expertise": keyword_result.primary_expertise,
        "justification": None,
        "explicit_expertise_13": keyword_result.matched_13,
        "sectors": keyword_result.sectors,
        "geographies": keyword_result.geography,
        "inferred_expertise_functional": [],
        "topic_overlap": [],
    }