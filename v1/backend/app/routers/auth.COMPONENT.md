# routers/auth

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Sign-up, sign-in, and "current user" endpoints.

## Source

- Path: `backend/app/routers/auth.py`
- Prefix: `/auth`
- Tags: `["auth"]`
- Layer: backend-router

## Endpoints

- `POST /auth/signup` (201) — body `SignupRequest`, response `TokenResponse`. Creates an `AppUser` + default `Watchlist`. Fails 400 on duplicate email.
- `POST /auth/login` — body `LoginRequest`, response `TokenResponse`. Fails 401 on bad credentials.
- `GET /auth/me` — requires auth, response `UserResponse` (uses `from_attributes = True`).

## Dependencies

- Imports: `fastapi`, `sqlalchemy.select`, `app.core.deps` (`get_current_user`, `get_db`), `app.core.security` (`create_access_token`, `hash_password`, `verify_password`), `app.db.enums.UserType`, `app.models.user` (`AppUser`, `Watchlist`), `app.schemas.auth`.

## Patterns (symmetry)

- Token issuance goes through the local `_issue_token(user)` helper. Do not inline JWT creation in routes.
- New signups always create a `Watchlist(user_id=user.user_id, watchlist_name="Default Watchlist")` — match this if you add a sign-up alternate path.
- Login error message is intentionally generic ("Invalid email or password.") — preserve to avoid leaking which field was wrong.

## Verification checklist

- [ ] `_issue_token` used by every code path
- [ ] Default watchlist created on signup
- [ ] Duplicate email returns 400, not 409 (consistent with existing client handling)
- [ ] `UserResponse.model_validate(user)` used for `/auth/me`
