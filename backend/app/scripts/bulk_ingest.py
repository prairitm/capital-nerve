"""Bulk IR-discovery ingest CLI.

For every `Company` row in the DB, ask an OpenAI Agents SDK + WebSearch
agent to locate the financial-results PDF, concall transcript, and
investor presentation for each quarter (and optionally annual report) in
the requested time period. Download each PDF into the canonical sha256
store + a human-browsable mirror, then run the same
`run_pipeline_for_document` that `POST /ingest/upload` queues.

Usage examples (run from ``backend/``)::

    python -m app.scripts.bulk_ingest --from "Q1 FY25-26" --to "Q3 FY25-26"
    python -m app.scripts.bulk_ingest --start 2024-04-01 --end 2026-03-31
    python -m app.scripts.bulk_ingest --last-quarters 6
    python -m app.scripts.bulk_ingest --symbols RELIANCE,TCS --from "Q3 FY25-26" --to "Q3 FY25-26" --dry-run

The CLI reads `OPENAI_API_KEY`, `IR_AGENT_MODEL`, `IR_AGENT_CONCURRENCY`,
and `IR_AGENT_RUNS_DIR` from the same `.env` the FastAPI app uses.
"""
from __future__ import annotations

# Load backend/.env into os.environ before Settings / Agents SDK initialise.
from app.core.env import bootstrap_cli_env, ensure_openai_api_key

bootstrap_cli_env()

import asyncio
import json
import logging
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.enums import UserType
from app.db.session import SessionLocal
from app.models.master import Company
from app.models.user import AppUser
from app.services.ir_discovery.agent import find_period_assets
from app.services.ir_discovery.exchange import (
    DiscoveryResult,
    discover_period_assets,
)
from app.services.ir_discovery.exchange.discover import merge_with_agent
from app.services.ir_discovery.ingest import IngestOutcome, ingest_one
from app.services.ir_discovery.periods import PeriodRangeError, expand_range
from app.services.ir_discovery.schemas import (
    DOC_TYPE_BY_ASSET_KEY,
    CompanyRef,
    CompanyTarget,
    PeriodAssetSet,
    PeriodSpec,
)


logger = logging.getLogger("app.scripts.bulk_ingest")


