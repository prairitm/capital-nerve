"""Shared SQL lookups used across routers."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from catalog import document_display_config, metric_meta, select_display_signals
from serializers import (
    document_dict,
    extracted_value_dict,
    event_dict,
    quarter_label,
    metric_value_dict,
    signal_dict,
)

# Headline facts shown in the financial snapshot, in display order.
SNAPSHOT_FACTS: list[tuple[str, str]] = [
    ("revenue_from_operations", "Revenue"),
    ("ebitda", "EBITDA"),
    ("pat", "PAT"),
    ("eps_basic", "EPS"),
]

DOCUMENT_TYPE_ORDER = {
    "FINANCIAL_RESULT": 0,
    "INVESTOR_PRESENTATION": 1,
    "EARNINGS_CALL_TRANSCRIPT": 2,
    "CONCALL_TRANSCRIPT": 2,
}

DOCUMENT_TYPE_LABELS = {
    "FINANCIAL_RESULT": "Financial Result",
    "INVESTOR_PRESENTATION": "Investor Presentation",
    "EARNINGS_CALL_TRANSCRIPT": "Earnings Call",
    "CONCALL_TRANSCRIPT": "Earnings Call",
}

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

PERIOD_ENDED_RE = re.compile(
    r"(?:period|quarter)\s+ended\s+"
    r"(?:(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)|([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?)"
    r",?\s+(\d{4})",
    re.IGNORECASE,
)


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def uses_eight_step_metrics(conn: sqlite3.Connection) -> bool:
    cols = table_columns(conn, "metrics")
    return {"metric_id", "company_id", "event_id", "metric_code", "value"}.issubset(cols)


def normalize_document_type(value: str | None) -> str:
    if not value:
        return "DOCUMENT"
    key = value.strip().upper().replace(" ", "_").replace("-", "_")
    if key in {"QUARTERLY_RESULT", "FINANCIAL_RESULTS"}:
        return "FINANCIAL_RESULT"
    if key in {"PRESENTATION", "INVESTOR_PRESENTATION"}:
        return "INVESTOR_PRESENTATION"
    if key in {"EARNINGS_CALL", "EARNINGS_CALL_TRANSCRIPT", "CONCALL", "CONCALL_TRANSCRIPT"}:
        return "EARNINGS_CALL_TRANSCRIPT"
    return key


def document_type_label(value: str | None) -> str:
    key = normalize_document_type(value)
    return DOCUMENT_TYPE_LABELS.get(key, key.replace("_", " ").title())


def find_company(conn: sqlite3.Connection, ticker: str) -> sqlite3.Row | None:
    """Resolve a company by ticker (case-insensitive), id, or name."""
    row = conn.execute(
        "SELECT * FROM companies WHERE ticker = ? COLLATE NOCASE", (ticker,)
    ).fetchone()
    if row:
        return row
    row = conn.execute("SELECT * FROM companies WHERE id = ?", (ticker,)).fetchone()
    if row:
        return row
    return conn.execute(
        "SELECT * FROM companies WHERE name = ? COLLATE NOCASE", (ticker,)
    ).fetchone()


def latest_event(conn: sqlite3.Connection, company_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM events
        WHERE company_id = ?
        ORDER BY event_date DESC, id DESC
        LIMIT 1
        """,
        (company_id,),
    ).fetchone()


def company_events(conn: sqlite3.Connection, company_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM events
        WHERE company_id = ?
        ORDER BY event_date DESC, id DESC
        """,
        (company_id,),
    ).fetchall()


def event_signals(conn: sqlite3.Connection, event_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM signals
        WHERE event_id = ?
        ORDER BY CASE UPPER(COALESCE(severity, ''))
            WHEN 'CRITICAL' THEN 0
            WHEN 'HIGH' THEN 1
            WHEN 'MEDIUM' THEN 2
            WHEN 'LOW' THEN 3
            ELSE 9
        END
        """,
        (event_id,),
    ).fetchall()
    event = conn.execute("SELECT event_type FROM events WHERE id = ?", (event_id,)).fetchone()
    event_type = event["event_type"] if event else None
    return select_display_signals([signal_dict(r) for r in rows], event_type)


