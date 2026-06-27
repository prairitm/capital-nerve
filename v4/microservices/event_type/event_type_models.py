"""Request and response models for the Step 3 event-type microservice."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, validator


class ResolveEventTypeRequest(BaseModel):
    symbol: str = Field(..., min_length=1, examples=["ITC"])
    from_date: str = Field(..., examples=["01-04-2026"])
    to_date: str = Field(..., examples=["30-06-2026"])
    company_id: str
    event_type: str = Field(default="Financial Results")

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

    @validator("company_id")
    @classmethod
    def normalize_company_id(cls, value: str) -> str:
        company_id = value.strip()
        if len(company_id) != 64:
            raise ValueError("company_id must be a 64-character sha256 hex digest")
        int(company_id, 16)
        return company_id

    @validator("event_type")
    @classmethod
    def normalize_event_type(cls, value: str) -> str:
        event_type = value.strip() or "Financial Results"
        if event_type != "Financial Results":
            raise ValueError("Step 3 only handles Financial Results")
        return event_type


class CandidateResponse(BaseModel):
    sort_date: str | None = None
    source_url: str | None = None
    title: str | None = None
    event_bucket: str
    chosen: bool


class ResolveEventTypeResponse(BaseModel):
    db_path: str
    symbol: str
    from_date: str
    to_date: str
    company_id: str
    event_type: str
    event_id: str
    chosen_source_url: str
    chosen_title: str | None = None
    chosen_sort_date: str | None = None
    announcements_count: int
    financial_results_count: int
    period_markers: list[str]
    classification: dict[str, Any]
    recovery_needed: bool
    rejected_url: str | None = None
    candidates: list[CandidateResponse]
    next_service_params: dict[str, Any]
