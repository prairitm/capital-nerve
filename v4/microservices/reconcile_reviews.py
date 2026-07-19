"""Apply approved fact reviews through a controlled, resumable workflow.

The administrator API only records decisions in the application database. This
maintenance command is the sole writer that promotes an approved observation
into analytics. Preview is the default; ``--apply`` is required to mutate data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


DIMENSIONS = (
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
OBSERVATION_FIELDS = (
    "value",
    "value_text",
    "unit",
    "period",
    "period_type",
    "basis",
    *DIMENSIONS,
    "fact_type",
    "value_lower",
    "value_upper",
    "sentiment",
    "is_explicit_guidance",
    "source_page",
    "source_text",
    "confidence",
)


class ReconciliationError(RuntimeError):
    pass


@dataclass
class ReconciliationResult:
    resolved_fact_id: str
    status: str
    event_id: str | None = None
    selected_observation_id: str | None = None
    message: str | None = None
    recompute_status: str | None = None


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(path: Path, *, writable: bool) -> sqlite3.Connection:
    if writable:
        conn = sqlite3.connect(str(path), timeout=10)
    else:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _require_schema(analytics: sqlite3.Connection, app: sqlite3.Connection) -> None:
    for table in ("resolved_facts", "fact_observations", "extracted_values", "events", "companies"):
        if not _table_exists(analytics, table):
            raise ReconciliationError(f"Analytics table {table!r} is missing.")
    decision_columns = _columns(app, "fact_review_decisions")
    required_decision_columns = {
        "resolved_fact_id",
        "decision",
        "selected_observation_id",
        "updated_at",
        "application_status",
        "recompute_status",
    }
    missing = required_decision_columns - decision_columns
    if missing:
        raise ReconciliationError(
            "Run backend application migrations before reconciliation; missing: "
            + ", ".join(sorted(missing))
        )


def bootstrap_reconciliation_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS fact_review_reconciliations (
            resolved_fact_id TEXT PRIMARY KEY,
            decision_updated_at TEXT NOT NULL,
            selected_observation_id TEXT NOT NULL,
            company_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            fact_code TEXT NOT NULL,
            previous_fact_json TEXT NOT NULL,
            applied_fact_json TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            applied_by TEXT NOT NULL,
            recompute_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (recompute_status IN ('pending', 'succeeded', 'failed')),
            recomputed_at TEXT,
            recompute_error TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_fact_review_reconciliations_event
            ON fact_review_reconciliations(event_id, applied_at);
        """
    )
    conn.commit()


def _approved_decisions(
    app: sqlite3.Connection, resolved_fact_ids: Iterable[str] | None
) -> list[sqlite3.Row]:
    params: list[Any] = []
    ids = list(dict.fromkeys(resolved_fact_ids or []))
    application_filter = (
        "application_status IN ('pending', 'failed', 'applied')"
        if ids
        else "(application_status IN ('pending', 'failed') OR "
        "(application_status = 'applied' AND recompute_status IN ('pending', 'failed')))"
    )
    where = f"decision = 'approved' AND {application_filter}"
    if ids:
        where += f" AND resolved_fact_id IN ({','.join('?' for _ in ids)})"
        params.extend(ids)
    rows = app.execute(
        f"SELECT * FROM fact_review_decisions WHERE {where} ORDER BY updated_at, resolved_fact_id",
        params,
    ).fetchall()
    if ids:
        found = {row["resolved_fact_id"] for row in rows}
        missing = [item for item in ids if item not in found]
        if missing:
            raise ReconciliationError(
                "No approved review decision found for: " + ", ".join(missing)
            )
    return rows


def _ledger_row(analytics: sqlite3.Connection, resolved_fact_id: str) -> sqlite3.Row | None:
    if not _table_exists(analytics, "fact_review_reconciliations"):
        return None
    return analytics.execute(
        "SELECT * FROM fact_review_reconciliations WHERE resolved_fact_id = ?",
        (resolved_fact_id,),
    ).fetchone()


def _same_identity(fact: sqlite3.Row, observation: sqlite3.Row) -> bool:
    for field in ("company_id", "event_id", "fact_code", "period", "period_type", "basis", *DIMENSIONS):
        if field not in fact.keys() or field not in observation.keys():
            continue
        if fact[field] != observation[field]:
            return False
    return True


