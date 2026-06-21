"""Resolve the int IDs the frontend sends back to v2 built periods/signals."""

from __future__ import annotations

from typing import Any

from . import ids
from .builder import BuiltPeriod, Catalog


def find_object(catalog: Catalog, object_id: int) -> BuiltPeriod | None:
    for built in catalog.all_built():
        p = built.period
        if ids.object_id(p.ticker, p.quarter, p.fy_start_year, "result_verdict") == object_id:
            return built
    return None


def find_event(catalog: Catalog, event_id: int) -> BuiltPeriod | None:
    for built in catalog.all_built():
        p = built.period
        if ids.event_id(p.ticker, p.quarter, p.fy_start_year) == event_id:
            return built
    return None


def find_signal(
    catalog: Catalog, signal_id: int
) -> tuple[BuiltPeriod, dict[str, Any]] | None:
    for built in catalog.all_built():
        p = built.period
        for signal in built.signals:
            if ids.signal_id(p.ticker, p.quarter, p.fy_start_year, signal["signal_key"]) == signal_id:
                return built, signal
    return None


def find_filing_by_int(catalog: Catalog, document_id: int):
    for filing in catalog._filings:  # noqa: SLF001 - same package read
        if ids.document_id(filing.document_id) == document_id:
            return filing
    return None
