"""Tests for Tier 0+1 signal and validation rules."""

from __future__ import annotations

from dataclasses import dataclass

from catalog_loader import load_catalog

from capital_nerve_logic import (
    accept_for_preferred_basis,
    attach_metric_provenance,
    build_raw_details,
    canonicalize_unit,
    compute_pipeline_metrics,
    dedupe_eps_values,
    earnings_card_metrics,
    interpret_metric_signals,
    is_blocking_check,
    resolve_unit,
    unit_from_text,
    validation_checks,
)


@dataclass
class _Row:
    fact_key: str
    status: str
    basis: str | None = None
    evidence: str = ""
    period: str | None = None
    document_id: str = "doc_1"


def test_dedupe_eps_prefers_basic():
    rows = [
        _Row("eps", "accepted", "standalone", evidence="- Basic | 22.76", period="Q4"),
        _Row("eps", "accepted", "standalone", evidence="- Diluted | 22.63", period="Q4"),
    ]
    out = dedupe_eps_values(
        rows,
        fact_key=lambda r: r.fact_key,
        evidence=lambda r: r.evidence,
        period=lambda r: r.period,
        basis=lambda r: r.basis,
        document_id=lambda r: r.document_id,
    )
    assert len(out) == 1
    assert "Basic" in out[0].evidence


def test_accept_prefers_consolidated_then_fallback():
    rows = [
        _Row("revenue", "accepted", "standalone"),
        _Row("revenue", "accepted", "consolidated"),
    ]
    strict = accept_for_preferred_basis(rows, "consolidated")
    assert len(strict) == 1
    assert strict[0].basis == "consolidated"

    only_sa = [_Row("revenue", "accepted", "standalone")]
    fb = accept_for_preferred_basis(only_sa, "consolidated")
    assert len(fb) == 1
    assert fb[0].basis == "standalone"


def test_revenue_decline_qoq_from_catalog():
    metrics = [
        {"metric_key": "revenue_qoq_growth", "value": -5.26, "derivation": "formula"},
        {"metric_key": "pat_growth_qoq", "value": 0.87, "derivation": "formula"},
    ]
    sigs = interpret_metric_signals(metrics)
    keys = {s["signal_key"] for s in sigs}
    assert "revenue_decline_qoq" in keys
    assert "no_material_change" not in keys


def test_earnings_card_includes_margin():
    metrics = [
        {"fact_key": "revenue_from_operations", "value": 100, "derivation": "raw"},
        {"metric_key": "ebitda_margin", "value": 12, "derivation": "margin"},
        {"metric_key": "revenue_qoq_pct", "value": -4, "derivation": "qoq"},
    ]
    card = earnings_card_metrics(metrics)
    keys = [
        m.get("fact_key") or m.get("metric_key")
        for m in card
    ]
    assert "ebitda_margin" in keys
    assert "revenue_qoq_pct" in keys


def test_build_raw_details_canonicalizes_keys():
    rows = [
        {
            "status": "accepted",
            "fact_key": "revenue",
            "numeric_value": 110.0,
            "unit": "crore",
            "evidence": "Revenue",
            "document_id": "doc_1",
        }
    ]
    details = build_raw_details(rows)
    assert "revenue_from_operations" in details
    assert details["revenue_from_operations"]["numeric_value"] == 110.0


def test_attach_metric_provenance_yoy():
    catalog = load_catalog(reload=True)

    def resolve(fact_key: str, scope: str) -> dict:
        if fact_key == "revenue_from_operations" and scope == "CURRENT":
            return {"value": 110.0, "period": "Q1 FY26", "source": "filing"}
        if fact_key == "revenue_from_operations" and scope == "PY":
            return {"value": 100.0, "period": "Q1 FY25", "source": "database"}
        return {}

    metrics = [
        {
            "metric_key": "revenue_yoy_growth",
            "value": 10.0,
            "derivation": "formula",
        }
    ]
    out = attach_metric_provenance(metrics, catalog, resolve)
    roles = {d["role"] for d in out[0]["input_details"]}
    assert roles == {"current", "prior_year"}
    assert out[0]["formula_evaluated"]


def test_compute_pipeline_metrics_matches_catalog():
    metrics = compute_pipeline_metrics(
        {"revenue": 110.0, "ebitda": 22.0},
        {"revenue": 100.0, "ebitda": 20.0},
        {"revenue": 105.0, "ebitda": 21.0},
        period_label="Q1 FY26",
    )
    by_key = {m["metric_key"]: m for m in metrics if "metric_key" in m}
    assert by_key["revenue_yoy_growth"]["value"] == 10.0
    assert by_key["ebitda_margin"]["value"] == 20.0
    assert by_key["revenue_yoy_pct"]["value"] == 10.0


def test_basis_mismatch_is_non_blocking():
    checks = validation_checks(
        {
            "numeric_value": 1.0,
            "fact_key": "revenue",
            "evidence": "x",
            "basis": "standalone",
            "confidence": 0.9,
        },
        "consolidated",
    )
    assert checks == ["basis_mismatch"]
    assert not is_blocking_check("basis_mismatch")


def test_canonicalize_unit_aliases():
    assert canonicalize_unit("INR_cr") == "crore"
    assert canonicalize_unit("lacs") == "lakh"
    assert canonicalize_unit("pct") == "percent"


def test_unit_from_text_detects_crores_heading():
    assert unit_from_text("(₹ in crores)") == "crore"
    assert unit_from_text("(` in crores)") == "crore"


def test_resolve_unit_prefers_chunk_heading_for_revenue():
    chunks = [
        {
            "chunk_id": "chk_1",
            "heading": "(₹ in crores)",
            "text": "TOTAL INCOME | 40,898.41",
        }
    ]
    unit, hint = resolve_unit(
        {"unit": "lakh"},
        chunks,
        "TOTAL INCOME | 40,898.41",
        "40,898.41",
        "revenue_from_operations",
    )
    assert unit == "crore"
    assert hint == "crore"


def test_resolve_unit_eps_uses_rs_not_crore_heading():
    chunks = [
        {
            "chunk_id": "chk_1",
            "heading": "(₹ in crores)",
            "text": "- Basic | 18.73",
        }
    ]
    unit, hint = resolve_unit(
        {"unit": "crore"},
        chunks,
        "- Basic | 18.73",
        "18.73",
        "eps",
    )
    assert unit == "Rs"
    assert hint == "crore"


def test_unit_heading_mismatch_flags_wrong_llm_unit():
    checks = validation_checks(
        {
            "numeric_value": 100.0,
            "fact_key": "revenue_from_operations",
            "evidence": "TOTAL INCOME | 100",
            "confidence": 0.9,
            "unit": "lakh",
            "chunk_unit_hint": "crore",
        },
        "consolidated",
    )
    assert "unit_heading_mismatch" in checks
