"""Backfill ``Company.bse_code`` from the BSE listed-equity master list.

The catalog seed loads NSE symbols into ``Company.nse_symbol`` from
``experiment/5 -metascraper/src/companies.json`` (which has no BSE
codes), so the BSE-first IR discovery in
:mod:`app.services.ir_discovery.exchange.discover` would fall through
to NSE / agent for every issuer until those codes are populated.

This one-shot script downloads the full BSE master list, caches it
under ``var/bse_master/equity.json`` (TTL = ``BSE_MASTER_TTL_DAYS``),
and resolves each missing ``Company.bse_code`` by:

1. ISIN exact match  (highest confidence)
2. NSE-symbol exact match
3. Fuzzy match on ``company_name`` (`difflib.SequenceMatcher`,
   default cutoff 0.92)

For low-confidence (fuzzy) matches the script prompts the operator
unless ``--auto-accept`` is passed.

Usage (run from ``backend/``)::

    python -m app.scripts.resolve_bse_codes              # interactive
    python -m app.scripts.resolve_bse_codes --auto-accept  # CI / scripted
    python -m app.scripts.resolve_bse_codes --refresh    # ignore on-disk cache
    python -m app.scripts.resolve_bse_codes --dry-run    # preview, no writes
"""
from __future__ import annotations

# Load backend/.env so STORAGE_DIR / BSE_MASTER_TTL_DAYS resolve correctly.
from app.core.env import bootstrap_cli_env

bootstrap_cli_env()

import logging
from typing import Optional

import typer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.master import Company
from app.services.ir_discovery.exchange.bse_master import (
    BseScrip,
    ResolutionMatch,
    load_master,
    resolve,
)


logger = logging.getLogger("app.scripts.resolve_bse_codes")


app = typer.Typer(
    add_completion=False,
    help="Backfill `Company.bse_code` from the BSE listed-equity master list.",
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def run(
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Force-refresh the on-disk BSE master cache before resolving.",
    ),
    auto_accept: bool = typer.Option(
        False,
        "--auto-accept",
        help="Auto-accept fuzzy matches above the cutoff without prompting.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print what would be updated without writing to the DB.",
    ),
    fuzzy_cutoff: float = typer.Option(
        0.92,
        "--fuzzy-cutoff",
        min=0.5,
        max=1.0,
        help="Minimum SequenceMatcher ratio for accepting a fuzzy match.",
    ),
    symbols: Optional[str] = typer.Option(
        None,
        "--symbols",
        help="Comma-separated NSE symbols to limit resolution to (default: all rows missing bse_code).",
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

    typer.echo("Loading BSE master list...")
    master = load_master(force_refresh=refresh)
    if not master:
        typer.echo(
            "BSE master list is empty (network failure and no cache). Aborting.",
            err=True,
        )
        raise typer.Exit(code=2)
    typer.echo(f"Master list rows: {len(master)}")

    target_symbols = (
        {s.strip().upper() for s in symbols.split(",") if s.strip()}
        if symbols
        else None
    )

    db = SessionLocal()
    try:
        rows = _load_companies_missing_bse_code(db, target_symbols)
        if not rows:
            typer.echo("Every Company already has a bse_code. Nothing to do.")
            return

        typer.echo(f"Companies missing bse_code: {len(rows)}")

        accepted = 0
        skipped = 0
        for company in rows:
            match = resolve(
                isin=company.isin,
                nse_symbol=company.nse_symbol,
                company_name=company.company_name,
                master=master,
                fuzzy_cutoff=fuzzy_cutoff,
            )
            if match is None:
                typer.echo(
                    f"  [skip]  {_label(company)} — no high-confidence match",
                )
                skipped += 1
                continue

            if not _confirm(company, match, auto_accept=auto_accept):
                typer.echo(f"  [skip]  {_label(company)} — declined")
                skipped += 1
                continue

            typer.echo(
                f"  [{match.method:>10}@{match.score:.2f}]  "
                f"{_label(company)} -> {match.scrip_code} ({match.scrip_name})"
            )
            if not dry_run:
                company.bse_code = match.scrip_code
                db.add(company)
            accepted += 1

        if dry_run:
            typer.echo(
                f"Dry-run summary: would update {accepted}, skip {skipped}."
            )
        else:
            db.commit()
            typer.echo(f"Done. Updated {accepted}, skipped {skipped}.")
    finally:
        db.close()


def _load_companies_missing_bse_code(
    db: Session,
    target_symbols: Optional[set[str]],
) -> list[Company]:
    stmt = select(Company).where(Company.bse_code.is_(None))
    if target_symbols is not None:
        stmt = stmt.where(Company.nse_symbol.in_(target_symbols))
    return list(db.scalars(stmt.order_by(Company.company_id)))


def _label(company: Company) -> str:
    parts = [company.company_name]
    if company.nse_symbol:
        parts.append(f"({company.nse_symbol})")
    return " ".join(parts)


def _confirm(
    company: Company,
    match: ResolutionMatch,
    *,
    auto_accept: bool,
) -> bool:
    """Auto-accept exact methods; prompt for fuzzy unless `--auto-accept`."""
    if match.method in ("isin", "nse_symbol"):
        return True
    if auto_accept:
        return True
    prompt = (
        f"Fuzzy match for {_label(company)}:\n"
        f"  -> scrip_code={match.scrip_code} name={match.scrip_name!r} "
        f"score={match.score:.2f}\n"
        "Accept? [y/N] "
    )
    answer = typer.prompt(prompt, default="N", show_default=False)
    return answer.strip().lower().startswith("y")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
