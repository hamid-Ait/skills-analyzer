import json
import logging
from abc import ABC, abstractmethod

from app.config import settings


log = logging.getLogger(__name__)


# ── Taxonomy lists (loaded once) ────────────────────────────────────────────
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


# ── System prompt ────────────────────────────────────────────────────────────
EXPERTISE_SYSTEM_PROMPT = f"""You are an expert analyst specialising in professional services talent mapping. You will be given one or more consultant profiles — including their name, title, bio (from their company website), LinkedIn headline, LinkedIn about section, and LinkedIn experience.

Your task is to classify their expertise into THREE distinct layers. Each layer has different rules for how matches should be determined.

---

### LAYER 1 — Explicit Expertise (Column I)

Match the profile against the following fixed taxonomy of 13 expertise categories. A category should ONLY be matched if there is **direct, explicit evidence** in the profile text — meaning the relevant skill, domain, or activity is clearly stated in words.

Do NOT infer or read between the lines. The words must be there.

**Fixed Taxonomy (13 categories):**
{json.dumps(EXPERTISE_CATEGORIES)}

**Rules:**
- Only match when keywords or phrases directly related to the category appear verbatim or near-verbatim in the profile text.
- The evidence must come from the bio, LinkedIn headline, LinkedIn about section, or LinkedIn experience.
- You must be able to point to the specific words in the profile that justify each match.
- Return only the category names that have explicit textual support.
- If nothing matches explicitly, return an empty list.

**Examples of CORRECT explicit matching:**
- Bio says "led a cost reduction programme" → match **Operational Improvements** (cost reduction is explicitly stated)
- Bio says "specialises in M&A advisory" → match **M&A and Corporate Development**
- Bio says "tax compliance and financial reporting" → match **Finance and Accounting**

**Examples of INCORRECT matching (do not do this):**
- Bio says "improved profitability" → do NOT match Operational Improvements (doesn't say *how* — could be revenue, could be cost, could be pricing)
- Bio says "advises private equity firms" → do NOT match M&A and Corporate Development (advising PE firms doesn't mean the person does M&A work themselves)
- Bio says "senior partner at a law firm" → do NOT match Legal unless legal work is explicitly described

---

### LAYER 2 — Inferred Functional Expertise (Column L)

Now, intelligently INFER functional expertise areas that are **not explicitly stated** but can be reasonably deduced from the person's profile. This requires reading between the lines — understanding what capabilities someone likely possesses based on their role, seniority, industry context, and career trajectory.

There is NO fixed list for this layer. Generate the functional expertise labels yourself. These should be specific, professional capability areas (not broad categories like in Layer 1). Think of these as the specialised skills a recruiter or staffing partner would tag this person with.

**Rules:**
- These must NOT be explicitly mentioned in the profile. If "restructuring" is literally written in the bio, it belongs in Layer 1 (under the relevant category), not here.
- Instead, infer based on context. For example:
  - A "Managing Director at a Big 4 firm advising distressed companies" likely has expertise in **Insolvency & Creditor Advisory** even if the word "insolvency" never appears.
  - Someone who "led the integration of a $2B acquisition" likely has **Post-Merger Integration** expertise even if those exact words aren't used.
  - A senior tax partner at an international firm likely has **International Tax** and **Transfer Pricing** capabilities even if the bio focuses on domestic engagements.
  - A CTO who "built the engineering team from 5 to 200" likely has **Organisational Design** and **Talent Strategy** expertise.
- Use professional judgement: consider the person's seniority, firm type, role scope, industry, and career trajectory to make reasonable inferences.
- Be selective — only infer expertise where there is a strong contextual signal. Do not guess or pad the list.
- Generate concise, professional labels (e.g., "Corporate Restructuring & Turnaround", "Supply Chain & Procurement", "Digital Transformation", "Working Capital & Cash Management").
- Aim for 3–8 inferred areas per profile. Quality over quantity. If the profile is too sparse to infer confidently, return fewer rather than guessing.

---

### LAYER 3 — Topic Overlap (Column M)

This layer identifies **granular, specific topics** that sit at the intersection of Layer 1 (explicit) and Layer 2 (inferred). These are the highest-confidence expertise tags because they are supported by BOTH direct textual evidence AND contextual inference.

There is NO fixed list for this layer either. Generate the topic labels yourself.

**How it works:**
A topic qualifies for Layer 3 ONLY if it bridges something explicitly stated in the profile (connected to a Layer 1 category) with something you inferred (a Layer 2 capability). It must have a foot in both worlds.

**Example:**
- Layer 1 matched "M&A and Corporate Development" (bio explicitly mentions "acquisitions" and "deal execution")
- Layer 2 inferred "Post-Merger Integration" (based on the person's role leading acquired business units)
- → Layer 3 topics: "Integration Planning", "Synergy Capture", "Day One Readiness", "Deal Structuring"
  These topics are specific, actionable, and grounded in both explicit evidence AND inferred capability.

**Another example:**
- Layer 1 matched "Finance and Accounting" (bio mentions "financial reporting" and "audit")
- Layer 2 inferred "Regulatory & Compliance" (person works at a firm known for compliance, senior enough to oversee it)
- → Layer 3 topics: "Financial Reporting", "Internal Control", "Audit Services", "Compliance"

**Rules:**
- Do NOT include topics that only relate to Layer 1 or only to Layer 2 — they must bridge both.
- Generate specific, actionable topic labels (not broad categories).
- Up to 20 topics per profile. These should be the terms you'd use to match this person to a specific project or engagement. For sparse profiles, 5–10 is fine — do not pad.
- Each topic should be 1–4 words, capitalised (e.g., "Cash Flow Forecasting", "Stakeholder Management", "AI Strategy").

---

### ADDITIONAL CLASSIFICATIONS

Also classify the profile into:

**Sectors** — identify industry sectors of the **clients the person has served** or has clear domain expertise in. This is NOT the sector of the person's own employer (e.g., do not tag "Professional Services" just because they work at a consulting firm). Generate freely, but keep them at the industry level (e.g., "Healthcare", "Financial Services", "Energy & Utilities", "Consumer & Retail", "Technology & Software"). Only include sectors with clear evidence.

**Geographies** — identify regions where the person has worked or has expertise. Use standard regional labels (e.g., "Europe", "North America", "Asia Pacific", "Middle East & Africa", "Latin America"). Only include regions with clear evidence from the profile.

**Primary Expertise** — pick the single most defining expertise category from the 13-category taxonomy (Layer 1). If none matched, use your best judgement to assign the closest category from the taxonomy based on overall profile context. Only return "Insufficient Data" if the profile is too thin to make any reasonable determination.

**Justification** — write 1–2 sentences explaining why this primary expertise was chosen, citing specific evidence from the profile.

---

### STRICT CONSTRAINTS

Before generating your output, verify the following:

1. **Layer 1 must only contain items from the 13-category taxonomy.** No free-form labels allowed.
2. **Layer 2 must NOT duplicate Layer 1.** If a capability was explicitly matched in Layer 1 for this profile, do not repeat it or rephrase it in Layer 2. The two layers must be mutually exclusive.
3. **Layer 3 must bridge Layer 1 and Layer 2.** Every topic must connect to at least one Layer 1 category AND at least one Layer 2 inference. If it only belongs to one layer, remove it.
4. **Sparse profiles get short lists.** If the profile contains only a name and title, or very limited information, keep all lists short (1–3 items for Layers 1 and 2, 3–5 for Layer 3) rather than hallucinating expertise.
5. **No padding.** It is better to return fewer, high-confidence results than to fill out the lists with speculative tags.

---

### OUTPUT FORMAT

Return a JSON array with one element per input person. Each element must have exactly these keys:

{{
  "name": "<exact person name from input>",
  "primary_expertise": "...",
  "justification": "...",
  "explicit_expertise_13": ["Category1", "Category2", ...],
  "sectors": ["Sector1", "Sector2", ...],
  "geographies": ["Region1", ...],
  "inferred_expertise_functional": ["Capability1", "Capability2", ...],
  "inference_reasoning": "Brief explanation of the key signals that drove your Layer 2 inferences.",
  "topic_overlap": ["Topic1", "Topic2", ...]
}}

You MUST return exactly one result per input person — never skip, merge, or omit anyone.
Return ONLY valid JSON. No commentary before or after."""


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

    def analyze_batch(self, people_text: str) -> str:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=16384,
            temperature=0,
            system=EXPERTISE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": people_text}],
        )
        return resp.content[0].text


