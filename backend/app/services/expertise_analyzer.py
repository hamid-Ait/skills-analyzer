import json
import logging
from abc import ABC, abstractmethod

from app.config import settings


log = logging.getLogger(__name__)


# # ── Taxonomy lists (loaded once) ─────────────────────────────────────────────
EXPERTISE_CATEGORIES = [
    "Revenue Growth",
    "Operational Improvements",
    "Finance and Accounting",
    "Marketing",
    "People and Talent",
    "Technology",
    "M&A and Corporate Development",
    "Real Estate & Assets",
    "R&D",
    "Environment (ESG)",
    "Governance (ESG)",
    "Social (ESG)",
    "Legal",
]

INFERRED_VOCAB = [
    "Corporate Restructuring & Turnaround",
    "Forensic Accounting & Investigations",
    "Litigation Support & Expert Witness",
    "Valuation",
    "International Tax",
    "Transfer Pricing",
    "State & Local Tax (SALT)",
    "Tax Controversy & Dispute",
    "Post-Merger Integration (PMI)",
    "Carve-outs & Divestitures",
    "Working Capital & Cash Management",
    "Cost Optimization",
    "Strategy & Corporate Development",
    "Interim Management & CXO",
    "Organizational Design",
    "Change Management",
    "Supply Chain & Procurement",
    "Lean & Operational Excellence",
    "Data Analytics & Business Intelligence",
    "Digital Transformation",
    "Cybersecurity",
    "ERP & Systems Implementation",
    "Private Equity Performance Improvement",
    "Transaction Advisory & Due Diligence",
    "Capital Markets & Investment Banking",
    "Regulatory & Compliance",
    "Risk Management",
    "Pricing Strategy",
    "Customer Experience & CRM",
    "Executive Compensation & Benefits",
    "Corporate Governance & Board Advisory",
    "Anti-Corruption & Integrity",
    "Insolvency & Creditor Advisory",
    "Intellectual Property",
    "Healthcare Operations",
    "Insurance Advisory",
    "Financial Modeling",
    "Economic Analysis",
    "Project Finance",
    "Turnaround Finance",
    "Complex Commercial Litigation",
    "Public Speaking & Thought Leadership",
]

SECTOR_VOCAB = [
    "Healthcare",
    "Pharmaceuticals & Life Sciences",
    "Financial Services",
    "Private Equity",
    "Energy & Utilities",
    "Consumer & Retail",
    "Food & Beverage",
    "Automotive",
    "Industrials & Manufacturing",
    "Technology & Software",
    "Real Estate",
    "Transportation & Logistics",
    "Education",
    "Government & Public Sector",
    "Non-profit & Social Sector",
    "Insurance",
    "Media & Entertainment",
    "Agriculture & Food",
]

MATCHED_SECTOR_VOCAB = [
    "Agriculture, Horticulture, Forestry & Fishing",
    "Financial, Investment and Insurance Services",
    "Media, News, Publishing & Information Services",
    "Education & Training",
    "Civil, Mechanical, Electrical Engineering and Architecture",
    "Advertising and Marketing",
    "Arts, Entertainment, Recreation, Sports",
    "Manufacturing and Product Development",
    "Aerospace",
    "Automotive",
    "Wholesale, Retail & Hiring",
    "Wellbeing, Fitness and Beauty",
    "Warehousing and Storage",
    "Mining, Quarrying and Extraction",
    "Professional, Business & Support Services",
    "Real Estate & Property: Industrial, Commercial and Private",
    "Transportation and Logistics",
    "Tourism, Travel and Hospitality",
    "Chemicals and Materials",
    "Life Sciences",
    "Construction",
    "Defence, Protection and Security",
    "Energy",
    "Environment",
    "Public Services",
    "Utilities",
    "Design Activities",
    "Food and Beverage",
    "Pharmaceutical",
    "Telecommunications",
    "Maritime & Marine",
    "Pets & Domesticated Animals",
    "Repairs, Maintenance & Servicing",
    "Electronics & Electrical",
    "Healthcare, Medical & Social Care",
    "Agnostic",
    "Consumer",
    "Industrials",
    "Computing, Technology, Robotics & AI",
]

# Lookup: 1-based ID → name (used to decode LLM integer output)
MATCHED_SECTOR_BY_ID: dict[int, str] = {i + 1: v for i, v in enumerate(MATCHED_SECTOR_VOCAB)}
_MATCHED_SECTOR_SET: set[str] = set(MATCHED_SECTOR_VOCAB)


