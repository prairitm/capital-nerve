"""Stage 3: `FinancialStatementFact` → `CalculatedMetric` (config-driven engine).

Every metric is declared in `metric_definitions` with three pieces of data:

1. ``inputs_json``       — list of input declarations consumed by `InputResolver`.
2. ``formula_text``      — a safe arithmetic/comparison expression (see
   ``formula.py``) evaluated against the resolved inputs.
3. ``dependencies_json`` — list of upstream metric codes this formula reads
   (used to topo-sort within a period so a metric is computed after every
   metric it references via ``kind="metric"``).

The runner walks the metric DAG once per period: for each definition it
resolves the inputs, evaluates the formula, and persists a `CalculatedMetric`
row that includes the formula, the input snapshot, and a step trace so the
drawer's "Calculation" panel can render without joining anywhere else.

If any declared input is missing, the metric is silently skipped — partial
documents are normal, and a missing fact must not cascade-kill a whole run.
"""
from __future__ import annotations

import logging
from collections import defaultdict, deque

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.models.events import SourceDocument
from app.models.intelligence import (
    CalculatedMetric,
    CardEvidence,
    GeneratedSignal,
    IntelligenceCard,
    MetricDefinition,
)
from app.models.master import FinancialPeriod
from app.services.pipeline.formula import FormulaError, evaluate
from app.services.pipeline.inputs import InputResolver

logger = logging.getLogger(__name__)


def _period_metric_ids_subq(company_id: int, period_id: int):
    return (
        select(CalculatedMetric.metric_id)
        .where(
            CalculatedMetric.company_id == company_id,
            CalculatedMetric.period_id == period_id,
        )
        .scalar_subquery()
    )


def _clear_period_metric_dependents(db: Session, *, company_id: int, period_id: int) -> None:
    """Drop cards/signals that FK old metrics before period-level metric refresh.

    Metrics are keyed by ``(company_id, period_id)`` only, so a re-ingest for
    one document can invalidate signals from another document that still point
    at the previous ``metric_id`` rows.
    """
    metric_ids = _period_metric_ids_subq(company_id, period_id)
    signal_ids = (
        select(GeneratedSignal.signal_id)
        .where(GeneratedSignal.primary_metric_id.in_(metric_ids))
        .scalar_subquery()
    )
    card_ids = (
        select(IntelligenceCard.card_id)
        .where(IntelligenceCard.signal_id.in_(signal_ids))
        .scalar_subquery()
    )
    db.execute(
        delete(CardEvidence).where(
            or_(
                CardEvidence.metric_id.in_(metric_ids),
                CardEvidence.card_id.in_(card_ids),
            )
        )
    )
    db.execute(delete(IntelligenceCard).where(IntelligenceCard.card_id.in_(card_ids)))
    db.execute(
        delete(GeneratedSignal).where(GeneratedSignal.primary_metric_id.in_(metric_ids))
    )


