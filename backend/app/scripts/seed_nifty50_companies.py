"""Create ``Company`` rows from a Nifty-50 JSON list and optionally bulk-ingest filings.

Each JSON object must include ``legal_name``, ``nse_symbol``, and ``sector``.
Existing companies are matched on ``nse_symbol`` and skipped.

Usage (run from ``backend/``)::

    python -m app.scripts.seed_nifty50_companies
    python -m app.scripts.seed_nifty50_companies --resolve-bse
    python -m app.scripts.seed_nifty50_companies --ingest --last-quarters 4
    python -m app.scripts.seed_nifty50_companies --ingest-only --last-quarters 4 --no-agent-fallback
"""
from __future__ import annotations

from app.core.env import bootstrap_cli_env

bootstrap_cli_env()

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import CompanyStatus, ExchangeCode
from app.db.session import SessionLocal
from app.models.master import Company, Sector, Security
from app.scripts.company_list_json import CompanyListRow, load_company_rows

logger = logging.getLogger("app.scripts.seed_nifty50_companies")

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_INPUT = _BACKEND_ROOT / "var" / "nse_nifty50.json"

app = typer.Typer(
    add_completion=False,
    help="Seed Nifty-50 companies and optionally resolve BSE codes / bulk-ingest filings.",
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def run(
    input_path: Path = typer.Option(
        _DEFAULT_INPUT,
        "--input",
        "-i",
        help="Path to the JSON array (default: var/nse_nifty50.json under backend/).",
        exists=True,
        readable=True,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Dry-run seeding; when combined with --ingest, also dry-runs bulk ingest.",
    ),
    ingest_only: bool = typer.Option(
        False,
        "--ingest-only",
        help="Skip seeding (and --resolve-bse) and only run bulk ingest for symbols in the JSON file.",
    ),
    resolve_bse: bool = typer.Option(
        False,
        "--resolve-bse",
        help="After seeding, run resolve_bse_codes --auto-accept for rows missing bse_code.",
    ),
    ingest: bool = typer.Option(
        False,
        "--ingest",
        help="After seeding (and optional BSE resolve), run bulk_ingest for symbols in the JSON file.",
    ),
    period_from: Optional[str] = typer.Option(
        None,
        "--from",
        help='Bulk-ingest quarter range start, e.g. "Q1 FY25-26".',
    ),
    period_to: Optional[str] = typer.Option(
        None,
        "--to",
        help='Bulk-ingest quarter range end, e.g. "Q3 FY25-26".',
    ),
    last_quarters: Optional[int] = typer.Option(
        None,
        "--last-quarters",
        help="Bulk-ingest rolling window: most recent N quarters.",
    ),
    no_agent_fallback: bool = typer.Option(
        False,
        "--no-agent-fallback",
        help="Pass through to bulk_ingest: exchange tier-1 only.",
    ),
    nse_scraper: bool = typer.Option(
        False,
        "--nse-scraper",
        help="Pass through to bulk_ingest: NSE scraper tier-1 only.",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Python logging level (DEBUG / INFO / WARNING / ERROR).",
    ),
) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    if ingest or ingest_only:
        _validate_ingest_period(period_from, period_to, last_quarters)

    try:
        rows = load_company_rows(input_path)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(f"Loaded {len(rows)} entries from {input_path}")

    if not ingest_only:
        _seed_companies(rows, dry_run=dry_run)

    if resolve_bse:
        _run_subcommand(
            [sys.executable, "-m", "app.scripts.resolve_bse_codes", "--auto-accept"]
            + (["--dry-run"] if dry_run else []),
            label="resolve_bse_codes",
        )

    if ingest or ingest_only:
        _run_bulk_ingest(
            input_path=input_path,
            dry_run=dry_run,
            period_from=period_from,
            period_to=period_to,
            last_quarters=last_quarters,
            no_agent_fallback=no_agent_fallback,
            nse_scraper=nse_scraper,
            log_level=log_level,
        )


def _seed_companies(rows: list[CompanyListRow], *, dry_run: bool) -> None:
    db = SessionLocal()
    try:
        created = 0
        skipped = 0
        for row in rows:
            symbol = row.nse_symbol.strip().upper()
            existing = db.scalar(select(Company).where(Company.nse_symbol == symbol))
            if existing:
                typer.echo(f"  [skip]  {symbol} — already registered as {existing.company_name!r}")
                skipped += 1
                continue

            sector = _get_or_create_sector(db, row.sector.strip(), dry_run=dry_run)
            company_name = row.legal_name.strip()

            typer.echo(f"  [create]  {symbol} — {company_name} ({row.sector.strip()})")
            if dry_run:
                created += 1
                continue

            company = Company(
                company_name=company_name,
                legal_name=company_name,
                short_name=symbol,
                nse_symbol=symbol,
                sector_id=sector.sector_id if sector else None,
                status=CompanyStatus.ACTIVE,
            )
            db.add(company)
            db.flush()

            db.add(
                Security(
                    company_id=company.company_id,
                    exchange=ExchangeCode.NSE,
                    symbol=symbol,
                    security_name=company_name,
                    is_active=True,
                )
            )
            created += 1

        if dry_run:
            typer.echo(f"Seed dry-run: would create {created}, skip {skipped}.")
        else:
            db.commit()
            typer.echo(f"Seed done. Created {created}, skipped {skipped}.")
    finally:
        db.close()


def _get_or_create_sector(
    db: Session,
    sector_name: str,
    *,
    dry_run: bool,
) -> Sector | None:
    sector = db.scalar(select(Sector).where(Sector.sector_name == sector_name))
    if sector or dry_run:
        return sector

    sector = Sector(sector_name=sector_name)
    db.add(sector)
    db.flush()
    return sector


def _validate_ingest_period(
    period_from: Optional[str],
    period_to: Optional[str],
    last_quarters: Optional[int],
) -> None:
    has_range = bool(period_from or period_to)
    has_last = last_quarters is not None
    if has_range == has_last:
        typer.echo(
            "Bulk ingest requires exactly one period mode: "
            '--from/--to (both) or --last-quarters N.',
            err=True,
        )
        raise typer.Exit(code=2)
    if has_range and not (period_from and period_to):
        typer.echo('Both --from and --to are required for a quarter range.', err=True)
        raise typer.Exit(code=2)


def _run_bulk_ingest(
    *,
    input_path: Path,
    dry_run: bool,
    period_from: Optional[str],
    period_to: Optional[str],
    last_quarters: Optional[int],
    no_agent_fallback: bool,
    nse_scraper: bool,
    log_level: str,
) -> None:
    cmd = [
        sys.executable,
        "-m",
        "app.scripts.bulk_ingest",
        "--symbols-file",
        str(input_path),
        "--log-level",
        log_level,
    ]
    if last_quarters is not None:
        cmd.extend(["--last-quarters", str(last_quarters)])
    if period_from:
        cmd.extend(["--from", period_from])
    if period_to:
        cmd.extend(["--to", period_to])
    if dry_run:
        cmd.append("--dry-run")
    if no_agent_fallback:
        cmd.append("--no-agent-fallback")
    if nse_scraper:
        cmd.append("--nse-scraper")

    _run_subcommand(cmd, label="bulk_ingest")


def _run_subcommand(cmd: list[str], *, label: str) -> None:
    typer.echo(f"Starting {label}: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        typer.echo(f"{label} exited with code {result.returncode}", err=True)
        raise typer.Exit(code=result.returncode)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
