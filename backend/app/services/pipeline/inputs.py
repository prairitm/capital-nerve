"""`InputResolver` — turn a metric definition's declarative input list into a
flat `{name: value}` dict ready for `formula.evaluate()`.

The pipeline computes one metric at a time for `(company_id, period_id)`.
Each metric declares its inputs in `MetricDefinition.inputs_json` like:

    [
      {"name": "revenue",     "code": "revenue_from_operations", "scope": "CURRENT"},
      {"name": "revenue_py",  "code": "revenue_from_operations", "scope": "PY"},
      {"name": "ttm_ebitda",  "code": "ebitda",                  "scope": "TTM"},
      {"name": "fcf",         "kind": "metric", "code": "fcf",   "scope": "CURRENT"},
    ]

`kind` defaults to `"fact"` (look up in `financial_statement_facts`). Setting
`kind="metric"` reads from earlier `calculated_metrics` rows so a metric can
depend on another metric (`fcf` → `cfo - capex`, `net_debt_to_ebitda` → `net_debt
/ ttm_ebitda`).

Supported scopes:
- `CURRENT`        — facts/metrics for the same period.
- `PQ`             — prior quarter (one quarter earlier; rolls fy_year when needed).
- `PY`             — prior year, same quarter.
- `PY_PQ`          — two-quarter lag (current quarter four ago - 1).
- `TTM`            — sum of last four quarters (CURRENT + 3 priors).
- `TTM_AVG`        — average of last four quarters.
- `AVG_2_OPENING_CLOSING` — (CURRENT + PY) / 2 — used for asset-turnover style metrics.

Missing inputs return `None`; the formula evaluator short-circuits to `None`
for the whole metric. This mirrors the existing pipeline's "drop incomplete
metrics, never raise" behaviour.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.facts import FinancialLineItemDefinition, FinancialStatementFact
from app.models.intelligence import CalculatedMetric, MetricDefinition
from app.models.master import FinancialPeriod

logger = logging.getLogger(__name__)


_SUPPORTED_SCOPES = {
    "CURRENT",
    "PQ",
    "PY",
    "PY_PQ",
    "TTM",
    "TTM_AVG",
    "AVG_2_OPENING_CLOSING",
}


# Comparator-integrity guard: substrings in ``column_label`` that mark a fact
# as a YTD / half-year / nine-month aggregate. A PQ or PY lookup against
# these would divide a quarter by a year-to-date, producing the 700+%
# Revenue QoQ figures seen during the analyst review.
_AGGREGATE_COLUMN_TOKENS: tuple[str, ...] = (
    "ytd",
    "year to date",
    "year-to-date",
    "9m",
    "nine month",
    "nine-month",
    "h1",
    "half year",
    "half-year",
    "h2",
    "full year",
    "fy ",
    "annual",
)


def _is_aggregate_column(label: str | None) -> bool:
    if not label:
        return False
    needle = label.strip().lower()
    return any(token in needle for token in _AGGREGATE_COLUMN_TOKENS)


@dataclass
class _InputSpec:
    name: str
    code: str
    scope: str
    kind: str  # "fact" | "metric"

    @classmethod
    def from_dict(cls, d: dict) -> "_InputSpec":
        scope = (d.get("scope") or "CURRENT").upper()
        if scope not in _SUPPORTED_SCOPES:
            raise ValueError(f"Unsupported scope `{scope}`")
        return cls(
            name=d["name"],
            code=d["code"],
            scope=scope,
            kind=(d.get("kind") or "fact").lower(),
        )


class InputResolver:
    """Resolve a metric's declared inputs against the database.

    One resolver per pipeline run. Lookups are cached per
    `(company_id, period_id, code, kind)` so repeated metrics don't requery.
    """

    def __init__(self, db: Session, *, company_id: int, period_id: int) -> None:
        self._db = db
        self._company_id = company_id
        self._period_id = period_id
        self._period = db.get(FinancialPeriod, period_id)
        # Cache: (kind, period_id, code) -> numeric value or None
        self._cache: dict[tuple[str, int, str], float | None] = {}
        # Cache for line-item code -> def id to avoid repeated lookups in the
        # fact resolver.
        self._li_def_id_by_code: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------
    def resolve(self, declarations: Iterable[dict]) -> dict[str, float | int | None]:
        """Return `{name: value}` for every declared input."""
        out: dict[str, float | int | None] = {}
        for raw in declarations:
            try:
                spec = _InputSpec.from_dict(raw)
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed input declaration %s: %s", raw, exc)
                out[raw.get("name", "<unknown>")] = None
                continue
            out[spec.name] = self._lookup(spec)
        return out

    # ------------------------------------------------------------------
    # Scope dispatch
    # ------------------------------------------------------------------
    def _lookup(self, spec: _InputSpec) -> float | None:
        if self._period is None:
            return None
        if spec.scope == "CURRENT":
            return self._value(spec, self._period_id)
        if spec.scope == "PQ":
            pid = self._prior_quarter_id(self._period)
            if pid is None:
                return None
            return self._comparator_value(spec, pid, scope="PQ")
        if spec.scope == "PY":
            pid = self._prior_year_id(self._period)
            if pid is None:
                return None
            return self._comparator_value(spec, pid, scope="PY")
        if spec.scope == "PY_PQ":
            py = self._prior_year(self._period)
            pid = self._prior_quarter_id(py) if py else None
            if pid is None:
                return None
            return self._comparator_value(spec, pid, scope="PY_PQ")
        if spec.scope == "TTM":
            return self._ttm(spec, mode="sum")
        if spec.scope == "TTM_AVG":
            return self._ttm(spec, mode="avg")
        if spec.scope == "AVG_2_OPENING_CLOSING":
            cq = self._value(spec, self._period_id)
            py_id = self._prior_year_id(self._period)
            py = self._comparator_value(spec, py_id, scope="PY") if py_id else None
            if cq is None or py is None:
                return None
            return (cq + py) / 2
        return None

    def _comparator_value(
        self, spec: _InputSpec, period_id: int, *, scope: str
    ) -> float | None:
        """Read a PQ/PY/PY_PQ fact, refusing YTD/9M/H1 columns.

        If the only fact we have for the prior period is a year-to-date or
        nine-month aggregate, returning it would silently turn a QoQ ratio
        into a quarter-vs-YTD ratio (the root cause of the 708 %% Revenue
        QoQ on RELIANCE). Better to return ``None`` so the dependent metric
        is skipped — the signal simply does not fire.
        """
        if spec.kind == "fact":
            label = self._fact_column_label(spec.code, period_id)
            if _is_aggregate_column(label):
                logger.info(
                    "Skipping %s comparator for %s: prior fact lives in aggregate column %r",
                    scope, spec.code, label,
                )
                return None
        return self._value(spec, period_id)

    def _fact_column_label(self, code: str, period_id: int) -> str | None:
        li_def_id = self._li_def_id_by_code.get(code)
        if li_def_id is None:
            li_def_id = self._db.scalar(
                select(FinancialLineItemDefinition.line_item_def_id).where(
                    FinancialLineItemDefinition.normalized_code == code
                )
            )
            if li_def_id is None:
                return None
            self._li_def_id_by_code[code] = li_def_id
        return self._db.scalar(
            select(FinancialStatementFact.column_label).where(
                FinancialStatementFact.company_id == self._company_id,
                FinancialStatementFact.period_id == period_id,
                FinancialStatementFact.line_item_def_id == li_def_id,
                FinancialStatementFact.period_value_type == "CURRENT",
            )
        )

    # ------------------------------------------------------------------
    # Period walking
    # ------------------------------------------------------------------
    def _prior_quarter(self, period: FinancialPeriod | None) -> FinancialPeriod | None:
        if period is None or period.quarter is None:
            return None
        prev_q = period.quarter - 1
        prev_fy = period.fy_year
        if prev_q < 1:
            prev_q = 4
            prev_fy = period.fy_year - 1
        return self._db.scalar(
            select(FinancialPeriod).where(
                FinancialPeriod.fy_year == prev_fy,
                FinancialPeriod.quarter == prev_q,
                FinancialPeriod.period_type == period.period_type,
            )
        )

    def _prior_quarter_id(self, period: FinancialPeriod | None) -> int | None:
        p = self._prior_quarter(period)
        return p.period_id if p else None

    def _prior_year(self, period: FinancialPeriod | None) -> FinancialPeriod | None:
        if period is None or period.quarter is None:
            return None
        return self._db.scalar(
            select(FinancialPeriod).where(
                FinancialPeriod.fy_year == period.fy_year - 1,
                FinancialPeriod.quarter == period.quarter,
                FinancialPeriod.period_type == period.period_type,
            )
        )

    def _prior_year_id(self, period: FinancialPeriod | None) -> int | None:
        p = self._prior_year(period)
        return p.period_id if p else None

    # ------------------------------------------------------------------
    # Value lookups (cached)
    # ------------------------------------------------------------------
    def _value(self, spec: _InputSpec, period_id: int | None) -> float | None:
        if period_id is None:
            return None
        key = (spec.kind, period_id, spec.code)
        if key in self._cache:
            return self._cache[key]
        if spec.kind == "metric":
            value = self._metric_value(spec.code, period_id)
        else:
            value = self._fact_value(spec.code, period_id)
        self._cache[key] = value
        return value

    def _fact_value(self, code: str, period_id: int) -> float | None:
        li_def_id = self._li_def_id_by_code.get(code)
        if li_def_id is None:
            li_def_id = self._db.scalar(
                select(FinancialLineItemDefinition.line_item_def_id).where(
                    FinancialLineItemDefinition.normalized_code == code
                )
            )
            if li_def_id is None:
                return None
            self._li_def_id_by_code[code] = li_def_id
        row = self._db.scalar(
            select(FinancialStatementFact.value).where(
                FinancialStatementFact.company_id == self._company_id,
                FinancialStatementFact.period_id == period_id,
                FinancialStatementFact.line_item_def_id == li_def_id,
                FinancialStatementFact.period_value_type == "CURRENT",
            )
        )
        return float(row) if row is not None else None

    def _metric_value(self, code: str, period_id: int) -> float | None:
        """Read an upstream CalculatedMetric value, ignoring quarantined rows.

        A composite metric (e.g. ``revenue_yoy_growth_acceleration_pp``) that
        reads another metric must never inherit a value the bounds engine
        already flagged as implausible — otherwise a 708% Revenue QoQ would
        propagate one layer up and silently fire a downstream signal.
        """
        row = self._db.scalar(
            select(CalculatedMetric.metric_value)
            .join(MetricDefinition, MetricDefinition.metric_def_id == CalculatedMetric.metric_def_id)
            .where(
                CalculatedMetric.company_id == self._company_id,
                CalculatedMetric.period_id == period_id,
                MetricDefinition.metric_code == code,
                CalculatedMetric.is_quarantined.is_(False),
            )
            .order_by(CalculatedMetric.metric_id.desc())
            .limit(1)
        )
        return float(row) if row is not None else None

    # ------------------------------------------------------------------
    # TTM helpers
    # ------------------------------------------------------------------
    def _ttm(self, spec: _InputSpec, *, mode: str) -> float | None:
        period = self._period
        values: list[float] = []
        for _ in range(4):
            if period is None or period.quarter is None:
                return None
            v = self._value(spec, period.period_id)
            if v is None:
                return None
            values.append(v)
            period = self._prior_quarter(period)
        if not values:
            return None
        if mode == "avg":
            return sum(values) / len(values)
        return sum(values)
