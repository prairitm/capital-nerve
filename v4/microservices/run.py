"""Run the full 7-step event microservice flow.

Example:
    python run.py --symbol ITC --from-date 01-04-2026 --to-date 30-06-2026 \
        --event-type "Financial Results"

This script expects the seven FastAPI services to already be running on their
default ports:
    company     8020
    event       8021
    event_type  8022
    values      8023
    metrics     8024
    signals     8025
    alerts      8026
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_SERVICES = {
    "company": "http://127.0.0.1:8020",
    "event": "http://127.0.0.1:8021",
    "event_type": "http://127.0.0.1:8022",
    "values": "http://127.0.0.1:8023",
    "metrics": "http://127.0.0.1:8024",
    "signals": "http://127.0.0.1:8025",
    "alerts": "http://127.0.0.1:8026",
}

EVENT_TYPE_TO_DOCUMENT_TYPE = {
    "Financial Results": "financial_result",
    "Investor Presentation": "investor_presentation",
    "Earnings Call Transcript": "earnings_call_transcript",
}
ALL_EVENT_TYPES = list(EVENT_TYPE_TO_DOCUMENT_TYPE)
SUPPORTED_EVENT_TYPES = set(EVENT_TYPE_TO_DOCUMENT_TYPE)
SUPPORTED_SOURCE_MODES = {"nse_auto", "ir_agent", "manual_url", "local_file"}


@dataclass(frozen=True)
class Step:
    number: int
    name: str
    service: str
    method: str
    path: str


STEPS = [
    Step(1, "COMPANY", "company", "POST", "/companies"),
    Step(2, "EVENT", "event", "POST", "/events/discover"),
    Step(3, "EVENT TYPE", "event_type", "POST", "/event-type/resolve"),
    Step(4, "VALUES", "values", "POST", "/values/extract"),
    Step(5, "METRICS", "metrics", "POST", "/metrics/compute"),
    Step(6, "SIGNALS", "signals", "POST", "/signals/evaluate"),
    Step(7, "ALERTS", "alerts", "GET", "/alerts"),
]


class FlowError(RuntimeError):
    pass


class SkippableFlowError(FlowError):
    pass


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )


def normalize_base_url(url: str) -> str:
    return url.rstrip("/")


def encode_query(params: dict[str, Any]) -> str:
    clean = {
        key: value
        for key, value in params.items()
        if value is not None and value != ""
    }
    return urllib.parse.urlencode(clean)


def parse_documents_json(value: str | None) -> list[dict[str, Any]] | None:
    if not value:
        return None
    path = Path(value)
    raw = path.read_text(encoding="utf-8") if path.exists() else value
    parsed = json.loads(raw)
    documents = parsed.get("documents") if isinstance(parsed, dict) else parsed
    if not isinstance(documents, list):
        raise FlowError("--documents-json must be a JSON array or object with documents")
    return [dict(item) for item in documents]


def parse_document_shorthand(values: list[str] | None) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for value in values or []:
        item: dict[str, Any] = {}
        for part in value.split(","):
            if not part.strip():
                continue
            if "=" not in part:
                raise FlowError("--document entries must be comma-separated key=value pairs")
            key, raw = part.split("=", 1)
            item[key.strip()] = raw.strip()
        if item:
            documents.append(item)
    return documents


def normalize_source_mode(value: str | None) -> str | None:
    if value is None:
        return None
    mode = value.strip().lower().replace("-", "_")
    if mode not in SUPPORTED_SOURCE_MODES:
        allowed = ", ".join(sorted(SUPPORTED_SOURCE_MODES))
        raise FlowError(f"--source-mode must be one of: {allowed}")
    return mode


def default_document_type(event_type: str) -> str:
    try:
        return EVENT_TYPE_TO_DOCUMENT_TYPE[event_type]
    except KeyError as exc:
        allowed = ", ".join(sorted(SUPPORTED_EVENT_TYPES))
        raise FlowError(f"EVENT_TYPE must be one of: {allowed}") from exc


def apply_source_mode(
    documents: list[dict[str, Any]] | None,
    *,
    event_type: str,
    source_mode: str | None,
) -> list[dict[str, Any]] | None:
    if not source_mode:
        return documents
    if not documents:
        return [
            {
                "document_type": default_document_type(event_type),
                "source_mode": source_mode,
            }
        ]
    return [
        {
            **document,
            "source_mode": document.get("source_mode") or source_mode,
        }
        for document in documents
    ]


def request_json(
    method: str,
    url: str,
    *,
    query: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    timeout: float,
) -> dict[str, Any]:
    if query:
        url = f"{url}?{encode_query(query)}"

    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return {}
            return json.loads(raw)
    except (TimeoutError, socket.timeout) as exc:
        raise FlowError(f"{method} {url} timed out after {timeout:.0f}s") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        message = f"{method} {url} failed with HTTP {exc.code}: {detail}"
        if exc.code == 404 and "announcements found" in detail:
            raise SkippableFlowError(message) from exc
        raise FlowError(message) from exc
    except urllib.error.URLError as exc:
        raise FlowError(f"{method} {url} failed: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise FlowError(f"{method} {url} returned non-JSON response") from exc


def health_check(service_urls: dict[str, str], timeout: float) -> None:
    logging.info("Checking service health")
    for name in DEFAULT_SERVICES:
        url = f"{service_urls[name]}/health"
        payload = request_json("GET", url, timeout=timeout)
        logging.info("  %-10s ok=%s db=%s", name, payload.get("ok"), payload.get("db_path"))


def log_step_start(step: Step, params: dict[str, Any]) -> None:
    logging.info("=" * 78)
    logging.info("STEP %s / 7 - %s", step.number, step.name)
    logging.info("Calling %s %s with params: %s", step.method, step.path, compact_params(params))


def compact_params(params: dict[str, Any]) -> dict[str, Any]:
    out = dict(params)
    for key in ("company_id", "event_id", "document_id"):
        value = out.get(key)
        if isinstance(value, str) and len(value) > 16:
            out[key] = f"{value[:12]}..."
    return out


def log_step_result(step: Step, response: dict[str, Any], elapsed: float) -> None:
    summary: dict[str, Any] = {}
    for key in (
        "company_id",
        "announcements_count",
        "stored_count",
        "event_id",
        "chosen_source_url",
        "document_id",
        "extracted_count",
        "metrics_count",
        "fired_count",
        "alert_count",
        "message",
    ):
        if key in response:
            summary[key] = response[key]
    if "reporting_period" in response:
        rp = response["reporting_period"] or {}
        summary["period"] = rp.get("label") or rp.get("quarter_end")
    logging.info("Completed step %s in %.1fs: %s", step.number, elapsed, compact_params(summary))


def log_microservice_details(
    step: Step,
    response: dict[str, Any],
    *,
    detail_limit: int,
) -> None:
    """Log the useful per-step payload each microservice returns."""
    if step.name == "COMPANY":
        company = response.get("company") or {}
        logging.info(
            "  company: ticker=%s exchange=%s id=%s name=%s",
            company.get("ticker"),
            company.get("exchange"),
            compact_params({"company_id": company.get("id")}).get("company_id"),
            company.get("name"),
        )
        return

    if step.name == "EVENT":
        logging.info(
            "  announcements=%s stored=%s buckets=%s",
            response.get("announcements_count"),
            response.get("stored_count"),
            response.get("desc_buckets") or {},
        )
        events = response.get("events") or []
        for event in events[:detail_limit]:
            logging.info(
                "  event: %s %s status=%s url=%s",
                event.get("event_date"),
                event.get("event_type"),
                event.get("status"),
                event.get("source_url"),
            )
        if len(events) > detail_limit:
            logging.info("  ... %s more event(s)", len(events) - detail_limit)
        return

    if step.name == "EVENT TYPE":
        logging.info(
            "  chosen event_id=%s pdf=%s",
            compact_params({"event_id": response.get("event_id")}).get("event_id"),
            response.get("chosen_source_url"),
        )
        logging.info(
            "  candidates=%s period_markers=%s recovery_needed=%s",
            response.get("financial_results_count"),
            len(response.get("period_markers") or []),
            response.get("recovery_needed"),
        )
        classification = response.get("classification") or {}
        logging.info(
            "  pdf classification: is_fr=%s confidence=%s kind=%s",
            classification.get("is_financial_report"),
            classification.get("confidence"),
            classification.get("document_kind"),
        )
        for candidate in (response.get("candidates") or [])[:detail_limit]:
            logging.info(
                "  candidate%s: %s %s",
                " [chosen]" if candidate.get("chosen") else "",
                candidate.get("sort_date"),
                candidate.get("source_url"),
            )
        return

    if step.name == "VALUES":
        period = response.get("reporting_period") or {}
        logging.info(
            "  document_id=%s markdown_chars=%s period=%s (%s)",
            compact_params({"document_id": response.get("document_id")}).get("document_id"),
            response.get("markdown_length"),
            period.get("label"),
            period.get("quarter_end"),
        )
        values = response.get("values") or []
        logging.info("  extracted_values=%s", response.get("extracted_count"))
        for row in values[:detail_limit]:
            logging.info(
                "  value: %-28s %12s %-8s basis=%s conf=%s",
                row.get("fact_key"),
                row.get("numeric_value"),
                row.get("unit") or "",
                row.get("basis"),
                row.get("confidence"),
            )
        if len(values) > detail_limit:
            logging.info("  ... %s more value(s)", len(values) - detail_limit)
        return

    if step.name == "METRICS":
        scope_counts = response.get("scope_counts") or {}
        logging.info(
            "  metrics=%s source_facts=%s",
            response.get("metrics_count"),
            scope_counts,
        )
        metrics = response.get("metrics") or []
        for metric in metrics[:detail_limit]:
            logging.info(
                "  metric: %-32s %12s %-6s [%s]",
                metric.get("metric_key"),
                metric.get("value"),
                metric.get("unit") or "",
                metric.get("category"),
            )
        if len(metrics) > detail_limit:
            logging.info("  ... %s more metric(s)", len(metrics) - detail_limit)
        return

    if step.name == "SIGNALS":
        source_counts = response.get("source_counts") or {}
        logging.info(
            "  rules=%s metrics=%s facts=%s fired=%s",
            source_counts.get("rules"),
            source_counts.get("metrics"),
            source_counts.get("facts"),
            response.get("fired_count"),
        )
        signals = response.get("signals") or []
        for signal in signals[:detail_limit]:
            logging.info(
                "  signal: [%s/%s] %s :: %s",
                signal.get("severity"),
                signal.get("direction"),
                signal.get("signal_key"),
                signal.get("trigger_values"),
            )
        if len(signals) > detail_limit:
            logging.info("  ... %s more signal(s)", len(signals) - detail_limit)
        return

    if step.name == "ALERTS":
        logging.info("  %s", response.get("message"))
        logging.info("  db_summary=%s", response.get("db_summary") or {})
        alerts = response.get("alerts") or []
        for alert in alerts[:detail_limit]:
            logging.info(
                "  alert: [%s/%s] %s triggers=%s",
                alert.get("severity"),
                alert.get("direction"),
                alert.get("title"),
                alert.get("trigger_values"),
            )
        if len(alerts) > detail_limit:
            logging.info("  ... %s more alert(s)", len(alerts) - detail_limit)


def require_next_params(response: dict[str, Any], step: Step) -> dict[str, Any]:
    next_params = response.get("next_service_params")
    if not isinstance(next_params, dict):
        raise FlowError(f"Step {step.number} response did not include next_service_params")
    return next_params


def wait_for_values_job(
    *,
    values_url: str,
    params: dict[str, Any],
    timeout: float,
    poll_interval: float,
) -> dict[str, Any]:
    started = time.monotonic()
    start_response = request_json(
        "POST",
        f"{values_url}/values/extract/jobs",
        query=params,
        timeout=min(timeout, 30.0),
    )
    job_id = start_response.get("job_id")
    status_url = start_response.get("status_url")
    if not job_id or not status_url:
        raise FlowError("VALUES job start response did not include job_id and status_url")

    job_url = status_url if str(status_url).startswith("http") else f"{values_url}{status_url}"
    logging.info("VALUES job queued: job_id=%s", job_id)
    last_status = ""
    last_progress = ""

    while True:
        elapsed = time.monotonic() - started
        remaining = timeout - elapsed
        if remaining <= 0:
            raise FlowError(f"VALUES job {job_id} timed out after {timeout:.0f}s")

        status_response = request_json(
            "GET",
            job_url,
            timeout=min(max(remaining, 1.0), 30.0),
        )
        status = str(status_response.get("status") or "")
        if status != last_status:
            logging.info("VALUES job %s status=%s elapsed=%.1fs", job_id, status, elapsed)
            last_status = status
        progress = status_response.get("progress")
        if isinstance(progress, dict):
            progress_key = json.dumps(progress, sort_keys=True, default=str)
            if progress_key != last_progress:
                logging.info(
                    "VALUES progress: phase=%s job_elapsed=%s route_elapsed=%s message=%s details=%s",
                    progress.get("phase"),
                    progress.get("job_elapsed_seconds"),
                    progress.get("elapsed_seconds"),
                    progress.get("message"),
                    compact_params(
                        {
                            key: value
                            for key, value in progress.items()
                            if key
                            not in {
                                "phase",
                                "message",
                                "job_id",
                                "job_elapsed_seconds",
                                "elapsed_seconds",
                                "route",
                            }
                        }
                    ),
                )
                last_progress = progress_key

        if status == "succeeded":
            result = status_response.get("result")
            if not isinstance(result, dict):
                raise FlowError(f"VALUES job {job_id} succeeded without result")
            return result
        if status == "failed":
            raise FlowError(f"VALUES job {job_id} failed: {status_response.get('error')}")

        time.sleep(min(poll_interval, max(remaining, 0.1)))


def run_flow(args: argparse.Namespace) -> dict[str, Any]:
    documents = parse_documents_json(args.documents_json)
    shorthand_documents = parse_document_shorthand(args.document)
    if documents and shorthand_documents:
        raise FlowError("Use either --documents-json or --document, not both")
    documents = documents or shorthand_documents or None
    if args.event_type not in SUPPORTED_EVENT_TYPES:
        allowed = ", ".join(sorted(SUPPORTED_EVENT_TYPES))
        raise FlowError(f"EVENT_TYPE must be one of: {allowed}")
    source_mode = normalize_source_mode(args.source_mode)
    documents = apply_source_mode(
        documents,
        event_type=args.event_type,
        source_mode=source_mode,
    )
    service_urls = {
        name: normalize_base_url(getattr(args, f"{name}_url"))
        for name in DEFAULT_SERVICES
    }

    if not args.skip_health:
        health_check(service_urls, args.timeout)

    params: dict[str, Any] = {
        "symbol": args.symbol.strip().upper(),
        "from_date": args.from_date.strip(),
        "to_date": args.to_date.strip(),
        "event_type": args.event_type,
    }
    if documents:
        params["documents"] = documents

    final_response: dict[str, Any] = {}
    for step in STEPS:
        log_step_start(step, params)
        url = f"{service_urls[step.service]}{step.path}"
        started = time.monotonic()

        if step.name == "COMPANY":
            response = request_json(
                step.method,
                url,
                body={"symbol": params["symbol"]},
                timeout=args.timeout,
            )
            company = response.get("company") or {}
            next_params = {
                "symbol": params["symbol"],
                "from_date": params["from_date"],
                "to_date": params["to_date"],
                "event_type": params["event_type"],
                "company_id": company.get("id"),
            }
            if not next_params["company_id"]:
                raise FlowError("Step 1 response did not include company.id")
        elif step.name == "EVENT TYPE":
            query = {
                "symbol": params["symbol"],
                "from_date": params["from_date"],
                "to_date": params["to_date"],
                "company_id": params["company_id"],
                "event_type": params["event_type"],
            }
            if params.get("documents"):
                query["documents_json"] = json.dumps(params["documents"])
            response = request_json(
                step.method,
                url,
                query=query,
                timeout=args.timeout,
            )
            next_params = require_next_params(response, step)
            next_params["event_type"] = params["event_type"]
            if response.get("resolved_documents"):
                next_params["resolved_documents"] = response["resolved_documents"]
        elif step.name == "VALUES" and not args.values_sync:
            values_params = {
                **params,
                **{
                    key: value
                    for key, value in {
                        "parse_max_workers": args.values_parse_workers,
                        "extraction_max_workers": args.values_extraction_workers,
                    }.items()
                    if value is not None
                },
            }
            if values_params.get("resolved_documents"):
                values_params["resolved_documents_json"] = json.dumps(values_params.pop("resolved_documents"))
            response = wait_for_values_job(
                values_url=service_urls[step.service],
                params=values_params,
                timeout=args.timeout,
                poll_interval=args.poll_interval,
            )
            next_params = require_next_params(response, step)
            next_params["event_type"] = params["event_type"]
        else:
            query_params = params
            if step.name == "VALUES":
                query_params = {
                    **params,
                    **{
                        key: value
                        for key, value in {
                            "parse_max_workers": args.values_parse_workers,
                            "extraction_max_workers": args.values_extraction_workers,
                        }.items()
                        if value is not None
                    },
                }
                if query_params.get("resolved_documents"):
                    query_params = dict(query_params)
                    query_params["resolved_documents_json"] = json.dumps(query_params.pop("resolved_documents"))
            response = request_json(
                step.method,
                url,
                query=query_params,
                timeout=args.timeout,
            )
            next_params = require_next_params(response, step)
            next_params["event_type"] = params["event_type"]

        elapsed = time.monotonic() - started
        log_step_result(step, response, elapsed)
        log_microservice_details(step, response, detail_limit=args.detail_limit)
        logging.debug("Full step %s response:\n%s", step.number, json.dumps(response, indent=2))

        params = next_params
        final_response = response

    logging.info("=" * 78)
    logging.info("Flow complete for %s [%s -> %s]", args.symbol, args.from_date, args.to_date)
    logging.info("Final params: %s", compact_params(params))
    return final_response


def event_types_for_args(args: argparse.Namespace) -> list[str]:
    if args.all_event_types:
        if args.event_type:
            raise FlowError("Use either --event-type or --all-event-types, not both")
        return ALL_EVENT_TYPES
    if not args.event_type:
        raise FlowError("Pass --event-type or --all-event-types")
    return [args.event_type]


def log_run_report(results: list[dict[str, Any]]) -> None:
    logging.info("=" * 78)
    logging.info("RUN REPORT")
    for result in results:
        logging.info(
            "%-24s %-9s %s",
            result["event_type"],
            result["status"],
            result.get("message") or "",
        )
    completed = sum(1 for result in results if result["status"] == "completed")
    skipped = sum(1 for result in results if result["status"] == "skipped")
    failed = sum(1 for result in results if result["status"] == "failed")
    logging.info(
        "Summary: completed=%s skipped=%s failed=%s total=%s",
        completed,
        skipped,
        failed,
        len(results),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the 7-step CapitalNerve event microservice flow."
    )
    parser.add_argument("--symbol", required=True, help="NSE-listed symbol, e.g. ITC")
    parser.add_argument("--from-date", required=True, help="NSE fromDate, DD-MM-YYYY")
    parser.add_argument("--to-date", required=True, help="NSE toDate, DD-MM-YYYY")
    parser.add_argument(
        "--event-type",
        default=None,
        help='Supported values: "Financial Results", "Investor Presentation", "Earnings Call Transcript".',
    )
    parser.add_argument(
        "--all-event-types",
        action="store_true",
        help="Run the flow once for each supported event type.",
    )
    parser.add_argument(
        "--documents-json",
        default=None,
        help="Unified document queue as a JSON string or a path to a JSON file.",
    )
    parser.add_argument(
        "--document",
        action="append",
        default=None,
        help=(
            "Repeatable unified document shorthand, e.g. "
            "document_type=investor_presentation,source_mode=nse_auto"
        ),
    )
    parser.add_argument(
        "--source-mode",
        choices=sorted(SUPPORTED_SOURCE_MODES),
        default=None,
        help=(
            "Source mode for the Step 3 document request. If --document or "
            "--documents-json is provided, this fills source_mode only when a "
            "document omits it."
        ),
    )
    parser.add_argument("--timeout", type=float, default=900.0, help="HTTP timeout seconds")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Seconds between VALUES job status polls",
    )
    parser.add_argument(
        "--values-sync",
        action="store_true",
        help="Call /values/extract synchronously instead of using the background job endpoint",
    )
    parser.add_argument(
        "--values-parse-workers",
        type=int,
        default=None,
        help="Override Step 4 PDF parse worker count",
    )
    parser.add_argument(
        "--values-extraction-workers",
        type=int,
        default=None,
        help="Override Step 4 fallback extraction worker count",
    )
    parser.add_argument(
        "--detail-limit",
        type=int,
        default=10,
        help="Maximum rows to log from list-like step outputs.",
    )
    parser.add_argument("--skip-health", action="store_true", help="Skip service health checks")
    parser.add_argument("--verbose", action="store_true", help="Log full JSON responses")

    for name, default in DEFAULT_SERVICES.items():
        parser.add_argument(
            f"--{name.replace('_', '-')}-url",
            default=default,
            help=f"{name} service base URL (default: {default})",
        )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)

    results: list[dict[str, Any]] = []
    try:
        event_types = event_types_for_args(args)
    except FlowError as exc:
        logging.error("%s", exc)
        return 1

    try:
        for index, event_type in enumerate(event_types, start=1):
            args.event_type = event_type
            if len(event_types) > 1:
                logging.info("=" * 78)
                logging.info(
                    "Running event type %s/%s: %s",
                    index,
                    len(event_types),
                    event_type,
                )
            try:
                run_flow(args)
            except SkippableFlowError as exc:
                logging.warning("Skipping %s: %s", event_type, exc)
                results.append(
                    {
                        "event_type": event_type,
                        "status": "skipped",
                        "message": str(exc),
                    }
                )
                continue
            except FlowError as exc:
                logging.error("%s failed: %s", event_type, exc)
                results.append(
                    {
                        "event_type": event_type,
                        "status": "failed",
                        "message": str(exc),
                    }
                )
                if len(event_types) == 1:
                    log_run_report(results)
                    return 1
                continue
            results.append(
                {
                    "event_type": event_type,
                    "status": "completed",
                    "message": "ok",
                }
            )
    except KeyboardInterrupt:
        logging.error("Interrupted")
        if results:
            log_run_report(results)
        return 130

    log_run_report(results)
    return 1 if any(result["status"] == "failed" for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