def event_metrics(conn: sqlite3.Connection, event_id: str) -> list[dict[str, Any]]:
    if uses_eight_step_metrics(conn):
        period_end = _event_period_end(conn, event_id)
        rows = conn.execute(
            """
            SELECT m.*, ? AS period_end, NULL AS period_start
            FROM metrics m
            WHERE m.event_id = ?
            """,
            (period_end, event_id),
        ).fetchall()
        return [metric_value_dict(r) for r in rows]

    rows = conn.execute(
        """
        SELECT mv.*, m.metric_code AS metric_code
        FROM metric_values mv
        JOIN metrics m ON m.id = mv.metric_id
        WHERE mv.event_id = ?
        """,
        (event_id,),
    ).fetchall()
    return [metric_value_dict(r) for r in rows]


def _period_label_from_end(period_end: str | None) -> str | None:
    if not period_end or len(period_end) < 10:
        return None
    try:
        year = int(period_end[:4])
        month = int(period_end[5:7])
    except ValueError:
        return period_end
    fy_start = year if month >= 4 else year - 1
    quarter = ((month - 4) % 12) // 3 + 1
    return quarter_label({"fiscal_year": fy_start, "fiscal_quarter": quarter})


def _period_end_from_label(period_label: str | None) -> str | None:
    if not period_label:
        return None
    match = re.search(r"\bQ([1-4])\s+FY(\d{4})-\d{2}\b", period_label, re.IGNORECASE)
    fy_start = None
    if match:
        quarter = int(match.group(1))
        fy_start = int(match.group(2))
    else:
        short_match = re.search(r"\bQ([1-4])\s+FY(\d{2})\b", period_label, re.IGNORECASE)
        if not short_match:
            return None
        quarter = int(short_match.group(1))
        fy_end_short = int(short_match.group(2))
        fy_end = 2000 + fy_end_short
        fy_start = fy_end - 1
    if fy_start is None:
        return None
    if quarter == 1:
        return f"{fy_start}-06-30"
    if quarter == 2:
        return f"{fy_start}-09-30"
    if quarter == 3:
        return f"{fy_start}-12-31"
    return f"{fy_start + 1}-03-31"


def period_scope(period_end: str | None, current_period_end: str | None) -> str:
    if not period_end or not current_period_end:
        return "UNKNOWN"
    if period_end == current_period_end:
        return "CURRENT"
    if period_end == _prior_year_end(current_period_end):
        return "PY"
    if period_end == _prior_quarter_end(current_period_end):
        return "PQ"
    return "COMPARATIVE"


def event_fact_periods(conn: sqlite3.Connection, event_id: str) -> list[dict[str, Any]]:
    current_period_end = _event_period_end(conn, event_id)
    extracted_rows = conn.execute(
        """
        SELECT period_end, COUNT(*) AS facts_count
        FROM extracted_values
        WHERE event_id = ? AND period_end IS NOT NULL
        GROUP BY period_end
        ORDER BY period_end DESC
        """,
        (event_id,),
    ).fetchall()
    period_counts: dict[str, int] = {
        row["period_end"]: row["facts_count"]
        for row in extracted_rows
        if row["period_end"]
    }

    if has_table(conn, "fact_observations"):
        observation_rows = conn.execute(
            """
            SELECT period, COUNT(*) AS facts_count
            FROM fact_observations
            WHERE event_id = ? AND period IS NOT NULL
            GROUP BY period
            """,
            (event_id,),
        ).fetchall()
        for row in observation_rows:
            pe = _period_end_from_label(row["period"])
            if pe and pe not in period_counts:
                period_counts[pe] = row["facts_count"]

    periods: list[dict[str, Any]] = []
    for pe, facts_count in period_counts.items():
        scope = period_scope(pe, current_period_end)
        periods.append(
            {
                "period_end": pe,
                "period_label": _period_label_from_end(pe),
                "scope": scope,
                "facts_count": facts_count,
                "is_current_event_period": scope == "CURRENT",
            }
        )
    return sorted(
        periods,
        key=lambda p: (
            _SCOPE_ORDER.get(p["scope"], 9),
            p["period_end"] or "",
        ),
    )


