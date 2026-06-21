"""Tests for unified ask routing."""
from __future__ import annotations

from app.services.unified_ask import classify_route


def test_route_eps_question_to_sql() -> None:
    assert (
        classify_route("What is EPS basic of Reliance for quarter 3 FY 2022-23?")
        == "sql"
    )


def test_route_management_question_to_rag() -> None:
    assert (
        classify_route("What did management say about demand on the last concall?")
        == "rag"
    )


def test_route_ambiguous_defaults_to_rag() -> None:
    assert classify_route("Tell me about Reliance") == "rag"
