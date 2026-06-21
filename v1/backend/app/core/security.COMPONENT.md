# core/security

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Password hashing (bcrypt) and JWT encode / decode helpers.

## Source

- Path: `backend/app/core/security.py`
- Layer: backend-security

## Contract

- Exports:
  - `hash_password(password) -> str`
  - `verify_password(plain, hashed) -> bool`
  - `create_access_token(subject, extra=None) -> str`
  - `decode_token(token) -> dict[str, Any] | None`

## Dependencies

- Imports: `datetime`, `python-jose` (`jwt`, `JWTError`), `passlib.context.CryptContext`, `app.core.config.settings`.

## Patterns (symmetry)

- `pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")` is the single hashing primitive. Do not use `bcrypt` directly elsewhere.
- `create_access_token` sets `sub` (string) and `exp` (UTC). `extra` is merged in — used by the auth router to add `email` and `type`.
- `decode_token` swallows `JWTError` and returns `None`; `get_current_user` translates that to a 401.
- Token lifetime uses `settings.JWT_EXPIRE_MINUTES`. Default is 7 days for dev convenience.

## Verification checklist

- [ ] All password ops route through `pwd_context`
- [ ] `sub` is stringified user id
- [ ] `decode_token` returns `None` on failure (does not raise)
- [ ] No hardcoded secret — always `settings.JWT_SECRET`
