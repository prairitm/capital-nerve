"""v1 company hub schemas.

`CompanyHubV1` is the typed equivalent of the legacy `GET /companies/{symbol}`
blob: latest event verdict, top intelligence objects, financial snapshot,
trends, event timeline, and source documents. Everything the company page
needs in a single request, mirrors `CompanyHubV1` derivations in
`app.routers.v1.companies`.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.common import (
    CompanyBadge,
    CompanyBrief,
    DocumentBrief,
    FinancialSnapshotRow,
    FinancialTrend,
    PeriodBrief,
    TimelineEvent,
)
from app.schemas.v1.intelligence_object import IntelligenceObjectBrief


class CompanyHubV1(BaseModel):
    """v1 company-page payload — typed, single round-trip."""

    company: CompanyBrief
    watchlist_status: bool
    badges: list[CompanyBadge] = []
    latest_event_id: int | None = None
    latest_period: PeriodBrief | None = None
    latest_summary: str | None = None
    main_issue: str | None = None
    watch_next: str | None = None
    top_objects: list[IntelligenceObjectBrief] = []
    financial_snapshot: list[FinancialSnapshotRow] = []
    trends: list[FinancialTrend] = []
    timeline: list[TimelineEvent] = []
    documents: list[DocumentBrief] = []
