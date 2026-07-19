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
_DATE_MONTH_FIRST_RE = re.compile(
    r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})",
    re.IGNORECASE,
)
_DATE_DMY_SHORT_YEAR_RE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s*['’]?\s*(\d{2})(?!\d)",
    re.IGNORECASE,
)
_HALF_YEAR_HEADER = re.compile(
    r"(?:half[\s-]?year|six\s+months?)\s+ended",
    re.IGNORECASE,
)
_NINE_MONTHS_HEADER = re.compile(r"nine\s+months?\s+ended", re.IGNORECASE)
_YEAR_HEADER = re.compile(
    r"(?:twelve\s+months?|year)\s+ended|\bannual\b",
    re.IGNORECASE,
)
_QUARTER_HEADER = re.compile(
    r"(?:quarter|3\s+months?|three\s+months?)\s+ended",
    re.IGNORECASE,
)
_PERIOD_HEADER = re.compile(
    r"(?:quarter|3\s+months?|three\s+months?|half[\s-]?year|six\s+months?|"
    r"nine\s+months?|twelve\s+months?|year)\s+ended|\bannual\b",
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
    (re.compile(r"\bprofit\b.{0,80}\bbefore\s+tax\b|\bPBT\b", re.I), "pbt"),
    (
        re.compile(r"total\s+comprehensive\s+income(?:\s+for\s+the\s+period)?", re.I),
        "total_comprehensive_income",
    ),
    (re.compile(r"(?:net\s+)?profit\s*(?:/\s*\(loss\))?\s*after\s+tax|\bPAT\b", re.I), "pat"),
    (
        re.compile(
            r"(?:net\s+)?profit\s*(?:/\s*\(?loss\)?)?\s+for\s+(?:the\s+)?period",
            re.I,
        ),
        "pat",
    ),
    (re.compile(r"tax\s+expense|\btax\s+expenses\b", re.I), "tax_expense"),
    (re.compile(r"\bexceptional\s+item", re.I), "exceptional_items"),
    (re.compile(r"\bfinance\s+cost", re.I), "finance_cost"),
    (re.compile(r"depreciation\s*(?:/|,|and)\s*amorti[sz]ation", re.I), "depreciation_and_amortization"),
    (re.compile(r"\binterest\s+earned\b", re.I), "interest_earned"),
    (re.compile(r"\boperating\s+profit\b", re.I), "operating_profit"),
    (re.compile(r"cash\s+(?:flow|generated)\s+from\s+(?:operating|operations)", re.I), "cfo"),
    (
        re.compile(
            r"\bdiluted\b.*(?:\bEPS\b|earnings\s+per\s+(?:equity\s+)?share)|"
            r"\bEPS\b.*\bdiluted\b",
            re.I,
        ),
        "eps_diluted",
    ),
    (
        re.compile(
            r"\bbasic\b.*(?:\bEPS\b|earnings\s+per\s+(?:equity\s+)?share)|"
            r"\bEPS\b.*\bbasic\b|\bearnings\s+per\s+equity\s+share\b",
            re.I,
        ),
        "eps_basic",
    ),
    (re.compile(r"\bEPS\b(?!.*\bdiluted\b)", re.I), "eps_basic"),
]

