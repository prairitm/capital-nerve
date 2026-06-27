"""Event-type resolution from financial_result_flow.ipynb Step 3."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from typing import Any

import requests

from event_type_client import PAGE_URL
from event_type_db import bootstrap_schema
from nse_fr_resolver import infer_period_markers, resolve_canonical_financial_report


def company_id_for_symbol(symbol: str) -> str:
    return hashlib.sha256(f"{symbol}:NSE".encode()).hexdigest()


def event_id_from_source(company_id: str, source_url: str) -> str:
    return hashlib.sha256(f"{company_id}:{source_url}".encode()).hexdigest()


def _text_blob(item: dict[str, Any]) -> str:
    parts = [
        item.get("desc") or "",
        item.get("attchmntText") or "",
        item.get("attchmntFile") or "",
    ]
    return " ".join(parts).lower()


def classify_announcement(item: dict[str, Any]) -> str:
    desc = (item.get("desc") or "").strip()
    blob = _text_blob(item)

    def has(*phrases: str) -> bool:
        return any(phrase in blob for phrase in phrases)

    if has("transcript of the discussion", "earnings call transcript", "concall transcript"):
        return "Earnings Call Transcript"

    if desc == "Investor Presentation" or has("investor presentation"):
        return "Investor Presentation"

    intimation = has(
        "scheduled to be held",
        "audio recording",
        "will hold",
        "will be held",
        "informed the exchange regarding board meeting",
        "conference call",
        "prior intimation",
        "recording and transcript",
        "media release",
        "shareholder meeting",
    )
    if desc == "Financial Results" and not intimation:
        return "Financial Results"
    if has(
        "financial results",
        "unaudited financial",
        "audited financial",
        "outcome of board meeting",
    ) and not intimation:
        return "Financial Results"

    return "Other"


def _sort_key(item: dict[str, Any]) -> datetime:
    try:
        return datetime.strptime(item.get("sort_date", ""), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.min


def resolve_event_type(
    conn: sqlite3.Connection,
    *,
    session: requests.Session,
    symbol: str,
    from_date: str,
    to_date: str,
    company_id: str,
    announcements: list[dict[str, Any]],
    event_type: str = "Financial Results",
) -> dict[str, Any]:
    expected_company_id = company_id_for_symbol(symbol)
    if company_id != expected_company_id:
        raise ValueError("company_id does not match the NSE symbol-derived company id")

    bootstrap_schema(conn)
    for item in announcements:
        item["event_bucket"] = classify_announcement(item)

    financial_results = [
        item for item in announcements if item["event_bucket"] == "Financial Results"
    ]
    financial_results.sort(key=_sort_key, reverse=True)
    if not financial_results:
        raise LookupError(
            f"No '{event_type}' announcements found for {symbol} in {from_date} -> {to_date}"
        )

    period_markers = infer_period_markers(announcements)
    resolved_fr = resolve_canonical_financial_report(
        announcements,
        financial_results,
        period_markers=period_markers or None,
        session=session,
        referer=PAGE_URL,
    )
    if not resolved_fr:
        raise LookupError(
            f"No valid financial results PDF found for {symbol} in {from_date} -> {to_date}"
        )

    chosen = resolved_fr["announcement"]
    chosen_source_url = resolved_fr["url"]
    event_id = event_id_from_source(company_id, chosen_source_url)

    conn.execute(
        "UPDATE events SET event_type = ?, status = 'selected' WHERE id = ?",
        (event_type, event_id),
    )
    conn.commit()

    candidates = [
        {
            "sort_date": item.get("sort_date"),
            "source_url": item.get("attchmntFile"),
            "title": item.get("attchmntText"),
            "event_bucket": item["event_bucket"],
            "chosen": item is chosen,
        }
        for item in financial_results
    ]

    return {
        "company_id": company_id,
        "event_id": event_id,
        "chosen_source_url": chosen_source_url,
        "chosen_title": chosen.get("attchmntText"),
        "chosen_sort_date": chosen.get("sort_date"),
        "announcements_count": len(announcements),
        "financial_results_count": len(financial_results),
        "period_markers": period_markers,
        "classification": resolved_fr.get("classification") or {},
        "recovery_needed": bool(resolved_fr.get("recovery_needed")),
        "rejected_url": resolved_fr.get("rejected_url"),
        "candidates": candidates,
    }
