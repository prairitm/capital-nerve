"""Static checks on `seed_catalog.METRIC_DEFS` / `SIGNAL_DEFS`.

These tests do NOT touch the database. They make sure every formula parses
through the safe AST evaluator, every input declaration uses a supported
scope, every signal rule references metrics that actually exist in
`METRIC_DEFS`, and the metric DAG is acyclic.

If you add a new metric or signal in `seed_catalog.py`, run::

    cd backend && pytest tests/test_seed_config.py
"""
from __future__ import annotations

import pytest

from app.seed.seed_catalog import METRIC_DEFS, SIGNAL_DEFS, _format_rule_text
from app.services.pipeline.formula import FormulaError, evaluate
from app.services.pipeline.inputs import _SUPPORTED_SCOPES


METRIC_CODES = {m["code"] for m in METRIC_DEFS}


def _input_names(spec: dict) -> set[str]:
    return {i["name"] for i in spec["inputs"]}


def test_every_metric_formula_parses():
    """Each formula must be valid under the AST allowlist using its declared inputs."""
    for spec in METRIC_DEFS:
        if not spec["formula"]:
            continue
        # Feed dummy 1.0 for every declared input — we only care about syntax.
        dummy_inputs = {n: 1.0 for n in _input_names(spec)}
        try:
            evaluate(spec["formula"], dummy_inputs)
        except FormulaError as exc:
            pytest.fail(f"metric `{spec['code']}` formula failed to parse: {exc}")


def test_every_input_uses_a_supported_scope():
    for spec in METRIC_DEFS:
        for inp in spec["inputs"]:
            scope = (inp.get("scope") or "CURRENT").upper()
            assert scope in _SUPPORTED_SCOPES, (
                f"metric `{spec['code']}` input `{inp['name']}` uses unknown scope `{scope}`"
            )


def test_metric_dependencies_resolve():
    for spec in METRIC_DEFS:
        for dep in spec["deps"]:
            assert dep in METRIC_CODES, (
                f"metric `{spec['code']}` declares missing dependency `{dep}`"
            )
        # Inputs with kind="metric" must also be declared in METRIC_CODES.
        for inp in spec["inputs"]:
            if (inp.get("kind") or "fact") == "metric":
                assert inp["code"] in METRIC_CODES, (
                    f"metric `{spec['code']}` input `{inp['name']}` references unknown metric `{inp['code']}`"
                )


def test_metric_dag_is_acyclic():
    """Light Kahn check: dropping in-degree must drain everything."""
    deps = {m["code"]: set(m["deps"]) for m in METRIC_DEFS}
    in_degree = {code: len(d & METRIC_CODES) for code, d in deps.items()}
    queue = [c for c, d in in_degree.items() if d == 0]
    seen: set[str] = set()
    children: dict[str, list[str]] = {c: [] for c in METRIC_CODES}
    for code, d in deps.items():
        for parent in d & METRIC_CODES:
            children[parent].append(code)

    while queue:
        c = queue.pop(0)
        if c in seen:
            continue
        seen.add(c)
        for child in children[c]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)
    assert seen == METRIC_CODES, f"Cycle in metric DAG; missed: {METRIC_CODES - seen}"


def test_signal_rules_reference_known_metrics():
    """Every leaf in every rule must point to a metric the engine knows about."""

    def walk(rule: dict) -> set[str]:
        if not rule:
            return set()
        if "all" in rule:
            return set().union(*(walk(c) for c in rule["all"]))
        if "any" in rule:
            return set().union(*(walk(c) for c in rule["any"]))
        if "not" in rule:
            return walk(rule["not"])
        out = set()
        if rule.get("metric"):
            out.add(rule["metric"])
        if rule.get("metric_ref"):
            out.add(rule["metric_ref"])
        return out

    for sig in SIGNAL_DEFS:
        for code in walk(sig["rule"]):
            assert code in METRIC_CODES, (
                f"signal `{sig['code']}` references unknown metric `{code}`"
            )


# ---------------------------------------------------------------------------
# Phase 1A — metric bounds + rule_text
# ---------------------------------------------------------------------------


def test_margin_and_growth_metrics_carry_sanity_bounds():
    """Margin / growth metrics that the user reported as breaking must declare bounds."""
    must_have_bounds = {
        "ebitda_margin",
        "pat_margin",
        "primary_segment_margin",
        "revenue_yoy_growth",
        "revenue_qoq_growth",
        "other_income_to_pbt",
    }
    by_code = {m["code"]: m for m in METRIC_DEFS}
    for code in must_have_bounds:
        spec = by_code[code]
        assert spec.get("bounds") is not None, f"metric `{code}` missing bounds"
        lo, hi = spec["bounds"]
        assert (lo is None or hi is None or lo < hi), (
            f"metric `{code}` bounds are inverted: {spec['bounds']}"
        )


