"""Deterministic metrics, validation, and signal rules for Capital Nerve."""

from __future__ import annotations

import re
from typing import Any, Callable, TypeVar

T = TypeVar("T")

ResolveProvenance = Callable[[str, str], dict[str, Any] | None]

CANONICAL_UNITS: tuple[str, ...] = ("crore", "lakh", "million", "Rs", "percent", "x")
CANONICAL_UNIT_ENUM: list[str | None] = [*CANONICAL_UNITS, None]

_NON_BLOCKING_CHECKS = frozenset(
    {"basis_mismatch", "unit_heading_mismatch", "unit_fact_mismatch"}
)

_UNIT_ALIASES: dict[str, str] = {
    "crores": "crore",
    "cr": "crore",
    "cr.": "crore",
    "inr cr": "crore",
    "inr_cr": "crore",
    "inr crore": "crore",
    "inr crores": "crore",
    "lakhs": "lakh",
    "lacs": "lakh",
    "lac": "lakh",
    "lakh": "lakh",
    "millions": "million",
    "mn": "million",
    "pct": "percent",
    "%": "percent",
    "rs.": "Rs",
    "inr": "Rs",
    "rupees": "Rs",
    "rupee": "Rs",
    "times": "x",
}

_CATALOG_FIXED_UNITS = frozenset({"Rs", "percent"})
_AMOUNT_FACT_KEYS = frozenset(
    {
        "revenue",
        "revenue_from_operations",
        "ebitda",
        "pat",
        "net_profit",
        "other_income",
        "pbt",
        "exceptional_items",
        "finance_cost",
        "tax_expense",
        "cfo",
        "operating_profit",
        "interest_earned",
    }
)


def dedupe_eps_values(
    values: list[T],
    *,
    fact_key: Callable[[T], str] = lambda v: v.fact_key,
    evidence: Callable[[T], str | None] = lambda v: v.evidence,
    period: Callable[[T], str | None] = lambda v: v.period,
    basis: Callable[[T], str | None] = lambda v: v.basis,
    document_id: Callable[[T], str] = lambda v: v.document_id,
) -> list[T]:
    """Keep one EPS per (period, basis, document): prefer basic over diluted."""
    eps_rows = [v for v in values if fact_key(v) == "eps"]
    if len(eps_rows) <= 1:
        return values

    def eps_rank(v: T) -> int:
        ev = (evidence(v) or "").lower()
        if "diluted" in ev:
            return 2
        if "basic" in ev:
            return 0
        return 1

    best: dict[tuple[Any, ...], T] = {}
    for v in eps_rows:
        key = (period(v), basis(v), document_id(v))
        prev = best.get(key)
        if prev is None or eps_rank(v) < eps_rank(prev):
            best[key] = v

    kept_ids = {id(v) for v in best.values()}
    return [v for v in values if fact_key(v) != "eps" or id(v) in kept_ids]


def canonicalize_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    key = unit.strip()
    if not key:
        return None
    lowered = key.lower()
    if key in CANONICAL_UNITS:
        return key
    if lowered in _UNIT_ALIASES:
        return _UNIT_ALIASES[lowered]
    if lowered in CANONICAL_UNITS:
        return lowered
    if lowered.endswith(" cr") or lowered.endswith(" crore") or lowered.endswith(" crores"):
        return "crore"
    if "lakh" in lowered or "lac" in lowered:
        return "lakh"
    if "million" in lowered or lowered == "mn":
        return "million"
    return key


def unit_from_text(text: str | None) -> str | None:
    if not text:
        return None
    lowered = text.lower()
    if "crore" in lowered or re.search(r"\bin\s+cr\b", lowered):
        return "crore"
    if "lakh" in lowered or re.search(r"\blac[s]?\b", lowered):
        return "lakh"
    if "million" in lowered:
        return "million"
    return None


def catalog_fact_unit(fact_key: str, catalog: Any | None = None) -> str | None:
    from catalog_loader import canonical_fact_key, get_catalog

    catalog = catalog or get_catalog()
    canonical = canonical_fact_key(fact_key) or fact_key
    spec = catalog.facts.get(canonical)
    if not spec:
        return None
    return spec.get("unit")


def unit_from_evidence(evidence: str, fact_key: str) -> str | None:
    ev = (evidence or "").lower()
    canonical = fact_key
    if canonical in {"eps", "eps_basic"} or "eps" in ev or "per share" in ev:
        return "Rs"
    if "%" in evidence or "ratio" in ev or "annualized" in ev:
        return "percent"
    return None


