"""Tests for filing retrieval query compaction."""
from __future__ import annotations

from app.services.document_search import build_retrieval_query


def test_build_retrieval_query_strips_stopwords() -> None:
    q = "What is EPS basic of Reliance for quarter 3 FY 2022-23?"
    compact = build_retrieval_query(q)
    assert "eps" in compact.lower()
    assert "what" not in compact.lower()


def test_hybrid_finds_eps_reliance_keywords() -> None:
    compact = build_retrieval_query("What is EPS basic of Reliance for quarter 3 FY 2022-23?")
    assert "RELIANCE" in compact
    assert "eps" in compact.lower()
