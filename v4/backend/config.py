"""Configuration for the v4 read-only API.

v4 serves the 7-step SQLite DB written by the v3 pipeline / notebook. It never
writes: ingestion stays in v3. Paths resolve relative to the repo root so the
service works regardless of the current working directory.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent.parent


class Settings:
    def __init__(self) -> None:
        default_db = REPO_ROOT / "v3" / "data" / "capital_nerve.db"
        self.db_path = Path(os.getenv("V4_DB_PATH", str(default_db))).resolve()
        self.data_dir = self.db_path.parent
        self.documents_dir = self.data_dir / "documents"
        self.parsed_dir = self.data_dir / "parsed"
        self.catalog_dir = Path(
            os.getenv("V4_CATALOG_DIR", str(REPO_ROOT / "v2" / "catalog"))
        ).resolve()
        # Comma-separated list of allowed CORS origins for the dev frontend.
        self.cors_origins = os.getenv(
            "V4_CORS_ORIGINS",
            "http://localhost:5174,http://127.0.0.1:5174",
        ).split(",")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
