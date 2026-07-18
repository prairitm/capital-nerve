"""Company registration logic from financial_result_flow.ipynb Step 1."""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

from company_db import bootstrap_schema


def company_id_for_symbol(symbol: str) -> str:
    return hashlib.sha256(f"{symbol}:NSE".encode()).hexdigest()


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def register_company(
    conn: sqlite3.Connection,
    symbol: str,
    *,
    name: str | None = None,
    isin: str | None = None,
) -> dict[str, Any]:
    company_id = company_id_for_symbol(symbol)
    bootstrap_schema(conn)
    safe_isin = isin
    if safe_isin:
        owner = conn.execute("SELECT id FROM companies WHERE isin = ?", (safe_isin,)).fetchone()
        if owner is not None and owner["id"] != company_id:
            safe_isin = None
    conn.execute(
        """
        INSERT INTO companies (id, name, ticker, exchange, isin)
        VALUES (?, ?, ?, 'NSE', ?)
        ON CONFLICT(id) DO UPDATE SET
            name = CASE
                WHEN excluded.name <> excluded.ticker THEN excluded.name
                ELSE companies.name
            END,
            ticker = excluded.ticker,
            exchange = 'NSE',
            isin = COALESCE(excluded.isin, companies.isin)
        """,
        (company_id, (name or symbol).strip(), symbol, safe_isin),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if row is None:
        raise RuntimeError(f"company insert did not return a row for {symbol}")
    return row_to_dict(row)
