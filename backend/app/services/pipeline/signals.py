"""Stage 4: `CalculatedMetric` → `GeneratedSignal` (composite rule grammar).

`SignalDefinition.rule_json` follows a small JSON grammar:

- **Leaf**: ``{"metric": "<code>", "operator": ">|>=|<|<=|==|!=", "threshold": <num>}``
  Optional ``"metric_ref": "<other_metric_code>"`` may replace ``threshold`` so
  the comparison is metric-vs-metric (e.g. ``receivables_growth > revenue_yoy_growth``).
- **All / Any / Not**: ``{"all": [<rule>, ...]}``, ``{"any": [<rule>, ...]}``,
  ``{"not": <rule>}``.

The evaluator walks the tree, returning a `bool` and the set of metrics it
read. Backwards-compat: a top-level leaf still fires the same way it always
has — Phase 0 wraps it in an implicit ``all`` so the existing single-rule
seeds keep working.

Signals without any numeric rule (concall tone, auditor red flags) are
deliberately not evaluated here — they are emitted by the dedicated NLP /
auditor extractors.
"""
from __future__ import annotations

import logging
from typing import Any, TypedDict

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.enums import SeverityLevel, SignalDirection
from app.models.events import SourceDocument
from app.models.intelligence import (
    CalculatedMetric,
    CardEvidence,
    GeneratedSignal,
    IntelligenceCard,
    MetricDefinition,
    SignalDefinition,
)

logger = logging.getLogger(__name__)


class SignalSkip(TypedDict):
    signal_code: str
    signal_name: str
    reason: str
    detail: str


class SignalFired(TypedDict):
    signal_code: str
    signal_name: str
    headline: str


class SignalDiagnostics(TypedDict):
    fired_count: int
    rules_total: int
    rules_evaluable: int
    rules_non_evaluable: int
    blockers: list[str]
    fired: list[SignalFired]
    not_fired: list[SignalSkip]


def run_signals(
    db: Session, *, document: SourceDocument
) -> tuple[list[GeneratedSignal], SignalDiagnostics]:
    """Evaluate rules for this document's metrics and return the new signals."""
    evaluation = evaluate_signal_rules(db, document=document)
    diagnostics = evaluation["diagnostics"]
    # Cards FK `signal_id`; clear them before replacing signals (cards stage
    # also clears by document_id, but signals runs first on re-extract).
    existing_card_ids = list(
        db.execute(
            select(IntelligenceCard.card_id).where(
                IntelligenceCard.document_id == document.document_id
            )
        ).scalars()
    )
    if existing_card_ids:
        db.execute(
            delete(CardEvidence).where(CardEvidence.card_id.in_(existing_card_ids))
        )
        db.execute(
            delete(IntelligenceCard).where(IntelligenceCard.card_id.in_(existing_card_ids))
        )
    db.execute(
        delete(GeneratedSignal).where(GeneratedSignal.document_id == document.document_id)
    )

    written: list[GeneratedSignal] = []
    for candidate in evaluation["candidates"]:
        sig = GeneratedSignal(
            company_id=document.company_id,
            event_id=document.event_id,
            document_id=document.document_id,
            period_id=document.period_id,
            signal_def_id=candidate["signal_def_id"],
            signal_direction=candidate["direction"],
            severity=candidate["severity"],
            signal_score=candidate["score"],
            confidence_score=88.0,
            headline=candidate["headline"],
            explanation=candidate["explanation"],
            primary_metric_id=candidate["primary_metric_id"],
            metric_refs=candidate["metric_refs"],
            is_published=True,
        )
        db.add(sig)
        db.flush()
        written.append(sig)
    return written, diagnostics


