"""SQLite persistence for Capital Nerve v3."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    ticker          TEXT,
    exchange        TEXT,
    sector          TEXT,
    industry        TEXT,
    isin            TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES companies(id),
    event_type      TEXT NOT NULL,
    event_date      TEXT NOT NULL,
    fiscal_year     INTEGER,
    fiscal_quarter  INTEGER,
    title           TEXT,
    source_url      TEXT,
    document_id     TEXT,
    status          TEXT DEFAULT 'processed'
);

CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES companies(id),
    source_url      TEXT,
    storage_path    TEXT NOT NULL,
    sha256          TEXT NOT NULL UNIQUE,
    title           TEXT,
    document_kind   TEXT,
    file_size       INTEGER,
    status          TEXT DEFAULT 'pending',
    error_message   TEXT,
    ingested_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS extracted_values (
    id              TEXT PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES companies(id),
    event_id        TEXT NOT NULL REFERENCES events(id),
    value_code      TEXT NOT NULL,
    value_numeric   REAL,
    value_text      TEXT,
    unit            TEXT,
    period_type     TEXT,
    period_start    TEXT,
    period_end      TEXT,
    basis           TEXT DEFAULT 'consolidated',
    segment         TEXT,
    geography       TEXT,
    source_text     TEXT,
    source_page     INTEGER,
    confidence      REAL
);

CREATE TABLE IF NOT EXISTS metrics (
    id              TEXT PRIMARY KEY,
    metric_code     TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    formula         TEXT,
    unit            TEXT,
    description     TEXT
);

CREATE TABLE IF NOT EXISTS metric_values (
    id              TEXT PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES companies(id),
    event_id        TEXT REFERENCES events(id),
    metric_id       TEXT NOT NULL REFERENCES metrics(id),
    metric_value    REAL NOT NULL,
    period_start    TEXT,
    period_end      TEXT,
    segment         TEXT,
    calculation_data TEXT,
    calculated_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS signals (
    id              TEXT PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES companies(id),
    event_id        TEXT REFERENCES events(id),
    signal_type     TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    direction       TEXT,
    severity        TEXT,
    confidence      REAL,
    evidence        TEXT,
    detected_at     TEXT DEFAULT (datetime('now'))
);
"""


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else settings.db_path
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


get_db_connection = connect


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return column in {
        row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _ensure_column(
    conn: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    if not _table_has_column(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _migrate_schema(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, "values") and not _table_exists(conn, "extracted_values"):
        conn.execute('ALTER TABLE "values" RENAME TO extracted_values')
    _ensure_column(conn, "documents", "status", "TEXT DEFAULT 'pending'")
    _ensure_column(conn, "documents", "error_message", "TEXT")
    _ensure_column(conn, "extracted_values", "basis", "TEXT DEFAULT 'consolidated'")


def init_db(db_path: Path | str | None = None) -> Path:
    path = Path(db_path) if db_path is not None else settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        _migrate_schema(conn)
        conn.commit()
    from seed_catalog import seed_metrics_catalog

    seed_metrics_catalog(path)
    return path
