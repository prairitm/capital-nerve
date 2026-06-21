from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
REPO_ROOT = ROOT_DIR.parent

load_dotenv(ROOT_DIR / ".env")


def _ensure_v2_on_path() -> Path:
    v2_dir = REPO_ROOT / "v2"
    v2_str = str(v2_dir)
    if v2_str not in sys.path:
        sys.path.insert(0, v2_str)
    return v2_dir


class Settings:
    def __init__(self) -> None:
        self.v2_dir = _ensure_v2_on_path()
        self.catalog_dir = self.v2_dir / "catalog"

        db_path = os.getenv("DB_PATH", "data/capital_nerve.db")
        self.db_path = (ROOT_DIR / db_path).resolve()
        self.data_dir = self.db_path.parent
        self.documents_dir = self.data_dir / "documents"
        self.parsed_dir = self.data_dir / "parsed"

        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.openai_parse_model = os.getenv("OPENAI_PARSE_MODEL", self.openai_model)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
