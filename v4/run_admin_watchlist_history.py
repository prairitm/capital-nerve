#!/usr/bin/env python3
"""Run the v4 pipeline for an administrator's watchlist quarter by quarter.

The oldest quarter is processed first so prior-period facts exist before later
quarters calculate comparisons. By default, the script processes Financial
Results for the latest eight completed calendar quarters.
"""

from __future__ import annotations

import argparse
import calendar
import os
import shlex
import sqlite3
import subprocess
import sys
from contextlib import closing
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Sequence


V4_DIR = Path(__file__).resolve().parent
DEFAULT_APP_DB = V4_DIR / "data" / "capital_nerve_app.db"
DEFAULT_ANALYTICS_DB = V4_DIR / "data" / "capital_nerve.db"
DEFAULT_RUN_SCRIPT = V4_DIR / "microservices" / "run.py"


class BatchError(RuntimeError):
    """A configuration or database error that prevents the batch from running."""


@dataclass(frozen=True)
class QuarterWindow:
    start: date
    end: date

    @property
    def label(self) -> str:
        quarter = (self.end.month - 1) // 3 + 1
        return f"{self.end.year} Q{quarter}"

    @property
    def from_date(self) -> str:
        return self.start.strftime("%d-%m-%Y")

    @property
    def to_date(self) -> str:
        return self.end.strftime("%d-%m-%Y")


@dataclass(frozen=True)
class Company:
    company_id: str
    symbol: str
    name: str