def event_facts(
    conn: sqlite3.Connection,
    event_id: str,
    *,
    period_end: str | None = None,
) -> list[dict[str, Any]]:
    current_period_end = _event_period_end(conn, event_id)
    selected_period_end = period_end or current_period_end
    if selected_period_end:
        rows = conn.execute(
            """
            SELECT * FROM extracted_values
            WHERE event_id = ? AND period_end = ?
            ORDER BY
                CASE basis WHEN 'consolidated' THEN 0 WHEN 'standalone' THEN 1 ELSE 2 END,
                value_code
            """,
            (event_id, selected_period_end),
        ).fetchall()
        if not rows and has_table(conn, "fact_observations"):
            cols = _observation_select_columns(conn)
            observation_rows = conn.execute(
                f"""
                SELECT {cols}
                FROM fact_observations
                WHERE event_id = ? AND period IS NOT NULL
                ORDER BY fact_code
                """,
                (event_id,),
            ).fetchall()
            obs_facts: list[dict[str, Any]] = []
            for row in observation_rows:
                if _period_end_from_label(row["period"]) != selected_period_end:
                    continue
                obs_facts.append(_fact_from_observation(row, period_end=selected_period_end))
            rows = obs_facts
    else:
        rows = conn.execute(
            """
            SELECT * FROM extracted_values
            WHERE event_id = ?
            ORDER BY
                CASE basis WHEN 'consolidated' THEN 0 WHEN 'standalone' THEN 1 ELSE 2 END,
                value_code
            """,
            (event_id,),
        ).fetchall()

    scope = period_scope(selected_period_end, current_period_end)
    facts: list[dict[str, Any]] = []
    for row in rows:
        fact = extracted_value_dict(row)
        fact["scope"] = period_scope(fact.get("period_end"), current_period_end) or scope
        facts.append(fact)
    return facts


def _fy_quarter_from_period_end(period_end: str | None) -> tuple[int, int] | None:
    if not period_end or len(period_end) < 10:
        return None
    try:
        year = int(period_end[:4])
        month = int(period_end[5:7])
    except ValueError:
        return None
    fy_start = year if month >= 4 else year - 1
    quarter = ((month - 4) % 12) // 3 + 1
    return fy_start, quarter


def _period_end_from_text(text: str | None) -> str | None:
    if not text:
        return None
    from_label = _period_end_from_label(text)
    if from_label:
        return from_label
    match = PERIOD_ENDED_RE.search(text)
    if not match:
        return None
    day = match.group(1) or match.group(4)
    month_name = match.group(2) or match.group(3)
    year = match.group(5)
    month = MONTHS.get(month_name.lower())
    if not month:
        return None
    return f"{int(year):04d}-{month:02d}-{int(day):02d}"


PRESENTATION_DIMENSION_COLUMNS = (
    "segment",
    "geography",
    "product",
    "channel",
    "project",
    "customer_type",
    "metric_context",
    "scope_level",
    "scope_name",
    "fact_type",
    "value_lower",
    "value_upper",
    "sentiment",
    "is_explicit_guidance",
)


def _optional_select(
    cols: set[str],
    column: str,
    *,
    alias: str | None = None,
    source_alias: str | None = None,
) -> str:
    output = alias or column
    if column not in cols:
        return f"NULL AS {output}"
    prefix = f"{source_alias}." if source_alias else ""
    return f"{prefix}{column} AS {output}"


def _scalar_fact_filter(conn: sqlite3.Connection, table: str, alias: str | None = None) -> str:
    cols = table_columns(conn, table)
    prefix = f"{alias}." if alias else ""
    filters = [
        f"AND COALESCE({prefix}{column}, '') = ''"
        for column in (
            "segment",
            "geography",
            "product",
            "channel",
            "project",
            "customer_type",
            "metric_context",
        )
        if column in cols
    ]
    return "\n".join(filters)


def _observation_select_columns(conn: sqlite3.Connection) -> str:
    cols = table_columns(conn, "fact_observations")
    value_text = "value_text" if "value_text" in cols else "NULL AS value_text"
    optional = [
        _optional_select(cols, column)
        for column in PRESENTATION_DIMENSION_COLUMNS
    ]
    return (
        "observation_id, company_id, event_id, document_id, fact_code, "
        f"value, {value_text}, unit, period, source_text, source_page, "
        f"{', '.join(optional)}, confidence"
    )


def _resolved_select_columns(conn: sqlite3.Connection) -> str:
    cols = table_columns(conn, "resolved_facts")
    value_text = (
        "rf.resolved_value_text AS resolved_value_text"
        if "resolved_value_text" in cols
        else "NULL AS resolved_value_text"
    )
    optional = [
        _optional_select(cols, column, source_alias="rf")
        for column in PRESENTATION_DIMENSION_COLUMNS
    ]
    return (
        "rf.resolved_fact_id, rf.fact_code, rf.resolved_value, "
        f"{value_text}, rf.unit, {', '.join(optional)}, rf.selected_observation_id, "
        "rf.resolution_status, rf.confidence AS resolved_confidence"
    )


