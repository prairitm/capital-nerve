"""Event-type resolution from financial_result_flow.ipynb Step 3."""

from __future__ import annotations

import hashlib
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from event_type_client import PAGE_URL
from event_type_db import bootstrap_schema
from nse_fr_resolver import (
    download_pdf,
    infer_period_markers,
    is_pdf_url,
    pdf_hash,
    resolve_canonical_financial_report,
)

DOCUMENT_TYPE_TO_EVENT_TYPE = {
    "financial_result": "Financial Results",
    "investor_presentation": "Investor Presentation",
    "earnings_call_transcript": "Earnings Call Transcript",
}
EVENT_TYPE_TO_DOCUMENT_TYPE = {
    value: key for key, value in DOCUMENT_TYPE_TO_EVENT_TYPE.items()
}
IR_AGENT_ASSET_BY_DOCUMENT_TYPE = {
    "financial_result": "financial_result",
    "investor_presentation": "investor_presentation",
    "earnings_call_transcript": "earnings_transcript",
}


def company_id_for_symbol(symbol: str) -> str:
    return hashlib.sha256(f"{symbol}:NSE".encode()).hexdigest()


def event_id_from_source(company_id: str, source_url: str) -> str:
    return hashlib.sha256(f"{company_id}:{source_url}".encode()).hexdigest()


def _parse_dmy_date(value: str) -> datetime:
    return datetime.strptime(value, "%d-%m-%Y")


def _to_iso_date(value: str) -> str:
    try:
        return _parse_dmy_date(value).date().isoformat()
    except ValueError:
        return value[:10]


def _legacy_document_request(event_type: str) -> dict[str, Any]:
    return {
        "document_type": EVENT_TYPE_TO_DOCUMENT_TYPE.get(event_type, "financial_result"),
        "source_mode": "nse_auto",
    }


def _event_type_for_document(document_type: str) -> str:
    if document_type not in DOCUMENT_TYPE_TO_EVENT_TYPE:
        raise ValueError(f"unsupported document_type: {document_type}")
    return DOCUMENT_TYPE_TO_EVENT_TYPE[document_type]


def _candidate_bucket(document_type: str) -> str:
    return _event_type_for_document(document_type)


