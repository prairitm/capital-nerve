"""Tests for natural-language data ask (SQL validation + mock generation)."""
from __future__ import annotations

import pytest

from app.services.data_ask import (
    DataAskError,
    _extract_period_label,
    _mock_generate_sql,
    validate_and_cap_sql,
)


def test_validate_sql_accepts_select_with_limit() -> None:
    sql = "SELECT 1 AS n LIMIT 10"
    assert "LIMIT" in validate_and_cap_sql(sql)


def test_validate_sql_appends_limit_when_missing() -> None:
    sql = "SELECT company_id FROM companies"
    capped = validate_and_cap_sql(sql)
    assert capped.rstrip().endswith("LIMIT 100")


def test_validate_sql_rejects_delete() -> None:
    with pytest.raises(DataAskError, match="read-only"):
        validate_and_cap_sql("DELETE FROM companies")


def test_validate_sql_rejects_multi_statement() -> None:
    with pytest.raises(DataAskError, match="single"):
        validate_and_cap_sql("SELECT 1; SELECT 2")


def test_validate_sql_rejects_comments() -> None:
    with pytest.raises(DataAskError, match="comments"):
        validate_and_cap_sql("SELECT 1 -- sneaky")


def test_mock_sql_reliance_eps_q3_fy2022_23() -> None:
    q = "What is EPS basic of Reliance for quarter 3 FY 2022-23?"
    sql = _mock_generate_sql(q)
    assert "RELIANCE" in sql
    assert "eps_basic" in sql
    assert "Q3 FY2022-23" in sql
    assert "financial_statement_facts" in sql
    validate_and_cap_sql(sql)


def test_extract_period_label_variants() -> None:
    assert _extract_period_label("Q3 FY 2022-23") == "Q3 FY2022-23"
    assert _extract_period_label("quarter 3 fy 2022-23") == "Q3 FY2022-23"