def _load_and_validate(
    analytics: sqlite3.Connection, decision: sqlite3.Row
) -> tuple[sqlite3.Row, sqlite3.Row, dict[str, Any]]:
    fact = analytics.execute(
        "SELECT * FROM resolved_facts WHERE resolved_fact_id = ?",
        (decision["resolved_fact_id"],),
    ).fetchone()
    if fact is None:
        raise ReconciliationError("The resolved fact no longer exists.")
    if fact["resolution_status"] != "review_required":
        raise ReconciliationError(
            f"The fact is no longer review_required (current status: {fact['resolution_status']!r})."
        )
    for field in ("company_id", "event_id", "fact_code"):
        if fact[field] != decision[field]:
            raise ReconciliationError(f"The approved decision has a stale {field}.")

    observation = analytics.execute(
        "SELECT * FROM fact_observations WHERE observation_id = ?",
        (decision["selected_observation_id"],),
    ).fetchone()
    if observation is None:
        raise ReconciliationError("The approved observation no longer exists.")
    if not _same_identity(fact, observation):
        raise ReconciliationError(
            "The approved observation no longer matches the fact's period, basis, or dimensions."
        )
    if observation["value"] is None and observation["value_text"] is None:
        raise ReconciliationError("The approved observation has no value.")
    if observation["source_page"] is None or not str(observation["source_text"] or "").strip():
        raise ReconciliationError(
            "The approved observation lacks page-level evidence and cannot be published."
        )

    event = analytics.execute(
        """
        SELECT e.*, c.ticker AS company_symbol
        FROM events e JOIN companies c ON c.id = e.company_id
        WHERE e.id = ?
        """,
        (fact["event_id"],),
    ).fetchone()
    if event is None or not str(event["company_symbol"] or "").strip():
        raise ReconciliationError("The event or company ticker required for recomputation is missing.")
    context = dict(event)
    context["period_end"] = observation["period"]
    return fact, observation, context


def preview_approved_reviews(
    analytics: sqlite3.Connection,
    app: sqlite3.Connection,
    *,
    resolved_fact_ids: Iterable[str] | None = None,
) -> list[ReconciliationResult]:
    _require_schema(analytics, app)
    results: list[ReconciliationResult] = []
    for decision in _approved_decisions(app, resolved_fact_ids):
        ledger = _ledger_row(analytics, decision["resolved_fact_id"])
        if ledger is not None:
            matching = (
                ledger["decision_updated_at"] == decision["updated_at"]
                and ledger["selected_observation_id"] == decision["selected_observation_id"]
            )
            results.append(
                ReconciliationResult(
                    decision["resolved_fact_id"],
                    "already_applied" if matching else "invalid",
                    event_id=ledger["event_id"],
                    selected_observation_id=decision["selected_observation_id"],
                    message=None if matching else "A different decision version was already applied.",
                    recompute_status=ledger["recompute_status"],
                )
            )
            continue
        try:
            _, _, event = _load_and_validate(analytics, decision)
            results.append(
                ReconciliationResult(
                    decision["resolved_fact_id"],
                    "ready",
                    event_id=event["id"],
                    selected_observation_id=decision["selected_observation_id"],
                )
            )
        except ReconciliationError as exc:
            results.append(
                ReconciliationResult(
                    decision["resolved_fact_id"],
                    "invalid",
                    event_id=decision["event_id"],
                    selected_observation_id=decision["selected_observation_id"],
                    message=str(exc),
                )
            )
    return results


def _review_value_id(resolved_fact_id: str) -> str:
    return hashlib.sha256(f"review:{resolved_fact_id}".encode()).hexdigest()


