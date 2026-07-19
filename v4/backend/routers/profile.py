"""Self-service profile and email-notification preferences."""

from __future__ import annotations

import secrets
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import RedirectResponse

from app_db import get_app_conn, utc_iso
from config import settings
from notifications import create_action_token, queue_email, token_digest
from profile_models import ProfileResponse, UpdateProfileRequest
from security import CurrentUser, api_error, normalize_email, require_ready_user

router = APIRouter(tags=["profile"])
def _profile_payload(user: CurrentUser, row) -> dict:
    login_email = user.email if isinstance(user, CurrentUser) else user["email"]
    full_name = user.full_name if isinstance(user, CurrentUser) else user["full_name"]
    destination = normalize_email(row["notification_email"] if row and row["notification_email"] else login_email)
    verified = destination == normalize_email(login_email) or bool(row and row["email_verified_at"])
    return {
        "full_name": full_name,
        "login_email": login_email,
        "notification_email": destination,
        "email_enabled": bool(row and row["email_enabled"]),
        "email_verified": verified,
        "verification_required": destination != normalize_email(login_email) and not verified,
        "financial_results_enabled": bool(row["financial_results_enabled"]) if row else True,
        "investor_presentations_enabled": bool(row["investor_presentations_enabled"]) if row else True,
        "earnings_calls_enabled": bool(row["earnings_calls_enabled"]) if row else True,
    }


@router.get("/profile", response_model=ProfileResponse)
def get_profile(user: CurrentUser = Depends(require_ready_user)):
    with get_app_conn() as conn:
        row = conn.execute(
            "SELECT * FROM notification_preferences WHERE user_id = ?", (user.id,)
        ).fetchone()
    return _profile_payload(user, row)


@router.patch("/profile", response_model=ProfileResponse)
def update_profile(body: UpdateProfileRequest, user: CurrentUser = Depends(require_ready_user)):
    destination = normalize_email(str(body.notification_email))
    full_name = body.full_name.strip() if body.full_name and body.full_name.strip() else None
    now = utc_iso()
    with get_app_conn() as conn:
        previous = conn.execute(
            "SELECT * FROM notification_preferences WHERE user_id = ?", (user.id,)
        ).fetchone()
        previous_email = normalize_email(previous["notification_email"]) if previous and previous["notification_email"] else normalize_email(user.email)
        changed = destination != previous_email
        trusted_login = destination == normalize_email(user.email)
        verified_at = now if trusted_login else (None if changed else (previous["email_verified_at"] if previous else None))
        conn.execute(
            "UPDATE users SET full_name = ?, updated_at = ? WHERE id = ?",
            (full_name, now, user.id),
        )
        conn.execute(
            """
            INSERT INTO notification_preferences(
                user_id, notification_email, email_verified_at, email_enabled,
                financial_results_enabled, investor_presentations_enabled,
                earnings_calls_enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                notification_email = excluded.notification_email,
                email_verified_at = excluded.email_verified_at,
                email_enabled = excluded.email_enabled,
                financial_results_enabled = excluded.financial_results_enabled,
                investor_presentations_enabled = excluded.investor_presentations_enabled,
                earnings_calls_enabled = excluded.earnings_calls_enabled,
                updated_at = excluded.updated_at
            """,
            (
                user.id, destination, verified_at, int(body.email_enabled),
                int(body.financial_results_enabled), int(body.investor_presentations_enabled),
                int(body.earnings_calls_enabled), now, now,
            ),
        )
        needs_verification_email = not trusted_login and (changed or not verified_at)
        if changed or needs_verification_email:
            conn.execute(
                """
                UPDATE notification_action_tokens SET used_at = ?
                WHERE user_id = ? AND action = 'verify_email' AND used_at IS NULL
                """,
                (now, user.id),
            )
            conn.execute(
                """
                UPDATE email_outbox SET status = 'cancelled', last_error = ?,
                    action_token = NULL, updated_at = ?
                WHERE user_id = ? AND message_kind = 'verify_email'
                  AND status IN ('pending', 'sending')
                """,
                ("Superseded by a newer verification request", now, user.id),
            )
        if needs_verification_email:
            token = create_action_token(
                conn, action="verify_email", user_id=user.id, email=destination, expires_hours=24
            )
            queue_email(
                conn,
                kind="verify_email",
                dedupe_key=f"verify:{user.id}:{destination}:{secrets.token_hex(8)}",
                user_id=user.id,
                recipient_email=destination,
                action_token=token,
            )
        conn.commit()
        refreshed_user = conn.execute("SELECT * FROM users WHERE id = ?", (user.id,)).fetchone()
        refreshed_pref = conn.execute(
            "SELECT * FROM notification_preferences WHERE user_id = ?", (user.id,)
        ).fetchone()
    return _profile_payload(refreshed_user, refreshed_pref)


