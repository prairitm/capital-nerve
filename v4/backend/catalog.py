"""Load the v4 event catalogs (signals, metrics, facts) for API enrichment.

The unified DB stores signal/metric/fact codes but not always the human-facing
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
    catalog = dict(_load("signals.json"))
    catalog.update(_load("investor_presentation/presentation_signals.json"))
    catalog.update(_load("earnings-call/earnings_call_signals.json"))
    return catalog


def metrics_catalog() -> dict[str, Any]:
    catalog = dict(_load("metrics.json"))
    catalog.update(_load("investor_presentation/presentation_metrics.json"))
    catalog.update(_load("earnings-call/earnings_call_metrics.json"))
    return catalog


def facts_catalog() -> dict[str, Any]:
    facts = dict(_load("facts.json"))
    # Event-specific definitions are overlays. They intentionally win for shared
    # codes because they describe the value stored by that event pipeline.
    facts.update(_load("investor_presentation/presentation_facts.json"))
    facts.update(_load("earnings-call/earnings_call_facts.json"))
    return facts


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
