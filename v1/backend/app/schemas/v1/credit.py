"""Credit-risk-only v1 signal slice.

Returned by `GET /v1/companies/{symbol}/credit-risk-signals`. The shape mirrors
`SignalBriefV1` plus a derived `credit_dimension` (debt, coverage, working
capital, auditor, rating) used to bucket the signals in dashboards.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.db.enums import SeverityLevel, SignalDirection
from app.schemas.common import CompanyBrief, PeriodBrief

CreditDimension = Literal[
    "debt",
    "coverage",
    "working_capital",
    "earnings_quality",
    "auditor",
    "rating",
    "other",
]


class CreditRiskSignal(BaseModel):
    signal_id: int
    signal_code: str
    signal_name: str
    signal_category: str
    credit_dimension: CreditDimension
    direction: SignalDirection
    severity: SeverityLevel
    confidence_score: float | None = None
    signal_score: float | None = None
    headline: str | None = None
    explanation: str | None = None
    period: PeriodBrief | None = None
    event_id: int | None = None
    created_at: datetime | None = None


class CreditRiskResponse(BaseModel):
    company: CompanyBrief
    overall_risk: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    rationale: str | None = None
    signals: list[CreditRiskSignal] = []