def _persist_resolved_event(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
    event_type: str,
    event_date: str,
    title: str | None,
    source_url: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO events (
            id, company_id, event_type, event_date, title, source_url, status
        ) VALUES (?, ?, ?, ?, ?, ?, 'selected')
        ON CONFLICT(id) DO UPDATE SET
            event_type = excluded.event_type,
            event_date = COALESCE(excluded.event_date, events.event_date),
            title = COALESCE(excluded.title, events.title),
            source_url = COALESCE(excluded.source_url, events.source_url),
            status = 'selected'
        """,
        (event_id, company_id, event_type, event_date, title, source_url),
    )


def _load_ir_agent_finder():
    repo_root = Path(__file__).resolve().parents[3]
    ir_agent_root = repo_root / "IR_agent"
    if str(ir_agent_root) not in sys.path:
        sys.path.insert(0, str(ir_agent_root))
    from ir_agent import find_ir_assets

    return find_ir_assets


def _resolve_ir_agent_document(
    *,
    request: dict[str, Any],
    symbol: str,
    from_date: str,
    to_date: str,
) -> dict[str, Any]:
    company_url = request.get("company_url")
    if not company_url:
        raise ValueError("source_mode='ir_agent' requires company_url")
    find_ir_assets = _load_ir_agent_finder()
    result = find_ir_assets(
        company_url=company_url,
        company_name=request.get("company_name") or symbol,
        start_date=request.get("start_date") or _to_iso_date(from_date),
        end_date=request.get("end_date") or _to_iso_date(to_date),
        model=request.get("model"),
    )
    requested_asset_type = IR_AGENT_ASSET_BY_DOCUMENT_TYPE[request["document_type"]]
    matches = [
        match for match in result.matches
        if getattr(match, "asset_type", None) == requested_asset_type
    ]
    if not matches:
        raise LookupError(f"IR agent did not find {requested_asset_type} for {symbol}")
    selected = sorted(matches, key=lambda m: (m.published_or_period_date or "", m.confidence), reverse=True)[0]
    return {
        "source_url": selected.url,
        "title": selected.title,
        "sort_date": selected.published_or_period_date,
        "ir_agent_metadata": {
            "source_page": selected.source_page,
            "confidence": selected.confidence,
            "period_label": selected.period_label,
            "notes": selected.notes,
        },
    }


def _resolve_nse_document(
    *,
    session: requests.Session,
    announcements: list[dict[str, Any]],
    document_type: str,
) -> dict[str, Any]:
    bucket = _candidate_bucket(document_type)
    candidates = [item for item in announcements if item["event_bucket"] == bucket]
    candidates.sort(key=_sort_key, reverse=True)
    if not candidates:
        raise LookupError(f"No '{bucket}' announcements found")

    if document_type == "financial_result":
        period_markers = infer_period_markers(announcements)
        resolved = resolve_canonical_financial_report(
            announcements,
            candidates,
            period_markers=period_markers or None,
            session=session,
            referer=PAGE_URL,
        )
        if not resolved:
            raise LookupError("No valid financial results PDF found")
        chosen = resolved["announcement"]
        return {
            "source_url": resolved["url"],
            "title": chosen.get("attchmntText"),
            "sort_date": chosen.get("sort_date"),
            "classification": resolved.get("classification") or {},
            "recovery_needed": bool(resolved.get("recovery_needed")),
            "rejected_url": resolved.get("rejected_url"),
            "candidates": candidates,
        }

    attach_candidates = [
        item for item in candidates if (item.get("attchmntFile") or "").strip()
    ]
    if not attach_candidates:
        raise LookupError(f"No downloadable '{bucket}' announcement found")
    chosen = attach_candidates[0]
    source_url = (chosen.get("attchmntFile") or "").strip()
    classification_kind = {
        "investor_presentation": "INVESTOR_PRESENTATION",
        "earnings_call_transcript": "EARNINGS_CALL_TRANSCRIPT",
    }[document_type]
    classification = {
        "is_financial_report": False,
        "confidence": 1.0,
        "document_kind": classification_kind,
        "reasons": [f"selected from {bucket} announcement bucket"],
    }
    if is_pdf_url(source_url):
        try:
            pdf_bytes = download_pdf(source_url, session, referer=PAGE_URL)
            classification["pdf_hash"] = pdf_hash(pdf_bytes)
        except requests.RequestException:
            pass
    return {
        "source_url": source_url,
        "title": chosen.get("attchmntText"),
        "sort_date": chosen.get("sort_date"),
        "classification": classification,
        "recovery_needed": False,
        "rejected_url": None,
        "candidates": candidates,
    }


def _resolve_exact_nse_document(
    *,
    session: requests.Session,
    announcements: list[dict[str, Any]],
    document_type: str,
    source_url: str,
) -> dict[str, Any]:
    """Resolve one discovered announcement without selecting a newer filing."""
    exact = next(
        (
            item
            for item in announcements
            if (item.get("attchmntFile") or "").strip() == source_url
        ),
        None,
    )
    if exact is None:
        raise LookupError("The exact NSE announcement is no longer present in the requested window")

    if document_type == "financial_result":
        resolved = resolve_canonical_financial_report(
            announcements,
            [exact],
            period_markers=infer_period_markers(announcements) or None,
            session=session,
            referer=PAGE_URL,
        )
        if not resolved:
            raise LookupError("No valid financial results PDF found for the exact announcement")
        chosen = resolved["announcement"]
        return {
            "source_url": resolved["url"],
            "title": chosen.get("attchmntText"),
            "sort_date": chosen.get("sort_date"),
            "classification": resolved.get("classification") or {},
            "recovery_needed": bool(resolved.get("recovery_needed")),
            "rejected_url": resolved.get("rejected_url"),
            "candidates": [exact],
        }

    resolved = _resolve_nse_document(
        session=session,
        announcements=[exact],
        document_type=document_type,
    )
    resolved["candidates"] = [exact]
    return resolved


def _resolve_document_request(
    conn: sqlite3.Connection,
    *,
    session: requests.Session,
    symbol: str,
    from_date: str,
    to_date: str,
    company_id: str,
    announcements: list[dict[str, Any]],
    request: dict[str, Any],
) -> dict[str, Any]:
    document_type = request["document_type"]
    source_mode = request.get("source_mode") or "nse_auto"
    event_type = _event_type_for_document(document_type)
    resolved: dict[str, Any] = {
        "document_type": document_type,
        "event_type": event_type,
        "source_mode": source_mode,
        "catalog": request.get("catalog"),
        "classification": {},
    }
    if source_mode == "nse_auto":
        resolved.update(_resolve_nse_document(session=session, announcements=announcements, document_type=document_type))
    elif source_mode == "nse_exact":
        source_url = request.get("source_url")
        if not source_url:
            raise ValueError("source_mode='nse_exact' requires source_url")
        resolved.update(
            _resolve_exact_nse_document(
                session=session,
                announcements=announcements,
                document_type=document_type,
                source_url=source_url,
            )
        )
    elif source_mode == "manual_url":
        source_url = request.get("source_url")
        if not source_url:
            raise ValueError("source_mode='manual_url' requires source_url")
        resolved.update({"source_url": source_url, "title": request.get("title") or Path(source_url).name})
    elif source_mode == "local_file":
        local_path = request.get("local_path")
        if not local_path:
            raise ValueError("source_mode='local_file' requires local_path")
        resolved.update({"local_path": local_path, "source_url": local_path, "title": Path(local_path).name})
    elif source_mode == "ir_agent":
        resolved.update(_resolve_ir_agent_document(request=request, symbol=symbol, from_date=from_date, to_date=to_date))
    else:
        raise ValueError(f"unsupported source_mode: {source_mode}")

    source_seed = resolved.get("source_url") or resolved.get("local_path") or f"{document_type}:{source_mode}:{to_date}"
    event_id = event_id_from_source(company_id, source_seed)
    resolved["event_id"] = event_id
    event_date = str(resolved.get("sort_date") or _to_iso_date(to_date))[:10]
    _persist_resolved_event(
        conn,
        company_id=company_id,
        event_id=event_id,
        event_type=event_type,
        event_date=event_date,
        title=resolved.get("title"),
        source_url=resolved.get("source_url"),
    )
    return resolved


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

    if desc == "Investor Presentation" or has(
        "investor presentation",
        "presentation made by company",
        "presentation_with_ppt",
        "presentationwithppt",
    ):
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
    documents: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    expected_company_id = company_id_for_symbol(symbol)
    if company_id != expected_company_id:
        raise ValueError("company_id does not match the NSE symbol-derived company id")

    bootstrap_schema(conn)
    for item in announcements:
        item["event_bucket"] = classify_announcement(item)

    document_requests = documents or [_legacy_document_request(event_type)]
    resolved_documents: list[dict[str, Any]] = []
    errors: list[str] = []
    for request in document_requests:
        try:
            resolved_documents.append(
                _resolve_document_request(
                    conn,
                    session=session,
                    symbol=symbol,
                    from_date=from_date,
                    to_date=to_date,
                    company_id=company_id,
                    announcements=announcements,
                    request=request,
                )
            )
        except (LookupError, ValueError) as exc:
            errors.append(f"{request.get('document_type')}: {exc}")
    if not resolved_documents:
        raise LookupError("; ".join(errors) if errors else "No documents resolved")
    conn.commit()

    primary = resolved_documents[0]
    primary_type = primary["event_type"]
    financial_results = [
        item for item in announcements if item["event_bucket"] == "Financial Results"
    ]
    investor_presentations = [
        item for item in announcements if item["event_bucket"] == "Investor Presentation"
    ]
    earnings_transcripts = [
        item for item in announcements if item["event_bucket"] == "Earnings Call Transcript"
    ]
    candidates_by_type = {
        "Financial Results": financial_results,
        "Investor Presentation": investor_presentations,
        "Earnings Call Transcript": earnings_transcripts,
    }
    candidates_for_type = candidates_by_type.get(primary_type, financial_results)
    candidates_for_type.sort(key=_sort_key, reverse=True)
    period_markers = infer_period_markers(announcements)
    candidates = [
        {
            "sort_date": item.get("sort_date"),
            "source_url": item.get("attchmntFile"),
            "title": item.get("attchmntText"),
            "event_bucket": item["event_bucket"],
            "chosen": item.get("attchmntFile") == primary.get("source_url"),
        }
        for item in candidates_for_type
    ]

    return {
        "company_id": company_id,
        "event_id": primary["event_id"],
        "chosen_source_url": primary.get("source_url") or primary.get("local_path") or "",
        "chosen_title": primary.get("title"),
        "chosen_sort_date": primary.get("sort_date"),
        "announcements_count": len(announcements),
        "financial_results_count": len(candidates_for_type),
        "period_markers": period_markers,
        "classification": primary.get("classification") or {},
        "recovery_needed": bool(primary.get("recovery_needed")),
        "rejected_url": primary.get("rejected_url"),
        "candidates": candidates,
        "resolved_documents": resolved_documents,
        "errors": errors,
    }
