"""Load Nifty-50-style company list JSON used by seed / bulk-ingest CLIs."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError


class CompanyListRow(BaseModel):
    legal_name: str = Field(min_length=1)
    nse_symbol: str = Field(min_length=1, max_length=32)
    sector: str = Field(min_length=1)


def load_company_rows(path: Path) -> list[CompanyListRow]:
    """Parse a JSON array of ``{legal_name, nse_symbol, sector}`` objects."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(raw, list):
        raise ValueError(f"Expected a JSON array in {path}")

    rows: list[CompanyListRow] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"Row {index}: expected an object, got {type(item).__name__}")
        try:
            rows.append(CompanyListRow.model_validate(item))
        except ValidationError as exc:
            raise ValueError(f"Row {index}: {exc}") from exc

    if not rows:
        raise ValueError(f"No entries in {path}")

    return rows


def load_nse_symbols(path: Path) -> list[str]:
    """Return uppercased NSE symbols from a company-list JSON file."""
    return [row.nse_symbol.strip().upper() for row in load_company_rows(path)]
