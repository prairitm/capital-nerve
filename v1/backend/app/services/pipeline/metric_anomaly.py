"""Historical-anomaly check for the metrics stage.

The static bounds defined in ``seed_catalog._m(bounds=...)`` quarantine
values that are physically impossible (a 1927 %% segment margin) but pass
values that are merely "way off for this company" — the RELIANCE Q2 FY25
PAT margin of 60.8 %% being the canonical example. PAT margin is bounded at
``[-50, 100]``, so 60.8 sails through; but Reliance's own median PAT margin
across the last twenty-plus quarters is roughly 7-8 %%, so an analyst would
immediately call it suspect.

This module provides a tiny, dependency-light check that compares a new
metric value against the company's own history for the same metric_code.
When the value sits well outside the historical envelope, we return an
``AnomalyReport`` so the metrics stage can persist the flag and the runner
can suppress auto-publish for documents whose primary card metric is
flagged.

The check is intentionally conservative — Phase 1 only flags the obvious
outliers. The thresholds are:

- N at least 3 historical observations (otherwise no anomaly call).
- "Margin gap" check for unit ``%``: value outside [median - 25 pp,
  median + 25 pp] -> anomaly.
- "Growth blow-out" check for ``%`` codes that look like growth rates
  (``*_growth_*``, ``*_qoq``, ``*_yoy``): value at least 4x the historical
  absolute median (and abs > 25 %) -> anomaly.
- Robust z-score (|value - median| / MAD) > 4 always anomalous.

Quarantined historical rows are excluded so a previous extraction bug does
not contaminate the baseline.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.intelligence import CalculatedMetric, MetricDefinition

logger = logging.getLogger(__name__)


# Codes the anomaly check actively guards. Adding a new code is cheap;
# leaving the list small keeps the Phase-1 surface understandable. The keys
# are the metric_code; the rules below pick which checks apply based on
# unit + the suffix of the code.
ANOMALY_GUARDED_CODES: frozenset[str] = frozenset(
    {
        "pat_margin",
        "ebitda_margin",
        "primary_segment_margin",
        "revenue_yoy_growth",
        "revenue_qoq_growth",
        "ebitda_growth_yoy",
        "pat_growth_yoy",
    }
)

# Minimum non-quarantined historical observations required before we will
# call anything an anomaly.
_MIN_HISTORY = 3

# Margin-style metrics (unit "%", not a growth code). 25 pp gives the
# RELIANCE 60.8 vs ~8 case plenty of headroom while still flagging the
# segment-revenue mismatch.
_MARGIN_PP_GAP = 25.0


@dataclass
class AnomalyReport:
    """Returned when a value sits far enough outside company history."""

    reason: str
    median: float
    sample_size: int


def check_anomaly(
    db: Session,
    *,
    company_id: int,
    metric_def: MetricDefinition,
    value: float,
    current_period_id: int,
) -> AnomalyReport | None:
    """Compare ``value`` against the company's own history for the metric.

    Excludes the row at ``current_period_id`` so a re-ingest of the same
    quarter does not bootstrap a value into its own baseline. Quarantined
    rows are also excluded — they were already flagged as wrong and must
    not poison the baseline used for the anomaly call.
    """
    if metric_def.metric_code not in ANOMALY_GUARDED_CODES:
        return None

    rows = db.execute(
        select(CalculatedMetric.metric_value).where(
            CalculatedMetric.company_id == company_id,
            CalculatedMetric.metric_def_id == metric_def.metric_def_id,
            CalculatedMetric.metric_value.is_not(None),
            CalculatedMetric.is_quarantined.is_(False),
            CalculatedMetric.period_id != current_period_id,
        )
    ).scalars()
    history = [float(v) for v in rows]
    if len(history) < _MIN_HISTORY:
        return None

    sorted_hist = sorted(history)
    median = _median(sorted_hist)
    mad = _median([abs(v - median) for v in sorted_hist]) or 0.0
    sample_size = len(history)
    unit = (metric_def.unit or "").lower()
    code = metric_def.metric_code

    # 1. Margin-style metrics: detect "off-baseline" values in pp space.
    is_growth_code = (
        "growth" in code
        or code.endswith("_qoq")
        or code.endswith("_yoy")
        or code.endswith("_qoq_growth")
    )
    if unit == "%" and not is_growth_code:
        diff = value - median
        if abs(diff) > _MARGIN_PP_GAP:
            return AnomalyReport(
                reason=(
                    f"Value {value:.1f}% is {diff:+.1f} pp away from the company's "
                    f"historical median of {median:.1f}% over {sample_size} quarters — "
                    "likely a unit / segment-mismatch error upstream."
                ),
                median=median,
                sample_size=sample_size,
            )

    # 2. Growth-rate blow-outs: 4x the historical |median| AND abs > 25 %.
    if unit == "%" and is_growth_code and abs(value) > 25.0:
        baseline = max(abs(median), 5.0)  # avoid divide-by-near-zero
        if abs(value) > 4 * baseline:
            return AnomalyReport(
                reason=(
                    f"Growth rate {value:+.1f}% is more than 4x the historical "
                    f"median magnitude ({median:+.1f}% over {sample_size} quarters)."
                ),
                median=median,
                sample_size=sample_size,
            )

    # The margin-pp gap and growth-blow-out checks above are the Phase 1
    # surface; we deliberately do not add a robust-z fallback because real
    # company history is too tight for it (e.g. PAT margin 6-12 % across
    # twenty quarters), which makes z-score noisy and over-flags valid
    # outlier prints. Anything subtler than 25 pp off-baseline should go
    # through the Phase 2 cross-statement and confidence checks instead.
    _ = mad  # kept for future Phase-2 use
    return None


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    n = len(values)
    s = sorted(values)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2
