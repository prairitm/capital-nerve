"""Retail-summary v1 schemas — the consumer-facing wedge for brokerages.

`GET /v1/companies/{symbol}/retail-summary` returns a short, plain-English
explainer with a `risk_level` and `momentum` so a retail app can power its
stock page without re-implementing aggregation logic.
"""

from typing import Literal

from pydantic import BaseModel

from app.schemas.common import CompanyBrief, PeriodBrief


class RetailSummaryPoint(BaseModel):
    label: str
    tone: Literal["positive", "negative", "mixed", "neutral"]
    detail: str | None = None


class RetailSummary(BaseModel):
    company: CompanyBrief
    period: PeriodBrief | None = None
    simple_summary: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    momentum: Literal["positive", "negative", "mixed", "neutral"]
    top_3_points: list[RetailSummaryPoint] = []
    headline_metrics: list[dict[str, str | float | None]] = []