def resolve_matched_sectors(raw: list) -> list[str]:
    """Convert LLM output (integer IDs or strings) to canonical vocab names."""
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        name: str | None = None
        if isinstance(item, int):
            name = MATCHED_SECTOR_BY_ID.get(item)
        elif isinstance(item, str):
            stripped = item.strip()
            try:
                name = MATCHED_SECTOR_BY_ID.get(int(stripped))
            except ValueError:
                if stripped in _MATCHED_SECTOR_SET:
                    name = stripped
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result
#
#
# GEOGRAPHY_VOCAB = [
#     "Europe",
#     "North America",
#     "Asia Pacific",
#     "Middle East & Africa",
#     "Latin America",
# ]
#
# # ── System prompt ─────────────────────────────────────────────────────────────
# EXPERTISE_SYSTEM_PROMPT = f"""You are an expert analyst specialising in professional services talent mapping. Given one or more consultant profiles (name, title, company bio, LinkedIn headline, about, experience), classify each into THREE layers.
#
# ---
#
# ### LAYER 1 — Explicit Expertise
#
# Match ONLY categories with **direct, verbatim evidence** in the profile text. Do not infer. Prefer a shorter, accurate list over a longer one with guesses.
#
# **Fixed taxonomy — use ONLY these exact strings:**
# {", ".join(EXPERTISE_CATEGORIES)}
#
# **Per-category evidence requirements — these categories are frequently over-applied. Apply ONLY when the stated condition is met:**
#
# - **R&D**: Only if the person's own work directly involves scientific or technical research, product development, or innovation pipelines — e.g. they lead an R&D function, run a research lab, develop new products or technologies. **Critical exclusions:** (a) a bio listing R&D as one of several practice topics (e.g. "Operations covers manufacturing, supply chain, R&D, engineering") does NOT qualify — that describes client advisory scope, not the person's expertise; (b) digital/analytics/AI advisory, "research" in the context of market research or consulting work, and engineering backgrounds do NOT qualify unless the person is actively running R&D programs.
# - **Legal**: Only if the profile mentions legal advice, litigation, contract work, regulatory legal filings, in-house counsel, or law firm work. Being involved in "compliance" or "regulatory" matters does NOT automatically qualify.
# - **Environment (ESG)**: Only if the profile explicitly references environmental programs, sustainability, climate, ESG reporting, or green initiatives. Do NOT apply because a person works in energy, utilities, or any sector adjacent to environment.
# - **Social (ESG)**: Only if the profile explicitly references social responsibility programs, community impact, workforce equity, or social ESG metrics. Do NOT apply because a person works in HR or non-profit.
# - **Governance (ESG)**: Only if the profile explicitly references corporate governance frameworks, ESG governance structures, or board-level governance oversight. A senior title alone is NOT sufficient.
#
# Return an empty list if nothing matches explicitly. **Aim for 2–4 categories per person.** Only add more if the evidence is unambiguous.
#
# ---
#
# ### LAYER 2 — Inferred Functional Expertise
#
# Now, intelligently INFER functional expertise areas that are **not explicitly stated** but can be reasonably deduced from the person's profile. This requires reading between the lines — understanding what capabilities someone likely possesses based on their role, seniority, industry context, and career trajectory.
#
# There is NO fixed list for this layer. Generate the functional expertise labels yourself. These should be specific, professional capability areas (not broad categories like in Layer 1). Think of these as the specialised skills a recruiter or staffing partner would tag this person with.
#
# **Rules:**
# - These must NOT be explicitly mentioned in the profile. If "restructuring" is literally written in the bio, it belongs in Layer 1 (under the relevant category), not here.
# - Instead, infer based on context. For example:
#   - A "Managing Director at a Big 4 firm advising distressed companies" likely has expertise in **Insolvency & Creditor Advisory** even if the word "insolvency" never appears.
#   - Someone who "led the integration of a $2B acquisition" likely has **Post-Merger Integration** expertise even if those exact words aren't used.
#   - A senior tax partner at an international firm likely has **International Tax** and **Transfer Pricing** capabilities even if the bio focuses on domestic engagements.
#   - A CTO who "built the engineering team from 5 to 200" likely has **Organisational Design** and **Talent Strategy** expertise.
# - Use professional judgement: consider the person's seniority, firm type, role scope, industry, and career trajectory to make reasonable inferences.
# - Be selective — only infer expertise where there is a strong contextual signal. Do not guess or pad the list.
# - Generate concise, professional labels (e.g., "Corporate Restructuring & Turnaround", "Supply Chain & Procurement", "Digital Transformation", "Working Capital & Cash Management").
# - Aim for 3–8 inferred areas per profile. Quality over quantity. If the profile is too sparse to infer confidently, return fewer rather than guessing.
# - **Do NOT use generic seniority labels** that apply to virtually any senior professional: "Executive Leadership", "Business Transformation", "Corporate Strategy", "Strategic Leadership", "Senior Advisory", "General Management", "New Idea Generation", "Thought Leadership". These describe a person's level, not a functional expertise — a recruiter already knows this from the title. Only include labels that distinguish this person's specific capability from other senior professionals.
# - **"Corporate Governance & Board Advisory"** must ONLY be tagged when the profile explicitly mentions board membership, a governance advisory mandate, board-level client work, or a directorship. A senior title (Managing Director, Partner, VP) alone is NOT sufficient evidence — do not use it as a default for senior professionals.
#
# ---
#
# ### LAYER 3 — Topic Overlap
#
# Granular topics that bridge BOTH a Layer 1 category AND a Layer 2 inference. Must have a foot in both worlds — topics connected to only one layer are excluded. Up to 20 per profile, 1–4 words each, capitalised.
#
# **Rules:**
# - Topics must be grounded in the profile text — do not inject generic technology or consulting buzzwords (e.g. "AI", "Data", "Digital Growth", "Consulting Services") unless the profile specifically references them.
# - "AI" is only valid if the profile explicitly mentions artificial intelligence, machine learning, or AI-related work — not as a default for any technology or strategy professional.
#
# ---
#
# ### SECTORS
#
# Sectors of clients served — **not the consulting firm itself** (do not list "Professional Services" or the person's employer as a sector). Include a sector when there is **direct evidence in the profile text** — either:
# 1. The profile explicitly names the sector (e.g. "advised Healthcare clients", "worked in Financial Services"), OR
# 2. The person's own practice area, title, or stated client work clearly references that sector (e.g. "Head of Healthcare Practice" → Healthcare; "Automotive & Mobility practice" → Automotive; "Infrastructure & Transport" → Transportation & Logistics).
#
# Do NOT infer from seniority, firm size, geography, or adjacent topics. If the sector is not supported by the profile text, leave it out.
#
# **Each sector requires its own direct evidence — do not add a broader or adjacent sector just because a more specific one already applies.** Examples of adjacency mistakes to avoid:
# - A profile mentioning only "Food & Beverage" does NOT automatically qualify for Consumer & Retail (that requires explicit mention of retail stores, apparel, electronics, or other non-food consumer categories).
# - A profile mentioning only "Pharmaceuticals" does NOT automatically qualify for Healthcare (that requires explicit mention of hospitals, clinics, providers, or payers).
# - A profile mentioning only "Automotive" does NOT automatically qualify for Industrials & Manufacturing (that requires explicit manufacturing or heavy-industry evidence beyond automotive).
#
# **Use ONLY these exact strings:**
# {", ".join(SECTOR_VOCAB)}
#
# No new labels. No sub-variants. Common mistakes to avoid: do not use "Real Estate & Assets" (that is a Layer 1 category — use "Real Estate" instead), "Telecommunications", "Aerospace", "Oil & Gas", "Banking", "Manufacturing", "Retail", "SaaS", "Industrial", "Cross-Sector", "Professional Services", "Food and Beverage" (use "Food & Beverage" instead).
#
# ---
#
# ### MATCHED SECTORS
#
# Re-express the sectors you selected above using this more granular vocabulary. **This is a strict re-labelling of SECTORS, not an independent analysis.** The two outputs MUST be consistent — every matched sector you include must correspond to a sector you already included in SECTORS.
#
# **Use this exact mapping — for each SECTOR you selected, include the matched sector ID(s) listed next to it. Some mappings are "default" (always include) and others are "conditional" (only include if the profile has specific evidence).**
#
# One-to-one mappings (always include):
# - **Healthcare** → 35 (Healthcare, Medical & Social Care)
# - **Financial Services** → 2 (Financial, Investment and Insurance Services)
# - **Private Equity** → 2 (Financial, Investment and Insurance Services)
# - **Insurance** → 2 (Financial, Investment and Insurance Services)
# - **Food & Beverage** → 28 (Food and Beverage)
# - **Automotive** → 10 (Automotive)
# - **Technology & Software** → 39 (Computing, Technology, Robotics & AI)
# - **Real Estate** → 16 (Real Estate & Property: Industrial, Commercial and Private)
# - **Transportation & Logistics** → 17 (Transportation and Logistics)
# - **Education** → 4 (Education & Training)
# - **Government & Public Sector** → 25 (Public Services)
# - **Non-profit & Social Sector** → 25 (Public Services)
#
# Conditional mappings (default + evidence-required extras):
# - **Pharmaceuticals & Life Sciences**:
#   - 29 (Pharmaceutical) — default (drug/therapeutics work)
#   - 20 (Life Sciences) — ONLY if profile mentions biotech, diagnostics, medical devices, genomics, or research
# - **Energy & Utilities**:
#   - 23 (Energy) — default (oil, gas, power, renewables)
#   - 26 (Utilities) — ONLY if profile mentions regulated utilities, water, electric utilities, grid
# - **Consumer & Retail**:
#   - 37 (Consumer) — default (consumer goods, FMCG)
#   - 11 (Wholesale, Retail & Hiring) — ONLY if profile mentions retail stores, wholesale, distribution, or hiring/staffing services
# - **Industrials & Manufacturing**:
#   - 8 (Manufacturing and Product Development) — default (making products)
#   - 38 (Industrials) — ONLY if profile mentions heavy industry, industrial equipment, or industrial processing
# - **Media & Entertainment**:
#   - 3 (Media, News, Publishing & Information Services) — default (media, news, publishing)
#   - 7 (Arts, Entertainment, Recreation, Sports) — ONLY if profile mentions sports, entertainment production, film, gaming, or performing arts
# - **Agriculture & Food**:
#   - 1 (Agriculture, Horticulture, Forestry & Fishing) — default (farming, primary production)
#   - 28 (Food and Beverage) — ONLY if profile mentions processed food, beverages, or CPG food products
#
# **Rules (strictly enforced):**
# - If SECTORS is empty, `matched_sectors` MUST be `[]`.
# - If you include a matched sector ID that does not correspond to any sector you selected above, that is an error — remove it.
# - Do NOT add matched sectors based on profile evidence alone if the corresponding SECTOR was not selected — either add the SECTOR too, or drop the matched sector.
# - Return integer IDs only (not text strings). Full numbered vocabulary list: {"; ".join(f"{i+1}={v}" for i, v in enumerate(MATCHED_SECTOR_VOCAB))}.
#
# ---
#
# ### GEOGRAPHIES
#
# Where expertise was APPLIED (clients served, projects delivered) — not office location.
#
# **Use ONLY:** {", ".join(GEOGRAPHY_VOCAB)}
#
# ---
#
# ### PRIMARY EXPERTISE
#
# Single most defining category from the 13-item taxonomy. Must be one of these exact strings: {", ".join(EXPERTISE_CATEGORIES)}
#
# No variants, composites, or values outside this list. A blank, dash, or null value is never acceptable — always assign a category.
#
# **Tiebreak rule:** when multiple categories match equally, prefer the one most directly stated in the person's job title or practice group name. Use these examples as anchors:
#
# - "Managing Director, Tax" → Finance and Accounting
# - "Managing Director, Tax Advisory Group" → Finance and Accounting
# - "Managing Director, Forensic Accounting" → Finance and Accounting
# - "Managing Director, Transaction Advisory / Due Diligence" → Finance and Accounting
# - "Managing Director, Disputes and Investigations" → Finance and Accounting
# - "Managing Director, Transaction Advisory Group" → M&A and Corporate Development
# - "Managing Director, Restructuring" → Operational Improvements (only when the role is explicitly operational, not financial)
#
# Finance and Accounting takes priority over Operational Improvements for anyone in a Tax, Forensic, Due Diligence, Disputes, or Financial Advisory practice — even if the firm itself is a restructuring firm.
#
# **Justification:** 1–2 sentences citing specific evidence from the profile.
#
# ---
#
# ### OUTPUT FORMAT
#
# Return a JSON array, one object per person. Return ONLY valid JSON — no commentary.
#
# {{
#   "name": "<exact name from input>",
#   "primary_expertise": "<one of the 13 fixed categories>",
#   "justification": "...",
#   "explicit_expertise_13": ["Category1", "Category2"],
#   "sectors": ["Sector1", "Sector2"],
#   "matched_sectors": [1, 5],
#   "geographies": ["Region1"],
#   "inferred_expertise_functional": ["Capability1", "Capability2"],
#   "inference_reasoning": "Brief explanation of the key signals that drove your Layer 2 inferences.",
#   "topic_overlap": ["Topic1", "Topic2"]
# }}
#
# Never skip, merge, or omit anyone. One result per input person."""


