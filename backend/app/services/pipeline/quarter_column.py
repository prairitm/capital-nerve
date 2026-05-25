"""Pick values from the *Quarter Ended* column in Indian quarterly result tables.

Statutory results PDFs usually stack labels, then a ``Quarter Ended`` number block,
then ``Nine Months Ended`` / ``Year Ended``. LLM extraction often mixes columns;
this module provides deterministic quarter-only values for the main P&L block and
refines inline multi-number rows.
"""
from __future__ import annotations

import re

from app.services.pipeline.llm import (
    ExtractedLineItem,
    _LABEL_PATTERNS,
    _NUMBER_RE,
    _source_quote,
)

_QUARTER_SECTION_START = re.compile(r"^Quarter\s+Ended\s*$", re.IGNORECASE)
_NINE_MONTHS_SECTION_START = re.compile(r"^Nine\s+Months\s+Ended\s*$", re.IGNORECASE)
_YEAR_SECTION_START = re.compile(r"^Year\s+Ended\s*$", re.IGNORECASE)
_PARTICULARS_START = re.compile(r"^Particulars\s*$", re.IGNORECASE)
_SECTION_HEADER = re.compile(r"^(particulars|income|expenses)$", re.IGNORECASE)
_ROMAN_NUMERAL = re.compile(r"^[IVX]+$", re.IGNORECASE)
_OCI_STOP = re.compile(
    r"other comprehensive income|total comprehensive income|net profit attributable",
    re.IGNORECASE,
)
# Rows after this are below-the-line; quarter value column no longer aligns 1:1.
_PL_STOP = re.compile(r"^total expenses\s*$", re.IGNORECASE)
_INVENTORY_ROW = re.compile(r"changes?\s+in\s+inventor", re.IGNORECASE)
# Same-line rows that are not the main consolidated P&L (segment / ratio tables).
_SKIP_INLINE_CONTEXT = re.compile(
    r"segment\s+(?:results|value|profit)|"
    r"earnings per equity share|"
    r"^\s*ratios\s*$|"
    r"operating margin\s*\(%\)|"
    r"net\s+profit\s+mar(?:gin|g)\s*%",
    re.IGNORECASE,
)


def enforce_quarter_ended_only(
    items: list[ExtractedLineItem],
    *,
    pages: list[tuple[int, str]],
) -> list[ExtractedLineItem]:
    """Merge LLM/mock items with quarter-column parses; drop nine-month / YTD picks."""
    quarter_items = extract_quarter_ended_items(pages=pages)
    by_code: dict[str, ExtractedLineItem] = {}

    for item in items:
        if _item_from_cumulative_section(item, pages):
            continue
        code = item.normalized_code
        if code not in by_code:
            by_code[code] = item

    for q_item in quarter_items:
        by_code[q_item.normalized_code] = q_item

    return list(by_code.values())


def extract_quarter_ended_items(
    *,
    pages: list[tuple[int, str]],
) -> list[ExtractedLineItem]:
    """Parse stacked *Quarter Ended* tables and inline quarterly rows."""
    found: dict[str, ExtractedLineItem] = {}
    for page_no, text in pages:
        for item in _extract_stacked_quarter_block(text, page_no):
            _merge_quarter_item(found, item)
        for item in _extract_inline_quarter_rows(text, page_no):
            _merge_quarter_item(found, item)
    return list(found.values())


def _merge_quarter_item(found: dict[str, ExtractedLineItem], item: ExtractedLineItem) -> None:
    """Prefer earlier pages (highlights / consolidated P&L) over segment tables."""
    prev = found.get(item.normalized_code)
    if prev is None:
        found[item.normalized_code] = item
        return
    if (
        item.page_number is not None
        and prev.page_number is not None
        and item.page_number < prev.page_number
    ):
        found[item.normalized_code] = item


