#!/usr/bin/env python3
"""Reprocess financial-result documents whose selected facts lack source pages.

The default mode is read-only and prints the affected documents. Pass --apply
to call the running values service and then recompute metrics, signals, and
alerts for each successfully reprocessed event.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Sequence


V4_DIR = Path(__file__).resolve().parent
DEFAULT_DB = V4_DIR / "data" / "capital_nerve.db"


class ReprocessError(RuntimeError):
    pass


@dataclass(frozen=True)
class AffectedDocument:
    document_id: str
    company_id: str
    symbol: str
    event_id: str
    event_type: str
    event_date: str
    source_url: str | None
    storage_path: str | None
    missing_facts: int
    fact_codes: str

    @property
    def request_dates(self) -> tuple[str, str]:
        parsed = date.fromisoformat(self.event_date)
        formatted = parsed.strftime("%d-%m-%Y")
        return formatted, formatted


def connect_read_only(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise ReprocessError(f"Analytics database does not exist: {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def find_affected_documents(
    conn: sqlite3.Connection,
    *,
    document_ids: Sequence[str] = (),
    limit: int | None = None,
) -> list[AffectedDocument]:
    filters = [
        "rf.resolution_status = 'review_required'",
        "fo.source_page IS NULL",
        "UPPER(REPLACE(COALESCE(d.document_kind, e.event_type, ''), ' ', '_')) "
        "IN ('FINANCIAL_RESULT', 'FINANCIAL_RESULTS', 'QUARTERLY_RESULT')",
    ]
    params: list[Any] = []
    if document_ids:
        placeholders = ",".join("?" for _ in document_ids)
        filters.append(f"d.id IN ({placeholders})")
        params.extend(document_ids)

    limit_sql = ""
    if limit is not None:
        limit_sql = "LIMIT ?"
        params.append(limit)

    rows = conn.execute(
        f"""
        SELECT d.id AS document_id,
               e.company_id,
               c.ticker AS symbol,
               e.id AS event_id,
               e.event_type,
               e.event_date,
               COALESCE(d.source_url, e.source_url) AS source_url,
               d.storage_path,
               COUNT(DISTINCT rf.resolved_fact_id) AS missing_facts,
               GROUP_CONCAT(DISTINCT rf.fact_code) AS fact_codes
        FROM resolved_facts rf
        JOIN fact_observations fo
          ON fo.observation_id = rf.selected_observation_id
        JOIN events e
          ON e.id = rf.event_id
        JOIN companies c
          ON c.id = e.company_id
        JOIN documents d
          ON d.id = COALESCE(fo.document_id, e.document_id)
        WHERE {' AND '.join(filters)}
        GROUP BY d.id, e.id
        ORDER BY e.event_date, c.ticker, d.id
        {limit_sql}
        """,
        tuple(params),
    ).fetchall()
    return [
        AffectedDocument(
            document_id=str(row["document_id"]),
            company_id=str(row["company_id"]),
            symbol=str(row["symbol"]),
            event_id=str(row["event_id"]),
            event_type=str(row["event_type"] or "Financial Results"),
            event_date=str(row["event_date"]),
            source_url=str(row["source_url"]) if row["source_url"] else None,
            storage_path=str(row["storage_path"]) if row["storage_path"] else None,
            missing_facts=int(row["missing_facts"]),
            fact_codes=str(row["fact_codes"] or ""),
        )
        for row in rows
    ]


def request_json(
    method: str,
    url: str,
    *,
    query: dict[str, Any] | None = None,
    timeout: float,
) -> dict[str, Any]:
    if query:
        clean = {
            key: str(value).lower() if isinstance(value, bool) else value
            for key, value in query.items()
            if value is not None and value != ""
        }
        url = f"{url}?{urllib.parse.urlencode(clean)}"
    request = urllib.request.Request(
        url,
        data=b"" if method == "POST" else None,
        headers={"Accept": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ReprocessError(f"{method} {url} failed with HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ReprocessError(f"{method} {url} failed: {exc}") from exc
    try:
        return json.loads(payload) if payload else {}
    except json.JSONDecodeError as exc:
        raise ReprocessError(f"{method} {url} returned invalid JSON") from exc


def local_document_path(document: AffectedDocument, db_path: Path) -> Path | None:
    if not document.storage_path:
        return None
    path = Path(document.storage_path).expanduser()
    candidates = [path] if path.is_absolute() else [db_path.parent / path, V4_DIR / path]
    return next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)


def reprocess_document(
    document: AffectedDocument,
    *,
    db_path: Path,
    values_url: str,
    metrics_url: str,
    signals_url: str,
    alerts_url: str,
    force_reparse: bool,
    recompute_downstream: bool,
    timeout: float,
) -> dict[str, Any]:
    source_path = local_document_path(document, db_path)
    if source_path is None and not document.source_url:
        raise ReprocessError(
            f"{document.document_id} has neither an accessible local file nor a source URL"
        )
    from_date, to_date = document.request_dates
    values_params: dict[str, Any] = {
        "symbol": document.symbol,
        "from_date": from_date,
        "to_date": to_date,
        "company_id": document.company_id,
        "event_id": document.event_id,
        "event_type": "Financial Results",
        "document_type": "financial_result",
        "local_path": str(source_path) if source_path else None,
        "pdf_url": None if source_path else document.source_url,
        "force_reparse": force_reparse,
    }
    values = request_json(
        "POST",
        f"{values_url.rstrip('/')}/values/extract",
        query=values_params,
        timeout=timeout,
    )
    result: dict[str, Any] = {"values": values.get("extracted_count", 0)}
    if not recompute_downstream:
        return result

    metrics = request_json(
        "POST",
        f"{metrics_url.rstrip('/')}/metrics/compute",
        query=values.get("next_service_params") or {},
        timeout=timeout,
    )
    signals = request_json(
        "POST",
        f"{signals_url.rstrip('/')}/signals/evaluate",
        query=metrics.get("next_service_params") or {},
        timeout=timeout,
    )
    alerts = request_json(
        "GET",
        f"{alerts_url.rstrip('/')}/alerts",
        query=signals.get("next_service_params") or {},
        timeout=timeout,
    )
    result.update(
        metrics=metrics.get("metrics_count", 0),
        signals=signals.get("fired_count", 0),
        alerts=alerts.get("alert_count", 0),
    )
    return result


def remaining_missing_facts(conn: sqlite3.Connection, document_id: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT rf.resolved_fact_id)
        FROM resolved_facts rf
        JOIN fact_observations fo
          ON fo.observation_id = rf.selected_observation_id
        JOIN events e ON e.id = rf.event_id
        WHERE rf.resolution_status = 'review_required'
          AND fo.source_page IS NULL
          AND COALESCE(fo.document_id, e.document_id) = ?
        """,
        (document_id,),
    ).fetchone()
    return int(row[0])


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.getenv("V4_DB_PATH", DEFAULT_DB)),
        help="analytics DB (default: V4_DB_PATH or v4/data/capital_nerve.db)",
    )
    parser.add_argument("--document-id", action="append", default=[], help="limit to a document; repeatable")
    parser.add_argument("--limit", type=int, help="maximum number of documents")
    parser.add_argument("--apply", action="store_true", help="perform reprocessing; otherwise preview only")
    parser.add_argument("--force-reparse", action="store_true", help="rerun PDF-to-Markdown parsing too")
    parser.add_argument("--skip-downstream", action="store_true", help="skip metrics, signals, and alerts recomputation")
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--timeout", type=float, default=3600, help="per-service request timeout in seconds")
    parser.add_argument("--values-url", default=os.getenv("REPROCESS_VALUES_URL", "http://127.0.0.1:8023"))
    parser.add_argument("--metrics-url", default=os.getenv("REPROCESS_METRICS_URL", "http://127.0.0.1:8024"))
    parser.add_argument("--signals-url", default=os.getenv("REPROCESS_SIGNALS_URL", "http://127.0.0.1:8025"))
    parser.add_argument("--alerts-url", default=os.getenv("REPROCESS_ALERTS_URL", "http://127.0.0.1:8026"))
    args = parser.parse_args(argv)
    args.db = args.db.expanduser().resolve()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        with closing(connect_read_only(args.db)) as conn:
            documents = find_affected_documents(
                conn,
                document_ids=args.document_id,
                limit=args.limit,
            )
    except (ReprocessError, sqlite3.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    total_facts = sum(document.missing_facts for document in documents)
    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"Mode: {mode}\nDocuments: {len(documents)}\nMissing-page facts: {total_facts}")
    for document in documents:
        source = local_document_path(document, args.db) or document.source_url or "unavailable"
        print(
            f"- {document.symbol} {document.event_date} "
            f"document={document.document_id} missing={document.missing_facts} "
            f"facts={document.fact_codes} source={source}"
        )
    if not args.apply or not documents:
        if not args.apply:
            print("\nNo changes made. Re-run with --apply after reviewing this list.")
        return 0

    failures = 0
    for index, document in enumerate(documents, start=1):
        print(f"\n[{index}/{len(documents)}] Reprocessing {document.symbol} {document.document_id}...", flush=True)
        try:
            result = reprocess_document(
                document,
                db_path=args.db,
                values_url=args.values_url,
                metrics_url=args.metrics_url,
                signals_url=args.signals_url,
                alerts_url=args.alerts_url,
                force_reparse=args.force_reparse,
                recompute_downstream=not args.skip_downstream,
                timeout=args.timeout,
            )
            with closing(connect_read_only(args.db)) as conn:
                remaining = remaining_missing_facts(conn, document.document_id)
            print(f"  complete: {result}; remaining no-page facts={remaining}", flush=True)
        except (ReprocessError, sqlite3.Error, ValueError) as exc:
            failures += 1
            print(f"  failed: {exc}", file=sys.stderr, flush=True)
            if args.stop_on_error:
                break
    print(f"\nFinished: {len(documents) - failures} succeeded, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