def evaluate_signal_rules(db: Session, *, document: SourceDocument) -> dict[str, Any]:
    diagnostics: SignalDiagnostics = {
        "fired_count": 0,
        "rules_total": 0,
        "rules_evaluable": 0,
        "rules_non_evaluable": 0,
        "blockers": [],
        "fired": [],
        "not_fired": [],
    }
    candidates: list[dict[str, Any]] = []

    if document.period_id is None:
        diagnostics["blockers"].append("no_period")
        return {"diagnostics": diagnostics, "candidates": candidates}

    metrics = _load_metric_values(
        db, company_id=document.company_id, period_id=document.period_id
    )
    if not metrics:
        diagnostics["blockers"].append("no_metrics")
        return {"diagnostics": diagnostics, "candidates": candidates}

    defs = list(db.execute(select(SignalDefinition)).scalars())
    diagnostics["rules_total"] = len(defs)
    if not defs:
        diagnostics["blockers"].append("no_signal_definitions")
        return {"diagnostics": diagnostics, "candidates": candidates}

    for sd in defs:
        rule = sd.rule_json or {}
        if not _has_evaluable_rule(rule):
            diagnostics["rules_non_evaluable"] += 1
            diagnostics["not_fired"].append(
                {
                    "signal_code": sd.signal_code,
                    "signal_name": sd.signal_name,
                    "reason": "no_numeric_rule",
                    "detail": (
                        "Needs concall, auditor notes, or another fact-based extractor — "
                        "not evaluated by metric rules."
                    ),
                }
            )
            continue

        diagnostics["rules_evaluable"] += 1
        outcome = _evaluate_rule(rule, metrics)
        if outcome.fired:
            primary_metric_id, metric_refs = _materialize_metric_refs(outcome.touched, metrics)
            primary_value, primary_unit, primary_code = _primary_metric_summary(
                outcome.touched, metrics
            )
            direction = sd.default_direction or SignalDirection.MIXED
            severity = _escalate_severity(sd, outcome.touched)
            headline, explanation = _signal_copy(sd, primary_value, primary_unit, primary_code)
            score = _score(outcome.touched)
            diagnostics["fired_count"] += 1
            diagnostics["fired"].append(
                {
                    "signal_code": sd.signal_code,
                    "signal_name": sd.signal_name,
                    "headline": headline,
                }
            )
            candidates.append(
                {
                    "signal_def_id": sd.signal_def_id,
                    "direction": direction,
                    "severity": severity,
                    "score": score,
                    "headline": headline,
                    "explanation": explanation,
                    "primary_metric_id": primary_metric_id,
                    "metric_refs": metric_refs,
                }
            )
        else:
            diagnostics["not_fired"].append(
                {
                    "signal_code": sd.signal_code,
                    "signal_name": sd.signal_name,
                    "reason": outcome.reason,
                    "detail": outcome.detail,
                }
            )

    return {"diagnostics": diagnostics, "candidates": candidates}


def diagnostics_to_dict(diagnostics: SignalDiagnostics) -> dict[str, Any]:
    return dict(diagnostics)


# ---------------------------------------------------------------------------
# Composite rule grammar
# ---------------------------------------------------------------------------


class _LeafTouch(TypedDict):
    metric_code: str
    op: str
    threshold: float | None
    metric_ref: str | None
    value: float
    fired: bool


class _Outcome:
    """Result of evaluating one (possibly composite) rule.

    Attributes:
        fired: did the entire rule pass?
        touched: leaves that contributed to the truthy path (so the UI knows
            which metrics matter for this signal). For ``any`` we record only
            leaves that fired; for ``all`` we record every evaluated leaf.
        reason / detail: human-readable diagnostics when ``fired=False``.
    """

    __slots__ = ("fired", "touched", "reason", "detail")

    def __init__(
        self,
        *,
        fired: bool,
        touched: list[_LeafTouch],
        reason: str = "",
        detail: str = "",
    ) -> None:
        self.fired = fired
        self.touched = touched
        self.reason = reason
        self.detail = detail


def _has_evaluable_rule(rule: dict) -> bool:
    if not rule:
        return False
    if any(k in rule for k in ("all", "any", "not")):
        return True
    return bool(rule.get("metric") and rule.get("operator"))