# # ── System prompt ─────────────────────────────────────────────────────────────
# EXPERTISE_SYSTEM_PROMPT = """
# # TAXONOMIES (exact strings only)
# <expertise>Revenue Growth, Operational Improvements, Finance and Accounting, Marketing, People and Talent, Technology, M&A and Corporate Development, Real Estate & Assets, R&D, Environment (ESG), Governance (ESG), Social (ESG), Legal</expertise>
# <sectors>Healthcare, Pharmaceuticals & Life Sciences, Financial Services, Private Equity, Energy & Utilities, Consumer & Retail, Food & Beverage, Automotive, Industrials & Manufacturing, Technology & Software, Real Estate, Transportation & Logistics, Education, Government & Public Sector, Non-profit & Social Sector, Insurance, Media & Entertainment, Agriculture & Food</sectors>
# <matched_sectors>Agriculture, Horticulture, Forestry & Fishing=1; Financial, Investment and Insurance Services=2; Media, News, Publishing & Information Services=3; Education & Training=4; Civil, Mechanical, Electrical Engineering and Architecture=5; Advertising and Marketing=6; Arts, Entertainment, Recreation, Sports=7; Manufacturing and Product Development=8; Aerospace=9; Automotive=10; Wholesale, Retail & Hiring=11; Wellbeing, Fitness and Beauty=12; Warehousing and Storage=13; Mining, Quarrying and Extraction=14; Professional, Business & Support Services=15; Real Estate & Property: Industrial, Commercial and Private=16; Transportation and Logistics=17; Tourism, Travel and Hospitality=18; Chemicals and Materials=19; Life Sciences=20; Construction=21; Defence, Protection and Security=22; Energy=23; Environment=24; Public Services=25; Utilities=26; Design Activities=27; Food and Beverage=28; Pharmaceutical=29; Telecommunications=30; Maritime & Marine=31; Pets & Domesticated Animals=32; Repairs, Maintenance & Servicing=33; Electronics & Electrical=34; Healthcare, Medical & Social Care=35; Agnostic=36; Consumer=37; Industrials=38; Computing, Technology, Robotics & AI=39</matched_sectors>
# <geos>Europe, North America, Asia Pacific, Middle East & Africa, Latin America</geos>
#
# # TASK
# Classify each consultant profile into 3 layers + metadata. Return JSON array only.
#
# ## LAYER 1: Explicit Expertise (2-4 max)
# - Match ONLY <expertise> strings with verbatim evidence in profile.
# - R&D: must lead scientific/technical R&D (not advise). Legal: must mention litigation/contracts/law firm. ESG tags: require explicit environmental/social/governance terms.
# - Return [] if no direct match.
#
# ## LAYER 2: Inferred Functional Expertise (0-5 max)
# - Infer specific capabilities NOT stated but deduced from bio/role/seniority/industry.
# - Use precise labels (e.g., "Distressed Asset Turnaround"), not generic titles.
# - Require strong contextual signal; return [] if weak.
#
# ## LAYER 3: Topic Overlap (≤20)
# - 1-4 word capitalized phrases bridging Layer 1 + Lay like er 2.
# - Grounded in profile text; no buzzwords.
#
# ## INPUT FIELDS
# - `website_industries` and `website_capabilities`: extracted directly from the firm's own profile page. Treat these as primary direct evidence — equivalent in weight to an explicit bio statement. Use them to assign SECTORS and MATCHED_SECTORS without requiring additional bio confirmation.
# - `website_education`: educational background from the firm's profile page. Use for context only; do not assign expertise categories based solely on degree subject.
#
# ## SECTORS & MATCHED_SECTORS
# - Select sectors from <sectors> ONLY with direct evidence (explicit name, practice reference, OR matching website_industries entry).
# - Each sector needs its own direct evidence — do NOT add a broader sector just because a more specific one applies: Food & Beverage alone does NOT qualify for Consumer & Retail (requires explicit mention of retail stores, apparel, or non-food consumer categories); Pharmaceuticals & Life Sciences alone does NOT qualify for Healthcare (requires explicit mention of hospitals, providers, or payers); Automotive alone does NOT qualify for Industrials & Manufacturing.
# - Coupling rule: every matched_sectors ID must have a corresponding sector string in `sectors`. If evidence justifies a matched ID, ADD the parent sector to `sectors` — do NOT drop the matched ID. Never leave matched_sectors populated while sectors is empty; resolve by adding the missing parent sector, not by removing the matched sector.
# - Map each selected sector to SINGLE most precise ID from <matched_sectors>:
#   • Use conditional ID if trigger words appear (e.g., "biotech"→20), ELSE default ID.
#   • Output integers only. Return [] if no sectors.
# - Default→Conditional mapping: Healthcare→35; Financial Services/Private Equity/Insurance→2; Food & Beverage→28; Automotive→10; Technology & Software→39; Real Estate→16; Transportation & Logistics→17; Education→4; Government/Non-profit→25; Pharmaceuticals & Life Sciences→29 (→20 if biotech/diagnostics/device/genomics); Energy & Utilities→23 (→26 if utility/water/grid); Consumer & Retail→37 (→11 if retail/wholesale/staffing); Industrials & Manufacturing→8 (→38 if heavy industry/equipment); Media & Entertainment→3 (→7 if sports/film/gaming); Agriculture & Food→1 (→28 if processed food/CPG).
#
# ## GEOGRAPHIES
# - Select from <geos> ONLY where expertise was applied (client/projects), not office location.
#
# ## PRIMARY EXPERTISE
# - Single most defining category from <expertise>. Tiebreak: prefer category in job title/practice group.
# - Justification: 1 sentence citing specific evidence.
#
# ## OUTPUT SCHEMA (strict JSON, no commentary)
#   {{
#     "name": "string",
#     "primary_expertise": "string",
#     "justification": "string",
#     "explicit_expertise_13": ["string"],
#     "sectors": ["string"],
#     "matched_sectors": [int],
#     "geographies": ["string"],
#     "inferred_expertise_functional": ["string"],
#     "inference_reasoning": "string",
#     "topic_overlap": ["string"]
#   }}
# - All arrays may be empty []. matched_sectors MUST be integers. One object per input person."""

