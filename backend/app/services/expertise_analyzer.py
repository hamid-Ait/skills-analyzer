import json
import logging
import os
import re
from abc import ABC, abstractmethod

from app.config import settings


def _load_prompt(version: str) -> str:
    if version.isdigit():
        version = f"v{version}"
    path = os.path.join(os.path.dirname(__file__), "..", "prompts", f"{version}.txt")
    with open(os.path.normpath(path)) as f:
        return f.read()


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


# ── System prompt ─────────────────────────────────────────────────────────────
# Versioned prompt files: backend/app/prompts/vN.txt
# Switch via PROMPT_VERSION env var (default: v2). See prompts/CHANGELOG.md.
# (archived prompt text moved to backend/app/prompts/v1.txt and v2.txt)

EXPERTISE_SYSTEM_PROMPT = _load_prompt(settings.PROMPT_VERSION)

# ── LLM Providers ───────────────────────────────────────────────────────────
class BaseLLMProvider(ABC):
    batch_size: int = 10  # override in subclasses with tight output token limits

    @abstractmethod
    def analyze_batch(self, people_text: str) -> str:
        pass


class ClaudeProvider(BaseLLMProvider):
    def __init__(self, model: str | None = None):
        import anthropic
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = model or settings.LLM_MODEL_CLAUDE
        self.last_usage: dict | None = None

    def analyze_batch(self, people_text: str) -> str:
        kwargs: dict = {}
        if not self.model.startswith(("claude-opus-4", "claude-sonnet-4", "claude-haiku-4")):
            kwargs["temperature"] = 0
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=16384,
            system=EXPERTISE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": people_text}],
            **kwargs,
        )
        self.last_usage = {
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
            "model": self.model,
        }
        return resp.content[0].text


def _openai_is_reasoning(model: str) -> bool:
    """True for models that use max_completion_tokens and don't support temperature."""
    return model.startswith(("o1", "o3", "o4", "o5", "gpt-5"))


class OpenAIProvider(BaseLLMProvider):
    def __init__(self, model: str | None = None):
        from openai import OpenAI
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = model or settings.LLM_MODEL_OPENAI
        self.last_usage: dict | None = None

    def analyze_batch(self, people_text: str) -> str:
        kwargs: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": EXPERTISE_SYSTEM_PROMPT},
                {"role": "user", "content": people_text},
            ],
        }
        if _openai_is_reasoning(self.model):
            kwargs["max_completion_tokens"] = 16384
        else:
            kwargs["max_tokens"] = 16384
            kwargs["temperature"] = 0
        resp = self.client.chat.completions.create(**kwargs)
        if resp.usage:
            self.last_usage = {
                "input_tokens": resp.usage.prompt_tokens,
                "output_tokens": resp.usage.completion_tokens,
                "model": self.model,
            }
        return resp.choices[0].message.content


class GeminiProvider(BaseLLMProvider):
    # Flash-Lite has a tighter practical output budget than full Flash.
    # With evidence_map JSON, 10 profiles can exceed ~16k tokens; keep batches small.
    batch_size = 5

    def __init__(self, model: str | None = None):
        from google import genai
        self.client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        self.model = model or settings.LLM_MODEL_GEMINI
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
    batch_size = 5  # 8192 output token cap — 10 profiles with evidence maps exceeds it

    def __init__(self, model: str | None = None):
        from openai import OpenAI
        self.client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
        )
        self.model = model or settings.LLM_MODEL_DEEPSEEK
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
    def __init__(self, model: str | None = None):
        from openai import OpenAI
        self.client = OpenAI(
            api_key=settings.QWEN_API_KEY,
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        )
        self.model = model or settings.LLM_MODEL_QWEN
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


SUPPORTED_PROVIDERS = {"claude", "openai", "gemini", "deepseek", "qwen"}

PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "claude":   settings.LLM_MODEL_CLAUDE,
    "openai":   settings.LLM_MODEL_OPENAI,
    "gemini":   settings.LLM_MODEL_GEMINI,
    "deepseek": settings.LLM_MODEL_DEEPSEEK,
    "qwen":     settings.LLM_MODEL_QWEN,
}


def get_provider_by_name(provider_name: str, model: str | None = None) -> BaseLLMProvider:
    if provider_name == "openai":
        return OpenAIProvider(model=model)
    if provider_name == "gemini":
        return GeminiProvider(model=model)
    if provider_name == "deepseek":
        return DeepSeekProvider(model=model)
    if provider_name == "qwen":
        return QwenProvider(model=model)
    if provider_name == "claude":
        return ClaudeProvider(model=model)
    raise ValueError(f"Unknown provider: {provider_name!r}. Supported: {sorted(SUPPORTED_PROVIDERS)}")


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
        if p.get("resolved_l1_hints"):
            hints = p["resolved_l1_hints"]
            if isinstance(hints, list):
                hints = "; ".join(hints)
            lines.append(f"  Resolved L1 Hints: {hints}")
        if p.get("resolved_sector_hints"):
            hints = p["resolved_sector_hints"]
            if isinstance(hints, list):
                hints = "; ".join(hints)
            lines.append(f"  Resolved Sector Hints: {hints}")
        lines.append("")
    return "\n".join(lines)


def _normalize_name(name: str) -> str:
    """Lowercase and collapse whitespace for fuzzy matching."""
    return " ".join(name.lower().strip().split())


def _extract_complete_objects(text: str) -> list[dict]:
    """Extract all complete top-level JSON objects from a (possibly truncated) string."""
    objects: list[dict] = []
    depth = 0
    start: int | None = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    obj = json.loads(text[start : i + 1])
                    if isinstance(obj, dict):
                        objects.append(obj)
                except json.JSONDecodeError:
                    pass
                start = None
    return objects


def _parse_llm_response(raw_response: str) -> list[dict]:
    """Parse LLM JSON response, handling markdown fences and truncated output."""
    cleaned = raw_response.strip()

    # Extract content from the first markdown code fence (handles ```json, ```, extra trailing text)
    # Use [^\n]* (not \s*) after the language tag so we don't skip past blank lines inside the JSON
    fence_match = re.search(r"```(?:json)?[^\n]*\n([\s\S]*?)\n[ \t]*```", cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    elif cleaned.startswith("```"):
        # Fallback: strip opening fence line only
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    # 1. Happy path — full valid JSON
    try:
        results = json.loads(cleaned)
        if isinstance(results, list):
            return results
        if isinstance(results, dict):
            return [results]
        return []
    except json.JSONDecodeError:
        pass

    # 2. Array bounds recovery — walk brackets to find the matching ']' for the first '['
    # (rfind would break if DeepSeek appends explanation text that contains ']' characters)
    arr_start = cleaned.find("[")
    if arr_start != -1:
        depth = 0
        arr_end = -1
        in_str = False
        escape_next = False
        for idx in range(arr_start, len(cleaned)):
            ch = cleaned[idx]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\" and in_str:
                escape_next = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    arr_end = idx
                    break
        if arr_end != -1:
            try:
                results = json.loads(cleaned[arr_start : arr_end + 1])
                return results if isinstance(results, list) else []
            except json.JSONDecodeError:
                pass

    # 3. Truncated output recovery — extract every complete object found
    objects = _extract_complete_objects(cleaned)
    if objects:
        log.warning(
            "LLM response was truncated — salvaged %d complete object(s). "
            "Raw (first 200 chars): %s",
            len(objects), cleaned[:200],
        )
        return objects

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
