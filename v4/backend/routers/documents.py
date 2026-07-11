"""Document metadata + PDF file serving over the 7-step DB."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from config import REPO_ROOT, settings
from db import get_conn
from queries import uses_eight_step_metrics
from serializers import company_dict, document_dict, event_dict
from source_locate import locate_source

router = APIRouter(tags=["documents"])


def _parsed_md_path(document_id: str) -> Path:
    primary = settings.parsed_dir / f"{document_id}.md"
    if primary.exists():
        return primary
    legacy_v4 = REPO_ROOT / "v4" / "data" / "parsed" / f"{document_id}.md"
    if legacy_v4.exists():
        return legacy_v4
    return primary


def _counts(conn, event_id: str | None) -> dict[str, int]:
    if not event_id:
        return {"extracted_values": 0, "metric_values": 0, "signals": 0}
    metric_count_sql = (
        "SELECT COUNT(*) AS c FROM metrics WHERE event_id = ?"
        if uses_eight_step_metrics(conn)
        else "SELECT COUNT(*) AS c FROM metric_values WHERE event_id = ?"
    )
    return {
        "extracted_values": conn.execute(
            "SELECT COUNT(*) AS c FROM extracted_values WHERE event_id = ?", (event_id,)
        ).fetchone()["c"],
        "metric_values": conn.execute(metric_count_sql, (event_id,)).fetchone()["c"],
        "signals": conn.execute(
            "SELECT COUNT(*) AS c FROM signals WHERE event_id = ?", (event_id,)
        ).fetchone()["c"],
    }


@router.get("/documents/{document_id}")
def document_detail(document_id: str):
    with get_conn() as conn:
        doc = conn.execute(
            "SELECT * FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        company = conn.execute(
            "SELECT * FROM companies WHERE id = ?", (doc["company_id"],)
        ).fetchone()
        event = conn.execute(
            "SELECT * FROM events WHERE document_id = ? ORDER BY event_date DESC LIMIT 1",
            (document_id,),
        ).fetchone()

        return {
            "document": document_dict(doc),
            "company": company_dict(company) if company else None,
            "event": event_dict(event) if event else None,
            "counts": _counts(conn, event["id"] if event else None),
        }


@router.get("/documents/{document_id}/locate")
def document_locate(
    document_id: str,
    text: str,
    page: int | None = None,
    value: str | None = None,
    context: str | None = None,
):
    if not text.strip():
        raise HTTPException(status_code=400, detail="text query parameter is required")
    preferred_page = page if page is not None and page > 0 else None
    with get_conn() as conn:
        doc = conn.execute(
            "SELECT storage_path FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        pdf_path = Path(doc["storage_path"])
        parsed_md_path = _parsed_md_path(document_id)
        return locate_source(
            parsed_md_path=parsed_md_path,
            pdf_path=pdf_path,
            source_text=text,
            target_value=value,
            context=context,
            preferred_page=preferred_page,
        )


@router.get("/documents/{document_id}/file")
def document_file(document_id: str):
    with get_conn() as conn:
        doc = conn.execute(
            "SELECT storage_path, title FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        path = Path(doc["storage_path"])
        if not path.exists():
            raise HTTPException(status_code=404, detail="PDF file not found on disk")
        return FileResponse(
            str(path),
            media_type="application/pdf",
            filename=f"{(doc['title'] or document_id)}.pdf",
        )
