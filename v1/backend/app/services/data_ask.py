"""Natural-language queries over ingested financial facts (read-only SQL)."""
from __future__ import annotations

import enum
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.pipeline.llm import AnthropicProvider, MockProvider, OpenAIProvider, get_provider

logger = logging.getLogger(__name__)

DATA_ASK_MAX_ROWS = 100
_DATA_ASK_MAX_SQL_CHARS = 12_000

_FORBIDDEN_SQL = re.compile(
    r"\b("
    r"insert|update|delete|drop|truncate|alter|create|grant|revoke|"
    r"copy|execute|call|merge|replace|attach|detach|pragma|vacuum|"
    r"into\s+outfile|load\s+data"
    r")\b",
    re.IGNORECASE,
)

_SCHEMA_CONTEXT = """
Tables (PostgreSQL):

companies(company_id PK, company_name, nse_symbol UNIQUE, bse_code, isin, sector_id)
financial_periods(period_id PK, fy_year INT, fy_label TEXT, quarter INT nullable, period_type enum,
  period_start_date, period_end_date, display_label UNIQUE-ish)
  -- Quarterly label format: display_label = 'Q{n} FY{start}-{end2}' e.g. 'Q3 FY2022-23'
  -- fy_label = 'FY2022-23' when fy_year=2022; quarter=1..4 for quarterly periods
financial_line_item_definitions(line_item_def_id PK, normalized_code UNIQUE, display_name, statement_type)
  -- Key codes: eps_basic, pat, ebitda, revenue_from_operations, total_assets, ...
financial_statement_facts(fact_id PK, company_id, period_id, line_item_def_id, value NUMERIC,
  unit, consolidation enum STANDALONE|CONSOLIDATED, period_value_type TEXT default 'CURRENT',
  source_extracted_value_id, document_id)
  -- Default filters for quarterly metrics: period_value_type='CURRENT', consolidation='CONSOLIDATED'
extracted_values(extracted_value_id PK, company_id, period_id, normalized_label, numeric_value, unit,
  raw_label, page_number, source_text, document_id)
calculated_metrics(metric_id PK, company_id, period_id, metric_definition_id, value, unit)
metric_definitions(metric_definition_id PK, metric_code UNIQUE, display_name, unit)
generated_signals(signal_id PK, company_id, period_id, signal_definition_id, ...)
intelligence_cards(card_id PK, company_id, period_id, headline, card_type, ...)
source_documents(document_id PK, company_id, period_id, document_type, document_title)
company_events(event_id PK, company_id, period_id, event_type, event_title, event_date)

Join patterns:
- facts: companies c JOIN financial_statement_facts fsf ON c.company_id = fsf.company_id
         JOIN financial_periods fp ON fp.period_id = fsf.period_id
         JOIN financial_line_item_definitions li ON li.line_item_def_id = fsf.line_item_def_id
- Resolve company by nse_symbol (uppercase) e.g. c.nse_symbol = 'RELIANCE'
- Resolve period by fp.display_label = 'Q3 FY2022-23' OR (fp.fy_label='FY2022-23' AND fp.quarter=3)
""".strip()

_SYSTEM_PROMPT = f"""You translate investor questions into a single PostgreSQL SELECT query.

Rules:
- Output ONLY valid JSON: {{"sql": "<query>", "summary": "<one line what the query returns>"}}
- Exactly one SELECT (WITH ... SELECT allowed). No semicolons inside the query.
- Read-only: never INSERT/UPDATE/DELETE/DDL.
- Always include LIMIT <= {DATA_ASK_MAX_ROWS} at the end.
- Prefer financial_statement_facts for published metrics; use extracted_values only when asking for raw extraction.
- For quarterly P&L metrics use period_value_type = 'CURRENT' and consolidation = 'CONSOLIDATED' unless the user asks for standalone or prior-year (PY).
- Map natural names to normalized_code (e.g. "EPS basic" -> eps_basic, "revenue" -> revenue_from_operations).
- Indian FY periods: "Q3 FY 2022-23" -> display_label 'Q3 FY2022-23'.

Schema:
{_SCHEMA_CONTEXT}
"""

_LINE_ITEM_ALIASES: dict[str, str] = {
    "eps": "eps_basic",
    "eps basic": "eps_basic",
    "eps (basic)": "eps_basic",
    "basic eps": "eps_basic",
    "revenue": "revenue_from_operations",
    "sales": "revenue_from_operations",
    "pat": "pat",
    "profit after tax": "pat",
    "net profit": "pat",
    "ebitda": "ebitda",
}


