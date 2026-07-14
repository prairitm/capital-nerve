"""Administrator-only user lifecycle endpoints."""

from __future__ import annotations

import sqlite3
import uuid

from fastapi import APIRouter, Depends, Query, status

from app_db import get_app_conn, utc_iso
from auth_models import (
    CreateUserRequest,
    TemporaryCredentialResponse,
    UpdateUserRequest,
    UserResponse,
)
from security import (
    CurrentUser,
    api_error,
    generate_temporary_password,
    hash_password,
    normalize_email,
    require_admin,
    user_payload,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _get_user(conn: sqlite3.Connection, user_id: str):
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        raise api_error(status.HTTP_404_NOT_FOUND, "user_not_found", "User not found.")
    return row


def _raise_duplicate_email() -> None:
    raise api_error(
        status.HTTP_409_CONFLICT,
        "duplicate_email",
        "An account with this email already exists.",
    )


@router.get("/users", response_model=list[UserResponse])
def list_users(
    search: str = "",
    limit: int = Query(default=200, ge=1, le=1000),
    _: CurrentUser = Depends(require_admin),
):
    with get_app_conn() as conn:
        if search.strip():
            like = f"%{search.strip()}%"
            rows = conn.execute(
                """
                SELECT * FROM users
                WHERE email LIKE ? COLLATE NOCASE OR full_name LIKE ? COLLATE NOCASE
                ORDER BY is_active DESC, full_name COLLATE NOCASE, email COLLATE NOCASE
                LIMIT ?
                """,
                (like, like, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM users
                ORDER BY is_active DESC, full_name COLLATE NOCASE, email COLLATE NOCASE
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [user_payload(row) for row in rows]


@router.post(
    "/users",
    response_model=TemporaryCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(body: CreateUserRequest, _: CurrentUser = Depends(require_admin)):
    temporary_password = generate_temporary_password()
    now = utc_iso()
    user_id = str(uuid.uuid4())
    try:
        with get_app_conn() as conn:
            conn.execute(
                """
                INSERT INTO users(
                    id, email, full_name, password_hash, role, is_active,
                    must_change_password, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?)
                """,
                (
                    user_id,
                    normalize_email(str(body.email)),
                    body.full_name.strip() if body.full_name and body.full_name.strip() else None,
                    hash_password(temporary_password),
                    body.role,
                    now,
                    now,
                ),
            )
            conn.commit()
            row = _get_user(conn, user_id)
    except sqlite3.IntegrityError as exc:
        if "email" in str(exc).lower() or "unique" in str(exc).lower():
            _raise_duplicate_email()
        raise
    return {"user": user_payload(row), "temporary_password": temporary_password}


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    body: UpdateUserRequest,
    admin: CurrentUser = Depends(require_admin),
):
    with get_app_conn() as conn:
        target = _get_user(conn, user_id)
        fields = body.model_fields_set
        next_role = body.role if "role" in fields and body.role is not None else target["role"]
        next_active = (
            body.is_active
            if "is_active" in fields and body.is_active is not None
            else bool(target["is_active"])
        )
        if user_id == admin.id and (next_role != "ADMIN" or not next_active):
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "self_admin_change",
                "You cannot demote or deactivate your own account.",
            )
        if target["role"] == "ADMIN" and target["is_active"] and (
            next_role != "ADMIN" or not next_active
        ):
            active_admins = conn.execute(
                "SELECT COUNT(*) AS count FROM users WHERE role = 'ADMIN' AND is_active = 1"
            ).fetchone()["count"]
            if active_admins <= 1:
                raise api_error(
                    status.HTTP_409_CONFLICT,
                    "final_admin",
                    "The final active administrator cannot be demoted or deactivated.",
                )

        email = (
            normalize_email(str(body.email))
            if "email" in fields and body.email is not None
            else target["email"]
        )
        full_name = (
            body.full_name.strip() if body.full_name and body.full_name.strip() else None
        ) if "full_name" in fields else target["full_name"]
        try:
            conn.execute(
                """
                UPDATE users
                SET email = ?, full_name = ?, role = ?, is_active = ?, updated_at = ?
                WHERE id = ?
                """,
                (email, full_name, next_role, int(next_active), utc_iso(), user_id),
            )
            if not next_active:
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            conn.commit()
        except sqlite3.IntegrityError as exc:
            if "email" in str(exc).lower() or "unique" in str(exc).lower():
                _raise_duplicate_email()
            raise
        return user_payload(_get_user(conn, user_id))


@router.post("/users/{user_id}/reset-password", response_model=TemporaryCredentialResponse)
def reset_password(user_id: str, admin: CurrentUser = Depends(require_admin)):
    if user_id == admin.id:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "self_password_reset",
            "Use Change password to update your own password.",
        )
    temporary_password = generate_temporary_password()
    with get_app_conn() as conn:
        _get_user(conn, user_id)
        conn.execute(
            """
            UPDATE users
            SET password_hash = ?, must_change_password = 1, updated_at = ?
            WHERE id = ?
            """,
            (hash_password(temporary_password), utc_iso(), user_id),
        )
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()
        row = _get_user(conn, user_id)
    return {"user": user_payload(row), "temporary_password": temporary_password}
