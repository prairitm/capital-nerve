#!/usr/bin/env python3
"""One-time migration: fiscal_year (end-year mod 100) -> fy_start_year + fy_label."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from periods import format_fy_label, legacy_fy_end_to_start  # noqa: E402

DB_PATH = ROOT / "data" / "capital_nerve.db"


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _convert_start_year(old_fiscal_year: int) -> int:
    if old_fiscal_year >= 1900:
        return old_fiscal_year
    return legacy_fy_end_to_start(old_fiscal_year)


def migrate(db_path: Path = DB_PATH) -> None:
    if not db_path.exists():
        print(f"No database at {db_path}; nothing to migrate.")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if not _table_exists(conn, "fact_values"):
            print("No fact_values table; initializing fresh schema.")
            from capital_nerve_db import FactStore

            FactStore(db_path)
            print("Done.")
            return

        cols = _columns(conn, "fact_values")
        if "fy_start_year" in cols and "fiscal_year" not in cols:
            print("Already migrated to fy_start_year format.")
            return

        if "fiscal_year" not in cols:
            print("Unexpected schema; run FactStore to initialize.")
            return

        print(f"Migrating {db_path} from fiscal_year to fy_start_year + fy_label ...")

        conn.executescript(
            """
            CREATE TABLE filings_new (
                document_id TEXT PRIMARY KEY,
                company_ticker TEXT NOT NULL,
                sha256 TEXT NOT NULL UNIQUE,
                title TEXT,
                quarter INTEGER,
                fy_start_year INTEGER,
                fy_label TEXT,
                quarter_end TEXT,
                ingested_at TEXT NOT NULL
            );

            CREATE TABLE fact_values_new (
                company_ticker TEXT NOT NULL,
                quarter INTEGER NOT NULL,
                fy_start_year INTEGER NOT NULL,
                fy_label TEXT NOT NULL,
                quarter_end TEXT NOT NULL,
                fact_key TEXT NOT NULL,
                basis TEXT NOT NULL DEFAULT 'consolidated',
                numeric_value REAL NOT NULL,
                unit TEXT,
                evidence TEXT,
                source_document_id TEXT,
                status TEXT NOT NULL DEFAULT 'accepted',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (company_ticker, quarter, fy_start_year, fact_key, basis)
            );

            CREATE TABLE signal_firings_new (
                company_ticker TEXT NOT NULL,
                quarter INTEGER NOT NULL,
                fy_start_year INTEGER NOT NULL,
                fy_label TEXT NOT NULL,
                quarter_end TEXT NOT NULL,
                basis TEXT NOT NULL DEFAULT 'consolidated',
                signal_key TEXT NOT NULL,
                headline TEXT NOT NULL,
                rationale TEXT NOT NULL,
                severity TEXT NOT NULL,
                category TEXT,
                direction TEXT,
                metric_keys TEXT NOT NULL,
                trigger_values TEXT,
                metric_snapshots TEXT,
                rule_json TEXT,
                rule_text TEXT,
                catalog_version TEXT NOT NULL,
                source_document_id TEXT,
                is_primary INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'fired',
                fired_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (company_ticker, quarter, fy_start_year, signal_key, basis)
            );
            """
        )

        if _table_exists(conn, "filings"):
            for row in conn.execute("SELECT * FROM filings").fetchall():
                fy_start = (
                    _convert_start_year(row["fiscal_year"])
                    if row["fiscal_year"] is not None
                    else None
                )
                fy_label = format_fy_label(fy_start) if fy_start is not None else None
                conn.execute(
                    """
                    INSERT INTO filings_new (
                        document_id, company_ticker, sha256, title, quarter,
                        fy_start_year, fy_label, quarter_end, ingested_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["document_id"],
                        row["company_ticker"],
                        row["sha256"],
                        row["title"],
                        row["quarter"],
                        fy_start,
                        fy_label,
                        row["quarter_end"],
                        row["ingested_at"],
                    ),
                )

        filing_cols = _columns(conn, "filings")
        signal_cols = _columns(conn, "signal_firings") if _table_exists(conn, "signal_firings") else set()

        for row in conn.execute("SELECT * FROM fact_values").fetchall():
            fy_start = _convert_start_year(row["fiscal_year"])
            conn.execute(
                """
                INSERT INTO fact_values_new (
                    company_ticker, quarter, fy_start_year, fy_label, quarter_end,
                    fact_key, basis, numeric_value, unit, evidence,
                    source_document_id, status, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["company_ticker"],
                    row["quarter"],
                    fy_start,
                    format_fy_label(fy_start),
                    row["quarter_end"],
                    row["fact_key"],
                    row["basis"],
                    row["numeric_value"],
                    row["unit"],
                    row["evidence"],
                    row["source_document_id"],
                    row["status"],
                    row["updated_at"],
                ),
            )

        if _table_exists(conn, "signal_firings"):
            for row in conn.execute("SELECT * FROM signal_firings").fetchall():
                fy_start = _convert_start_year(row["fiscal_year"])
                conn.execute(
                    """
                    INSERT INTO signal_firings_new (
                        company_ticker, quarter, fy_start_year, fy_label, quarter_end, basis,
                        signal_key, headline, rationale, severity, category, direction,
                        metric_keys, trigger_values, metric_snapshots, rule_json, rule_text,
                        catalog_version, source_document_id, is_primary, status,
                        fired_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["company_ticker"],
                        row["quarter"],
                        fy_start,
                        format_fy_label(fy_start),
                        row["quarter_end"],
                        row["basis"],
                        row["signal_key"],
                        row["headline"],
                        row["rationale"],
                        row["severity"],
                        row["category"],
                        row["direction"],
                        row["metric_keys"],
                        row["trigger_values"],
                        row["metric_snapshots"] if "metric_snapshots" in signal_cols else None,
                        row["rule_json"] if "rule_json" in signal_cols else None,
                        row["rule_text"] if "rule_text" in signal_cols else None,
                        row["catalog_version"],
                        row["source_document_id"],
                        row["is_primary"],
                        row["status"],
                        row["fired_at"],
                        row["updated_at"],
                    ),
                )

        conn.executescript(
            """
            DROP TABLE IF EXISTS signal_firings;
            DROP TABLE IF EXISTS fact_values;
            DROP TABLE IF EXISTS filings;

            ALTER TABLE filings_new RENAME TO filings;
            ALTER TABLE fact_values_new RENAME TO fact_values;
            ALTER TABLE signal_firings_new RENAME TO signal_firings;

            CREATE INDEX IF NOT EXISTS idx_fact_values_company_period
                ON fact_values (company_ticker, fy_start_year, quarter);
            CREATE INDEX IF NOT EXISTS idx_signal_firings_company_period
                ON signal_firings (company_ticker, fy_start_year, quarter);
            CREATE INDEX IF NOT EXISTS idx_signal_firings_signal_key
                ON signal_firings (signal_key);
            """
        )
        conn.commit()
        n_facts = conn.execute("SELECT COUNT(*) FROM fact_values").fetchone()[0]
        print(f"Migrated {n_facts} fact rows to FY2024-25 format.")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