app = typer.Typer(
    add_completion=False,
    help=(
        "Bulk-fetch quarterly results / concall transcripts / presentations "
        "for every Company in the DB across the requested time period."
    ),
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def run(
    period_from: Optional[str] = typer.Option(
        None,
        "--from",
        help='Start of quarter range, e.g. "Q1 FY25-26".',
    ),
    period_to: Optional[str] = typer.Option(
        None,
        "--to",
        help='End of quarter range, e.g. "Q3 FY25-26".',
    ),
    start_date: Optional[datetime] = typer.Option(
        None,
        "--start",
        formats=["%Y-%m-%d"],
        help="Start of date range (inclusive). Format YYYY-MM-DD.",
    ),
    end_date: Optional[datetime] = typer.Option(
        None,
        "--end",
        formats=["%Y-%m-%d"],
        help="End of date range (inclusive). Format YYYY-MM-DD.",
    ),
    last_quarters: Optional[int] = typer.Option(
        None,
        "--last-quarters",
        help="Rolling window: number of most recent quarters to include.",
    ),
    symbols: Optional[str] = typer.Option(
        None,
        "--symbols",
        help="Comma-separated NSE symbols. Defaults to every Company in the DB.",
    ),
    doc_types: Optional[str] = typer.Option(
        None,
        "--doc-types",
        help=(
            "Comma-separated asset keys to ingest. One or more of: "
            "financial_report_pdf, transcript, presentation, annual_report. "
            "Defaults to all four."
        ),
    ),
    include_annual: bool = typer.Option(
        False,
        "--include-annual",
        help="Also fetch the annual report PDF for every FY whose Q4 is in range.",
    ),
    concurrency: Optional[int] = typer.Option(
        None,
        "--concurrency",
        help="Max parallel agent calls. Defaults to settings.IR_AGENT_CONCURRENCY.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Run agent discovery only; print the planned URLs and exit. No downloads, no DB writes.",
    ),
    skip_pipeline: bool = typer.Option(
        False,
        "--skip-pipeline",
        help="Persist SourceDocument / ExtractionJob rows but do not run the pipeline. Worker will drain.",
    ),
    force_reextract: bool = typer.Option(
        False,
        "--force-reextract",
        help=(
            "Re-run the pipeline even when the same file hash was already "
            "extracted successfully. Default: skip pipeline for completed duplicates."
        ),
    ),
    no_agent_fallback: bool = typer.Option(
        False,
        "--no-agent-fallback",
        help=(
            "Skip the OpenAI Agents WebSearch fallback for asset slots the BSE / NSE "
            "tier-1 didn't cover. Useful for a deterministic, free, exchange-only run."
        ),
    ),
    agent_only: bool = typer.Option(
        False,
        "--agent-only",
        help=(
            "Skip the BSE / NSE tier-1 entirely and rely solely on the OpenAI "
            "Agents WebSearch path. Mirrors `--no-agent-fallback`; mutually "
            "exclusive with it."
        ),
    ),
    admin_email: Optional[str] = typer.Option(
        None,
        "--admin-email",
        help=(
            "AppUser email to stamp on ExtractionJob.meta.queued_by_user_id. "
            "Defaults to the first AppUser with user_type=ADMIN."
        ),
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Python logging level (DEBUG / INFO / WARNING / ERROR).",
    ),
) -> None:
    """Run the bulk IR-discovery ingest."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    if no_agent_fallback and agent_only:
        typer.echo(
            "--no-agent-fallback and --agent-only are mutually exclusive: "
            "the first disables tier-2, the second disables tier-1.",
            err=True,
        )
        raise typer.Exit(code=2)

    if not no_agent_fallback:
        try:
            ensure_openai_api_key()
        except RuntimeError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc

    try:
        period_specs = expand_range(
            period_from=period_from,
            period_to=period_to,
            start_date=start_date.date() if isinstance(start_date, datetime) else start_date,
            end_date=end_date.date() if isinstance(end_date, datetime) else end_date,
            last_quarters=last_quarters,
            include_annual=include_annual,
        )
    except PeriodRangeError as exc:
        typer.echo(f"Bad period inputs: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    asset_keys = _parse_doc_types(doc_types)
    target_symbols = _parse_symbols(symbols)
    concurrency = concurrency or settings.IR_AGENT_CONCURRENCY

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    log_path = settings.ir_agent_runs_path / run_id / "run.log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    typer.echo(f"Run id: {run_id}")
    typer.echo(f"Periods ({len(period_specs)}): {[p.display_label for p in period_specs]}")

    db = SessionLocal()
    try:
        companies = _load_companies(db, target_symbols)
        if not companies:
            typer.echo("No companies match the given filter; aborting.", err=True)
            raise typer.Exit(code=2)

        admin_id: Optional[int] = None
        if not dry_run:
            admin_id = _resolve_admin_user_id(db, admin_email)

        typer.echo(f"Companies ({len(companies)}): {[c.nse_symbol or c.company_name for c in companies]}")
        typer.echo(f"Asset keys: {list(asset_keys)}")
        typer.echo(f"Concurrency: {concurrency}")
        typer.echo(f"Dry run: {dry_run}; skip pipeline: {skip_pipeline}")
        typer.echo(
            f"Tiers: exchange={'off' if agent_only else 'on'}, "
            f"agent={'off' if no_agent_fallback else 'on'}"
        )
        typer.echo(f"Run log: {log_path}")
    finally:
        db.close()

    failures = asyncio.run(
        _run_async(
            companies=companies,
            periods=period_specs,
            asset_keys=asset_keys,
            concurrency=concurrency,
            run_id=run_id,
            log_path=log_path,
            dry_run=dry_run,
            skip_pipeline=skip_pipeline,
            no_agent_fallback=no_agent_fallback,
            agent_only=agent_only,
            force_reextract=force_reextract,
            admin_user_id=admin_id,
        )
    )

    typer.echo(f"Done. Run log: {log_path}")
    if failures:
        typer.echo(f"Completed with {failures} pair-level failure(s); see run log for details.", err=True)
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Async driver
# ---------------------------------------------------------------------------


async def _run_async(
    *,
    companies: list[CompanyTarget],
    periods: list[PeriodSpec],
    asset_keys: tuple[str, ...],
    concurrency: int,
    run_id: str,
    log_path: Path,
    dry_run: bool,
    skip_pipeline: bool,
    no_agent_fallback: bool,
    agent_only: bool,
    force_reextract: bool,
    admin_user_id: Optional[int],
) -> int:
    """Returns the count of pair-level failures.

    Two-tier discovery per pair (either tier may be disabled):

    1. ``exchange.discover_period_assets`` — deterministic BSE-first,
       NSE-fallback corporate-filings client. Skipped entirely when
       ``--agent-only`` is set.
    2. ``agent.find_period_assets`` — invoked when at least one slot
       is still missing. Skipped entirely when ``--no-agent-fallback``
       is set.
    """
    semaphore = asyncio.Semaphore(max(1, concurrency))
    failures = 0
    log_fh = log_path.open("a", encoding="utf-8")

    async def _process_pair(company: CompanyTarget, period: PeriodSpec) -> None:
        nonlocal failures
        async with semaphore:
            # ---- Tier 1: BSE/NSE corporate filings ----
            if agent_only:
                discovery = _empty_discovery(company, period)
            else:
                discovery = await _run_exchange_tier(company, period, asset_keys)

            # ---- Tier 2: agent fallback ----
            # The agent runs whenever any slot is missing; we then merge
            # its results so empty slots get a primary URL AND already-
            # filled slots get an agent URL stashed as a download-time
            # fallback (see merge_with_agent).
            missing = discovery.missing_keys(asset_keys)
            if missing and not no_agent_fallback:
                try:
                    agent_assets = await find_period_assets(company, period)
                except Exception as exc:
                    failures += 1
                    logger.exception(
                        "Agent fallback crashed for %s / %s",
                        company.nse_symbol or company.company_name,
                        period.display_label,
                    )
                    _log(
                        log_fh,
                        _agent_error_record(run_id, company, period, exc, missing),
                    )
                    # We still have the exchange-tier hits; carry on.
                else:
                    discovery = merge_with_agent(
                        discovery,
                        agent_assets,
                        keys_to_fill=asset_keys,
                    )

        if dry_run:
            _log(
                log_fh,
                _dry_run_record(
                    run_id,
                    company,
                    period,
                    discovery.assets,
                    asset_keys,
                    discovery.source_by_asset_key,
                    discovery.fallback_by_asset_key,
                ),
            )
            return

        outcome = await asyncio.to_thread(
            _ingest_pair_blocking,
            company,
            period,
            discovery.assets,
            asset_keys,
            admin_user_id,
            skip_pipeline,
            discovery.source_by_asset_key,
            discovery.fallback_by_asset_key,
            force_reextract,
        )
        if outcome.failures:
            failures += outcome.failures
        _log(log_fh, _outcome_record(run_id, outcome))

    tasks = [
        _process_pair(c, p)
        for c in companies
        for p in periods
    ]
    await asyncio.gather(*tasks)
    log_fh.close()
    return failures


async def _run_exchange_tier(
    company: CompanyTarget,
    period: PeriodSpec,
    asset_keys: tuple[str, ...],
) -> DiscoveryResult:
    """Run tier-1 with a short-lived session for lazy ``bse_code`` resolution.

    Failures degrade to an empty ``DiscoveryResult`` so the agent
    fallback (or simply-empty result, with ``--no-agent-fallback``) takes
    over.
    """
    db = await asyncio.to_thread(SessionLocal)
    try:
        try:
            return await discover_period_assets(
                company,
                period,
                db=db,
                asset_keys=asset_keys,
            )
        except Exception:
            logger.exception(
                "Tier-1 discovery crashed for %s / %s",
                company.nse_symbol or company.company_name,
                period.display_label,
            )
            return _empty_discovery(company, period)
    finally:
        await asyncio.to_thread(db.close)


def _empty_discovery(
    company: CompanyTarget, period: PeriodSpec
) -> DiscoveryResult:
    """The "no tier-1 data" baseline used by ``--agent-only`` and by the
    tier-1 crash branch. Every slot starts empty so the agent fills them
    all as primaries on the next merge step."""
    return DiscoveryResult(
        assets=PeriodAssetSet(
            company=CompanyRef(
                symbol=company.nse_symbol,
                name=company.company_name,
            ),
            period=period.display_label,
        ),
        source_by_asset_key={},
        fallback_by_asset_key={},
    )


def _ingest_pair_blocking(
    company: CompanyTarget,
    period: PeriodSpec,
    assets: PeriodAssetSet,
    asset_keys: tuple[str, ...],
    admin_user_id: Optional[int],
    skip_pipeline: bool,
    discovery_source_by_key: dict[str, str],
    fallback_by_asset_key: dict[str, list],
    force_reextract: bool,
) -> IngestOutcome:
    """Sync wrapper used inside ``asyncio.to_thread`` so DB calls don't block the loop."""
    db = SessionLocal()
    try:
        assert admin_user_id is not None  # _run_async resolves this before dispatching
        return ingest_one(
            db,
            company=company,
            period=period,
            assets=assets,
            asset_keys=asset_keys,
            queued_by_user_id=admin_user_id,
            skip_pipeline=skip_pipeline,
            discovery_source_by_key=discovery_source_by_key,
            fallback_by_asset_key=fallback_by_asset_key,
            force_reextract=force_reextract,
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_doc_types(value: Optional[str]) -> tuple[str, ...]:
    if not value:
        return tuple(DOC_TYPE_BY_ASSET_KEY.keys())
    keys = tuple(part.strip() for part in value.split(",") if part.strip())
    unknown = [k for k in keys if k not in DOC_TYPE_BY_ASSET_KEY]
    if unknown:
        raise typer.BadParameter(
            f"Unknown asset key(s): {unknown}. "
            f"Allowed: {sorted(DOC_TYPE_BY_ASSET_KEY)}"
        )
    return keys


def _parse_symbols(value: Optional[str]) -> Optional[set[str]]:
    if not value:
        return None
    return {s.strip().upper() for s in value.split(",") if s.strip()}


def _load_companies(db: Session, symbols: Optional[set[str]]) -> list[CompanyTarget]:
    stmt = select(Company)
    if symbols is not None:
        stmt = stmt.where(Company.nse_symbol.in_(symbols))
    rows = db.scalars(stmt.order_by(Company.company_id)).all()
    targets: list[CompanyTarget] = []
    skipped: list[str] = []
    for row in rows:
        if not row.nse_symbol:
            skipped.append(row.company_name)
            continue
        targets.append(
            CompanyTarget(
                company_id=row.company_id,
                company_name=row.company_name,
                nse_symbol=row.nse_symbol,
                bse_code=row.bse_code,
                investor_relations_url=row.investor_relations_url,
            )
        )
    if skipped:
        logger.warning(
            "Skipping %s company row(s) with no nse_symbol: %s",
            len(skipped),
            ", ".join(skipped),
        )
    return targets


def _resolve_admin_user_id(db: Session, admin_email: Optional[str]) -> int:
    if admin_email:
        user = db.scalar(select(AppUser).where(AppUser.email == admin_email))
        if not user:
            raise typer.BadParameter(f"--admin-email {admin_email!r} not found in app_users.")
        return user.user_id
    user = db.scalar(
        select(AppUser).where(AppUser.user_type == UserType.ADMIN).order_by(AppUser.user_id)
    )
    if not user:
        raise typer.BadParameter(
            "No AppUser with user_type=ADMIN exists. Pass --admin-email explicitly "
            "or bootstrap an admin via ADMIN_EMAIL/ADMIN_PASSWORD env vars."
        )
    return user.user_id


# ---------------------------------------------------------------------------
# JSONL log records
# ---------------------------------------------------------------------------


def _log(fh, record: dict) -> None:
    fh.write(json.dumps(record, default=_json_default) + "\n")
    fh.flush()


def _json_default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _agent_error_record(
    run_id: str,
    company: CompanyTarget,
    period: PeriodSpec,
    exc: BaseException,
    missing_keys: list[str] | None = None,
) -> dict:
    return {
        "run_id": run_id,
        "kind": "agent_error",
        "company": {"company_id": company.company_id, "nse_symbol": company.nse_symbol},
        "period": {"display_label": period.display_label},
        "missing_keys": missing_keys or [],
        "error": str(exc),
        "logged_at": datetime.now(timezone.utc),
    }


def _dry_run_record(
    run_id: str,
    company: CompanyTarget,
    period: PeriodSpec,
    assets: PeriodAssetSet,
    asset_keys: tuple[str, ...],
    source_by_key: dict[str, str] | None = None,
    fallback_by_key: dict[str, list] | None = None,
) -> dict:
    sources = source_by_key or {}
    fallbacks = fallback_by_key or {}
    discovered = {}
    for key in asset_keys:
        match = getattr(assets, key, None)
        if match is not None:
            discovered[key] = {
                "url": match.url,
                "title": match.title,
                "source_page": match.source_page,
                "discovery_source": sources.get(key),
                "fallbacks": [
                    {
                        "url": alt.url,
                        "title": alt.title,
                        "source": src,
                    }
                    for alt, src in fallbacks.get(key, [])
                ],
            }
    return {
        "run_id": run_id,
        "kind": "dry_run",
        "company": {"company_id": company.company_id, "nse_symbol": company.nse_symbol},
        "period": {"display_label": period.display_label},
        "echoed_period": assets.period,
        "assets": discovered,
        "notes": assets.notes,
        "logged_at": datetime.now(timezone.utc),
    }


def _outcome_record(run_id: str, outcome: IngestOutcome) -> dict:
    payload = outcome.to_jsonable()
    payload["run_id"] = run_id
    payload["kind"] = "ingest_outcome"
    payload["logged_at"] = datetime.now(timezone.utc).isoformat()
    return payload


def main() -> None:
    app()


if __name__ == "__main__":
    main()
