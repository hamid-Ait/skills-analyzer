from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://pi_user:pi_pass@localhost:5432/people_intel"
    REDIS_URL: str = "redis://localhost:6379/0"
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    APIFY_API_TOKEN: str = ""
    LLM_PROVIDER: str = "claude"  # "claude" or "openai"
    LLM_MODEL_CLAUDE: str = "claude-sonnet-4-20250514"
    LLM_MODEL_OPENAI: str = "gpt-4o-mini"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    PROXY_URLS: Optional[str] = None

    class Config:
        env_file = ".env"


settings = Settings()
