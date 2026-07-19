"""Pure SQLite operations for the administrator fact-review queue.

Analytics remains read-only. Review decisions are stored in the writable app
database as an auditable overlay and never publish a fact by themselves.
"""

from __future__ import annotations

import sqlite3
from typing import Any


class ReviewNotFoundError(LookupError):
    pass


class InvalidReviewDecisionError(ValueError):
    pass


class AppliedReviewDecisionError(RuntimeError):
    pass


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _optional(alias: str, columns: set[str], name: str, fallback: str = "NULL") -> str:
    return f"{alias}.{name} AS {name}" if name in columns else f"{fallback} AS {name}"


def _decision_rows(app_conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    if not _table_exists(app_conn, "fact_review_decisions"):
        return {}
    rows = app_conn.execute(
        """
        SELECT d.*, u.email AS reviewer_email, u.full_name AS reviewer_name
        FROM fact_review_decisions d
        LEFT JOIN users u ON u.id = d.reviewed_by
        """
    ).fetchall()
    return {row["resolved_fact_id"]: dict(row) for row in rows}


def _review_rows(analytics_conn: sqlite3.Connection) -> list[sqlite3.Row]:
    if not _table_exists(analytics_conn, "resolved_facts") or not _table_exists(
        analytics_conn, "fact_observations"
    ):
        return []
    resolved_cols = _columns(analytics_conn, "resolved_facts")
    observation_cols = _columns(analytics_conn, "fact_observations")
    fact_name = (
        "fd.fact_name AS fact_name"
        if _table_exists(analytics_conn, "fact_definitions")
        else "rf.fact_code AS fact_name"
    )
    fact_join = (
        "LEFT JOIN fact_definitions fd ON fd.fact_code = rf.fact_code"
        if _table_exists(analytics_conn, "fact_definitions")
        else ""
    )
    document_title = (
        "d.title AS document_title"
        if _table_exists(analytics_conn, "documents")
        else "NULL AS document_title"
    )
    document_join = (
        "LEFT JOIN documents d ON d.id = fo.document_id"
        if _table_exists(analytics_conn, "documents")
        else ""
    )
    sql = f"""
        SELECT rf.resolved_fact_id, rf.company_id, rf.event_id, rf.fact_code,
               rf.resolved_value, {_optional('rf', resolved_cols, 'resolved_value_text')},
               rf.unit, rf.selected_observation_id, rf.resolution_status,
               rf.confidence, {_optional('rf', resolved_cols, 'basis')},
               {_optional('rf', resolved_cols, 'period')},
               {_optional('rf', resolved_cols, 'period_type')},
               c.name AS company_name, c.ticker AS company_symbol,
               e.event_date, e.title AS event_title,
               fo.document_id, fo.value AS observation_value,
               {_optional('fo', observation_cols, 'value_text', "NULL")},
               fo.source_page, fo.source_text, fo.confidence AS observation_confidence,
               {_optional('fo', observation_cols, 'extraction_method')},
               {fact_name}, {document_title}
        FROM resolved_facts rf
        JOIN companies c ON c.id = rf.company_id
        JOIN events e ON e.id = rf.event_id
        LEFT JOIN fact_observations fo ON fo.observation_id = rf.selected_observation_id
        {fact_join}
        {document_join}
        WHERE rf.resolution_status = 'review_required'
        ORDER BY e.event_date DESC, c.ticker, rf.fact_code
    """
    return analytics_conn.execute(sql).fetchall()


def _same_optional_dimensions(item: dict[str, Any], candidate: sqlite3.Row) -> bool:
    for name in (
        "basis",
        "period",
        "period_type",
        "segment",
        "geography",
        "product",
        "channel",
        "project",
        "customer_type",
        "metric_context",
        "scope_level",
        "scope_name",
    ):
        if name not in candidate.keys():
            continue
        expected = item.get(name)
        actual = candidate[name]
        if expected is not None and actual is not None and expected != actual:
            return False
    return True


def _candidate_observations(
    analytics_conn: sqlite3.Connection, item: dict[str, Any]
) -> list[dict[str, Any]]:
    columns = _columns(analytics_conn, "fact_observations")
    optional = [
        _optional("fo", columns, name)
        for name in (
            "value_text",
            "basis",
            "period_type",
            "extraction_method",
            "segment",
            "geography",
            "product",
            "channel",
            "project",
            "customer_type",
            "metric_context",
            "scope_level",
            "scope_name",
        )
    ]
    rows = analytics_conn.execute(
        f"""
        SELECT fo.observation_id, fo.document_id, fo.fact_code, fo.value,
               fo.unit, fo.period, fo.source_page, fo.source_text, fo.confidence,
               {', '.join(optional)}
        FROM fact_observations fo
        WHERE fo.event_id = ? AND fo.fact_code = ?
        ORDER BY CASE WHEN fo.observation_id = ? THEN 0 ELSE 1 END,
                 fo.confidence DESC, fo.source_page
        """,
        (item["event_id"], item["fact_code"], item.get("selected_observation_id")),
    ).fetchall()
    return [dict(row) for row in rows if _same_optional_dimensions(item, row)]


def list_review_items(
    analytics_conn: sqlite3.Connection,
    app_conn: sqlite3.Connection,
    *,
    status: str = "open",
    search: str = "",
    limit: int = 200,
) -> list[dict[str, Any]]:
    if status not in {"open", "approved", "rejected", "all"}:
        raise InvalidReviewDecisionError("Invalid review status filter.")
    decisions = _decision_rows(app_conn)
    needle = search.strip().lower()
    items: list[dict[str, Any]] = []
    for row in _review_rows(analytics_conn):
        item = dict(row)
        decision = decisions.get(item["resolved_fact_id"])
        queue_status = decision["decision"] if decision else "open"
        if status != "all" and queue_status != status:
            continue
        haystack = " ".join(
            str(item.get(name) or "")
            for name in (
                "company_name",
                "company_symbol",
                "fact_code",
                "fact_name",
                "event_title",
                "source_text",
            )
        ).lower()
        if needle and needle not in haystack:
            continue
        item["queue_status"] = queue_status
        item["decision"] = decision
        item["candidates"] = _candidate_observations(analytics_conn, item)
        items.append(item)
        if len(items) >= limit:
            break
    return items


def review_summary(
    analytics_conn: sqlite3.Connection, app_conn: sqlite3.Connection
) -> dict[str, int]:
    items = list_review_items(
        analytics_conn, app_conn, status="all", limit=100_000
    )
    counts = {"open": 0, "approved": 0, "rejected": 0, "total": len(items)}
    for item in items:
        counts[item["queue_status"]] += 1
    return counts


def record_review_decision(
    analytics_conn: sqlite3.Connection,
    app_conn: sqlite3.Connection,
    *,
    resolved_fact_id: str,
    decision: str,
    selected_observation_id: str | None,
    reviewer_note: str | None,
    reviewed_by: str,
    timestamp: str,
) -> dict[str, Any]:
    if decision not in {"approved", "rejected"}:
        raise InvalidReviewDecisionError("Decision must be approved or rejected.")
    matches = [
        item
        for item in list_review_items(
            analytics_conn, app_conn, status="all", limit=100_000
        )
        if item["resolved_fact_id"] == resolved_fact_id
    ]
    if not matches:
        raise ReviewNotFoundError("Review item not found.")
    item = matches[0]
    candidate_ids = {candidate["observation_id"] for candidate in item["candidates"]}
    if decision == "approved":
        if not selected_observation_id:
            raise InvalidReviewDecisionError(
                "An observation must be selected before approval."
            )
        if selected_observation_id not in candidate_ids:
            raise InvalidReviewDecisionError(
                "The selected observation does not belong to this review item."
            )
    elif not (reviewer_note or "").strip():
        raise InvalidReviewDecisionError("A rejection note is required.")

    app_conn.execute(
        """
        INSERT INTO fact_review_decisions (
            resolved_fact_id, company_id, event_id, fact_code, decision,
            selected_observation_id, reviewer_note, reviewed_by,
            reviewed_at, updated_at, application_status, applied_at,
            applied_by, application_error, recompute_status, recomputed_at,
            recompute_error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL,
                  'not_applicable', NULL, NULL)
        ON CONFLICT(resolved_fact_id) DO UPDATE SET
            decision = excluded.decision,
            selected_observation_id = excluded.selected_observation_id,
            reviewer_note = excluded.reviewer_note,
            reviewed_by = excluded.reviewed_by,
            reviewed_at = excluded.reviewed_at,
            updated_at = excluded.updated_at,
            application_status = excluded.application_status,
            applied_at = NULL,
            applied_by = NULL,
            application_error = NULL,
            recompute_status = 'not_applicable',
            recomputed_at = NULL,
            recompute_error = NULL
        """,
        (
            resolved_fact_id,
            item["company_id"],
            item["event_id"],
            item["fact_code"],
            decision,
            selected_observation_id if decision == "approved" else None,
            (reviewer_note or "").strip() or None,
            reviewed_by,
            timestamp,
            timestamp,
            "pending" if decision == "approved" else "not_applicable",
        ),
    )
    app_conn.commit()
    return next(
        row
        for row in list_review_items(
            analytics_conn, app_conn, status="all", limit=100_000
        )
        if row["resolved_fact_id"] == resolved_fact_id
    )


def reopen_review(app_conn: sqlite3.Connection, resolved_fact_id: str) -> bool:
    row = app_conn.execute(
        "SELECT application_status FROM fact_review_decisions WHERE resolved_fact_id = ?",
        (resolved_fact_id,),
    ).fetchone()
    if row is not None and row["application_status"] == "applied":
        raise AppliedReviewDecisionError(
            "An applied decision cannot be reopened; create a corrective review instead."
        )
    cursor = app_conn.execute(
        "DELETE FROM fact_review_decisions WHERE resolved_fact_id = ?",
        (resolved_fact_id,),
    )
    app_conn.commit()
    return cursor.rowcount > 0