def run_metrics(db: Session, *, document: SourceDocument) -> int:
    """Compute and persist calculated metrics for the document's period.

    Returns the number of metric rows written. Skips silently when the
    document has no period (e.g. a generic press release) — metrics are a
    period-bound concept.
    """
    if document.period_id is None:
        return 0

    current_period = db.get(FinancialPeriod, document.period_id)
    if not current_period:
        return 0

    defs = list(db.execute(select(MetricDefinition)).scalars())
    if not defs:
        return 0

    ordered = _topo_sort(defs)
    if ordered is None:
        logger.error("metric_definitions has cyclic dependencies; aborting metrics stage")
        return 0

    # Re-runs replace previous metrics for this company+period — the unique
    # key does not include document_id so seeded metrics for the same quarter
    # must be overwritten on re-ingest.
    _clear_period_metric_dependents(
        db, company_id=document.company_id, period_id=document.period_id
    )
    db.execute(
        delete(CalculatedMetric).where(
            CalculatedMetric.company_id == document.company_id,
            CalculatedMetric.period_id == document.period_id,
        )
    )

    resolver = InputResolver(db, company_id=document.company_id, period_id=document.period_id)

    written = 0
    for md in ordered:
        if not md.formula_text:
            # No formula = nothing to compute. (Some legacy/sentinel rows may
            # exist for which only the metric_code is meaningful.)
            continue
        inputs_decl = list(md.inputs_json or [])
        if not inputs_decl:
            # Without an inputs declaration there's nothing to feed the formula
            # — skip silently. Migrate by populating ``inputs_json`` in the
            # seed when adding new metrics.
            logger.debug("metric %s has no inputs declaration; skipping", md.metric_code)
            continue

        resolved = resolver.resolve(inputs_decl)
        try:
            result = evaluate(md.formula_text, resolved)
        except FormulaError as exc:
            logger.warning("metric %s formula error: %s", md.metric_code, exc)
            continue

        if result.value is None:
            # Inputs incomplete — drop the metric (matches legacy behaviour).
            continue

        comparison = _comparison_metadata(inputs_decl, resolved, current_period, db)
        steps = _build_steps(md.formula_text, resolved, result.value, md.unit)

        quarantine_reason = _bounds_breach_reason(md, result.value)
        db.add(
            CalculatedMetric(
                company_id=document.company_id,
                event_id=document.event_id,
                document_id=document.document_id,
                period_id=document.period_id,
                metric_def_id=md.metric_def_id,
                metric_value=result.value,
                comparison_period_id=comparison.get("period_id"),
                comparison_type=comparison.get("type"),
                change_absolute=comparison.get("change_abs"),
                change_percent=comparison.get("change_pct"),
                change_bps=comparison.get("change_bps"),
                unit=md.unit,
                confidence_score=88.0,
                input_values=steps["inputs"],
                calculation_steps=steps,
                is_quarantined=quarantine_reason is not None,
                quarantine_reason=quarantine_reason,
            )
        )
        if quarantine_reason:
            logger.warning(
                "metric %s quarantined: %s", md.metric_code, quarantine_reason
            )
        written += 1
        # Flush so the next metric in topo order can read this metric back via
        # the resolver's ``kind="metric"`` lookup (e.g. fcf depends on cfo).
        db.flush()
    return written


def _bounds_breach_reason(md: MetricDefinition, value: float) -> str | None:
    """Return a human-readable reason when ``value`` is outside the metric's bounds.

    ``MetricDefinition.validation_min`` / ``validation_max`` are seeded from
    [`backend/app/seed/seed_catalog.py`](../../seed/seed_catalog.py) ``_m(bounds=...)``.
    NULL bounds mean unbounded on that side. Quarantined values are still
    persisted so the Review Queue surfaces the breach.
    """
    v_min = md.validation_min
    v_max = md.validation_max
    if v_min is None and v_max is None:
        return None
    unit = md.unit or ""
    pretty_value = _format_value(value, unit)
    if v_min is not None and value < float(v_min):
        return (
            f"Value {pretty_value} is below plausible minimum "
            f"{_format_value(float(v_min), unit)} — likely a unit-scale or "
            f"period-comparator error upstream."
        )
    if v_max is not None and value > float(v_max):
        return (
            f"Value {pretty_value} is above plausible maximum "
            f"{_format_value(float(v_max), unit)} — likely a unit-scale or "
            f"period-comparator error upstream."
        )
    return None


def _topo_sort(defs: list[MetricDefinition]) -> list[MetricDefinition] | None:
    """Kahn's algorithm: order metrics so dependencies are evaluated first.

    Returns `None` if a cycle is detected. Definitions with no dependencies
    keep their original ordering (stable inside Kahn's queue).
    """
    by_code = {md.metric_code: md for md in defs}
    in_degree: dict[str, int] = defaultdict(int)
    children: dict[str, list[str]] = defaultdict(list)

    for md in defs:
        deps = list(md.dependencies_json or [])
        for dep in deps:
            if dep in by_code:
                in_degree[md.metric_code] += 1
                children[dep].append(md.metric_code)

    queue = deque([md for md in defs if in_degree[md.metric_code] == 0])
    seen = set()
    out: list[MetricDefinition] = []
    while queue:
        md = queue.popleft()
        if md.metric_code in seen:
            continue
        seen.add(md.metric_code)
        out.append(md)
        for child_code in children[md.metric_code]:
            in_degree[child_code] -= 1
            if in_degree[child_code] == 0 and child_code in by_code:
                queue.append(by_code[child_code])

    if len(out) != len(defs):
        return None
    return out