def _upsert_extracted_value(
    analytics: sqlite3.Connection,
    fact: sqlite3.Row,
    observation: sqlite3.Row,
) -> None:
    available = _columns(analytics, "extracted_values")
    payload: dict[str, Any] = {
        "id": _review_value_id(fact["resolved_fact_id"]),
        "company_id": fact["company_id"],
        "event_id": fact["event_id"],
        "value_code": fact["fact_code"],
        "value_numeric": observation["value"],
        "value_text": observation["value_text"],
        "unit": observation["unit"],
        "period_type": observation["period_type"],
        "period_start": None,
        "period_end": observation["period"],
        "basis": observation["basis"],
        **{field: observation[field] for field in DIMENSIONS},
        "fact_type": observation["fact_type"],
        "value_lower": observation["value_lower"],
        "value_upper": observation["value_upper"],
        "sentiment": observation["sentiment"],
        "is_explicit_guidance": observation["is_explicit_guidance"],
        "source_text": observation["source_text"],
        "source_page": observation["source_page"],
        "confidence": observation["confidence"],
    }
    payload = {key: value for key, value in payload.items() if key in available}
    required = {"id", "company_id", "event_id", "value_code"}
    if not required.issubset(payload):
        raise ReconciliationError("The extracted_values schema is incompatible.")
    columns = list(payload)
    updates = [column for column in columns if column != "id"]
    analytics.execute(
        f"""
        INSERT INTO extracted_values ({', '.join(columns)})
        VALUES ({', '.join('?' for _ in columns)})
        ON CONFLICT(id) DO UPDATE SET
            {', '.join(f'{column} = excluded.{column}' for column in updates)}
        """,
        [payload[column] for column in columns],
    )


def _apply_one(
    analytics: sqlite3.Connection,
    decision: sqlite3.Row,
    *,
    applied_by: str,
    timestamp: str,
) -> tuple[ReconciliationResult, dict[str, Any]]:
    ledger = _ledger_row(analytics, decision["resolved_fact_id"])
    if ledger is not None:
        if (
            ledger["decision_updated_at"] != decision["updated_at"]
            or ledger["selected_observation_id"] != decision["selected_observation_id"]
        ):
            raise ReconciliationError("A different decision version was already applied.")
        event = analytics.execute(
            "SELECT e.*, c.ticker AS company_symbol FROM events e JOIN companies c ON c.id = e.company_id WHERE e.id = ?",
            (ledger["event_id"],),
        ).fetchone()
        context = dict(event) if event is not None else {"id": ledger["event_id"]}
        context["period_end"] = json.loads(ledger["applied_fact_json"]).get("period")
        return (
            ReconciliationResult(
                decision["resolved_fact_id"],
                "already_applied",
                event_id=ledger["event_id"],
                selected_observation_id=decision["selected_observation_id"],
                recompute_status=ledger["recompute_status"],
            ),
            context,
        )

    fact, observation, context = _load_and_validate(analytics, decision)
    previous = dict(fact)
    assignments = {
        "resolved_value": observation["value"],
        "resolved_value_text": observation["value_text"],
        "unit": observation["unit"],
        "period": observation["period"],
        "period_type": observation["period_type"],
        "basis": observation["basis"],
        **{field: observation[field] for field in DIMENSIONS},
        "fact_type": observation["fact_type"],
        "value_lower": observation["value_lower"],
        "value_upper": observation["value_upper"],
        "sentiment": observation["sentiment"],
        "is_explicit_guidance": observation["is_explicit_guidance"],
        "selected_observation_id": observation["observation_id"],
        "resolution_status": "resolved",
        "confidence": observation["confidence"],
    }
    available = _columns(analytics, "resolved_facts")
    assignments = {key: value for key, value in assignments.items() if key in available}
    analytics.execute(
        f"UPDATE resolved_facts SET {', '.join(f'{key} = ?' for key in assignments)} WHERE resolved_fact_id = ?",
        [*assignments.values(), fact["resolved_fact_id"]],
    )
    _upsert_extracted_value(analytics, fact, observation)
    applied = {field: observation[field] for field in OBSERVATION_FIELDS}
    analytics.execute(
        """
        INSERT INTO fact_review_reconciliations (
            resolved_fact_id, decision_updated_at, selected_observation_id,
            company_id, event_id, fact_code, previous_fact_json,
            applied_fact_json, applied_at, applied_by, recompute_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """,
        (
            fact["resolved_fact_id"],
            decision["updated_at"],
            observation["observation_id"],
            fact["company_id"],
            fact["event_id"],
            fact["fact_code"],
            json.dumps(previous, sort_keys=True),
            json.dumps(applied, sort_keys=True),
            timestamp,
            applied_by,
        ),
    )
    return (
        ReconciliationResult(
            fact["resolved_fact_id"],
            "applied",
            event_id=fact["event_id"],
            selected_observation_id=observation["observation_id"],
            recompute_status="pending",
        ),
        context,
    )


