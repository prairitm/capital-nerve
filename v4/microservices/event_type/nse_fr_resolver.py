"""Resolve the canonical NSE financial-results PDF from an announcement batch."""

from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime
from typing import Any

import requests

PdfReader = None


def _get_pdf_reader():
    global PdfReader
    if PdfReader is not None:
        return PdfReader
    try:
        from pypdf import PdfReader as reader
    except ImportError:
        try:
            from PyPDF2 import PdfReader as reader
        except ImportError as exc:
            raise ImportError("Install pypdf or PyPDF2 to classify financial-result PDFs") from exc
    PdfReader = reader
    return PdfReader

_PDF_MAGIC = b"%PDF-"
_NUMBER_RE = re.compile(r"(?<![\d.])(-?\d[\d,]*(?:\.\d+)?)(?![\d.])")

# url -> (pdf_hash, classification dict, pdf_bytes)
_PDF_CLASSIFICATION_CACHE: dict[str, tuple[str, dict[str, Any], bytes]] = {}

_POSITIVE_PHRASES = (
    r"statement of profit and loss",
    r"statement of (?:consolidated|standalone|unaudited|audited)?\s*financial",
    r"standalone statement of profit and loss",
    r"balance sheet",
    r"cash flow statement",
    r"(?:standalone|consolidated)\s+(?:unaudited|audited)\s+financial results",
    r"financial\s+r[eé]?sults for the (?:quarter|period|year) ended",
    r"financial results for the quarter and financial year",
    r"\bind as\b",
    r"regulation 33",
    r"limited review report",
    r"\bin crorel?\b",
    r"₹\s*in\s*(?:crore|lakh|million)",
    r"profit before tax",
    r"profit after tax",
    r"revenue from operations",
    r"independent auditor's report",
)

_HARD_EXCLUDED_CONTENT_PHRASES = (
    r"monitoring agency report",
    r"utilization of proceeds",
    r"certificate under regulation 74",
    r"regulation 74\s*\(\s*5\s*\)",
    r"postal ballot",
)

_SOFT_EXCLUDED_CONTENT_PHRASES = (
    r"monitoring agency",
    r"credit rating",
)

_CORE_FINANCIAL_PHRASES = (
    r"statement of profit and loss",
    r"statement of (?:consolidated|standalone|unaudited|audited)?\s*financial",
    r"financial\s+r[eé]?sults for the (?:quarter|period|year) ended",
    r"(?:standalone|consolidated)\s+(?:unaudited|audited)\s+financial results",
    r"revenue from operations",
    r"profit before tax",
    r"profit after tax",
)

_NEGATIVE_PHRASES = (
    r"record date for the purpose of",
    r"annual general meeting.{0,40}will be held",
    r"appointment of (?:mr\.|ms\.|shri)",
    r"change in director",
    r"conference call.{0,60}intimation",
    r"conference call will be held",
    r"intimation of conference call",
    r"link of recording",
    r"re-appointment of",
    r"trading window",
    r"prior intimation",
    r"scheduled to be held",
    r"dear sir/madam",
    r"kindly take the same on record",
    r"dial in and other details",
    r"monitoring agency",
    r"utilization of proceeds",
)

_POSITIVE_RES = [re.compile(p, re.IGNORECASE) for p in _POSITIVE_PHRASES]
_NEGATIVE_RES = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in _NEGATIVE_PHRASES]
_HARD_EXCLUDED_CONTENT_RES = [
    re.compile(p, re.IGNORECASE) for p in _HARD_EXCLUDED_CONTENT_PHRASES
]
_SOFT_EXCLUDED_CONTENT_RES = [
    re.compile(p, re.IGNORECASE) for p in _SOFT_EXCLUDED_CONTENT_PHRASES
]
_CORE_FINANCIAL_RES = [re.compile(p, re.IGNORECASE) for p in _CORE_FINANCIAL_PHRASES]

_STRONG_FIN_URL_MARKERS = (
    "financialresults",
    "financialresult",
    "finresult",
    "fin_result",
    "sefr_",
    "se_result",
    "bsenseoutcome",
    "financial_result",
    "results_",
)

_URL_FIN_MARKERS = (
    "bsenseoutcome",
    "outcomesigned",
    "outcome",
    "sefr_",
    "se_result",
    "finresult",
    "mediarelease",
    "_mr.",
    "financialresult",
    "fin_result",
    "results_",
)