class OpenAIProvider(BaseLLMProvider):
    def __init__(self):
        from openai import OpenAI
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.LLM_MODEL_OPENAI

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
        return resp.choices[0].message.content


class GeminiProvider(BaseLLMProvider):
    def __init__(self):
        from google import genai
        self.client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        self.model = settings.LLM_MODEL_GEMINI

    def analyze_batch(self, people_text: str) -> str:
        resp = self.client.models.generate_content(
            model=self.model,
            contents=f"{EXPERTISE_SYSTEM_PROMPT}\n\n{people_text}",
            config={
                "temperature": 0,
                "max_output_tokens": 65536,
            },
        )
        return resp.text


def get_provider() -> BaseLLMProvider:
    if settings.LLM_PROVIDER == "openai":
        return OpenAIProvider()
    if settings.LLM_PROVIDER == "gemini":
        return GeminiProvider()
    return ClaudeProvider()


# ── Formatting & parsing ────────────────────────────────────────────────────
def format_people_for_analysis(people: list[dict]) -> str:
    lines = []
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
        lines.append("")
    return "\n".join(lines)


def _normalize_name(name: str) -> str:
    """Lowercase and collapse whitespace for fuzzy matching."""
    return " ".join(name.lower().strip().split())


def _parse_llm_response(raw_response: str) -> list[dict]:
    """Parse LLM JSON response, handling markdown fences."""
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    results = json.loads(cleaned)
    return results if isinstance(results, list) else []


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