def _fact_from_observation(row: sqlite3.Row, *, period_end: str | None = None) -> dict[str, Any]:
    fact = extracted_value_dict(
        {
            "value_code": row["fact_code"],
            "value_numeric": row["value"],
            "value_text": row["value_text"],
            "unit": row["unit"],
            "period_type": "quarter" if period_end else None,
            "period_start": None,
            "period_end": period_end,
            "basis": None,
            "segment": row["segment"],
            "geography": row["geography"],
            "product": row["product"],
            "channel": row["channel"],
            "project": row["project"],
            "customer_type": row["customer_type"],
            "metric_context": row["metric_context"],
            "scope_level": row["scope_level"],
            "scope_name": row["scope_name"],
            "fact_type": row["fact_type"],
            "value_lower": row["value_lower"],
            "value_upper": row["value_upper"],
            "sentiment": row["sentiment"],
            "is_explicit_guidance": row["is_explicit_guidance"],
            "source_text": row["source_text"],
            "source_page": row["source_page"],
            "confidence": row["confidence"],
            "document_id": row["document_id"],
        }
    )
    fact["observation_id"] = row["observation_id"]
    return fact


def _fact_from_resolved(row: sqlite3.Row, *, period_end: str | None = None) -> dict[str, Any]:
    fact = extracted_value_dict(
        {
            "value_code": row["fact_code"],
            "value_numeric": row["resolved_value"],
            "value_text": row["resolved_value_text"] or row["value_text"],
            "unit": row["unit"],
            "period_type": "quarter" if period_end else None,
            "period_start": None,
            "period_end": period_end,
            "basis": None,
            "segment": row["segment"],
            "geography": row["geography"],
            "product": row["product"],
            "channel": row["channel"],
            "project": row["project"],
            "customer_type": row["customer_type"],
            "metric_context": row["metric_context"],
            "scope_level": row["scope_level"],
            "scope_name": row["scope_name"],
            "fact_type": row["fact_type"],
            "value_lower": row["value_lower"],
            "value_upper": row["value_upper"],
            "sentiment": row["sentiment"],
            "is_explicit_guidance": row["is_explicit_guidance"],
            "resolved_fact_id": row["resolved_fact_id"],
            "resolution_status": row["resolution_status"],
            "source_text": row["source_text"],
            "source_page": row["source_page"],
            "confidence": row["resolved_confidence"] or row["confidence"],
            "document_id": row["document_id"],
        }
    )
    fact["observation_id"] = row["selected_observation_id"] or row["observation_id"]
    fact["resolved_fact_id"] = row["resolved_fact_id"]
    fact["resolution_status"] = row["resolution_status"]
    return fact


