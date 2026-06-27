"""Request and response models for the Step 4 values microservice."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, validator


class ExtractValuesRequest(BaseModel):
    symbol: str = Field(..., min_length=1, examples=["ITC"])
    from_date: str = Field(..., examples=["01-04-2026"])
    to_date: str = Field(..., examples=["30-06-2026"])
    company_id: str
    event_id: str
    pdf_url: str
    force_reparse: bool = False

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

    @validator("company_id", "event_id")
    @classmethod
    def normalize_hash(cls, value: str) -> str:
        digest = value.strip()
        if len(digest) != 64:
            raise ValueError("hash parameters must be 64-character sha256 hex digests")
        int(digest, 16)
        return digest

    @validator("pdf_url")
    @classmethod
    def validate_pdf_url(cls, value: str) -> str:
        url = value.strip()
        if not url:
            raise ValueError("pdf_url is required")
        return url


class ExtractedValueResponse(BaseModel):
    fact_key: str
    numeric_value: float
    unit: str | None = None
    basis: str
    evidence: str
    confidence: float


class ReportingPeriodResponse(BaseModel):
    quarter: int
    fy_start_year: int
    quarter_end: str
    label: str
    fy_label: str
    period_type: str
    source: str


class ExtractValuesResponse(BaseModel):
    db_path: str
    symbol: str
    from_date: str
    to_date: str
    company_id: str
    event_id: str
    pdf_url: str
    document_id: str
    storage_path: str
    markdown_length: int
    reporting_period: ReportingPeriodResponse
    extracted_count: int
    values: list[ExtractedValueResponse]
    next_service_params: dict[str, Any]
