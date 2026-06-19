"""Merge keyword-matched and LLM-classified expertise results.

Only the 13 explicit categories have a fixed taxonomy and get validated.
All other fields (functional, topics, sectors, geographies) are free-form
LLM output and pass through without taxonomy validation.

The keyword matcher still contributes to the 13 categories (deterministic baseline).
"""

import logging
from difflib import get_close_matches, SequenceMatcher

from app.services.keyword_matcher import KeywordResult
from app.services.expertise_analyzer import (
    EXPERTISE_CATEGORIES,
    MATCHED_SECTOR_VOCAB,
    SECTOR_VOCAB,
    resolve_matched_sectors,
)

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

# All known sector vocabulary (both free-form and controlled) — used to detect
# sector names being misassigned to expertise fields.
_SECTOR_INTRUDERS: frozenset[str] = frozenset(
    v.lower() for v in SECTOR_VOCAB + MATCHED_SECTOR_VOCAB
)

# Best-effort mapping from sector name → closest L1 category.
# Used when primary_expertise is a sector name and we need a valid fallback.
_SECTOR_TO_L1: dict[str, str] = {
    "technology & software": "Technology",
    "computing, technology, robotics & ai": "Technology",
    "telecommunications": "Technology",
    "electronics & electrical": "Technology",
    "financial services": "Finance and Accounting",
    "financial, investment and insurance services": "Finance and Accounting",
    "insurance": "Finance and Accounting",
    "private equity": "M&A and Corporate Development",
    "real estate": "Real Estate & Assets",
    "real estate & property: industrial, commercial and private": "Real Estate & Assets",
    "energy & utilities": "Environment (ESG)",
    "energy": "Environment (ESG)",
    "utilities": "Environment (ESG)",
    "environment": "Environment (ESG)",
    "media & entertainment": "Marketing",
    "media, news, publishing & information services": "Marketing",
    "advertising and marketing": "Marketing",
    "transportation & logistics": "Operational Improvements",
    "transportation and logistics": "Operational Improvements",
    "warehousing and storage": "Operational Improvements",
    "industrials & manufacturing": "Operational Improvements",
    "manufacturing and product development": "Operational Improvements",
    "automotive": "Operational Improvements",
}

_VALID_13 = {v.lower(): v for v in EXPERTISE_CATEGORIES}
_VALID_PRIMARY = {v.lower(): v for v in EXPERTISE_CATEGORIES}  # same set, named for clarity