def quarter_start(value: date) -> date:
    month = ((value.month - 1) // 3) * 3 + 1
    return date(value.year, month, 1)


def quarter_end(value: date) -> date:
    month = ((value.month - 1) // 3 + 1) * 3
    return date(value.year, month, calendar.monthrange(value.year, month)[1])


def completed_quarters(as_of: date, count: int) -> list[QuarterWindow]:
    """Return completed calendar quarters in chronological order."""
    if count < 1:
        raise BatchError("--quarters must be at least 1")

    current_end = quarter_end(as_of)
    latest_end = current_end if current_end <= as_of else quarter_start(as_of) - timedelta(days=1)
    windows: list[QuarterWindow] = []
    cursor = latest_end
    for _ in range(count):
        start = quarter_start(cursor)
        windows.append(QuarterWindow(start=start, end=quarter_end(start)))
        cursor = start - timedelta(days=1)
    return list(reversed(windows))


def connect_read_only(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise BatchError(f"Database does not exist: {path}")
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise BatchError(f"Could not open database {path}: {exc}") from exc
    conn.row_factory = sqlite3.Row
    return conn


def resolve_admin(conn: sqlite3.Connection, email: str | None) -> sqlite3.Row:
    try:
        if email:
            admin = conn.execute(
                """
                SELECT id, email
                FROM users
                WHERE email = ? COLLATE NOCASE AND role = 'ADMIN' AND is_active = 1
                """,
                (email.strip(),),
            ).fetchone()
            if admin is None:
                raise BatchError(f"No active administrator found for {email!r}")
            return admin

        admins = conn.execute(
            """
            SELECT id, email
            FROM users
            WHERE role = 'ADMIN' AND is_active = 1
            ORDER BY created_at, email
            """
        ).fetchall()
    except sqlite3.Error as exc:
        raise BatchError(f"Could not read administrators: {exc}") from exc

    if not admins:
        raise BatchError("No active administrator account was found")
    if len(admins) > 1:
        emails = ", ".join(str(row["email"]) for row in admins)
        raise BatchError(
            f"Multiple active administrators found ({emails}); select one with --admin-email"
        )
    return admins[0]


def watchlist_company_ids(conn: sqlite3.Connection, user_id: str) -> list[str]:
    try:
        rows = conn.execute(
            """
            SELECT company_id
            FROM watchlist_companies
            WHERE user_id = ?
            ORDER BY added_at, company_id
            """,
            (user_id,),
        ).fetchall()
    except sqlite3.Error as exc:
        raise BatchError(f"Could not read the administrator watchlist: {exc}") from exc
    return [str(row["company_id"]) for row in rows]


def resolve_companies(analytics_db: Path, company_ids: Sequence[str]) -> list[Company]:
    if not company_ids:
        return []
    with closing(connect_read_only(analytics_db)) as conn:
        placeholders = ",".join("?" for _ in company_ids)
        try:
            rows = conn.execute(
                f"SELECT id, ticker, name FROM companies WHERE id IN ({placeholders})",
                tuple(company_ids),
            ).fetchall()
        except sqlite3.Error as exc:
            raise BatchError(f"Could not resolve watchlist companies: {exc}") from exc

    by_id = {str(row["id"]): row for row in rows}
    missing = [company_id for company_id in company_ids if company_id not in by_id]
    if missing:
        raise BatchError(
            "Watchlist company IDs missing from the analytics database: " + ", ".join(missing)
        )

    companies: list[Company] = []
    for company_id in company_ids:
        row = by_id[company_id]
        symbol = str(row["ticker"] or "").strip().upper()
        if not symbol:
            raise BatchError(f"Watchlist company {company_id} has no ticker")
        companies.append(
            Company(company_id=company_id, symbol=symbol, name=str(row["name"]))
        )
    return companies


def build_run_command(
    args: argparse.Namespace,
    company: Company,
    window: QuarterWindow,
) -> list[str]:
    command = [
        args.python,
        str(args.run_script),
        "--symbol",
        company.symbol,
        "--from-date",
        window.from_date,
        "--to-date",
        window.to_date,
    ]
    if args.all_event_types:
        command.append("--all-event-types")
    else:
        command.extend(["--event-type", args.event_type])
    command.extend(args.run_args)
    return command


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--admin-email",
        help="administrator whose watchlist should run (required only when several admins exist)",
    )
    parser.add_argument("--quarters", type=int, default=8, help="completed quarters to run")
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=date.today(),
        metavar="YYYY-MM-DD",
        help="date used to determine completed quarters (default: today)",
    )
    parser.add_argument(
        "--event-type",
        default="Financial Results",
        help="run.py event type (default: Financial Results)",
    )
    parser.add_argument(
        "--all-event-types",
        action="store_true",
        help="pass --all-event-types to run.py instead of --event-type",
    )
    parser.add_argument(
        "--app-db",
        type=Path,
        default=Path(os.getenv("V4_APP_DB_PATH", DEFAULT_APP_DB)),
        help="application DB (default: V4_APP_DB_PATH or v4/data/capital_nerve_app.db)",
    )
    parser.add_argument(
        "--analytics-db",
        type=Path,
        default=Path(os.getenv("V4_DB_PATH", DEFAULT_ANALYTICS_DB)),
        help="analytics DB (default: V4_DB_PATH or v4/data/capital_nerve.db)",
    )
    parser.add_argument("--python", default=sys.executable, help="Python used to invoke run.py")
    parser.add_argument(
        "--run-script",
        type=Path,
        default=DEFAULT_RUN_SCRIPT,
        help="path to the v4 run.py entry point",
    )
    parser.add_argument("--dry-run", action="store_true", help="print commands without running them")
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="stop at the first failed run instead of finishing the batch",
    )
    parser.add_argument(
        "run_args",
        nargs=argparse.REMAINDER,
        help="extra run.py arguments after --, for example: -- --verbose",
    )
    args = parser.parse_args(argv)
    if args.all_event_types and args.event_type != "Financial Results":
        parser.error("use either --event-type or --all-event-types, not both")
    if args.run_args[:1] == ["--"]:
        args.run_args = args.run_args[1:]
    args.app_db = args.app_db.expanduser().resolve()
    args.analytics_db = args.analytics_db.expanduser().resolve()
    args.run_script = args.run_script.expanduser().resolve()
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if not args.run_script.is_file():
            raise BatchError(f"run.py does not exist: {args.run_script}")
        windows = completed_quarters(args.as_of, args.quarters)
        with closing(connect_read_only(args.app_db)) as app_conn:
            admin = resolve_admin(app_conn, args.admin_email)
            company_ids = watchlist_company_ids(app_conn, str(admin["id"]))
        companies = resolve_companies(args.analytics_db, company_ids)
    except BatchError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if not companies:
        print(f"Administrator {admin['email']} has no companies on the watchlist.")
        return 0

    total = len(companies) * len(windows)
    print(
        f"Administrator: {admin['email']}\n"
        f"Companies: {len(companies)} ({', '.join(company.symbol for company in companies)})\n"
        f"Quarters: {len(windows)} ({windows[0].label} through {windows[-1].label})\n"
        f"Runs: {total}",
        flush=True,
    )

    failures: list[tuple[str, str, int]] = []
    run_number = 0
    for window in windows:
        for company in companies:
            run_number += 1
            command = build_run_command(args, company, window)
            print(
                f"\n[{run_number}/{total}] {company.symbol} - {window.label} "
                f"({window.from_date} to {window.to_date})\n{shlex.join(command)}",
                flush=True,
            )
            if args.dry_run:
                continue
            try:
                result = subprocess.run(command, check=False)
                return_code = result.returncode
            except OSError as exc:
                print(f"Could not start run.py: {exc}", file=sys.stderr)
                return_code = 126
            if return_code:
                failures.append((company.symbol, window.label, return_code))
                if args.stop_on_error:
                    break
        if failures and args.stop_on_error:
            break

    if failures:
        print("\nFailed runs:", file=sys.stderr)
        for symbol, label, return_code in failures:
            print(f"  {symbol} {label}: exit {return_code}", file=sys.stderr)
        print(f"Completed with {len(failures)} failure(s) out of {run_number} attempted run(s).")
        return 1

    action = "Planned" if args.dry_run else "Completed"
    print(f"\n{action} all {run_number} run(s) successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
