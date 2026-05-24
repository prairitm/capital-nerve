"""Tests for RAG answer generation (mock path)."""
from __future__ import annotations

from app.services.pipeline.llm import RAGChunk, _mock_rag_answer


def test_mock_rag_answer_includes_citations_with_page_numbers() -> None:
    chunks = [
        RAGChunk(
            page_id=10,
            document_id=5,
            page_number=3,
            document_title="Q4 Concall",
            text="Management noted strong demand visibility in enterprise deals.",
        ),
        RAGChunk(
            page_id=11,
            document_id=5,
            page_number=4,
            document_title="Q4 Concall",
            text="Pricing power remained intact across key accounts.",
        ),
    ]
    result = _mock_rag_answer("What about demand?", chunks)
    assert "Q4 Concall" in result.answer
    assert len(result.citations) == 2
    assert result.citations[0].page_number == 3
    assert result.citations[0].document_id == 5
    assert "demand" in result.citations[0].quote.lower()


def test_mock_rag_answer_empty_chunks() -> None:
    result = _mock_rag_answer("anything", [])
    assert result.citations == []
    assert "No relevant passages" in result.answer
