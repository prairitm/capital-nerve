"""RAG Q&A over ingested document pages with mandatory citations."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.document_search import DocumentPageHit, build_retrieval_query, hybrid_search_pages
from app.services.pipeline.llm import RAGAnswerResult, RAGChunk, RAGCitation, answer_from_context


@dataclass(frozen=True)
class AskResult:
    answer: str
    citations: list[RAGCitation]
    retrieval_mode: str


def ask(
    db: Session,
    q: str,
    *,
    company_id: int | None = None,
    event_id: int | None = None,
) -> AskResult:
    hits, retrieval_mode = hybrid_search_pages(
        db,
        q,
        company_id=company_id,
        event_id=event_id,
        limit=settings.RAG_TOP_K,
    )
    if not hits:
        compact = build_retrieval_query(q)
        hint = (
            f" No filing pages matched{' (even with keywords: ' + compact + ')' if compact != q else ''}."
            " Upload and process concall / result PDFs for this company, or ask a metric question"
            " (e.g. EPS, revenue for a quarter) to query structured facts instead."
        )
        return AskResult(
            answer="No relevant passages found in the indexed filings." + hint,
            citations=[],
            retrieval_mode=retrieval_mode,
        )

    chunks = [_hit_to_chunk(hit) for hit in hits]
    result: RAGAnswerResult = answer_from_context(question=q, chunks=chunks)
    return AskResult(
        answer=result.answer,
        citations=result.citations,
        retrieval_mode=retrieval_mode,
    )


def _hit_to_chunk(hit: DocumentPageHit) -> RAGChunk:
    return RAGChunk(
        page_id=hit.page_id,
        document_id=hit.document_id,
        page_number=hit.page_number,
        document_title=hit.document_title,
        text=hit.page_text,
    )
