#!/usr/bin/env python3
"""Audit and reprocess v4 events whose stored fiscal quarter is misaligned.

The default mode is read-only. It detects the expected reporting period with
the same logic as the values service and prints only mismatches. Pass --apply
to re-run values extraction and, by default, metrics, signals, and alerts.
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
VALUES_DIR = V4_DIR / "microservices" / "values"
if str(VALUES_DIR) not in sys.path:
    sys.path.insert(0, str(VALUES_DIR))

from periods import (  # noqa: E402
    ReportingPeriod,
    detect_reporting_period,
    prior_quarter_period,
    reporting_period_from_date,
)


DEFAULT_DB = V4_DIR / "data" / "capital_nerve.db"
EVENT_DOCUMENT_TYPES = {
    "Financial Results": "financial_result",
    "Investor Presentation": "investor_presentation",
    "Earnings Call Transcript": "earnings_call_transcript",
}


class ReprocessError(RuntimeError):
    pass


@dataclass(frozen=True)
class MisalignedEvent:
    event_id: str
    company_id: str
    symbol: str
    event_type: str
    event_date: str
    title: str
    document_id: str | None
    source_url: str | None
    storage_path: str | None
    stored_fiscal_year: int
    stored_fiscal_quarter: int
    expected_fiscal_year: int
    expected_fiscal_quarter: int
    expected_period_end: str
    expected_label: str
    detection_source: str
    parsed_path: str | None

    @property
    def stored_label(self) -> str:
        end_short = (self.stored_fiscal_year + 1) % 100
        return (
            f"Q{self.stored_fiscal_quarter} "
            f"FY{self.stored_fiscal_year}-{end_short:02d}"
        )

    @property
    def request_dates(self) -> tuple[str, str]:
        parsed = date.fromisoformat(self.event_date[:10])
        formatted = parsed.strftime("%d-%m-%Y")
        return formatted, formatted

    @property
    def document_type(self) -> str:
        return EVENT_DOCUMENT_TYPES.get(self.event_type, "financial_result")


def connect_read_only(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise ReprocessError(f"Analytics database does not exist: {path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _existing_path(candidates: Sequence[Path]) -> Path | None:
    return next((path.resolve() for path in candidates if path.is_file()), None)


def parsed_document_path(
    document_id: str | None,
    *,
    db_path: Path,
) -> Path | None:
    if not document_id:
        return None
    filename = f"{document_id}.md"
    return _existing_path(
        (
            db_path.parent / "parsed" / filename,
            V4_DIR / "data" / "parsed" / filename,
        )
    )


def local_document_path(
    storage_path: str | None,
    *,
    db_path: Path,
) -> Path | None:
    if not storage_path:
        return None
    path = Path(storage_path).expanduser()
    candidates = (
        (path,)
        if path.is_absolute()
        else (db_path.parent / path, V4_DIR / path)
    )
    return _existing_path(candidates)


def expected_reporting_period(
    *,
    markdown: str,
    title: str,
    event_date: str,
) -> ReportingPeriod:
    detected = detect_reporting_period(markdown, title=title)
    if detected is not None:
        return detected
    announcement = reporting_period_from_date(
        date.fromisoformat(event_date[:10]),
        "announcement_date",
    )
    fallback = prior_quarter_period(announcement)
    fallback.source = "previous_completed_quarter_fallback"
    return fallback


def find_misaligned_events(
    conn: sqlite3.Connection,
    *,
    db_path: Path,
    event_ids: Sequence[str] = (),
    document_ids: Sequence[str] = (),
    symbols: Sequence[str] = (),
    limit: int | None = None,
) -> list[MisalignedEvent]:
    filters = [
        "e.fiscal_year IS NOT NULL",
        "e.fiscal_quarter IS NOT NULL",
        "e.event_date IS NOT NULL",
    ]
    params: list[Any] = []
    for column, values in (
        ("e.id", event_ids),
        ("e.document_id", document_ids),
        ("UPPER(c.ticker)", tuple(value.upper() for value in symbols)),
    ):
        if values:
            placeholders = ",".join("?" for _ in values)
            filters.append(f"{column} IN ({placeholders})")
            params.extend(values)

    rows = conn.execute(
        f"""
        SELECT e.id AS event_id,
               e.company_id,
               c.ticker AS symbol,
               e.event_type,
               e.event_date,
               COALESCE(e.title, d.title, '') AS title,
               e.document_id,
               COALESCE(d.source_url, e.source_url) AS source_url,
               d.storage_path,
               e.fiscal_year,
               e.fiscal_quarter
        FROM events e
        JOIN companies c ON c.id = e.company_id
        LEFT JOIN documents d ON d.id = e.document_id
        WHERE {' AND '.join(filters)}
        ORDER BY e.event_date, c.ticker, e.id
        """,
        tuple(params),
    ).fetchall()

    mismatches: list[MisalignedEvent] = []
    for row in rows:
        parsed_path = parsed_document_path(row["document_id"], db_path=db_path)
        markdown = (
            parsed_path.read_text(encoding="utf-8", errors="replace")
            if parsed_path
            else ""
        )
        expected = expected_reporting_period(
            markdown=markdown,
            title=str(row["title"] or ""),
            event_date=str(row["event_date"]),
        )
        stored = (int(row["fiscal_year"]), int(row["fiscal_quarter"]))
        corrected = (expected.fy_start_year, expected.quarter)
        if stored == corrected:
            continue
        mismatches.append(
            MisalignedEvent(
                event_id=str(row["event_id"]),
                company_id=str(row["company_id"]),
                symbol=str(row["symbol"]),
                event_type=str(row["event_type"] or "Financial Results"),
                event_date=str(row["event_date"]),
                title=str(row["title"] or ""),
                document_id=(
                    str(row["document_id"]) if row["document_id"] else None
                ),
                source_url=str(row["source_url"]) if row["source_url"] else None,
                storage_path=(
                    str(row["storage_path"]) if row["storage_path"] else None
                ),
                stored_fiscal_year=stored[0],
                stored_fiscal_quarter=stored[1],
                expected_fiscal_year=corrected[0],
                expected_fiscal_quarter=corrected[1],
                expected_period_end=expected.quarter_end,
                expected_label=expected.label,
                detection_source=expected.source,
                parsed_path=str(parsed_path) if parsed_path else None,
            )
        )
        if limit is not None and len(mismatches) >= limit:
            break
    return mismatches


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
        raise ReprocessError(
            f"{method} {url} failed with HTTP {exc.code}: {detail}"
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ReprocessError(f"{method} {url} failed: {exc}") from exc
    try:
        return json.loads(payload) if payload else {}
    except json.JSONDecodeError as exc:
        raise ReprocessError(f"{method} {url} returned invalid JSON") from exc


def reprocess_event(
    event: MisalignedEvent,
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
    source_path = local_document_path(event.storage_path, db_path=db_path)
    if source_path is None and not event.source_url:
        raise ReprocessError(
            f"{event.event_id} has neither an accessible local file nor a source URL"
        )
    from_date, to_date = event.request_dates
    values = request_json(
        "POST",
        f"{values_url.rstrip('/')}/values/extract",
        query={
            "symbol": event.symbol,
            "from_date": from_date,
            "to_date": to_date,
            "company_id": event.company_id,
            "event_id": event.event_id,
            "event_type": event.event_type,
            "document_type": event.document_type,
            "local_path": str(source_path) if source_path else None,
            "pdf_url": None if source_path else event.source_url,
            "force_reparse": force_reparse,
        },
        timeout=timeout,
    )
    period = values.get("reporting_period") or {}
    result: dict[str, Any] = {
        "values": values.get("extracted_count", 0),
        "period": period.get("label"),
    }
    if period.get("label") != event.expected_label:
        raise ReprocessError(
            f"values service returned {period.get('label')!r}; "
            f"expected {event.expected_label!r}"
        )
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


def stored_period(conn: sqlite3.Connection, event_id: str) -> tuple[int, int]:
    row = conn.execute(
        "SELECT fiscal_year, fiscal_quarter FROM events WHERE id = ?",
        (event_id,),
    ).fetchone()
    if row is None or row["fiscal_year"] is None or row["fiscal_quarter"] is None:
        raise ReprocessError(f"event {event_id} has no stored reporting period")
    return int(row["fiscal_year"]), int(row["fiscal_quarter"])


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.getenv("V4_DB_PATH", DEFAULT_DB)),
        help="analytics DB (default: V4_DB_PATH or v4/data/capital_nerve.db)",
    )
    parser.add_argument("--event-id", action="append", default=[])
    parser.add_argument("--document-id", action="append", default=[])
    parser.add_argument("--symbol", action="append", default=[])
    parser.add_argument("--limit", type=int, help="maximum number of mismatches")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform reprocessing; otherwise preview only",
    )
    parser.add_argument(
        "--force-reparse",
        action="store_true",
        help="rerun PDF-to-Markdown parsing too",
    )
    parser.add_argument(
        "--skip-downstream",
        action="store_true",
        help="skip metrics, signals, and alerts recomputation",
    )
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument(
        "--timeout",
        type=float,
        default=3600,
        help="per-service request timeout in seconds",
    )
    parser.add_argument(
        "--values-url",
        default=os.getenv("REPROCESS_VALUES_URL", "http://127.0.0.1:8023"),
    )
    parser.add_argument(
        "--metrics-url",
        default=os.getenv("REPROCESS_METRICS_URL", "http://127.0.0.1:8024"),
    )
    parser.add_argument(
        "--signals-url",
        default=os.getenv("REPROCESS_SIGNALS_URL", "http://127.0.0.1:8025"),
    )
    parser.add_argument(
        "--alerts-url",
        default=os.getenv("REPROCESS_ALERTS_URL", "http://127.0.0.1:8026"),
    )
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
            events = find_misaligned_events(
                conn,
                db_path=args.db,
                event_ids=args.event_id,
                document_ids=args.document_id,
                symbols=args.symbol,
                limit=args.limit,
            )
    except (OSError, ReprocessError, sqlite3.Error, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"Mode: {mode}\nMisaligned events: {len(events)}")
    for event in events:
        source = (
            local_document_path(event.storage_path, db_path=args.db)
            or event.source_url
            or "unavailable"
        )
        print(
            f"- {event.symbol} {event.event_date} {event.event_type}: "
            f"{event.stored_label} -> {event.expected_label} "
            f"[{event.detection_source}] event={event.event_id} source={source}"
        )
    if not args.apply or not events:
        if not args.apply:
            print("\nNo changes made. Re-run with --apply after reviewing this list.")
        return 0

    failures = 0
    succeeded = 0
    for index, event in enumerate(events, start=1):
        print(
            f"\n[{index}/{len(events)}] Reprocessing "
            f"{event.symbol} {event.event_id}...",
            flush=True,
        )
        try:
            result = reprocess_event(
                event,
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
                actual = stored_period(conn, event.event_id)
            expected = (
                event.expected_fiscal_year,
                event.expected_fiscal_quarter,
            )
            if actual != expected:
                raise ReprocessError(
                    f"stored period after reprocessing is {actual}; expected {expected}"
                )
            succeeded += 1
            print(f"  complete: {result}", flush=True)
        except (OSError, ReprocessError, sqlite3.Error, ValueError) as exc:
            failures += 1
            print(f"  failed: {exc}", file=sys.stderr, flush=True)
            if args.stop_on_error:
                break
    print(f"\nFinished: {succeeded} succeeded, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
