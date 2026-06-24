"""Row -> JSON serializers for the 7-step schema.

Keeps the API response shapes consistent and centralises the small amount of
normalization the frontend relies on (event-type mapping, JSON column parsing,
catalog enrichment).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from catalog import fact_meta, metric_meta, signal_meta

# v3 stores free-text event buckets (e.g. "Financial Results"). The frontend
# uses a small enum-like set of labels; map the common ones, pass through the
# rest as a Title Cased string.
_EVENT_TYPE_MAP = {
    "financial results": "QUARTERLY_RESULT",
    "quarterly result": "QUARTERLY_RESULT",
    "quarterly results": "QUARTERLY_RESULT",
    "board meeting": "EXCHANGE_FILING",
    "investor presentation": "INVESTOR_PRESENTATION",
    "analysts/institutional investor meet/con. call updates": "CONCALL_TRANSCRIPT",
    "press release": "PRESS_RELEASE",
    "annual report": "ANNUAL_REPORT",
}


def normalize_event_type(raw: str | None) -> str:
    if not raw:
        return "EXCHANGE_FILING"
    key = raw.strip().lower()
    if key in _EVENT_TYPE_MAP:
        return _EVENT_TYPE_MAP[key]
    return raw.strip().upper().replace(" ", "_").replace("/", "_")


def parse_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def quarter_label(row: sqlite3.Row | dict) -> str | None:
    """Build a 'Q3 FY2025-26'-style label from fiscal_year/quarter when set."""
    fy = _get(row, "fiscal_year")
    q = _get(row, "fiscal_quarter")
    if fy is None or q is None:
        return None
    fy_short = int(fy) + 1
    return f"Q{q} FY{fy}-{str(fy_short)[-2:]}"


def _get(row: sqlite3.Row | dict, key: str, default: Any = None) -> Any:
    try:
        value = row[key]
    except (KeyError, IndexError):
        return default
    return value if value is not None else default


def company_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": _get(row, "name"),
        "ticker": _get(row, "ticker"),
        "exchange": _get(row, "exchange"),
        "sector": _get(row, "sector"),
        "industry": _get(row, "industry"),
        "isin": _get(row, "isin"),
    }


def event_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "company_id": _get(row, "company_id"),
        "event_type": normalize_event_type(_get(row, "event_type")),
        "event_type_raw": _get(row, "event_type"),
        "event_date": _get(row, "event_date"),
        "fiscal_year": _get(row, "fiscal_year"),
        "fiscal_quarter": _get(row, "fiscal_quarter"),
        "period_label": quarter_label(row),
        "title": _get(row, "title"),
        "source_url": _get(row, "source_url"),
        "document_id": _get(row, "document_id"),
        "status": _get(row, "status"),
    }


def extracted_value_dict(row: sqlite3.Row) -> dict[str, Any]:
    code = row["value_code"]
    meta = fact_meta(code)
    return {
        "value_code": code,
        "value_name": meta.get("name") or code,
        "value_numeric": _get(row, "value_numeric"),
        "value_text": _get(row, "value_text"),
        "unit": _get(row, "unit") or meta.get("unit"),
        "period_type": _get(row, "period_type"),
        "period_start": _get(row, "period_start"),
        "period_end": _get(row, "period_end"),
        "basis": _get(row, "basis"),
        "source_text": _get(row, "source_text"),
        "source_page": _get(row, "source_page"),
        "confidence": _get(row, "confidence"),
    }


def metric_value_dict(row: sqlite3.Row) -> dict[str, Any]:
    code = _get(row, "metric_code")
    meta = metric_meta(code)
    calc = parse_json(_get(row, "calculation_data")) or {}
    return {
        "metric_code": code,
        "metric_name": meta.get("name") or code,
        "metric_value": _get(row, "metric_value"),
        "unit": meta.get("unit") or calc.get("unit"),
        "category": meta.get("category"),
        "period_start": _get(row, "period_start"),
        "period_end": _get(row, "period_end"),
        "calculation_data": calc,
    }


def signal_dict(row: sqlite3.Row, company: sqlite3.Row | None = None) -> dict[str, Any]:
    code = _get(row, "signal_type")
    meta = signal_meta(code)
    evidence = parse_json(_get(row, "evidence")) or {}
    return {
        "id": row["id"],
        "company_id": _get(row, "company_id"),
        "event_id": _get(row, "event_id"),
        "signal_type": code,
        "signal_name": meta.get("name") or _get(row, "title") or code,
        "title": _get(row, "title"),
        "description": _get(row, "description") or meta.get("description"),
        "direction": _get(row, "direction") or meta.get("direction"),
        "severity": _get(row, "severity") or meta.get("severity"),
        "category": evidence.get("category") or meta.get("category"),
        "confidence": _get(row, "confidence"),
        "evidence": evidence,
        "detected_at": _get(row, "detected_at"),
        "company": company_dict(company) if company is not None else None,
    }


def document_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "company_id": _get(row, "company_id"),
        "source_url": _get(row, "source_url"),
        "title": _get(row, "title"),
        "document_kind": _get(row, "document_kind"),
        "file_size": _get(row, "file_size"),
        "status": _get(row, "status"),
        "error_message": _get(row, "error_message"),
        "ingested_at": _get(row, "ingested_at"),
    }