def _extract_stacked_quarter_block(text: str, page_no: int) -> list[ExtractedLineItem]:
    if not re.search(
        r"consolidated\s+financial\s+results|unaudited\s+consolidated",
        text,
        re.IGNORECASE,
    ):
        return []
    lines = [line.strip() for line in text.splitlines()]
    q_idx = next((i for i, line in enumerate(lines) if _QUARTER_SECTION_START.match(line)), None)
    if q_idx is None:
        return []

    end_idx = len(lines)
    for i in range(q_idx + 1, len(lines)):
        if _NINE_MONTHS_SECTION_START.match(lines[i]) or _YEAR_SECTION_START.match(lines[i]):
            end_idx = i
            break

    part_start = next(
        (i for i, line in enumerate(lines[:q_idx]) if _PARTICULARS_START.match(line)),
        None,
    )
    if part_start is None:
        return []

    particular_rows = _collect_particular_rows(lines, part_start, q_idx)
    quarter_values: list[float] = []
    for line in lines[q_idx + 1 : end_idx]:
        value = _first_number(line)
        if value is not None:
            quarter_values.append(value)

    if not particular_rows or not quarter_values:
        return []

    items: list[ExtractedLineItem] = []
    for idx, (_, label_line) in enumerate(particular_rows):
        if idx >= len(quarter_values):
            break
        for pattern, code, raw_label, unit in _LABEL_PATTERNS:
            if not pattern.search(label_line):
                continue
            if code == "inventory" and _INVENTORY_ROW.search(label_line):
                continue
            if code == "tax_expense" and re.match(r"^tax expenses\s*$", label_line, re.IGNORECASE):
                continue
            value = _adjust_quarter_value(code, idx, quarter_values)
            items.append(
                ExtractedLineItem(
                    normalized_code=code,
                    raw_label=raw_label,
                    value=value,
                    unit=unit,
                    page_number=page_no,
                    source_text=_source_quote(raw_label, value, unit),
                    confidence=88.0,
                )
            )
            break

    tax_value = _sum_current_and_deferred_tax(particular_rows, quarter_values)
    if tax_value is not None:
        items.append(
            ExtractedLineItem(
                normalized_code="tax_expense",
                raw_label="Tax Expense",
                value=tax_value,
                unit="crore",
                page_number=page_no,
                source_text=_source_quote("Tax Expense", tax_value, "crore"),
                confidence=88.0,
            )
        )

    return items


def _adjust_quarter_value(code: str, idx: int, quarter_values: list[float]) -> float:
    """Fix one-column drift when a subtotal row has no label in the PDF text layer."""
    value = quarter_values[idx]
    if code != "pbt" or idx + 1 >= len(quarter_values):
        return value
    nxt = quarter_values[idx + 1]
    # Total Expenses often sits in the value column without a matching label row.
    if value > 50_000 and nxt < value / 5:
        return nxt
    return value


def _sum_current_and_deferred_tax(
    particular_rows: list[tuple[int, str]],
    quarter_values: list[float],
) -> float | None:
    for idx, (_, label_line) in enumerate(particular_rows):
        if idx + 1 >= len(quarter_values):
            break
        if not re.search(r"current\s+tax", label_line, re.IGNORECASE):
            continue
        total = quarter_values[idx]
        if idx + 1 < len(particular_rows) and "deferred" in particular_rows[idx + 1][1].lower():
            total += quarter_values[idx + 1]
        return total
    return None


def _collect_particular_rows(lines: list[str], part_start: int, q_idx: int) -> list[tuple[int, str]]:
    """Row labels for the P&L block before the quarter value column (merge wrapped lines)."""
    rows: list[tuple[int, str]] = []
    i = part_start + 1
    while i < q_idx:
        line = lines[i].strip()
        if not line or _SECTION_HEADER.match(line) or _ROMAN_NUMERAL.match(line):
            i += 1
            continue
        if _OCI_STOP.search(line) or _PL_STOP.match(line):
            break

        merged = line
        while i + 1 < q_idx:
            nxt = lines[i + 1].strip()
            if not nxt or _first_number(nxt) is not None:
                break
            if _SECTION_HEADER.match(nxt) or _ROMAN_NUMERAL.match(nxt) or _OCI_STOP.search(nxt):
                break
            if _QUARTER_SECTION_START.match(nxt):
                break
            if _starts_new_particular(nxt):
                break
            if not _is_wrapped_continuation(merged, nxt):
                break
            merged = f"{merged} {nxt}"
            i += 1

        rows.append((i, merged))
        i += 1
    return rows


def _starts_new_particular(line: str) -> bool:
    """Next line begins a new table row (not a wrapped fragment)."""
    if re.match(r"^less\s*:", line, re.IGNORECASE):
        return True
    if any(pattern.search(line) for pattern, _, _, _ in _LABEL_PATTERNS):
        return True
    return bool(
        re.match(
            r"^(?:\d+\s+)?(?:value of|cost of|purchase|excise|employee|finance|"
            r"depreciation|profit|tax|total|share)\b",
            line,
            re.IGNORECASE,
        )
    )


def _is_financial_table_row(line: str) -> bool:
    """Filter narrative / footnote lines that mention a metric but are not table rows."""
    if re.search(r"\b(?:up|down)\s+[\d.,]+\s*%", line, re.IGNORECASE):
        return False
    if re.match(r"^\d+\s+\S", line):
        return True
    numbers: list[float] = []
    for m in _NUMBER_RE.finditer(line):
        raw = (m.group("num") or "").replace(",", "")
        try:
            val = float(raw)
        except ValueError:
            continue
        if 1900 <= val <= 2099 and val == int(val):
            continue
        numbers.append(val)
    material = [n for n in numbers if abs(n) >= 500]
    return len(material) >= 2


