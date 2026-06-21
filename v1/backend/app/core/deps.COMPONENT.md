# core/deps

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

FastAPI dependency callables for database sessions and authenticated users.

## Source

- Path: `backend/app/core/deps.py`
- Layer: backend-dependency-injection

## Contract

- Exports:
  - `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)`
  - `get_db() -> Generator[Session, None, None]`
  - `get_current_user(token, db) -> AppUser` — raises 401 on missing / invalid token / missing user.
  - `get_current_admin(user) -> AppUser` — raises 403 unless `user.user_type == UserType.ADMIN`.

## Dependencies

- Imports: `fastapi`, `fastapi.security`, `sqlalchemy.orm.Session`, `app.core.security` (`decode_token`), `app.db.enums.UserType`, `app.db.session.SessionLocal`, `app.models.user.AppUser`.

## Patterns (symmetry)

- All routers depend on these helpers — they are the only way to obtain a session or authenticated user.
- `OAuth2PasswordBearer.auto_error=False` so `get_current_user` controls the 401 message and treats "no token" the same as "bad token".
- Token payload contract: `payload["sub"]` is the user id as a string. Keep this aligned with `create_access_token` in [`security.py`](security.py).
- `get_current_admin` chains off `get_current_user` — never duplicate the JWT decode logic.

## Verification checklist

- [ ] Routers import `get_db`, `get_current_user`, `get_current_admin` from this module
- [ ] Missing / invalid token raises 401 with a clear `detail`
- [ ] Admin gating uses `UserType.ADMIN` (enum, not string)
- [ ] `SessionLocal` is closed in the `finally` block
