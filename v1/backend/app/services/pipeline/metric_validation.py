"""Cross-statement + recompute-drift validation for calculated metrics.

Phase 2B of the metric-governance roadmap. The metrics stage already flags
values outside static bounds (``services/pipeline/metrics.py``) and values
that look anomalous against the company's own history
(``services/pipeline/metric_anomaly.py``). This module adds a third tier of
checks that catch *internally inconsistent* extractions:

- **Cross-statement:** PAT must not exceed Revenue; EBITDA must not exceed
  Revenue. Both invariants hold for any company that actually earns money
  (the LLM occasionally swaps segment vs consolidated rows, producing
  PAT > Revenue — exactly the RELIANCE Q2 segment mismatch in another
  disguise).
- **Recompute drift:** when both PAT and Revenue are present as facts, the
  stored ``pat_margin`` calculated value must be within 2 pp of the
  freshly-recomputed ``pat / revenue * 100``. Drift here usually means the
  metric was computed against a stale fact that has since been corrected.
- **Growth review gate:** any growth-style metric with absolute value above
  500 % opens a review entry even though it sits within the static bounds.

Failures are surfaced via :class:`MetricValidationReport`, which the runner
attaches to the review queue alongside ``validator_report``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.facts import FinancialLineItemDefinition, FinancialStatementFact
from app.models.intelligence import CalculatedMetric, MetricDefinition

logger = logging.getLogger(__name__)


# Tolerance for the recompute-drift check (PAT margin / EBITDA margin etc.).
# 2 percentage points is wide enough to absorb rounding in the source filing
# but narrow enough to catch a real recompute drift.
_RECOMPUTE_DRIFT_PP: float = 2.0

# Growth-rate magnitude that opens a review entry even when static bounds pass.
# YoY growth on a small base can legitimately exceed 200 %, so the YoY gate is
# wider; QoQ growth that crosses ±100 % almost always indicates a YTD-vs-PQ
# column mismatch (see INDHOTEL Q1 → Q2 −99.8 % revenue case).
_GROWTH_REVIEW_PCT_YOY: float = 300.0
_GROWTH_REVIEW_PCT_QOQ: float = 100.0


@dataclass
class MetricValidationReport:
    """Aggregate of cross-statement / drift failures for one document run."""

    cross_statement_breaches: list[dict] = field(default_factory=list)
    recompute_drift: list[dict] = field(default_factory=list)
    growth_review: list[dict] = field(default_factory=list)

    @property
    def has_failures(self) -> bool:
        return bool(
            self.cross_statement_breaches
            or self.recompute_drift
            or self.growth_review
        )

    def to_dict(self) -> dict:
        return {
            "cross_statement_breaches": self.cross_statement_breaches,
            "recompute_drift": self.recompute_drift,
            "growth_review": self.growth_review,
        }


def validate_calculated_metrics(
    db: Session,
    *,
    company_id: int,
    period_id: int,
) -> MetricValidationReport:
    """Run all post-metric validations for a (company, period) pair.

    The function is pure read + report; it does not mutate metrics. The
    runner inspects the report after :func:`run_metrics` and decides whether
    to gate auto-publish on its findings.
    """
    report = MetricValidationReport()

    fact_values = _fact_lookup(db, company_id=company_id, period_id=period_id)
    metric_rows = _metric_rows(db, company_id=company_id, period_id=period_id)

    _check_cross_statement(fact_values, report)
    _check_recompute_drift(metric_rows, fact_values, report)
    _check_growth_review(metric_rows, report)

    if report.has_failures:
        logger.info(
            "metric_validation: company=%s period=%s cross=%s drift=%s growth=%s",
            company_id,
            period_id,
            len(report.cross_statement_breaches),
            len(report.recompute_drift),
            len(report.growth_review),
        )
    return report


def apply_validation_actions(
    db: Session,
    *,
    company_id: int,
    period_id: int,
    report: MetricValidationReport,
) -> int:
    """Quarantine metrics that fail recompute-drift or extreme-growth checks.

    Called immediately after :func:`validate_calculated_metrics` and before
    signal evaluation so drifted margins and obviously wrong growth rates
    cannot fire rules. Returns the number of rows quarantined.
    """
    if not report.recompute_drift and not report.growth_review:
        return 0
    drift_by_code = {d["metric_code"]: d for d in report.recompute_drift}
    growth_by_code = {d["metric_code"]: d for d in report.growth_review}
    quarantined = 0
    for cm, md in _metric_rows(db, company_id=company_id, period_id=period_id):
        reason: str | None = None
        drift = drift_by_code.get(md.metric_code)
        if drift is not None:
            reason = (
                f"Recompute drift: stored {drift['actual']}% vs fact-derived "
                f"{drift['expected']}% ({drift['drift_pp']:+.1f} pp)"
            )
        elif (growth := growth_by_code.get(md.metric_code)) is not None:
            reason = (
                f"Extreme {growth['comparator'].upper()} growth: "
                f"{growth['value']:+.1f}% exceeds review threshold "
                f"±{growth['threshold']:.0f}% — likely comparator / column-tag "
                f"mismatch upstream."
            )
        if reason is None or cm.is_quarantined:
            continue
        cm.is_quarantined = True
        cm.quarantine_reason = reason
        if cm.confidence_score is not None:
            cm.confidence_score = min(float(cm.confidence_score), 50.0)
        quarantined += 1
    if quarantined:
        logger.info(
            "metric_validation: quarantined %s metric(s) company=%s period=%s",
            quarantined,
            company_id,
            period_id,
        )
    return quarantined


def _fact_lookup(
    db: Session, *, company_id: int, period_id: int
) -> dict[str, float]:
    rows = db.execute(
        select(FinancialLineItemDefinition.normalized_code, FinancialStatementFact.value)
        .join(
            FinancialLineItemDefinition,
            FinancialLineItemDefinition.line_item_def_id
            == FinancialStatementFact.line_item_def_id,
        )
        .where(
            FinancialStatementFact.company_id == company_id,
            FinancialStatementFact.period_id == period_id,
            FinancialStatementFact.period_value_type == "CURRENT",
        )
    ).all()
    out: dict[str, float] = {}
    for code, value in rows:
        if value is None:
            continue
        out[code] = float(value)
    return out


def _metric_rows(
    db: Session, *, company_id: int, period_id: int
) -> list[tuple[CalculatedMetric, MetricDefinition]]:
    rows = db.execute(
        select(CalculatedMetric, MetricDefinition)
        .join(MetricDefinition, MetricDefinition.metric_def_id == CalculatedMetric.metric_def_id)
        .where(
            CalculatedMetric.company_id == company_id,
            CalculatedMetric.period_id == period_id,
            CalculatedMetric.metric_value.is_not(None),
        )
    ).all()
    return [(cm, md) for cm, md in rows]


def _check_cross_statement(
    facts: dict[str, float], report: MetricValidationReport
) -> None:
    revenue = facts.get("revenue_from_operations")
    if revenue is None or revenue <= 0:
        return  # without revenue there is nothing to cross-check
    pat = facts.get("pat")
    if pat is not None and pat > revenue:
        report.cross_statement_breaches.append(
            {
                "rule": "pat <= revenue",
                "pat": pat,
                "revenue": revenue,
                "reason": (
                    "PAT exceeds revenue — likely segment vs consolidated mismatch "
                    "in the source extraction."
                ),
            }
        )
    ebitda = facts.get("ebitda")
    if ebitda is not None and ebitda > revenue:
        report.cross_statement_breaches.append(
            {
                "rule": "ebitda <= revenue",
                "ebitda": ebitda,
                "revenue": revenue,
                "reason": "EBITDA exceeds revenue — implies operating expenses are negative.",
            }
        )


def _check_recompute_drift(
    metric_rows: list[tuple[CalculatedMetric, MetricDefinition]],
    facts: dict[str, float],
    report: MetricValidationReport,
) -> None:
    revenue = facts.get("revenue_from_operations")
    pat = facts.get("pat")
    ebitda = facts.get("ebitda")
    for cm, md in metric_rows:
        if md.metric_code == "pat_margin" and revenue and pat is not None:
            expected = (pat / revenue) * 100.0
            actual = float(cm.metric_value or 0.0)
            if abs(expected - actual) > _RECOMPUTE_DRIFT_PP:
                report.recompute_drift.append(
                    {
                        "metric_code": md.metric_code,
                        "expected": round(expected, 4),
                        "actual": round(actual, 4),
                        "drift_pp": round(actual - expected, 4),
                    }
                )
        if md.metric_code == "ebitda_margin" and revenue and ebitda is not None:
            expected = (ebitda / revenue) * 100.0
            actual = float(cm.metric_value or 0.0)
            if abs(expected - actual) > _RECOMPUTE_DRIFT_PP:
                report.recompute_drift.append(
                    {
                        "metric_code": md.metric_code,
                        "expected": round(expected, 4),
                        "actual": round(actual, 4),
                        "drift_pp": round(actual - expected, 4),
                    }
                )


def _check_growth_review(
    metric_rows: list[tuple[CalculatedMetric, MetricDefinition]],
    report: MetricValidationReport,
) -> None:
    for cm, md in metric_rows:
        unit = (md.unit or "").lower()
        if unit != "%":
            continue
        code = md.metric_code
        # Catalog uses both `revenue_qoq_growth` and `pat_growth_qoq` shapes;
        # the substring test handles either.
        is_qoq = "_qoq" in code
        is_yoy = "_yoy" in code
        if not (is_qoq or is_yoy):
            continue
        threshold = _GROWTH_REVIEW_PCT_QOQ if is_qoq else _GROWTH_REVIEW_PCT_YOY
        value = float(cm.metric_value or 0.0)
        if abs(value) > threshold:
            report.growth_review.append(
                {
                    "metric_code": code,
                    "value": round(value, 4),
                    "threshold": threshold,
                    "comparator": "qoq" if is_qoq else "yoy",
                }
            )