EXPERTISE_SYSTEM_PROMPT = """
# TAXONOMIES

<expertise>Revenue Growth, Operational Improvements, Finance and Accounting, Marketing, People and Talent, Technology, M&A and Corporate Development, Real Estate & Assets, R&D, Environment (ESG), Governance (ESG), Social (ESG), Legal</expertise>

<sectors>Healthcare, Pharmaceuticals & Life Sciences, Financial Services, Private Equity, Energy & Utilities, Consumer & Retail, Food & Beverage, Automotive, Industrials & Manufacturing, Technology & Software, Real Estate, Transportation & Logistics, Education, Government & Public Sector, Non-profit & Social Sector, Insurance, Media & Entertainment, Agriculture & Food, Agnostic</sectors>

<matched_sectors>Agriculture, Horticulture, Forestry & Fishing, Financial, Investment and Insurance Services, Media, News, Publishing & Information Services, Education & Training, Civil, Mechanical, Electrical Engineering and Architecture, Advertising and Marketing, Arts, Entertainment, Recreation, Sports, Manufacturing and Product Development, Aerospace, Automotive, Wholesale, Retail & Hiring, Wellbeing, Fitness and Beauty, Warehousing and Storage, Mining, Quarrying and Extraction, Professional, Business & Support Services, Real Estate & Property: Industrial, Commercial and Private, Transportation and Logistics, Tourism, Travel and Hospitality, Chemicals and Materials, Life Sciences, Construction, Defence, Protection and Security, Energy, Environment, Public Services, Utilities, Design Activities, Food and Beverage, Pharmaceutical, Telecommunications, Maritime & Marine, Pets & Domesticated Animals, Repairs, Maintenance & Servicing, Electronics & Electrical, Healthcare, Medical & Social Care, Agnostic, Consumer, Industrials, Computing, Technology, Robotics & AI</matched_sectors>

<geos>Europe, North America, Asia Pacific, Middle East & Africa, Latin America</geos>

---

# TASK
Classify each consultant profile into 3 layers + metadata. Return **JSON array only**. No explanatory text before or after.

---

## LAYER 1: Explicit Expertise (2-4 max)
- Match ONLY from `<expertise>` using **verbatim or near-verbatim** evidence (e.g., "revenue growth strategy" matches "Revenue Growth").
- **R&D**: requires leading scientific or technical R&D (not advising R&D organizations).
- **Legal**: requires litigation, contracts, IP law, or law firm partnership.
- **ESG tags**: require explicit environmental, social, or governance keywords.
- Return [] if no direct match.
- **If more than 4 matches**, prioritize by: (1) appears in job title → (2) appears in practice group → (3) most frequently mentioned. Truncate to 4.

---

## LAYER 2: Inferred Functional Expertise (0-5 max)
- Infer capabilities **NOT explicitly stated** but strongly implied by bio/role/seniority/industry/results.
- Use precise labels (e.g., "Distressed Asset Turnaround", not "Turnaround").
- **Confidence threshold**: include only if confidence >70% based on:
  - Seniority (Director/Partner/VP+ → higher confidence)
  - Quantifiable results (e.g., "increased EBITDA by 30%")
  - Industry-standard role expectations (e.g., "CFO" → "Financial Planning & Analysis")
- Return [] if weak or ambiguous signal.
- **If more than 5 matches**, keep highest-confidence only.

---

## LAYER 3: Topic Overlap (≤20)
- This is a **granular set of expertise topics** (1–4 word phrases) that are **supported by both Layer 1 (explicit expertise) and Layer 2 (inferred functional expertise)**.
- Topics should be **specific, actionable, and grounded in the profile text** – not generic buzzwords.
- Examples from real profiles:
  - For a Finance and Accounting + Restructuring expert:  
    `["Restructuring", "Strategic Planning", "Cash Management", "Financial Analysis", "Capital Raising", "Liquidity Management"]`
  - For a Revenue Growth + Pricing Strategy expert:  
    `["Pricing Optimization", "Value-Based Pricing", "Market Entry Strategy", "Commercial Due Diligence"]`
- **Do NOT** simply concatenate Layer 1 and Layer 2 strings (e.g., avoid `"Finance and Accounting Restructuring"` unless that exact phrase is used in the profile).
- Instead, extract specific **verbs, nouns, and technical domains** that appear in the profile and logically combine the two layers.
- If the profile text contains explicit technical terms (e.g., "AI", "data security", "ERP implementation"), include them as topics.
- **If more than 20 topics**, keep the most relevant to primary_expertise and the strongest evidence.
- Return [] if no clear topics emerge.

---
## INPUT FIELDS
- `website_industries`: extracted directly from the firm's own profile page. Use as primary evidence for **SECTORS** and **MATCHED_SECTORS**.
- `website_capabilities`: granular topic expertise areas declared by the firm for this person (e.g. "Pricing & Revenue Optimization", "Post-merger Integration", "Route-to-Market Design"). Use these primarily as **Layer 3 topic_overlap** entries — they represent specific practice-level expertises, not broad 13-category buckets. Only map to **LAYER 1 (explicit_expertise_13)** when the capability is an unambiguous, direct match to one of the 13 categories AND confirmed by bio or title (e.g. "People & Organization" → "People and Talent" only if the person's role is clearly HR/OD-focused). Do NOT use website_capabilities as a basis for Layer 2 — declared capabilities belong in Layer 1 (if broadly matching) or Layer 3 (specific topics), not as inferences.
- `website_education`: educational background from the firm's profile page. Use for context only; do not assign expertise categories based solely on degree subject.

## SECTORS & MATCHED_SECTORS

### Core Principle: Evidence-Based Only
- **Both fields require direct evidence from the profile** (explicit sector name, client name, project description, industry terminology).
- The two fields describe the **same underlying sector evidence** – one in free text, one as a controlled vocabulary string.
- **Never add a sector or matched_sectors string without evidence.**

### `sectors` (Free Text)
- Infer from profile data. Use **concise, descriptive strings** (2-5 words typical).
- Examples: `"biotech commercial strategy"`, `"hospital revenue cycle"`, `"retail supply chain"`, `"pharmaceutical R&D portfolio"`
- Not tied to any fixed list. Write what the evidence actually describes.
- May have multiple entries if profile spans multiple sectors.
- Return [] if no sector evidence.

### `matched_sectors` (Controlled Vocabulary)
- Also infer from profile data, but **use exact strings from the `<matched_sectors>` list above**.
- Do NOT modify the strings. Use them exactly as written.
- If evidence matches a string in `<matched_sectors>`, include that exact string.
- May have multiple strings if profile spans multiple sectors.
- Return [] if no sector evidence or if evidence does not match any controlled string.
- **Validation**: For each `matched_sectors` entry, you should be able to point to the same evidence that supports a `sectors` entry. They are two representations of the same fact.

### Workflow for Sector Classification

1. Scan profile for **any sector evidence** (industry names, client types, project domains, role contexts).
2. For the evidence, write a **concise free-text sector string** → add to `sectors` array.
3. For the **same evidence**, find the **exact matching string(s)** in `<matched_sectors>` → add to `matched_sectors` array.
4. If evidence fits multiple `<matched_sectors>` strings, include all that apply.
5. If evidence matches a `sectors` entry but has no match in `<matched_sectors>`, still include the `sectors` entry but no corresponding `matched_sectors` entry.
6. If evidence matches a `<matched_sectors>` string but you already have a corresponding free-text `sectors` entry, both are present — that's correct.

### Sector Examples

**Example 1: Pharma commercial**
- Profile: "Led pricing strategy for oncology portfolio at Novartis"
- Evidence: pharmaceutical company
- `sectors`: `["pharmaceutical commercial strategy"]`
- `matched_sectors`: `["Pharmaceutical"]`
- Valid ✅

**Example 2: Biotech operations**
- Profile: "CFO at a genomics startup, managed Series B raise"
- Evidence: genomics startup
- `sectors`: `["biotech finance"]`
- `matched_sectors`: `["Life Sciences"]`
- Valid ✅

**Example 3: Hospital + Pharma cross-sector**
- Profile: "Advised both a hospital system and a pharmaceutical company"
- Evidence: hospital system + pharmaceutical company
- `sectors`: `["hospital operations", "pharmaceutical pricing"]`
- `matched_sectors`: `["Healthcare, Medical & Social Care", "Pharmaceutical"]`
- Valid ✅

**Example 4: Consumer retail**
- Profile: "Optimized supply chain for a national grocery chain"
- Evidence: grocery chain
- `sectors`: `["grocery retail supply chain"]`
- `matched_sectors`: `["Wholesale, Retail & Hiring"]`
- Valid ✅

**Example 5: Weak evidence (reject both)**
- Profile: "Helped company grow market share"
- No sector evidence
- `sectors`: `[]`
- `matched_sectors`: `[]`
- Valid ✅

---

## GEOGRAPHIES
- Select from `<geos>` ONLY where expertise was **applied** (client/project location), not office location.
- Examples:
  - "Led European supply chain transformation" → `["Europe"]`
  - "Based in NY, client in London" → `["Europe"]` (not North America)
  - "Global role with projects in US, Germany, Japan" → `["Europe", "North America", "Asia Pacific"]`
- Return [] if no geographic evidence.

---

## PRIMARY EXPERTISE
- Single most defining category from `<expertise>`.
- Tiebreak priority:
  1. Appears in job title (partial match allowed: "Head of Revenue" → Revenue Growth)
  2. Appears in practice group or team name
  3. Most frequent mention in profile
- **Justification**: Exactly 1 sentence citing specific evidence (e.g., "Job title 'Partner, Revenue Practice' and 4 projects mention top-line growth").

---

## EVIDENCE MAP

For every item you assign, record which specific input field(s) provided the supporting evidence.
Populate `evidence_map` in the output object alongside the classification arrays.

Keys:
- `categories` — one entry per item in `explicit_expertise_13`
- `sectors` — one entry per item in `sectors`
- `matched_sectors` — one entry per item in `matched_sectors`
- `inferred` — one entry per item in `inferred_expertise_functional`
- `topics` — one entry per item in `topic_overlap`

Each value is a list of `{"source": "<field>", "text": "<phrase>"}` objects.
Valid source values: `bio`, `title`, `department`, `linkedin_headline`, `linkedin_summary`, `linkedin_experience`, `linkedin_skills`, `website_industries`, `website_capabilities`.
Keep `text` to ≤15 words — extract the specific phrase that triggered the assignment, not the full field.
Omit a key entirely if the array it covers is empty.

---

## OUTPUT SCHEMA (strict JSON, no commentary)

{
  "name": "string",
  "primary_expertise": "string",
  "justification": "string",
  "explicit_expertise_13": ["string"],
  "sectors": ["string"],
  "matched_sectors": ["string"],
  "geographies": ["string"],
  "inferred_expertise_functional": ["string"],
  "inference_reasoning": "string",
  "topic_overlap": ["string"],
  "evidence_map": {
    "categories": {"<category>": [{"source": "string", "text": "string"}]},
    "sectors": {"<sector_string>": [{"source": "string", "text": "string"}]},
    "matched_sectors": {"<matched_sector_string>": [{"source": "string", "text": "string"}]},
    "inferred": {"<inferred_item>": [{"source": "string", "text": "string"}]},
    "topics": {"<topic>": [{"source": "string", "text": "string"}]}
  }
}

- Arrays may be empty [].
- `matched_sectors` must contain **exact strings** from `<matched_sectors>` taxonomy.
- Sort `explicit_expertise_13` alphabetically.
- Sort `matched_sectors` alphabetically.
- Sort `sectors` alphabetically.
- Sort `inferred_expertise_functional` by relevance (most relevant first).
- Sort `topic_overlap` alphabetically.
- One object per input person.

---

## COMPLETE EXAMPLE

**Input Profile:**

**Output:**
```json
{
  "name": "John Smith",
  "primary_expertise": "Revenue Growth",
  "justification": "Job title 'Partner in Revenue Practice' and multiple projects mention commercial transformation and pricing.",
  "explicit_expertise_13": ["Revenue Growth"],
  "sectors": ["hospital revenue cycle", "pharmaceutical commercial strategy"],
  "matched_sectors": ["Healthcare, Medical & Social Care", "Pharmaceutical"],
  "geographies": ["Europe"],
  "inferred_expertise_functional": ["Commercial Excellence", "Pricing Strategy", "Revenue Cycle Management"],
  "inference_reasoning": "'Pricing optimization' suggests pricing strategy; 'revenue cycle management' is explicit; CFO background and biotech imply commercial excellence.",
  "topic_overlap": ["CFO Experience", "Commercial Transformation", "Cross-Border Advisory", "EBITDA Improvement", "Oncology Portfolio", "Pricing Optimization", "Revenue Cycle Enhancement", "Value-Based Pricing"],
  "evidence_map": {
    "categories": {
      "Revenue Growth": [
        {"source": "title", "text": "Partner in Revenue Practice"},
        {"source": "bio", "text": "commercial transformation and pricing"}
      ]
    },
    "sectors": {
      "hospital revenue cycle": [{"source": "bio", "text": "hospital revenue cycle management"}],
      "pharmaceutical commercial strategy": [{"source": "bio", "text": "oncology portfolio at Novartis"}]
    },
    "matched_sectors": {
      "Healthcare, Medical & Social Care": [{"source": "bio", "text": "hospital revenue cycle management"}],
      "Pharmaceutical": [{"source": "bio", "text": "oncology portfolio at Novartis"}]
    },
    "inferred": {
      "Commercial Excellence": [{"source": "title", "text": "Partner in Revenue Practice"}, {"source": "bio", "text": "cross-border deals"}],
      "Pricing Strategy": [{"source": "bio", "text": "pricing optimization"}],
      "Revenue Cycle Management": [{"source": "bio", "text": "revenue cycle management"}]
    },
    "topics": {
      "CFO Experience": [{"source": "bio", "text": "CFO background"}],
      "Commercial Transformation": [{"source": "bio", "text": "commercial transformation"}],
      "Pricing Optimization": [{"source": "bio", "text": "pricing optimization"}],
      "Revenue Cycle Enhancement": [{"source": "bio", "text": "revenue cycle management"}]
    }
  }
}
"""
# ── LLM Providers ───────────────────────────────────────────────────────────
class BaseLLMProvider(ABC):
    @abstractmethod
    def analyze_batch(self, people_text: str) -> str:
        pass