def _evaluate_rule(rule: dict, metrics: dict[str, CalculatedMetric]) -> _Outcome:
    if "all" in rule:
        children = rule["all"] or []
        touched: list[_LeafTouch] = []
        for child in children:
            outcome = _evaluate_rule(child, metrics)
            touched.extend(outcome.touched)
            if not outcome.fired:
                return _Outcome(
                    fired=False,
                    touched=touched,
                    reason=outcome.reason or "all_branch_failed",
                    detail=outcome.detail,
                )
        return _Outcome(fired=True, touched=touched)
    if "any" in rule:
        children = rule["any"] or []
        any_touched: list[_LeafTouch] = []
        last_detail = ""
        for child in children:
            outcome = _evaluate_rule(child, metrics)
            if outcome.fired:
                any_touched.extend(outcome.touched)
                return _Outcome(fired=True, touched=any_touched)
            last_detail = outcome.detail or last_detail
        return _Outcome(fired=False, touched=[], reason="no_any_branch_fired", detail=last_detail)
    if "not" in rule:
        outcome = _evaluate_rule(rule["not"], metrics)
        if outcome.fired:
            return _Outcome(fired=False, touched=outcome.touched, reason="negated_branch_fired")
        return _Outcome(fired=True, touched=outcome.touched)
    return _evaluate_leaf(rule, metrics)


def _evaluate_leaf(leaf: dict, metrics: dict[str, CalculatedMetric]) -> _Outcome:
    metric_code = leaf.get("metric")
    op = leaf.get("operator")
    threshold = leaf.get("threshold")
    metric_ref = leaf.get("metric_ref")
    if not metric_code or not op:
        return _Outcome(
            fired=False, touched=[], reason="malformed_leaf", detail=str(leaf)
        )
    metric = metrics.get(metric_code)
    if metric is None or metric.metric_value is None:
        return _Outcome(
            fired=False,
            touched=[],
            reason="metric_missing",
            detail=f"Metric `{metric_code}` not calculated for this period.",
        )
    value = float(metric.metric_value)

    if metric_ref:
        ref_metric = metrics.get(metric_ref)
        if ref_metric is None or ref_metric.metric_value is None:
            return _Outcome(
                fired=False,
                touched=[],
                reason="metric_ref_missing",
                detail=f"Comparator metric `{metric_ref}` not calculated.",
            )
        threshold_f: float = float(ref_metric.metric_value)
    elif threshold is None:
        return _Outcome(
            fired=False,
            touched=[],
            reason="no_threshold",
            detail=f"Leaf for `{metric_code}` has neither threshold nor metric_ref.",
        )
    else:
        threshold_f = float(threshold)

    fired = _compare(value, op, threshold_f)
    touch: _LeafTouch = {
        "metric_code": metric_code,
        "op": op,
        "threshold": float(threshold) if threshold is not None else None,
        "metric_ref": metric_ref,
        "value": value,
        "fired": fired,
    }
    if not fired:
        return _Outcome(
            fired=False,
            touched=[touch],
            reason="threshold_not_met",
            detail=_threshold_detail(value, metric.unit, op, threshold_f),
        )
    return _Outcome(fired=True, touched=[touch])


def _compare(value: float, op: str, threshold: float) -> bool:
    if op == ">":
        return value > threshold
    if op == ">=":
        return value >= threshold
    if op == "<":
        return value < threshold
    if op == "<=":
        return value <= threshold
    if op == "==":
        return value == threshold
    if op == "!=":
        return value != threshold
    return False


# ---------------------------------------------------------------------------
# Helpers for materializing the GeneratedSignal payload
# ---------------------------------------------------------------------------


def _materialize_metric_refs(
    touched: list[_LeafTouch],
    metrics: dict[str, CalculatedMetric],
) -> tuple[int | None, list[dict[str, Any]]]:
    seen: set[int] = set()
    refs: list[dict[str, Any]] = []
    primary: int | None = None
    for t in touched:
        cm = metrics.get(t["metric_code"])
        if not cm or cm.metric_id in seen:
            continue
        seen.add(cm.metric_id)
        refs.append(
            {
                "metric_id": cm.metric_id,
                "metric_code": t["metric_code"],
                "value": float(cm.metric_value) if cm.metric_value is not None else None,
                "unit": cm.unit,
                "op": t["op"],
                "threshold": t["threshold"],
                "metric_ref": t["metric_ref"],
            }
        )
        if primary is None:
            primary = cm.metric_id
    return primary, refs


