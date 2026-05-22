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

from app.seed.seed_catalog import METRIC_DEFS, SIGNAL_DEFS
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
