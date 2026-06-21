"""NSE corporate-announcements API client.

Endpoint: ``https://www.nseindia.com/api/corporate-announcements``.
NSE blocks bot traffic without a session cookie. The fix is the same
pattern that ``nsetools`` / ``nse-utility`` libraries use:

1. Open a browser-like ``httpx.Client`` (real ``User-Agent``).
2. GET ``https://www.nseindia.com/`` once so NSE sets ``nsit`` /
   ``nseappid`` cookies.
3. Reuse that client for the JSON call.

A 401/403 retry is built in: if the warmup cookie expired between
calls we re-warm and try once more before giving up.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Iterable, Optional

import httpx

from app.services.ir_discovery.exchange.schemas import (
    ExchangeFiling,
    map_nse_category,
)


logger = logging.getLogger(__name__)


_API_ENDPOINT = "https://www.nseindia.com/api/corporate-announcements"
_HOMEPAGE = "https://www.nseindia.com"
_ANN_PAGE_TEMPLATE = (
    "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
}


class _NSESession:
    """Wraps an ``httpx.Client`` with one-shot cookie warmup."""

    def __init__(self, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers=_HEADERS,
        )
        self._warmed = False

    def warm(self) -> None:
        try:
            response = self._client.get(_HOMEPAGE)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.debug("NSE homepage warmup failed: %s", exc)
            return
        self._warmed = True

    def get_json(self, params: dict) -> Optional[object]:
        """GET the announcements API; returns parsed JSON or None on failure."""
        if not self._warmed:
            self.warm()
        response = self._client.get(_API_ENDPOINT, params=params)
        if response.status_code in (401, 403):
            # Cookie probably expired — one re-warm + retry.
            logger.debug("NSE returned %s; re-warming session", response.status_code)
            self._warmed = False
            self.warm()
            response = self._client.get(_API_ENDPOINT, params=params)
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("NSE list_filings HTTP error: %s", exc)
            return None
        try:
            return response.json()
        except ValueError as exc:
            logger.warning("NSE list_filings JSON decode failed: %s", exc)
            return None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "_NSESession":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def list_filings(
    *,
    symbol: str,
    from_date: date,
    to_date: date,
    timeout: float = 30.0,
    session: Optional[_NSESession] = None,
) -> list[ExchangeFiling]:
    """Return all corporate filings for ``symbol`` in ``[from_date, to_date]``.

    Empty list (not exception) on any failure — the orchestrator falls
    back to the agent.
    """
    params = {
        "index": "equities",
        "from_date": from_date.strftime("%d-%m-%Y"),
        "to_date": to_date.strftime("%d-%m-%Y"),
        "symbol": symbol.strip().upper(),
    }

    own_session = session is None
    if own_session:
        session = _NSESession(timeout=timeout)
    try:
        try:
            payload = session.get_json(params)
        except httpx.HTTPError as exc:
            logger.warning(
                "NSE list_filings failed for symbol=%s [%s..%s]: %s",
                symbol,
                from_date.isoformat(),
                to_date.isoformat(),
                exc,
            )
            return []
        if payload is None:
            return []
        rows = _coerce_rows(payload)
        return list(_parse_rows(symbol, rows))
    finally:
        if own_session:
            session.close()


def _coerce_rows(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "rows", "Table"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    logger.debug("NSE response did not contain a known rows key")
    return []


def _parse_rows(symbol: str, rows: Iterable[dict]) -> Iterable[ExchangeFiling]:
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            filing = _row_to_filing(symbol, row)
        except Exception:
            logger.debug("NSE row failed to parse: %s", row, exc_info=True)
            continue
        if filing is not None:
            yield filing


def _row_to_filing(symbol: str, row: dict) -> Optional[ExchangeFiling]:
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

    category = (row.get("desc") or row.get("category") or row.get("subject") or "").strip()
    subcategory_raw = row.get("subCategory") or row.get("subjct") or row.get("attchmntText")
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

    document_type = map_nse_category(category, subcategory)
    return ExchangeFiling(
        source="nse",
        company_id_at_source=symbol.strip().upper(),
        filing_date=filing_dt,
        headline=headline,
        category=category,
        subcategory=subcategory,
        attachment_url=attachment_url,
        document_type=document_type,
        source_page=_ANN_PAGE_TEMPLATE,
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
    for fmt in (
        "%d-%b-%Y %H:%M:%S",
        "%d-%b-%Y",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(text[: len(fmt) + 8], fmt)
        except ValueError:
            continue
    logger.debug("NSE filing_date unparseable: %r", text)
    return None


__all__ = ["list_filings"]
