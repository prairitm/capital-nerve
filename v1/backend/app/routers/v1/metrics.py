"""v1 metric-registry router.

Exposes the seeded :class:`MetricDefinition` rows as a stable, typed catalog
the frontend can browse. Drives the analyst-trust "open definition" affordance
on metric chips and the new ``MetricRegistryDrawer``.

The endpoint is purely read-only and uses the metric definitions written by
``app.seed.seed_catalog.upsert_metric_defs``. Related signals are derived from
``signal_definitions.rule_json`` so the registry stays in sync with whatever
signal rules currently fire on the metric.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.intelligence import MetricDefinition, SignalDefinition
from app.models.user import AppUser
from app.schemas.v1.metrics import (
    MetricRegistryEntry,
    MetricRegistryInput,
    MetricRegistryResponse,
    MetricRegistrySignal,
)

router = APIRouter(prefix="/v1/metrics", tags=["v1: metrics"])


def _walk_rule(rule: dict | None) -> set[str]:
    """Return every metric_code referenced by a signal rule (leaf or composite)."""
    if not rule:
        return set()
    if "all" in rule:
        out: set[str] = set()
        for child in rule.get("all") or []:
            out |= _walk_rule(child)
        return out
    if "any" in rule:
        out = set()
        for child in rule.get("any") or []:
            out |= _walk_rule(child)
        return out
    if "not" in rule:
        return _walk_rule(rule.get("not"))
    refs: set[str] = set()
    if rule.get("metric"):
        refs.add(rule["metric"])
    if rule.get("metric_ref"):
        refs.add(rule["metric_ref"])
    return refs


def _signals_by_metric_code(db: Session) -> dict[str, list[MetricRegistrySignal]]:
    """Group SignalDefinitions by every metric_code they reference.

    One pass over the SignalDefinitions table; each rule walk is cheap, and
    we cache the resulting dict for the lifetime of one request.
    """
    out: dict[str, list[MetricRegistrySignal]] = {}
    for sd in db.scalars(select(SignalDefinition)).all():
        for code in _walk_rule(sd.rule_json):
            out.setdefault(code, []).append(
                MetricRegistrySignal(
                    signal_code=sd.signal_code,
                    signal_name=sd.signal_name,
                    rule_text=sd.rule_text,
                )
            )
    return out


def _to_entry(
    md: MetricDefinition,
    related_signals: list[MetricRegistrySignal],
) -> MetricRegistryEntry:
    inputs = [
        MetricRegistryInput(
            name=i.get("name") or "",
            code=i.get("code"),
            scope=(i.get("scope") or "CURRENT").upper(),
            kind=(i.get("kind") or "fact").lower(),
        )
        for i in (md.inputs_json or [])
        if isinstance(i, dict)
    ]
    return MetricRegistryEntry(
        metric_code=md.metric_code,
        metric_name=md.metric_name,
        metric_category=md.metric_category,
        metric_kind=md.metric_kind,  # type: ignore[arg-type]
        unit=md.unit,
        formula_text=md.formula_text,
        is_percentage=bool(md.is_percentage),
        is_bps=bool(md.is_bps),
        validation_min=float(md.validation_min) if md.validation_min is not None else None,
        validation_max=float(md.validation_max) if md.validation_max is not None else None,
        inputs=inputs,
        dependencies=list(md.dependencies_json or []),
        related_signals=related_signals,
    )


@router.get("/registry", response_model=MetricRegistryResponse)
def list_metric_registry(
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
) -> MetricRegistryResponse:
    """Return every metric definition with its formula, range, inputs, signals.

    The list is sorted by ``(metric_kind, metric_category, metric_code)`` so
    the frontend can group financial metrics, then composites, then model
    scores without re-sorting client-side.
    """
    by_metric = _signals_by_metric_code(db)
    rows = db.scalars(
        select(MetricDefinition).order_by(
            MetricDefinition.metric_kind.asc(),
            MetricDefinition.metric_category.asc(),
            MetricDefinition.metric_code.asc(),
        )
    ).all()
    metrics = [_to_entry(md, by_metric.get(md.metric_code, [])) for md in rows]
    return MetricRegistryResponse(metrics=metrics)


@router.get("/registry/{metric_code}", response_model=MetricRegistryEntry)
def get_metric_registry_entry(
    metric_code: str,
    db: Session = Depends(get_db),
    _: AppUser = Depends(get_current_user),
) -> MetricRegistryEntry:
    """Single-metric lookup used by the inline "Definition" link."""
    md = db.scalar(
        select(MetricDefinition).where(MetricDefinition.metric_code == metric_code)
    )
    if md is None:
        raise HTTPException(status_code=404, detail="Unknown metric_code")
    by_metric = _signals_by_metric_code(db)
    return _to_entry(md, by_metric.get(md.metric_code, []))
