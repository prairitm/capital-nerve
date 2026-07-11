"""Request and response models for the Step 5 metrics microservice."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, validator


class ComputeMetricsRequest(BaseModel):
    symbol: str = Field(..., min_length=1, examples=["ITC"])
    from_date: str = Field(..., examples=["01-04-2026"])
    to_date: str = Field(..., examples=["30-06-2026"])
    company_id: str
    event_id: str
    event_type: str = "Financial Results"
    pdf_url: str | None = None
    document_id: str | None = None
    period_quarter: int = Field(..., ge=1, le=4)
    period_fy_start: int
    period_end: str
    period_label: str | None = None

    @validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        symbol = value.strip().upper()
        if not symbol:
            raise ValueError("symbol is required")
        return symbol

    @validator("from_date", "to_date")
    @classmethod
    def validate_nse_date(cls, value: str) -> str:
        text = value.strip()
        datetime.strptime(text, "%d-%m-%Y")
        return text

    @validator("company_id", "event_id", "document_id")
    @classmethod
    def normalize_hash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        digest = value.strip()
        if not digest:
            return None
        if len(digest) != 64:
            raise ValueError("hash parameters must be 64-character sha256 hex digests")
        int(digest, 16)
        return digest

    @validator("period_end")
    @classmethod
    def validate_period_end(cls, value: str) -> str:
        text = value.strip()
        datetime.strptime(text, "%Y-%m-%d")
        return text

    @validator("event_type")
    @classmethod
    def normalize_event_type(cls, value: str) -> str:
        event_type = value.strip() or "Financial Results"
        if event_type not in {"Financial Results", "Investor Presentation", "Earnings Call Transcript"}:
            raise ValueError("event_type must be Financial Results, Investor Presentation, or Earnings Call Transcript")
        return event_type


class MetricValueResponse(BaseModel):
    metric_key: str
    name: str
    value: float
    unit: str | None = None
    category: str | None = None
    formula: str
    inputs: list[str]
    segment: str | None = None
    geography: str | None = None


class ScopeCountsResponse(BaseModel):
    current_facts: int
    prior_year_facts: int
    prior_quarter_facts: int


class ComputeMetricsResponse(BaseModel):
    db_path: str
    symbol: str
    from_date: str
    to_date: str
    company_id: str
    event_id: str
    event_type: str
    pdf_url: str | None = None
    document_id: str | None = None
    period_quarter: int
    period_fy_start: int
    period_end: str
    period_label: str | None = None
    metrics_count: int
    scope_counts: ScopeCountsResponse
    metrics: list[MetricValueResponse]
    next_service_params: dict[str, Any]
