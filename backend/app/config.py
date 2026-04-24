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
    LLM_MODEL_CLAUDE: str = "claude-sonnet-4-20250514"
    LLM_MODEL_OPENAI: str = "gpt-4o-mini"
    LLM_MODEL_GEMINI: str = "gemini-2.5-flash-lite"
    LLM_MODEL_DEEPSEEK: str = "deepseek-chat"
    LLM_MODEL_QWEN: str = "qwen3.6-35b-a3b"
    DEEPSEEK_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    LLM_PROVIDER_SCRAPING: str = "claude"    # override for scraping code gen (defaults to LLM_PROVIDER)
    LLM_MODEL_SCRAPING: str = "claude-opus-4-6" #"claude-sonnet-4-20250514"      # override model for scraping (defaults to provider's default)
    LLM_PROVIDER_DISCOVERY: str = ""  # override for team page discovery (defaults to LLM_PROVIDER_SCRAPING)
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    PROXY_URLS: Optional[str] = None

    class Config:
        env_file = str(Path(__file__).parent.parent.parent / ".env")


settings = Settings()
