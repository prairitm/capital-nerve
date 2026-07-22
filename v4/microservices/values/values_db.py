"""SQLite bootstrap used by the Step 4 values microservice."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from values_config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, ticker TEXT, exchange TEXT,
    sector TEXT, industry TEXT, isin TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
    event_type TEXT NOT NULL, event_date TEXT NOT NULL, fiscal_year INTEGER,
    fiscal_quarter INTEGER, title TEXT, source_url TEXT, document_id TEXT,
    status TEXT DEFAULT 'processed'
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
    source_url TEXT, storage_path TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE,
    title TEXT, document_kind TEXT, file_size INTEGER,
    status TEXT DEFAULT 'pending', error_message TEXT,
    ingested_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS extracted_values (
    id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
    event_id TEXT NOT NULL REFERENCES events(id), value_code TEXT NOT NULL,
    value_numeric REAL, value_text TEXT, unit TEXT, period_type TEXT,
    period_start TEXT, period_end TEXT, basis TEXT DEFAULT 'consolidated',
    segment TEXT, geography TEXT, source_text TEXT, source_page INTEGER,
    confidence REAL
);
CREATE TABLE IF NOT EXISTS fact_definitions (
    fact_code TEXT PRIMARY KEY,
    fact_name TEXT NOT NULL,
    fact_category TEXT NOT NULL,
    value_type TEXT NOT NULL,
    standard_unit TEXT,
    preferred_source TEXT
);
CREATE TABLE IF NOT EXISTS fact_observations (
    observation_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    event_id TEXT NOT NULL REFERENCES events(id),
    document_id TEXT REFERENCES documents(id),
    fact_code TEXT NOT NULL REFERENCES fact_definitions(fact_code),
    value REAL,
    unit TEXT,
    period TEXT,
    source_page INTEGER,
    source_text TEXT,
    confidence REAL
);
CREATE TABLE IF NOT EXISTS resolved_facts (
    resolved_fact_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    event_id TEXT NOT NULL REFERENCES events(id),
    fact_code TEXT NOT NULL REFERENCES fact_definitions(fact_code),
    resolved_value REAL,
    unit TEXT,
    selected_observation_id TEXT REFERENCES fact_observations(observation_id),
    resolution_status TEXT,
    confidence REAL
);
CREATE TABLE IF NOT EXISTS metrics (
    metric_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    event_id TEXT NOT NULL REFERENCES events(id),
    metric_code TEXT NOT NULL,
    value REAL,
    unit TEXT,
    input_fact_ids TEXT,
    formula TEXT
);
CREATE TABLE IF NOT EXISTS signals (
    signal_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    event_id TEXT NOT NULL REFERENCES events(id),
    signal_code TEXT NOT NULL,
    severity TEXT,
    direction TEXT,
    supporting_metric_ids TEXT,
    supporting_fact_ids TEXT
);
CREATE TABLE IF NOT EXISTS intelligence_cards (
    card_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    event_id TEXT NOT NULL REFERENCES events(id),
    card_title TEXT NOT NULL,
    signal_id TEXT NOT NULL REFERENCES signals(signal_id),
    confidence TEXT,
    display_status TEXT DEFAULT 'published'
);
CREATE TABLE IF NOT EXISTS event_summaries (
    event_id TEXT PRIMARY KEY REFERENCES events(id),
    document_id TEXT NOT NULL REFERENCES documents(id),
    markdown_sha256 TEXT NOT NULL,
    model TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT NOT NULL,
    key_points_json TEXT NOT NULL,
    investor_takeaway TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def prepare_paths() -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.documents_dir.mkdir(parents=True, exist_ok=True)
    settings.parsed_dir.mkdir(parents=True, exist_ok=True)


def connect() -> sqlite3.Connection:
    prepare_paths()
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def bootstrap_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    migrate_unified_schema(conn)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    if column not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def migrate_unified_schema(conn: sqlite3.Connection) -> None:
    for table in ("fact_observations", "resolved_facts", "extracted_values"):
        for column in ("segment", "geography", "product", "channel", "project", "customer_type", "metric_context"):
            _ensure_column(conn, table, column, "TEXT")
        for column in ("scope_level", "scope_name", "fact_type", "sentiment"):
            _ensure_column(conn, table, column, "TEXT")
        for column in ("value_lower", "value_upper"):
            _ensure_column(conn, table, column, "REAL")
        _ensure_column(conn, table, "is_explicit_guidance", "INTEGER")
    _ensure_column(conn, "fact_observations", "value_text", "TEXT")
    _ensure_column(conn, "fact_observations", "extraction_method", "TEXT")
    _ensure_column(conn, "fact_observations", "basis", "TEXT")
    _ensure_column(conn, "fact_observations", "period_type", "TEXT")
    _ensure_column(conn, "resolved_facts", "resolved_value_text", "TEXT")
    _ensure_column(conn, "resolved_facts", "period", "TEXT")
    _ensure_column(conn, "resolved_facts", "period_type", "TEXT")
    _ensure_column(conn, "resolved_facts", "basis", "TEXT")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS presentation_document_inventory (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id),
            event_id TEXT NOT NULL REFERENCES events(id),
            document_id TEXT NOT NULL REFERENCES documents(id),
            period_label TEXT,
            inventory_json TEXT NOT NULL,
            extraction_plan_json TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS presentation_segments (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id),
            event_id TEXT NOT NULL REFERENCES events(id),
            document_id TEXT NOT NULL REFERENCES documents(id),
            segment_name TEXT NOT NULL,
            segment_slug TEXT,
            aliases_json TEXT,
            slides_json TEXT,
            confidence REAL
        );
        """
    )
    conn.commit()
