"""Turn raw uploaded bytes into `DocumentPage` rows.

The downstream extraction stage reads from `DocumentPage.page_text` for FTS /
evidence and from `DocumentPage.image_path` for the LLM vision call. We render
each PDF page to a PNG once at parse time so the extraction stage can hand the
provider stable, layout-preserving images instead of pypdf's variable text
dumps (which were the dominant source of run-to-run extraction drift).
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from pypdf import PdfReader
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.events import DocumentPage, SourceDocument
from app.services.pipeline.storage import get_storage

logger = logging.getLogger(__name__)


# Bumped whenever the parse output (text shape or image rendering) changes in
# a way that should invalidate the extraction cache on ``extraction_jobs``.
PARSER_VERSION = "parsing.v2"

# DPI for rendered page PNGs. 200 keeps row labels readable on dense Indian
# quarterly-result tables while staying under a few MB per page.
_PAGE_IMAGE_DPI = 200


@dataclass
class ParsedPage:
    page_number: int
    text: str  # plain text — also fed to FTS / RAG
    markdown: str  # display copy — rendered in the evidence viewer
    image_bytes: bytes | None = None  # PNG; persisted to storage by persist_pages


def parse_document_bytes(data: bytes, *, content_type: str | None) -> list[ParsedPage]:
    """Dispatch to the right parser based on content type / magic bytes."""
    if _looks_like_pdf(data, content_type):
        return _parse_pdf(data)
    return _parse_text(data)


def persist_pages(db: Session, document: SourceDocument, pages: list[ParsedPage]) -> int:
    """Replace any existing pages for this document and insert the fresh batch.

    The pipeline is allowed to re-run on a failed document, so we wipe and
    re-insert rather than upsert page by page.

    ``SessionLocal`` uses ``autoflush=False``, so we must flush the DELETE
    before INSERTing the new batch — otherwise two concurrent pipeline runs
    (e.g. bulk_ingest inline + the in-process worker) can both INSERT and hit
    ``uq_document_pages``. We also expire the identity map so stale
    ``DocumentPage`` rows from a prior load cannot confuse the unit of work.
    """
    doc_id = document.document_id
    db.execute(
        delete(DocumentPage)
        .where(DocumentPage.document_id == doc_id)
        .execution_options(synchronize_session=False)
    )
    db.flush()
    db.expire_all()
    storage = get_storage()
    for p in pages:
        image_path: str | None = None
        if p.image_bytes:
            stored = storage.put_bytes_at(
                p.image_bytes,
                path=f"page_images/{doc_id}/{p.page_number:04d}.png",
            )
            image_path = stored.storage_path
        db.add(
            DocumentPage(
                document_id=doc_id,
                page_number=p.page_number,
                page_text=p.text,
                page_markdown=p.markdown,
                image_path=image_path,
            )
        )
    document.page_count = len(pages)
    db.flush()
    return len(pages)


def _looks_like_pdf(data: bytes, content_type: str | None) -> bool:
    if content_type and "pdf" in content_type.lower():
        return True
    return data[:5] == b"%PDF-"


def _parse_pdf(data: bytes) -> list[ParsedPage]:
    reader = PdfReader(io.BytesIO(data))
    text_pages: list[str] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # pypdf can throw on malformed pages
            logger.warning("pypdf failed on page %s: %s", i, exc)
            text = ""
        text_pages.append(text.strip())

    images = _render_pdf_pages_to_png(data, page_count=len(text_pages))

    out: list[ParsedPage] = []
    for i, text in enumerate(text_pages, start=1):
        out.append(
            ParsedPage(
                page_number=i,
                text=text,
                # ``page_markdown`` is what the evidence viewer renders. Plain
                # PDF text already round-trips reasonably as markdown.
                markdown=text or "*(no extractable text on this page)*",
                image_bytes=images[i - 1] if i - 1 < len(images) else None,
            )
        )
    return out


def _render_pdf_pages_to_png(data: bytes, *, page_count: int) -> list[bytes]:
    """Render every PDF page to a PNG using poppler via ``pdf2image``.

    Returns one PNG byte-string per page in 1-based order. If poppler is not
    installed on the host the call raises ``pdf2image.exceptions.PDFInfoNotInstalledError``;
    we log and return an empty list so the pipeline degrades to the text-only
    path instead of crashing.
    """
    if page_count == 0:
        return []
    try:
        from pdf2image import convert_from_bytes  # lazy import — heavy dep
    except ImportError:
        logger.warning("pdf2image is not installed; page-image rendering disabled.")
        return []
    try:
        pil_pages = convert_from_bytes(data, dpi=_PAGE_IMAGE_DPI, fmt="png")
    except Exception as exc:
        # Most commonly poppler-utils is missing on the host.
        logger.warning("pdf2image rendering failed (poppler missing?): %s", exc)
        return []
    out: list[bytes] = []
    for pil in pil_pages:
        buf = io.BytesIO()
        pil.save(buf, format="PNG", optimize=True)
        out.append(buf.getvalue())
    return out


def _parse_text(data: bytes) -> list[ParsedPage]:
    """Plain-text fallback: split on form-feeds first, then double newlines."""
    raw = data.decode("utf-8", errors="replace")
    # Form-feed is the conventional page break in text dumps of PDFs.
    if "\f" in raw:
        chunks = [c for c in raw.split("\f") if c.strip()]
    else:
        # Otherwise treat the whole document as one logical page so the
        # downstream stages still get something to chew on.
        chunks = [raw]
    return [
        ParsedPage(page_number=i, text=c.strip(), markdown=c.strip(), image_bytes=None)
        for i, c in enumerate(chunks, start=1)
    ]
