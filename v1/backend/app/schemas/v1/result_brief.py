"""Result-brief v1 schemas — analyst-shaped briefing on a quarterly result.

`GET /v1/companies/{symbol}/result-brief?period=` returns the structured brief
that a sell-side analyst would otherwise spend hours assembling.
"""

from pydantic import BaseModel

from app.schemas.common import (
    CardMetricComparison,
    CompanyBrief,
    EvidenceItem,
    PeriodBrief,
)


class ResultBriefPoint(BaseModel):
    title: str
    detail: str | None = None
    metric_code: str | None = None
    value: float | str | None = None
    unit: str | None = None


class ResultPeerComparison(BaseModel):
    metric_code: str
    metric_name: str
    company_value: float | None = None
    peer_median: float | None = None
    rank: int | None = None
    sample_size: int = 0
    unit: str = ""


class ResultBrief(BaseModel):
    company: CompanyBrief
    period: PeriodBrief | None = None
    event_id: int | None = None
    headline: str
    overall_verdict: str | None = None
    key_positives: list[ResultBriefPoint] = []
    key_negatives: list[ResultBriefPoint] = []
    model_update_fields: dict[str, float | str | None] = {}
    peer_comparison: list[ResultPeerComparison] = []
    metric_comparisons: list[CardMetricComparison] = []
    source_evidence: list[EvidenceItem] = []