def _validate_13(values: list) -> list[str]:
    """Validate values against the 13-category taxonomy.

    Pipeline: sector-blocklist → exact → alias → fuzzy (0.8) → reject.
    """
    normalized = []
    for v in values:
        if not v or not isinstance(v, str):
            continue
        v_lower = v.strip().lower()

        # 0. Sector intruder — silently drop, no warning needed
        if v_lower in _SECTOR_INTRUDERS:
            log.debug("  Dropped sector '%s' from explicit_expertise_13", v)
            continue

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

        # 4. Rejected — only log nearest if it's a plausible match (≥0.6)
        best_score = 0.0
        best_match = None
        for tax_lower, tax_canonical in _VALID_13.items():
            s = SequenceMatcher(None, v_lower, tax_lower).ratio()
            if s > best_score:
                best_score = s
                best_match = tax_canonical
        if best_score >= 0.6:
            log.warning(
                "  Rejected '%s' [explicit_expertise_13] — nearest: '%s' (%.2f)",
                v, best_match, best_score,
            )
        else:
            log.warning(
                "  Rejected '%s' [explicit_expertise_13] — no close match (best %.2f)",
                v, best_score,
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
    merged_13 = _validate_13(list(set(llm_13)))  # kw_13 disabled — LLM only

    # ── primary_expertise ────────────────────────────────────────────────
    primary = llm_result.get("primary_expertise") or keyword_result.primary_expertise

    # Guard: primary_expertise must be a valid L1 taxonomy value.
    # The model occasionally assigns a sector name (e.g. "Pharmaceuticals & Life Sciences").
    if primary:
        primary_lower = primary.strip().lower()
        if primary_lower in _SECTOR_INTRUDERS:
            # Sector name — try hint map first, then first validated L1, else clear
            hint = _SECTOR_TO_L1.get(primary_lower)
            if hint and hint in merged_13:
                fallback = hint
            elif hint:
                fallback = hint  # hint is a valid L1 even if not in merged_13
            else:
                fallback = merged_13[0] if merged_13 else None
            log.warning(
                "  primary_expertise '%s' is a sector name — %s",
                primary, f"using '{fallback}'" if fallback else "clearing",
            )
            primary = fallback
        elif primary_lower not in _VALID_PRIMARY:
            # Fuzzy-correct typos, otherwise fall back
            close = get_close_matches(primary_lower, _VALID_PRIMARY.keys(), n=1, cutoff=0.8)
            if close:
                primary = _VALID_PRIMARY[close[0]]
                log.debug("  primary_expertise '%s' fuzzy-corrected to '%s'", primary_lower, primary)
            else:
                fallback = merged_13[0] if merged_13 else None
                log.warning(
                    "  primary_expertise '%s' is not a valid taxonomy value — %s",
                    primary, f"using '{fallback}'" if fallback else "clearing",
                )
                primary = fallback

    # ── justification ────────────────────────────────────────────────────
    justification = llm_result.get("justification") or ""

    # ── sectors (LLM only — keyword matching removed due to false positives) ──
    llm_sectors = llm_result.get("sectors") or llm_result.get("sector") or []
    if isinstance(llm_sectors, str):
        llm_sectors = [s.strip() for s in llm_sectors.split(";") if s.strip()]
    sectors = list(llm_sectors)

    # ── matched_sectors (resolve integer IDs → canonical names) ─────────────
    llm_matched = llm_result.get("matched_sectors") or []
    if isinstance(llm_matched, str):
        llm_matched = [s.strip() for s in llm_matched.split(";") if s.strip()]
    matched_sectors = resolve_matched_sectors(llm_matched)

    # ── geographies (merge keyword + LLM) ────────────────────────────────
    llm_geo = llm_result.get("geographies") or llm_result.get("geography") or []
    if isinstance(llm_geo, str):
        llm_geo = [s.strip() for s in llm_geo.split(";") if s.strip()]
    kw_geo = keyword_result.geography or []
    seen_geo = {g.lower() for g in llm_geo}
    geographies = list(llm_geo)
    for g in kw_geo:
        if g.lower() not in seen_geo:
            geographies.append(g)
            seen_geo.add(g.lower())

    # ── inferred_expertise_functional (free-form from LLM) ───────────────
    func = llm_result.get("inferred_expertise_functional") or []
    if isinstance(func, str):
        func = [s.strip() for s in func.split(";") if s.strip()]

    # ── topic_overlap (free-form from LLM) ───────────────────────────────
    topics = llm_result.get("topic_overlap") or llm_result.get("matched_inferred_expertise_topics") or []
    if isinstance(topics, str):
        topics = [s.strip() for s in topics.split(";") if s.strip()]

    # Augment evidence_map: for categories the keyword matcher added that the
    # LLM didn't cover, inject the specific keyword(s) that triggered the match.
    evidence_map: dict = dict(llm_result.get("evidence_map") or {})
    categories_evidence: dict = dict(evidence_map.get("categories") or {})
    for cat in kw_13:
        if cat not in categories_evidence:
            hits = keyword_result.matched_13_keywords.get(cat, [])
            categories_evidence[cat] = [
                {"source": "keyword_match", "text": kw} for kw in hits[:5]
            ] or [{"source": "keyword_match", "text": "keyword analysis"}]
    if categories_evidence:
        evidence_map["categories"] = categories_evidence

    return {
        "primary_expertise": primary,
        "justification": justification,
        "explicit_expertise_13": merged_13,
        "sectors": sectors,
        "matched_sectors": matched_sectors,
        "geographies": geographies,
        "inferred_expertise_functional": func,
        "topic_overlap": topics,
        "inference_reasoning": llm_result.get("inference_reasoning"),
        "company_practice": llm_result.get("company_practice"),
        "evidence_map": evidence_map,
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