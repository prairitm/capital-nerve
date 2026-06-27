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


def register_company(conn: sqlite3.Connection, symbol: str) -> dict[str, Any]:
    company_id = company_id_for_symbol(symbol)
    bootstrap_schema(conn)
    conn.execute(
        """
        INSERT INTO companies (id, name, ticker, exchange)
        VALUES (?, ?, ?, 'NSE')
        ON CONFLICT(id) DO UPDATE SET ticker = excluded.ticker
        """,
        (company_id, symbol, symbol),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()
    if row is None:
        raise RuntimeError(f"company insert did not return a row for {symbol}")
    return row_to_dict(row)
