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
  `LLM_PROVIDER`, `LLM_MODEL`, `LLM_MODEL_FAST`, `LLM_SEED`,
  `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
  `IR_AGENT_MODEL`, `IR_AGENT_CONCURRENCY`, `IR_AGENT_RUNS_DIR`, plus
  ingestion/worker tunables (`STORAGE_DIR`, `WORKER_*`, `AUTO_PUBLISH_CONFIDENCE`).
- `LLM_MODEL` is the premium-tier model used for `FINANCIAL_RESULT`
  documents. `LLM_MODEL_FAST` is an optional cheap-tier model used for
  transcripts / press releases / presentations / annual reports — see
  `services/pipeline/llm.select_extraction_model`. Leave `LLM_MODEL_FAST`
  unset (or empty string) to route every document type through `LLM_MODEL`.
- Property `cors_origins_list -> list[str]` splits the comma-separated `CORS_ORIGINS` env value.
- Property `storage_path -> Path` resolves `STORAGE_DIR` against `cwd`.
- Property `ir_agent_runs_path -> Path` resolves `IR_AGENT_RUNS_DIR` against `cwd`.
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
