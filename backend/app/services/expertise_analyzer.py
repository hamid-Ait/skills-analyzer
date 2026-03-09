import json
import logging
from abc import ABC, abstractmethod

from app.config import settings


log = logging.getLogger(__name__)

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

EXPERTISE_SYSTEM_PROMPT = f"""You are an expert at categorizing professional expertise.
Given information about people (name, title, bio, department, location, and optionally LinkedIn headline, summary, experience, and skills), classify each person into:

1. primary_expertise: A concise label for their main area of expertise (e.g., "Restructuring Advisory", "Digital Transformation", "Tax Consulting")

2. justification: A brief explanation (1-2 sentences) of why this classification was chosen.

3. matched_13_categories: Select ALL that apply from this exact list:
{json.dumps(EXPERTISE_CATEGORIES, indent=2)}

4. sector: The industry sector they specialize in (e.g., "Financial Services", "Healthcare", "Energy", "Technology", "Consumer & Retail", "Public Sector", "General")

5. geography: The geographic region(s) where the person has applied their expertise, based on their work experience, clients, and projects — NOT simply where they are located (e.g., "North America", "Europe", "Middle East", "Asia Pacific", "Global", "Latin America", "Africa")

6. inferred_expertise_functional: Their functional expertise area (e.g., "Advisory", "Implementation", "Analytics", "Leadership", "Consulting")

7. matched_inferred_expertise_topics: Specific topic areas as a list (e.g., ["bankruptcy", "turnaround", "creditor negotiations"])

Return a JSON array where each element corresponds to the input person (same order).
Each element must have exactly these keys: primary_expertise, justification, matched_13_categories, sector, geography, inferred_expertise_functional, matched_inferred_expertise_topics.
For matched_13_categories, only use values from the exact list above. Return ONLY valid JSON, no prose."""


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
            temperature=0.1,
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
                "temperature": 0.1,
                "max_output_tokens": 16384,
            },
        )
        return resp.text


def get_provider() -> BaseLLMProvider:
    if settings.LLM_PROVIDER == "openai":
        return OpenAIProvider()
    if settings.LLM_PROVIDER == "gemini":
        return GeminiProvider()
    return ClaudeProvider()


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
        # LinkedIn-enriched fields for richer analysis
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


def analyze_people(people_data: list[dict], batch_size: int = 10) -> list[dict]:
    """Analyze a batch of people and return expertise classifications."""
    provider = get_provider()
    all_results = []

    for i in range(0, len(people_data), batch_size):
        batch = people_data[i:i + batch_size]
        text = format_people_for_analysis(batch)

        try:
            raw_response = provider.analyze_batch(text)
            # Clean markdown fences if present
            cleaned = raw_response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            results = json.loads(cleaned)
            if isinstance(results, list):
                all_results.extend(results)
            else:
                log.warning(f"LLM returned non-list for batch starting at {i}")
                all_results.extend([{}] * len(batch))
        except (json.JSONDecodeError, Exception) as exc:
            log.error(f"Failed to parse LLM response for batch starting at {i}: {exc}")
            all_results.extend([{}] * len(batch))

    return all_results
