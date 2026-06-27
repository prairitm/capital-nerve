"""SQLite bootstrap used by the Step 1 company microservice."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from company_config import settings

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
CREATE TABLE IF NOT EXISTS metrics (
    id TEXT PRIMARY KEY, metric_code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
    formula TEXT, unit TEXT, description TEXT
);
CREATE TABLE IF NOT EXISTS metric_values (
    id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
    event_id TEXT REFERENCES events(id), metric_id TEXT NOT NULL REFERENCES metrics(id),
    metric_value REAL NOT NULL, period_start TEXT, period_end TEXT, segment TEXT,
    calculation_data TEXT, calculated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY, company_id TEXT NOT NULL REFERENCES companies(id),
    event_id TEXT REFERENCES events(id), signal_type TEXT NOT NULL, title TEXT NOT NULL,
    description TEXT, direction TEXT, severity TEXT, confidence REAL, evidence TEXT,
    detected_at TEXT DEFAULT (datetime('now'))
);
"""


def prepare_paths() -> None:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.documents_dir.mkdir(parents=True, exist_ok=True)


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
