"""Request and response models for the Step 7 alerts microservice."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, validator


class PresentAlertsRequest(BaseModel):
    symbol: str = Field(..., min_length=1, examples=["ITC"])
    from_date: str = Field(..., examples=["01-04-2026"])
    to_date: str = Field(..., examples=["30-06-2026"])
    company_id: str
    event_id: str
    pdf_url: str | None = None
    document_id: str | None = None
    period_quarter: int = Field(..., ge=1, le=4)
    period_fy_start: int
    period_end: str
    period_label: str | None = None
    metrics_count: int | None = None
    signals_count: int | None = None

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


class AlertResponse(BaseModel):
    signal_type: str
    title: str
    description: str | None = None
    direction: str | None = None
    severity: str | None = None
    evidence: dict[str, Any]
    trigger_values: dict[str, Any]


class DbSummaryResponse(BaseModel):
    extracted_values: int
    metric_values: int
    signals: int


class PresentAlertsResponse(BaseModel):
    db_path: str
    symbol: str
    from_date: str
    to_date: str
    company_id: str
    event_id: str
    pdf_url: str | None = None
    document_id: str | None = None
    period_quarter: int
    period_fy_start: int
    period_end: str
    period_label: str | None = None
    metrics_count: int | None = None
    signals_count: int | None = None
    alert_count: int
    alerts: list[AlertResponse]
    db_summary: DbSummaryResponse
    message: str
    next_service_params: dict[str, Any]