class ClaudeProvider(BaseLLMProvider):
    def __init__(self):
        import anthropic
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.LLM_MODEL_CLAUDE
        self.last_usage: dict | None = None

    def analyze_batch(self, people_text: str) -> str:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=16384,
            temperature=0,
            system=EXPERTISE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": people_text}],
        )
        self.last_usage = {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "model": self.model,
        }
        return resp.content[0].text


class OpenAIProvider(BaseLLMProvider):
    def __init__(self):
        from openai import OpenAI
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.LLM_MODEL_OPENAI
        self.last_usage: dict | None = None

    def analyze_batch(self, people_text: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": EXPERTISE_SYSTEM_PROMPT},
                {"role": "user", "content": people_text},
            ],
            max_tokens=16384,
            temperature=0,
        )
        if resp.usage:
            self.last_usage = {
                "input_tokens": resp.usage.prompt_tokens,
                "output_tokens": resp.usage.completion_tokens,
                "model": self.model,
            }
        return resp.choices[0].message.content


class GeminiProvider(BaseLLMProvider):
    def __init__(self):
        from google import genai
        self.client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        self.model = settings.LLM_MODEL_GEMINI
        self.last_usage: dict | None = None

    def analyze_batch(self, people_text: str) -> str:
        from google.genai import types
        resp = self.client.models.generate_content(
            model=self.model,
            contents=f"{EXPERTISE_SYSTEM_PROMPT}\n\n{people_text}",
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=65536,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        if resp.usage_metadata:
            self.last_usage = {
                "input_tokens": resp.usage_metadata.prompt_token_count,
                "output_tokens": resp.usage_metadata.candidates_token_count,
                "model": self.model,
            }
        return resp.text


class DeepSeekProvider(BaseLLMProvider):
    """DeepSeek uses an OpenAI-compatible API (max_tokens capped at 8192)."""
    def __init__(self):
        from openai import OpenAI
        self.client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
        )
        self.model = settings.LLM_MODEL_DEEPSEEK
        self.last_usage: dict | None = None

    def analyze_batch(self, people_text: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": EXPERTISE_SYSTEM_PROMPT},
                {"role": "user", "content": people_text},
            ],
            max_tokens=8192,
            temperature=0,
        )
        if resp.usage:
            self.last_usage = {
                "input_tokens": resp.usage.prompt_tokens,
                "output_tokens": resp.usage.completion_tokens,
                "model": self.model,
            }
        return resp.choices[0].message.content


