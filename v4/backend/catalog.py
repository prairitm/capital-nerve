"""Load the v2 catalog (signals, metrics, facts) to enrich sparse DB rows.

The 7-step DB stores signal/metric/fact codes but not always the human-facing
name, category, or direction. The catalog JSON is the source of truth for those,
and also powers the category filter on the signals screener.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from config import settings


@lru_cache
def _load(name: str) -> dict[str, Any]:
    path = settings.catalog_dir / name
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def signals_catalog() -> dict[str, Any]:
    return _load("signals.json")


def metrics_catalog() -> dict[str, Any]:
    return _load("metrics.json")


def facts_catalog() -> dict[str, Any]:
    return _load("facts.json")


def signal_meta(code: str | None) -> dict[str, Any]:
    """Name / category / direction / severity for a signal code."""
    if not code:
        return {}
    return signals_catalog().get(code, {})


def metric_meta(code: str | None) -> dict[str, Any]:
    """Name / unit / category for a metric code."""
    if not code:
        return {}
    return metrics_catalog().get(code, {})


def fact_meta(code: str | None) -> dict[str, Any]:
    """Name / unit / statement for an extracted fact code."""
    if not code:
        return {}
    return facts_catalog().get(code, {})


def signal_categories() -> list[str]:
    """Distinct categories across the signal catalog (for filter chips)."""
    seen: list[str] = []
    for spec in signals_catalog().values():
        cat = spec.get("category")
        if cat and cat not in seen:
            seen.append(cat)
    return seen
