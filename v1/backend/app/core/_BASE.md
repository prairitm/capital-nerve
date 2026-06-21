# `backend/app/core/` baseline

> Inherits: [../_BASE.md](../_BASE.md)

Cross-cutting concerns: configuration, security primitives, dependency-injection wiring.

## Modules

- [`config.py`](config.py) — `Settings(BaseSettings)` loaded from `.env`. Exposes a module-level `settings` singleton via `@lru_cache`.
- [`security.py`](security.py) — bcrypt password hashing and JWT encode/decode using `python-jose`.
- [`deps.py`](deps.py) — `get_db`, `get_current_user`, `get_current_admin`, and the `OAuth2PasswordBearer` scheme.

## Rules

- All FastAPI `Depends(...)` building blocks live here. Routers must not declare their own session-management dependency.
- Settings access is via the `settings` singleton (`from app.core.config import settings`). Do not call `Settings()` directly elsewhere.
- Tokens use HS256 and the secret comes from `settings.JWT_SECRET`; never inline the key.
- `decode_token` returns `None` on failure so `get_current_user` can translate that to a 401 — preserve this contract.
- Adding a new dependency (e.g. rate limiting, feature flags) goes here, exported as `Depends(...)` factories.
