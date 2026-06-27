"""NSE corporate announcement client used by Step 2."""

from __future__ import annotations

from typing import Any

import requests

from event_config import settings

API_URL = "https://www.nseindia.com/api/NextApi/apiClient/GetQuoteApi"
HOMEPAGE = "https://www.nseindia.com"
PAGE_URL = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": PAGE_URL,
}


def fetch_corporate_announcements(
    symbol: str, from_date: str, to_date: str
) -> list[dict[str, Any]]:
    params = {
        "functionName": "getCorporateAnnouncement",
        "symbol": symbol,
        "marketApiType": "equities",
        "subject": "",
        "fromDate": from_date,
        "toDate": to_date,
    }
    session = requests.Session()
    session.headers.update(HEADERS)
    session.get(HOMEPAGE, timeout=settings.request_timeout_seconds)
    response = session.get(API_URL, params=params, timeout=settings.request_timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("NSE announcement response was not a list")
    return payload
