"""Durable notification outbox helpers used by the web API."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from datetime import timedelta

from app_db import utc_iso, utc_now


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_action_token(
    conn: sqlite3.Connection,
    *,
    action: str,
    user_id: str,
    email: str | None = None,
    expires_hours: int | None = None,
) -> str:
    token = secrets.token_urlsafe(32)
    now = utc_now()
    conn.execute(
        """
        INSERT INTO notification_action_tokens(
            id, token_hash, action, user_id, email, expires_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()), token_digest(token), action, user_id, email,
            utc_iso(now + timedelta(hours=expires_hours)) if expires_hours else None,
            utc_iso(now),
        ),
    )
    return token


def queue_email(
    conn: sqlite3.Connection,
    *,
    kind: str,
    dedupe_key: str,
    user_id: str,
    recipient_email: str,
    action_token: str | None = None,
    max_attempts: int = 5,
) -> bool:
    now = utc_iso()
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO email_outbox(
            id, message_kind, dedupe_key, user_id, recipient_email, action_token,
            status, attempts, max_attempts, available_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()), kind, dedupe_key, user_id, recipient_email,
            action_token, max_attempts, now, now, now,
        ),
    )
    return cursor.rowcount > 0
