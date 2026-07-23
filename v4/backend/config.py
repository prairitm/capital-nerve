"""Configuration for the v4 API.

Paths resolve relative to the repo root so the service works regardless of the
current working directory.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent.parent


class Settings:
    def __init__(self) -> None:
        default_db = REPO_ROOT / "v4" / "data" / "capital_nerve.db"
        self.db_path = Path(os.getenv("V4_DB_PATH", str(default_db))).resolve()
        default_app_db = REPO_ROOT / "v4" / "data" / "capital_nerve_app.db"
        self.app_db_path = Path(
            os.getenv("V4_APP_DB_PATH", str(default_app_db))
        ).resolve()
        self.data_dir = self.db_path.parent
        self.documents_dir = self.data_dir / "documents"
        self.parsed_dir = self.data_dir / "parsed"
        self.catalog_dir = Path(
            os.getenv("V4_CATALOG_DIR", str(REPO_ROOT / "v4" / "microservices" / "catalog"))
        ).resolve()
        # Comma-separated list of allowed CORS origins for the dev frontend.
        self.cors_origins = os.getenv(
            "V4_CORS_ORIGINS",
            "http://localhost:5174,http://127.0.0.1:5174",
        ).split(",")
        self.session_ttl_hours = int(os.getenv("V4_SESSION_TTL_HOURS", "168"))
        self.cookie_secure = os.getenv("V4_COOKIE_SECURE", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.admin_email = os.getenv("V4_ADMIN_EMAIL")
        self.admin_password = os.getenv("V4_ADMIN_PASSWORD")
        self.company_service_url = os.getenv(
            "V4_COMPANY_SERVICE_URL", "http://127.0.0.1:8020"
        ).rstrip("/")
        self.values_service_url = os.getenv(
            "V4_VALUES_SERVICE_URL", "http://127.0.0.1:8023"
        ).rstrip("/")
        self.nse_equity_csv_url = os.getenv(
            "V4_NSE_EQUITY_CSV_URL",
            "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
        )
        self.nse_refresh_hours = int(os.getenv("V4_NSE_REFRESH_HOURS", "24"))
        self.nse_request_timeout_seconds = float(
            os.getenv("V4_NSE_REQUEST_TIMEOUT_SECONDS", "30")
        )
        self.nse_refresh_on_startup = os.getenv(
            "V4_NSE_REFRESH_ON_STARTUP", "true"
        ).lower() in {"1", "true", "yes", "on"}
        self.public_app_url = os.getenv(
            "V4_PUBLIC_APP_URL", "https://www.capitalnerve.com"
        ).rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
