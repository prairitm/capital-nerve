"""Tests for document search merge logic."""
from __future__ import annotations

from app.db.enums import DocumentType
from app.services.document_search import DocumentPageHit, _reciprocal_rank_fusion


def _hit(page_id: int, rank: float = 1.0) -> DocumentPageHit:
    return DocumentPageHit(
        page_id=page_id,
        document_id=page_id + 100,
        page_number=1,
        snippet=f"snippet-{page_id}",
        document_type=DocumentType.CONCALL_TRANSCRIPT,
        document_title=f"Doc {page_id}",
        company_id=1,
        company_name="Test Co",
        company_symbol="TEST",
        rank=rank,
        page_text=f"text-{page_id}",
    )


def test_rrf_prefers_pages_in_both_lists() -> None:
    fts = [_hit(1), _hit(2), _hit(3)]
    vector = [_hit(2), _hit(4)]
    merged = _reciprocal_rank_fusion(fts, vector, limit=3)
    page_ids = [h.page_id for h in merged]
    assert page_ids[0] == 2
    assert set(page_ids) == {2, 1, 4} or set(page_ids) == {2, 1, 3}


def test_rrf_respects_limit() -> None:
    fts = [_hit(i) for i in range(1, 6)]
    vector = [_hit(i) for i in range(6, 11)]
    merged = _reciprocal_rank_fusion(fts, vector, limit=4)
    assert len(merged) == 4
