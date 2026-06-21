"""BSE corporate-announcements API client.

Endpoint: ``https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w``.
Documented behavior (verified empirically Apr 2026):

- ``scrip``        — BSE 6-digit scrip code (e.g. ``500325`` for RIL)
- ``strFromDate``  — yyyymmdd
- ``strToDate``    — yyyymmdd
- ``strSearch=P``  — paginated "all"
- ``strType=C``    — corporate filings (vs. "M" market filings)
- ``strCat=-1``    — all categories (we filter client-side via
  :func:`schemas.map_bse_category`).

Response shape: ``{"Table": [{...}, ...], "Table1": [{...}], ...}``.
``Table`` is the filings list. Each row has at minimum
``NEWSID``, ``NEWS_DT``, ``HEADLINE``, ``CATEGORYNAME``, ``SUBCATNAME``,
``ATTACHMENTNAME`` (sometimes a UUID, sometimes a full URL).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Iterable, Optional

import httpx

from app.services.ir_discovery.exchange.schemas import (
    ExchangeFiling,
    map_bse_category,
)


logger = logging.getLogger(__name__)


_API_BASE = "https://api.bseindia.com/BseIndiaAPI/api"
_LIST_ENDPOINT = f"{_API_BASE}/AnnGetData/w"
_ATTACH_BASE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive"
_ANN_PAGE = "https://www.bseindia.com/corporates/ann.html"

# BSE blocks generic Python user agents; this is a stable UA spoof.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.bseindia.com",
    "Referer": "https://www.bseindia.com/",
}


def list_filings(
    *,
    scrip: str,
    from_date: date,
    to_date: date,
    timeout: float = 30.0,
    client: Optional[httpx.Client] = None,
) -> list[ExchangeFiling]:
    """Return all corporate filings for ``scrip`` in ``[from_date, to_date]``.

    Returns an empty list (not an exception) when BSE returns no rows or
    the call fails — the orchestrator falls back to NSE / agent.

    A long-lived ``client`` may be passed in to share connection state
    across calls; otherwise one is created per call and closed.
    """
    params = {
        "pageno": "1",
        "strCat": "-1",
        "strPrevDate": from_date.strftime("%Y%m%d"),
        "strScrip": str(scrip).strip(),
        "strSearch": "P",
        "strToDate": to_date.strftime("%Y%m%d"),
        "strType": "C",
    }

    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=timeout, follow_redirects=True, headers=_HEADERS)
    try:
        try:
            response = client.get(_LIST_ENDPOINT, params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "BSE list_filings failed for scrip=%s [%s..%s]: %s",
                scrip,
                from_date.isoformat(),
                to_date.isoformat(),
                exc,
            )
            return []
        rows = _coerce_rows(payload)
        return list(_parse_rows(scrip, rows))
    finally:
        if own_client:
            client.close()


def _coerce_rows(payload: object) -> list[dict]:
    """BSE responses occasionally wrap the rows in different keys."""
    if isinstance(payload, dict):
        for key in ("Table", "table", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        # Some endpoints return ``{"d": "{...json...}"}``; log + bail.
        logger.debug("BSE response did not contain a known rows key: %s", list(payload))
        return []
    if isinstance(payload, list):
        return payload
    return []


def _parse_rows(scrip: str, rows: Iterable[dict]) -> Iterable[ExchangeFiling]:
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            filing = _row_to_filing(scrip, row)
        except Exception:  # one bad row shouldn't kill the whole list
            logger.debug("BSE row failed to parse: %s", row, exc_info=True)
            continue
        if filing is not None:
            yield filing


def _row_to_filing(scrip: str, row: dict) -> Optional[ExchangeFiling]:
    attachment = (row.get("ATTACHMENTNAME") or row.get("AttachmentName") or "").strip()
    if not attachment:
        return None
    if attachment.lower().startswith(("http://", "https://")):
        attachment_url = attachment
    else:
        attachment_url = f"{_ATTACH_BASE}/{attachment.lstrip('/')}"

    category = (row.get("CATEGORYNAME") or row.get("CategoryName") or "").strip()
    subcategory_raw = (
        row.get("SUBCATNAME")
        or row.get("SubCatName")
        or row.get("Sub_Category_Name")
        or ""
    )
    subcategory = subcategory_raw.strip() or None

    headline = (
        row.get("HEADLINE")
        or row.get("NEWSSUB")
        or row.get("Subject")
        or category
        or "BSE filing"
    ).strip()

    filing_date_raw = (
        row.get("NEWS_DT")
        or row.get("News_submission_dt")
        or row.get("DT_TM")
        or row.get("DissemDT")
    )
    filing_dt = _parse_dt(filing_date_raw)
    if filing_dt is None:
        return None

    document_type = map_bse_category(category, subcategory)
    return ExchangeFiling(
        source="bse",
        company_id_at_source=str(scrip).strip(),
        filing_date=filing_dt,
        headline=headline,
        category=category,
        subcategory=subcategory,
        attachment_url=attachment_url,
        document_type=document_type,
        source_page=_ANN_PAGE,
        raw=dict(row),
    )


def _parse_dt(value: object) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    # BSE returns variants like ``2025-10-15T18:42:00`` or
    # ``2025-10-15 18:42:00.123``. Try the common shapes.
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d",
        "%d-%b-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
    ):
        try:
            return datetime.strptime(text[: len(fmt) + 8], fmt)
        except ValueError:
            continue
    logger.debug("BSE filing_date unparseable: %r", text)
    return None


__all__ = ["list_filings"]
