from __future__ import annotations

import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from run import request_json, run_exact_document_flow
from reconcile_reviews import apply_approved_reviews, connect as reconciliation_conn, recompute_event

from .monitor_config import Settings
from .monitor_db import (
    cancel_email,
    claim_email,
    claim_due_company,
    claim_job,
    complete_job,
    complete_job_and_enqueue_notifications,
    complete_email,
    email_counts,
    email_delivery_allowed,
    enqueue_job,
    ensure_watch_states,
    fail_job,
    fail_email,
    fail_poll,
    finish_poll,
    heartbeat_job,
    job_counts,
    require_schema,
    reserve_canonical_job,
    utc_iso,
    utc_now,
)
from .notifications import PermanentNotificationError, send_email


logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class CanonicalJobAlreadyQueued(RuntimeError):
    pass


def _parse_time(value: str | None, *, naive_timezone=timezone.utc) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d-%b-%Y %H:%M:%S", "%d-%m-%Y %H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=naive_timezone).astimezone(timezone.utc)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=naive_timezone)
    return parsed.astimezone(timezone.utc)


def _nse_date(value: datetime) -> str:
    return value.astimezone(IST).strftime("%d-%m-%Y")


class MonitorRuntime:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.worker_id = uuid.uuid4().hex
        self.stop_event = threading.Event()
        self.threads: list[threading.Thread] = []
        self.last_poll_at: str | None = None

    def start(self) -> None:
        require_schema(self.settings.app_db_path)
        ensure_watch_states(self.settings.app_db_path)
        self.threads = [
            threading.Thread(target=self._poll_loop, name="filing-poller", daemon=True),
            threading.Thread(target=self._worker_loop, name="filing-worker", daemon=True),
            threading.Thread(target=self._notification_loop, name="email-worker", daemon=True),
            threading.Thread(
                target=self._review_reconciliation_loop,
                name="review-reconciler",
                daemon=True,
            ),
        ]
        for thread in self.threads:
            thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        for thread in self.threads:
            thread.join(timeout=5)

    def health(self) -> dict:
        return {
            "ok": bool(self.threads) and all(thread.is_alive() for thread in self.threads),
            "worker_id": self.worker_id,
            "last_poll_at": self.last_poll_at,
            "jobs": job_counts(self.settings.app_db_path),
            "emails": email_counts(self.settings.app_db_path),
            "smtp_configured": bool(self.settings.smtp_password),
            "app_db_path": str(self.settings.app_db_path),
        }

    def _reconcile_approved_reviews(self) -> int:
        app = reconciliation_conn(self.settings.app_db_path, writable=True)
        try:
            due = app.execute(
                """
                SELECT 1 FROM fact_review_decisions
                WHERE decision = 'approved' AND (
                    application_status IN ('pending', 'failed')
                    OR (application_status = 'applied' AND recompute_status IN ('pending', 'failed'))
                )
                LIMIT 1
                """
            ).fetchone()
            if due is None:
                return 0

            analytics = reconciliation_conn(self.settings.analytics_db_path, writable=True)
            try:
                results = apply_approved_reviews(
                    analytics,
                    app,
                    applied_by="automatic-review-reconciler",
                    recompute=recompute_event,
                )
            finally:
                analytics.close()
        finally:
            app.close()
        for result in results:
            if result.recompute_status == "failed" or result.status == "invalid":
                logger.error(
                    "Review reconciliation %s failed: %s",
                    result.resolved_fact_id,
                    result.message,
                )
            else:
                logger.info(
                    "Review reconciliation %s completed (%s)",
                    result.resolved_fact_id,
                    result.recompute_status,
                )
        return len(results)

    def _review_reconciliation_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                self._reconcile_approved_reviews()
                self.stop_event.wait(self.settings.review_reconciliation_interval_seconds)
            except Exception:
                logger.exception("Review reconciliation loop error")
                self.stop_event.wait(self.settings.review_reconciliation_interval_seconds)

    def _company_symbol(self, company_id: str) -> str:
        uri = f"file:{self.settings.analytics_db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT ticker FROM companies WHERE id = ?", (company_id,)).fetchone()
        finally:
            conn.close()
        if row is None or not row["ticker"]:
            raise LookupError(f"Watched company {company_id} has no analytics ticker")
        return str(row["ticker"]).strip().upper()

    def _poll_company(self, state: dict) -> None:
        company_id = state["company_id"]
        symbol = self._company_symbol(company_id)
        now = utc_now()
        baseline = _parse_time(state.get("baseline_at")) or now
        last_success = _parse_time(state.get("last_success_at")) or baseline
        from_time = min(last_success, baseline) - timedelta(days=1)
        from_date, to_date = _nse_date(from_time), _nse_date(now)
        response = request_json(
            "POST",
            f"{self.settings.service_urls['event'].rstrip('/')}/events/discover",
            query={
                "symbol": symbol,
                "from_date": from_date,
                "to_date": to_date,
                "company_id": company_id,
            },
            timeout=60,
        )
        queued = 0
        for item in response.get("events") or []:
            event_type = item.get("normalized_event_type")
            source_url = item.get("source_url")
            published = _parse_time(item.get("published_at"), naive_timezone=IST)
            if not event_type or not source_url or not published or published < baseline:
                continue
            queued += int(
                enqueue_job(
                    self.settings.app_db_path,
                    pipeline_version=self.settings.pipeline_version,
                    max_attempts=self.settings.max_attempts,
                    event={
                        "event_id": item["id"],
                        "company_id": company_id,
                        "symbol": symbol,
                        "event_type": event_type,
                        "source_url": source_url,
                        "title": item.get("title"),
                        "published_at": utc_iso(published),
                        "from_date": from_date,
                        "to_date": to_date,
                    },
                )
            )
        finish_poll(self.settings.app_db_path, company_id, self.settings.poll_interval_seconds)
        self.last_poll_at = utc_iso()
        logger.info("Polled %s: announcements=%s queued=%s", symbol, response.get("announcements_count"), queued)

    def _poll_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                ensure_watch_states(self.settings.app_db_path)
                state = claim_due_company(self.settings.app_db_path, self.settings.poll_lease_seconds)
                if state is None:
                    self.stop_event.wait(1)
                    continue
                try:
                    self._poll_company(state)
                except Exception as exc:
                    logger.exception("Company poll failed for %s", state["company_id"])
                    fail_poll(
                        self.settings.app_db_path,
                        state["company_id"],
                        str(exc),
                        self.settings.poll_interval_seconds,
                    )
            except Exception:
                logger.exception("Monitor poll loop error")
                self.stop_event.wait(5)

    def _flow_args(self, job: dict) -> SimpleNamespace:
        values = {
            "symbol": job["symbol"],
            "from_date": job["from_date"],
            "to_date": job["to_date"],
            "event_type": job["event_type"],
            "skip_health": True,
            "timeout": self.settings.flow_timeout_seconds,
            "poll_interval": 5.0,
            "values_sync": False,
            "values_parse_workers": None,
            "values_extraction_workers": None,
            "detail_limit": 5,
        }
        for name, url in self.settings.service_urls.items():
            values[f"{name}_url"] = url
        return SimpleNamespace(**values)

    def _heartbeat_loop(self, job_id: str, done: threading.Event) -> None:
        interval = max(5, self.settings.job_lease_seconds // 3)
        while not done.wait(interval):
            try:
                heartbeat_job(
                    self.settings.app_db_path,
                    job_id,
                    self.worker_id,
                    self.settings.job_lease_seconds,
                )
            except Exception:
                logger.exception("Could not renew job lease for %s", job_id)

    def _run_job(self, job: dict) -> None:
        done = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_loop,
            args=(job["id"], done),
            name=f"job-heartbeat-{job['id'][:8]}",
            daemon=True,
        )
        heartbeat.start()
        try:
            def reserve(canonical_event_id: str) -> None:
                if not reserve_canonical_job(self.settings.app_db_path, job["id"], canonical_event_id):
                    raise CanonicalJobAlreadyQueued(canonical_event_id)

            result = run_exact_document_flow(
                self._flow_args(job),
                company_id=job["company_id"],
                source_url=job["source_url"],
                title=job.get("title"),
                resolved_callback=reserve,
            )
            queued = complete_job_and_enqueue_notifications(
                self.settings.app_db_path,
                job["id"],
                result["canonical_event_id"],
                max_attempts=self.settings.email_max_attempts,
            )
            logger.info("Pipeline job %s succeeded; queued %s email(s)", job["id"], queued)
        except CanonicalJobAlreadyQueued as exc:
            complete_job(self.settings.app_db_path, job["id"], str(exc))
            logger.info("Pipeline job %s is a canonical duplicate", job["id"])
        except Exception as exc:
            logger.exception("Pipeline job %s failed", job["id"])
            fail_job(self.settings.app_db_path, job, str(exc))
        finally:
            done.set()
            heartbeat.join(timeout=2)

    def _worker_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                job = claim_job(
                    self.settings.app_db_path,
                    self.worker_id,
                    self.settings.job_lease_seconds,
                )
                if job is None:
                    self.stop_event.wait(1)
                    continue
                self._run_job(job)
            except Exception:
                logger.exception("Monitor worker loop error")
                self.stop_event.wait(5)

    def _notification_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                item = claim_email(
                    self.settings.app_db_path,
                    self.worker_id,
                    self.settings.email_lease_seconds,
                )
                if item is None:
                    self.stop_event.wait(self.settings.email_worker_interval_seconds)
                    continue
                allowed, reason = email_delivery_allowed(self.settings.app_db_path, item)
                if not allowed:
                    cancel_email(self.settings.app_db_path, item["id"], reason or "Delivery cancelled")
                    continue
                try:
                    provider_id = send_email(self.settings, item)
                except PermanentNotificationError as exc:
                    logger.error("Email %s permanently failed: %s", item["id"], exc)
                    fail_email(self.settings.app_db_path, item, str(exc), permanent=True)
                except Exception as exc:
                    logger.exception("Email %s failed", item["id"])
                    fail_email(self.settings.app_db_path, item, str(exc))
                else:
                    complete_email(self.settings.app_db_path, item["id"], provider_id)
                    logger.info("Email %s sent", item["id"])
            except Exception:
                logger.exception("Notification worker loop error")
                self.stop_event.wait(5)
