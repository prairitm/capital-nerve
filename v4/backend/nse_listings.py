"""Cached directory of companies in NSE's equity-segment security list."""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from datetime import datetime, timedelta
from typing import Any

import httpx

from app_db import get_app_conn, utc_iso, utc_now
from config import settings


logger = logging.getLogger(__name__)

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,*/*;q=0.8",
    "Referer": "https://www.nseindia.com/static/market-data/securities-available-for-trading",
}


def parse_nse_equity_csv(text: str) -> list[dict[str, str | None]]:
    """Normalize the official CSV while tolerating whitespace in its headers."""
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    rows: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for raw in reader:
        normalized = {str(key).strip().upper(): (value or "").strip() for key, value in raw.items()}
        symbol = normalized.get("SYMBOL", "").upper()
        name = normalized.get("NAME OF COMPANY", "")
        if not symbol or not name or symbol in seen:
            continue
        seen.add(symbol)
        rows.append(
            {
                "symbol": symbol,
                "company_name": name,
                "series": normalized.get("SERIES") or None,
                "listing_date": normalized.get("DATE OF LISTING") or None,
                "isin": normalized.get("ISIN NUMBER") or None,
            }
        )
    if not rows:
        raise ValueError("NSE equity CSV contained no valid company rows")
    return rows


def replace_nse_listings(rows: list[dict[str, Any]]) -> int:
    """Atomically mark the latest NSE snapshot active and retain stale rows as inactive."""
    if not rows:
        raise ValueError("Refusing to replace NSE directory with an empty snapshot")
    refreshed_at = utc_iso()
    with get_app_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE nse_listings SET is_active = 0, refreshed_at = ?", (refreshed_at,))
        conn.executemany(
            """
            INSERT INTO nse_listings(
                symbol, company_name, series, listing_date, isin, is_active, refreshed_at
            ) VALUES (?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                company_name = excluded.company_name,
                series = excluded.series,
                listing_date = excluded.listing_date,
                isin = excluded.isin,
                is_active = 1,
                refreshed_at = excluded.refreshed_at
            """,
            [
                (
                    row["symbol"],
                    row["company_name"],
                    row.get("series"),
                    row.get("listing_date"),
                    row.get("isin"),
                    refreshed_at,
                )
                for row in rows
            ],
        )
        conn.commit()
    return len(rows)


def nse_directory_is_due() -> bool:
    with get_app_conn() as conn:
        row = conn.execute(
            "SELECT MAX(refreshed_at) AS refreshed_at FROM nse_listings WHERE is_active = 1"
        ).fetchone()
    if row is None or not row["refreshed_at"]:
        return True
    try:
        refreshed_at = datetime.fromisoformat(row["refreshed_at"])
    except (TypeError, ValueError):
        return True
    if refreshed_at.tzinfo is None:
        refreshed_at = refreshed_at.replace(tzinfo=utc_now().tzinfo)
    return refreshed_at <= utc_now() - timedelta(hours=settings.nse_refresh_hours)


def refresh_nse_listings_if_due(*, force: bool = False) -> int | None:
    """Refresh the cache; callers may retain the last-known-good snapshot on failure."""
    if not force and not nse_directory_is_due():
        return None
    with httpx.Client(headers=NSE_HEADERS, follow_redirects=True) as client:
        response = client.get(
            settings.nse_equity_csv_url,
            timeout=settings.nse_request_timeout_seconds,
        )
        response.raise_for_status()
    count = replace_nse_listings(parse_nse_equity_csv(response.text))
    logger.info("Refreshed NSE company directory with %s entries", count)
    return count


def register_company_for_listing(listing: dict[str, Any]) -> dict[str, Any]:
    """Ask the Step 1 service—the analytics DB owner—to materialize a company."""
    symbol = str(listing["symbol"]).strip().upper()
    with httpx.Client() as client:
        response = client.post(
            f"{settings.company_service_url}/companies",
            json={
                "symbol": symbol,
                "name": listing.get("company_name"),
                "isin": listing.get("isin"),
            },
            timeout=settings.nse_request_timeout_seconds,
        )
        response.raise_for_status()
    payload = response.json()
    company = payload.get("company") if isinstance(payload, dict) else None
    expected_id = hashlib.sha256(f"{symbol}:NSE".encode()).hexdigest()
    if not isinstance(company, dict) or company.get("id") != expected_id:
        raise ValueError("Company service returned an invalid NSE company identity")
    return company
