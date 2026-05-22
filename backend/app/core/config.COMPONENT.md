# core/config

> Inherits: [./_BASE.md](./_BASE.md)

## Purpose

Typed application settings loaded from `.env` via `pydantic-settings`.

## Source

- Path: `backend/app/core/config.py`
- Layer: backend-config

## Contract

- `class Settings(BaseSettings)` with fields: `DATABASE_URL`, `JWT_SECRET`,
  `JWT_ALGORITHM`, `JWT_EXPIRE_MINUTES`, `CORS_ORIGINS`, `APP_ENV`,
  `LLM_PROVIDER`, `LLM_MODEL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, plus
  ingestion/worker tunables (`STORAGE_DIR`, `WORKER_*`, `AUTO_PUBLISH_CONFIDENCE`).
- Property `cors_origins_list -> list[str]` splits the comma-separated `CORS_ORIGINS` env value.
- `get_settings()` and module-level `settings` singleton (cached via `@lru_cache`).

## Dependencies

- Imports: `functools.lru_cache`, `pydantic_settings`.

## Patterns (symmetry)

- Defaults are dev-friendly but `JWT_SECRET` must be overridden in production. `.env.example` lists the expected keys.
- `model_config = SettingsConfigDict(env_file=".env", extra="ignore")` silently ignores unknown env vars — intentional so deployment platforms can inject extras without breaking startup.
- Read settings via the module-level `settings` (`from app.core.config import settings`). Avoid instantiating `Settings()` directly.

## Verification checklist

- [ ] New env var added to `Settings` + `.env.example`
- [ ] Settings access uses the cached `settings` singleton
- [ ] `cors_origins_list` returns the list form (no comma string consumers)
