"""Login, logout, current-user, and password-change endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from app_db import get_app_conn, utc_iso
from auth_models import ChangePasswordRequest, LoginRequest, UserResponse
from security import (
    CurrentUser,
    api_error,
    clear_session_cookie,
    create_session,
    get_authenticated_user,
    normalize_email,
    session_token,
    set_session_cookie,
    token_digest,
    user_from_row,
    user_payload,
    verify_password,
    verify_unknown_password,
    hash_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserResponse)
def login(body: LoginRequest, response: Response):
    email = normalize_email(str(body.email))
    with get_app_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,)
        ).fetchone()
        if not row:
            verify_unknown_password(body.password)
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "invalid_credentials",
                "Invalid email or password.",
            )
        if not verify_password(body.password, row["password_hash"]):
            raise api_error(
                status.HTTP_401_UNAUTHORIZED,
                "invalid_credentials",
                "Invalid email or password.",
            )
        if not row["is_active"]:
            raise api_error(
                status.HTTP_403_FORBIDDEN,
                "inactive_account",
                "This account is inactive.",
            )
        now = utc_iso()
        conn.execute("UPDATE users SET last_login_at = ? WHERE id = ?", (now, row["id"]))
        token = create_session(conn, row["id"])
        conn.commit()
        refreshed = conn.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone()
    set_session_cookie(response, token)
    return user_payload(refreshed)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    _: CurrentUser = Depends(get_authenticated_user),
):
    token = session_token(request)
    if token:
        with get_app_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_digest(token),))
            conn.commit()
    clear_session_cookie(response)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=response.headers)


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser = Depends(get_authenticated_user)):
    return user_payload(user)


@router.post("/change-password", response_model=UserResponse)
def change_password(
    body: ChangePasswordRequest,
    response: Response,
    user: CurrentUser = Depends(get_authenticated_user),
):
    with get_app_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user.id,)).fetchone()
        if not row or not verify_password(body.current_password, row["password_hash"]):
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "invalid_current_password",
                "The current password is incorrect.",
            )
        if verify_password(body.new_password, row["password_hash"]):
            raise api_error(
                status.HTTP_400_BAD_REQUEST,
                "password_reuse",
                "The new password must be different from the current password.",
            )
        now = utc_iso()
        conn.execute(
            """
            UPDATE users
            SET password_hash = ?, must_change_password = 0, updated_at = ?
            WHERE id = ?
            """,
            (hash_password(body.new_password), now, user.id),
        )
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user.id,))
        new_token = create_session(conn, user.id)
        conn.commit()
        refreshed = conn.execute("SELECT * FROM users WHERE id = ?", (user.id,)).fetchone()
    set_session_cookie(response, new_token)
    return user_payload(user_from_row(refreshed))