def _comparison_metadata(
    inputs_decl: list[dict],
    resolved: dict,
    current_period: FinancialPeriod,
    db: Session,
) -> dict:
    """Pull a YoY/QoQ change-summary from the resolved inputs when present.

    Convention: a metric whose first comparator input has scope ``PY`` is YoY;
    ``PQ`` is QoQ. The drawer reads `change_absolute`, `change_percent`,
    `change_bps`, and `comparison_period_id` to render the trend chip.
    """
    comparator: dict | None = None
    for spec in inputs_decl:
        scope = (spec.get("scope") or "CURRENT").upper()
        if scope in ("PY", "PQ"):
            comparator = spec
            break
    if not comparator:
        return {}

    name = comparator["name"]
    base_name = _matching_current_input(inputs_decl, comparator["code"])
    base_value = resolved.get(base_name) if base_name else None
    prior_value = resolved.get(name)
    if prior_value is None or base_value is None:
        return {}

    scope = (comparator.get("scope") or "CURRENT").upper()
    comparison_type = "yoy" if scope == "PY" else "qoq"
    period_id = _resolve_comparator_period_id(scope, current_period, db)

    change_abs = base_value - prior_value
    change_pct = (base_value - prior_value) / prior_value * 100 if prior_value else None
    return {
        "period_id": period_id,
        "type": comparison_type,
        "change_abs": change_abs,
        "change_pct": change_pct,
        "change_bps": None,
    }


def _matching_current_input(inputs_decl: list[dict], code: str) -> str | None:
    for spec in inputs_decl:
        if (spec.get("scope") or "CURRENT").upper() == "CURRENT" and spec.get("code") == code:
            return spec["name"]
    return None


def _resolve_comparator_period_id(
    scope: str, current_period: FinancialPeriod, db: Session
) -> int | None:
    if current_period.quarter is None:
        return None
    if scope == "PY":
        prior = db.scalar(
            select(FinancialPeriod).where(
                FinancialPeriod.fy_year == current_period.fy_year - 1,
                FinancialPeriod.quarter == current_period.quarter,
                FinancialPeriod.period_type == current_period.period_type,
            )
        )
    elif scope == "PQ":
        prev_q = current_period.quarter - 1
        prev_fy = current_period.fy_year
        if prev_q < 1:
            prev_q = 4
            prev_fy -= 1
        prior = db.scalar(
            select(FinancialPeriod).where(
                FinancialPeriod.fy_year == prev_fy,
                FinancialPeriod.quarter == prev_q,
                FinancialPeriod.period_type == current_period.period_type,
            )
        )
    else:
        return None
    return prior.period_id if prior else None


def _build_steps(
    formula: str,
    resolved: dict,
    value: float,
    unit: str | None,
) -> dict:
    inputs_clean = {k: v for k, v in resolved.items() if v is not None}
    pretty = _format_value(value, unit)
    lines = [f"{name}: {v:.4f}".rstrip("0").rstrip(".") for name, v in inputs_clean.items()]
    lines.append(f"= {pretty}")
    return {
        "inputs": inputs_clean,
        "formula": formula,
        "steps": lines,
    }


def _format_value(value: float, unit: str | None) -> str:
    if unit == "%":
        return f"{value:.2f}%"
    if unit == "bps":
        return f"{value:+.0f} bps"
    if unit == "x":
        return f"{value:.2f}x"
    return f"{value:.2f}"
