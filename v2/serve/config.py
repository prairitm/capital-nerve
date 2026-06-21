"""Runtime configuration for the serving layer, sourced from environment."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# v2/ root — the parent of this `serve/` package.
ROOT_DIR = Path(__file__).resolve().parent.parent

load_dotenv(ROOT_DIR / ".env")


class Settings:
    def __init__(self) -> None:
        db_path = os.getenv("DB_PATH", "data/capital_nerve.db")
        self.db_path = (ROOT_DIR / db_path).resolve()

        self.data_dir = self.db_path.parent
        self.raw_dir = self.data_dir / "raw"
        self.parsed_dir = self.data_dir / "parsed"
        self.uploads_dir = self.data_dir / "uploads"

        self.jwt_secret = os.getenv("JWT_SECRET", "dev-change-me")
        self.jwt_algorithm = "HS256"
        self.jwt_expire_minutes = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))

        self.dev_email = os.getenv("DEV_EMAIL", "dev@capitalnerve.local")
        self.dev_password = os.getenv("DEV_PASSWORD", "dev")

        origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        self.cors_origins = [o.strip() for o in origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
