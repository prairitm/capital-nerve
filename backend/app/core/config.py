from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve backend/.env from this file's location so Settings loads correctly
# even when the process cwd is the repo root (e.g. root-level .venv).
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _BACKEND_ROOT / ".env"

# Environment values that trigger production-grade safety checks. Anything
# else (dev / test / staging) is treated as non-production.
_PRODUCTION_ENV_VALUES = {"production", "prod"}

# Tokens that obviously indicate a placeholder JWT secret. Production refuses
# to boot if any of these substrings appear in `JWT_SECRET`.
_WEAK_JWT_SECRET_MARKERS = ("dev-secret", "change-me", "placeholder", "example")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.is_file() else ".env",
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql+psycopg://capitalnerve:capitalnerve@db:5432/capitalnerve"
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7
    CORS_ORIGINS: str = "http://localhost:5173"
    APP_ENV: str = "dev"

    # --- Ingestion pipeline ---
    # Where uploaded source documents live. Relative paths resolve against the
    # backend working directory so `var/storage/<hash>.pdf` survives reloads
    # without touching project code.
    STORAGE_DIR: str = "var/storage"

    # Which LLM provider drives structured extraction. `mock` is a deterministic
    # regex-based fallback that works without any API key. It is intentionally
    # the default for local development; production startup refuses to run it
    # (see `assert_production_ready`).
    LLM_PROVIDER: str = "mock"  # one of: "mock", "anthropic", "openai"
    LLM_MODEL: str = "claude-sonnet-4-5-20250929"
    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None

    # --- IR discovery agent (used by `python -m app.scripts.bulk_ingest`) ---
    # The OpenAI Agents SDK + WebSearchTool model that the bulk ingestor uses
    # to locate quarterly result / concall transcript / presentation PDFs for
    # a given (Company, FinancialPeriod) pair. `OPENAI_API_KEY` above doubles
    # as the auth token for this agent — there is no separate key.
    IR_AGENT_MODEL: str = "gpt-5.5"
    # How many concurrent agent calls the CLI may run by default. Each agent
    # call issues several web searches plus a structured-output completion,
    # so going above ~8 hits OpenAI rate limits on standard tiers.
    IR_AGENT_CONCURRENCY: int = 4
    # Where the human-browsable mirror of bulk-ingested PDFs lives. Sits
    # alongside `STORAGE_DIR` so an S3 swap on the canonical path leaves the
    # local mirror behind for inspection.
    IR_AGENT_RUNS_DIR: str = "var/ingest_runs"
    # How long the on-disk BSE master-list cache (used by the exchange-tier
    # discovery to resolve `Company.bse_code`) is considered fresh before it
    # is refreshed from `api.bseindia.com/...ListofScripData/w`.
    BSE_MASTER_TTL_DAYS: int = 7

    # Worker tunables. The worker polls `extraction_jobs` for PENDING rows.
    WORKER_POLL_INTERVAL_SECONDS: float = 2.0
    WORKER_INPROCESS: bool = True  # run worker inside FastAPI lifespan (dev)
    # Reclaim PROCESSING rows left behind when the worker dies mid-job (e.g. uvicorn reload).
    WORKER_STALE_CLAIM_SECONDS: float = 90.0  # claimed but extraction never started
    WORKER_STALE_RUN_SECONDS: float = 1800.0  # extraction started but never finished

    # Confidence at which a fully-processed job auto-publishes its cards.
    # Below this threshold the cards stay unpublished and the ReviewQueue stays
    # OPEN until an admin approves.
    AUTO_PUBLISH_CONFIDENCE: float = 80.0

    # --- Document search / RAG ---
    EMBEDDING_PROVIDER: str = "mock"  # one of: "mock", "openai"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    RAG_TOP_K: int = 8
    RAG_MAX_CHUNK_CHARS: int = 2500

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def storage_path(self) -> Path:
        p = Path(self.STORAGE_DIR)
        if not p.is_absolute():
            p = Path.cwd() / p
        return p

    @property
    def ir_agent_runs_path(self) -> Path:
        p = Path(self.IR_AGENT_RUNS_DIR)
        if not p.is_absolute():
            p = Path.cwd() / p
        return p

    @property
    def is_production(self) -> bool:
        return (self.APP_ENV or "").strip().lower() in _PRODUCTION_ENV_VALUES

    def assert_production_ready(self) -> None:
        """Refuse to boot a production process with insecure defaults.

        Called from `app.main.create_app()` on every startup. Raises
        `RuntimeError` with a clear message when:

        - `JWT_SECRET` still contains a development placeholder
        - `LLM_PROVIDER` is `mock`
        - `LLM_PROVIDER=anthropic` but `ANTHROPIC_API_KEY` is empty
        - `LLM_PROVIDER=openai` but `OPENAI_API_KEY` is empty
        """
        if not self.is_production:
            return

        secret = (self.JWT_SECRET or "").lower()
        if any(marker in secret for marker in _WEAK_JWT_SECRET_MARKERS) or len(secret) < 32:
            raise RuntimeError(
                "APP_ENV=production requires a strong JWT_SECRET (at least 32 chars, "
                "no dev / change-me placeholders)."
            )

        provider = (self.LLM_PROVIDER or "").lower()
        if provider == "mock":
            raise RuntimeError(
                "APP_ENV=production cannot run with LLM_PROVIDER=mock. "
                "Set LLM_PROVIDER=anthropic or openai with a valid API key."
            )
        if provider == "anthropic" and not (self.ANTHROPIC_API_KEY or "").strip():
            raise RuntimeError(
                "LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY in production."
            )
        if provider == "openai" and not (self.OPENAI_API_KEY or "").strip():
            raise RuntimeError(
                "LLM_PROVIDER=openai requires OPENAI_API_KEY in production."
            )

        embedding_provider = (self.EMBEDDING_PROVIDER or "mock").lower()
        if embedding_provider == "openai" and not (self.OPENAI_API_KEY or "").strip():
            raise RuntimeError(
                "EMBEDDING_PROVIDER=openai requires OPENAI_API_KEY in production."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
