"""Ingest router — accepts uploads to disk; processing stays in the notebook."""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from ..config import settings
from ..deps import get_current_user
from ..state import User, store

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload(
    file: UploadFile = File(...),
    company_id: int | None = Form(default=None),
    document_type: str | None = Form(default=None),
    user: User = Depends(get_current_user),
) -> dict:
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    contents = await file.read()
    file_hash = hashlib.sha256(contents).hexdigest()
    dest = settings.uploads_dir / (file.filename or f"{file_hash}.pdf")
    dest.write_bytes(contents)

    job = store.add_ingest_job(
        {
            "document_id": 0,
            "company_id": company_id or 0,
            "company_name": "",
            "company_symbol": None,
            "document_title": file.filename or "upload",
            "document_type": document_type or "FINANCIAL_RESULT",
            "model_name": None,
            "started_at": None,
            "completed_at": None,
            "input_tokens": None,
            "output_tokens": None,
            "cost_usd": None,
            "extraction_confidence": None,
            "values_extracted": None,
            "cards_generated": None,
            "error_message": "Uploaded. Run the v2 notebook pipeline to process this filing.",
            "meta": {"stored_path": str(dest)},
        }
    )
    return {
        "queued": False,
        "event_id": 0,
        "document_id": 0,
        "job_id": job["job_id"],
        "review_id": 0,
        "file_hash": file_hash,
        "size_bytes": len(contents),
    }


@router.get("/jobs")
def list_jobs(
    limit: int = Query(default=30, ge=1, le=200),
    user: User = Depends(get_current_user),
) -> list[dict]:
    return list(reversed(store.ingest_jobs))[:limit]
