"""Local configuration for the Step 1 company microservice."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

MICROSERVICES_DIR = Path(__file__).resolve().parent
REPO_ROOT = MICROSERVICES_DIR.parent.parent.parent


class Settings:
    def __init__(self) -> None:
        default_db_path = REPO_ROOT / "v4" / "data" / "capital_nerve.db"
        self.db_path = Path(
            os.getenv("COMPANY_SERVICE_DB_PATH", str(default_db_path))
        ).resolve()
        self.catalog_dir = Path(
            os.getenv(
                "COMPANY_SERVICE_CATALOG_DIR",
                str(REPO_ROOT / "v4" / "microservices" / "catalog"),
            )
        ).resolve()
        self.documents_dir = Path(
            os.getenv(
                "COMPANY_SERVICE_DOCUMENTS_DIR",
                str(REPO_ROOT / "v4" / "data" / "documents"),
            )
        ).resolve()
        self.env_path = Path(
            os.getenv("COMPANY_SERVICE_ENV_PATH", str(REPO_ROOT / "v3" / ".env"))
        ).resolve()
        self.cors_origins = [
            origin.strip()
            for origin in os.getenv(
                "COMPANY_SERVICE_CORS_ORIGINS",
                "http://localhost:5174,http://127.0.0.1:5174",
            ).split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
