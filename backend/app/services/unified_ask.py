"""Unified natural-language ask — routes to SQL (facts) or RAG (filings)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.data_ask import (
    DataAskError,
    DataAskResult,
    _execute_sql,
    _format_answer,
    _mock_generate_sql,
    ask_data,
    validate_and_cap_sql,
)
from app.services.document_rag import ask as rag_ask
from app.services.pipeline.llm import RAGCitation

logger = logging.getLogger(__name__)

AskMode = Literal["sql", "rag"]

_SQL_SIGNALS: tuple[tuple[str, int], ...] = (
    (r"\beps\b", 3),
    (r"\bpat\b", 2),
    (r"\bebitda\b", 2),
    (r"\brevenue\b", 2),
    (r"\bmargin\b", 2),
    (r"\bnet\s+profit\b", 2),
    (r"\bfinancial\s+fact", 3),
    (r"\bline\s+item\b", 2),
    (r"\bmetric\b", 2),
    (r"\bhow\s+much\b", 2),
    (r"\bwhat\s+was\b", 2),
    (r"\bwhat\s+is\b", 1),
    (r"\bvalue\s+of\b", 2),
    (r"\bcrore\b", 2),
    (r"\brs\.?\b", 1),
    (r"\bquarter\b", 2),
    (r"\bq[1-4]\b", 2),
    (r"\bfy\s*20\d{2}", 2),
    (r"\byoy\b", 2),
    (r"\bgrowth\s+rate\b", 2),
    (r"\broe\b", 2),
    (r"\bdebt\b", 1),
    (r"\bassets\b", 1),
    (r"\bsignal\b", 1),
    (r"\bintelligence\s+card", 1),
    (r"\bcalculated\s+metric", 3),
    (r"\bcompare\b.*\bquarter", 2),
    (r"\btrend\b", 1),
    (r"\bdatabase\b", 3),
    (r"\bingested\b", 2),
)

_RAG_SIGNALS: tuple[tuple[str, int], ...] = (
    (r"\bmanagement\b", 3),
    (r"\bsaid\b", 2),
    (r"\bconcall\b", 3),
    (r"\btranscript\b", 3),
    (r"\bcommentary\b", 2),
    (r"\boutlook\b", 2),
    (r"\bguidance\b", 2),
    (r"\bwhy\b", 2),
    (r"\baccording\s+to\b", 2),
    (r"\bmention", 2),
    (r"\bspeaker\b", 2),
    (r"\banalyst\b", 1),
    (r"\border\s+book\b", 2),
    (r"\bpricing\s+power\b", 2),
    (r"\bdemand\s+visibility\b", 3),
    (r"\binvestor\s+presentation\b", 2),
    (r"\bfiling\b", 1),
    (r"\bpassage\b", 2),
    (r"\bquote\b", 2),
    (r"\bsay\s+about\b", 2),
    (r"\btalked\s+about\b", 2),
    (r"\bexplained\b", 2),
    (r"\bremarks\b", 2),
)


@dataclass(frozen=True)
class UnifiedAskResult:
    answer: str
    mode: AskMode
    citations: list[RAGCitation] = field(default_factory=list)
    retrieval_mode: str | None = None
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    row_count: int = 0


def classify_route(question: str) -> AskMode:
    """Pick SQL (structured facts) vs RAG (filing passages)."""
    q = question.lower()
    sql_score = sum(weight for pat, weight in _SQL_SIGNALS if re.search(pat, q))
    rag_score = sum(weight for pat, weight in _RAG_SIGNALS if re.search(pat, q))

    has_period = bool(
        re.search(r"q\s*[1-4]|quarter\s*[1-4]|fy\s*20\d{2}", q, re.IGNORECASE)
    )
    has_metric = bool(
        re.search(
            r"\beps\b|\bpat\b|\bebitda\b|\brevenue\b|\bmargin\b|\bprofit\b|\bmetric\b",
            q,
            re.IGNORECASE,
        )
    )

    if sql_score > rag_score + 1:
        return "sql"
    if rag_score > sql_score + 1:
        return "rag"
    if has_period and has_metric:
        return "sql"
    if rag_score > 0:
        return "rag"
    if sql_score > 0:
        return "sql"
    return "rag"


def ask_unified(
    db: Session,
    question: str,
    *,
    company_id: int | None = None,
    event_id: int | None = None,
) -> UnifiedAskResult:
    q = (question or "").strip()
    if not q:
        raise DataAskError("Question cannot be empty.")

    mode = classify_route(q)
    if mode == "sql":
        return _ask_sql_or_fallback(db, q, company_id=company_id, event_id=event_id)
    return _ask_rag(db, q, company_id=company_id, event_id=event_id)


def _ask_sql_or_fallback(
    db: Session,
    question: str,
    *,
    company_id: int | None,
    event_id: int | None,
) -> UnifiedAskResult:
    try:
        data = ask_data(db, question)
    except DataAskError:
        raise
    except Exception as exc:
        logger.warning("unified_ask SQL path failed: %s", exc)
        data = _try_mock_sql(db, question)
        if data is None:
            raise DataAskError(
                "Could not query structured financial facts. Try rephrasing with company symbol,"
                " metric (EPS, revenue, PAT), and quarter (e.g. Q3 FY 2022-23)."
            ) from exc

    if data.row_count > 0:
        return UnifiedAskResult(
            answer=data.answer,
            mode="sql",
            sql=data.sql,
            columns=data.columns,
            rows=data.rows,
            row_count=data.row_count,
        )

    # Metric-style questions: return the SQL empty result instead of useless RAG fallback.
    return UnifiedAskResult(
        answer=data.answer,
        mode="sql",
        sql=data.sql,
        columns=data.columns,
        rows=data.rows,
        row_count=0,
    )


def _try_mock_sql(db: Session, question: str):
    """Last-resort SQL when the LLM provider errors (dev / transient failures)."""
    if settings.is_production:
        return None
    try:
        sql = validate_and_cap_sql(_mock_generate_sql(question))
        columns, rows = _execute_sql(db, sql)
        answer = _format_answer(question, "Fallback query after LLM error.", columns, rows)
        return DataAskResult(
            answer=answer,
            sql=sql,
            columns=columns,
            rows=rows,
            row_count=len(rows),
        )
    except Exception:
        logger.exception("mock SQL fallback also failed")
        return None


def _ask_rag(
    db: Session,
    question: str,
    *,
    company_id: int | None,
    event_id: int | None,
    prefix: str = "",
) -> UnifiedAskResult:
    result = rag_ask(db, question, company_id=company_id, event_id=event_id)
    answer = f"{prefix}{result.answer}" if prefix else result.answer
    return UnifiedAskResult(
        answer=answer,
        mode="rag",
        citations=result.citations,
        retrieval_mode=result.retrieval_mode,
    )
