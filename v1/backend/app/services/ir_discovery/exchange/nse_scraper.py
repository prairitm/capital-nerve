"""NSE corporate-announcements scraper (tier-1 alternative).

A no-date-range variant of :mod:`nse_client`. The CLI hits

    GET https://www.nseindia.com/api/corporate-announcements
        ?index=equities&symbol=<SYM>&reqXbrl=false

once per symbol and gets back the full list of recent corporate
announcements. Each announcement is matched against the requested
:class:`PeriodSpec` by lowercased text markers extracted from the period
itself (quarter / FY label / period_end formatted several ways). The
latest filing per :class:`DocumentType` whose text matches is picked as
that slot's :class:`AssetMatch` and stamped with
``source = "nse_scraper"`` on the returned :class:`DiscoveryResult`.

This module is the deterministic, free, agent-bypassing path triggered
by the ``--nse-scraper`` flag on :mod:`app.scripts.bulk_ingest`. It is
mutually exclusive with the existing BSE / NSE-JSON tier-1 path and with
the OpenAI WebSearch agent fallback.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import Iterable, Optional

from app.db.enums import DocumentType
from app.services.ir_discovery.exchange.nse_client import (
    _ANN_PAGE_TEMPLATE,
    _NSESession,
    _parse_dt,
)
from app.services.ir_discovery.exchange.schemas import map_nse_category
from app.services.ir_discovery.schemas import (
    DOC_TYPE_BY_ASSET_KEY,
    AssetMatch,
    CompanyRef,
    CompanyTarget,
    PeriodAssetSet,
    PeriodSpec,
)


logger = logging.getLogger(__name__)


SOURCE_LABEL = "nse_scraper"

# Must match ``ingest_common.fetch_document_from_url`` — only these suffixes
# can be downloaded and run through the pipeline.
_INGESTIBLE_URL_SUFFIXES = (".pdf", ".txt", ".md")


# Importing DiscoveryResult at module load time would be a circular import
# (discover -> nse_client/etc -> .). We re-import lazily inside the
# discover function instead. The dataclass shape is part of the
# `exchange` package surface so consumers never see this dodge.


_MONTH_NAMES = {
    1: ("january", "jan"),
    2: ("february", "feb"),
    3: ("march", "mar"),
    4: ("april", "apr"),
    5: ("may", "may"),
    6: ("june", "jun"),
    7: ("july", "jul"),
    8: ("august", "aug"),
    9: ("september", "sep", "sept"),
    10: ("october", "oct"),
    11: ("november", "nov"),
    12: ("december", "dec"),
}


# ---------------------------------------------------------------------------
# Internal scraper row
# ---------------------------------------------------------------------------


class _ScraperFiling:
    """Lightweight projection of one NSE announcement row used by the matcher."""

    __slots__ = ("attachment_url", "headline", "filing_date", "document_type", "text_blob")

    def __init__(
        self,
        *,
        attachment_url: str,
        headline: str,
        filing_date: datetime,
        document_type: Optional[DocumentType],
        text_blob: str,
    ) -> None:
        self.attachment_url = attachment_url
        self.headline = headline
        self.filing_date = filing_date
        self.document_type = document_type
        self.text_blob = text_blob


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def discover_period_assets_via_scraper(
    company: CompanyTarget,
    period: PeriodSpec,
    *,
    asset_keys: Optional[Iterable[str]] = None,
    session: Optional[_NSESession] = None,
    payload: Optional[object] = None,
):
    """NSE-only discovery: scrape recent announcements, match by period text.

    Args:
        company: Wire-format projection of the :class:`Company` row. Must
            carry ``nse_symbol`` — companies without a ticker are skipped
            silently (callers already log this at load time).
        period: The reporting window we're filling.
        asset_keys: Restrict the slots we try to fill. Defaults to all
            keys on :data:`DOC_TYPE_BY_ASSET_KEY` (filtered by period
            type: annual periods only get ``annual_report``).
        session: Optional shared :class:`_NSESession` so multiple periods
            for the same symbol reuse cookies.
        payload: Optional pre-fetched JSON payload (the
            ``corporate-announcements`` response). When provided we skip
            the HTTP call entirely — used by the CLI to cache one fetch
            per symbol across periods.

    Returns:
        A :class:`DiscoveryResult` whose ``assets`` is a partial
        :class:`PeriodAssetSet` and whose ``source_by_asset_key`` stamps
        ``"nse_scraper"`` on each filled key. Fallbacks are always empty
        (this tier intentionally produces no alternate URLs).
    """
    from app.services.ir_discovery.exchange.discover import DiscoveryResult

    keys = tuple(asset_keys) if asset_keys is not None else tuple(DOC_TYPE_BY_ASSET_KEY.keys())
    keys = tuple(_filter_keys_for_period(keys, period))

    empty_result = DiscoveryResult(
        assets=PeriodAssetSet(
            company=CompanyRef(symbol=company.nse_symbol, name=company.company_name),
            period=period.display_label,
        ),
        source_by_asset_key={},
        fallback_by_asset_key={},
    )

    if not company.nse_symbol:
        logger.info(
            "Skipping NSE scraper for %s/%s — no nse_symbol",
            company.company_name,
            period.display_label,
        )
        return empty_result

    if payload is None:
        payload = await asyncio.to_thread(_fetch_payload, company.nse_symbol, session)
    if payload is None:
        return empty_result

    rows = _coerce_rows(payload)
    filings = list(_parse_rows(rows))
    if not filings:
        return empty_result

    markers = _period_markers(period)
    needed_doc_types: dict[str, DocumentType] = {
        key: DOC_TYPE_BY_ASSET_KEY[key][1] for key in keys
    }

    candidates: dict[DocumentType, list[_ScraperFiling]] = {}
    for filing in filings:
        if filing.document_type is None or not filing.attachment_url:
            continue
        if filing.document_type not in needed_doc_types.values():
            continue
        if not _matches_period(filing.text_blob, markers):
            continue
        if not _is_ingestible_attachment_url(filing.attachment_url):
            continue
        candidates.setdefault(filing.document_type, []).append(filing)

    picks: dict[DocumentType, _ScraperFiling] = {
        doc_type: max(group, key=lambda f: f.filing_date)
        for doc_type, group in candidates.items()
    }

    assets = PeriodAssetSet(
        company=CompanyRef(symbol=company.nse_symbol, name=company.company_name),
        period=period.display_label,
    )
    source_by_asset_key: dict[str, str] = {}
    for key in keys:
        doc_type = needed_doc_types[key]
        filing = picks.get(doc_type)
        if filing is None:
            continue
        setattr(assets, key, _filing_to_asset_match(filing))
        source_by_asset_key[key] = SOURCE_LABEL

    return DiscoveryResult(
        assets=assets,
        source_by_asset_key=source_by_asset_key,
        fallback_by_asset_key={},
    )


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------


def _fetch_payload(symbol: str, session: Optional[_NSESession]) -> Optional[object]:
    """Single sync HTTP fetch. Empty list / None on failure."""
    params = {
        "index": "equities",
        "symbol": symbol.strip().upper(),
        "reqXbrl": "false",
    }
    own_session = session is None
    if own_session:
        session = _NSESession()
    try:
        try:
            return session.get_json(params)
        except Exception as exc:
            logger.warning("NSE scraper fetch failed for symbol=%s: %s", symbol, exc)
            return None
    finally:
        if own_session:
            session.close()


# ---------------------------------------------------------------------------
# Row parsing (mirrors nse_client._row_to_filing but produces our matcher row)
# ---------------------------------------------------------------------------


def _coerce_rows(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("data", "rows", "Table"):
            value = payload.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    logger.debug("NSE scraper response did not contain a known rows key")
    return []


def _parse_rows(rows: Iterable[dict]) -> Iterable[_ScraperFiling]:
    for row in rows:
        try:
            filing = _row_to_filing(row)
        except Exception:
            logger.debug("NSE scraper row failed to parse: %s", row, exc_info=True)
            continue
        if filing is not None:
            yield filing


def _row_to_filing(row: dict) -> Optional[_ScraperFiling]:
    attachment_url = (
        row.get("attchmntFile")
        or row.get("attachmntFile")
        or row.get("attachmentFile")
        or ""
    ).strip()
    if not attachment_url:
        return None
    if not attachment_url.lower().startswith(("http://", "https://")):
        attachment_url = "https://" + attachment_url.lstrip("/")
    if not _is_ingestible_attachment_url(attachment_url):
        return None

    category = (row.get("desc") or row.get("category") or row.get("subject") or "").strip()
    subcategory_raw = row.get("subCategory") or row.get("subjct")
    subcategory = (subcategory_raw or "").strip() or None

    headline = (
        row.get("attchmntText")
        or row.get("smIndustry")
        or row.get("desc")
        or category
        or "NSE filing"
    ).strip()

    filing_date_raw = (
        row.get("an_dt")
        or row.get("sort_date")
        or row.get("exchdisstime")
        or row.get("dissemDate")
    )
    filing_dt = _parse_dt(filing_date_raw)
    if filing_dt is None:
        return None

    text_blob = _build_text_blob(row, attachment_url, category, subcategory, headline)
    document_type = map_nse_category(category, subcategory)
    # NSE tags board-meeting prior intimations under the analyst-meet
    # category; require transcript-specific language before accepting.
    if document_type == DocumentType.CONCALL_TRANSCRIPT and not _has_transcript_signals(
        text_blob, attachment_url
    ):
        document_type = None
    if document_type is None:
        document_type = _infer_document_type(category, text_blob, attachment_url)

    return _ScraperFiling(
        attachment_url=attachment_url,
        headline=headline,
        filing_date=filing_dt,
        document_type=document_type,
        text_blob=text_blob,
    )


def _is_ingestible_attachment_url(url: str) -> bool:
    """True when ``ingest_common`` can download and pipeline this attachment."""
    path = url.split("?", 1)[0].lower()
    return any(path.endswith(suffix) for suffix in _INGESTIBLE_URL_SUFFIXES)


def _has_transcript_signals(text_blob: str, attachment_url: str) -> bool:
    """True when the row is an earnings-call transcript / AV recording filing."""
    if any(p in text_blob for p in _TRANSCRIPT_PHRASES):
        return True
    url_lower = attachment_url.lower()
    return "transcript" in url_lower and (
        "transcript" in text_blob or "avr" in url_lower or "transcriptav" in url_lower
    )


_TRANSCRIPT_PHRASES = (
    "audio / video recording and transcript",
    "audio/video recording and transcript",
    "transcript of the presentation",
    "transcript of the audio",
    "transcripts and audio",
    "transcript and audio",
    "earnings call transcript",
    "earning call transcript",
    "concall transcript",
)


def _infer_document_type(
    category: str,
    text_blob: str,
    attachment_url: str,
) -> Optional[DocumentType]:
    """Guess ``DocumentType`` from announcement text when NSE category is generic.

    Many result PDFs arrive under ``Outcome of Board Meeting``, ``Updates``,
    or ``Press Release`` rather than ``Financial Results``. The structured
    ``NSE_CATEGORY_MAP`` misses those; this helper recovers them from
    ``attchmntText`` / URL basename patterns.
    """
    cat = (category or "").strip().lower()

    if _has_transcript_signals(text_blob, attachment_url):
        return DocumentType.CONCALL_TRANSCRIPT
    url_lower = attachment_url.lower()

    if "investor presentation" in text_blob or cat == "investor presentation":
        return DocumentType.INVESTOR_PRESENTATION
    if ("presentation" in url_lower or "_ip." in url_lower) and "transcript" not in url_lower:
        if "presentation" in text_blob and "transcript" not in text_blob[:120]:
            return DocumentType.INVESTOR_PRESENTATION

    if "annual report" in text_blob:
        return DocumentType.ANNUAL_REPORT

    fin_phrases = (
        "financial results for the period",
        "financial results for the quarter",
        "unaudited financial results",
        "audited financial results",
        "standalone unaudited financial results",
        "consolidated unaudited financial results",
        "consolidated and standalone unaudited financial results",
        "integrated filing (financial)",
        "integrated filing- financial",
        "submitted to the exchange, the financial results",
        "submitted to the exchange, the consolidated",
        "media release - consolidated",
        "media release - consolidated and standalone",
    )
    url_fin_markers = (
        "sefr_",
        "se_result",
        "finresult",
        "mediarelease",
        "_mr.",
        "financialresult",
        "fin_result",
        "bm_se_",
    )
    fin_match = (
        any(p in text_blob for p in fin_phrases)
        or any(m in url_lower for m in url_fin_markers)
        or (cat == "outcome of board meeting" and "financial result" in text_blob)
        or (cat == "press release" and "financial result" in text_blob)
        or (
            cat == "updates"
            and "media release" in text_blob
            and ("financial result" in text_blob or "unaudited" in text_blob)
        )
    )
    if fin_match and not _is_prior_board_intimation(text_blob):
        return DocumentType.FINANCIAL_RESULT

    return None


def _is_prior_board_intimation(text_blob: str) -> bool:
    """Board-meeting notices mention results but are not the results PDF."""
    if "submitted to the exchange" in text_blob:
        return False
    return (
        "scheduled to be held" in text_blob
        or "prior intimation" in text_blob
        or "prior-intimation" in text_blob
    )


def _build_text_blob(
    row: dict,
    attachment_url: str,
    category: str,
    subcategory: Optional[str],
    headline: str,
) -> str:
    """Lowercased concatenation of every text-ish field on the row."""
    parts: list[str] = [headline, category]
    if subcategory:
        parts.append(subcategory)
    for key in ("attchmntText", "subject", "subjct", "desc", "smIndustry"):
        value = row.get(key)
        if isinstance(value, str) and value:
            parts.append(value)
    # The URL basename frequently carries the period (e.g.
    # ``RELIANCE_31122024_FinResult.pdf``).
    parts.append(attachment_url.rsplit("/", 1)[-1])
    return " ".join(parts).lower()


def _filing_to_asset_match(filing: _ScraperFiling) -> AssetMatch:
    return AssetMatch(
        url=filing.attachment_url,
        title=filing.headline,
        source_page=_ANN_PAGE_TEMPLATE,
    )


# ---------------------------------------------------------------------------
# Period filtering
# ---------------------------------------------------------------------------


def _filter_keys_for_period(keys: Iterable[str], period: PeriodSpec) -> Iterable[str]:
    """Annual periods only fill ``annual_report``; quarterly periods skip it.

    Mirrors :func:`exchange.discover._filter_keys_for_period`.
    """
    for key in keys:
        if period.is_annual and key != "annual_report":
            continue
        if not period.is_annual and key == "annual_report":
            continue
        yield key


# ---------------------------------------------------------------------------
# Period-text marker set
# ---------------------------------------------------------------------------


def _period_markers(period: PeriodSpec) -> set[str]:
    """Build the lowercased text-marker set used to match announcements.

    A row whose ``text_blob`` contains ANY one of these markers counts as
    a hit for ``period``. The set is intentionally generous (it includes
    half a dozen quarter/FY/date renderings) because NSE announcement
    subject lines are written by listed-company secretaries with no
    consistent format.
    """
    markers: set[str] = set()
    fy_year = period.fy_year
    # FY rendered as the canonical 4-2 form ("FY2024-25") and the common
    # short 2-2 form ("FY24-25").
    fy_long = f"fy{fy_year}-{(fy_year + 1) % 100:02d}"
    fy_short = f"fy{fy_year % 100:02d}-{(fy_year + 1) % 100:02d}"
    fy_compact = f"fy{fy_year % 100:02d}{(fy_year + 1) % 100:02d}"
    fy_next_short = f"fy{(fy_year + 1) % 100:02d}"  # e.g. "fy25" used loosely

    for token in (fy_long, fy_short, fy_compact):
        markers.add(token)
        markers.add(token.replace("fy", "fy "))

    if period.is_quarterly and period.quarter is not None:
        q = period.quarter
        # Quarter + FY combinations.
        for fy in (fy_long, fy_short, fy_compact, fy_next_short):
            markers.add(f"q{q} {fy}")
            markers.add(f"q{q}{fy}")
            markers.add(f"q{q}-{fy}")
        # Bare quarter codes (e.g. "Q3FY25", "Q3-FY25") in URL basenames.
        markers.add(f"q{q}fy{(fy_year + 1) % 100:02d}")
        markers.add(f"q{q}-fy{(fy_year + 1) % 100:02d}")

    markers.update(_date_markers(period.period_end, period.is_annual))
    return {m for m in markers if m}


def _date_markers(d: date, is_annual: bool) -> set[str]:
    """Date renderings the matcher looks for in announcement text.

    Covers ``31-12-2024``, ``31.12.2024``, ``31122024`` (URL form),
    ``31st december 2024``, ``december 2024``, ``31 december 2024``,
    ``december 31, 2024``. For annuals we also emit the "year ended"
    phrasings.
    """
    out: set[str] = set()
    dd = f"{d.day:02d}"
    mm = f"{d.month:02d}"
    yyyy = f"{d.year}"
    out.add(f"{dd}-{mm}-{yyyy}")
    out.add(f"{dd}.{mm}.{yyyy}")
    out.add(f"{dd}/{mm}/{yyyy}")
    out.add(f"{dd}{mm}{yyyy}")
    out.add(f"{yyyy}-{mm}-{dd}")

    names = _MONTH_NAMES.get(d.month, ())
    ordinal = _ordinal(d.day)
    for name in names:
        out.add(f"{name} {yyyy}")
        out.add(f"{name}, {yyyy}")
        out.add(f"{d.day} {name} {yyyy}")
        out.add(f"{dd} {name} {yyyy}")
        out.add(f"{ordinal} {name} {yyyy}")
        out.add(f"{ordinal} {name}, {yyyy}")
        out.add(f"{name} {d.day}, {yyyy}")
        out.add(f"{name} {dd}, {yyyy}")
        if is_annual:
            out.add(f"year ended {ordinal} {name} {yyyy}")
            out.add(f"year ended {name} {d.day}, {yyyy}")
            out.add(f"year ended {dd}-{mm}-{yyyy}")
        else:
            out.add(f"quarter ended {ordinal} {name} {yyyy}")
            out.add(f"quarter ended {name} {d.day}, {yyyy}")
            out.add(f"quarter ended {dd}-{mm}-{yyyy}")
    return out


def _ordinal(day: int) -> str:
    """English ordinal suffix for ``day`` (1 -> ``1st``, 22 -> ``22nd``)."""
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _matches_period(text_blob: str, markers: set[str]) -> bool:
    if not text_blob or not markers:
        return False
    return any(marker in text_blob for marker in markers)


__all__ = [
    "SOURCE_LABEL",
    "discover_period_assets_via_scraper",
]
