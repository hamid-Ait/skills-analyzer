from typing import Optional
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Date
from pydantic import BaseModel

from app.database import get_db
from app.models import Company
from app.models.usage_log import UsageLog

router = APIRouter(prefix="/costs")


# --- Response models ---

class ServiceCost(BaseModel):
    service: str
    cost: float


class ProviderCost(BaseModel):
    provider: str
    cost: float


class CompanyCost(BaseModel):
    company_id: str
    company_name: Optional[str]
    cost: float


class StepCost(BaseModel):
    step: str
    cost: float


class DailyCost(BaseModel):
    date: str
    cost: float


class TokenTotals(BaseModel):
    input_tokens: int
    output_tokens: int


class CostSummary(BaseModel):
    total_cost_usd: float
    cost_by_service: list[ServiceCost]
    cost_by_provider: list[ProviderCost]
    cost_by_company: list[CompanyCost]
    cost_by_step: list[StepCost]
    cost_over_time: list[DailyCost]
    token_totals: TokenTotals


@router.get("/summary", response_model=CostSummary)
def get_cost_summary(
    days: int = Query(30, ge=1, le=365),
    company_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    base = db.query(UsageLog).filter(UsageLog.created_at >= since)
    if company_id:
        base = base.filter(UsageLog.company_id == company_id)

    # Total cost
    total = base.with_entities(func.coalesce(func.sum(UsageLog.cost_usd), 0.0)).scalar()

    # Cost by service
    by_service = (
        base.with_entities(UsageLog.service, func.sum(UsageLog.cost_usd))
        .group_by(UsageLog.service)
        .all()
    )

    # Cost by provider
    by_provider = (
        base.with_entities(UsageLog.provider, func.sum(UsageLog.cost_usd))
        .group_by(UsageLog.provider)
        .order_by(func.sum(UsageLog.cost_usd).desc())
        .all()
    )

    # Cost by company (top 50)
    by_company_q = (
        base.with_entities(
            UsageLog.company_id,
            func.sum(UsageLog.cost_usd),
        )
        .filter(UsageLog.company_id.isnot(None))
        .group_by(UsageLog.company_id)
        .order_by(func.sum(UsageLog.cost_usd).desc())
        .limit(50)
        .all()
    )
    # Resolve company names
    company_ids = [str(row[0]) for row in by_company_q]
    company_names = {}
    if company_ids:
        companies = db.query(Company).filter(Company.id.in_(company_ids)).all()
        company_names = {str(c.id): c.name or c.url for c in companies}

    by_company = [
        CompanyCost(
            company_id=str(row[0]),
            company_name=company_names.get(str(row[0])),
            cost=round(row[1], 6),
        )
        for row in by_company_q
    ]

    # Cost by pipeline step
    by_step = (
        base.with_entities(UsageLog.pipeline_step, func.sum(UsageLog.cost_usd))
        .group_by(UsageLog.pipeline_step)
        .order_by(func.sum(UsageLog.cost_usd).desc())
        .all()
    )

    # Cost over time (daily)
    daily = (
        base.with_entities(
            cast(UsageLog.created_at, Date).label("day"),
            func.sum(UsageLog.cost_usd),
        )
        .group_by("day")
        .order_by("day")
        .all()
    )

    # Token totals
    tokens = base.with_entities(
        func.coalesce(func.sum(UsageLog.input_tokens), 0),
        func.coalesce(func.sum(UsageLog.output_tokens), 0),
    ).first()

    return CostSummary(
        total_cost_usd=round(total, 6),
        cost_by_service=[
            ServiceCost(service=row[0], cost=round(row[1], 6)) for row in by_service
        ],
        cost_by_provider=[
            ProviderCost(provider=row[0], cost=round(row[1], 6)) for row in by_provider
        ],
        cost_by_company=by_company,
        cost_by_step=[
            StepCost(step=row[0], cost=round(row[1], 6)) for row in by_step
        ],
        cost_over_time=[
            DailyCost(date=str(row[0]), cost=round(row[1], 6)) for row in daily
        ],
        token_totals=TokenTotals(
            input_tokens=tokens[0],
            output_tokens=tokens[1],
        ),
    )
