"""Request and response models for the Step 4 values microservice."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from pydantic import BaseModel, Field, root_validator, validator

SUPPORTED_EVENT_TYPES = {"Financial Results", "Investor Presentation", "Earnings Call Transcript"}
DOCUMENT_TYPE_TO_EVENT_TYPE = {
    "financial_result": "Financial Results",
    "investor_presentation": "Investor Presentation",
    "earnings_call_transcript": "Earnings Call Transcript",
}
EVENT_TYPE_TO_DOCUMENT_TYPE = {
    value: key for key, value in DOCUMENT_TYPE_TO_EVENT_TYPE.items()
}


class ResolvedDocumentRequest(BaseModel):
    document_type: str
    event_type: str | None = None
    source_mode: str = "nse_auto"
    event_id: str
    source_url: str | None = None
    local_path: str | None = None
    title: str | None = None
    sort_date: str | None = None
    catalog: str | None = None
    classification: dict[str, Any] = Field(default_factory=dict)
    ir_agent_metadata: dict[str, Any] | None = None

    @validator("event_id")
    @classmethod
    def normalize_hash(cls, value: str) -> str:
        digest = value.strip()
        if len(digest) != 64:
            raise ValueError("event_id must be a 64-character sha256 hex digest")
        int(digest, 16)
        return digest

    @validator("event_type", always=True)
    @classmethod
    def default_event_type(cls, value: str | None, values: dict[str, Any]) -> str:
        return value or DOCUMENT_TYPE_TO_EVENT_TYPE.get(values.get("document_type"), "Financial Results")


class ExtractValuesRequest(BaseModel):
    symbol: str = Field(..., min_length=1, examples=["ITC"])
    from_date: str = Field(..., examples=["01-04-2026"])
    to_date: str = Field(..., examples=["30-06-2026"])
    company_id: str
    event_id: str | None = None
    pdf_url: str | None = None
    event_type: str = "Financial Results"
    document_type: str | None = None
    local_path: str | None = None
    resolved_documents: list[ResolvedDocumentRequest] | None = None
    force_reparse: bool = False
    parse_max_workers: int | None = None
    extraction_max_workers: int | None = None

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
    def normalize_hash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        digest = value.strip()
        if len(digest) != 64:
            raise ValueError("hash parameters must be 64-character sha256 hex digests")
        int(digest, 16)
        return digest

    @validator("pdf_url")
    @classmethod
    def validate_pdf_url(cls, value: str) -> str:
        if value is None:
            return value
        url = value.strip()
        return url or None

    @validator("event_type")
    @classmethod
    def normalize_event_type(cls, value: str) -> str:
        event_type = value.strip() or "Financial Results"
        if event_type not in SUPPORTED_EVENT_TYPES:
            allowed = ", ".join(sorted(SUPPORTED_EVENT_TYPES))
            raise ValueError(f"event_type must be one of: {allowed}")
        return event_type

    @validator("resolved_documents", pre=True)
    @classmethod
    def parse_resolved_documents(cls, value: Any) -> Any:
        if value in (None, ""):
            return None
        if isinstance(value, str):
            parsed = json.loads(value)
            return parsed.get("resolved_documents") if isinstance(parsed, dict) else parsed
        return value

    @validator("document_type", always=True)
    @classmethod
    def default_document_type(cls, value: str | None, values: dict[str, Any]) -> str:
        if value:
            return value
        return EVENT_TYPE_TO_DOCUMENT_TYPE.get(values.get("event_type"), "financial_result")

    @root_validator(skip_on_failure=True)
    @classmethod
    def require_legacy_or_batch_input(cls, values: dict[str, Any]) -> dict[str, Any]:
        docs = values.get("resolved_documents") or []
        if docs:
            return values
        if not values.get("event_id"):
            raise ValueError("event_id is required when resolved_documents is not provided")
        if not (values.get("pdf_url") or values.get("local_path")):
            raise ValueError("pdf_url or local_path is required when resolved_documents is not provided")
        return values


class ExtractedValueResponse(BaseModel):
    fact_key: str
    numeric_value: float | None = None
    value_text: str | None = None
    unit: str | None = None
    basis: str
    segment: str | None = None
    geography: str | None = None
    product: str | None = None
    channel: str | None = None
    project: str | None = None
    customer_type: str | None = None
    metric_context: str | None = None
    scope_level: str | None = None
    scope_name: str | None = None
    fact_type: str | None = None
    value_lower: float | None = None
    value_upper: float | None = None
    sentiment: str | None = None
    is_explicit_guidance: bool | None = None
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
    pdf_url: str | None = None
    event_type: str
    document_id: str
    storage_path: str
    markdown_length: int
    reporting_period: ReportingPeriodResponse
    extracted_count: int
    values: list[ExtractedValueResponse]
    document_results: list[dict[str, Any]] = Field(default_factory=list)
    next_service_params: dict[str, Any]


class ExtractValuesJobStartResponse(BaseModel):
    job_id: str
    status: str
    status_url: str


class ExtractValuesJobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: dict[str, Any] | None = None
    result: ExtractValuesResponse | None = None
    error: str | None = None


class EventSummaryRequest(BaseModel):
    event_id: str
    force: bool = False

    @validator("event_id")
    @classmethod
    def normalize_event_id(cls, value: str) -> str:
        digest = value.strip()
        if len(digest) != 64:
            raise ValueError("event_id must be a 64-character sha256 hex digest")
        int(digest, 16)
        return digest


class EventSummaryResponse(BaseModel):
    event_id: str
    document_id: str
    model: str
    headline: str
    summary: str
    key_points: list[str]
    investor_takeaway: str
    generated_at: str
    cached: bool
