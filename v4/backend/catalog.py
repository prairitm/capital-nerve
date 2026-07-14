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


def display_catalog() -> dict[str, Any]:
    """Source-specific rules for the small primary intelligence surface."""
    return _load("display.json")


def document_display_config(document_type: str | None) -> dict[str, Any]:
    normalized = (document_type or "").strip().upper().replace("-", "_").replace(" ", "_")
    key = {
        "FINANCIAL_RESULT": "financial_results",
        "FINANCIAL_RESULTS": "financial_results",
        "QUARTERLY_RESULT": "financial_results",
        "INVESTOR_PRESENTATION": "investor_presentation",
        "PRESENTATION": "investor_presentation",
        "EARNINGS_CALL": "earnings_call_transcript",
        "EARNINGS_CALL_TRANSCRIPT": "earnings_call_transcript",
        "CONCALL": "earnings_call_transcript",
        "CONCALL_TRANSCRIPT": "earnings_call_transcript",
    }.get(normalized)
    if not key:
        return {}
    return dict(display_catalog().get(key) or {})


def quarter_synthesis_config() -> dict[str, Any]:
    return dict(display_catalog().get("quarter_synthesis") or {})


def select_display_signals(
    signals: list[dict[str, Any]],
    document_type: str | None,
) -> list[dict[str, Any]]:
    """Rank, allow-list and de-duplicate primary signals for one event."""
    config = document_display_config(document_type)
    priority = config.get("signal_priority") or []
    if not priority:
        return signals[: int(config.get("max_signals") or len(signals))]
    allowed = set(priority)
    rank = {code: index for index, code in enumerate(priority)}
    groups = config.get("signal_groups") or {}
    candidates = [signal for signal in signals if signal.get("signal_type") in allowed]
    candidates.sort(key=lambda signal: rank.get(signal.get("signal_type"), len(rank)))
    selected: list[dict[str, Any]] = []
    seen_groups: set[str] = set()
    for signal in candidates:
        code = signal.get("signal_type") or ""
        group = groups.get(code, code)
        if group in seen_groups:
            continue
        seen_groups.add(group)
        selected.append(signal)
        if len(selected) >= int(config.get("max_signals") or 3):
            break
    return selected


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
