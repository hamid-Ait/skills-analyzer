from dataclasses import dataclass, field

from app.services.expertise_analyzer import EXPERTISE_CATEGORIES, MATCHED_SECTOR_VOCAB

_EXPERTISE_SET: frozenset[str] = frozenset(EXPERTISE_CATEGORIES)
_MATCHED_SECTOR_SET: frozenset[str] = frozenset(MATCHED_SECTOR_VOCAB)
_GEO_SET: frozenset[str] = frozenset(
    {"Europe", "North America", "Asia Pacific", "Middle East & Africa", "Latin America"}
)


@dataclass(frozen=True)
class QAThresholds:
    max_l1_categories: int = 4
    max_declared_capabilities: int = 8
    max_inferred: int = 5
    max_topics: int = 20


@dataclass
class ValidationResult:
    passed: bool
    hard_failures: list[str] = field(default_factory=list)
    soft_warnings: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.hard_failures:
            return "failed"
        if self.soft_warnings:
            return "flagged"
        return "clean"


def validate_person(person, thresholds: QAThresholds) -> ValidationResult:
    raw: dict = person.expertise_raw or {}
    hard: list[str] = []
    soft: list[str] = []

    cats: list[str] = person.matched_13_categories or []
    inferred: list[str] = person.inferred_expertise_functional or []
    sectors: list[str] = person.matched_sector or []
    topics: list[str] = person.matched_inferred_expertise_topics or []
    declared: list[str] = raw.get("declared_narrow_capabilities") or []
    pe: str | None = person.primary_expertise

    # ── Taxonomy ──────────────────────────────────────────────────────────────
    if pe and pe not in _EXPERTISE_SET:
        hard.append(f"primary_expertise '{pe}' is not a valid taxonomy value")

    invalid_cats = [c for c in cats if c not in _EXPERTISE_SET]
    if invalid_cats:
        hard.append(f"matched_13_categories contains invalid values: {invalid_cats}")

    invalid_sectors = [s for s in sectors if s not in _MATCHED_SECTOR_SET]
    if invalid_sectors:
        hard.append(f"matched_sector contains invalid values: {invalid_sectors}")

    # ── Count violations (soft — over-count is noisy but not incorrect) ─────────
    if len(cats) > thresholds.max_l1_categories:
        soft.append(
            f"matched_13_categories has {len(cats)} items (max {thresholds.max_l1_categories})"
        )
    if len(declared) > thresholds.max_declared_capabilities:
        soft.append(
            f"declared_narrow_capabilities has {len(declared)} items "
            f"(max {thresholds.max_declared_capabilities})"
        )
    if len(inferred) > thresholds.max_inferred:
        soft.append(
            f"inferred_expertise_functional has {len(inferred)} items "
            f"(max {thresholds.max_inferred})"
        )
    if len(topics) > thresholds.max_topics:
        soft.append(f"topic_overlap has {len(topics)} items (max {thresholds.max_topics})")

    # ── Cross-field consistency ───────────────────────────────────────────────
    if pe and cats and pe not in cats:
        hard.append(f"primary_expertise '{pe}' not present in matched_13_categories")

    if inferred and not person.inference_reasoning:
        hard.append("inference_reasoning is empty but inferred_expertise_functional is non-empty")

    evidence_map: dict = raw.get("evidence_map") or {}
    em_matched = evidence_map.get("matched_sectors")
    # Only check keys that are valid vocabulary strings — invalid keys in evidence_map
    # are a separate taxonomy violation, not a consistency issue
    em_sector_keys = (
        {k for k in em_matched.keys() if k in _MATCHED_SECTOR_SET}
        if isinstance(em_matched, dict)
        else set()
    )
    missing_from_output = em_sector_keys - set(sectors)
    if missing_from_output:
        hard.append(
            f"evidence_map.matched_sectors has entries not committed to matched_sector output: "
            f"{sorted(missing_from_output)}"
        )

    # ── Verbatim copy detection in Layer 2 ───────────────────────────────────
    # Only check declared fields — narrative fields (bio, experience) are
    # inference triggers, not capability declarations.
    extra = person.extra or {}
    declared_text = " ".join([
        person.linkedin_headline or "",
        person.linkedin_summary or "",
        " ".join(getattr(person, "linkedin_skills", None) or []),
        " ".join(extra.get("expertise_capabilities") or []),
    ]).lower()

    verbatim = [i for i in inferred if i.lower() in declared_text]
    if verbatim:
        hard.append(
            f"inferred_expertise_functional contains verbatim profile text: {verbatim}"
        )

    # ── Soft flags ────────────────────────────────────────────────────────────
    if not sectors and person.expertise_raw:
        soft.append("matched_sector is empty — sector inference may have failed")

    if not cats and person.expertise_raw:
        soft.append("matched_13_categories is empty — no L1 category assigned")

    if not pe and person.expertise_raw:
        soft.append("primary_expertise is not set after analysis")

    return ValidationResult(
        passed=len(hard) == 0,
        hard_failures=hard,
        soft_warnings=soft,
    )


def categorize_issue(message: str) -> str:
    m = message.lower()
    if "not a valid taxonomy" in m or "invalid values" in m:
        return "taxonomy_violation"
    if "items (max" in m:
        return "count_violation"
    if "verbatim" in m:
        return "verbatim_copy"
    if "evidence_map" in m or "not committed" in m or "not present in" in m:
        return "consistency"
    if "empty" in m or "not set" in m:
        return "missing_fields"
    return "other"