class ManusProvider(BaseLLMProvider):
    """Manus uses an OpenAI-compatible API."""
    def __init__(self):
        from openai import OpenAI
        self.client = OpenAI(
            api_key=settings.MANUS_API_KEY,
            base_url="https://api.manus.im/v1",
        )
        self.model = settings.LLM_MODEL_MANUS
        self.last_usage: dict | None = None

    def analyze_batch(self, people_text: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": EXPERTISE_SYSTEM_PROMPT},
                {"role": "user", "content": people_text},
            ],
            max_tokens=16384,
            temperature=0,
        )
        if resp.usage:
            self.last_usage = {
                "input_tokens": resp.usage.prompt_tokens,
                "output_tokens": resp.usage.completion_tokens,
                "model": self.model,
            }
        return resp.choices[0].message.content

class QwenProvider(BaseLLMProvider):
    def __init__(self):
        from openai import OpenAI
        self.client = OpenAI(
            api_key=settings.QWEN_API_KEY,
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        )
        self.model = settings.LLM_MODEL_QWEN
        self.last_usage: dict | None = None

    def analyze_batch(self, people_text: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": EXPERTISE_SYSTEM_PROMPT},
                {"role": "user", "content": people_text},
            ],
            max_tokens=16384,
            temperature=0,
            extra_body={"enable_thinking": True},
        )
        if resp.usage:
            self.last_usage = {
                "input_tokens": resp.usage.prompt_tokens,
                "output_tokens": resp.usage.completion_tokens,
                "model": self.model,
            }
        return resp.choices[0].message.content

