"""Pick values from the target *Quarter Ended* column in Indian quarterly result tables.

Primary path: parse markdown pipe tables (from ``pdf_parse``) and match the column
whose header date equals ``target.quarter_end``.

Fallback: stacked plain-text layout (Particulars block + Quarter Ended value block)
for filings that never become proper tables.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from periods import ReportingPeriod, _month_from_name

_NUMBER_RE = re.compile(
    r"(?<!\d)(?:\((?P<neg>[\d,]+(?:\.\d+)?)\)|(?P<num>[\d,]+(?:\.\d+)?))(?!\d)"
)
_DATE_DMY_RE = re.compile(
    r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})"
)
_DATE_MDY_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s*,?\s*(\d{4})",
    re.IGNORECASE,
)
_CUMULATIVE_HEADER = re.compile(
    r"nine\s+months?\s+ended|twelve\s+months?\s+ended|year\s+ended|half[\s-]year|ytd|annual",
    re.IGNORECASE,
)
_QUARTER_HEADER = re.compile(
    r"(?:quarter|3\s+months?|three\s+months?)\s+ended",
    re.IGNORECASE,
)
_SEGMENT_CONTEXT = re.compile(
    r"segment[\s-]wise|segment\s+revenue|segment\s+results|segment\s+assets",
    re.IGNORECASE,
)
_PL_CONTEXT = re.compile(
    r"statement\s+of\s+(?:unaudited\s+)?financial\s+results|"
    r"consolidated\s+financial\s+results|profit\s+and\s+loss",
    re.IGNORECASE,
)

_LABEL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bEBITDA\b", re.I), "ebitda"),
    (re.compile(r"revenue\s+from\s+operations|revenue\s+from\s+ops", re.I), "revenue_from_operations"),
    (re.compile(r"\bgross\s+revenue\b", re.I), "revenue_from_operations"),
    (re.compile(r"\bother\s+income\b", re.I), "other_income"),
    (re.compile(r"profit\s+before\s+tax|\bPBT\b", re.I), "pbt"),
    (re.compile(r"profit\s+after\s+tax|\bPAT\b", re.I), "pat"),
    (re.compile(r"profit\s+for\s+the\s+period", re.I), "pat"),
    (re.compile(r"\bexceptional\s+item", re.I), "exceptional_items"),
    (re.compile(r"\bfinance\s+cost", re.I), "finance_cost"),
    (re.compile(r"\binterest\s+earned\b", re.I), "interest_earned"),
    (re.compile(r"tax\s+expense|\btax\s+expenses\b", re.I), "tax_expense"),
    (re.compile(r"\boperating\s+profit\b", re.I), "operating_profit"),
    (re.compile(r"cash\s+(?:flow|generated)\s+from\s+(?:operating|operations)", re.I), "cfo"),
    (re.compile(r"\bEPS\b.*\bbasic\b|\bearnings\s+per\s+equity\s+share\b", re.I), "eps_basic"),
    (re.compile(r"\bEPS\b", re.I), "eps_basic"),
]

_QUARTER_SECTION = re.compile(r"^Quarter\s+Ended\s*$", re.I)
_NINE_MONTHS_SECTION = re.compile(r"^Nine\s+Months\s+Ended\s*$", re.I)
_YEAR_SECTION = re.compile(r"^Year\s+Ended\s*$", re.I)
_PARTICULARS = re.compile(r"^Particulars\s*$", re.I)
_PAGE_HEADER_RE = re.compile(r"^# Page (\d+)\s*$")


def _page_markers(markdown: str) -> list[tuple[int, int]]:
    markers: list[tuple[int, int]] = []
    for i, line in enumerate(markdown.splitlines()):
        m = _PAGE_HEADER_RE.match(line.strip())
        if m:
            markers.append((i, int(m.group(1))))
    return markers


def _page_at_line(markers: list[tuple[int, int]], line: int) -> int | None:
    page: int | None = None
    for mline, mpage in markers:
        if mline <= line:
            page = mpage
        else:
            break
    return page


def _iter_page_sections(markdown: str) -> list[tuple[int, str]]:
    lines = markdown.splitlines()
    sections: list[tuple[int, str]] = []
    current_page = 1
    buffer: list[str] = []
    for line in lines:
        m = _PAGE_HEADER_RE.match(line.strip())
        if m:
            if buffer:
                sections.append((current_page, "\n".join(buffer)))
            current_page = int(m.group(1))
            buffer = []
        else:
            buffer.append(line)
    if buffer:
        sections.append((current_page, "\n".join(buffer)))
    return sections


def extract_facts_from_quarter_column(
    text: str,
    *,
    target: ReportingPeriod,
    fact_keys: set[str],
    facts_catalog: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Extract deterministic facts for ``target`` quarter from markdown or plain text."""
    catalog = facts_catalog or {}
    by_key: dict[str, dict[str, Any]] = {}

    for row in _extract_from_markdown_tables(text, target=target, fact_keys=fact_keys, catalog=catalog):
        by_key[row["fact_key"]] = row

    if len(by_key) < max(1, len(fact_keys) // 4):
        for row in _extract_stacked_fallback(text, target=target, fact_keys=fact_keys, catalog=catalog):
            by_key.setdefault(row["fact_key"], row)

    return list(by_key.values())


def _extract_from_markdown_tables(
    markdown: str,
    *,
    target: ReportingPeriod,
    fact_keys: set[str],
    catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    target_end = date.fromisoformat(target.quarter_end)
    page_markers = _page_markers(markdown)

    for table, context, start_line in _iter_markdown_tables(markdown):
        if _SEGMENT_CONTEXT.search(context) or _SEGMENT_CONTEXT.search("\n".join(table[:3])):
            continue
        col_idx = _quarter_column_index(table, target_end)
        if col_idx is None:
            continue
        if not _looks_like_pl_table(table):
            continue
        score = 2 if _PL_CONTEXT.search(context) else 1
        if _SEGMENT_CONTEXT.search(context):
            score = 0
        if score == 0:
            continue

        source_page = _page_at_line(page_markers, start_line)
        for row in _rows_from_table(table, col_idx, fact_keys, catalog, source_page=source_page):
            prev = found.get(row["fact_key"])
            if prev is None or score >= prev.get("_table_score", 0):
                row["_table_score"] = score
                found[row["fact_key"]] = row

    return [{k: v for k, v in row.items() if k != "_table_score"} for row in found.values()]


def _iter_markdown_tables(markdown: str) -> list[tuple[list[str], str, int]]:
    lines = markdown.splitlines()
    tables: list[tuple[list[str], str, int]] = []
    i = 0
    while i < len(lines):
        if not lines[i].strip().startswith("|"):
            i += 1
            continue
        start = i
        block: list[str] = []
        while i < len(lines) and lines[i].strip().startswith("|"):
            block.append(lines[i])
            i += 1
        if len(block) >= 2 and _is_table_separator(block[1]):
            context = "\n".join(lines[max(0, start - 8) : start])
            tables.append((block, context, start))
    return tables


def _is_table_separator(line: str) -> bool:
    cells = _split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells)


def _split_table_row(line: str) -> list[str]:
    raw = line.strip()
    if not raw.startswith("|"):
        return []
    inner = raw.strip("|")
    return [c.strip() for c in inner.split("|")]


def _looks_like_pl_table(table: list[str]) -> bool:
    head = " ".join(
        cell for r in table[:4] for cell in _split_table_row(r)
    ).lower()
    if "particulars" not in head:
        return False
    if not _QUARTER_HEADER.search(head) and not _DATE_DMY_RE.search(head):
        return False
    body = " ".join(cell for r in table for cell in _split_table_row(r)).lower()
    markers = sum(
        1
        for pat in (
            r"revenue\s+from\s+operations",
            r"profit\s+before\s+tax",
            r"profit\s+after\s+tax",
            r"total\s+income",
            r"total\s+expenses",
        )
        if re.search(pat, body)
    )
    return markers >= 2


def _parse_cell_date(text: str) -> date | None:
    cell = re.sub(r"\(.*?\)", "", text or "").strip()
    m = _DATE_DMY_RE.search(cell)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = _DATE_MDY_RE.search(cell)
    if m:
        month = _month_from_name(m.group(2))
        if month:
            return date(int(m.group(3)), month, int(m.group(1)))
    return None


def _quarter_column_index(table: list[str], target_end: date) -> int | None:
    """Return 0-based data column index (after label column) for ``target_end``."""
    header_rows: list[list[str]] = []
    for line in table:
        cells = _split_table_row(line)
        if not cells:
            continue
        if _is_table_separator(line):
            continue
        if _row_has_dates(cells) or _QUARTER_HEADER.search(" ".join(cells)):
            header_rows.append(cells)
        elif header_rows:
            break

    if not header_rows:
        return None

    ncols = max(len(r) for r in header_rows)
    sections = _expand_sections(header_rows[0], ncols)

    col_dates: list[str | None] = [None] * ncols
    for row in header_rows[1:]:
        for i, cell in enumerate(row):
            d = _parse_cell_date(cell)
            if d:
                col_dates[i] = d.isoformat()
    if not any(col_dates):
        for i, cell in enumerate(header_rows[-1]):
            d = _parse_cell_date(cell)
            if d:
                col_dates[i] = d.isoformat()

    target_iso = target_end.isoformat()
    matches = [i for i, d in enumerate(col_dates) if d == target_iso]
    if not matches:
        return None

    quarter_matches = [i for i in matches if sections[i] == "quarter"]
    pick = quarter_matches[0] if quarter_matches else matches[0]
    return max(0, pick - 1) if pick > 0 else pick


def _expand_sections(header_row: list[str], ncols: int) -> list[str]:
    """Expand section headers across data columns (handles merged header cells)."""
    markers: list[tuple[int, str]] = []
    for i, cell in enumerate(header_row):
        if _QUARTER_HEADER.search(cell):
            markers.append((i, "quarter"))
        elif _CUMULATIVE_HEADER.search(cell):
            markers.append((i, "cumulative"))

    sections = ["label"] * ncols
    if not markers:
        return sections

    for j, (start, sec) in enumerate(markers):
        end = markers[j + 1][0] if j + 1 < len(markers) else ncols
        # Merged headers: section spans from marker until next marker or end of row,
        # but data columns often extend beyond the next marker cell — stretch quarter
        # through the date sub-columns (typically 3) when only one header cell exists.
        if sec == "quarter" and j + 1 < len(markers):
            gap = markers[j + 1][0] - start
            if gap == 1:
                end = min(ncols, start + 3)
        for c in range(start, end):
            if c < ncols:
                sections[c] = sec
    return sections


def _row_has_dates(cells: list[str]) -> bool:
    return any(_parse_cell_date(c) for c in cells)


def _rows_from_table(
    table: list[str],
    col_idx: int,
    fact_keys: set[str],
    catalog: dict[str, Any],
    *,
    source_page: int | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    data_started = False

    for line in table:
        if _is_table_separator(line):
            data_started = True
            continue
        cells = _split_table_row(line)
        if not cells or not data_started:
            continue
        if len(cells) <= col_idx + 1:
            continue

        label = _clean_label(cells[0])
        if not label or re.match(r"^\d+\.?\s*$", label):
            continue
        value_cell = cells[col_idx + 1] if col_idx + 1 < len(cells) else cells[-1]
        numeric = _parse_number(value_cell)
        if numeric is None:
            continue

        fact_key = _match_fact_key(label, fact_keys, catalog)
        if not fact_key:
            continue

        row: dict[str, Any] = {
            "fact_key": fact_key,
            "numeric_value": numeric,
            "unit": catalog.get(fact_key, {}).get("unit"),
            "basis": "consolidated",
            "evidence": f"{label} {value_cell.strip()}",
            "confidence": 0.92,
        }
        if source_page is not None:
            row["source_page"] = source_page
        rows.append(row)
    return rows


def _clean_label(text: str) -> str:
    return re.sub(r"[*_]+", "", text).strip()


def _match_fact_key(label: str, fact_keys: set[str], catalog: dict[str, Any]) -> str | None:
    low = label.lower()
    for alias, canonical in _catalog_aliases(catalog).items():
        if canonical not in fact_keys:
            continue
        if alias in low:
            return canonical
    for pattern, code in _LABEL_PATTERNS:
        if code not in fact_keys:
            continue
        if pattern.search(label):
            return code
    return None


def _catalog_aliases(catalog: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, spec in catalog.items():
        name = str(spec.get("name") or "").lower()
        if name:
            out[name] = key
        out[key.replace("_", " ")] = key
        for alias in spec.get("aliases") or []:
            out[str(alias).lower()] = key
    return out


def _parse_number(text: str) -> float | None:
    raw = (text or "").strip()
    if not raw or raw in {"-", "—", "–", ""}:
        return None
    negative = raw.startswith("(") and raw.endswith(")")
    m = _NUMBER_RE.search(raw.replace(" ", ""))
    if not m:
        return None
    num_str = (m.group("neg") or m.group("num") or "").replace(",", "")
    try:
        val = float(num_str)
    except ValueError:
        return None
    if negative or m.group("neg"):
        val = -abs(val)
    if 1900 <= val <= 2099 and val == int(val):
        return None
    return val


def _extract_stacked_fallback(
    text: str,
    *,
    target: ReportingPeriod,
    fact_keys: set[str],
    catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for page_num, chunk in _iter_page_sections(text):
        for item in _extract_stacked_block(chunk, fact_keys, catalog):
            item["source_page"] = page_num
            found[item["fact_key"]] = item
    return list(found.values())


def _extract_stacked_block(
    text: str,
    fact_keys: set[str],
    catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    if not re.search(r"consolidated\s+financial\s+results|unaudited\s+consolidated", text, re.I):
        return []
    lines = [ln.strip() for ln in text.splitlines()]
    q_idx = next((i for i, ln in enumerate(lines) if _QUARTER_SECTION.match(ln)), None)
    if q_idx is None:
        return []
    end_idx = len(lines)
    for i in range(q_idx + 1, len(lines)):
        if _NINE_MONTHS_SECTION.match(lines[i]) or _YEAR_SECTION.match(lines[i]):
            end_idx = i
            break
    part_start = next((i for i, ln in enumerate(lines[:q_idx]) if _PARTICULARS.match(ln)), None)
    if part_start is None:
        return []

    labels: list[str] = []
    for ln in lines[part_start + 1 : q_idx]:
        if ln and not _PARTICULARS.match(ln):
            labels.append(ln)

    values: list[float] = []
    for ln in lines[q_idx + 1 : end_idx]:
        num = _parse_number(ln)
        if num is not None:
            values.append(num)

    if not labels or not values:
        return []

    items: list[dict[str, Any]] = []
    for idx, label in enumerate(labels):
        if idx >= len(values):
            break
        fact_key = _match_fact_key(label, fact_keys, catalog)
        if not fact_key:
            continue
        val = values[idx]
        items.append(
            {
                "fact_key": fact_key,
                "numeric_value": val,
                "unit": catalog.get(fact_key, {}).get("unit"),
                "basis": "consolidated",
                "evidence": f"{label} {val:,.2f}",
                "confidence": 0.75,
            }
        )
    return items