_URL_EXCLUDED_MARKERS = (
    "monitoring_agency",
    "certificate745",
    "certificate_74",
    "reg74",
    "grantdisclosure",
    "priorintimation",
    "changeindirector",
    "investorpresentation",
    "presentation_with_ppt",
    "presentationwithppt",
    "transcript",
    "concall",
    "shlsigned",
    "shareholdersletter",
    "shareholderletter",
)

_EXCLUDED_EVENT_BUCKETS = frozenset({
    "Monitoring Agency Report",
    "AGM Intimation",
    "Record Date",
    "Director Appointment",
    "Director Change",
    "Board Meeting Intimation",
    "Earnings Call Intimation",
    "Earnings Call Audio Recording",
    "Earnings Call Transcript",
    "Investor Presentation",
    "Credit Rating",
    "Certificate under SEBI (Depositories and Participants) Regulations, 2018",
    "ESOP / Share Allotment",
})

_MISLINKED_BUCKETS = _EXCLUDED_EVENT_BUCKETS

_PERIOD_ENDED_RE = re.compile(
    r"(?:period|quarter|year|financial year)\s+ended\s+"
    r"(\d{1,2}(?:st|nd|rd|th)?\s+[a-z]+\s+\d{4}|"
    r"[a-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})",
    re.IGNORECASE,
)
_FY_TOKEN_RE = re.compile(r"q([1-4])fy(\d{2,4})", re.IGNORECASE)
_DATE_IN_URL_RE = re.compile(
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[_\s]?20\d{2}",
    re.IGNORECASE,
)
_DDMMYYYY_IN_URL_RE = re.compile(r"(?<!\d)(\d{8})(?!\d)")
_MONTH_TO_NAME = {
    1: "january", 2: "february", 3: "march", 4: "april", 5: "may", 6: "june",
    7: "july", 8: "august", 9: "september", 10: "october", 11: "november", 12: "december",
}
_MONTH_NAME_TO_NUM = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}


def parse_file_size_kb(raw: str | None) -> float | None:
    """Parse NSE fileSize strings like '32.83 MB' or '220.26 KB'."""
    if not raw:
        return None
    match = re.match(r"^\s*([\d.]+)\s*(KB|MB|GB)\s*$", raw.strip(), re.IGNORECASE)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).upper()
    if unit == "KB":
        return value
    if unit == "MB":
        return value * 1024
    return value * 1024 * 1024


def build_text_blob(item: dict[str, Any]) -> str:
    """Lowercased concatenation of announcement text fields + URL basename."""
    url = (item.get("attchmntFile") or "").strip()
    parts: list[str] = []
    for key in ("attchmntText", "desc", "smIndustry", "subject"):
        value = item.get(key)
        if isinstance(value, str) and value:
            parts.append(value)
    if url:
        parts.append(url.rsplit("/", 1)[-1])
    return " ".join(parts).lower()


def is_pdf_url(url: str) -> bool:
    path = url.split("?", 1)[0].lower()
    return path.endswith(".pdf")


def download_pdf(
    url: str,
    session: requests.Session,
    *,
    timeout: int = 120,
    referer: str | None = None,
) -> bytes:
    """Download a PDF from NSE archives using the warmed session."""
    headers = {"Referer": referer} if referer else None
    response = session.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    data = response.content
    if not data:
        raise ValueError(f"Empty response from {url}")
    if not data.startswith(_PDF_MAGIC):
        raise ValueError(f"Not a PDF (no %PDF- header): {url}")
    return data


