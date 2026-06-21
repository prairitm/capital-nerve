"""Tier-1 IR discovery orchestrator (BSE-first, NSE-fallback).

Public entry point :func:`discover_period_assets` is the only function
the bulk ingest CLI imports from this package. Steps:

1. Compute the filing window for the period (``period_end + [1..60]`` for
   quarterly periods; ``+[1..180]`` for annual). This is where transcripts
   typically arrive, since they trail the result PDF by ~4-6 weeks.
2. If the company has a ``bse_code`` (resolving lazily via
   :func:`bse_master.lazy_resolve_bse_code` if missing), call
   :func:`bse_client.list_filings` and pick the latest filing per
   :class:`DocumentType` slot.
3. For any remaining slot, call :func:`nse_client.list_filings` (always
   tried — NSE coverage occasionally beats BSE for transcripts).
4. Return a :class:`PeriodAssetSet` populated only with what the
   exchanges had, and a parallel ``source_by_asset_key`` map so the
   caller can stamp ``discovery_source`` onto its JSONL log.

The function is async so it can run inside the existing
``asyncio.Semaphore`` in the CLI; the actual HTTP work is delegated to
``asyncio.to_thread`` because both clients use the sync ``httpx`` API.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.db.enums import DocumentType
from app.services.ir_discovery.exchange import bse_client, nse_client
from app.services.ir_discovery.exchange.bse_master import lazy_resolve_bse_code
from app.services.ir_discovery.exchange.schemas import (
    ExchangeFiling,
    FilingWindow,
)
from app.services.ir_discovery.schemas import (
    DOC_TYPE_BY_ASSET_KEY,
    AssetMatch,
    CompanyRef,
    CompanyTarget,
    PeriodAssetSet,
    PeriodSpec,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


@dataclass
class DiscoveryResult:
    """Pairs a `PeriodAssetSet` with per-asset provenance + fallbacks.

    ``assets`` carries the *primary* candidate per slot (whatever tier-1
    picked first, or whichever URL `merge_with_agent` decided was best).

    ``fallback_by_asset_key`` carries the rest. Each entry is a list of
    ``(AssetMatch, source)`` tuples that download-side code can try in
    order if the primary URL fails to download. Today this is how we
    survive BSE returning a 200 OK HTML wrapper instead of the real
    financial-result PDF: the agent's URL was already discovered, we
    just need to fall through to it.
    """

    assets: PeriodAssetSet
    # asset_key -> "bse" | "nse" | "agent"; absent keys are still empty
    # (and will be filled by the agent fallback if enabled).
    source_by_asset_key: dict[str, str] = field(default_factory=dict)
    # Secondary candidates per slot, in priority order. The primary
    # (mirrored on `assets`) is NOT duplicated here.
    fallback_by_asset_key: dict[str, list[tuple[AssetMatch, str]]] = field(
        default_factory=dict
    )

    def covered_keys(self) -> set[str]:
        return {
            key
            for key in DOC_TYPE_BY_ASSET_KEY
            if getattr(self.assets, key, None) is not None
        }

    def missing_keys(self, required: Iterable[str]) -> list[str]:
        return [k for k in required if getattr(self.assets, k, None) is None]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def discover_period_assets(
    company: CompanyTarget,
    period: PeriodSpec,
    *,
    db: Optional[Session] = None,
    asset_keys: Optional[Iterable[str]] = None,
    bse_window_days_after: Optional[int] = None,
) -> DiscoveryResult:
    """Discover IR assets for one ``(company, period)`` pair from BSE / NSE.

    Args:
        company: Wire-format projection of the `Company` row.
        period: The reporting window we're filling.
        db: Optional SQLAlchemy session — required only if the caller
            wants ``Company.bse_code`` to be lazy-resolved + persisted.
            When ``None``, missing BSE codes are simply logged.
        asset_keys: Restrict the slots we try to fill. Defaults to all
            keys on :data:`DOC_TYPE_BY_ASSET_KEY`.
        bse_window_days_after: Override for the filing-window length.

    Returns:
        A :class:`DiscoveryResult` whose `assets` is a partial
        `PeriodAssetSet` (only fields covered by the exchange tier are
        non-null).
    """
    keys = tuple(asset_keys) if asset_keys is not None else tuple(DOC_TYPE_BY_ASSET_KEY.keys())
    keys = tuple(_filter_keys_for_period(keys, period))
    window = _filing_window(period, override_days=bse_window_days_after)

    by_doc_type: dict[DocumentType, ExchangeFiling] = {}
    source_by_doc_type: dict[DocumentType, str] = {}
    fallback_by_doc_type: dict[DocumentType, list[tuple[ExchangeFiling, str]]] = {}

    # ---- BSE first ----
    bse_code = await _resolve_bse_code(company, db=db)
    if bse_code:
        try:
            bse_rows = await asyncio.to_thread(
                bse_client.list_filings,
                scrip=bse_code,
                from_date=window.start,
                to_date=window.end,
            )
        except Exception as exc:  # ditto — never crash the run
            logger.warning(
                "BSE list_filings raised for %s/%s: %s",
                company.nse_symbol or company.company_name,
                period.display_label,
                exc,
            )
            bse_rows = []
        for filing in _pick_latest_per_type(bse_rows):
            assert filing.document_type is not None
            by_doc_type[filing.document_type] = filing
            source_by_doc_type[filing.document_type] = "bse"
    else:
        logger.info(
            "Skipping BSE for %s/%s — no bse_code resolvable",
            company.nse_symbol or company.company_name,
            period.display_label,
        )

    # ---- NSE for whatever BSE didn't cover ----
    # When BSE already filled a slot we still record the NSE candidate
    # as a tier-1 fallback so download-side code can fall through if
    # BSE's URL turns out to be a 200 OK HTML wrapper page.
    needed_doc_types = {dt for key in keys for _, dt in [DOC_TYPE_BY_ASSET_KEY[key]]}
    if needed_doc_types and company.nse_symbol:
        try:
            nse_rows = await asyncio.to_thread(
                nse_client.list_filings,
                symbol=company.nse_symbol,
                from_date=window.start,
                to_date=window.end,
            )
        except Exception as exc:
            logger.warning(
                "NSE list_filings raised for %s/%s: %s",
                company.nse_symbol,
                period.display_label,
                exc,
            )
            nse_rows = []
        for filing in _pick_latest_per_type(nse_rows):
            assert filing.document_type is not None
            if filing.document_type not in by_doc_type:
                by_doc_type[filing.document_type] = filing
                source_by_doc_type[filing.document_type] = "nse"
            else:
                fallback_by_doc_type.setdefault(filing.document_type, []).append(
                    (filing, "nse")
                )

    # ---- Project filings into a PeriodAssetSet ----
    assets = PeriodAssetSet(
        company=CompanyRef(symbol=company.nse_symbol, name=company.company_name),
        period=period.display_label,
    )
    source_by_asset_key: dict[str, str] = {}
    fallback_by_asset_key: dict[str, list[tuple[AssetMatch, str]]] = {}
    for key in keys:
        _, doc_type = DOC_TYPE_BY_ASSET_KEY[key]
        filing = by_doc_type.get(doc_type)
        if filing is None:
            continue
        setattr(assets, key, _filing_to_asset_match(filing))
        source_by_asset_key[key] = source_by_doc_type[doc_type]
        fallbacks = fallback_by_doc_type.get(doc_type, [])
        if fallbacks:
            fallback_by_asset_key[key] = [
                (_filing_to_asset_match(f), src) for f, src in fallbacks
            ]

    return DiscoveryResult(
        assets=assets,
        source_by_asset_key=source_by_asset_key,
        fallback_by_asset_key=fallback_by_asset_key,
    )


# ---------------------------------------------------------------------------
# Merge helper (used by the CLI when the agent fallback fills gaps)
# ---------------------------------------------------------------------------


def merge_with_agent(
    exchange: DiscoveryResult,
    agent_assets: PeriodAssetSet,
    *,
    keys_to_fill: Iterable[str],
) -> DiscoveryResult:
    """Merge agent-discovered URLs into the exchange result.

    For each ``key`` in ``keys_to_fill``:

    - If the exchange tier left the slot empty, the agent's URL becomes
      the primary (``source = "agent"``).
    - If the exchange tier already filled the slot, the agent's URL is
      stashed as a *fallback* candidate for that slot. Download-side
      code will try the primary first, then fall through to fallbacks
      in priority order if the primary fails to download.

    The exchange tier therefore still wins on the happy path, but a
    broken BSE/NSE attachment no longer wastes the agent's research.
    """
    final = exchange.assets
    sources = dict(exchange.source_by_asset_key)
    fallbacks: dict[str, list[tuple[AssetMatch, str]]] = {
        k: list(v) for k, v in exchange.fallback_by_asset_key.items()
    }
    for key in keys_to_fill:
        agent_match = getattr(agent_assets, key, None)
        if agent_match is None:
            continue
        if getattr(final, key, None) is None:
            setattr(final, key, agent_match)
            sources[key] = "agent"
        else:
            fallbacks.setdefault(key, []).append((agent_match, "agent"))
    return DiscoveryResult(
        assets=final,
        source_by_asset_key=sources,
        fallback_by_asset_key=fallbacks,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _filter_keys_for_period(keys: Iterable[str], period: PeriodSpec) -> Iterable[str]:
    """Annual periods only fill ``annual_report``; quarterly periods skip it."""
    for key in keys:
        if period.is_annual and key != "annual_report":
            continue
        if not period.is_annual and key == "annual_report":
            continue
        yield key


def _filing_window(period: PeriodSpec, *, override_days: Optional[int]) -> FilingWindow:
    if override_days is not None:
        from datetime import timedelta

        return FilingWindow(
            start=period.period_end + timedelta(days=1),
            end=period.period_end + timedelta(days=int(override_days)),
        )
    return FilingWindow.for_period(
        period.period_start,
        period.period_end,
        is_annual=period.is_annual,
    )


def _pick_latest_per_type(filings: Iterable[ExchangeFiling]) -> Iterable[ExchangeFiling]:
    """Group filings by `document_type`, keep only the latest per group."""
    latest: dict[DocumentType, ExchangeFiling] = {}
    for filing in filings:
        if filing.document_type is None or not filing.attachment_url:
            continue
        existing = latest.get(filing.document_type)
        if existing is None or filing.filing_date > existing.filing_date:
            latest[filing.document_type] = filing
    return latest.values()


def _filing_to_asset_match(filing: ExchangeFiling) -> AssetMatch:
    return AssetMatch(
        url=filing.attachment_url,
        title=filing.headline,
        source_page=filing.source_page,
    )


async def _resolve_bse_code(
    company: CompanyTarget,
    *,
    db: Optional[Session],
) -> Optional[str]:
    if company.bse_code:
        return company.bse_code
    if db is None:
        return None

    # Master-list resolution can hit the network; offload to a thread so
    # we don't block the event loop.
    return await asyncio.to_thread(_lazy_resolve_via_db, db, company)


def _lazy_resolve_via_db(db: Session, company_target: CompanyTarget) -> Optional[str]:
    from app.models.master import Company

    company_row = db.get(Company, company_target.company_id)
    if company_row is None:
        return None
    return lazy_resolve_bse_code(db, company_row)


__all__ = [
    "DiscoveryResult",
    "discover_period_assets",
    "merge_with_agent",
]