@dataclass(frozen=True)
class DataAskResult:
    answer: str
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int


class DataAskError(ValueError):
    """User-facing data-ask failure (bad question, unsafe SQL, empty result)."""


def ask_data(db: Session, question: str) -> DataAskResult:
    q = (question or "").strip()
    if not q:
        raise DataAskError("Question cannot be empty.")

    provider = get_provider()
    if isinstance(provider, MockProvider):
        sql = _mock_generate_sql(q)
        summary = "Mock query for local development."
    else:
        try:
            sql, summary = _llm_generate_sql(provider, q)
        except Exception as exc:
            if settings.is_production:
                raise DataAskError("Could not generate SQL for this question.") from exc
            logger.exception("data_ask LLM failed; using mock SQL: %s", exc)
            sql = _mock_generate_sql(q)
            summary = "Fallback mock query after LLM error."

    safe_sql = validate_and_cap_sql(sql)
    columns, rows = _execute_sql(db, safe_sql)
    answer = _format_answer(q, summary, columns, rows)
    return DataAskResult(
        answer=answer,
        sql=safe_sql,
        columns=columns,
        rows=rows,
        row_count=len(rows),
    )


def validate_and_cap_sql(sql: str) -> str:
    raw = (sql or "").strip()
    if not raw:
        raise DataAskError("No SQL was generated.")
    if len(raw) > _DATA_ASK_MAX_SQL_CHARS:
        raise DataAskError("Generated SQL is too long.")
    if ";" in raw.rstrip(";").strip():
        raise DataAskError("Only a single SQL statement is allowed.")
    if "--" in raw or "/*" in raw:
        raise DataAskError("SQL comments are not allowed.")
    if _FORBIDDEN_SQL.search(raw):
        raise DataAskError("Only read-only SELECT queries are allowed.")
    lowered = raw.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise DataAskError("Query must start with SELECT or WITH.")

    if not re.search(r"\blimit\s+\d+", raw, re.IGNORECASE):
        raw = f"{raw.rstrip()}\nLIMIT {DATA_ASK_MAX_ROWS}"

    return raw


def _execute_sql(db: Session, sql: str) -> tuple[list[str], list[dict[str, Any]]]:
    try:
        result = db.execute(text(sql))
    except Exception as exc:
        logger.warning("data_ask SQL execution failed: %s", exc)
        raise DataAskError(f"Query failed: {exc}") from exc

    columns = list(result.keys())
    rows = [_serialize_row(dict(zip(columns, row))) for row in result.fetchall()]
    return columns, rows


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, val in row.items():
        if isinstance(val, Decimal):
            out[key] = float(val)
        elif isinstance(val, (datetime, date)):
            out[key] = val.isoformat()
        elif isinstance(val, enum.Enum):
            out[key] = val.value
        else:
            out[key] = val
    return out


def _format_answer(
    question: str,
    summary: str,
    columns: list[str],
    rows: list[dict[str, Any]],
) -> str:
    if not rows:
        return f"No rows matched your question. ({summary})"

    if len(rows) == 1 and len(columns) <= 4:
        parts = [f"{col}: {rows[0].get(col)}" for col in columns]
        return f"{' · '.join(parts)}"

    preview = min(5, len(rows))
    lines = [summary, f"Returned {len(rows)} row(s). Top {preview}:"]
    for i, row in enumerate(rows[:preview]):
        snippet = ", ".join(f"{k}={row[k]}" for k in columns[:6])
        lines.append(f"  {i + 1}. {snippet}")
    if len(rows) > preview:
        lines.append(f"  … and {len(rows) - preview} more (see full table below).")
    return "\n".join(lines)


def _llm_generate_sql(provider: AnthropicProvider | OpenAIProvider, question: str) -> tuple[str, str]:
    user_message = f"Question: {question}"
    try:
        if isinstance(provider, AnthropicProvider):
            raw = _anthropic_text(provider, user_message)
        else:
            raw = _openai_text(provider, user_message)
    except Exception as exc:
        if settings.is_production:
            raise DataAskError("Could not generate SQL for this question.") from exc
        logger.exception("data_ask LLM failed; using mock SQL: %s", exc)
        return _mock_generate_sql(question), "Fallback mock query."

    return _parse_sql_json(raw)


