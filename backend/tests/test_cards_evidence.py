"""Card evidence input resolution (formula name → extracted fact code)."""
from __future__ import annotations

from types import SimpleNamespace

from app.services.pipeline.cards import _match_extracted_for_metric_input


def _ev(code: str) -> SimpleNamespace:
    return SimpleNamespace(normalized_label=code, extracted_value_id=1)


def test_concall_input_s_resolves_to_fact_code():
    by_code = {"concall_capex_intent_score": _ev("concall_capex_intent_score")}
    inputs = [{"name": "s", "code": "concall_capex_intent_score", "scope": "CURRENT"}]
    got = _match_extracted_for_metric_input(by_code, "s", inputs)
    assert got is not None
    assert got.normalized_label == "concall_capex_intent_score"


def test_prior_quarter_input_returns_none():
    by_code = {"concall_confidence_score": _ev("concall_confidence_score")}
    inputs = [
        {"name": "now", "code": "concall_confidence_score", "scope": "CURRENT"},
        {"name": "pq", "code": "concall_confidence_score", "scope": "PQ"},
    ]
    assert _match_extracted_for_metric_input(by_code, "pq", inputs) is None
    assert _match_extracted_for_metric_input(by_code, "now", inputs) is not None


def test_revenue_alias_still_works_without_inputs_decl():
    by_code = {"revenue_from_operations": _ev("revenue_from_operations")}
    got = _match_extracted_for_metric_input(by_code, "revenue", [])
    assert got is not None