def _mark_application(
    app: sqlite3.Connection,
    resolved_fact_id: str,
    *,
    status: str,
    timestamp: str,
    applied_by: str,
    error: str | None = None,
    recompute_status: str = "not_applicable",
) -> None:
    app.execute(
        """
        UPDATE fact_review_decisions
        SET application_status = ?, applied_at = ?, applied_by = ?,
            application_error = ?, recompute_status = ?,
            recomputed_at = CASE WHEN ? = 'succeeded' THEN ? ELSE NULL END,
            recompute_error = NULL
        WHERE resolved_fact_id = ?
        """,
        (
            status,
            timestamp if status == "applied" else None,
            applied_by,
            error,
            recompute_status,
            recompute_status,
            timestamp,
            resolved_fact_id,
        ),
    )
    app.commit()


def _mark_recompute(
    analytics: sqlite3.Connection,
    app: sqlite3.Connection,
    resolved_fact_ids: list[str],
    *,
    status: str,
    timestamp: str,
    error: str | None,
) -> None:
    placeholders = ",".join("?" for _ in resolved_fact_ids)
    analytics.execute(
        f"UPDATE fact_review_reconciliations SET recompute_status = ?, recomputed_at = ?, recompute_error = ? WHERE resolved_fact_id IN ({placeholders})",
        (status, timestamp if status == "succeeded" else None, error, *resolved_fact_ids),
    )
    analytics.commit()
    app.execute(
        f"UPDATE fact_review_decisions SET recompute_status = ?, recomputed_at = ?, recompute_error = ? WHERE resolved_fact_id IN ({placeholders})",
        (status, timestamp if status == "succeeded" else None, error, *resolved_fact_ids),
    )
    app.commit()


def apply_approved_reviews(
    analytics: sqlite3.Connection,
    app: sqlite3.Connection,
    *,
    resolved_fact_ids: Iterable[str] | None = None,
    applied_by: str,
    timestamp: str | None = None,
    recompute: Callable[[sqlite3.Connection, dict[str, Any]], Any] | None = None,
) -> list[ReconciliationResult]:
    _require_schema(analytics, app)
    bootstrap_reconciliation_schema(analytics)
    now = timestamp or utc_iso()
    results: list[ReconciliationResult] = []
    event_contexts: dict[str, dict[str, Any]] = {}
    event_result_ids: dict[str, list[str]] = {}

    for decision in _approved_decisions(app, resolved_fact_ids):
        try:
            analytics.execute("BEGIN IMMEDIATE")
            result, context = _apply_one(
                analytics, decision, applied_by=applied_by, timestamp=now
            )
            analytics.commit()
            _mark_application(
                app,
                decision["resolved_fact_id"],
                status="applied",
                timestamp=now,
                applied_by=applied_by,
                recompute_status=result.recompute_status or "pending",
            )
            results.append(result)
            if result.recompute_status != "succeeded" and result.event_id:
                event_contexts[result.event_id] = context
                event_result_ids.setdefault(result.event_id, []).append(result.resolved_fact_id)
        except Exception as exc:
            analytics.rollback()
            message = str(exc)
            _mark_application(
                app,
                decision["resolved_fact_id"],
                status="failed",
                timestamp=now,
                applied_by=applied_by,
                error=message,
                recompute_status="not_applicable",
            )
            results.append(
                ReconciliationResult(
                    decision["resolved_fact_id"],
                    "invalid",
                    event_id=decision["event_id"],
                    selected_observation_id=decision["selected_observation_id"],
                    message=message,
                )
            )

    if recompute is None:
        return results

    for event_id, context in event_contexts.items():
        ids = event_result_ids[event_id]
        try:
            recompute(analytics, context)
            completed_at = utc_iso()
            _mark_recompute(
                analytics, app, ids, status="succeeded", timestamp=completed_at, error=None
            )
            for result in results:
                if result.resolved_fact_id in ids:
                    result.recompute_status = "succeeded"
        except Exception as exc:
            error = str(exc)
            _mark_recompute(
                analytics, app, ids, status="failed", timestamp=utc_iso(), error=error
            )
            for result in results:
                if result.resolved_fact_id in ids:
                    result.recompute_status = "failed"
                    result.message = f"Fact applied, but recomputation failed: {error}"
    return results