def _best_observation_by_fact(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    best: dict[tuple[Any, ...], sqlite3.Row] = {}

    def identity(row: sqlite3.Row) -> tuple[Any, ...]:
        return (
            row["fact_code"],
            row["segment"],
            row["geography"],
            row["product"],
            row["channel"],
            row["project"],
            row["customer_type"],
            row["metric_context"],
            row["scope_level"],
            row["scope_name"],
        )

    def score(row: sqlite3.Row) -> tuple[float, int, int, str]:
        confidence = float(row["confidence"] or 0)
        has_source = 1 if row["source_text"] else 0
        has_page = 1 if row["source_page"] is not None else 0
        return (confidence, has_source, has_page, str(row["observation_id"]))

    for row in rows:
        key = identity(row)
        current = best.get(key)
        if current is None or score(row) > score(current):
            best[key] = row
    return [best[key] for key in sorted(best, key=lambda parts: tuple(str(p or "") for p in parts))]


def document_fact_periods(
    conn: sqlite3.Connection,
    document_id: str | None,
    *,
    fallback_event_id: str | None = None,
) -> list[dict[str, Any]]:
    if document_id and has_table(conn, "fact_observations"):
        rows = conn.execute(
            """
            SELECT period, COUNT(*) AS facts_count
            FROM fact_observations
            WHERE document_id = ? AND period IS NOT NULL
            GROUP BY period
            """,
            (document_id,),
        ).fetchall()
        period_counts: dict[str, int] = {}
        for row in rows:
            period_end = _period_end_from_label(row["period"])
            if not period_end:
                continue
            period_counts[period_end] = period_counts.get(period_end, 0) + int(row["facts_count"])
        periods: list[dict[str, Any]] = []
        for period_end, facts_count in period_counts.items():
            periods.append(
                {
                    "period_end": period_end,
                    "period_label": _period_label_from_end(period_end),
                    "scope": "CURRENT",
                    "facts_count": facts_count,
                    "is_current_event_period": True,
                }
            )
        if periods:
            return sorted(periods, key=lambda p: p["period_end"] or "", reverse=True)

    if fallback_event_id:
        return event_fact_periods(conn, fallback_event_id)
    return []


def document_facts(
    conn: sqlite3.Connection,
    *,
    document_id: str | None,
    fallback_event_id: str | None = None,
    period_end: str | None = None,
) -> list[dict[str, Any]]:
    if document_id and has_table(conn, "fact_observations"):
        cols = _observation_select_columns(conn)
        if fallback_event_id and has_table(conn, "resolved_facts"):
            resolved_cols = _resolved_select_columns(conn)
            observation_cols = table_columns(conn, "fact_observations")
            observation_value_text = (
                "fo.value_text AS value_text"
                if "value_text" in observation_cols
                else "NULL AS value_text"
            )
            resolved_rows = conn.execute(
                f"""
                SELECT {resolved_cols},
                       fo.observation_id, fo.company_id, fo.event_id, fo.document_id,
                       fo.value, {observation_value_text}, fo.period, fo.source_text,
                       fo.source_page, fo.confidence
                FROM resolved_facts rf
                JOIN fact_observations fo ON fo.observation_id = rf.selected_observation_id
                WHERE rf.event_id = ? AND fo.document_id = ?
                ORDER BY rf.fact_code
                """,
                (fallback_event_id, document_id),
            ).fetchall()
            resolved_facts: list[dict[str, Any]] = []
            for row in resolved_rows:
                row_period_end = _period_end_from_label(row["period"])
                if period_end and row_period_end != period_end:
                    continue
                resolved_facts.append(_fact_from_resolved(row, period_end=row_period_end))
            if resolved_facts:
                return resolved_facts

        rows = conn.execute(
            f"""
            SELECT {cols}
            FROM fact_observations
            WHERE document_id = ?
            ORDER BY fact_code, source_page
            """,
            (document_id,),
        ).fetchall()
        facts: list[dict[str, Any]] = []
        for row in rows:
            row_period_end = _period_end_from_label(row["period"])
            if period_end and row_period_end != period_end:
                continue
            facts.append(row)
        if facts:
            return [
                _fact_from_observation(row, period_end=_period_end_from_label(row["period"]))
                for row in _best_observation_by_fact(facts)
            ]

    if fallback_event_id:
        return event_facts(conn, fallback_event_id, period_end=period_end)
    return []


def _event_document(conn: sqlite3.Connection, event: sqlite3.Row) -> sqlite3.Row | None:
    if not event["document_id"]:
        return None
    return conn.execute(
        "SELECT * FROM documents WHERE id = ?", (event["document_id"],)
    ).fetchone()


def _related_quarter_events(
    conn: sqlite3.Connection,
    event: sqlite3.Row,
) -> list[sqlite3.Row]:
    if event["fiscal_year"] is not None and event["fiscal_quarter"] is not None:
        return conn.execute(
            """
            SELECT * FROM events
            WHERE company_id = ?
              AND fiscal_year = ?
              AND fiscal_quarter = ?
              AND document_id IS NOT NULL
              AND COALESCE(status, '') = 'processed'
            """,
            (event["company_id"], event["fiscal_year"], event["fiscal_quarter"]),
        ).fetchall()
    if event["event_date"]:
        return conn.execute(
            """
            SELECT * FROM events
            WHERE company_id = ?
              AND event_date = ?
              AND document_id IS NOT NULL
              AND COALESCE(status, '') = 'processed'
            """,
            (event["company_id"], event["event_date"]),
        ).fetchall()
    return [event] if event["document_id"] else []


def _orphan_documents_for_event_period(
    conn: sqlite3.Connection,
    event: sqlite3.Row,
    seen_document_ids: set[str],
) -> list[sqlite3.Row]:
    if event["fiscal_year"] is None or event["fiscal_quarter"] is None:
        return []
    rows = conn.execute(
        """
        SELECT d.*
        FROM documents d
        LEFT JOIN events e ON e.document_id = d.id
        WHERE d.company_id = ?
          AND e.id IS NULL
          AND COALESCE(d.status, '') = 'processed'
        """,
        (event["company_id"],),
    ).fetchall()
    matches: list[sqlite3.Row] = []
    for row in rows:
        if row["id"] in seen_document_ids:
            continue
        kind = normalize_document_type(row["document_kind"])
        if kind not in DOCUMENT_TYPE_ORDER:
            continue
        period_end = _period_end_from_text(row["title"])
        fyq = _fy_quarter_from_period_end(period_end)
        if fyq == (event["fiscal_year"], event["fiscal_quarter"]):
            matches.append(row)
    return matches


def _section_sort_key(section: dict[str, Any]) -> tuple[int, str, str]:
    doc_type = section["document_type"]
    event = section.get("event") or {}
    document = section.get("document") or {}
    return (
        DOCUMENT_TYPE_ORDER.get(doc_type, 99),
        event.get("event_date") or document.get("ingested_at") or "",
        section["key"],
    )


def _quarter_period_end_from_event(event: sqlite3.Row | None) -> str | None:
    if not event or event["fiscal_year"] is None or event["fiscal_quarter"] is None:
        return None
    quarter = int(event["fiscal_quarter"])
    fy_start = int(event["fiscal_year"])
    if quarter == 1:
        return f"{fy_start}-06-30"
    if quarter == 2:
        return f"{fy_start}-09-30"
    if quarter == 3:
        return f"{fy_start}-12-31"
    return f"{fy_start + 1}-03-31"


def quarter_document_sections(
    conn: sqlite3.Connection,
    event: sqlite3.Row,
) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    seen_document_ids: set[str] = set()

    for related_event in _related_quarter_events(conn, event):
        doc = _event_document(conn, related_event)
        if not doc:
            continue
        seen_document_ids.add(doc["id"])
        sections.append(
            _quarter_document_section(
                conn,
                event=related_event,
                document=doc,
            )
        )

    for doc in _orphan_documents_for_event_period(conn, event, seen_document_ids):
        seen_document_ids.add(doc["id"])
        sections.append(_quarter_document_section(conn, event=None, document=doc))

    return sorted(sections, key=_section_sort_key)


def _quarter_document_section(
    conn: sqlite3.Connection,
    *,
    event: sqlite3.Row | None,
    document: sqlite3.Row,
) -> dict[str, Any]:
    document_type = normalize_document_type(document["document_kind"] or (event["event_type"] if event else None))
    fallback_event_id = event["id"] if event else None
    fact_periods = document_fact_periods(
        conn,
        document["id"],
        fallback_event_id=fallback_event_id,
    )
    selected_period_end = _quarter_period_end_from_event(event) or _period_end_from_text(
        document["title"]
    ) or next(
        (
            p["period_end"]
            for p in fact_periods
            if p.get("is_current_event_period")
        ),
        fact_periods[0]["period_end"] if fact_periods else None,
    )
    facts = document_facts(
        conn,
        document_id=document["id"],
        fallback_event_id=fallback_event_id,
        period_end=selected_period_end,
    )
    metrics = event_metrics(conn, fallback_event_id) if fallback_event_id else []
    signals = event_signals(conn, fallback_event_id) if fallback_event_id else []
    return {
        "key": f"{document_type}:{document['id']}",
        "document_type": document_type,
        "label": document_type_label(document_type),
        "event": event_dict(event) if event else None,
        "document": document_dict(document),
        "facts": facts,
        "fact_periods": fact_periods,
        "selected_fact_period_end": selected_period_end,
        "metrics": metrics,
        "signals": signals,
        "display": document_display_config(document_type),
        "presentation_summary": _presentation_summary(
            conn,
            document_id=document["id"],
            event_id=fallback_event_id,
        )
        if document_type == "INVESTOR_PRESENTATION"
        else None,
        "counts": {
            "facts": len(facts),
            "metrics": len(metrics),
            "signals": len(signals),
        },
    }


def _presentation_summary(
    conn: sqlite3.Connection,
    *,
    document_id: str,
    event_id: str | None,
) -> dict[str, Any]:
    segments: list[dict[str, Any]] = []
    if has_table(conn, "presentation_segments"):
        params: list[Any] = [document_id]
        event_filter = ""
        if event_id:
            event_filter = "AND event_id = ?"
            params.append(event_id)
        segment_cols = table_columns(conn, "presentation_segments")
        slug_col = "segment_slug" if "segment_slug" in segment_cols else "NULL AS segment_slug"
        rows = conn.execute(
            f"""
            SELECT segment_name, {slug_col}, aliases_json, slides_json, confidence
            FROM presentation_segments
            WHERE document_id = ?
            {event_filter}
            ORDER BY segment_name
            """,
            tuple(params),
        ).fetchall()
        for row in rows:
            segments.append(
                {
                    "name": row["segment_name"],
                    "slug": row["segment_slug"],
                    "aliases": row["aliases_json"],
                    "slides": row["slides_json"],
                    "confidence": row["confidence"],
                }
            )

    scope_counts: dict[str, int] = {}
    fact_type_counts: dict[str, int] = {}
    guidance_count = 0
    average_confidence = None
    if has_table(conn, "fact_observations"):
        obs_cols = table_columns(conn, "fact_observations")
        scope_expr = "COALESCE(scope_level, 'unknown')" if "scope_level" in obs_cols else "'unknown'"
        fact_type_expr = "COALESCE(fact_type, 'unknown')" if "fact_type" in obs_cols else "'unknown'"
        scope_rows = conn.execute(
            f"""
            SELECT {scope_expr} AS key, COUNT(*) AS c
            FROM fact_observations
            WHERE document_id = ?
            GROUP BY {scope_expr}
            """,
            (document_id,),
        ).fetchall()
        scope_counts = {row["key"]: int(row["c"]) for row in scope_rows}

        type_rows = conn.execute(
            f"""
            SELECT {fact_type_expr} AS key, COUNT(*) AS c
            FROM fact_observations
            WHERE document_id = ?
            GROUP BY {fact_type_expr}
            """,
            (document_id,),
        ).fetchall()
        fact_type_counts = {row["key"]: int(row["c"]) for row in type_rows}

        fact_type_guidance_clause = (
            "OR COALESCE(fact_type, '') = 'guidance'"
            if "fact_type" in obs_cols
            else ""
        )
        guidance_rows = conn.execute(
            f"""
            SELECT COUNT(*) AS c
            FROM fact_observations
            WHERE document_id = ?
              AND (
                fact_code IN ('revenue_growth_guidance', 'margin_guidance', 'management_outlook', 'segment_outlook')
                {fact_type_guidance_clause}
              )
            """,
            (document_id,),
        ).fetchone()
        guidance_count = int(guidance_rows["c"] if guidance_rows else 0)

        conf_row = conn.execute(
            """
            SELECT AVG(confidence) AS avg_confidence
            FROM fact_observations
            WHERE document_id = ? AND confidence IS NOT NULL
            """,
            (document_id,),
        ).fetchone()
        average_confidence = conf_row["avg_confidence"] if conf_row else None

    return {
        "segments": segments,
        "scope_counts": scope_counts,
        "fact_type_counts": fact_type_counts,
        "guidance_count": guidance_count,
        "average_confidence": average_confidence,
    }


def _prior_year_end(period_end: str | None) -> str | None:
    """Given an ISO quarter-end date, return the same quarter one year prior."""
    if not period_end or len(period_end) < 4:
        return None
    try:
        year = int(period_end[:4])
    except ValueError:
        return None
    return f"{year - 1}{period_end[4:]}"


def _prior_quarter_end(period_end: str | None) -> str | None:
    """Given an ISO quarter-end date, return the immediately preceding quarter-end."""
    if not period_end or len(period_end) < 10:
        return None
    try:
        year = int(period_end[:4])
    except ValueError:
        return None
    md = period_end[5:]
    if md == "03-31":
        return f"{year - 1}-12-31"
    if md == "06-30":
        return f"{year}-03-31"
    if md == "09-30":
        return f"{year}-06-30"
    if md == "12-31":
        return f"{year}-09-30"
    return None


def _event_period_end(conn: sqlite3.Connection, event_id: str) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(period_end) AS period_end FROM extracted_values
        WHERE event_id = ? AND period_end IS NOT NULL
        """,
        (event_id,),
    ).fetchone()
    if row and row["period_end"]:
        return row["period_end"]
    if uses_eight_step_metrics(conn):
        return None
    if not has_table(conn, "metric_values"):
        return None
    row = conn.execute(
        """
        SELECT period_end FROM metric_values
        WHERE event_id = ? AND period_end IS NOT NULL
        LIMIT 1
        """,
        (event_id,),
    ).fetchone()
    return row["period_end"] if row else None


def _load_fact_for_scope(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
    fact_key: str,
    scope: str,
    period_end: str | None,
) -> dict[str, Any] | None:
    scope = (scope or "CURRENT").upper()
    scalar_filter = _scalar_fact_filter(conn, "extracted_values", "ev")
    if scope == "CURRENT":
        row = conn.execute(
            f"""
            SELECT ev.*, e.document_id AS document_id
            FROM extracted_values ev
            LEFT JOIN events e ON e.id = ev.event_id
            WHERE ev.event_id = ? AND ev.value_code = ?
            {scalar_filter}
            ORDER BY CASE ev.basis WHEN 'consolidated' THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (event_id, fact_key),
        ).fetchone()
    else:
        target_end = None
        if scope == "PY":
            target_end = _prior_year_end(period_end)
        elif scope == "PQ":
            target_end = _prior_quarter_end(period_end)
        if not target_end:
            return None
        row = conn.execute(
            f"""
            SELECT ev.*, e.document_id AS document_id
            FROM extracted_values ev
            LEFT JOIN events e ON e.id = ev.event_id
            WHERE ev.company_id = ? AND ev.period_end = ? AND ev.value_code = ?
            {scalar_filter}
            ORDER BY CASE ev.basis WHEN 'consolidated' THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (company_id, target_end, fact_key),
        ).fetchone()

    if not row or row["value_numeric"] is None:
        return None

    fact = extracted_value_dict(row)
    fact["scope"] = scope
    fact["fact_key"] = fact_key
    fact["document_id"] = row["document_id"]
    return fact


_SCOPE_ORDER = {"CURRENT": 0, "PY": 1, "PQ": 2}


def signal_input_facts(
    conn: sqlite3.Connection,
    *,
    company_id: str,
    event_id: str,
    metric_keys: list[str],
) -> list[dict[str, Any]]:
    """Resolve catalog metric inputs to extracted facts with source provenance."""
    if not metric_keys:
        return []

    seen: set[tuple[str, str]] = set()
    ordered_keys: list[tuple[str, str]] = []
    for metric_key in metric_keys:
        for inp in metric_meta(metric_key).get("inputs") or []:
            fact_key = inp.get("fact_key")
            scope = (inp.get("scope") or "CURRENT").upper()
            if not fact_key:
                continue
            pair = (fact_key, scope)
            if pair in seen:
                continue
            seen.add(pair)
            ordered_keys.append(pair)

    if not ordered_keys:
        return []

    period_end = _event_period_end(conn, event_id)
    facts: list[dict[str, Any]] = []
    for fact_key, scope in sorted(
        ordered_keys, key=lambda p: (_SCOPE_ORDER.get(p[1], 9), p[0])
    ):
        fact = _load_fact_for_scope(
            conn,
            company_id=company_id,
            event_id=event_id,
            fact_key=fact_key,
            scope=scope,
            period_end=period_end,
        )
        if fact:
            facts.append(fact)
    return facts


def build_snapshot(
    conn: sqlite3.Connection,
    company_id: str,
    period_end: str | None,
) -> list[dict[str, Any]]:
    """Current vs prior-year headline facts (crore amounts / EPS)."""
    if not period_end:
        return []
    scalar_filter = _scalar_fact_filter(conn, "extracted_values")

    def load(pe: str) -> dict[str, dict[str, Any]]:
        rows = conn.execute(
            f"""
            SELECT value_code, value_numeric, unit FROM extracted_values
            WHERE company_id = ? AND period_end = ?
            {scalar_filter}
            ORDER BY CASE basis WHEN 'consolidated' THEN 0 ELSE 1 END
            """,
            (company_id, pe),
        ).fetchall()
        pool: dict[str, dict[str, Any]] = {}
        for r in rows:
            if r["value_numeric"] is None:
                continue
            pool.setdefault(
                r["value_code"],
                {"value": float(r["value_numeric"]), "unit": r["unit"]},
            )
        return pool

    current = load(period_end)
    py_end = _prior_year_end(period_end)
    prior = load(py_end) if py_end else {}

    snapshot: list[dict[str, Any]] = []
    for code, label in SNAPSHOT_FACTS:
        cur = current.get(code)
        if cur is None:
            continue
        prev = prior.get(code)
        cur_v = cur["value"]
        prev_v = prev["value"] if prev else None
        yoy = None
        if prev_v not in (None, 0):
            yoy = (cur_v - prev_v) / abs(prev_v) * 100
        snapshot.append(
            {
                "code": code,
                "metric": label,
                "current_value": cur_v,
                "previous_value": prev_v,
                "yoy_change_pct": yoy,
                "unit": cur["unit"],
            }
        )
    return snapshot