def test_format_rule_text_handles_grammar_variants():
    """Leaf, all, any, not, and metric_ref must all produce readable text."""
    leaf = {"metric": "ebitda_margin", "operator": ">", "threshold": 20}
    assert _format_rule_text(leaf) == "ebitda_margin > 20"

    composite_all = {"all": [leaf, {"metric": "pat_margin", "operator": "<", "threshold": 8}]}
    assert _format_rule_text(composite_all) == "ebitda_margin > 20 and pat_margin < 8"

    composite_any = {"any": [leaf, {"metric": "pat_margin", "operator": "<", "threshold": 8}]}
    assert _format_rule_text(composite_any) == "ebitda_margin > 20 or pat_margin < 8"

    negated = {"not": leaf}
    assert _format_rule_text(negated) == "not (ebitda_margin > 20)"

    ref = {"metric": "receivables_growth_yoy", "operator": ">", "metric_ref": "revenue_yoy_growth"}
    assert _format_rule_text(ref) == "receivables_growth_yoy > revenue_yoy_growth"

    # Empty / manual signals should yield None.
    assert _format_rule_text({}) is None


def test_every_evaluable_signal_produces_rule_text():
    """Numeric signals must carry a non-empty rule_text so the UI can show it."""
    for sig in SIGNAL_DEFS:
        rule = sig["rule"]
        if not rule:
            continue
        text = _format_rule_text(rule)
        assert text, f"signal `{sig['code']}` produced empty rule_text from rule {rule}"


# ---------------------------------------------------------------------------
# Metric ontology (metric_kind) + acceleration metric
# ---------------------------------------------------------------------------


def test_every_metric_declares_a_kind():
    """Every metric must declare a kind so the feed badge is never blank."""
    allowed = {"financial", "model_score", "composite"}
    for spec in METRIC_DEFS:
        assert spec["kind"] in allowed, (
            f"metric `{spec['code']}` has unknown kind `{spec['kind']}`"
        )


def test_concall_scores_are_model_kind():
    """Concall lexicon scores must be labelled model_score so they don't pose as financial metrics."""
    by_code = {m["code"]: m for m in METRIC_DEFS}
    for code in (
        "concall_capex_intent_score",
        "concall_margin_tone_score",
        "concall_demand_score",
        "concall_cost_pressure_score",
        "concall_pricing_power_score",
    ):
        assert by_code[code]["kind"] == "model_score", (
            f"`{code}` should be kind=model_score"
        )


def test_acceleration_metric_is_composite():
    """The acceleration metric reads its own metric at PQ — it must be composite."""
    by_code = {m["code"]: m for m in METRIC_DEFS}
    accel = by_code["revenue_yoy_growth_acceleration_pp"]
    assert accel["kind"] == "composite"
    assert accel["unit"] == "pp"
    # Must depend on revenue_yoy_growth via kind=metric inputs at CURRENT + PQ.
    kinds_scopes = {(i["scope"], i.get("kind")) for i in accel["inputs"]}
    assert ("CURRENT", "metric") in kinds_scopes
    assert ("PQ", "metric") in kinds_scopes


def test_metric_descriptions_cover_analyst_set() -> None:
    """Phase 2A: top metrics used on feed / trend charts have registry copy."""
    from app.seed.seed_catalog import METRIC_DESCRIPTIONS

    required = {
        "revenue_yoy_growth",
        "revenue_qoq_growth",
        "revenue_yoy_growth_acceleration_pp",
        "pat_margin",
        "ebitda_margin",
        "primary_segment_margin",
    }
    assert required <= set(METRIC_DESCRIPTIONS.keys())
    for code in required:
        assert len(METRIC_DESCRIPTIONS[code]) >= 40


def test_revenue_acceleration_signal_uses_real_acceleration_metric():
    """The signal previously fired on a YoY level threshold; now must use pp delta."""
    by_code = {s["code"]: s for s in SIGNAL_DEFS}
    rule = by_code["revenue_acceleration"]["rule"]
    assert rule == {
        "metric": "revenue_yoy_growth_acceleration_pp",
        "operator": ">",
        "threshold": 5,
    }
