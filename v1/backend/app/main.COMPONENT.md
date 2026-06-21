# main

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

FastAPI application factory and composition root. Registers CORS, the `/health` probe, and every router.

## Source

- Path: `backend/app/main.py`
- Layer: backend-bootstrap

## Contract

- `create_app() -> FastAPI` builds the app.
- Module-level `app = create_app()` is the ASGI target used by uvicorn (`app.main:app`).

## Dependencies

- Imports: `fastapi`, `fastapi.middleware.cors`, `app.core.config.settings`, every router module under `app.routers`.
- Must not: introduce routing logic here — endpoints live in their routers.

## Patterns (symmetry)

- CORS uses `settings.cors_origins_list` (comma-separated `CORS_ORIGINS` env var). Headers and methods are wildcarded.
- The `/health` endpoint returns `{"status": "ok"}` — keep this for orchestration checks.
- Routers are registered in alphabetical order of their domain to make additions reviewable; preserve the order when adding new routers.
- Title / version metadata appears in OpenAPI; update on a real release.

## Verification checklist

- [ ] New router added with `app.include_router(...)`
- [ ] CORS origins still come from `settings.cors_origins_list`
- [ ] `/health` endpoint unchanged
- [ ] No business logic in the factory
