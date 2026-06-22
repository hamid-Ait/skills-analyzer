from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://pi_user:pi_pass@localhost:5432/people_intel"
    REDIS_URL: str = "redis://localhost:6379/0"
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    QWEN_API_KEY: str = ""
    APIFY_API_TOKEN: str = ""
    LLM_PROVIDER: str = "gemini"  # "claude", "openai", or "gemini"
    LLM_MODEL_CLAUDE: str = "claude-haiku-4-5-20251001"#"claude-sonnet-4-20250514"
    LLM_MODEL_OPENAI: str = "gpt-4o"
    LLM_MODEL_GEMINI: str = "gemini-2.5-flash"
    LLM_MODEL_DEEPSEEK: str = "deepseek-v4-flash"
    LLM_MODEL_QWEN: str = "qwen3.6-plus"
    DEEPSEEK_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    LLM_PROVIDER_SCRAPING: str = "claude"    # override for scraping code gen (defaults to LLM_PROVIDER)
    LLM_MODEL_SCRAPING: str = "claude-opus-4-6" #"claude-sonnet-4-20250514"      # override model for scraping (defaults to provider's default)
    LLM_PROVIDER_DISCOVERY: str = ""  # override for team page discovery (defaults to LLM_PROVIDER_SCRAPING)
    PROMPT_VERSION: str = "v4"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # QA validator thresholds (configurable via env vars)
    QA_MAX_L1_CATEGORIES: int = 4
    QA_MAX_DECLARED_CAPABILITIES: int = 8
    QA_MAX_INFERRED: int = 12
    QA_MAX_TOPICS: int = 20
    PROXY_URLS: Optional[str] = None
    SCRAPE_MAX_PROFILES: int = 10000

    # LinkedIn resolution: max employees to bulk-fetch for the Stage 0 roster match.
    # Bounds cost on very large companies; the roster only adds coverage (unmatched
    # people always fall through to Google + per-person search), so capping it never
    # lowers recall — it just trades a big single fetch for cheaper targeted lookups.
    LINKEDIN_ROSTER_MAX: int = 3000

    class Config:
        env_file = str(Path(__file__).parent.parent.parent / ".env")
        extra = "ignore"


settings = Settings()