def pdf_hash(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


def url_suggests_financial_report(url: str) -> bool:
    url_lower = (url or "").lower()
    return any(marker in url_lower for marker in _STRONG_FIN_URL_MARKERS)


def _is_financial_table_row(line: str) -> bool:
    numbers: list[float] = []
    for match in _NUMBER_RE.finditer(line):
        raw = match.group(1).replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        if 1900 <= val <= 2099 and val == int(val):
            continue
        numbers.append(val)
    material = [n for n in numbers if abs(n) >= 500]
    return len(material) >= 2


def _extract_pdf_text_pypdf(pdf_bytes: bytes, *, max_pages: int = 20) -> tuple[str, int]:
    reader_cls = _get_pdf_reader()
    reader = reader_cls(io.BytesIO(pdf_bytes))
    page_count = len(reader.pages)
    sample_indices: list[int] = []
    for i in range(min(max_pages, page_count)):
        if i not in sample_indices:
            sample_indices.append(i)
    for i in range(6, min(page_count, 22)):
        if i not in sample_indices:
            sample_indices.append(i)
    sample_indices.sort()

    chunks: list[str] = []
    for i in sample_indices:
        try:
            chunks.append(reader.pages[i].extract_text() or "")
        except Exception:
            chunks.append("")
    return "\n".join(chunks), page_count


def _extract_pdf_text_pymupdf(pdf_bytes: bytes, *, max_pages: int = 20) -> tuple[str, int]:
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = doc.page_count
    sample_indices: list[int] = []
    for i in range(min(max_pages, page_count)):
        if i not in sample_indices:
            sample_indices.append(i)
    for i in range(6, min(page_count, 22)):
        if i not in sample_indices:
            sample_indices.append(i)
    sample_indices.sort()

    chunks: list[str] = []
    for i in sample_indices:
        try:
            chunks.append(doc.load_page(i).get_text("text") or "")
        except Exception:
            chunks.append("")
    doc.close()
    return "\n".join(chunks), page_count


def _extract_pdf_text(pdf_bytes: bytes, *, max_pages: int = 20) -> tuple[str, int]:
    text, page_count = _extract_pdf_text_pypdf(pdf_bytes, max_pages=max_pages)
    if len(text.strip()) >= 1200:
        return text, page_count
    try:
        alt_text, alt_pages = _extract_pdf_text_pymupdf(pdf_bytes, max_pages=max_pages)
        if len(alt_text.strip()) > len(text.strip()):
            return alt_text, alt_pages
    except Exception:
        pass
    return text, page_count


def classify_pdf_content(
    pdf_bytes: bytes,
    *,
    max_pages: int = 20,
    source_url: str | None = None,
) -> dict[str, Any]:
    """Heuristic classifier: is this PDF a financial results filing?"""
    text, page_count = _extract_pdf_text(pdf_bytes, max_pages=max_pages)
    lower = text.lower()
    text_len = len(lower)

    positive_hits = sum(1 for pat in _POSITIVE_RES if pat.search(lower))
    negative_hits = sum(1 for pat in _NEGATIVE_RES if pat.search(lower))
    hard_excluded_hits = sum(
        1 for pat in _HARD_EXCLUDED_CONTENT_RES if pat.search(lower)
    )
    soft_excluded_hits = sum(
        1 for pat in _SOFT_EXCLUDED_CONTENT_RES if pat.search(lower)
    )
    excluded_hits = hard_excluded_hits + soft_excluded_hits
    has_core_financial = any(pat.search(lower) for pat in _CORE_FINANCIAL_RES)
    table_row_count = sum(1 for line in lower.splitlines() if _is_financial_table_row(line))

    score = 0.0
    reasons: list[str] = []

    if hard_excluded_hits:
        reasons.append(f"{hard_excluded_hits} hard-excluded doc phrase(s)")
        return {
            "is_financial_report": False,
            "confidence": 0.0,
            "document_kind": "EXCLUDED",
            "signals": {
                "positive_hits": positive_hits,
                "negative_hits": negative_hits,
                "excluded_hits": excluded_hits,
                "hard_excluded_hits": hard_excluded_hits,
                "soft_excluded_hits": soft_excluded_hits,
                "has_core_financial": has_core_financial,
                "table_row_count": table_row_count,
                "page_count": page_count,
                "text_len": text_len,
            },
            "reasons": reasons,
        }

    score += min(positive_hits * 0.12, 0.48)
    if positive_hits:
        reasons.append(f"{positive_hits} financial phrase(s)")

    score -= min(negative_hits * 0.12, 0.36)
    if negative_hits:
        reasons.append(f"{negative_hits} letter/admin phrase(s)")

    if soft_excluded_hits:
        score -= min(soft_excluded_hits * 0.12, 0.24)
        reasons.append(f"{soft_excluded_hits} ambiguous excluded phrase(s)")

    if page_count >= 20:
        score += 0.42
        reasons.append(f"{page_count} pages (integrated filing)")
    elif page_count >= 10:
        score += 0.28
        reasons.append(f"{page_count} pages")
    elif page_count >= 5:
        score += 0.10
    elif page_count <= 3:
        score -= 0.25
        reasons.append(f"short doc ({page_count} pages)")

    if table_row_count >= 8:
        score += 0.28
        reasons.append(f"{table_row_count} table-like rows")
    elif table_row_count >= 3:
        score += 0.14
    elif table_row_count < 2 and page_count <= 5:
        score -= 0.20
        reasons.append("few numeric table rows")

    if text_len > 12000:
        score += 0.10
    elif text_len < 1200 and page_count <= 4:
        score -= 0.15
        reasons.append("minimal extractable text")

    if page_count <= 4 and table_row_count < 4:
        score -= 0.18
        reasons.append("letter-shaped (short + no tables)")

    confidence = max(0.0, min(1.0, score))
    is_financial_report = confidence >= 0.55 and has_core_financial
    if confidence >= 0.55 and not has_core_financial:
        reasons.append("missing core financial-results sections")

    if (
        not is_financial_report
        and source_url
        and url_suggests_financial_report(source_url)
        and hard_excluded_hits == 0
        and (soft_excluded_hits == 0 or has_core_financial)
        and negative_hits < 2
        and (confidence >= 0.30 or table_row_count >= 2 or page_count >= 5)
    ):
        is_financial_report = True
        confidence = max(confidence, 0.60)
        reasons.append("accepted via financial-results URL marker")

    if is_financial_report:
        document_kind = "FINANCIAL_RESULT"
    elif negative_hits >= 2 or (page_count <= 3 and table_row_count < 2):
        document_kind = "LETTER"
    else:
        document_kind = "OTHER"

    return {
        "is_financial_report": is_financial_report,
        "confidence": round(confidence, 3),
        "document_kind": document_kind,
        "signals": {
            "positive_hits": positive_hits,
            "negative_hits": negative_hits,
            "excluded_hits": excluded_hits,
            "hard_excluded_hits": hard_excluded_hits,
            "soft_excluded_hits": soft_excluded_hits,
            "has_core_financial": has_core_financial,
            "table_row_count": table_row_count,
            "page_count": page_count,
            "text_len": text_len,
        },
        "reasons": reasons,
    }


def _parse_ddmmyyyy(token: str) -> tuple[int, int, int] | None:
    if len(token) != 8 or not token.isdigit():
        return None
    day, month, year = int(token[:2]), int(token[2:4]), int(token[4:])
    if 1 <= day <= 31 and 1 <= month <= 12 and 2000 <= year <= 2099:
        return day, month, year
    return None


def _expand_period_date(day: int, month: int, year: int) -> set[str]:
    month_name = _MONTH_TO_NAME[month]
    month_abbr = month_name[:3]
    return {
        f"{day} {month_name} {year}",
        f"{month_name} {day} {year}",
        f"{day} {month_abbr} {year}",
        f"{month_abbr} {day} {year}",
        f"{day:02d}{month:02d}{year}",
        f"{day:02d}{month:02d}{year % 100}",
        f"{month_abbr}{year}",
    }


def _expand_period_text(raw: str) -> set[str]:
    raw = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", raw)
    markers = {raw}
    parts = raw.replace(",", "").split()
    if len(parts) == 3 and parts[0].isdigit() and parts[2].isdigit():
        month_num = _MONTH_NAME_TO_NUM.get(parts[1])
        if month_num:
            markers.update(_expand_period_date(int(parts[0]), month_num, int(parts[2])))
            return markers
    if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
        month_num = _MONTH_NAME_TO_NUM.get(parts[0])
        if month_num:
            markers.update(_expand_period_date(int(parts[1]), month_num, int(parts[2])))
            return markers
    if len(parts) == 3:
        markers.add(f"{parts[1]} {parts[0]} {parts[2]}")
    return markers


def infer_period_markers(announcements: list[dict[str, Any]]) -> list[str]:
    """Derive period text markers from the announcement batch (symbol-agnostic)."""
    markers: set[str] = set()
    for item in announcements:
        for field in ("attchmntText", "desc"):
            text = item.get(field) or ""
            for match in _PERIOD_ENDED_RE.finditer(text):
                raw = match.group(1).lower().replace(",", "").strip()
                markers.update(_expand_period_text(raw))
        url = (item.get("attchmntFile") or "").lower()
        for match in _FY_TOKEN_RE.finditer(url):
            markers.add(f"q{match.group(1)}fy{match.group(2)}")
        for match in _DATE_IN_URL_RE.finditer(url):
            markers.add(match.group(0).replace("_", " "))
        for match in _DDMMYYYY_IN_URL_RE.finditer(url):
            parsed = _parse_ddmmyyyy(match.group(1))
            # Bare eight-digit tokens in NSE filenames are commonly the upload
            # date (for example Boardoutcome_07052024.pdf).  Only canonical
            # quarter ends are safe enough to treat as reporting-period hints.
            if parsed and (parsed[0], parsed[1]) in {
                (31, 3),
                (30, 6),
                (30, 9),
                (31, 12),
            }:
                markers.update(_expand_period_date(*parsed))
    return sorted(markers)


def _is_excluded_candidate(item: dict[str, Any]) -> bool:
    bucket = item.get("event_bucket") or item.get("desc") or ""
    if bucket in _EXCLUDED_EVENT_BUCKETS:
        return True
    url_lower = (item.get("attchmntFile") or "").lower()
    if any(marker in url_lower for marker in _URL_EXCLUDED_MARKERS):
        return True
    text = build_text_blob(item)
    if (
        "monitoring agency" in text
        or "certificate under regulation 74" in text
        or "presentation made by company" in text
    ):
        return True
    return False


def metadata_score(item: dict[str, Any]) -> float:
    text = build_text_blob(item)
    url_lower = (item.get("attchmntFile") or "").lower()
    score = 0.0

    if "submitted to the exchange, the financial results" in text:
        score += 5.0
    elif "submitted to the exchange, the consolidated" in text:
        score += 4.0
    elif "outcome of the board meeting" in text and "financial results" in text:
        score += 3.5
    elif "financial results" in text and "scheduled to be held" not in text:
        if "conference call" not in text and "will hold" not in text:
            score += 2.0

    size_kb = parse_file_size_kb(item.get("fileSize") or item.get("attFileSize"))
    if size_kb is not None:
        if size_kb > 2048:
            score += 3.0
        elif size_kb > 800:
            score += 1.0
        elif size_kb < 300:
            score -= 2.0

    if any(marker in url_lower for marker in _URL_FIN_MARKERS):
        score += 2.0
    if any(marker in url_lower for marker in _URL_EXCLUDED_MARKERS):
        score -= 4.0

    if item.get("event_bucket") == "Financial Results":
        score += 1.5
    if item.get("event_bucket") == "Outcome of Board Meeting" or item.get("desc") == "Outcome of Board Meeting":
        score += 2.5

    if item.get("event_bucket") in _MISLINKED_BUCKETS:
        score -= 3.0

    return score


def _matches_period_markers(item: dict[str, Any], period_markers: list[str] | None) -> bool:
    if not period_markers:
        return True
    text = build_text_blob(item)
    return any(marker.lower() in text for marker in period_markers)


def build_same_filing_recovery_scope(
    announcements: list[dict[str, Any]],
    anchor: dict[str, Any],
    *,
    period_markers: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Limit exact-source recovery to companion attachments for one filing.

    NSE commonly publishes a board letter, the result PDF, and supporting
    material on the same day.  Exact-mode recovery may inspect those companion
    files, but it must not select another filing elsewhere in the query window.
    """
    anchor_url = (anchor.get("attchmntFile") or "").strip()
    anchor_sort_date = str(anchor.get("sort_date") or "")
    anchor_day = anchor_sort_date[:10] if len(anchor_sort_date) >= 10 else ""
    markers = period_markers or infer_period_markers([anchor])

    scoped: list[dict[str, Any]] = []
    for item in announcements:
        url = (item.get("attchmntFile") or "").strip()
        if url == anchor_url:
            scoped.append(item)
            continue
        if not anchor_day:
            continue
        item_sort_date = str(item.get("sort_date") or "")
        if item_sort_date[:10] != anchor_day:
            continue
        if markers and not _matches_period_markers(item, markers):
            continue
        scoped.append(item)
    return scoped


def build_candidate_pool(
    announcements: list[dict[str, Any]],
    *,
    period_markers: list[str] | None = None,
    allow_period_fallback: bool = True,
) -> list[dict[str, Any]]:
    def _collect(markers: list[str] | None) -> list[dict[str, Any]]:
        seen_urls: set[str] = set()
        pool: list[dict[str, Any]] = []
        for item in announcements:
            url = (item.get("attchmntFile") or "").strip()
            if not url or not is_pdf_url(url):
                continue
            if _is_excluded_candidate(item):
                continue
            if url in seen_urls:
                continue
            if not _matches_period_markers(item, markers):
                continue
            seen_urls.add(url)
            pool.append({**item, "_metadata_score": metadata_score(item)})
        pool.sort(key=lambda x: x["_metadata_score"], reverse=True)
        return pool

    pool = _collect(period_markers)
    if not pool and period_markers and allow_period_fallback:
        pool = _collect(None)
    return pool


def _financial_url_candidates(
    announcements: list[dict[str, Any]],
    tried: set[str],
    *,
    period_markers: list[str] | None = None,
    strict_period_match: bool = False,
) -> list[dict[str, Any]]:
    """PDFs whose URL strongly suggests a financial-results attachment."""
    pool: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for item in announcements:
        url = (item.get("attchmntFile") or "").strip()
        if not url or not is_pdf_url(url) or url in tried or url in seen_urls:
            continue
        if _is_excluded_candidate(item):
            continue
        if strict_period_match and not _matches_period_markers(item, period_markers):
            continue
        url_lower = url.lower()
        if not any(marker in url_lower for marker in _URL_FIN_MARKERS):
            continue
        seen_urls.add(url)
        pool.append({**item, "_metadata_score": metadata_score(item)})
    pool.sort(key=lambda x: x["_metadata_score"], reverse=True)
    return pool


def _fetch_and_classify(
    url: str,
    session: requests.Session,
    *,
    referer: str | None = None,
) -> tuple[str, dict[str, Any], bytes]:
    if url in _PDF_CLASSIFICATION_CACHE:
        return _PDF_CLASSIFICATION_CACHE[url]

    pdf_bytes = download_pdf(url, session, referer=referer)
    digest = pdf_hash(pdf_bytes)

    for cached_url, (cached_hash, cached_cls, cached_bytes) in _PDF_CLASSIFICATION_CACHE.items():
        if cached_hash == digest:
            _PDF_CLASSIFICATION_CACHE[url] = (cached_hash, cached_cls, cached_bytes)
            return cached_hash, cached_cls, cached_bytes

    classification = classify_pdf_content(pdf_bytes, source_url=url)
    _PDF_CLASSIFICATION_CACHE[url] = (digest, classification, pdf_bytes)
    return digest, classification, pdf_bytes


def classify_pdf_url(
    url: str,
    session: requests.Session,
    *,
    referer: str | None = None,
) -> dict[str, Any]:
    """Download (or cache) and classify a PDF by URL."""
    _, classification, _ = _fetch_and_classify(url, session, referer=referer)
    return classification


def _resolved_rank(resolved: dict[str, Any]) -> tuple[datetime, float, float]:
    cls = resolved.get("classification") or {}
    item = resolved.get("announcement") or {}
    try:
        published_at = datetime.strptime(
            str(item.get("sort_date") or ""), "%Y-%m-%d %H:%M:%S"
        )
    except ValueError:
        published_at = datetime.min
    return (
        published_at,
        float(cls.get("confidence") or 0),
        float(resolved.get("metadata_score") or 0),
    )


def _resolved_from_item(
    item: dict[str, Any],
    *,
    url: str,
    cls: dict[str, Any],
    digest: str,
    pdf_bytes: bytes,
    recovery_needed: bool = False,
    rejected_url: str | None = None,
) -> dict[str, Any]:
    resolved: dict[str, Any] = {
        "url": url,
        "announcement": item,
        "classification": cls,
        "pdf_hash": digest,
        "pdf_bytes": pdf_bytes,
        "metadata_score": metadata_score(item),
        "recovery_needed": recovery_needed,
    }
    if rejected_url:
        resolved["rejected_url"] = rejected_url
    return resolved


def _try_candidate_pool(
    pool: list[dict[str, Any]],
    tried: set[str],
    session: requests.Session,
    max_candidates: int,
    *,
    referer: str | None = None,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for candidate in pool[:max_candidates]:
        url = candidate["attchmntFile"]
        if url in tried:
            continue
        tried.add(url)
        try:
            digest, classification, pdf_bytes = _fetch_and_classify(
                url, session, referer=referer
            )
        except Exception as exc:
            print(f"  skip {url.rsplit('/', 1)[-1]}: {exc}")
            continue

        if classification["is_financial_report"]:
            resolved = _resolved_from_item(
                candidate,
                url=url,
                cls=classification,
                digest=digest,
                pdf_bytes=pdf_bytes,
            )
            if best is None or _resolved_rank(resolved) > _resolved_rank(best):
                best = resolved
    return best


def resolve_financial_report_pdf(
    announcements: list[dict[str, Any]],
    *,
    period_markers: list[str] | None = None,
    max_candidates: int = 24,
    session: requests.Session,
    tried_urls: set[str] | None = None,
    referer: str | None = None,
    strict_period_match: bool = False,
) -> dict[str, Any] | None:
    """Search announcement batch for the PDF that actually is a financial report."""
    tried = set(tried_urls or ())

    if tried_urls:
        fin_url_pool = _financial_url_candidates(
            announcements,
            tried,
            period_markers=period_markers,
            strict_period_match=strict_period_match,
        )
        found = _try_candidate_pool(
            fin_url_pool, tried, session, max_candidates, referer=referer
        )
        if found:
            return found

    marker_passes: list[list[str] | None] = [period_markers]
    if period_markers and not strict_period_match:
        marker_passes.append(None)

    best: dict[str, Any] | None = None
    for markers in marker_passes:
        pool = build_candidate_pool(
            announcements,
            period_markers=markers,
            allow_period_fallback=not strict_period_match,
        )
        found = _try_candidate_pool(
            pool, tried, session, max_candidates, referer=referer
        )
        if found and (best is None or _resolved_rank(found) > _resolved_rank(best)):
            best = found

    return best


def resolve_canonical_financial_report(
    announcements: list[dict[str, Any]],
    financial_results: list[dict[str, Any]],
    *,
    period_markers: list[str] | None = None,
    session: requests.Session,
    max_candidates: int = 24,
    referer: str | None = None,
    strict_period_match: bool = False,
) -> dict[str, Any] | None:
    """Resolve the canonical financial report with per-bucket mislink recovery."""
    tried: set[str] = set()
    best: dict[str, Any] | None = None

    eligible_financial_results = financial_results
    if strict_period_match and period_markers:
        eligible_financial_results = [
            item
            for item in financial_results
            if _matches_period_markers(item, period_markers)
        ]

    for item in eligible_financial_results:
        url = (item.get("attchmntFile") or "").strip()
        if not url:
            continue
        # Presentations often reproduce complete financial statements and can
        # therefore score 1.0 in the content classifier.  They are supporting
        # investor material, not the canonical exchange results filing.
        if _is_excluded_candidate(item):
            continue
        tried.add(url)
        try:
            digest, cls, pdf_bytes = _fetch_and_classify(url, session, referer=referer)
        except Exception as exc:
            print(f"  skip {url.rsplit('/', 1)[-1]}: {exc}")
            recovered = resolve_financial_report_pdf(
                announcements,
                period_markers=period_markers,
                max_candidates=max_candidates,
                session=session,
                tried_urls=tried.copy(),
                referer=referer,
                strict_period_match=strict_period_match,
            )
            if recovered:
                recovered["recovery_needed"] = True
                recovered["rejected_url"] = url
                if best is None or _resolved_rank(recovered) > _resolved_rank(best):
                    best = recovered
            continue

        if cls["is_financial_report"]:
            resolved = _resolved_from_item(
                item, url=url, cls=cls, digest=digest, pdf_bytes=pdf_bytes
            )
            if best is None or _resolved_rank(resolved) > _resolved_rank(best):
                best = resolved
        else:
            recovered = resolve_financial_report_pdf(
                announcements,
                period_markers=period_markers,
                max_candidates=max_candidates,
                session=session,
                tried_urls=tried.copy(),
                referer=referer,
                strict_period_match=strict_period_match,
            )
            if recovered:
                recovered["recovery_needed"] = True
                recovered["rejected_url"] = url
                if best is None or _resolved_rank(recovered) > _resolved_rank(best):
                    best = recovered

    if best is not None:
        return best

    return resolve_financial_report_pdf(
        announcements,
        period_markers=period_markers,
        max_candidates=max_candidates,
        session=session,
        tried_urls=tried or None,
        referer=referer,
        strict_period_match=strict_period_match,
    )
