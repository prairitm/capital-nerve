from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


REQUIRED_TABLES = {
    "company_poll_state", "pipeline_jobs", "watchlist_companies", "users",
    "notification_preferences", "notification_action_tokens", "email_outbox",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat()


def connect_app(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def app_conn(path: Path) -> Iterator[sqlite3.Connection]:
    conn = connect_app(path)
    try:
        yield conn
    finally:
        conn.close()


def require_schema(path: Path) -> None:
    with app_conn(path) as conn:
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
    missing = REQUIRED_TABLES - tables
    if missing:
        raise RuntimeError(f"Monitor database migration is missing tables: {', '.join(sorted(missing))}")


def ensure_watch_states(path: Path) -> None:
    now = utc_iso()
    with app_conn(path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO company_poll_state(
                company_id, baseline_at, next_poll_at, created_at, updated_at
            )
            SELECT DISTINCT w.company_id, ?, ?, ?, ?
            FROM watchlist_companies w
            JOIN users u ON u.id = w.user_id AND u.is_active = 1
            """,
            (now, now, now, now),
        )
        conn.commit()


def claim_due_company(path: Path, lease_seconds: int) -> dict[str, Any] | None:
    now = utc_now()
    lease_until = utc_iso(now + timedelta(seconds=lease_seconds))
    with app_conn(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT cps.*
            FROM company_poll_state cps
            WHERE datetime(cps.next_poll_at) <= datetime(?)
              AND (cps.lease_until IS NULL OR datetime(cps.lease_until) <= datetime(?))
              AND EXISTS (
                  SELECT 1 FROM watchlist_companies w
                  JOIN users u ON u.id = w.user_id
                  WHERE w.company_id = cps.company_id AND u.is_active = 1
              )
            ORDER BY datetime(cps.next_poll_at), cps.company_id
            LIMIT 1
            """,
            (utc_iso(now), utc_iso(now)),
        ).fetchone()
        if row is None:
            conn.commit()
            return None
        conn.execute(
            "UPDATE company_poll_state SET lease_until = ?, updated_at = ? WHERE company_id = ?",
            (lease_until, utc_iso(now), row["company_id"]),
        )
        conn.commit()
        return dict(row)


def finish_poll(path: Path, company_id: str, interval_seconds: int) -> None:
    now = utc_now()
    with app_conn(path) as conn:
        conn.execute(
            """
            UPDATE company_poll_state
            SET last_success_at = ?, next_poll_at = ?, lease_until = NULL,
                last_error = NULL, consecutive_failures = 0, updated_at = ?
            WHERE company_id = ?
            """,
            (utc_iso(now), utc_iso(now + timedelta(seconds=interval_seconds)), utc_iso(now), company_id),
        )
        conn.commit()


def fail_poll(path: Path, company_id: str, message: str, interval_seconds: int) -> None:
    now = utc_now()
    with app_conn(path) as conn:
        row = conn.execute(
            "SELECT consecutive_failures FROM company_poll_state WHERE company_id = ?",
            (company_id,),
        ).fetchone()
        failures = int(row["consecutive_failures"] if row else 0) + 1
        delay = min(interval_seconds * (2 ** min(failures, 4)), 1800)
        conn.execute(
            """
            UPDATE company_poll_state
            SET next_poll_at = ?, lease_until = NULL, last_error = ?,
                consecutive_failures = ?, updated_at = ?
            WHERE company_id = ?
            """,
            (utc_iso(now + timedelta(seconds=delay)), message[:2000], failures, utc_iso(now), company_id),
        )
        conn.commit()


def enqueue_job(path: Path, *, pipeline_version: str, max_attempts: int, event: dict[str, Any]) -> bool:
    now = utc_iso()
    event_id = event["event_id"]
    job_id = hashlib.sha256(f"{pipeline_version}:{event_id}".encode()).hexdigest()
    with app_conn(path) as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO pipeline_jobs(
                id, event_id, canonical_event_id, pipeline_version, company_id,
                symbol, event_type, source_url, title, published_at,
                from_date, to_date, status, attempts, max_attempts,
                available_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0, ?, ?, ?, ?)
            """,
            (
                job_id, event_id, event_id, pipeline_version, event["company_id"],
                event["symbol"], event["event_type"], event["source_url"], event.get("title"),
                event["published_at"], event["from_date"], event["to_date"],
                max_attempts, now, now, now,
            ),
        )
        conn.commit()
        return cursor.rowcount > 0


def claim_job(path: Path, worker_id: str, lease_seconds: int) -> dict[str, Any] | None:
    now = utc_now()
    with app_conn(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT * FROM pipeline_jobs
            WHERE (
                    status = 'queued' AND datetime(available_at) <= datetime(?)
                  ) OR (
                    status = 'running' AND datetime(lease_until) <= datetime(?)
                  )
            ORDER BY datetime(available_at), created_at
            LIMIT 1
            """,
            (utc_iso(now), utc_iso(now)),
        ).fetchone()
        if row is None:
            conn.commit()
            return None
        conn.execute(
            """
            UPDATE pipeline_jobs
            SET status = 'running', attempts = attempts + 1, worker_id = ?,
                lease_until = ?, updated_at = ?
            WHERE id = ?
            """,
            (worker_id, utc_iso(now + timedelta(seconds=lease_seconds)), utc_iso(now), row["id"]),
        )
        conn.commit()
        claimed = dict(row)
        claimed["attempts"] = int(row["attempts"]) + 1
        claimed["worker_id"] = worker_id
        return claimed


def heartbeat_job(path: Path, job_id: str, worker_id: str, lease_seconds: int) -> None:
    now = utc_now()
    with app_conn(path) as conn:
        conn.execute(
            """
            UPDATE pipeline_jobs SET lease_until = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND worker_id = ?
            """,
            (utc_iso(now + timedelta(seconds=lease_seconds)), utc_iso(now), job_id, worker_id),
        )
        conn.commit()


def reserve_canonical_job(path: Path, job_id: str, canonical_event_id: str) -> bool:
    """Attach the resolved event while the job runs so the feed stays hidden."""
    with app_conn(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT pipeline_version FROM pipeline_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            conn.commit()
            raise LookupError(f"Pipeline job {job_id} no longer exists")
        duplicate = conn.execute(
            """
            SELECT id FROM pipeline_jobs
            WHERE canonical_event_id = ? AND pipeline_version = ? AND id <> ?
            """,
            (canonical_event_id, row["pipeline_version"], job_id),
        ).fetchone()
        if duplicate:
            conn.commit()
            return False
        conn.execute(
            "UPDATE pipeline_jobs SET canonical_event_id = ?, updated_at = ? WHERE id = ?",
            (canonical_event_id, utc_iso(), job_id),
        )
        conn.commit()
        return True


def complete_job(path: Path, job_id: str, canonical_event_id: str) -> None:
    now = utc_iso()
    with app_conn(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT pipeline_version FROM pipeline_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        duplicate = conn.execute(
            """
            SELECT id FROM pipeline_jobs
            WHERE canonical_event_id = ? AND pipeline_version = ? AND id <> ?
            """,
            (canonical_event_id, row["pipeline_version"], job_id),
        ).fetchone() if row else None
        if duplicate:
            conn.execute(
                """
                UPDATE pipeline_jobs SET status = 'succeeded', lease_until = NULL,
                    worker_id = NULL, last_error = ?, completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (f"Canonical duplicate of job {duplicate['id']}", now, now, job_id),
            )
        else:
            conn.execute(
                """
                UPDATE pipeline_jobs SET canonical_event_id = ?, status = 'succeeded',
                    lease_until = NULL, worker_id = NULL, last_error = NULL,
                    completed_at = ?, updated_at = ? WHERE id = ?
                """,
                (canonical_event_id, now, now, job_id),
            )
        conn.commit()


def _event_preference_column(event_type: str) -> str | None:
    normalized = event_type.strip().lower().replace("_", " ")
    if normalized in {"financial result", "financial results", "quarterly result"}:
        return "financial_results_enabled"
    if normalized == "investor presentation":
        return "investor_presentations_enabled"
    if normalized in {"earnings call transcript", "earnings call"}:
        return "earnings_calls_enabled"
    return None


def complete_job_and_enqueue_notifications(
    path: Path,
    job_id: str,
    canonical_event_id: str,
    *,
    max_attempts: int = 5,
) -> int:
    """Publish a job and snapshot eligible recipients in the same transaction."""
    now = utc_iso()
    queued = 0
    with app_conn(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        job = conn.execute("SELECT * FROM pipeline_jobs WHERE id = ?", (job_id,)).fetchone()
        duplicate = conn.execute(
            """
            SELECT id FROM pipeline_jobs
            WHERE canonical_event_id = ? AND pipeline_version = ? AND id <> ?
            """,
            (canonical_event_id, job["pipeline_version"], job_id),
        ).fetchone() if job else None
        if duplicate:
            conn.execute(
                """
                UPDATE pipeline_jobs SET status = 'succeeded', lease_until = NULL,
                    worker_id = NULL, last_error = ?, completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (f"Canonical duplicate of job {duplicate['id']}", now, now, job_id),
            )
            conn.commit()
            return 0
        if not job:
            conn.rollback()
            raise LookupError(f"Pipeline job {job_id} no longer exists")
        conn.execute(
            """
            UPDATE pipeline_jobs SET canonical_event_id = ?, status = 'succeeded',
                lease_until = NULL, worker_id = NULL, last_error = NULL,
                completed_at = ?, updated_at = ? WHERE id = ?
            """,
            (canonical_event_id, now, now, job_id),
        )
        preference_column = _event_preference_column(job["event_type"])
        if preference_column:
            watchers = conn.execute(
                f"""
                SELECT u.id AS user_id, u.email AS login_email,
                       COALESCE(NULLIF(np.notification_email, ''), u.email) AS recipient_email
                FROM watchlist_companies w
                JOIN users u ON u.id = w.user_id AND u.is_active = 1
                JOIN notification_preferences np ON np.user_id = u.id
                WHERE w.company_id = ? AND np.email_enabled = 1
                  AND np.{preference_column} = 1
                  AND (
                      LOWER(COALESCE(NULLIF(np.notification_email, ''), u.email)) = LOWER(u.email)
                      OR np.email_verified_at IS NOT NULL
                  )
                """,
                (job["company_id"],),
            ).fetchall()
            for watcher in watchers:
                raw_token = secrets.token_urlsafe(32)
                outbox_id = str(uuid.uuid4())
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO email_outbox(
                        id, message_kind, dedupe_key, user_id, recipient_email,
                        company_id, event_id, pipeline_job_id, action_token,
                        status, attempts, max_attempts, available_at, created_at, updated_at
                    ) VALUES (?, 'watchlist_update', ?, ?, ?, ?, ?, ?, ?,
                              'pending', 0, ?, ?, ?, ?)
                    """,
                    (
                        outbox_id, f"watchlist:{watcher['user_id']}:{canonical_event_id}",
                        watcher["user_id"], watcher["recipient_email"], job["company_id"],
                        canonical_event_id, job_id, raw_token, max_attempts, now, now, now,
                    ),
                )
                if cursor.rowcount:
                    conn.execute(
                        """
                        INSERT INTO notification_action_tokens(
                            id, token_hash, action, user_id, email, expires_at, created_at
                        ) VALUES (?, ?, 'unsubscribe', ?, ?, NULL, ?)
                        """,
                        (
                            str(uuid.uuid4()), hashlib.sha256(raw_token.encode()).hexdigest(),
                            watcher["user_id"], watcher["recipient_email"], now,
                        ),
                    )
                    queued += 1
        conn.commit()
    return queued


def claim_email(path: Path, worker_id: str, lease_seconds: int) -> dict[str, Any] | None:
    now = utc_now()
    with app_conn(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT * FROM email_outbox
            WHERE (status = 'pending' AND datetime(available_at) <= datetime(?))
               OR (status = 'sending' AND datetime(lease_until) <= datetime(?))
            ORDER BY datetime(available_at), created_at
            LIMIT 1
            """,
            (utc_iso(now), utc_iso(now)),
        ).fetchone()
        if row is None:
            conn.commit()
            return None
        conn.execute(
            """
            UPDATE email_outbox SET status = 'sending', attempts = attempts + 1,
                worker_id = ?, lease_until = ?, updated_at = ? WHERE id = ?
            """,
            (
                worker_id, utc_iso(now + timedelta(seconds=lease_seconds)),
                utc_iso(now), row["id"],
            ),
        )
        conn.commit()
        claimed = dict(row)
        claimed["attempts"] = int(row["attempts"]) + 1
        claimed["worker_id"] = worker_id
        return claimed


def email_delivery_allowed(path: Path, email: dict[str, Any]) -> tuple[bool, str | None]:
    with app_conn(path) as conn:
        user = conn.execute("SELECT is_active FROM users WHERE id = ?", (email["user_id"],)).fetchone()
        if not user or not user["is_active"]:
            return False, "User is inactive"
        if email["message_kind"] == "verify_email":
            if not email.get("action_token"):
                return False, "Verification token is missing"
            token = conn.execute(
                """
                SELECT used_at, expires_at FROM notification_action_tokens
                WHERE token_hash = ? AND action = 'verify_email'
                """,
                (hashlib.sha256(str(email["action_token"]).encode()).hexdigest(),),
            ).fetchone()
            if not token or token["used_at"] or (token["expires_at"] and token["expires_at"] <= utc_iso()):
                return False, "Verification token is no longer valid"
        if email["message_kind"] != "watchlist_update":
            return True, None
        pref = conn.execute(
            """
            SELECT np.*, u.email AS login_email
            FROM notification_preferences np JOIN users u ON u.id = np.user_id
            WHERE np.user_id = ?
            """,
            (email["user_id"],),
        ).fetchone()
        if not pref or not pref["email_enabled"]:
            return False, "Email notifications are disabled"
        destination = pref["notification_email"] or pref["login_email"]
        if destination.lower() != str(email["recipient_email"]).lower():
            return False, "Notification address changed"
        if destination.lower() != pref["login_email"].lower() and not pref["email_verified_at"]:
            return False, "Notification address is unverified"
        watched = conn.execute(
            "SELECT 1 FROM watchlist_companies WHERE user_id = ? AND company_id = ?",
            (email["user_id"], email["company_id"]),
        ).fetchone()
        if not watched:
            return False, "Company is no longer watched"
        job = conn.execute(
            "SELECT event_type FROM pipeline_jobs WHERE id = ?", (email["pipeline_job_id"],)
        ).fetchone()
        column = _event_preference_column(job["event_type"]) if job else None
        if not column or not pref[column]:
            return False, "This filing type is disabled"
    return True, None


def cancel_email(path: Path, email_id: str, reason: str) -> None:
    with app_conn(path) as conn:
        conn.execute(
            """
            UPDATE email_outbox SET status = 'cancelled', lease_until = NULL,
                worker_id = NULL, last_error = ?, action_token = NULL, updated_at = ?
            WHERE id = ?
            """,
            (reason[:2000], utc_iso(), email_id),
        )
        conn.commit()


def complete_email(path: Path, email_id: str, provider_message_id: str | None) -> None:
    now = utc_iso()
    with app_conn(path) as conn:
        conn.execute(
            """
            UPDATE email_outbox SET status = 'sent', lease_until = NULL, worker_id = NULL,
                provider_message_id = ?, last_error = NULL, action_token = NULL,
                sent_at = ?, updated_at = ? WHERE id = ?
            """,
            (provider_message_id, now, now, email_id),
        )
        conn.commit()


def fail_email(path: Path, email: dict[str, Any], message: str, *, permanent: bool = False) -> None:
    now = utc_now()
    exhausted = permanent or int(email["attempts"]) >= int(email["max_attempts"])
    delay = min(30 * (2 ** max(int(email["attempts"]) - 1, 0)), 1800)
    with app_conn(path) as conn:
        conn.execute(
            """
            UPDATE email_outbox SET status = ?, available_at = ?, lease_until = NULL,
                worker_id = NULL, last_error = ?, updated_at = ? WHERE id = ?
            """,
            (
                "failed" if exhausted else "pending",
                utc_iso(now if exhausted else now + timedelta(seconds=delay)),
                message[:4000], utc_iso(now), email["id"],
            ),
        )
        conn.commit()


def email_counts(path: Path) -> dict[str, int]:
    counts = {"pending": 0, "sending": 0, "sent": 0, "failed": 0, "cancelled": 0}
    with app_conn(path) as conn:
        for row in conn.execute("SELECT status, COUNT(*) count FROM email_outbox GROUP BY status"):
            counts[row["status"]] = row["count"]
    return counts


def fail_job(path: Path, job: dict[str, Any], message: str) -> None:
    now = utc_now()
    exhausted = int(job["attempts"]) >= int(job["max_attempts"])
    delay = min(30 * (2 ** max(int(job["attempts"]) - 1, 0)), 1800)
    with app_conn(path) as conn:
        conn.execute(
            """
            UPDATE pipeline_jobs SET status = ?, available_at = ?, lease_until = NULL,
                worker_id = NULL, last_error = ?, updated_at = ? WHERE id = ?
            """,
            (
                "failed" if exhausted else "queued",
                utc_iso(now if exhausted else now + timedelta(seconds=delay)),
                message[:4000], utc_iso(now), job["id"],
            ),
        )
        conn.commit()


def job_counts(path: Path) -> dict[str, int]:
    counts = {"queued": 0, "running": 0, "succeeded": 0, "failed": 0}
    with app_conn(path) as conn:
        for row in conn.execute("SELECT status, COUNT(*) count FROM pipeline_jobs GROUP BY status"):
            counts[row["status"]] = row["count"]
    return counts
