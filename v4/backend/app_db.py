"""Writable application database for users, sessions, and watchlists."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from config import BACKEND_DIR, settings

MIGRATIONS_DIR = BACKEND_DIR / "migrations"


REVIEW_DECISION_COLUMNS = {
    "application_status": (
        "TEXT NOT NULL DEFAULT 'not_applicable' "
        "CHECK (application_status IN ('pending', 'applied', 'failed', 'not_applicable'))"
    ),
    "applied_at": "TEXT",
    "applied_by": "TEXT",
    "application_error": "TEXT",
    "recompute_status": (
        "TEXT NOT NULL DEFAULT 'not_applicable' "
        "CHECK (recompute_status IN ('pending', 'succeeded', 'failed', 'not_applicable'))"
    ),
    "recomputed_at": "TEXT",
    "recompute_error": "TEXT",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat()


def connect_app(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or settings.app_db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def get_app_conn() -> Iterator[sqlite3.Connection]:
    conn = connect_app()
    try:
        yield conn
    finally:
        conn.close()


def migrate_app_db(path: Path | None = None) -> None:
    """Apply numbered SQL migrations once, in filename order."""
    conn = connect_app(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        applied = {
            row["version"]
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            prefix = migration.stem.split("_", 1)[0]
            if not prefix.isdigit():
                continue
            version = int(prefix)
            if version in applied:
                continue
            sql = migration.read_text(encoding="utf-8")
            escaped_name = migration.name.replace("'", "''")
            applied_at = utc_iso().replace("'", "''")
            conn.executescript(
                "BEGIN IMMEDIATE;\n"
                + sql
                + f"\nINSERT OR IGNORE INTO schema_migrations(version, name, applied_at) "
                f"VALUES ({version}, '{escaped_name}', '{applied_at}');\nCOMMIT;"
            )
        _repair_review_decision_schema(conn)
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (utc_iso(),))
        conn.commit()
    finally:
        conn.close()


def _repair_review_decision_schema(conn: sqlite3.Connection) -> None:
    """Backfill reconciliation fields skipped by historical duplicate migrations."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'fact_review_decisions'"
    ).fetchone()
    if not exists:
        return

    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(fact_review_decisions)").fetchall()
    }
    added_application_status = "application_status" not in existing
    for name, ddl in REVIEW_DECISION_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE fact_review_decisions ADD COLUMN {name} {ddl}")

    if added_application_status:
        conn.execute(
            """
            UPDATE fact_review_decisions
            SET application_status = CASE
                    WHEN decision = 'approved' THEN 'pending'
                    ELSE 'not_applicable'
                END,
                recompute_status = 'not_applicable'
            """
        )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fact_review_decisions_application
        ON fact_review_decisions(application_status, updated_at)
        """
    )
