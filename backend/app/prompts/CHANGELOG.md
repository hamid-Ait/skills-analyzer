# Prompt Changelog

## v3 (current)

**Structural rework — added Layer 1.5, tightened Layer 2 gate, expanded Layer 3 scope**

### v3 patches

- **Primary expertise tiebreak (Rule 1) — practice-head/sector-lead titles**: Rule 1 now explicitly covers practice-lead and sector-lead roles (e.g., "Global TMT Sector Lead", "Healthcare Practice Head"). The named domain maps directly to the closest `<expertise>` string and stops — the model must NOT fall through to bio or frequency signals. Domain mapping examples added inline (TMT → Technology, M&A → M&A and Corporate Development, etc.). Root cause: model was mixing title + bio signals for "TMT Sector Lead" and assigning Revenue Growth instead of Technology.
- **Matched sectors / evidence_map consistency rule**: Added validation check that every key in `evidence_map.matched_sectors` must also appear in the `matched_sectors` output array. Root cause: model was recording sector evidence in evidence_map but outputting `matched_sectors: []`.

- **NEW Layer 1.5: Declared Narrow Capabilities (0-8)** — captures `website_capabilities` (and verbatim linkedin_headline/summary items) that are legitimate functional expertise but too narrow for the 13 Layer 1 categories (e.g. "Commercial Due Diligence", "Post-merger Integration", "Working Capital Optimization"). This closes the gap where practice-area level declared capabilities had no clean home in v2.
- **`website_capabilities` routing updated**: L1 if direct 13-category match; L1.5 by default for declared practice-area expertise; L3 for sub-topics narrower than typical capabilities; never L2.
- **Layer 2 condition (b) revised**: more specific elaborations of declared capabilities ARE now allowed (e.g. "Pricing Strategy" declared → "Value-Based Pricing Implementation" qualifies in L2); only same-specificity terms are blocked (e.g. "Commercial Due Diligence" declared → "Commercial Due Diligence" or "Commercial DD" still disqualified).
- **Layer 2 confidence threshold raised**: now requires ≥2 of: seniority signal, quantifiable result, role-standard expectation (v2 required only 1 at >70% confidence).
- **Layer 2 can be populated even if Layer 1 is empty** (seniority + role expectations alone can justify L2 when no 13-category match exists).
- **Layer 3 scope expanded**: can now be populated from L1.5 alone, or when L1 is empty; explicitly prohibits role labels ("CFO Experience") and generic buzzwords ("Strategic Planning"); updated examples reference L1.5.
- **Step 0 condensed**: holistic reading instruction tightened to one paragraph with inline examples; output format and taxonomy rule moved inline.
- **Taxonomy separation rule condensed** to a single line (unchanged in substance).
- **`resolved_l1_hints`**: clarified that absence of bio confirmation is not contradiction — include unless the profile actively conflicts.

## v2

**Major rework — holistic reading, structured taxonomy, evidence map**


- Added Step 0: read profile holistically before classifying (no keyword scanning)
- Layer 1: changed from verbatim-match-only to semantic match ("work described is unambiguously in this domain")
- Layer 2: added strict 3-condition gate (absent from L1, not explicitly stated in website_capabilities/linkedin_headline/linkedin_summary, derived from seniority/results/role expectations); max 5 items (was 3–8)
- Layer 2: added rule blocking near-synonyms/elaborations of declared capabilities (e.g. "Due Diligence" declared → "Commercial Due Diligence" disqualified from L2)
- Layer 3: added rule — items must be distinct from L1 and L2 verbatim; extract sub-topics instead of copying labels
- Sectors: replaced integer ID output with exact string output from controlled vocab
- Sectors: added consolidation rule — one entry per top-level industry, no sub-topic fragmentation
- Sectors: added semantic inference principle with examples (NHS → Healthcare, etc.)
- Sectors: added adjacency mistake callouts (data centers ≠ Real Estate; Food & Beverage ≠ Consumer & Retail; etc.)
- Primary expertise: redefined as "deepest experience + current professional identity"; tiebreak is now strict early-exit (title → practice group → frequency, stop at first match)
- Added evidence map: every assigned item must have source + text passage from the profile
- Added PRE-OUTPUT VALIDATION checklist
- Added INPUT FIELDS section documenting how to use website_industries, website_capabilities, resolved hints

## v1

**Initial prompt — keyword matching, integer matched_sectors, no evidence map**

- Layer 1: verbatim keyword match only; detailed per-category exclusion rules (R&D, Legal, ESG)
- Layer 2: free-form inference with 3–8 target labels; no fixed conditions; banned generic labels (e.g. "Executive Leadership", "Business Transformation")
- Layer 3: topics bridging L1 and L2; up to 20 items
- Sectors: explicit string vocab; matched_sectors returned as integer IDs
- Primary expertise: single most defining category; tiebreak by title → practice group → frequency
- No evidence map
- No holistic reading instruction
- No pre-output validation checklist