def find_chunk_id(
    chunks: list[dict[str, Any]],
    evidence: str,
    raw_value: str,
) -> str:
    for size in (120, 80, 40):
        needle = evidence[:size].strip()
        if needle:
            for chunk in chunks:
                if needle in chunk["text"]:
                    return chunk["chunk_id"]
    if raw_value:
        for chunk in chunks:
            if raw_value in chunk["text"]:
                return chunk["chunk_id"]
    return chunks[0]["chunk_id"] if chunks else ""


def chunk_unit_hint(
    chunks: list[dict[str, Any]],
    evidence: str,
    raw_value: str,
) -> str | None:
    chunk_id = find_chunk_id(chunks, evidence, raw_value)
    for chunk in chunks:
        if chunk["chunk_id"] != chunk_id:
            continue
        for source in (chunk.get("heading"), (chunk.get("text") or "")[:240]):
            unit = unit_from_text(source)
            if unit:
                return unit
    return None


def resolve_unit(
    entry: dict[str, Any],
    chunks: list[dict[str, Any]],
    evidence: str,
    raw_value: str,
    fact_key: str,
    *,
    catalog: Any | None = None,
) -> tuple[str | None, str | None]:
    """Resolve a canonical unit and the chunk heading hint used."""
    from catalog_loader import canonical_fact_key

    canonical = canonical_fact_key(fact_key) or fact_key
    catalog_unit = catalog_fact_unit(canonical, catalog)
    hint = chunk_unit_hint(chunks, evidence, raw_value)
    llm_unit = canonicalize_unit(entry.get("unit"))

    if catalog_unit in _CATALOG_FIXED_UNITS:
        return catalog_unit, hint

    evidence_unit = unit_from_evidence(evidence, canonical)
    if evidence_unit:
        return evidence_unit, hint

    if canonical in _AMOUNT_FACT_KEYS or (catalog_unit == "crore"):
        if hint:
            return hint, hint
        if llm_unit:
            return llm_unit, hint
        if catalog_unit:
            return canonicalize_unit(catalog_unit), hint
        return None, hint

    if llm_unit:
        return llm_unit, hint
    if catalog_unit:
        return canonicalize_unit(catalog_unit), hint
    return None, hint


def unit_validation_checks(row: dict[str, Any]) -> list[str]:
    checks: list[str] = []
    unit = canonicalize_unit(row.get("unit"))
    fact_key = row.get("fact_key") or ""
    expected = catalog_fact_unit(fact_key)
    hint = canonicalize_unit(row.get("chunk_unit_hint"))

    if expected in _CATALOG_FIXED_UNITS and unit and unit != expected:
        checks.append("unit_fact_mismatch")

    if (
        hint
        and unit
        and hint != unit
        and fact_key in _AMOUNT_FACT_KEYS
        and expected != "Rs"
    ):
        checks.append("unit_heading_mismatch")

    return checks


def validation_checks(
    row: dict[str, Any],
    preferred_basis: str,
) -> list[str]:
    checks: list[str] = []
    if row.get("numeric_value") is None:
        checks.append("non_numeric")
        return checks

    v = float(row["numeric_value"])
    if v < 0 and row.get("fact_key") in {"revenue", "ebitda", "net_profit", "revenue_from_operations", "pat"}:
        checks.append("unexpected_negative")
    if not row.get("evidence"):
        checks.append("missing_evidence")
    if row.get("confidence", 0) < 0.5:
        checks.append("low_confidence")

    row_basis = (row.get("basis") or "").strip().lower()
    pref = preferred_basis.strip().lower()
    if row_basis and row_basis != pref:
        checks.append("basis_mismatch")

    checks.extend(unit_validation_checks(row))
    return checks


def is_blocking_check(check: str) -> bool:
    return check not in _NON_BLOCKING_CHECKS


def accept_for_preferred_basis(
    validated: list[Any],
    preferred_basis: str,
    *,
    status: Callable[[Any], str] = lambda v: v.status,
    basis: Callable[[Any], str | None] = lambda v: v.basis,
) -> list[Any]:
    """Accept rows matching preferred basis; fall back to standalone if consolidated missing."""
    pref = preferred_basis.strip().lower()
    strict = [
        v
        for v in validated
        if status(v) == "accepted" and (basis(v) or pref).strip().lower() == pref
    ]
    if strict:
        return strict
    if pref == "consolidated":
        return [
            v
            for v in validated
            if status(v) == "accepted"
            and (basis(v) or "").strip().lower() == "standalone"
        ]
    return [v for v in validated if status(v) == "accepted"]


