"""Shared helpers for the document-intake paths.

Both the multipart upload endpoint (`POST /ingest/upload`) and the standalone
bulk-ingest CLI (`python -m app.scripts.bulk_ingest`) need to:

- Download an http(s) URL into bytes (with size limits + content-type sniffing).
- Resolve a `FinancialPeriod` from a `period_id` / label / event date, creating
  a quarterly period on the fly when necessary.
- Pick a sensible storage suffix from filename + content-type.

Keeping these helpers on a router module would force any non-HTTP caller to
pull in FastAPI just to ingest a document. They live here instead so the
router and the CLI can both import them without a circular dep.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional
from urllib.parse import unquote, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import DocumentType, PeriodType
from app.models.master import FinancialPeriod


# ---------------------------------------------------------------------------
# Canonical period labels (match seed_catalog FinancialPeriod.display_label)
# ---------------------------------------------------------------------------
#
# Quarterly:  Q{n} FY{yyyy}-{yy}   e.g. Q3 FY2025-26
# Annual:     FY{yyyy}-{yy}        e.g. FY2025-26
#
# Filesystem slug = display_label with spaces -> underscores:
#   Q3_FY2025-26, FY2025-26
#
# Mirror / export filename stem (company + period live in parent directories):
#   {document_type}   e.g. financial_result
# ---------------------------------------------------------------------------


def format_fy_label(fy_year: int) -> str:
    """Indian FY label with 4-digit start year and 2-digit end year."""
    return f"FY{fy_year}-{(fy_year + 1) % 100:02d}"


def format_quarterly_display_label(fy_year: int, quarter: int) -> str:
    """Canonical quarterly label, e.g. ``Q3 FY2025-26``."""
    return f"Q{quarter} {format_fy_label(fy_year)}"


def format_annual_display_label(fy_year: int) -> str:
    """Canonical annual label (same as ``fy_label``), e.g. ``FY2025-26``."""
    return format_fy_label(fy_year)


def period_slug_from_display_label(display_label: str) -> str:
    """Filesystem-safe period segment derived from a canonical display label."""
    return display_label.strip().replace(" ", "_")


def standard_document_basename(
    *,
    document_type: DocumentType,
) -> str:
    """Standard mirror filename stem (no extension).

    Example: ``financial_result``.
    """
    return document_type.value.lower()


def standard_document_title(
    *,
    symbol: str | None,
    display_label: str,
    document_type: DocumentType,
) -> str:
    """Canonical title for ``SourceDocument`` / ``CompanyEvent`` rows.

    Example: ``RELIANCE Q3 FY2025-26 Financial Results``.
    """
    pretty = _DOCUMENT_TYPE_TITLES.get(document_type, document_type.value.replace("_", " ").title())
    prefix = f"{symbol.strip().upper()} " if symbol else ""
    return f"{prefix}{display_label} {pretty}"


_DOCUMENT_TYPE_TITLES: dict[DocumentType, str] = {
    DocumentType.FINANCIAL_RESULT: "Financial Results",
    DocumentType.CONCALL_TRANSCRIPT: "Concall Transcript",
    DocumentType.INVESTOR_PRESENTATION: "Investor Presentation",
    DocumentType.ANNUAL_REPORT: "Annual Report",
    DocumentType.PRESS_RELEASE: "Press Release",
    DocumentType.EXCHANGE_FILING: "Exchange Filing",
    DocumentType.CREDIT_RATING_REPORT: "Credit Rating Report",
}


# ---------------------------------------------------------------------------
# URL fetching
# ---------------------------------------------------------------------------

MAX_URL_BYTES = 50 * 1024 * 1024

# Hosts that require a browser-style User-Agent + Referer to download
# attachments. Both BSE's CDN (`bseindia.com`) and NSE's archives
# (`nseindia.com` / `nsearchives.nseindia.com`) silently return HTML
# error pages or simply hang when called with an httpx default UA.
_BROWSER_DOWNLOAD_HOSTS = (
    "bseindia.com",
    "nseindia.com",
    "nsearchives.nseindia.com",
)

_BROWSER_DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "application/pdf;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# Magic-byte signatures we use to verify that a `.pdf` URL really
# returned a PDF and not an HTML error page.
_PDF_MAGIC = b"%PDF-"


class FetchError(ValueError):
    """Raised when the remote URL cannot be downloaded as a usable document."""


def fetch_document_from_url(url: str) -> tuple[bytes, str | None, str | None]:
    """Download a PDF / text filing from an http(s) URL.

    Returns ``(data, filename, content_type)``.

    Raises :class:`FetchError` (a `ValueError` subclass) on any failure mode
    so callers can surface a clean message to the user — the FastAPI router
    converts these into HTTP 400 and the CLI prints them to the run log.

    Also rejects responses that *look* like a PDF by URL extension but
    aren't actually PDFs (BSE's CDN routinely serves a 200 OK HTML
    homepage when an attachment id no longer exists, instead of a 404).
    """
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise FetchError("document_url must be a valid http or https URL")

    headers = _download_headers_for(parsed.netloc)
    timeout = _download_timeout_for(parsed.netloc)
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers=headers,
        ) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                content_type = (
                    response.headers.get("content-type", "").split(";")[0].strip()
                    or None
                )
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > MAX_URL_BYTES:
                        raise FetchError(
                            f"Remote document exceeds {MAX_URL_BYTES // (1024 * 1024)} MB limit"
                        )
                    chunks.append(chunk)
                data = b"".join(chunks)
    except httpx.HTTPStatusError as exc:
        raise FetchError(
            f"Could not fetch document_url: HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise FetchError(f"Could not fetch document_url: {exc}") from exc

    if not data:
        raise FetchError("Remote document is empty")

    filename = filename_from_url(parsed.path) or filename_from_content_type(content_type)
    suffix = suffix_for(filename, content_type)
    if suffix not in (".pdf", ".txt", ".md"):
        raise FetchError(
            "Remote document must be a PDF or plain text file "
            "(check the URL extension or Content-Type header)"
        )

    # If the URL / content-type promised a PDF, the body must actually be
    # one. BSE's CDN routinely returns a 200 OK with an HTML wrapper page
    # when an attachment id is missing — without this guard we'd happily
    # store that HTML as a `.pdf` and the pipeline would then run on
    # garbage.
    if suffix == ".pdf" and not data.startswith(_PDF_MAGIC):
        sniffed = _looks_like_html(data)
        detail = "looks like HTML" if sniffed else "is not a PDF (no %PDF- header)"
        raise FetchError(
            f"Remote document at {url} {detail}; refusing to ingest a non-PDF "
            f"response. content-type={content_type!r}"
        )

    return data, filename, content_type


def _download_headers_for(netloc: str) -> dict[str, str]:
    """Browser-style headers for hosts that block default httpx UAs."""
    host = (netloc or "").lower().rsplit(":", 1)[0]
    if any(host == suffix or host.endswith("." + suffix) for suffix in _BROWSER_DOWNLOAD_HOSTS):
        headers = dict(_BROWSER_DOWNLOAD_HEADERS)
        # Origin / Referer match the parent landing page so NSE / BSE
        # don't reject the request as cross-origin abuse.
        if "nseindia.com" in host:
            headers["Referer"] = "https://www.nseindia.com/"
        elif "bseindia.com" in host:
            headers["Referer"] = "https://www.bseindia.com/"
        return headers
    return {}


def _download_timeout_for(netloc: str) -> httpx.Timeout:
    """Generous timeouts for exchange CDNs which can be slow under load."""
    host = (netloc or "").lower().rsplit(":", 1)[0]
    if any(host == suffix or host.endswith("." + suffix) for suffix in _BROWSER_DOWNLOAD_HOSTS):
        return httpx.Timeout(60.0, connect=15.0)
    return httpx.Timeout(30.0, connect=10.0)


def _looks_like_html(data: bytes) -> bool:
    """Cheap sniff for HTML masquerading as PDF.

    Inspects only the first 1 KB so this stays O(1) regardless of
    payload size.
    """
    head = data[:1024].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html") or b"<head" in head[:512]


def filename_from_url(path: str) -> str | None:
    name = unquote(path.rsplit("/", 1)[-1]).strip()
    if name and "." in name:
        return name
    return None


def filename_from_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    if "pdf" in content_type:
        return "document.pdf"
    if "markdown" in content_type:
        return "document.md"
    if "text" in content_type:
        return "document.txt"
    return None


def suffix_for(filename: str | None, content_type: str | None) -> str:
    """Pick a sensible extension so storage files stay introspectable."""
    if filename and "." in filename:
        return "." + filename.rsplit(".", 1)[-1].lower()
    if content_type:
        if "pdf" in content_type:
            return ".pdf"
        if "markdown" in content_type:
            return ".md"
        if "text" in content_type:
            return ".txt"
    return ".bin"


# ---------------------------------------------------------------------------
# Period resolution
# ---------------------------------------------------------------------------

# e.g. "Q4 FY2025-26", "Q4 FY25-26", "q4 fy25/26"
PERIOD_LABEL_RE = re.compile(
    r"^\s*Q([1-4])\s+FY\s*(\d{2,4})\s*[-/]\s*(\d{2,4})\s*$",
    re.IGNORECASE,
)


class PeriodResolutionError(ValueError):
    """Raised when no `FinancialPeriod` can be located or constructed."""


def resolve_period_id(
    db: Session,
    *,
    period_id: int | None,
    period_label: str | None,
    event_date: date | None,
) -> int | None:
    """Find an existing financial period by id, label, or event date.

    Resolution order: ``period_id`` -> exact ``display_label`` -> parsed
    quarter/FY label -> date lookup -> create quarterly period from date or
    parsed label. Returns ``None`` only when all three inputs are absent.

    Raises :class:`PeriodResolutionError` when ``period_id`` is supplied but
    does not exist; callers convert that to HTTP 400 / log entry.
    """
    if period_id:
        if db.get(FinancialPeriod, period_id):
            return period_id
        raise PeriodResolutionError(f"period_id {period_id} not found")

    if period_label:
        raw = period_label.strip()
        # Normalise shorthand labels (Q3 FY25-26) to the canonical display form
        # before an exact match so we align with seed_catalog rows.
        label = raw
        parsed = parse_period_label(raw)
        if parsed:
            quarter, fy_year = parsed
            label = format_quarterly_display_label(fy_year, quarter)
        matched = db.scalar(
            select(FinancialPeriod).where(FinancialPeriod.display_label == label)
        )
        if matched:
            return matched.period_id
        if parsed:
            quarter, fy_year = parsed
            by_key = db.scalar(
                select(FinancialPeriod).where(
                    FinancialPeriod.fy_year == fy_year,
                    FinancialPeriod.quarter == quarter,
                    FinancialPeriod.period_type == PeriodType.QUARTERLY,
                )
            )
            if by_key:
                return by_key.period_id
            return create_period_from_quarter(db, fy_year=fy_year, quarter=quarter)

    if event_date:
        q = db.scalar(
            select(FinancialPeriod).where(
                FinancialPeriod.period_type == PeriodType.QUARTERLY,
                FinancialPeriod.period_start_date <= event_date,
                FinancialPeriod.period_end_date >= event_date,
            )
        )
        if q:
            return q.period_id
        return create_period_from_date(db, event_date)

    return None


def parse_period_label(label: str) -> tuple[int, int] | None:
    """Parse 'Q4 FY25-26' -> (quarter=4, fy_year=2025). Returns None if unrecognized."""
    m = PERIOD_LABEL_RE.match(label.strip())
    if not m:
        return None
    quarter = int(m.group(1))
    y1 = int(m.group(2))
    if len(m.group(2)) == 2:
        y1 = 2000 + y1 if y1 < 70 else 1900 + y1
    return quarter, y1


def quarter_date_bounds(fy_year: int, quarter: int) -> tuple[date, date, str, str]:
    """Indian-FY quarter window and canonical labels for ``fy_year`` + ``quarter``.

    FY ``fy_year`` runs from 1 April ``fy_year`` to 31 March ``fy_year + 1``.
    Q1 = Apr-Jun, Q2 = Jul-Sep, Q3 = Oct-Dec, Q4 = Jan-Mar (of the next civil year).
    """
    q_start_month = 4 + (quarter - 1) * 3
    q_start_year = fy_year if q_start_month <= 12 else fy_year + 1
    if q_start_month > 12:
        q_start_month -= 12
    start = date(q_start_year, q_start_month, 1)
    next_month = q_start_month + 3
    end_year = q_start_year + (next_month - 1) // 12
    end_month = ((next_month - 1) % 12) + 1
    end = date(end_year, end_month, 1) - timedelta(days=1)
    fy_label = format_fy_label(fy_year)
    display_label = format_quarterly_display_label(fy_year, quarter)
    return start, end, fy_label, display_label


def create_period_from_quarter(db: Session, *, fy_year: int, quarter: int) -> int:
    """Find or insert a quarterly period for the given FY + quarter."""
    existing = db.scalar(
        select(FinancialPeriod).where(
            FinancialPeriod.fy_year == fy_year,
            FinancialPeriod.quarter == quarter,
            FinancialPeriod.period_type == PeriodType.QUARTERLY,
        )
    )
    if existing:
        return existing.period_id
    start, end, fy_label, display_label = quarter_date_bounds(fy_year, quarter)
    period = FinancialPeriod(
        fy_year=fy_year,
        fy_label=fy_label,
        quarter=quarter,
        period_type=PeriodType.QUARTERLY,
        period_start_date=start,
        period_end_date=end,
        display_label=display_label,
    )
    db.add(period)
    db.flush()
    return period.period_id


def create_period_from_date(db: Session, d: date) -> int:
    """Create a quarterly `FinancialPeriod` whose window contains ``d``."""
    month = d.month
    quarter = ((month - 4) % 12) // 3 + 1
    fy_year = d.year if month >= 4 else d.year - 1
    return create_period_from_quarter(db, fy_year=fy_year, quarter=quarter)


def create_annual_period(db: Session, *, fy_year: int) -> int:
    """Find or insert an ANNUAL period for the given fiscal year.

    The catalog seeder already creates annual periods for the canonical
    range; this helper only kicks in when the bulk ingestor reaches a year
    outside that range.
    """
    existing = db.scalar(
        select(FinancialPeriod).where(
            FinancialPeriod.fy_year == fy_year,
            FinancialPeriod.period_type == PeriodType.ANNUAL,
        )
    )
    if existing:
        return existing.period_id
    start = date(fy_year, 4, 1)
    end = date(fy_year + 1, 3, 31)
    fy_label = format_fy_label(fy_year)
    period = FinancialPeriod(
        fy_year=fy_year,
        fy_label=fy_label,
        quarter=None,
        period_type=PeriodType.ANNUAL,
        period_start_date=start,
        period_end_date=end,
        display_label=format_annual_display_label(fy_year),
    )
    db.add(period)
    db.flush()
    return period.period_id


__all__ = [
    "MAX_URL_BYTES",
    "FetchError",
    "PeriodResolutionError",
    "fetch_document_from_url",
    "filename_from_url",
    "filename_from_content_type",
    "suffix_for",
    "resolve_period_id",
    "parse_period_label",
    "format_fy_label",
    "format_quarterly_display_label",
    "format_annual_display_label",
    "period_slug_from_display_label",
    "standard_document_basename",
    "standard_document_title",
    "quarter_date_bounds",
    "create_period_from_quarter",
    "create_period_from_date",
    "create_annual_period",
]
