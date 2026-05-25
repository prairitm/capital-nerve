# data_ask

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Translate natural-language investor questions into read-only SQL over ingested
financial facts, execute safely, and return tabular results plus a short answer.

## Source

- Path: `backend/app/services/data_ask.py`
- Layer: backend-service (read-only; executes SELECT via SQLAlchemy `text()`)

## Contract

- `ask_data(db, question: str) -> DataAskResult` — main entry.
- `validate_and_cap_sql(sql: str) -> str` — rejects non-SELECT / DDL / multi-statement;
  appends `LIMIT` when missing.
- `DataAskResult`: `answer`, `sql`, `columns`, `rows`, `row_count`.
- `DataAskError` — raised for user-facing failures (empty question, unsafe SQL, execution error).

## Dependencies

- May import: `sqlalchemy.text`, `app.core.config.settings`, `app.services.pipeline.llm.get_provider`.
- Must not: import FastAPI or raise `HTTPException`.
- Must not: allow INSERT/UPDATE/DELETE or multiple statements.

## Patterns (symmetry)

- Schema context documents `financial_statement_facts` + `financial_periods` join patterns
  matching `routers/v1/companies.py` snapshot queries (`period_value_type='CURRENT'`,
  `consolidation='CONSOLIDATED'`).
- Period labels use canonical `Q{n} FY{yyyy}-{yy}` from `ingest_common.format_quarterly_display_label`.
- Mock path (`LLM_PROVIDER=mock`) uses `_mock_generate_sql` heuristics — no API key required.

## Verification checklist

- [ ] `validate_and_cap_sql` rejects `DELETE`, `INSERT`, `;` mid-query, and `--` comments
- [ ] Generated SQL always includes `LIMIT <= 100`
- [ ] `ask_data` serializes `Decimal` and dates to JSON-safe values
- [ ] Mock provider builds fact lookup SQL for symbol + period + line item
