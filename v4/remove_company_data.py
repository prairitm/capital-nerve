#!/usr/bin/env python3
"""Remove one v4 company's data while retaining users and other companies.

Run without ``--confirm`` to preview the rows and files that would be removed.
Stop the v4 services before running with ``--confirm`` so no pipeline or monitor
process writes data during the cleanup.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from remove_all_company_data import (
    DEFAULT_ANALYTICS_DB,
    DEFAULT_APP_DB,
    connect,
    existing_tables,
    remove_file,
)


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

APP_TABLES = (
    "email_outbox",
    "pipeline_jobs",
    "company_poll_state",
    "watchlist_companies",
)


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def company_where(table: str, company_id: str) -> tuple[str, tuple[str, ...]]:
    if table == "companies":
        return '"id" = ?', (company_id,)
    return '"company_id" = ?', (company_id,)


def company_counts(
    conn: sqlite3.Connection, tables: tuple[str, ...], company_id: str
) -> Counter[str]:
    present = existing_tables(conn)
    counts: Counter[str] = Counter()
    for table in tables:
        if table not in present:
            continue
        where, params = company_where(table, company_id)
        required_column = "id" if table == "companies" else "company_id"
        if required_column not in table_columns(conn, table):
            continue
        counts[table] = int(
            conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE {where}', params).fetchone()[0]
        )
    return counts


def delete_company_rows(
    conn: sqlite3.Connection, tables: tuple[str, ...], company_id: str
) -> None:
    present = existing_tables(conn)
    for table in tables:
        if table not in present:
            continue
        where, params = company_where(table, company_id)
        required_column = "id" if table == "companies" else "company_id"
        if required_column in table_columns(conn, table):
            conn.execute(f'DELETE FROM "{table}" WHERE {where}', params)


def find_company(conn: sqlite3.Connection, selector: str) -> sqlite3.Row | None:
    if "companies" not in existing_tables(conn):
        return None
    columns = table_columns(conn, "companies")
    conn.row_factory = sqlite3.Row
    clauses = ['"id" = ?']
    params: list[str] = [selector]
    for column in ("ticker", "isin"):
        if column in columns:
            clauses.append(f'"{column}" = ? COLLATE NOCASE')
            params.append(selector)
    return conn.execute(
        f'SELECT * FROM companies WHERE {" OR ".join(clauses)}', params
    ).fetchone()


def document_records(conn: sqlite3.Connection, company_id: str) -> list[tuple[str, str]]:
    if "documents" not in existing_tables(conn):
        return []
    if not {"id", "company_id", "storage_path"} <= table_columns(conn, "documents"):
        return []
    return [
        (str(row[0]), str(row[1]))
        for row in conn.execute(
            "SELECT id, storage_path FROM documents WHERE company_id = ?", (company_id,)
        )
    ]


def managed_files(
    records: list[tuple[str, str]], documents_dir: Path, parsed_dir: Path
) -> list[tuple[Path, Path]]:
    candidates: list[tuple[Path, Path]] = []
    for document_id, storage_path in records:
        candidates.append((Path(storage_path), documents_dir))
        if parsed_dir.exists():
            for parsed_path in parsed_dir.glob(f"{document_id}.*"):
                candidates.append((parsed_path, parsed_dir))
    # Preserve order while avoiding duplicate paths.
    return list(dict.fromkeys(candidates))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "selector", nargs="?", help="company ticker, ISIN, or exact company ID"
    )
    parser.add_argument("--symbol", dest="symbol", help="company ticker (alias for selector)")
    parser.add_argument("--confirm", action="store_true", help="perform the irreversible deletion")
    parser.add_argument(
        "--analytics-db",
        type=Path,
        default=Path(os.getenv("V4_DB_PATH", DEFAULT_ANALYTICS_DB)),
    )
    parser.add_argument(
        "--app-db",
        type=Path,
        default=Path(os.getenv("V4_APP_DB_PATH", DEFAULT_APP_DB)),
    )
    parser.add_argument("--documents-dir", type=Path, help="stored PDF directory")
    parser.add_argument("--parsed-dir", type=Path, help="parsed-document cache directory")
    args = parser.parse_args()

    selector = (args.symbol or args.selector or "").strip()
    if not selector:
        parser.error("provide a ticker, ISIN, or company ID (for example: --symbol RELIANCE)")
    if args.symbol and args.selector:
        parser.error("provide either selector or --symbol, not both")

    analytics_db = args.analytics_db.resolve()
    app_db = args.app_db.resolve()
    documents_dir = (args.documents_dir or analytics_db.parent / "documents").resolve()
    parsed_dir = (args.parsed_dir or analytics_db.parent / "parsed").resolve()
    analytics = connect(analytics_db)
    if analytics is None:
        print(f"Analytics database not found: {analytics_db}", file=sys.stderr)
        return 1
    app = connect(app_db)

    try:
        company = find_company(analytics, selector)
        if company is None:
            print(f"Company not found: {selector}", file=sys.stderr)
            return 1
        company_id = str(company["id"])
        ticker = str(company["ticker"]) if "ticker" in company.keys() and company["ticker"] else "-"
        name = str(company["name"]) if "name" in company.keys() and company["name"] else "-"

        analytics_counts = company_counts(analytics, ANALYTICS_TABLES, company_id)
        app_counts = company_counts(app, APP_TABLES, company_id) if app else Counter()
        records = document_records(analytics, company_id)
        files = managed_files(records, documents_dir, parsed_dir)
        existing_files = [(path, root) for path, root in files if path.is_file()]

        print(f"Company: {name} ({ticker})")
        print(f"Company ID: {company_id}")
        print(f"Analytics database: {analytics_db}")
        for table, count in analytics_counts.items():
            print(f"  {table}: {count}")
        print(f"Application database: {app_db}")
        for table, count in app_counts.items():
            print(f"  {table}: {count}")
        print(f"  managed files: {len(existing_files)}")

        if not args.confirm:
            print("Dry run only. Re-run with --confirm after stopping v4 services.")
            return 0

        analytics.execute("BEGIN IMMEDIATE")
        if app:
            app.execute("BEGIN IMMEDIATE")
        try:
            delete_company_rows(analytics, ANALYTICS_TABLES, company_id)
            if app:
                delete_company_rows(app, APP_TABLES, company_id)
            analytics.commit()
            if app:
                app.commit()
        except sqlite3.Error:
            analytics.rollback()
            if app:
                app.rollback()
            raise

        removed_files = sum(remove_file(path, root) for path, root in existing_files)
        removed_rows = sum(analytics_counts.values()) + sum(app_counts.values())
        print(f"Removed {removed_rows} database rows and {removed_files} files for {ticker}.")
        return 0
    except sqlite3.Error as exc:
        print(f"Cleanup failed; active transactions were rolled back: {exc}", file=sys.stderr)
        return 1
    finally:
        analytics.close()
        if app:
            app.close()


if __name__ == "__main__":
    raise SystemExit(main())
