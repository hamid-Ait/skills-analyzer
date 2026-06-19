"""Cost tracking service for LLM and Apify usage."""
import logging
from typing import Optional

from app.database import SessionLocal
from app.models.usage_log import UsageLog

log = logging.getLogger(__name__)

# Pricing per 1M tokens (input, output) in USD
TOKEN_PRICING: dict[str, tuple[float, float]] = {
    # Claude Sonnet 4
    "claude-sonnet-4-20250514": (3.0, 15.0),
    # GPT-4o-mini
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-5-mini" : (0.25, 2.0),
    # Gemini 2.5 Flash
    "gemini-2.5-flash": (0.30, 2.50),
    # DeepSeek Chat (cache-miss input price)
    "deepseek-chat": (0.28, 0.42),
    # Manus
    "manus-1": (3.0, 15.0),
    # Claude Opus 4.6 (scraping agent)
    "claude-opus-4-6": (5.0, 25.0),
}


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute cost in USD from token counts and model pricing."""
    pricing = TOKEN_PRICING.get(model)
    if not pricing:
        # Try prefix matching for versioned model names
        for key, val in TOKEN_PRICING.items():
            if model.startswith(key) or key.startswith(model):
                pricing = val
                break
    if not pricing:
        log.warning(f"No pricing found for model '{model}', using zero cost")
        return 0.0

    input_price, output_price = pricing
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def log_usage(
    *,
    company_id: Optional[str] = None,
    service: str,
    provider: str,
    model: Optional[str] = None,
    pipeline_step: str,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    cost_usd: Optional[float] = None,
    metadata_json: Optional[dict] = None,
) -> None:
    """Log a usage event to the database.

    If cost_usd is not provided, it's computed from token counts + model pricing.
    """
    if cost_usd is None and model and input_tokens and output_tokens:
        cost_usd = compute_cost(model, input_tokens, output_tokens)
    if cost_usd is None:
        cost_usd = 0.0

    db = SessionLocal()
    try:
        entry = UsageLog(
            company_id=company_id,
            service=service,
            provider=provider,
            model=model,
            pipeline_step=pipeline_step,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            metadata_json=metadata_json,
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        log.error(f"Failed to log usage: {exc}")
        db.rollback()
    finally:
        db.close()


def extract_apify_cost(apify_client, run: dict) -> Optional[float]:
    """Extract the actual USD cost from an Apify actor run."""
    try:
        run_id = run.get("id")
        if not run_id:
            return None
        run_data = apify_client.run(run_id).get()
        return run_data.get("usageTotalUsd")
    except Exception as exc:
        log.warning(f"Failed to extract Apify run cost: {exc}")
        return None