def _canonical_event_type(raw: Any) -> str:
    value = str(raw or "").strip().upper().replace("-", "_").replace(" ", "_")
    if value in {"INVESTOR_PRESENTATION"}:
        return "Investor Presentation"
    if value in {"EARNINGS_CALL_TRANSCRIPT", "CONCALL_TRANSCRIPT"}:
        return "Earnings Call Transcript"
    return "Financial Results"


def _quarter_context(context: dict[str, Any]) -> tuple[int, int]:
    period_end = str(context.get("period_end") or "")
    try:
        end = datetime.fromisoformat(period_end[:10])
    except ValueError as exc:
        raise ReconciliationError("A valid fact period is required for recomputation.") from exc
    quarter = context.get("fiscal_quarter")
    if quarter is None:
        quarter = {3: 4, 6: 1, 9: 2, 12: 3}.get(end.month)
    if quarter not in {1, 2, 3, 4}:
        raise ReconciliationError("The event fiscal quarter is invalid.")
    fy_start = context.get("fiscal_year")
    if fy_start is None:
        fy_start = end.year - 1 if end.month <= 3 else end.year
    return int(quarter), int(fy_start)


def recompute_event(analytics: sqlite3.Connection, context: dict[str, Any]) -> None:
    base = Path(__file__).resolve().parent
    for directory in (base / "values", base / "metrics", base / "signals"):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    from metrics_service import compute_and_persist_metrics
    from signals_service import evaluate_and_persist_signals

    quarter, fy_start = _quarter_context(context)
    event_type = _canonical_event_type(context.get("event_type"))
    kwargs = {
        "symbol": str(context["company_symbol"]),
        "company_id": str(context["company_id"]),
        "event_id": str(context["id"]),
        "period_end": str(context["period_end"]),
        "event_type": event_type,
    }
    compute_and_persist_metrics(
        analytics,
        **kwargs,
        period_quarter=quarter,
        period_fy_start=fy_start,
    )
    evaluate_and_persist_signals(analytics, **kwargs)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--analytics-db", type=Path, default=root / "data" / "capital_nerve.db")
    parser.add_argument("--app-db", type=Path, default=root / "data" / "capital_nerve_app.db")
    parser.add_argument("--resolved-fact-id", action="append", dest="resolved_fact_ids")
    parser.add_argument("--apply", action="store_true", help="Apply validated approvals; otherwise preview only.")
    parser.add_argument("--no-recompute", action="store_true", help="Apply facts but leave dependent metrics/signals pending.")
    parser.add_argument("--applied-by", default="review-reconciler", help="Operator identity recorded in the audit ledger.")
    return parser


def main() -> int:
    args = _parser().parse_args()
    for path in (args.analytics_db, args.app_db):
        if not path.is_file():
            raise SystemExit(f"Database not found: {path}")
    analytics = connect(args.analytics_db.resolve(), writable=args.apply)
    app = connect(args.app_db.resolve(), writable=args.apply)
    try:
        if args.apply:
            results = apply_approved_reviews(
                analytics,
                app,
                resolved_fact_ids=args.resolved_fact_ids,
                applied_by=args.applied_by,
                recompute=None if args.no_recompute else recompute_event,
            )
        else:
            results = preview_approved_reviews(
                analytics, app, resolved_fact_ids=args.resolved_fact_ids
            )
        payload = {
            "mode": "apply" if args.apply else "preview",
            "results": [asdict(result) for result in results],
            "counts": {
                status: sum(result.status == status for result in results)
                for status in ("ready", "applied", "already_applied", "invalid")
            },
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1 if any(result.status == "invalid" or result.recompute_status == "failed" for result in results) else 0
    finally:
        analytics.close()
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
