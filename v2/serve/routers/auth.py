"""Auth router — in-memory users with JWT bearer tokens."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import create_access_token, get_current_user
from ..schemas import LoginRequest, SignupRequest
from ..state import User, store

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(user: User) -> dict:
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user_id": user.user_id,
        "email": user.email,
        "user_type": user.user_type,
        "full_name": user.full_name,
    }


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest) -> dict:
    if body.email in store.users:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")
    user = store.create_user(body.email, body.password, body.full_name)
    return _token_response(user)


@router.post("/login")
def login(body: LoginRequest) -> dict:
    user = store.verify(body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return _token_response(user)


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return {
        "user_id": user.user_id,
        "email": user.email,
        "full_name": user.full_name,
        "user_type": user.user_type,
    }
