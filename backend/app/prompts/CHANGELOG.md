# Prompt Changelog

## v4 (current)

**Precision fixes — Rule 1 escape valve, L2 self-check restructure, L1.5/L3 decision test, sector disambiguation, geography scope**

- **Rule 1 escape valve (PRIMARY EXPERTISE)**: Added a narrow exception to the sector-lead/practice-head override. Rule 1 is now bypassed when the body of work explicitly and overwhelmingly demonstrates a different functional category AND there is no evidence the person does work in the title domain (e.g. "Global Healthcare Sector Lead" whose entire career is M&A deal execution with zero healthcare advisory). Vague bio language or mixed signals still do NOT override Rule 1. Root cause: Rule 1 was a hard override with no escape, conflating sector-client focus with functional expertise in edge cases.

- **Layer 2 self-check restructure**: Reorganised the mandatory self-check so the elaboration exception is evaluated *inside* the check procedure (step 3), not as a separate afterthought. The new flow is: search → if absent, may qualify → if found, ask "is this a genuinely more specific elaboration?" → if yes, may still qualify; if no, stop. Added an explicit "elaboration test" (two conditions must hold: broad term in profile, candidate is a more specific concrete technique) and added examples that show the abstraction-level distinction ("pricing strategy" → "Pricing Strategy" is same-level, blocked; "pricing work" → "Value-Based Pricing Implementation" is genuinely more specific, allowed). Root cause: the check and the exception were written in sequence, creating apparent contradiction about whether "core words" found in the profile always block inclusion.

- **Layer 1.5 vs Layer 3 decision test**: Added explicit "service offering vs technique" test to replace the vague "too narrow for Layer 1" / "sub-topics" distinction. Test: "Would a consulting firm list this on their website as a named service offering a client could buy?" → YES = L1.5. "Would this appear in a deliverable or methodology description?" → YES = L3. Root cause: L1.5 and L3 boundaries were ambiguous, producing inconsistent placement of items like "Post-merger Integration" (L1.5) vs "Day-1 readiness planning" (L3).

- **Matched sectors disambiguation hierarchy fix**: Specificity over frequency now explicitly applies only *within the same sector cluster*. Across different sector families, frequency always wins. Example: "Life Sciences" 5× vs "Pharmaceutical" 1× → frequency wins, use "Life Sciences". "Life Sciences" 2× vs "Pharmaceutical" 2× → specificity tiebreak → "Pharmaceutical" (drug-focused). Root cause: original hierarchy said "specificity first, frequency second" without stating that specificity only applies within the same cluster, leading models to always prefer the more specific string regardless of evidence weight.

- **Geography regional scope clarification**: Replaced vague "role is regional in scope" test with a concrete rule: regional scope requires an explicit regional designation in the title, not just an office city. Added examples of what qualifies (e.g. "Head of UK & Ireland", "Director, DACH Region") vs what does not ("Partner, London", "Managing Director, Chicago"). Root cause: "Partner, London" was ambiguously treated as regional scope evidence.

- **Evidence map resolved hints guidance**: Added note that for `resolved_l1_hints` and `resolved_sector_hints`, the `text` field should quote the hint string itself (these are pre-computed signals, not raw profile text). Root cause: evidence map table had no guidance for pre-computed injection fields.

- **Layer 2 verbatim check scoped to declared fields only**: The mandatory self-check and post-processing strip now only examine `linkedin_headline`, `linkedin_summary`, `linkedin_skills`, and `website_capabilities`. Narrative fields (`bio`, `title`, `department`, `linkedin_experience`) are inference triggers — a phrase appearing in a career narrative does not make it an explicit declaration. Also clarified that single generic words (`"strategy"`, `"growth"`, `"operations"`) appearing in declared fields do NOT block a candidate; only domain-specific compound phrases count. Root cause: the full-corpus verbatim check was suppressing genuine inferences because functional terms naturally appear in narrative career descriptions, resulting in 1-2 L2 items per profile instead of the expected 3-5.

- **Evidence semantics by layer — L2 trigger vs citation distinction**: Added explicit section clarifying that `inferred` evidence entries record the **inference trigger** (what in the profile implied the capability), NOT a quote of the capability itself. For L1/L1.5/sectors the `text` is a direct citation; for L2 it is the reasoning chain input — the phrase that justified the deduction. Role-standard inferences (e.g. "CFO" → "Financial Planning & Analysis") may cite the title/seniority signal as the sole trigger. Root cause: the same `{"source", "text"}` schema was used for all layers, creating ambiguity about whether L2 evidence should cite the capability (impossible by definition — the self-check blocks it) or cite the trigger (correct). Models were either hallucinating evidence quotes or conflating the two, producing verbatim-copy failures in disguise.

## v3 (previous)

**Structural rework — added Layer 1.5, tightened Layer 2 gate, expanded Layer 3 scope**

### v3 patches

- **Primary expertise tiebreak (Rule 1) — practice-head/sector-lead titles**: Rule 1 now explicitly covers practice-lead and sector-lead roles (e.g., "Global TMT Sector Lead", "Healthcare Practice Head"). The named domain maps directly to the closest `<expertise>` string and stops — the model must NOT fall through to bio or frequency signals. Domain mapping examples added inline (TMT → Technology, M&A → M&A and Corporate Development, etc.). Root cause: model was mixing title + bio signals for "TMT Sector Lead" and assigning Revenue Growth instead of Technology.
- **Matched sectors / evidence_map consistency rule**: Added validation check that every key in `evidence_map.matched_sectors` must also appear in the `matched_sectors` output array. Root cause: model was recording sector evidence in evidence_map but outputting `matched_sectors: []`.
- **Layer 2 verbatim copy prevention (major rewrite)**: Replaced the vague "NOT verbatim or near-verbatim" rule with a mandatory step-by-step self-check procedure. The model must now search for each candidate phrase in every profile field before including it. Added definition of what counts as "appears in the profile" (exact, reordering, partial, synonym, skill tag), the one allowed exception (meaningfully more specific elaboration), and four WRONG/CORRECT contrast examples. Root cause: models were copying profile text into Layer 2 because the rule was abstract; a concrete procedure is harder to circumvent.

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