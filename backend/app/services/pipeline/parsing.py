"""Turn raw uploaded bytes into `DocumentPage` rows.

The downstream extraction stage reads from `DocumentPage.page_text`. Anything
that produces page-level text (PDF, plain text, markdown) is acceptable; the
existing demo seeder writes markdown to `page_markdown`, we keep the same
convention so the evidence viewer renders uploaded documents identically to
seeded ones.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from pypdf import PdfReader
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.events import DocumentPage, SourceDocument

logger = logging.getLogger(__name__)


@dataclass
class ParsedPage:
    page_number: int
    text: str  # plain text — fed to the LLM
    markdown: str  # display copy — rendered in the evidence viewer


def parse_document_bytes(data: bytes, *, content_type: str | None) -> list[ParsedPage]:
    """Dispatch to the right parser based on content type / magic bytes."""
    if _looks_like_pdf(data, content_type):
        return _parse_pdf(data)
    return _parse_text(data)


def persist_pages(db: Session, document: SourceDocument, pages: list[ParsedPage]) -> int:
    """Replace any existing pages for this document and insert the fresh batch.

    The pipeline is allowed to re-run on a failed document, so we wipe and
    re-insert rather than upsert page by page.
    """
    db.execute(delete(DocumentPage).where(DocumentPage.document_id == document.document_id))
    for p in pages:
        db.add(
            DocumentPage(
                document_id=document.document_id,
                page_number=p.page_number,
                page_text=p.text,
                page_markdown=p.markdown,
            )
        )
    document.page_count = len(pages)
    return len(pages)


def _looks_like_pdf(data: bytes, content_type: str | None) -> bool:
    if content_type and "pdf" in content_type.lower():
        return True
    return data[:5] == b"%PDF-"


def _parse_pdf(data: bytes) -> list[ParsedPage]:
    reader = PdfReader(io.BytesIO(data))
    out: list[ParsedPage] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # pypdf can throw on malformed pages
            logger.warning("pypdf failed on page %s: %s", i, exc)
            text = ""
        text = text.strip()
        out.append(
            ParsedPage(
                page_number=i,
                text=text,
                # `page_markdown` is what the evidence viewer renders. Plain
                # PDF text already round-trips reasonably as markdown.
                markdown=text or "*(no extractable text on this page)*",
            )
        )
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
        ParsedPage(page_number=i, text=c.strip(), markdown=c.strip())
        for i, c in enumerate(chunks, start=1)
    ]