def _primary_metric_summary(
    touched: list[_LeafTouch],
    metrics: dict[str, CalculatedMetric],
) -> tuple[float | None, str | None, str | None]:
    if not touched:
        return None, None, None
    first = touched[0]
    cm = metrics.get(first["metric_code"])
    if not cm:
        return None, None, first["metric_code"]
    return (
        float(cm.metric_value) if cm.metric_value is not None else None,
        cm.unit,
        first["metric_code"],
    )


def _load_metric_values(
    db: Session, *, company_id: int, period_id: int
) -> dict[str, CalculatedMetric]:
    """Load published metrics for the period, skipping quarantined rows.

    Quarantined metrics (`is_quarantined=True`) breached their sanity bounds
    and would only produce wrong signals. They stay in the DB for the admin
    Review Queue but never participate in rule evaluation.
    """
    stmt = (
        select(CalculatedMetric, MetricDefinition)
        .join(MetricDefinition, MetricDefinition.metric_def_id == CalculatedMetric.metric_def_id)
        .where(
            CalculatedMetric.company_id == company_id,
            CalculatedMetric.period_id == period_id,
            CalculatedMetric.is_quarantined.is_(False),
        )
    )
    return {md.metric_code: cm for cm, md in db.execute(stmt).all()}


def _escalate_severity(sd: SignalDefinition, touched: list[_LeafTouch]) -> SeverityLevel:
    severity = sd.default_severity or SeverityLevel.MEDIUM
    # Only the first leaf drives escalation (it's the headline metric). Other
    # leaves are corroborators; bumping on each makes severity unstable.
    if not touched:
        return severity
    leaf = touched[0]
    threshold = leaf["threshold"]
    if threshold is None or threshold == 0:
        return severity
    op = leaf["op"]
    value = leaf["value"]
    if op in (">", ">="):
        ratio = (value - threshold) / max(abs(threshold), 1)
    elif op in ("<", "<="):
        ratio = (threshold - value) / max(abs(threshold), 1)
    else:
        ratio = 0
    if ratio >= 2 and severity is SeverityLevel.MEDIUM:
        severity = SeverityLevel.HIGH
    if abs(value - threshold) >= 500 and severity is SeverityLevel.HIGH and sd.signal_category != "margin":
        severity = SeverityLevel.CRITICAL
    return severity


def _score(touched: list[_LeafTouch]) -> float:
    if not touched:
        return 60.0
    leaf = touched[0]
    threshold = leaf["threshold"]
    op = leaf["op"]
    value = leaf["value"]
    if threshold in (None, 0):
        return 80.0
    if op in (">", ">="):
        ratio = (value - threshold) / abs(threshold)
    elif op in ("<", "<="):
        ratio = (threshold - value) / abs(threshold)
    else:
        ratio = 0
    score = 60 + ratio * 25
    return float(max(35, min(99, score)))


def _signal_copy(
    sd: SignalDefinition, value: float | None, unit: str | None, code: str | None
) -> tuple[str, str]:
    if value is None:
        headline = sd.signal_name
        explanation = sd.description or sd.signal_name
        return headline, explanation
    pretty = _format_value(value, unit)
    headline = f"{sd.signal_name}: {pretty}"
    explanation = (
        f"{sd.description or sd.signal_name} "
        f"Triggered at {pretty} (rule: {sd.rule_text or sd.signal_code})."
    )
    return headline, explanation


def _format_value(value: float, unit: str | None) -> str:
    if unit == "%":
        return f"{value:.1f}%"
    if unit == "bps":
        return f"{value:+.0f} bps"
    if unit == "x":
        return f"{value:.2f}x"
    return f"{value:.2f}"


def _threshold_detail(value: float, unit: str | None, op: str, threshold: float) -> str:
    actual = _format_value(value, unit)
    need = _format_value(threshold, unit)
    return f"Actual {actual}; rule requires {op} {need}."
