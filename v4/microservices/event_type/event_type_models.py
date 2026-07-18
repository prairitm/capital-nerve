"""Request and response models for the Step 3 event-type microservice."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from pydantic import BaseModel, Field, validator

DOCUMENT_TYPE_ALIASES = {
    "financial result": "financial_result",
    "financial results": "financial_result",
    "financial_result": "financial_result",
    "investor presentation": "investor_presentation",
    "investor_presentation": "investor_presentation",
    "earnings call transcript": "earnings_call_transcript",
    "earnings_call_transcript": "earnings_call_transcript",
    "earnings transcript": "earnings_call_transcript",
    "earnings_transcript": "earnings_call_transcript",
    "transcript": "earnings_call_transcript",
}
EVENT_TYPE_TO_DOCUMENT_TYPE = {
    "Financial Results": "financial_result",
    "Investor Presentation": "investor_presentation",
    "Earnings Call Transcript": "earnings_call_transcript",
}
DOCUMENT_TYPE_TO_EVENT_TYPE = {
    "financial_result": "Financial Results",
    "investor_presentation": "Investor Presentation",
    "earnings_call_transcript": "Earnings Call Transcript",
}
SUPPORTED_EVENT_TYPES = set(EVENT_TYPE_TO_DOCUMENT_TYPE)
SUPPORTED_SOURCE_MODES = {"nse_auto", "nse_exact", "ir_agent", "manual_url", "local_file"}


def normalize_document_type(value: str) -> str:
    key = value.strip().lower().replace("-", "_")
    normalized = DOCUMENT_TYPE_ALIASES.get(key, key)
    if normalized not in DOCUMENT_TYPE_TO_EVENT_TYPE:
        allowed = ", ".join(sorted(DOCUMENT_TYPE_TO_EVENT_TYPE))
        raise ValueError(f"document_type must be one of: {allowed}")
    return normalized


def normalize_source_mode(value: str) -> str:
    mode = value.strip().lower().replace("-", "_")
    if mode not in SUPPORTED_SOURCE_MODES:
        allowed = ", ".join(sorted(SUPPORTED_SOURCE_MODES))
        raise ValueError(f"source_mode must be one of: {allowed}")
    return mode


class DocumentRequest(BaseModel):
    document_type: str = Field(default="financial_result")
    source_mode: str = Field(default="nse_auto")
    catalog: str | None = None
    source_url: str | None = None
    local_path: str | None = None
    company_url: str | None = None
    company_name: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    model: str | None = None

    @validator("document_type")
    @classmethod
    def validate_document_type(cls, value: str) -> str:
        return normalize_document_type(value)

    @validator("source_mode")
    @classmethod
    def validate_source_mode(cls, value: str) -> str:
        return normalize_source_mode(value or "nse_auto")

    @validator("source_url", "local_path", "catalog", "company_url", "company_name", "start_date", "end_date", "model")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class ResolvedDocumentResponse(BaseModel):
    document_type: str
    event_type: str
    source_mode: str
    event_id: str
    source_url: str | None = None
    local_path: str | None = None
    title: str | None = None
    sort_date: str | None = None
    catalog: str | None = None
    classification: dict[str, Any] = Field(default_factory=dict)
    ir_agent_metadata: dict[str, Any] | None = None


class ResolveEventTypeRequest(BaseModel):
    symbol: str = Field(..., min_length=1, examples=["ITC"])
    from_date: str = Field(..., examples=["01-04-2026"])
    to_date: str = Field(..., examples=["30-06-2026"])
    company_id: str
    event_type: str = Field(default="Financial Results")
    documents: list[DocumentRequest] | None = None

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
        if event_type not in SUPPORTED_EVENT_TYPES:
            allowed = ", ".join(sorted(SUPPORTED_EVENT_TYPES))
            raise ValueError(f"Step 3 only handles: {allowed}")
        return event_type

    @validator("documents", pre=True)
    @classmethod
    def parse_documents(cls, value: Any) -> Any:
        if value in (None, ""):
            return None
        if isinstance(value, str):
            parsed = json.loads(value)
            return parsed.get("documents") if isinstance(parsed, dict) else parsed
        return value


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
    resolved_documents: list[ResolvedDocumentResponse] = Field(default_factory=list)
    next_service_params: dict[str, Any]
