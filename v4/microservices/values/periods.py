"""Indian fiscal-year period utilities for v2.

FY labels follow market convention: ``FY2024-25`` (April 2024 – March 2025).
The canonical stored key is ``fy_start_year`` (e.g. 2024), with ``fy_label``
as the formatted range string.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

_MONTH_MAP = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


def _month_from_name(name: str) -> int | None:
    key = name.lower().strip(".")
    return _MONTH_MAP.get(key) or _MONTH_MAP.get(key[:3])

_PERIOD_LABEL_RE = re.compile(
    r"^\s*Q([1-4])\s+FY\s*(\d{2,4})\s*[-/]\s*(\d{2,4})\s*$",
    re.IGNORECASE,
)
_FILENAME_PERIOD_RE = re.compile(
    r"Q([1-4])[_\s-]*FY(?:(\d{4})[-_/]?(\d{2,4})|(\d{2})[-_/](\d{2}))",
    re.IGNORECASE,
)
_SHORT_FY_RE = re.compile(r"Q([1-4])\s*FY(\d{2})\b", re.IGNORECASE)
_SEARCHABLE_FY_RE = re.compile(
    r"\bQ([1-4])\s*FY\s*(\d{2,4})(?:\s*[-/]\s*(\d{2,4}))?\b",
    re.IGNORECASE,
)


def format_fy_label(fy_start_year: int) -> str:
    """Indian FY label, e.g. ``FY2024-25``."""
    return f"FY{fy_start_year}-{(fy_start_year + 1) % 100:02d}"


def format_quarterly_label(quarter: int, fy_start_year: int) -> str:
    """Canonical quarterly label, e.g. ``Q3 FY2024-25``."""
    return f"Q{quarter} {format_fy_label(fy_start_year)}"


def fy_start_year_from_date(d: date) -> int:
    """FY start calendar year containing ``d`` (Indian FY: Apr–Mar)."""
    return d.year if d.month >= 4 else d.year - 1


def quarter_from_date(d: date) -> int:
    return ((d.month - 4) % 12) // 3 + 1


def quarter_end_date(quarter: int, fy_start_year: int) -> date:
    """Last day of the Indian-FY quarter."""
    q_start_month = 4 + (quarter - 1) * 3
    q_start_year = fy_start_year if q_start_month <= 12 else fy_start_year + 1
    if q_start_month > 12:
        q_start_month -= 12
    next_month = q_start_month + 3
    end_year = q_start_year + (next_month - 1) // 12
    end_month = ((next_month - 1) % 12) + 1
    return date(end_year, end_month, 1) - timedelta(days=1)


def legacy_fy_end_to_start(fy_end_mod100: int) -> int:
    """Convert deprecated end-year-mod-100 encoding to FY start year."""
    if fy_end_mod100 >= 1900:
        return fy_end_mod100 - 1
    return 2000 + fy_end_mod100 - 1


def parse_fy_start_year_from_label(label: str) -> int | None:
    """Parse FY start year from ``Q3 FY2024-25`` or legacy ``Q3 FY25``."""
    raw = label.strip()
    m = _PERIOD_LABEL_RE.match(raw)
    if m:
        y1 = int(m.group(2))
        if len(m.group(2)) == 2:
            y1 = 2000 + y1 if y1 < 70 else 1900 + y1
        return y1
    m = _SHORT_FY_RE.search(raw)
    if m:
        end_yy = int(m.group(2))
        return legacy_fy_end_to_start(end_yy)
    return None


@dataclass
class ReportingPeriod:
    quarter: int
    fy_start_year: int
    quarter_end: str
    label: str = ""
    fy_label: str = ""
    period_type: str = "quarter"
    source: str = ""

    def __post_init__(self) -> None:
        if not self.fy_label:
            self.fy_label = format_fy_label(self.fy_start_year)
        if not self.label:
            self.label = format_quarterly_label(self.quarter, self.fy_start_year)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReportingPeriod:
        if "fy_start_year" in data:
            return cls(
                quarter=int(data["quarter"]),
                fy_start_year=int(data["fy_start_year"]),
                quarter_end=str(data["quarter_end"]),
                label=str(data.get("label") or ""),
                fy_label=str(data.get("fy_label") or ""),
                period_type=str(data.get("period_type") or "quarter"),
                source=str(data.get("source") or ""),
            )
        if "fiscal_year" in data:
            fy_start = legacy_fy_end_to_start(int(data["fiscal_year"]))
            return cls(
                quarter=int(data["quarter"]),
                fy_start_year=fy_start,
                quarter_end=str(data["quarter_end"]),
                label=str(data.get("label") or ""),
                period_type=str(data.get("period_type") or "quarter"),
                source=str(data.get("source") or ""),
            )
        raise ValueError("reporting period dict missing fy_start_year")

    def match_terms(self) -> list[str]:
        end = date.fromisoformat(self.quarter_end)
        month_name = list(_MONTH_MAP.keys())[end.month - 1]
        end_suffix = (self.fy_start_year + 1) % 100
        legacy_end = f"fy{end_suffix:02d}"
        return [
            self.label.lower(),
            self.fy_label.lower(),
            f"q{self.quarter} {self.fy_label.lower()}",
            f"q{self.quarter} fy{self.fy_start_year}",
            f"q{self.quarter} {legacy_end}",
            f"q{self.quarter} fy{end_suffix:02d}",
            f"{end.day:02d}.{end.month:02d}.{end.year}",
            f"{end.day} {month_name} {end.year}",
            self.quarter_end,
            f"quarter ended {end.day} {month_name} {end.year}",
        ]


def reporting_period_from_date(d: date, source: str) -> ReportingPeriod:
    quarter = quarter_from_date(d)
    fy_start = fy_start_year_from_date(d)
    return ReportingPeriod(
        quarter=quarter,
        fy_start_year=fy_start,
        quarter_end=d.isoformat(),
        source=source,
    )


def detect_period_from_filename(title: str) -> ReportingPeriod | None:
    m = _FILENAME_PERIOD_RE.search(title)
    if not m:
        return None
    quarter = int(m.group(1))
    if m.group(2):
        fy_start_year = int(m.group(2))
    else:
        fy_start_year = 2000 + int(m.group(4))
    end = quarter_end_date(quarter, fy_start_year)
    return ReportingPeriod(
        quarter=quarter,
        fy_start_year=fy_start_year,
        quarter_end=end.isoformat(),
        source="filename",
    )


def _period_candidates(text: str) -> list[ReportingPeriod]:
    candidates: list[ReportingPeriod] = []
    seen: set[tuple[int, str]] = set()
    patterns = (
        (
            r"(?:QUARTER|quarter).{0,60}?ENDED(?:\s+on)?\s+(\d{1,2})\s*(?:ST|ND|RD|TH)?\s+([A-Za-z]+)\s*,?\s*(\d{4})",
            "heading",
            "day_first",
        ),
        (
            r"(?:QUARTER|quarter).{0,60}?ENDED\s+([A-Za-z]+)\s+(\d{1,2})\s*,?\s*(\d{4})",
            "heading",
            "month_first",
        ),
        (
            r"FOR\s+THE\s+QUARTER(?:\s*&\s*YEAR)?\s+ENDED\s+([A-Za-z]+)\s+(\d{1,2})\s*,?\s*(\d{4})",
            "heading",
            "month_first",
        ),
        (
            r"FOR\s+THE\s+QUARTER(?:\s*&\s*YEAR)?\s+ENDED\s+(\d{2})\.(\d{2})\.(\d{4})",
            "table_header",
            "numeric",
        ),
        (
            r"FOR\s+THE\s+QUARTER\s+ENDED\s+(\d{2})\.(\d{2})\.(\d{4})",
            "table_header",
            "numeric",
        ),
        (
            r"(?<![A-Za-z])Quarter\s+Ended\s+(\d{2})\.(\d{2})\.(\d{4})",
            "table_header",
            "numeric",
        ),
    )
    for pattern, source, order in patterns:
        for match in re.finditer(pattern, text, re.I | re.S):
            try:
                if order == "day_first":
                    month = _month_from_name(match.group(2))
                    if not month:
                        continue
                    period_date = date(int(match.group(3)), month, int(match.group(1)))
                elif order == "month_first":
                    month = _month_from_name(match.group(1))
                    if not month:
                        continue
                    period_date = date(int(match.group(3)), month, int(match.group(2)))
                else:
                    period_date = date(
                        int(match.group(3)), int(match.group(2)), int(match.group(1))
                    )
            except ValueError:
                continue
            dedupe_key = (match.start(), period_date.isoformat())
            if dedupe_key not in seen:
                seen.add(dedupe_key)
                candidates.append(reporting_period_from_date(period_date, source))

    for match in _SEARCHABLE_FY_RE.finditer(text):
        quarter = int(match.group(1))
        year_text = match.group(2)
        if len(year_text) == 4:
            fy_start = int(year_text)
        elif match.group(3):
            fy_start = 2000 + int(year_text)
        else:
            fy_start = legacy_fy_end_to_start(int(year_text))
        end = quarter_end_date(quarter, fy_start)
        dedupe_key = (match.start(), end.isoformat())
        if dedupe_key not in seen:
            seen.add(dedupe_key)
            candidates.append(
                ReportingPeriod(
                    quarter=quarter,
                    fy_start_year=fy_start,
                    quarter_end=end.isoformat(),
                    source="quarter_label",
                )
            )
    return candidates


def _best_period_candidate(candidates: list[ReportingPeriod]) -> ReportingPeriod | None:
    if not candidates:
        return None
    counts = Counter(
        (candidate.quarter, candidate.fy_start_year, candidate.quarter_end)
        for candidate in candidates
    )
    best_key = max(
        counts,
        key=lambda key: (
            counts[key],
            key[2]
            == quarter_end_date(key[0], key[1]).isoformat(),
            key[2],
        ),
    )
    selected = next(
        candidate
        for candidate in candidates
        if (candidate.quarter, candidate.fy_start_year, candidate.quarter_end) == best_key
    )
    if counts[best_key] > 1:
        selected.source = f"{selected.source}_consensus"
    return selected


def detect_period_from_markdown(markdown: str) -> ReportingPeriod | None:
    return _best_period_candidate(_period_candidates(markdown[:12000]))


def detect_period_from_title(title: str) -> ReportingPeriod | None:
    explicit = _best_period_candidate(_period_candidates(title))
    if explicit:
        explicit.source = "title"
        return explicit
    match = re.search(
        r"\bperiod\s+ended\s+(?:(\d{1,2})\s+([A-Za-z]+)|([A-Za-z]+)\s+(\d{1,2}))\s*,?\s*(\d{4})",
        title,
        re.I,
    )
    if match:
        day = int(match.group(1) or match.group(4))
        month = _month_from_name(match.group(2) or match.group(3))
        if month:
            try:
                return reporting_period_from_date(
                    date(int(match.group(5)), month, day), "title"
                )
            except ValueError:
                pass
    from_filename = detect_period_from_filename(title)
    if from_filename:
        from_filename.source = "title"
    return from_filename


def detect_reporting_period(markdown: str, title: str = "") -> ReportingPeriod | None:
    from_markdown = detect_period_from_markdown(markdown)
    from_title = detect_period_from_title(title) if title else None
    if from_markdown and from_title:
        if from_markdown.label == from_title.label:
            from_title.source = "title+document"
        return from_title
    if from_title:
        return from_title
    return from_markdown


def prior_year_period(target: ReportingPeriod) -> ReportingPeriod:
    fy_start = target.fy_start_year - 1
    end = quarter_end_date(target.quarter, fy_start)
    return ReportingPeriod(
        quarter=target.quarter,
        fy_start_year=fy_start,
        quarter_end=end.isoformat(),
        period_type=target.period_type,
        source="derived",
    )


def prior_quarter_period(target: ReportingPeriod) -> ReportingPeriod:
    if target.quarter == 1:
        quarter, fy_start = 4, target.fy_start_year - 1
    else:
        quarter, fy_start = target.quarter - 1, target.fy_start_year
    end = quarter_end_date(quarter, fy_start)
    return ReportingPeriod(
        quarter=quarter,
        fy_start_year=fy_start,
        quarter_end=end.isoformat(),
        period_type=target.period_type,
        source="derived",
    )


def resolve_period_label(period_str: str | None) -> ReportingPeriod | None:
    if not period_str:
        return None
    p = period_str.strip()
    m = _PERIOD_LABEL_RE.match(p)
    if m:
        quarter = int(m.group(1))
        y1 = int(m.group(2))
        if len(m.group(2)) == 2:
            y1 = 2000 + y1 if y1 < 70 else 1900 + y1
        end = quarter_end_date(quarter, y1)
        return ReportingPeriod(
            quarter=quarter,
            fy_start_year=y1,
            quarter_end=end.isoformat(),
            source="value_tag",
        )
    m = _SHORT_FY_RE.search(p)
    if m:
        quarter = int(m.group(1))
        fy_start = legacy_fy_end_to_start(int(m.group(2)))
        end = quarter_end_date(quarter, fy_start)
        return ReportingPeriod(
            quarter=quarter,
            fy_start_year=fy_start,
            quarter_end=end.isoformat(),
            source="value_tag",
        )
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", p)
    if m:
        d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        rp = reporting_period_from_date(d, "value_tag")
        return rp
    return None


def period_match_score(value_period: str | None, target: ReportingPeriod) -> int:
    if not value_period:
        return 0
    p = value_period.strip().lower()
    if any(k in p for k in ("nine month", "nine months", "9 month")):
        return -1
    if "year ended" in p or "full year" in p:
        return -1
    if re.fullmatch(r"fy\d{2,4}([-/]\d{2,4})?", p.replace(" ", "")):
        return -1
    if p.startswith("fy") and "q" not in p:
        return -1
    for term in target.match_terms():
        if term in p:
            return 100
    end_suffix = (target.fy_start_year + 1) % 100
    if f"q{target.quarter}" in p and (
        target.fy_label.lower().replace(" ", "") in p.replace(" ", "")
        or f"fy{end_suffix:02d}" in p
        or f"fy{target.fy_start_year}" in p
    ):
        return 100
    return 0


def prior_period_match_score(value_period: str | None, target: ReportingPeriod) -> int:
    score = period_match_score(value_period, prior_year_period(target))
    return score if score > 0 else 0


def prior_quarter_match_score(value_period: str | None, target: ReportingPeriod) -> int:
    score = period_match_score(value_period, prior_quarter_period(target))
    return score if score > 0 else 0


def prior_quarter(quarter: int, fy_start_year: int) -> tuple[int, int]:
    if quarter > 1:
        return quarter - 1, fy_start_year
    return 4, fy_start_year - 1