_GENERIC_CATALOG_ALIASES = {"revenue", "sales", "pat", "pbt", "eps"}

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
    period_type: str | None = None,
) -> list[dict[str, Any]]:
    """Extract deterministic facts for a target period from markdown or plain text.

    The historical function name is retained for API compatibility. ``period_type``
    defaults to the target's type (normally ``quarter``) and also supports ``year``.
    """
    catalog = facts_catalog or {}
    resolved_period_type = _normalise_period_type(
        period_type or getattr(target, "period_type", None) or "quarter"
    )
    by_key: dict[tuple[str, str], dict[str, Any]] = {}

    for row in _extract_from_markdown_tables(
        text,
        target=target,
        period_type=resolved_period_type,
        fact_keys=fact_keys,
        catalog=catalog,
    ):
        by_key[(row["fact_key"], row.get("basis") or "consolidated")] = row

    if resolved_period_type == "quarter" and len(by_key) < max(1, len(fact_keys) // 4):
        for row in _extract_stacked_fallback(text, target=target, fact_keys=fact_keys, catalog=catalog):
            by_key.setdefault((row["fact_key"], row.get("basis") or "consolidated"), row)

    rows = list(by_key.values())
    full_text = text.casefold()
    if (
        "continuing operations" in full_text
        and "discontinued operations" in full_text
        and re.search(
            r"tax\s+expense.{0,40}discontinued\s+operations",
            full_text,
            re.DOTALL,
        )
    ):
        # Apply the ambiguity guard across page/table boundaries as well. A
        # later continuation or summary table must not reintroduce one scoped
        # tax row after the primary statement correctly withheld it.
        rows = [row for row in rows if row["fact_key"] != "tax_expense"]
    for row in rows:
        row.setdefault("period_end", target.quarter_end)
        row.setdefault("period_type", resolved_period_type)
        row.setdefault(
            "extraction_method",
            "deterministic_quarter_column"
            if resolved_period_type == "quarter"
            else "deterministic_period_column",
        )
    return rows


def _extract_from_markdown_tables(
    markdown: str,
    *,
    target: ReportingPeriod,
    period_type: str,
    fact_keys: set[str],
    catalog: dict[str, Any],
) -> list[dict[str, Any]]:
    found: dict[tuple[str, str], dict[str, Any]] = {}
    target_end = date.fromisoformat(target.quarter_end)
    page_markers = _page_markers(markdown)
    statement_columns: dict[tuple[int | None, str], int] = {}
    page_basis: dict[int | None, str] = {}
    revenue_anchors: dict[str, tuple[float, int | None]] = {}
    document_has_statement_conflict = False

    for table, context, start_line in _iter_markdown_tables(markdown):
        if _SEGMENT_CONTEXT.search(context) or _SEGMENT_CONTEXT.search("\n".join(table[:3])):
            continue
        source_page = _page_at_line(page_markers, start_line)
        explicit_basis = _explicit_table_basis(context, table)
        if explicit_basis:
            page_basis[source_page] = explicit_basis
        basis = explicit_basis or page_basis.get(source_page) or "consolidated"
        col_idx = _period_column_index(table, target_end, period_type)
        continuation = False
        if col_idx is None and _looks_like_eps_continuation(table):
            col_idx = statement_columns.get((source_page, basis))
            continuation = col_idx is not None
        if col_idx is None:
            continue
        if (
            not continuation
            and not _looks_like_pl_table(table)
            and not _looks_like_headered_eps_table(table)
        ):
            continue
        score = 2 if _PL_CONTEXT.search(context) else 1
        if _SEGMENT_CONTEXT.search(context):
            score = 0
        if score == 0:
            continue

        if not continuation:
            statement_columns[(source_page, basis)] = col_idx
        table_rows = _rows_from_table(
            table,
            col_idx,
            fact_keys,
            catalog,
            source_page=source_page,
            basis=basis,
            include_header_row=continuation,
            unit_context=f"{context}\n{' '.join(table[:3])}",
        )
        # Prefer the most complete P&L table for a basis. Filings can include
        # later compact disclosure tables that repeat only a few facts; those
        # must not overwrite the detailed statement merely because they occur
        # later in the document.
        table_completeness = len({row["fact_key"] for row in table_rows})
        for row in table_rows:
            key = (row["fact_key"], basis)
            if row["fact_key"] == "revenue_from_operations":
                previous_anchor = revenue_anchors.get(basis)
                current_value = float(row["numeric_value"])
                if previous_anchor is None:
                    revenue_anchors[basis] = (current_value, source_page)
                elif previous_anchor[1] != source_page:
                    previous_value = previous_anchor[0]
                    material_difference = max(
                        1.0,
                        0.005 * max(abs(previous_value), abs(current_value)),
                    )
                    if abs(previous_value - current_value) > material_difference:
                        # Repeated same-basis statements should agree apart from
                        # harmless summary rounding. A material disagreement is
                        # usually a dropped standalone/consolidated heading or
                        # an OCR digit error. Withhold the whole document rather
                        # than guessing which visually parsed table is faithful.
                        document_has_statement_conflict = True
            prev = found.get(key)
            row_priority = _semantic_fact_priority(row)
            table_score = (row_priority, table_completeness, score)
            same_table = prev is not None and prev.get("_table_start_line") == start_line
            same_page = (
                prev is not None and prev.get("source_page") == row.get("source_page")
            )
            same_table_can_replace = (
                same_table
                and row_priority >= prev.get("_table_score", (0, 0, 0))[0]
            )
            same_page_score_wins = (
                same_page
                and table_score > prev.get("_table_score", (0, 0, 0))
            )
            cross_page_score = (table_completeness, score, row_priority)
            previous_cross_page_score = (
                prev.get("_table_score", (0, 0, 0))[1],
                prev.get("_table_score", (0, 0, 0))[2],
                prev.get("_table_score", (0, 0, 0))[0],
            ) if prev is not None else (0, 0, 0)
            if (
                prev is None
                or same_page_score_wins
                or (not same_page and cross_page_score > previous_cross_page_score)
                or same_table_can_replace
            ):
                row["_table_score"] = table_score
                row["_table_start_line"] = start_line
                found[key] = row

    result = [
        {k: v for k, v in row.items() if not k.startswith("_table_")}
        for row in found.values()
    ]
    if document_has_statement_conflict:
        for row in result:
            row["decision"] = "review"
            row["has_unresolved_conflict"] = True
            row["conflict_reason"] = "material_cross_page_statement_disagreement"
    return result


def _semantic_fact_priority(row: dict[str, Any]) -> int:
    """Prefer final post-exceptional rows over pre-exceptional subtotals."""
    text = str(row.get("evidence") or "").lower()
    fact_key = row.get("fact_key")
    if "before exceptional" in text:
        return 0
    if "including exceptional" in text or "after exceptional" in text:
        return 3
    if fact_key == "tax_expense" and "tax on exceptional" in text:
        return 3
    if fact_key == "pat" and "before non-controlling interests" in text:
        return 4
    if fact_key == "pat" and (
        "attributable to" in text
        or "and non-controlling interests" in text
        or "owners of the" in text
    ):
        return 0
    if fact_key == "pat" and "including share" in text:
        return 2
    return 1


def _table_basis(context: str, table: list[str]) -> str:
    return _explicit_table_basis(context, table) or "consolidated"


def _explicit_table_basis(context: str, table: list[str]) -> str | None:
    sample = f"{context}\n{' '.join(table[:3])}"
    statement = r"(?:financial\s+results|statement\s+of\s+profit\s+and\s+loss)"
    if re.search(
        rf"\bstandalone\b(?=.{{0,100}}\b{statement}\b)|"
        rf"\b{statement}\b(?=.{{0,100}}\bstandalone\b)",
        sample,
        re.IGNORECASE | re.DOTALL,
    ):
        return "standalone"
    if re.search(
        rf"\bconsolidated\b(?=.{{0,100}}\b{statement}\b)|"
        rf"\b{statement}\b(?=.{{0,100}}\bconsolidated\b)",
        sample,
        re.IGNORECASE | re.DOTALL,
    ):
        return "consolidated"
    return None


def _looks_like_eps_continuation(table: list[str]) -> bool:
    body = " ".join(cell for row in table for cell in _split_table_row(row))
    return bool(
        re.search(r"earnings\s+per\s+(?:equity\s+)?share", body, re.IGNORECASE)
    )


def _looks_like_headered_eps_table(table: list[str]) -> bool:
    if not _looks_like_eps_continuation(table):
        return False
    head = " ".join(cell for row in table[:4] for cell in _split_table_row(row))
    return bool(
        _PERIOD_HEADER.search(head)
        or any(_row_has_dates(_split_table_row(row)) for row in table[:4])
    )


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
            after: list[str] = []
            for line in lines[i : min(len(lines), i + 8)]:
                if _PAGE_HEADER_RE.match(line.strip()):
                    break
                after.append(line)
            context = "\n".join(
                [
                    *lines[max(0, start - 8) : start],
                    *after,
                ]
            )
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
    first_row = _split_table_row(table[0]) if table else []
    first_label = _clean_label(first_row[0]).lower() if first_row else ""
    # Some issuers (including TCS) leave the label-column header blank instead
    # of writing "Particulars". A non-empty unrelated header is still rejected.
    if "particulars" not in head and first_label:
        return False
    if not _PERIOD_HEADER.search(head) and not _DATE_DMY_RE.search(head):
        return False
    body = " ".join(cell for r in table for cell in _split_table_row(r)).lower()
    markers = sum(
        1
        for pat in (
            r"revenue\s+from\s+operations",
            r"profit\s*(?:/\s*\(loss\))?\s*before\s+tax",
            r"profit\s*(?:/\s*\(loss\))?\s*after\s+tax",
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
    m = _DATE_MONTH_FIRST_RE.search(cell)
    if m:
        month = _month_from_name(m.group(1))
        if month:
            return date(int(m.group(3)), month, int(m.group(2)))
    m = _DATE_DMY_SHORT_YEAR_RE.search(cell)
    if m:
        month = _month_from_name(m.group(2))
        if month:
            return date(2000 + int(m.group(3)), month, int(m.group(1)))
    return None


def _period_column_index(
    table: list[str], target_end: date, period_type: str
) -> int | None:
    """Return the data column for the requested period type and end date."""
    header_rows: list[list[str]] = []
    for line in table:
        cells = _split_table_row(line)
        if not cells:
            continue
        if _is_table_separator(line):
            continue
        if _row_has_dates(cells) or _PERIOD_HEADER.search(" ".join(cells)):
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

    desired_section = _normalise_period_type(period_type)
    period_matches = [i for i in matches if sections[i] == desired_section]
    if period_matches:
        pick = period_matches[0]
    elif len(matches) == 1:
        pick = matches[0]
    else:
        # The same date commonly appears in both quarter and year columns. If
        # the table does not prove which section a match belongs to, abstain.
        return None
    return max(0, pick - 1) if pick > 0 else pick


def _normalise_period_type(period_type: str) -> str:
    value = str(period_type or "quarter").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "annual": "year",
        "full_year": "year",
        "twelve_months": "year",
        "six_months": "half_year",
        "halfyear": "half_year",
        "nine_month": "nine_months",
    }
    return aliases.get(value, value)


def _section_type(text: str) -> str | None:
    if _QUARTER_HEADER.search(text):
        return "quarter"
    if _HALF_YEAR_HEADER.search(text):
        return "half_year"
    if _NINE_MONTHS_HEADER.search(text):
        return "nine_months"
    if _YEAR_HEADER.search(text):
        return "year"
    return None


def _expand_sections(header_row: list[str], ncols: int) -> list[str]:
    """Expand section headers across data columns (handles merged header cells)."""
    markers: list[tuple[int, str]] = []
    for i, cell in enumerate(header_row):
        # Column zero is the row-label/title column. OCR can put the complete
        # statement title there, including period words that are not section
        # markers for any numeric column.
        if i == 0:
            continue
        section = _section_type(cell)
        if section:
            markers.append((i, section))

    sections = ["label"] * ncols
    if not markers:
        return sections

    # PDF-to-Markdown sometimes collapses colspan cells, e.g. a six-column
    # table becomes ``Particulars | Quarter ended | Year ended``. Reconstruct
    # the conventional 3-quarter/2-year layout before matching duplicate dates.
    if len(header_row) < ncols and len(markers) >= 2:
        cursor = markers[0][0]
        default_width = {"quarter": 3, "half_year": 2, "nine_months": 2, "year": 2}
        for j, (_, sec) in enumerate(markers):
            remaining = ncols - cursor
            width = remaining if j == len(markers) - 1 else min(default_width[sec], remaining)
            for c in range(cursor, min(ncols, cursor + width)):
                sections[c] = sec
            cursor += width
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
    basis: str = "consolidated",
    include_header_row: bool = False,
    unit_context: str = "",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    data_started = include_header_row
    eps_section = False

    for line in table:
        if _is_table_separator(line):
            data_started = True
            continue
        cells = _split_table_row(line)
        if not cells or not data_started:
            continue
        if len(cells) <= col_idx + 1:
            continue

        # Some tables keep serial number and particulars in separate columns.
        # Use the rightmost textual cell before the selected value column so a
        # section label such as "Tax expense" cannot be paired with a child
        # row's current-tax value.
        label = ""
        for candidate in reversed(cells[: col_idx + 1]):
            cleaned = _clean_label(candidate)
            # A period selector is expressed as a zero-based data-column
            # index.  With multi-period tables, the cells before that value
            # therefore include earlier numeric values as well as the label
            # columns.  Select the rightmost *textual* label; otherwise a
            # prior-period amount (for example ``5,525.01``) is mistaken for
            # the row name and every annual/half-year value is dropped.
            if cleaned and re.search(r"[A-Za-z]", cleaned):
                label = cleaned
                break
        if not label or re.match(r"^\d+\.?\s*$", label):
            continue
        if re.search(
            r"earnings\s+per\s+(?:equity\s+)?share", label, re.IGNORECASE
        ):
            eps_section = True
        value_cell = cells[col_idx + 1] if col_idx + 1 < len(cells) else cells[-1]
        numeric = _parse_number(value_cell)
        if numeric is None:
            continue

        combined_eps = (
            bool(re.search(r"\bbasic\b", label, re.IGNORECASE))
            and bool(re.search(r"\bdiluted\b", label, re.IGNORECASE))
            and bool(
                re.search(
                    r"\bEPS\b|earnings\s+per\s+(?:equity\s+)?share",
                    label,
                    re.IGNORECASE,
                )
            )
        )
        if combined_eps and "eps_basic" in fact_keys:
            fact_key = "eps_basic"
        else:
            fact_key = _match_fact_key(label, fact_keys, catalog)
        if fact_key is None and eps_section:
            if re.search(r"\bbasic\b", label, re.IGNORECASE) and "eps_basic" in fact_keys:
                fact_key = "eps_basic"
            elif re.search(r"\bdiluted\b", label, re.IGNORECASE) and "eps_diluted" in fact_keys:
                fact_key = "eps_diluted"
        if not fact_key:
            continue

        matched_keys = [fact_key]
        if (
            fact_key == "eps_basic"
            and "eps_diluted" in fact_keys
            and combined_eps
        ):
            matched_keys.append("eps_diluted")
        for matched_key in matched_keys:
            catalog_unit = catalog.get(matched_key, {}).get("unit")
            normalized_numeric, normalization_note = _normalise_statement_unit(
                numeric,
                catalog_unit=catalog_unit,
                unit_context=unit_context,
            )
            evidence = f"{label} {value_cell.strip()}"
            if normalization_note:
                evidence = f"{evidence}; {normalization_note}"
            row: dict[str, Any] = {
                "fact_key": matched_key,
                "numeric_value": normalized_numeric,
                "unit": catalog_unit,
                "basis": basis,
                "evidence": evidence,
                "confidence": 0.92,
            }
            if source_page is not None:
                row["source_page"] = source_page
            rows.append(row)
    table_text = " ".join(
        cell for line in table for cell in _split_table_row(line)
    ).casefold()
    if (
        "continuing operations" in table_text
        and "discontinued operations" in table_text
        and sum(row["fact_key"] == "tax_expense" for row in rows) > 1
    ):
        # The core contract has no operation-scope dimension.  A continuing
        # tax row and a discontinued tax row cannot safely collapse into one
        # published tax_expense fact, so retain neither automatically.
        rows = [row for row in rows if row["fact_key"] != "tax_expense"]
    return rows


def _normalise_statement_unit(
    value: float,
    *,
    catalog_unit: Any,
    unit_context: str,
) -> tuple[float, str | None]:
    """Normalize common Indian statement scales to the catalog's crore unit."""
    if str(catalog_unit or "").strip().casefold() != "crore":
        return value, None
    sample = unit_context.casefold().replace("₹", "rs")
    scale: float | None = None
    source_unit = ""
    if re.search(
        r"\b(?:(?:inr|indian\s+rupees|rs\.?)\s+(?:in\s+)?)?millions?\b",
        sample,
    ):
        scale, source_unit = 0.1, "million"
    elif re.search(r"\b(?:inr|rs\.?)?\s*in\s+lakhs?\b", sample):
        scale, source_unit = 0.01, "lakh"
    elif re.search(r"\b(?:inr|rs\.?)?\s*in\s+(?:'000|thousands?)\b", sample):
        scale, source_unit = 0.0001, "thousand"
    if scale is None:
        return value, None
    normalized = round(value * scale, 10)
    # ``:g`` defaults to six significant digits and can round a normalized
    # amount (14315.86 -> 14315.9), breaking the evidence/value contract.
    return normalized, f"{value} {source_unit} = {normalized} crore"


def _clean_label(text: str) -> str:
    return re.sub(r"[*_]+", "", text).strip()


def _match_fact_key(label: str, fact_keys: set[str], catalog: dict[str, Any]) -> str | None:
    low = label.lower()
    normalized = re.sub(r"^\s*(?:\d+|[a-z])?[.)]?\s*", "", low).strip()
    # Ratio and margin disclosures can contain a core fact name while their
    # numeric cell is a percentage (for example, "net profit after tax /
    # turnover").  They are not statement amounts and must never replace the
    # corresponding P&L row.
    if re.search(r"\b(?:margin|ratio)\b|/\s*turnover\b", low):
        return None
    # Financial-statement row semantics take precedence over embedded catalog
    # names. For example, "profit after exceptional items and before tax" is
    # PBT, not the exceptional-items fact merely because that phrase appears.
    for pattern, code in _LABEL_PATTERNS:
        if code not in fact_keys:
            continue
        if pattern.search(label):
            return code
    aliases = sorted(_catalog_aliases(catalog).items(), key=lambda item: len(item[0]), reverse=True)
    for alias, canonical in aliases:
        if canonical not in fact_keys:
            continue
        if alias in _GENERIC_CATALOG_ALIASES:
            if normalized == alias:
                return canonical
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", low):
            return canonical
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
        catalog_unit = catalog.get(fact_key, {}).get("unit")
        normalized_val, normalization_note = _normalise_statement_unit(
            val,
            catalog_unit=catalog_unit,
            unit_context=text,
        )
        evidence = f"{label} {val:,.2f}"
        if normalization_note:
            evidence = f"{evidence}; {normalization_note}"
        items.append(
            {
                "fact_key": fact_key,
                "numeric_value": normalized_val,
                "unit": catalog_unit,
                "basis": "consolidated",
                "evidence": evidence,
                "confidence": 0.75,
            }
        )
    return items
