"""Persistence helpers for PDF documents and NSE ingestion."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

from config import settings
from db import connect, init_db


def company_id_from_announcement(announcement: dict[str, Any]) -> str:
    isin = (announcement.get("sm_isin") or "").strip()
    if isin:
        return hashlib.sha256(isin.encode()).hexdigest()
    symbol = (announcement.get("symbol") or "").strip()
    return hashlib.sha256(f"{symbol}:NSE".encode()).hexdigest()


def event_id_from_source(company_id: str, source_url: str) -> str:
    return hashlib.sha256(f"{company_id}:{source_url}".encode()).hexdigest()


def save_pdf_file(pdf_bytes: bytes, sha256: str) -> tuple[Path, bool]:
    """Write PDF to documents dir. Returns (path, already_existed)."""
    settings.documents_dir.mkdir(parents=True, exist_ok=True)
    path = settings.documents_dir / f"{sha256}.pdf"
    if path.exists():
        return path, True
    path.write_bytes(pdf_bytes)
    return path, False


def upsert_company(conn: sqlite3.Connection, announcement: dict[str, Any]) -> str:
    company_id = company_id_from_announcement(announcement)
    conn.execute(
        """
        INSERT INTO companies (id, name, ticker, exchange, industry, isin)
        VALUES (?, ?, ?, 'NSE', ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            ticker = excluded.ticker,
            industry = excluded.industry,
            isin = excluded.isin
        """,
        (
            company_id,
            announcement.get("sm_name") or announcement.get("symbol") or "Unknown",
            announcement.get("symbol"),
            announcement.get("smIndustry"),
            announcement.get("sm_isin"),
        ),
    )
    return company_id


def insert_document(
    conn: sqlite3.Connection,
    *,
    document_id: str,
    company_id: str,
    source_url: str | None,
    storage_path: str,
    sha256: str,
    title: str | None,
    document_kind: str | None,
    file_size: int,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO documents (
            id, company_id, source_url, storage_path, sha256,
            title, document_kind, file_size, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """,
        (
            document_id,
            company_id,
            source_url,
            storage_path,
            sha256,
            title,
            document_kind,
            file_size,
        ),
    )


def insert_event(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    company_id: str,
    event_type: str,
    event_date: str,
    title: str | None,
    source_url: str | None,
    document_id: str,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO events (
            id, company_id, event_type, event_date,
            title, source_url, document_id, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'ingested')
        """,
        (
            event_id,
            company_id,
            event_type,
            event_date,
            title,
            source_url,
            document_id,
        ),
    )


def save_resolved_financial_pdf(resolved: dict[str, Any], pdf_bytes: bytes) -> dict[str, Any]:
    """Persist a resolved NSE financial report PDF and metadata."""
    init_db()
    announcement = resolved["announcement"]
    url = resolved["url"]
    digest = resolved["pdf_hash"]
    classification = resolved.get("classification") or {}

    storage_path, file_existed = save_pdf_file(pdf_bytes, digest)
    company_id = company_id_from_announcement(announcement)
    event_id = event_id_from_source(company_id, url)

    with connect() as conn:
        upsert_company(conn, announcement)
        insert_document(
            conn,
            document_id=digest,
            company_id=company_id,
            source_url=url,
            storage_path=str(storage_path),
            sha256=digest,
            title=announcement.get("attchmntText") or announcement.get("desc"),
            document_kind=classification.get("document_kind"),
            file_size=len(pdf_bytes),
        )
        insert_event(
            conn,
            event_id=event_id,
            company_id=company_id,
            event_type=announcement.get("event_bucket") or "Financial Results",
            event_date=(announcement.get("sort_date") or "")[:10],
            title=announcement.get("attchmntText"),
            source_url=url,
            document_id=digest,
        )
        conn.commit()

    result = {
        "company_id": company_id,
        "document_id": digest,
        "event_id": event_id,
        "storage_path": str(storage_path),
        "already_existed": file_existed,
    }
    result["processing"] = _run_processing(digest)
    return result


def _run_processing(document_id: str) -> dict:
    try:
        from pipeline.runner import process_document

        return process_document(document_id)
    except Exception as exc:
        with connect() as conn:
            from pipeline.persist import set_document_status

            set_document_status(conn, document_id, "failed", error_message=str(exc))
            conn.commit()
        return {"success": False, "document_id": document_id, "error": str(exc)}


def ingest_pdf_bytes(
    pdf_bytes: bytes,
    *,
    company_id: str | None = None,
    source_url: str | None = None,
    title: str | None = None,
    document_kind: str | None = None,
) -> dict[str, Any]:
    """Ingest raw PDF bytes (API upload path)."""
    init_db()
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    storage_path, already_existed = save_pdf_file(pdf_bytes, digest)

    if company_id:
        with connect() as conn:
            insert_document(
                conn,
                document_id=digest,
                company_id=company_id,
                source_url=source_url,
                storage_path=str(storage_path),
                sha256=digest,
                title=title,
                document_kind=document_kind,
                file_size=len(pdf_bytes),
            )
            conn.commit()

    return {
        "sha256": digest,
        "document_id": digest,
        "storage_path": str(storage_path),
        "size": len(pdf_bytes),
        "already_existed": already_existed,
    }