@router.post("/profile/test-email", status_code=status.HTTP_202_ACCEPTED)
def send_test_email(user: CurrentUser = Depends(require_ready_user)):
    with get_app_conn() as conn:
        row = conn.execute(
            "SELECT * FROM notification_preferences WHERE user_id = ?", (user.id,)
        ).fetchone()
        destination = normalize_email(row["notification_email"] if row and row["notification_email"] else user.email)
        verified = destination == normalize_email(user.email) or bool(row and row["email_verified_at"])
        if not verified:
            raise api_error(status.HTTP_409_CONFLICT, "email_not_verified", "Verify this notification email before sending a test.")
        queue_email(
            conn, kind="test_email", dedupe_key=f"test:{user.id}:{secrets.token_hex(12)}",
            user_id=user.id, recipient_email=destination,
        )
        conn.commit()
    return {"queued": True, "recipient_email": destination}


def _redirect(result: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.public_app_url}/notifications/{result}", status_code=303)


@router.get("/notifications/verify")
def verify_notification_email(token: str = Query(min_length=20, max_length=256)):
    now = utc_iso()
    with get_app_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT * FROM notification_action_tokens
            WHERE token_hash = ? AND action = 'verify_email' AND used_at IS NULL
            """,
            (token_digest(token),),
        ).fetchone()
        if not row or (row["expires_at"] and row["expires_at"] <= now):
            conn.commit()
            return _redirect("verification-expired")
        pref = conn.execute(
            "SELECT notification_email FROM notification_preferences WHERE user_id = ?",
            (row["user_id"],),
        ).fetchone()
        if not pref or normalize_email(pref["notification_email"]) != normalize_email(row["email"]):
            conn.execute("UPDATE notification_action_tokens SET used_at = ? WHERE id = ?", (now, row["id"]))
            conn.commit()
            return _redirect("verification-expired")
        conn.execute(
            "UPDATE notification_preferences SET email_verified_at = ?, updated_at = ? WHERE user_id = ?",
            (now, now, row["user_id"]),
        )
        conn.execute("UPDATE notification_action_tokens SET used_at = ? WHERE id = ?", (now, row["id"]))
        conn.commit()
    return _redirect("verified")


@router.get("/notifications/unsubscribe")
def unsubscribe(token: str = Query(min_length=20, max_length=256)):
    now = utc_iso()
    with get_app_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT * FROM notification_action_tokens
            WHERE token_hash = ? AND action = 'unsubscribe' AND used_at IS NULL
            """,
            (token_digest(token),),
        ).fetchone()
        if not row:
            conn.commit()
            return _redirect("unsubscribe-expired")
        conn.execute(
            "UPDATE notification_preferences SET email_enabled = 0, updated_at = ? WHERE user_id = ?",
            (now, row["user_id"]),
        )
        conn.execute("UPDATE notification_action_tokens SET used_at = ? WHERE id = ?", (now, row["id"]))
        conn.commit()
    return _redirect("unsubscribed")
