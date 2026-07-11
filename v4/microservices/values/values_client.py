"""HTTP client helpers for the Step 4 values microservice."""

from __future__ import annotations

import requests

from values_config import settings

PAGE_URL = "https://www.nseindia.com/companies-listing/corporate-filings-announcements"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": PAGE_URL,
}


def download_pdf(pdf_url: str) -> bytes:
    response = requests.get(
        pdf_url,
        headers=HEADERS,
        timeout=settings.request_timeout_seconds,
    )
    response.raise_for_status()
    return response.content