def get_provider() -> BaseLLMProvider:
    if settings.LLM_PROVIDER == "openai":
        return OpenAIProvider()
    if settings.LLM_PROVIDER == "gemini":
        return GeminiProvider()
    if settings.LLM_PROVIDER == "deepseek":
        return DeepSeekProvider()
    if settings.LLM_PROVIDER == "manus":
        return ManusProvider()
    if settings.LLM_PROVIDER == "qwen":
        return QwenProvider()
    return ClaudeProvider()


# ── Formatting & parsing ────────────────────────────────────────────────────
def format_people_for_analysis(people: list[dict], company_name: str = "") -> str:
    lines = []
    if company_name:
        lines.append(f"Company: {company_name}")
        lines.append("")
    for i, p in enumerate(people):
        lines.append(f"Person {i+1}:")
        lines.append(f"  Name: {p.get('name', 'Unknown')}")
        lines.append(f"  Title: {p.get('title', 'N/A')}")
        lines.append(f"  Department: {p.get('department', 'N/A')}")
        lines.append(f"  Location: {p.get('location', 'N/A')}")
        bio = p.get("bio", "")
        if bio:
            lines.append(f"  Bio: {bio[:500]}")
        if p.get("linkedin_headline"):
            lines.append(f"  LinkedIn Headline: {p['linkedin_headline']}")
        if p.get("linkedin_summary"):
            lines.append(f"  LinkedIn Summary: {p['linkedin_summary'][:500]}")
        if p.get("linkedin_experience_summary"):
            lines.append(f"  LinkedIn Experience: {p['linkedin_experience_summary'][:500]}")
        if p.get("linkedin_skills"):
            skills = p["linkedin_skills"]
            if isinstance(skills, list):
                skills = ", ".join(str(s) for s in skills[:20])
            lines.append(f"  Skills: {skills}")
        if p.get("website_industries"):
            industries = p["website_industries"]
            if isinstance(industries, list):
                industries = "; ".join(str(s) for s in industries)
            lines.append(f"  Website Industries: {industries}")
        if p.get("website_capabilities"):
            caps = p["website_capabilities"]
            if isinstance(caps, list):
                caps = "; ".join(str(s) for s in caps)
            lines.append(f"  Website Capabilities: {caps}")
        if p.get("website_education"):
            edu = p["website_education"]
            if isinstance(edu, list):
                parts = []
                for e in edu:
                    if isinstance(e, dict):
                        raw = e.get("raw") or ", ".join(filter(None, [e.get("degree"), e.get("institution"), e.get("year")]))
                        if raw:
                            parts.append(raw)
                    else:
                        parts.append(str(e))
                edu = " | ".join(parts)
            lines.append(f"  Website Education: {edu}")
        lines.append("")
    return "\n".join(lines)


