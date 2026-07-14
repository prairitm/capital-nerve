"""Password, session, and role-based authorization helpers."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import timedelta

from email_validator import EmailNotValidError, validate_email
from fastapi import Depends, HTTPException, Request, Response, status
from pwdlib import PasswordHash

from app_db import get_app_conn, utc_iso, utc_now
from config import settings

SESSION_COOKIE = "cn_session"
PASSWORD_MIN_LENGTH = 12
password_hash = PasswordHash.recommended()
_DUMMY_HASH = password_hash.hash("capital-nerve-dummy-password")


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    full_name: str | None
    role: str
    is_active: bool
    must_change_password: bool
    created_at: str
    updated_at: str
    last_login_at: str | None


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def normalize_email(email: str) -> str:
    return email.strip().lower()


def user_from_row(row: sqlite3.Row) -> CurrentUser:
    return CurrentUser(
        id=row["id"],
        email=row["email"],
        full_name=row["full_name"],
        role=row["role"],
        is_active=bool(row["is_active"]),
        must_change_password=bool(row["must_change_password"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_login_at=row["last_login_at"],
    )


def user_payload(user: CurrentUser | sqlite3.Row) -> dict:
    value = user if isinstance(user, CurrentUser) else user_from_row(user)
    return {
        "id": value.id,
        "email": value.email,
        "full_name": value.full_name,
        "role": value.role,
        "is_active": value.is_active,
        "must_change_password": value.must_change_password,
        "created_at": value.created_at,
        "updated_at": value.updated_at,
        "last_login_at": value.last_login_at,
    }


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        return password_hash.verify(password, stored_hash)
    except Exception:
        return False


def verify_unknown_password(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def generate_temporary_password() -> str:
    # token_urlsafe(18) produces at least 24 high-entropy characters.
    return secrets.token_urlsafe(18)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(conn: sqlite3.Connection, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = utc_now()
    conn.execute(
        "INSERT INTO sessions(token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (
            token_digest(token),
            user_id,
            utc_iso(now),
            utc_iso(now + timedelta(hours=settings.session_ttl_hours)),
        ),
    )
    return token


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_hours * 60 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def session_token(request: Request) -> str | None:
    return request.cookies.get(SESSION_COOKIE)


def get_authenticated_user(request: Request) -> CurrentUser:
    token = session_token(request)
    if not token:
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "not_authenticated",
            "Authentication is required.",
        )
    digest = token_digest(token)
    with get_app_conn() as conn:
        row = conn.execute(
            """
            SELECT u.*, s.expires_at AS session_expires_at
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ?
            """,
            (digest,),
        ).fetchone()
        if not row or row["session_expires_at"] <= utc_iso():
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (digest,))
            conn.commit()
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "not_authenticated",
                "The session is invalid or has expired.",
            )
        if not row["is_active"]:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (row["id"],))
            conn.commit()
            raise api_error(
                status.HTTP_403_FORBIDDEN,
                "inactive_account",
                "This account is inactive.",
            )
        return user_from_row(row)


def require_ready_user(
    user: CurrentUser = Depends(get_authenticated_user),
) -> CurrentUser:
    if user.must_change_password:
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "password_change_required",
            "Change the temporary password before continuing.",
        )
    return user


def require_admin(user: CurrentUser = Depends(require_ready_user)) -> CurrentUser:
    if user.role != "ADMIN":
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "forbidden",
            "Administrator access is required.",
        )
    return user


def bootstrap_admin() -> None:
    email = settings.admin_email
    password = settings.admin_password
    if not email and not password:
        return
    if not email or not password:
        raise RuntimeError("V4_ADMIN_EMAIL and V4_ADMIN_PASSWORD must be set together")
    if len(password) < PASSWORD_MIN_LENGTH:
        raise RuntimeError(
            f"V4_ADMIN_PASSWORD must contain at least {PASSWORD_MIN_LENGTH} characters"
        )
    try:
        normalized = normalize_email(
            validate_email(email, check_deliverability=False).normalized
        )
    except EmailNotValidError as exc:
        raise RuntimeError("V4_ADMIN_EMAIL must be a valid email address") from exc
    with get_app_conn() as conn:
        existing = conn.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE", (normalized,)
        ).fetchone()
        if existing:
            if existing["role"] != "ADMIN":
                raise RuntimeError(
                    "V4_ADMIN_EMAIL belongs to a non-admin account; refusing to promote it implicitly"
                )
            return
        now = utc_iso()
        conn.execute(
            """
            INSERT INTO users(
                id, email, full_name, password_hash, role, is_active,
                must_change_password, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'ADMIN', 1, 0, ?, ?)
            """,
            (str(uuid.uuid4()), normalized, "Administrator", hash_password(password), now, now),
        )
        conn.commit()