def build_raw_details(
    values: list[dict[str, Any]],
    *,
    status: str = "accepted",
) -> dict[str, dict[str, Any]]:
    """Build raw_details for compute_catalog_metrics from validated value rows."""
    from catalog_loader import canonical_fact_key

    out: dict[str, dict[str, Any]] = {}
    for row in values:
        if row.get("status") != status:
            continue
        storage_key = row.get("fact_key")
        if not storage_key:
            continue
        canonical = canonical_fact_key(storage_key) or storage_key
        out[canonical] = {
            "numeric_value": float(row["numeric_value"]),
            "unit": canonicalize_unit(row.get("unit")),
            "evidence": row.get("evidence"),
            "source_document_id": row.get("document_id"),
        }
    return out


def _scope_role(
    scope: str,
    *,
    metric_key: str,
    input_index: int,
    total_inputs: int,
) -> str:
    scope_upper = scope.upper()
    if scope_upper == "PY":
        return "prior_year"
    if scope_upper == "PQ":
        return "prior_quarter"
    if "margin" in metric_key and total_inputs == 2 and scope_upper == "CURRENT":
        return "numerator" if input_index == 0 else "denominator"
    return "current"


def attach_metric_provenance(
    metrics: list[dict[str, Any]],
    catalog: Any,
    resolve_provenance: ResolveProvenance | None,
) -> list[dict[str, Any]]:
    """Attach input_details and formula_evaluated to catalog-derived metrics."""
    if resolve_provenance is None:
        return metrics

    from catalog_engine import catalog_metric_key

    for metric in metrics:
        derivation = metric.get("derivation")
        if derivation not in ("formula", "alias", "margin"):
            continue

        metric_key = metric.get("metric_key")
        if not metric_key:
            continue

        spec_key = catalog_metric_key(metric_key)
        spec = catalog.metrics.get(spec_key)
        if not spec:
            continue

        inputs_spec = spec.get("inputs") or []
        input_details: list[dict[str, Any]] = []
        for idx, inp in enumerate(inputs_spec):
            fact_key = inp["fact_key"]
            scope = inp["scope"]
            prov = resolve_provenance(fact_key, scope)
            role = _scope_role(
                scope,
                metric_key=spec_key,
                input_index=idx,
                total_inputs=len(inputs_spec),
            )
            detail: dict[str, Any] = {
                "fact_key": fact_key,
                "role": role,
            }
            if prov:
                detail.update(prov)
            elif metric.get("value") is not None and scope.upper() == "CURRENT":
                detail["value"] = metric["value"]
            input_details.append(detail)

        if input_details:
            metric["input_details"] = input_details
        if not metric.get("formula_evaluated") and spec.get("formula"):
            metric["formula_evaluated"] = spec["formula"]
        if derivation == "formula" and "margin" in spec_key:
            metric["derivation"] = "margin"

    return metrics


def compute_pipeline_metrics(
    base: dict[str, float],
    prior_year: dict[str, float],
    prior_quarter: dict[str, float],
    *,
    period_label: str | None,
    raw_details: dict[str, dict[str, Any]] | None = None,
    prior_year_details: dict[str, dict[str, Any]] | None = None,
    prior_quarter_details: dict[str, dict[str, Any]] | None = None,
    resolve_provenance: ResolveProvenance | None = None,
    catalog: Any | None = None,
) -> list[dict[str, Any]]:
    """Compute metrics via catalog_engine with optional provenance enrichment."""
    from catalog_engine import ScopeContext, compute_catalog_metrics
    from catalog_loader import get_catalog

    catalog = catalog or get_catalog()
    label = period_label or ""

    if raw_details is not None:
        ctx = ScopeContext.from_fact_details(
            raw_details,
            prior_year_details or {},
            prior_quarter_details or {},
        )
    else:
        ctx = ScopeContext(
            current=base,
            prior_year=prior_year,
            prior_quarter=prior_quarter,
        )
    metrics = compute_catalog_metrics(
        ctx,
        period_label=label,
        raw_details=raw_details,
        catalog=catalog,
    )
    return attach_metric_provenance(metrics, catalog, resolve_provenance)


def earnings_card_metrics(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw_metrics = [m for m in metrics if m.get("derivation") == "raw"]
    derived = [
        m
        for m in metrics
        if m.get("derivation") in ("yoy", "qoq", "formula", "alias")
    ]
    margins = [
        m
        for m in metrics
        if m.get("derivation") == "margin" or "margin" in m.get("metric_key", "")
    ]
    top_raw = sorted(raw_metrics, key=lambda m: abs(m.get("value", 0)), reverse=True)[:5]
    return top_raw + derived + margins


def interpret_metric_signals(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return signal payloads (without signal_id) from calculated metrics."""
    from catalog_engine import evaluate_catalog_signals

    return evaluate_catalog_signals(metrics)
