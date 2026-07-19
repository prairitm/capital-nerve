#!/usr/bin/env python3
"""Remove all v4 company data while retaining users and catalog definitions.

Run without ``--confirm`` to see what would be removed. Stop the v4 services
first so no pipeline or monitor process writes data during the cleanup.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path


V4_DIR = Path(__file__).resolve().parent
DEFAULT_ANALYTICS_DB = V4_DIR / "data" / "capital_nerve.db"
DEFAULT_APP_DB = V4_DIR / "data" / "capital_nerve_app.db"

# Child tables must precede their parents. fact_definitions is deliberately not
# included: it is catalog configuration, not company data.
ANALYTICS_TABLES = (
    "intelligence_cards",
    "signals",
    "metrics",
    "presentation_segments",
    "presentation_document_inventory",
    "resolved_facts",
    "fact_observations",
    "extracted_values",
    "documents",
    "events",
    "companies",
)

# These tables live in the writable application database. Users, sessions,
# preferences, and the cached NSE security directory are intentionally kept.
APP_TABLES = (
    "email_outbox",
    "pipeline_jobs",
    "company_poll_state",
    "watchlist_companies",
)


def existing_tables(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def table_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def document_paths(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    tables = existing_tables(conn)
    if "documents" not in tables:
        return []
    columns = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
    if not {"id", "storage_path"} <= columns:
        return []
    return [(str(row[0]), str(row[1])) for row in conn.execute("SELECT id, storage_path FROM documents")]


def delete_rows(conn: sqlite3.Connection, tables: tuple[str, ...]) -> Counter[str]:
    present = existing_tables(conn)
    deleted: Counter[str] = Counter()
    for table in tables:
        if table not in present:
            continue
        deleted[table] = table_count(conn, table)
        conn.execute(f'DELETE FROM "{table}"')
    return deleted


def remove_file(path: Path, allowed_dir: Path) -> bool:
    """Remove one regular file only when it belongs to a managed data folder."""
    try:
        path.resolve().relative_to(allowed_dir.resolve())
    except ValueError:
        print(f"Skipped unsafe file path outside {allowed_dir}: {path}", file=sys.stderr)
        return False
    if path.is_file():
        path.unlink()
        return True
    return False


def remove_managed_files(directory: Path) -> int:
    """Remove regular files from a v4-managed company-data directory."""
    removed = 0
    if not directory.exists():
        return removed
    for path in directory.rglob("*"):
        if path.is_file() and not path.is_symlink():
            removed += remove_file(path, directory)
    return removed


def connect(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="perform the irreversible deletion")
    parser.add_argument(
        "--analytics-db",
        type=Path,
        default=Path(os.getenv("V4_DB_PATH", DEFAULT_ANALYTICS_DB)),
        help="analytics SQLite database (default: V4_DB_PATH or v4/data/capital_nerve.db)",
    )
    parser.add_argument(
        "--app-db",
        type=Path,
        default=Path(os.getenv("V4_APP_DB_PATH", DEFAULT_APP_DB)),
        help="application SQLite database (default: V4_APP_DB_PATH or v4/data/capital_nerve_app.db)",
    )
    parser.add_argument("--documents-dir", type=Path, help="stored PDF directory")
    parser.add_argument("--parsed-dir", type=Path, help="parsed-document cache directory")
    args = parser.parse_args()

    analytics_db = args.analytics_db.resolve()
    app_db = args.app_db.resolve()
    documents_dir = (args.documents_dir or analytics_db.parent / "documents").resolve()
    parsed_dir = (args.parsed_dir or analytics_db.parent / "parsed").resolve()

    analytics = connect(analytics_db)
    app = connect(app_db)
    if analytics is None and app is None:
        print("No v4 databases found; nothing to remove.")
        return 0

    analytics_counts: Counter[str] = Counter()
    app_counts: Counter[str] = Counter()
    records: list[tuple[str, str]] = []
    try:
        if analytics:
            records = document_paths(analytics)
            for table in ANALYTICS_TABLES:
                if table in existing_tables(analytics):
                    analytics_counts[table] = table_count(analytics, table)
        if app:
            for table in APP_TABLES:
                if table in existing_tables(app):
                    app_counts[table] = table_count(app, table)

        print(f"Analytics database: {analytics_db}")
        for table, count in analytics_counts.items():
            print(f"  {table}: {count}")
        print(f"Application database: {app_db}")
        for table, count in app_counts.items():
            print(f"  {table}: {count}")
        print(f"  stored document records: {len(records)}")

        if not args.confirm:
            print("Dry run only. Re-run with --confirm after stopping v4 services.")
            return 0

        if analytics:
            analytics.execute("BEGIN IMMEDIATE")
            delete_rows(analytics, ANALYTICS_TABLES)
            analytics.commit()
        if app:
            app.execute("BEGIN IMMEDIATE")
            delete_rows(app, APP_TABLES)
            app.commit()
        removed_files = remove_managed_files(documents_dir) + remove_managed_files(parsed_dir)
        print(f"Removed {sum(analytics_counts.values()) + sum(app_counts.values())} database rows and {removed_files} files.")
        return 0
    except sqlite3.Error as exc:
        if analytics:
            analytics.rollback()
        if app:
            app.rollback()
        print(
            f"Cleanup failed; any active transaction was rolled back: {exc}",
            file=sys.stderr,
        )
        return 1
    finally:
        if analytics:
            analytics.close()
        if app:
            app.close()


if __name__ == "__main__":
    raise SystemExit(main())
