"""Request and response models for the Step 2 event microservice."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, validator


class DiscoverEventsRequest(BaseModel):
    symbol: str = Field(..., min_length=1, examples=["ITC"])
    from_date: str = Field(..., examples=["01-04-2026"])
    to_date: str = Field(..., examples=["30-06-2026"])
    company_id: str | None = Field(default=None)

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
    def normalize_company_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        company_id = value.strip()
        if not company_id:
            return None
        if len(company_id) != 64:
            raise ValueError("company_id must be a 64-character sha256 hex digest")
        int(company_id, 16)
        return company_id


class EventResponse(BaseModel):
    id: str
    company_id: str
    event_type: str
    event_date: str
    title: str | None = None
    source_url: str | None = None
    status: str | None = None


class DiscoverEventsResponse(BaseModel):
    db_path: str
    company_id: str
    symbol: str
    from_date: str
    to_date: str
    next_service_params: dict[str, Any]
    announcements_count: int
    stored_count: int
    desc_buckets: dict[str, int]
    events: list[EventResponse]
    first_announcement: dict[str, Any] | None = None
