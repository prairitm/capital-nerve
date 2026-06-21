"""Shared FastAPI dependencies: JWT auth and the catalog handle."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from .builder import Catalog, get_catalog
from .config import settings
from .state import User, store

_bearer = HTTPBearer(auto_error=False)


def create_access_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(user.user_id), "email": user.email, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    if creds is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(
            creds.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = store.users_by_id.get(int(payload.get("sub", 0)))
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user


def catalog_dep() -> Catalog:
    return get_catalog()
