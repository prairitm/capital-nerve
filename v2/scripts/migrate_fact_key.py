#!/usr/bin/env python3
"""One-time migration: metric_values.metric_key -> fact_values.fact_key."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from catalog_loader import canonical_fact_key, get_catalog  # noqa: E402

DB_PATH = ROOT / "data" / "capital_nerve.db"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def migrate(db_path: Path = DB_PATH) -> None:
    get_catalog.cache_clear()
    get_catalog()

    if not db_path.exists():
        print(f"No database at {db_path}; nothing to migrate.")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if _table_exists(conn, "fact_values"):
            print("Already migrated (fact_values exists).")
            return

        if not _table_exists(conn, "metric_values"):
            print("No metric_values table; creating fresh schema via FactStore.")
            from capital_nerve_db import FactStore

            FactStore(db_path)
            print("Done.")
            return

        conn.execute("ALTER TABLE metric_values RENAME TO fact_values")
        conn.execute("ALTER TABLE fact_values RENAME COLUMN metric_key TO fact_key")
        conn.execute("DROP INDEX IF EXISTS idx_metric_values_company_period")
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_fact_values_company_period
                ON fact_values (company_ticker, fy_start_year, quarter)
            """
        )

        rows = conn.execute(
            """
            SELECT rowid, company_ticker, quarter, fiscal_year, quarter_end,
                   fact_key, basis, numeric_value, unit, evidence,
                   source_document_id, status, updated_at
            FROM fact_values
            """
        ).fetchall()

        seen: dict[tuple, sqlite3.Row] = {}
        for row in rows:
            canonical = canonical_fact_key(row["fact_key"]) or row["fact_key"]
            pk = (
                row["company_ticker"],
                row["quarter"],
                row["fiscal_year"],
                canonical,
                row["basis"],
            )
            prev = seen.get(pk)
            if prev is None or row["updated_at"] >= prev["updated_at"]:
                seen[pk] = row

        conn.execute("DELETE FROM fact_values")
        for row in seen.values():
            canonical = canonical_fact_key(row["fact_key"]) or row["fact_key"]
            conn.execute(
                """
                INSERT INTO fact_values (
                    company_ticker, quarter, fiscal_year, quarter_end,
                    fact_key, basis, numeric_value, unit, evidence,
                    source_document_id, status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["company_ticker"],
                    row["quarter"],
                    row["fiscal_year"],
                    row["quarter_end"],
                    canonical,
                    row["basis"],
                    row["numeric_value"],
                    row["unit"],
                    row["evidence"],
                    row["source_document_id"],
                    row["status"],
                    row["updated_at"],
                ),
            )

        conn.commit()
        print(f"Migrated {len(seen)} fact rows in {db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