def _parse_sql_json(raw: str) -> tuple[str, str]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not m:
        raise DataAskError("LLM did not return valid JSON.")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise DataAskError("LLM returned malformed JSON.") from exc

    sql = str(data.get("sql", "")).strip()
    summary = str(data.get("summary", "Query results")).strip()
    if not sql:
        raise DataAskError("LLM did not include a SQL query.")
    return sql, summary


def _anthropic_text(provider: AnthropicProvider, user_message: str) -> str:
    from app.services.pipeline.llm import _anthropic_omit_sampling_params, _cached_anthropic_system

    create_kwargs: dict[str, Any] = {
        "model": provider._model,
        "max_tokens": 2048,
        "system": _cached_anthropic_system(_SYSTEM_PROMPT),
        "messages": [{"role": "user", "content": user_message}],
    }
    if not _anthropic_omit_sampling_params(provider._model):
        create_kwargs["temperature"] = 0
    resp = provider._client.messages.create(**create_kwargs)
    text_chunks = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    return "".join(text_chunks).strip()


def _openai_text(provider: OpenAIProvider, user_message: str) -> str:
    resp = provider._client.chat.completions.create(
        model=provider._model,
        max_tokens=2048,
        temperature=0,
        seed=provider._seed,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def _mock_generate_sql(question: str) -> str:
    """Deterministic SQL for common dev questions without an API key."""
    q_lower = question.lower()
    symbol = _extract_symbol(question) or "RELIANCE"
    period_label = _extract_period_label(question) or "Q3 FY2025-26"
    line_code = _extract_line_item_code(q_lower) or "eps_basic"

    return f"""
SELECT
  c.company_name,
  c.nse_symbol,
  fp.display_label,
  li.display_name AS metric,
  fsf.value,
  fsf.unit,
  fsf.consolidation
FROM financial_statement_facts fsf
JOIN companies c ON c.company_id = fsf.company_id
JOIN financial_periods fp ON fp.period_id = fsf.period_id
JOIN financial_line_item_definitions li ON li.line_item_def_id = fsf.line_item_def_id
WHERE c.nse_symbol = '{symbol}'
  AND fp.display_label = '{period_label}'
  AND li.normalized_code = '{line_code}'
  AND fsf.period_value_type = 'CURRENT'
  AND fsf.consolidation = 'CONSOLIDATED'
LIMIT {DATA_ASK_MAX_ROWS}
""".strip()


_SYMBOL_BLOCKLIST = frozenset(
    {
        "WHAT", "WHICH", "SHOW", "GIVE", "TELL", "EPS", "PAT", "EBITDA",
        "THE", "FOR", "AND", "FROM", "WITH", "FY", "Q1", "Q2", "Q3", "Q4",
    }
)


def _extract_symbol(question: str) -> str | None:
    q_lower = question.lower()
    for name, sym in (
        ("reliance", "RELIANCE"),
        ("tcs", "TCS"),
        ("infosys", "INFY"),
        ("hdfc bank", "HDFCBANK"),
    ):
        if name in q_lower:
            return sym
    for m in re.finditer(r"\b([A-Z]{2,12})\b", question):
        token = m.group(1)
        if token not in _SYMBOL_BLOCKLIST:
            return token
    return None


def _extract_period_label(question: str) -> str | None:
    def _label(q: str, start: str, end: str) -> str:
        if len(start) == 2:
            start = "20" + start
        end2 = end[-2:] if len(end) >= 2 else end
        return f"Q{q} FY{start}-{end2}"

    m = re.search(
        r"Q\s*([1-4])\s*(?:FY|fy)\s*(\d{4})\s*[-–]\s*(\d{2,4})",
        question,
        re.IGNORECASE,
    )
    if m:
        return _label(m.group(1), m.group(2), m.group(3))
    m = re.search(r"Q\s*([1-4])\s*FY\s*(\d{2,4})\s*[-–]\s*(\d{2,4})", question, re.IGNORECASE)
    if m:
        return _label(m.group(1), m.group(2), m.group(3))
    m = re.search(
        r"quarter\s*([1-4])\s*(?:fy)?\s*(\d{4})\s*[-–]\s*(\d{2,4})",
        question,
        re.IGNORECASE,
    )
    if m:
        return _label(m.group(1), m.group(2), m.group(3))
    return None


def _extract_line_item_code(q_lower: str) -> str | None:
    for phrase, code in sorted(_LINE_ITEM_ALIASES.items(), key=lambda x: -len(x[0])):
        if phrase in q_lower:
            return code
    return None
