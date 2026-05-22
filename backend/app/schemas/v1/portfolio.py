"""Portfolio monitoring v1 schemas.

`POST /v1/portfolio/monitor` accepts a list of symbols + optional severity /
importance filters and returns a ranked list of portfolio alerts each linked to
an underlying Intelligence Object.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.db.enums import SeverityLevel, SignalDirection
from app.schemas.common import CompanyBrief
from app.schemas.v1.intelligence_object import IntelligenceObjectBrief


class PortfolioMonitorRequest(BaseModel):
    """Portfolio monitor input — keep it small so it can be embedded in URLs
    or webhooks. The frontend sends NSE/BSE symbols verbatim."""

    symbols: list[str] = Field(default_factory=list, max_length=200)
    min_importance: int | None = Field(default=None, ge=0, le=100)
    severity_in: list[SeverityLevel] | None = None
    direction_in: list[SignalDirection] | None = None
    limit_per_company: int = Field(default=3, ge=1, le=10)


class PortfolioAlert(BaseModel):
    """One ranked alert for one company inside the portfolio."""

    company: CompanyBrief
    matched: bool
    reason: str | None = None
    top_objects: list[IntelligenceObjectBrief] = []
    triggered_at: datetime | None = None


class PortfolioMonitorResponse(BaseModel):
    """Wrapper response so consumers can read meta alongside the alerts."""

    requested_symbols: list[str]
    resolved_companies: int
    unresolved_symbols: list[str] = []
    alerts: list[PortfolioAlert] = []