def _normalize_name(name: str) -> str:
    """Lowercase and collapse whitespace for fuzzy matching."""
    return " ".join(name.lower().strip().split())


def _parse_llm_response(raw_response: str) -> list[dict]:
    """Parse LLM JSON response, handling markdown fences and minor JSON errors."""
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        results = json.loads(cleaned)
        return results if isinstance(results, list) else []
    except json.JSONDecodeError:
        pass

    # Attempt recovery: find the JSON array bounds and re-parse
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            results = json.loads(cleaned[start:end + 1])
            return results if isinstance(results, list) else []
        except json.JSONDecodeError:
            pass

    log.error("Failed to parse LLM response as JSON. Raw (first 500 chars): %s", cleaned[:500])
    return []


# ── Batch analysis ──────────────────────────────────────────────────────────
def analyze_batch_by_name(people_data: list[dict], batch_size: int = 50) -> dict[str, dict]:
    """Analyze people and return results keyed by normalized name."""
    provider = get_provider()
    results_by_name: dict[str, dict] = {}

    for i in range(0, len(people_data), batch_size):
        batch = people_data[i:i + batch_size]
        text = format_people_for_analysis(batch)
        batch_num = i // batch_size + 1
        total_batches = (len(people_data) + batch_size - 1) // batch_size

        try:
            raw_response = provider.analyze_batch(text)
            results = _parse_llm_response(raw_response)

            matched = 0
            for result in results:
                result_name = result.get("name", "")
                if not result_name:
                    continue
                norm = _normalize_name(result_name)
                results_by_name[norm] = result
                matched += 1

            # Fallback: positional matching if LLM didn't return names
            if matched == 0 and len(results) == len(batch):
                log.warning(f"  Batch {batch_num}: LLM returned no names, falling back to positional matching")
                for person, result in zip(batch, results):
                    norm = _normalize_name(person.get("name", ""))
                    if norm:
                        results_by_name[norm] = result

            log.info(f"  Batch {batch_num}/{total_batches}: matched {matched}/{len(batch)} by name")

        except (json.JSONDecodeError, Exception) as exc:
            log.error(f"  Batch {batch_num}/{total_batches} failed: {exc}")

    return results_by_name


def analyze_people(people_data: list[dict], batch_size: int = 10) -> list[dict]:
    """Legacy wrapper — returns positional list for backward compat."""
    results_by_name = analyze_batch_by_name(people_data, batch_size=batch_size)
    out = []
    for p in people_data:
        norm = _normalize_name(p.get("name", ""))
        out.append(results_by_name.get(norm, {}))
    return out
