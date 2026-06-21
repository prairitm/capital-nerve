"""Seed v3 metrics table from v2 JSON catalog."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from config import settings
from db import connect


def _metric_id(metric_code: str) -> str:
    return hashlib.sha256(metric_code.encode()).hexdigest()


def seed_metrics_catalog(db_path: Path | None = None) -> int:
    from catalog_loader import get_catalog

    catalog = get_catalog()
    path = db_path or settings.db_path
    count = 0

    with connect(path) as conn:
        for code, spec in catalog.metrics.items():
            formula_payload = json.dumps(
                {
                    "formula": spec.get("formula"),
                    "inputs": spec.get("inputs") or [],
                    "category": spec.get("category"),
                }
            )
            conn.execute(
                """
                INSERT INTO metrics (id, metric_code, name, formula, unit, description)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(metric_code) DO UPDATE SET
                    name = excluded.name,
                    formula = excluded.formula,
                    unit = excluded.unit,
                    description = excluded.description
                """,
                (
                    _metric_id(code),
                    code,
                    spec.get("name", code),
                    formula_payload,
                    spec.get("unit"),
                    spec.get("category"),
                ),
            )
            count += 1
        conn.commit()
    return count
