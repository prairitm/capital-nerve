"""Wire formats for the exchange-filings tier.

`ExchangeFiling` is the unified representation a `bse_client` /
`nse_client` row collapses to. `BSE_CATEGORY_MAP` and `NSE_CATEGORY_MAP`
translate exchange-specific category strings into our canonical
`DocumentType` enum.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, Optional

from app.db.enums import DocumentType


# ---------------------------------------------------------------------------
# Filing rows
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExchangeFiling:
    """One row from BSE or NSE's corporate-announcement feed.

    Categorisation happens at parse time: filings whose category isn't in
    the relevant map come back with ``document_type=None`` and are
    dropped by `discover_period_assets`.
    """

    source: Literal["bse", "nse"]
    company_id_at_source: str  # BSE scrip code or NSE symbol
    filing_date: datetime
    headline: str
    category: str
    subcategory: Optional[str]
    attachment_url: str
    document_type: Optional[DocumentType]
    source_page: Optional[str] = None
    raw: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Category mappings
# ---------------------------------------------------------------------------
#
# The *_CATEGORY_MAP dicts translate exchange-specific (CATEGORYNAME,
# SUBCATNAME / subject) tuples into a `DocumentType`. The first matching
# entry wins. ``None`` in the subcategory slot is a wildcard.


BSE_CATEGORY_MAP: dict[tuple[str, Optional[str]], DocumentType] = {
    # Result PDFs
    ("Result", None): DocumentType.FINANCIAL_RESULT,
    ("Company Update", "Financial Result"): DocumentType.FINANCIAL_RESULT,
    ("Integrated Filing(Financial)", None): DocumentType.FINANCIAL_RESULT,
    # Concall transcripts / audio recordings
    ("Analysts/Institutional Investor Meet", None): DocumentType.CONCALL_TRANSCRIPT,
    ("Earnings Call Transcript / Audio Recording", None): DocumentType.CONCALL_TRANSCRIPT,
    ("Corp. Action", "Earnings Call Transcript"): DocumentType.CONCALL_TRANSCRIPT,
    ("Company Update", "Earnings Call Transcript"): DocumentType.CONCALL_TRANSCRIPT,
    # Investor presentations
    ("Investor Presentation", None): DocumentType.INVESTOR_PRESENTATION,
    ("Company Update", "Investor Presentation"): DocumentType.INVESTOR_PRESENTATION,
    ("Corp. Action", "Investor Presentation"): DocumentType.INVESTOR_PRESENTATION,
    # Annual report
    ("Annual Report", None): DocumentType.ANNUAL_REPORT,
    ("Company Update", "Annual Report"): DocumentType.ANNUAL_REPORT,
}


NSE_CATEGORY_MAP: dict[tuple[str, Optional[str]], DocumentType] = {
    # Results
    ("Financial Results", None): DocumentType.FINANCIAL_RESULT,
    ("Integrated Filing- Financial", None): DocumentType.FINANCIAL_RESULT,
    # Transcripts
    ("Earnings Call Transcript", None): DocumentType.CONCALL_TRANSCRIPT,
    ("Analysts/Institutional Investor Meet/Con. Call Updates", None): DocumentType.CONCALL_TRANSCRIPT,
    ("Earnings Call Transcript / Audio Recording", None): DocumentType.CONCALL_TRANSCRIPT,
    # Presentations
    ("Investor Presentation", None): DocumentType.INVESTOR_PRESENTATION,
    # Annual report
    ("Annual Report", None): DocumentType.ANNUAL_REPORT,
}


def map_bse_category(category: str, subcategory: Optional[str]) -> Optional[DocumentType]:
    """Look up `(category, subcategory)` against `BSE_CATEGORY_MAP`.

    Tries exact match first; falls back to wildcard (subcategory=None).
    """
    return _lookup(BSE_CATEGORY_MAP, category, subcategory)


def map_nse_category(category: str, subcategory: Optional[str]) -> Optional[DocumentType]:
    return _lookup(NSE_CATEGORY_MAP, category, subcategory)


def _lookup(
    table: dict[tuple[str, Optional[str]], DocumentType],
    category: str,
    subcategory: Optional[str],
) -> Optional[DocumentType]:
    cat = (category or "").strip()
    sub = (subcategory or "").strip() or None
    if (cat, sub) in table:
        return table[(cat, sub)]
    if (cat, None) in table:
        return table[(cat, None)]
    return None


# ---------------------------------------------------------------------------
# Filing-window math
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FilingWindow:
    """Inclusive date range over which we expect a quarter's filings to land."""

    start: date
    end: date

    @classmethod
    def for_period(cls, period_start: date, period_end: date, *, is_annual: bool) -> "FilingWindow":
        """Quarterly filings normally arrive within ~45 days; transcripts
        push that to ~60 days. Annual reports legally have until 6 months
        after FY-end."""
        from datetime import timedelta

        if is_annual:
            delta = timedelta(days=180)
        else:
            delta = timedelta(days=60)
        return cls(start=period_end + timedelta(days=1), end=period_end + delta)


__all__ = [
    "BSE_CATEGORY_MAP",
    "NSE_CATEGORY_MAP",
    "ExchangeFiling",
    "FilingWindow",
    "map_bse_category",
    "map_nse_category",
]
