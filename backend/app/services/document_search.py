"""Read-side full-text and vector search over document pages."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.pgvector_cap import pgvector_ready
from app.db.enums import DocumentType
from app.models.events import DocumentPage, DocumentPageEmbedding, SourceDocument
from app.models.master import Company
from app.services.embeddings import get_embedding_provider


@dataclass(frozen=True)
class DocumentPageHit:
    page_id: int
    document_id: int
    page_number: int
    snippet: str
    document_type: DocumentType
    document_title: str
    company_id: int
    company_name: str
    company_symbol: str | None
    rank: float
    page_text: str


def _base_join():
    return (
        select(
            DocumentPage.page_id,
            DocumentPage.document_id,
            DocumentPage.page_number,
            DocumentPage.page_text,
            SourceDocument.document_type,
            SourceDocument.document_title,
            SourceDocument.company_id,
            Company.company_name,
            Company.nse_symbol,
            Company.bse_code,
        )
        .join(SourceDocument, SourceDocument.document_id == DocumentPage.document_id)
        .join(Company, Company.company_id == SourceDocument.company_id)
    )


def _apply_filters(
    stmt,
    *,
    company_id: int | None,
    event_id: int | None,
    document_type: DocumentType | None,
):
    if company_id is not None:
        stmt = stmt.where(SourceDocument.company_id == company_id)
    if event_id is not None:
        stmt = stmt.where(SourceDocument.event_id == event_id)
    if document_type is not None:
        stmt = stmt.where(SourceDocument.document_type == document_type)
    return stmt


def search_pages_fts(
    db: Session,
    q: str,
    *,
    company_id: int | None = None,
    event_id: int | None = None,
    document_type: DocumentType | None = None,
    limit: int = 15,
) -> list[DocumentPageHit]:
    ts_query = func.plainto_tsquery("english", q)
    rank_expr = func.ts_rank(DocumentPage.search_vector, ts_query)
    snippet_expr = func.ts_headline(
        "english",
        func.coalesce(DocumentPage.page_text, ""),
        ts_query,
        "MaxFragments=2, MaxWords=35, MinWords=8",
    )
    stmt = (
        _base_join()
        .add_columns(rank_expr.label("rank"), snippet_expr.label("snippet"))
        .where(DocumentPage.search_vector.op("@@")(ts_query))
        .order_by(rank_expr.desc(), DocumentPage.page_number.asc())
        .limit(limit)
    )
    stmt = _apply_filters(
        stmt, company_id=company_id, event_id=event_id, document_type=document_type
    )
    rows = db.execute(stmt).all()
    return [_row_to_hit(row) for row in rows]


def search_pages_vector(
    db: Session,
    query_embedding: list[float],
    *,
    company_id: int | None = None,
    event_id: int | None = None,
    document_type: DocumentType | None = None,
    limit: int = 15,
) -> list[DocumentPageHit]:
    if not pgvector_ready(db):
        return []
    distance = DocumentPageEmbedding.embedding.cosine_distance(query_embedding)
    stmt = (
        _base_join()
        .join(DocumentPageEmbedding, DocumentPageEmbedding.page_id == DocumentPage.page_id)
        .add_columns((1.0 - distance).label("rank"))
        .add_columns(
            func.left(func.coalesce(DocumentPage.page_text, ""), 280).label("snippet")
        )
        .order_by(distance.asc())
        .limit(limit)
    )
    stmt = _apply_filters(
        stmt, company_id=company_id, event_id=event_id, document_type=document_type
    )
    rows = db.execute(stmt).all()
    return [_row_to_hit(row) for row in rows]


def hybrid_search_pages(
    db: Session,
    q: str,
    *,
    company_id: int | None = None,
    event_id: int | None = None,
    document_type: DocumentType | None = None,
    limit: int = 8,
) -> tuple[list[DocumentPageHit], str]:
    fts_hits = search_pages_fts(
        db,
        q,
        company_id=company_id,
        event_id=event_id,
        document_type=document_type,
        limit=limit * 2,
    )

    vector_hits: list[DocumentPageHit] = []
    provider = get_embedding_provider()
    if provider.is_available and pgvector_ready(db):
        try:
            query_vec = provider.embed_texts([q])[0]
            vector_hits = search_pages_vector(
                db,
                query_vec,
                company_id=company_id,
                event_id=event_id,
                document_type=document_type,
                limit=limit * 2,
            )
        except Exception:
            vector_hits = []

    if not vector_hits:
        return fts_hits[:limit], "fts_only"

    merged = _reciprocal_rank_fusion(fts_hits, vector_hits, limit=limit)
    return merged, "hybrid"


def _reciprocal_rank_fusion(
    fts_hits: list[DocumentPageHit],
    vector_hits: list[DocumentPageHit],
    *,
    limit: int,
    k: int = 60,
) -> list[DocumentPageHit]:
    by_page: dict[int, DocumentPageHit] = {}
    scores: dict[int, float] = {}

    for rank, hit in enumerate(fts_hits):
        by_page.setdefault(hit.page_id, hit)
        scores[hit.page_id] = scores.get(hit.page_id, 0.0) + 1.0 / (k + rank + 1)
    for rank, hit in enumerate(vector_hits):
        by_page.setdefault(hit.page_id, hit)
        scores[hit.page_id] = scores.get(hit.page_id, 0.0) + 1.0 / (k + rank + 1)

    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
    out: list[DocumentPageHit] = []
    for page_id, score in ordered:
        hit = by_page[page_id]
        out.append(
            DocumentPageHit(
                page_id=hit.page_id,
                document_id=hit.document_id,
                page_number=hit.page_number,
                snippet=hit.snippet,
                document_type=hit.document_type,
                document_title=hit.document_title,
                company_id=hit.company_id,
                company_name=hit.company_name,
                company_symbol=hit.company_symbol,
                rank=score,
                page_text=hit.page_text,
            )
        )
    return out


def _row_to_hit(row) -> DocumentPageHit:
    symbol = row.nse_symbol or row.bse_code
    page_text = row.page_text or ""
    snippet = getattr(row, "snippet", None) or page_text[:280]
    return DocumentPageHit(
        page_id=row.page_id,
        document_id=row.document_id,
        page_number=row.page_number,
        snippet=snippet,
        document_type=row.document_type,
        document_title=row.document_title,
        company_id=row.company_id,
        company_name=row.company_name,
        company_symbol=symbol,
        rank=float(getattr(row, "rank", 0.0) or 0.0),
        page_text=page_text,
    )
