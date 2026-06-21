"""v1 API surface backed by the v2 store (companies, IO, signals, events, metrics)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import mapper, resolve
from ..builder import Catalog
from ..deps import catalog_dep, get_current_user
from ..state import User, store

router = APIRouter(prefix="/v1", tags=["v1"])


# ----------------------------------------------------------------- companies

@router.get("/companies")
def list_companies(
    search: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    briefs = [mapper.company_brief(catalog, t) for t in catalog.tickers()]
    briefs.extend(store.extra_companies)
    if search:
        q = search.lower()
        briefs = [
            b
            for b in briefs
            if q in (b["company_name"] or "").lower()
            or q in (b["nse_symbol"] or "").lower()
        ]
    return briefs[:limit]


@router.get("/companies/{symbol}")
def company_hub(
    symbol: str,
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    ticker = catalog.resolve_ticker(symbol)
    if not ticker:
        raise HTTPException(status_code=404, detail="Company not found")
    watching = catalog_company_in_watchlist(catalog, ticker, user)
    return mapper.company_detail(catalog, ticker, watching)


@router.get("/companies/{symbol}/events")
def company_events(
    symbol: str,
    limit: int = Query(default=60, ge=1, le=200),
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    ticker = catalog.resolve_ticker(symbol)
    if not ticker:
        raise HTTPException(status_code=404, detail="Company not found")
    builts = list(reversed(catalog.built_for_ticker(ticker)))
    return [mapper.event_brief(catalog, b) for b in builts[:limit]]


@router.get("/companies/{symbol}/signals")
def company_signals(
    symbol: str,
    limit: int = Query(default=20, ge=1, le=100),
    category: str | None = None,
    severity: str | None = None,
    direction: str | None = None,
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    ticker = catalog.resolve_ticker(symbol)
    if not ticker:
        raise HTTPException(status_code=404, detail="Company not found")
    out: list[dict[str, Any]] = []
    for built in reversed(catalog.built_for_ticker(ticker)):
        for signal in built.signals:
            if signal["signal_key"] == "no_material_change":
                continue
            out.append(mapper.signal_brief(catalog, built, signal))
    out = _filter_signal_briefs(out, category=category, severity=severity, direction=direction)
    return out[:limit]


@router.get("/companies/{symbol}/metric-trend")
def company_metric_trend(
    symbol: str,
    codes: str | None = None,
    quarters: int = Query(default=8, ge=1, le=24),
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    ticker = catalog.resolve_ticker(symbol)
    if not ticker:
        raise HTTPException(status_code=404, detail="Company not found")
    requested = (
        [c.strip() for c in codes.split(",") if c.strip()]
        if codes
        else list(mapper.DEFAULT_TREND_CODES)
    )
    return mapper.company_trends(catalog, ticker, requested, quarters)


# ------------------------------------------------------- intelligence objects

@router.get("/intelligence-objects")
def list_intelligence_objects(
    feed: str = "home",
    tab: str = "all",
    limit: int = Query(default=40, ge=1, le=200),
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    builts = catalog.all_built()
    builts.sort(key=lambda b: (b.period.quarter_end or "", b.period.ticker), reverse=True)

    if feed == "watchlist":
        builts = [b for b in builts if catalog_company_in_watchlist(catalog, b.period.ticker, user)]

    briefs = [mapper.intelligence_object_brief(catalog, b) for b in builts]
    briefs = _apply_tab(briefs, tab)
    return briefs[:limit]


def _apply_tab(briefs: list[dict[str, Any]], tab: str) -> list[dict[str, Any]]:
    if tab in ("all", "results", "verdicts"):
        return briefs
    if tab in ("positive", "growth"):
        return [b for b in briefs if b["status"] == "POSITIVE"]
    if tab in ("negative", "risks", "red_flags", "margin_pressure", "margins"):
        return [b for b in briefs if b["status"] == "NEGATIVE"]
    return briefs


@router.get("/intelligence-objects/summary")
def intelligence_summary(
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return mapper.feed_summary(catalog, catalog.all_built())


@router.get("/intelligence-objects/{object_id}")
def get_intelligence_object(
    object_id: int,
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    built = resolve.find_object(catalog, object_id)
    if built is None:
        raise HTTPException(status_code=404, detail="Intelligence object not found")
    return mapper.intelligence_object(catalog, built)


@router.get("/intelligence-objects/{object_id}/reproducibility")
def get_reproducibility(
    object_id: int,
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    built = resolve.find_object(catalog, object_id)
    if built is None:
        raise HTTPException(status_code=404, detail="Intelligence object not found")
    return mapper.reproducibility(catalog, built)


# ------------------------------------------------------------------ signals

@router.get("/signals")
def list_signals(
    limit: int = Query(default=40, ge=1, le=200),
    category: str | None = None,
    severity: str | None = None,
    direction: str | None = None,
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for built in catalog.all_built():
        for signal in built.signals:
            if signal["signal_key"] == "no_material_change":
                continue
            brief = mapper.signal_brief(catalog, built, signal)
            out.append((built.period.quarter_end or "", brief))
    out.sort(key=lambda x: x[0], reverse=True)
    briefs = _filter_signal_briefs(
        [b for _, b in out],
        category=category,
        severity=severity,
        direction=direction,
    )
    return briefs[:limit]


@router.get("/signals/categories")
def signal_categories(
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    cats: dict[str, int] = {}
    for built in catalog.all_built():
        for signal in built.signals:
            if signal["signal_key"] == "no_material_change":
                continue
            cat = mapper.SIGNAL_CATEGORY.get(signal["signal_key"], "general")
            cats[cat] = cats.get(cat, 0) + 1
    return [{"category": c, "count": n} for c, n in sorted(cats.items())]


@router.get("/signals/{signal_id}")
def get_signal(
    signal_id: int,
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    found = resolve.find_signal(catalog, signal_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    built, signal = found
    return mapper.signal_detail(catalog, built, signal)


# ------------------------------------------------------------------- events

@router.get("/events/{event_id}")
def get_event(
    event_id: int,
    catalog: Catalog = Depends(catalog_dep),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    built = resolve.find_event(catalog, event_id)
    if built is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return mapper.event_detail(catalog, built)


# ------------------------------------------------------------------ metrics

_REGISTRY_METRICS = [
    ("revenue_from_operations", "Revenue", "financial", "Cr", None, False),
    ("ebitda", "EBITDA", "financial", "Cr", None, False),
    ("ebitda_margin", "EBITDA Margin", "financial", "%", "ebitda / revenue * 100", True),
    ("operating_profit", "Operating Profit", "financial", "Cr", None, False),
    ("pat", "PAT", "financial", "Cr", None, False),
    ("eps_basic", "EPS", "financial", "Rs", None, False),
    ("revenue_yoy_pct", "Revenue YoY", "financial", "%", "(current - prior) / prior * 100", True),
    ("pat_yoy_pct", "PAT YoY", "financial", "%", "(current - prior) / prior * 100", True),
    ("revenue_qoq_pct", "Revenue QoQ", "financial", "%", "(current - prior) / prior * 100", True),
]


@router.get("/metrics/registry")
def metrics_registry(
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    metrics = [
        {
            "metric_code": code,
            "metric_name": name,
            "metric_category": "financial",
            "metric_kind": kind,
            "unit": unit,
            "formula_text": formula,
            "is_percentage": is_pct,
            "is_bps": False,
            "validation_min": None,
            "validation_max": None,
            "inputs": [],
            "dependencies": [],
            "related_signals": [],
        }
        for (code, name, kind, unit, formula, is_pct) in _REGISTRY_METRICS
    ]
    return {"metrics": metrics}


@router.get("/metrics/registry/{metric_code}")
def metric_registry_entry(
    metric_code: str,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    for code, name, kind, unit, formula, is_pct in _REGISTRY_METRICS:
        if code == metric_code:
            return {
                "metric_code": code,
                "metric_name": name,
                "metric_category": "financial",
                "metric_kind": kind,
                "unit": unit,
                "formula_text": formula,
                "is_percentage": is_pct,
                "is_bps": False,
                "validation_min": None,
                "validation_max": None,
                "inputs": [],
                "dependencies": [],
                "related_signals": [],
            }
    raise HTTPException(status_code=404, detail="Metric not found")


# ------------------------------------------------------------------ helpers

def _filter_signal_briefs(
    briefs: list[dict[str, Any]],
    *,
    category: str | None = None,
    severity: str | None = None,
    direction: str | None = None,
) -> list[dict[str, Any]]:
    if category:
        briefs = [b for b in briefs if b["signal_category"] == category]
    if severity:
        briefs = [b for b in briefs if b["severity"] == severity.upper()]
    if direction:
        briefs = [b for b in briefs if b["direction"] == direction.upper()]
    return briefs


def catalog_company_in_watchlist(catalog: Catalog, ticker: str, user: User) -> bool:
    from .. import ids

    return ids.company_id(ticker) in user.watchlist_company_ids