def _is_wrapped_continuation(prev: str, nxt: str) -> bool:
    """True when ``nxt`` continues a broken PDF label line."""
    if prev.endswith(("-", "­", "-­")):
        return True
    if nxt and nxt[0].islower():
        return True
    if "work-in" in prev.lower():
        return True
    return False


def _extract_inline_quarter_rows(text: str, page_no: int) -> list[ExtractedLineItem]:
    """Rows with label + multiple numbers on one line (press-release style tables)."""
    if not (
        _QUARTER_SECTION_START.search(text)
        or re.search(
            r"quarter\s+ended|consolidated\s+financial\s+highlights",
            text,
            re.IGNORECASE,
        )
    ):
        return []

    items: list[ExtractedLineItem] = []
    for line in text.splitlines():
        line_clean = line.strip()
        if not line_clean or len(line_clean) > 240:
            continue
        if not _is_financial_table_row(line_clean):
            continue
        if _SKIP_INLINE_CONTEXT.search(line_clean):
            continue
        if re.search(r"capital expenditure for the quarter", line_clean, re.IGNORECASE):
            continue
        if re.search(r"\bcapex\b", line_clean, re.IGNORECASE) and not re.match(
            r"^\d+\s", line_clean
        ):
            continue
        if _NINE_MONTHS_SECTION_START.match(line_clean) or _YEAR_SECTION_START.match(line_clean):
            continue

        for pattern, code, raw_label, unit in _LABEL_PATTERNS:
            if not pattern.search(line_clean):
                continue
            value = _extract_quarter_number(line_clean, after=pattern)
            if value is None:
                continue
            items.append(
                ExtractedLineItem(
                    normalized_code=code,
                    raw_label=raw_label,
                    value=value,
                    unit=unit,
                    page_number=page_no,
                    source_text=_source_quote(raw_label, value, unit),
                    confidence=82.0,
                )
            )
            break
    return items


def _extract_quarter_number(line: str, *, after: re.Pattern[str]) -> float | None:
    """Pick the current *quarter ended* figure from a multi-column inline row."""
    match = after.search(line)
    if not match:
        return None
    tail = line[match.end() :]
    numbers: list[float] = []
    for m in _NUMBER_RE.finditer(tail):
        raw = (m.group("num") or "").replace(",", "")
        if not raw:
            continue
        try:
            val = float(raw)
        except ValueError:
            continue
        if "(" in m.group(0) and ")" in m.group(0):
            val = -abs(val)
        if 1900 <= val <= 2099 and val == int(val):
            continue
        numbers.append(val)

    if not numbers:
        return None
    idx = _quarter_column_index(numbers)
    return numbers[idx] if idx < len(numbers) else None


def _quarter_column_index(numbers: list[float]) -> int:
    """Choose the quarter-ended column index for a multi-number P&L row."""
    if len(numbers) == 1:
        return 0
    # Four numbers with a large 4th token → Q | prior Y | YoY% | nine-month/YTD → col 0.
    if len(numbers) >= 4 and numbers[3] > max(numbers[0], numbers[1]) * 1.35:
        return 0
    # QoQ layout: prior Q, current Q, abs change, % change → col 1.
    if len(numbers) >= 3 and numbers[2] < max(numbers[0], numbers[1]) * 0.25:
        return 1
    return 0


def _item_from_cumulative_section(
    item: ExtractedLineItem,
    pages: list[tuple[int, str]],
) -> bool:
    """True when the value only appears under Nine Months / Year Ended blocks."""
    if item.page_number is None:
        return False
    page_text = next((t for p, t in pages if p == item.page_number), None)
    if not page_text:
        return False

    val = float(item.value)
    val_tokens = {_format_match_token(val)}
    if val == int(val):
        val_tokens.add(str(int(val)))

    lines = [line.strip() for line in page_text.splitlines()]
    in_quarter = in_nine = in_year = False
    for line in lines:
        if _QUARTER_SECTION_START.match(line):
            in_quarter, in_nine, in_year = True, False, False
            continue
        if _NINE_MONTHS_SECTION_START.match(line):
            in_quarter, in_nine, in_year = False, True, False
            continue
        if _YEAR_SECTION_START.match(line):
            in_quarter, in_nine, in_year = False, False, True
            continue

        if not any(tok in line.replace(",", "") for tok in val_tokens):
            continue
        if in_nine or in_year:
            return True
        if in_quarter:
            return False

    return False


def _format_match_token(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _first_number(line: str) -> float | None:
    for m in _NUMBER_RE.finditer(line):
        raw = (m.group("num") or "").replace(",", "")
        if not raw:
            continue
        try:
            val = float(raw)
        except ValueError:
            continue
        if "(" in m.group(0) and ")" in m.group(0):
            val = -abs(val)
        if 1900 <= val <= 2099 and val == int(val):
            continue
        return val
    return None
