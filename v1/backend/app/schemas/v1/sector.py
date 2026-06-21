"""Sector-level v1 schemas — cross-company signal aggregation."""

from pydantic import BaseModel

from app.db.enums import SeverityLevel, SignalDirection
from app.schemas.common import CompanyBrief, PeriodBrief


class SectorSignalRow(BaseModel):
    """One signal row from a sector roll-up — same shape as `SignalBriefV1`
    minus the embedded company sector since the sector is the parent context."""

    signal_id: int
    signal_code: str
    signal_name: str
    signal_category: str
    direction: SignalDirection
    severity: SeverityLevel
    confidence_score: float | None = None
    signal_score: float | None = None
    headline: str | None = None
    company: CompanyBrief
    period: PeriodBrief | None = None
    event_id: int | None = None


class SectorSignalsResponse(BaseModel):
    sector_name: str
    company_count: int
    signal_count: int
    signals: list[SectorSignalRow]
